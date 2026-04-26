from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta
from jose import jwt
from pathlib import Path
import json
import asyncio
import base64
import os
import hashlib
import hmac
from urllib.parse import parse_qs
from pydantic import BaseModel
from typing import Optional

from aiobale import Client, Dispatcher

from . import models, schemas
from .db import get_async_db
from .config import settings

router = APIRouter(prefix="/auth", tags=["Authentication"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")

BOT_TOKEN = settings.BOT_TOKEN


# ============================================================
# INIT DATA VALIDATION (MiniApp)
# ============================================================

def validate_init_data(init_data: str) -> dict:
    parsed = parse_qs(init_data, strict_parsing=True)
    hash_received = parsed.pop("hash")[0]

    data_check_string = "\n".join(
        f"{k}={v[0]}" for k, v in sorted(parsed.items())
    )

    secret_key = hashlib.sha256(
        ("WebAppData" + BOT_TOKEN).encode()
    ).digest()

    calculated_hash = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256
    ).hexdigest()

    if calculated_hash != hash_received:
        raise HTTPException(401, "initData نامعتبر است")

    return {k: v[0] for k, v in parsed.items()}


# ============================================================
# JWT
# ============================================================

def create_jwt(user_id: int, expires: int = 60 * 60 * 24 * 7):
    payload = {
        "user_id": user_id,
        "exp": datetime.utcnow() + timedelta(seconds=expires),
    }

    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_async_db),
):
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        user_id = int(payload["user_id"])
    except Exception:
        raise HTTPException(401, "توکن نامعتبر است")

    user = await db.scalar(
        select(models.User).where(models.User.id == user_id)
    )

    if not user:
        raise HTTPException(401, "کاربر پیدا نشد")

    return user


# ============================================================
# SESSION STORAGE
# ============================================================

SESSION_DIR = Path("session.bale")
SESSION_DIR.mkdir(exist_ok=True)

pending_auth: dict[str, dict] = {}
lock = asyncio.Lock()


# ============================================================
# MINIAPP LOGIN
# ============================================================

class InitDataSchema(BaseModel):
    init_data: str


@router.post("/check")
async def check_user(
    data: InitDataSchema,
    db: AsyncSession = Depends(get_async_db),
):
    validated = validate_init_data(data.init_data)

    bale_user = json.loads(validated["user"])
    bale_user_id = bale_user["id"]

    user = await db.scalar(
        select(models.User).where(models.User.bale_user_id == bale_user_id)
    )

    if not user:
        user = models.User(bale_user_id=bale_user_id)
        db.add(user)
        await db.commit()
        await db.refresh(user)

    token = create_jwt(user.id)

    return {
        "has_account": True, "token": token
    }


# ============================================================
# START LOGIN ACCOUNT
# ============================================================

@router.post("/start", response_model=schemas.StartLoginResponse)
async def start_login(
    data: schemas.StartLoginRequest,
    user: models.User = Depends(get_current_user),
):
    phone = data.phone

    session_file = SESSION_DIR / f"{phone}.bale"

    if session_file.exists():
        try:
            os.remove(session_file)
        except:
            pass

    async with lock:

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
            "user_id": user.id
        }

    return schemas.StartLoginResponse(
        ok=True,
        transaction_hash=res.transaction_hash,
        message="کد ارسال شد"
    )


# ============================================================
# CONFIRM LOGIN
# ============================================================

@router.post("/confirm")
async def confirm_code(
    data: schemas.ConfirmCodeRequest,
    db: AsyncSession = Depends(get_async_db),
):
    phone = data.phone
    code = data.code

    async with lock:
        entry = pending_auth.pop(phone, None)

    if not entry:
        raise HTTPException(400, "ابتدا start را اجرا کنید")

    client: Client = entry["client"]
    tx = entry["tx"]
    user_id = entry["user_id"]

    try:
        await client.validate_code(code, tx)

    except Exception as e:
        msg = str(e)

        if "PHONE_CODE_INVALID" in msg:
            raise HTTPException(400, "کد اشتباه است")

        if "PHONE_CODE_EXPIRED" in msg:
            raise HTTPException(400, "کد منقضی شده")

        if "FLOOD_WAIT" in msg:
            raise HTTPException(429, "تلاش زیاد")

        raise HTTPException(500, "خطا در تایید کد")

    session_file = SESSION_DIR / f"{phone}.bale"

    if not session_file.exists():
        raise HTTPException(500, "session ساخته نشد")

    session_data = base64.b64encode(session_file.read_bytes()).decode()

    account = await db.scalar(
        select(models.Account).where(models.Account.phone == phone)
    )

    if not account:
        account = models.Account(
            phone=phone,
            session_data=session_data,
            is_blocked=False
        )
        existing_link = None

        db.add(account)
        await db.flush()

        await db.execute(
            models.user_accounts.insert().values(
                user_id=user_id,
                account_id=account.id
            )
        )

    else:
        account.session_data = session_data
        existing_link = await db.scalar(
    select(models.user_accounts).where(
        models.user_accounts.c.user_id == user_id,
        models.user_accounts.c.account_id == account.id
    )
)

    await db.commit()

    return {"ok": True}


# ============================================================
# GET USER ACCOUNTS
# ============================================================

@router.get("/accounts")
async def get_accounts(
    user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):

    result = await db.execute(
        select(models.Account)
        .join(models.user_accounts)
        .where(models.user_accounts.c.user_id == user.id)
    )

    accounts = result.scalars().all()

    return accounts


# ============================================================
# PROFILE UPDATE
# ============================================================

@router.post("/profile/{account_id}")
async def complete_profile(
    account_id: int,
    data: schemas.ProfileSchema,
    user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):

    account = await db.scalar(
        select(models.Account)
        .join(models.user_accounts)
        .where(
            models.Account.id == account_id,
            models.user_accounts.c.user_id == user.id
        )
    )

    if not account:
        raise HTTPException(404, "اکانت پیدا نشد")

    account.gender = data.gender
    account.birthdate = data.birthdate
    account.city = data.city

    await db.commit()

    return {"ok": True}
