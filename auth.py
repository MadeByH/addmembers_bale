from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from datetime import datetime, timedelta
from jose import jwt
from pathlib import Path
import asyncio
import base64
import os

from aiobale import Client, Dispatcher

from . import models, schemas
from .db import get_async_db
from .config import settings

router = APIRouter(prefix="/auth", tags=["Authentication"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")

# ============================================================
# JWT
# ============================================================

def create_access_token(data: dict, expires_delta: int = 3600 * 24 * 7):
    payload = data.copy()
    expire = datetime.utcnow() + timedelta(seconds=expires_delta)
    payload.update({"exp": expire})
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


async def get_current_account(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_async_db)
):
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        account_id = int(payload.get("account_id"))
    except Exception:
        raise HTTPException(status_code=401, detail="توکن نامعتبر است")

    stmt = (
        select(models.Account)
        .where(models.Account.id == account_id)
        .options(selectinload(models.Account.owner))
    )

    res = await db.execute(stmt)
    account = res.scalar_one_or_none()

    if not account:
        raise HTTPException(status_code=401, detail="اکانت پیدا نشد")

    return account


# ============================================================
# LOGIN STATE
# ============================================================

SESSION_DIR = Path("session.bale")
SESSION_DIR.mkdir(exist_ok=True)

pending_auth: dict[str, dict] = {}
lock = asyncio.Lock()

# ============================================================
# START LOGIN
# ============================================================

@router.post("/start", response_model=schemas.StartLoginResponse)
async def start_login(
    data: schemas.StartLoginRequest,
    db: AsyncSession = Depends(get_async_db)
):
    phone = data.phone
    owner_id = data.owner_id

    # check owner exists
    stmt = select(models.User).where(models.User.id == owner_id)
    res = await db.execute(stmt)
    owner = res.scalar_one_or_none()

    if not owner:
        raise HTTPException(404, "کاربر پیدا نشد")

    session_file = SESSION_DIR / f"{phone}.bale"

    if session_file.exists():
        try:
            os.remove(session_file)
        except:
            pass

    async with lock:

        # cleanup old login
        if phone in pending_auth:
            old = pending_auth.pop(phone)
            try:
                await old["client"].stop()
            except:
                pass

        dispatcher = Dispatcher()
        client = Client(dispatcher, session_file=str(session_file))

        try:
            res = await client.start_phone_auth(phone)
        except Exception as e:
            raise HTTPException(500, f"خطا در ارسال کد: {str(e)}")

        pending_auth[phone] = {
            "client": client,
            "tx": res.transaction_hash,
            "owner_id": owner_id
        }

    return schemas.StartLoginResponse(
        ok=True,
        transaction_hash=res.transaction_hash,
        message="کد ارسال شد"
    )


# ============================================================
# CONFIRM CODE
# ============================================================

@router.post("/confirm", response_model=schemas.TokenData)
async def confirm_code(
    data: schemas.ConfirmCodeRequest,
    db: AsyncSession = Depends(get_async_db)
):
    phone = data.phone
    code = data.code

    async with lock:
        entry = pending_auth.pop(phone, None)

    if not entry:
        raise HTTPException(400, "ابتدا start را اجرا کنید")

    client: Client = entry["client"]
    tx = entry["tx"]
    owner_id = entry["owner_id"]

    try:
        await client.validate_code(code, tx)

    except Exception as e:
        msg = str(e)

        if "PHONE_CODE_INVALID" in msg:
            raise HTTPException(400, "کد اشتباه است")

        if "PHONE_CODE_EXPIRED" in msg:
            raise HTTPException(400, "کد منقضی شده")

        if "FLOOD_WAIT" in msg:
            raise HTTPException(429, "تلاش زیاد، بعداً امتحان کنید")

        raise HTTPException(500, "خطا در تایید کد")

    # read session file
    session_file = SESSION_DIR / f"{phone}.bale"

    if not session_file.exists():
        raise HTTPException(500, "session ساخته نشد")

    session_data = base64.b64encode(session_file.read_bytes()).decode()

    # save account
    stmt = select(models.Account).where(
        models.Account.phone == phone,
        models.Account.owner_id == owner_id
    )

    res = await db.execute(stmt)
    account = res.scalar_one_or_none()

    if not account:
        account = models.Account(
            phone=phone,
            owner_id=owner_id,
            session_data=session_data,
            is_blocked=False
        )
        db.add(account)

    else:
        account.session_data = session_data
        account.is_blocked = False

    await db.commit()
    await db.refresh(account)

    token = create_access_token({"account_id": account.id})

    return schemas.TokenData(
        access_token=token,
        token_type="bearer"
    )


# ============================================================
# ME
# ============================================================

@router.get("/me", response_model=schemas.Account)
async def me(account: models.Account = Depends(get_current_account)):
    return account
