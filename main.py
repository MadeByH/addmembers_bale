# main.py
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, APIRouter
from fastapi.responses import FileResponse

from .db import AsyncSessionLocal
from .auth import router as auth_router
from fastapi.staticfiles import StaticFiles

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
        "birhdate": account.birthdate,
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


# Register extra routers
router.include_router(profile_router)
router.include_router(wallet_router)
router.include_router(orders_router)
