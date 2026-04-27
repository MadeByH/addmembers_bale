# main.py
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, exists

from . import models
from .db import AsyncSessionLocal, get_async_db
from .auth import router as auth_router, get_current_user
from fastapi.staticfiles import StaticFiles
from .useraccounts import account_manager
from datetime import date, datetime, timezone, timedelta

# ==========================================================
# BACKGROUND HEARTBEAT LOOP
# ==========================================================

async def heartbeat_loop():
    """
    Periodically updates account status and health.
    Runs forever until app shutdown.
    """
    while True:
        try:
            async with AsyncSessionLocal() as db:
                await account_manager.heartbeat(db)

        except Exception as e:
            print("❌ Heartbeat error:", e)

        await asyncio.sleep(60)  # every 60 seconds


# ==========================================================
# APP LIFESPAN (BEST PRACTICE METHOD)
# ==========================================================

@asynccontextmanager
async def lifespan(app: FastAPI):

    print("🚀 Application starting...")

    # ------------------------------
    # START ALL ACCOUNTS
    # ------------------------------
    async with AsyncSessionLocal() as db:
        await account_manager.start_all()

    # ------------------------------
    # START BACKGROUND TASK
    # ------------------------------
    heartbeat_task = asyncio.create_task(heartbeat_loop())

    print("✅ Startup complete.")

    yield  # ← app runs here

    # ------------------------------
    # SHUTDOWN LOGIC
    # ------------------------------
    print("🛑 Application shutting down...")

    heartbeat_task.cancel()

    async with AsyncSessionLocal() as db:
        # Stop all running accounts safely
        for acc_id in list(account_manager.running.keys()):
            await account_manager.stop(acc_id, db)

    print("✅ Shutdown complete.")


# ==========================================================
# FASTAPI INIT
# ==========================================================

app = FastAPI(
    title="Multi Account Bot System",
    version="1.0.0",
    lifespan=lifespan
)

app.include_router(auth_router)

app.mount("/static", StaticFiles(directory="static"), name="static")


# ==========================================================
# BASIC ROUTES
# ==========================================================

@app.get("/")
async def root():
    return FileResponse("index.html")


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "running_accounts": len(account_manager.running)
    }


# ============================
# PROFILE OF ACTIVE ACCOUNT
# ============================

profile_router = APIRouter(prefix="/me", tags=["Profile"])

