import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import FileResponse

from .db import get_async_db
from .useraccounts import account_manager


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
            async with get_async_db() as db:
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
    async with get_async_db() as db:
        await account_manager.start_all(db)

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

    async with get_async_db() as db:
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