@profile_router.get("/profile")
async def get_profile(
    user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    if not user.active_account_id:
        raise HTTPException(400, "No active account selected")

    account = user.active_account
    if not account:
        raise HTTPException(404, "Account not found")

    return {
        "id": account.id,
        "phone": account.phone,
        "gender": account.gender,
        "birthdate": account.birthdate,
        "city": account.city,
        "bale_id": account.bale_id,
        "bale_username": account.bale_username,
        "bale_name": account.bale_name,
        "bale_avatar": account.bale_avatar,
    }


# ============================
# WALLET OF ACTIVE ACCOUNT
# ============================

wallet_router = APIRouter(tags=["Wallet"])

@wallet_router.get("/wallet")
async def get_wallet(
    user: models.User = Depends(get_current_user)
):
    if not user.active_account_id:
        raise HTTPException(400, "No active account selected")

    account = user.active_account
    return {"coins": account.coins}


# ============================
# ORDERS FOR ACTIVE ACCOUNT
# ============================

orders_router = APIRouter(tags=["Orders"])

@orders_router.get("/orders")
async def get_orders(
    user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    if not user.active_account_id:
        raise HTTPException(400, "No active account selected")

    account = user.active_account

    result = await db.execute(
        select(models.Order)
        .where(models.Order.account_id == account.id)
        .order_by(models.Order.created_at.desc())
    )

    orders = result.scalars().all()

    return {
        "orders": [
            {
                "id": o.id,
                "title": o.join_link,  # یا هر عنوانی که می‌خوای
                "status": o.order_status,
                "avatar": o.profile_picture_url,
                "join_link": o.join_link,
            }
            for o in orders
        ]
    }


earn_router = APIRouter(prefix="/earn", tags=["Earn"])

def calculate_age(birthdate):
            if not birthdate:
                return None
            today = date.today()
            return today.year - birthdate.year - (
        (today.month, today.day) < (birthdate.month, birthdate.day)
    )

@earn_router.get("/next")
async def get_next_order(
    user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    if not user.active_account_id:
        raise HTTPException(400, "No active account selected")

    account = user.active_account

    # ۱. پیدا کردن سفارش‌هایی که قبلاً عضو نشده
    subq = select(order_accounts_association.c.order_id).where(
        order_accounts_association.c.account_id == account.id
    )
    
    # ۲. کوئری بهینه با اولویت‌بندی دیتابیس
    stmt = (
        select(models.Order)
        .where(
            models.Order.order_status == models.OrderStatus.RUNNING,
            models.Order.order_count > 0,
            models.Order.account_id != account.id,
            ~models.Order.id.in_(subq)
        )
        .order_by(
            models.Order.priority_score.desc(), # اولویت سرعت (یوزپلنگ > خرگوش > لاکپشت)
            models.Order.created_at.asc()       # قدیمی‌ترین‌ها اول
        )
        .limit(50) # برای بهینه‌سازی
    )

    result = await db.execute(stmt)
    orders = result.scalars().all()

    # ۳. فیلتر دموگرافیک در پایتون
    for order in orders:
        factors = order.differentiation_factors or {}
        ok = True

        if "gender" in factors and account.gender != factors["gender"]:
            ok = False
        if "city" in factors and account.city != factors["city"]:
            ok = False
        
        age = calculate_age(account.birthdate)
        if "age_min" in factors and (age is None or age < factors["age_min"]):
            ok = False
        if "age_max" in factors and (age is None or age > factors["age_max"]):
            ok = False
        
        if ok:
            return {
                "id": order.id,
                "join_link": order.join_link,
                "avatar": order.profile_picture_url,
                "reward": order.reward_coins,
                "remaining": order.order_count,
                "type": order.order_type,
            }

    return {"order": None}

@earn_router.post("/{order_id}/join")
async def join_order(
    order_id: int,
    user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    if not user.active_account_id:
        raise HTTPException(400, "No active account")

    account = user.active_account

    # ۱. قفل کردن رکورد سفارش برای جلوگیری از Race Condition
    # (پرانتز دور کوئری برای جلوگیری از سینتکس ارور اضافه شد)
    stmt = (
        select(models.Order)
        .where(models.Order.id == order_id)
        .with_for_update()
    )
    res = await db.execute(stmt)
    order = res.scalar_one_or_none()

    if not order or order.order_status != models.OrderStatus.RUNNING or order.order_count <= 0:
        raise HTTPException(400, "Order is not available")

    # ۲. چک کردن Cooldown (حداقل ۲۰ ثانیه فاصله)
    now = datetime.now(timezone.utc)
    if account.last_join_time:
        # اگر دیتابیس timezone-naive هست، دقت کن که هر دو یکسان باشند
        diff = (now - account.last_join_time).total_seconds()
        if diff < 20:
            raise HTTPException(429, f"Please wait {int(20-diff)} seconds")

    # ۳. چک کردن تکراری نبودن (سریع)
    stmt_check = select(order_accounts_association).where(
        order_accounts_association.c.order_id == order_id,
        order_accounts_association.c.account_id == account.id
    )
    res_check = await db.execute(stmt_check)
    if res_check.first():
        raise HTTPException(400, "Already joined")
    
    if account.total_joins_today >= 100:
        raise HTTPException(400, "Daily limit reached")

    # ۴. عملیات جوین واقعی
    ok = await account_manager.join_chat(account.id, order.join_link, db)
    if not ok:
        raise HTTPException(400, "Join failed")

    # ۵. به‌روزرسانی وضعیت
    order.order_count -= 1
    if order.order_count <= 0:
        order.order_status = models.OrderStatus.COMPLETED
        order.completed_at = datetime.now(timezone.utc)

    account.coins += order.reward_coins
    account.last_join_time = now # ثبت زمان آخرین جوین

    # مدیریت ریست روزانه
    today = date.today()
    if account.last_join_reset_date != today:
        account.total_joins_today = 0
        account.last_join_reset_date = today
    account.total_joins_today += 1

    if account.total_joins_today % 5 == 0:
        account.wheel_chances += 1

    # ثبت در جدول واسط (Association)
    # توجه: در SQLAlchemy 2.0 برای جداول Table مستقیم باید اینطور درج کنی:
    await db.execute(
        order_accounts_association.insert().values(
            order_id=order.id, 
            account_id=account.id
        )
    )

    await db.commit()

    return {"success": True, "coins": account.coins}

@earn_router.post("/{order_id}/report")
async def report_order(
    order_id: int,
    user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):

    stmt = select(models.Order).where(models.Order.id == order_id)
    res = await db.execute(stmt)
    order = res.scalar_one_or_none()

    if not order:
        raise HTTPException(404, "Order not found")

    order.report_count += 1

    if order.report_count >= 7:
        order.order_status = models.OrderStatus.FAILED

    await db.commit()

    return {
        "reports": order.report_count
    }


@orders_router.post("/create")
async def create_order(
    data: OrderCreate,
    user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):

    if not user.active_account_id:
        raise HTTPException(400, "No active account")

    account = user.active_account

    # ------------------------
    # 1️⃣ محاسبه قیمت پایه
    # ------------------------

    if data.speed == models.OrderSpeed.TORTOISE:
        base_price = 2
        priority = 1
    elif data.speed == models.OrderSpeed.RABBIT:
        base_price = 3
        priority = 2
    else:
        base_price = 4
        priority = 3

    # ------------------------
    # 2️⃣ شمارش فاکتورهای تفکیک
    # ------------------------

    diff_count = 0
    factors = data.differentiation_factors or {}

    if "gender" in factors:
        diff_count += 1

    if "city" in factors:
        diff_count += 1

    if "age_min" in factors or "age_max" in factors:
        diff_count += 1
    
    reward_coins = max(1, min(3, data.reward_coins))
    price_per_member = base_price + diff_count + reward_coins

    total_cost = price_per_member * data.order_count

    # ------------------------
    # 3️⃣ بررسی موجودی
    # ------------------------

    if account.coins < total_cost:
        raise HTTPException(400, "Not enough coins")

    # ------------------------
    # 4⃣ محدودیت تعداد
    # ------------------------
    
    if data.order_count < 50:
        raise HTTPException(400, "Not minima order count")

    # ------------------------
    # 5⃣ کم کردن سکه
    # ------------------------

    account.coins -= total_cost

    # ------------------------
    # 6⃣ ساخت سفارش
    # ------------------------

    order = models.Order(
        join_link=data.join_link,
        order_count=data.order_count,
        reward_coins=reward_coins,
        order_type=data.order_type,
        speed=data.speed,
        priority_score=priority,
        differentiation_factors=factors,
        account_id=account.id,
        order_status=models.OrderStatus.RUNNING
    )

    db.add(order)
    await db.commit()
    await db.refresh(order)

    return {
        "order_id": order.id,
        "price_per_member": price_per_member,
        "total_cost": total_cost,
        "remaining_coins": account.coins
    }

@orders_router.get("/my")
async def my_orders(
    user: models.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):

    stmt = select(models.Order).where(
        models.Order.account_id == user.active_account_id
    )

    res = await db.execute(stmt)
    orders = res.scalars().all()

    return orders


# Register extra routers
app.include_router(profile_router)
app.include_router(wallet_router)
app.include_router(orders_router)
app.include_router(earn_router)
