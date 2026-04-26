import asyncio
import base64
from pathlib import Path
from datetime import datetime, timezone
import time

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aiobale import Client, Dispatcher
from aiobale import types

from . import models
from .db import AsyncSessionLocal

SESSION_DIR = Path("session.bale")
SESSION_DIR.mkdir(exist_ok=True)


# ============================================================
# ACCOUNT MANAGER
# ============================================================

class AccountManager:
    def __init__(self):
        self.running: dict[int, Client] = {}
        self.lock = asyncio.Lock()

    # ---------------------------------------------------------
    # RESTORE SESSION FROM DB
    # ---------------------------------------------------------
    async def _restore_session_file(self, account: models.Account):
        """
        If file `.bale` doesn't exist, recreate from base64 DB `session_data`
        """
        session_file = SESSION_DIR / f"{account.phone}.bale"

        if not session_file.exists():
            if not account.session_data:
                return False

            try:
                raw = base64.b64decode(account.session_data)
                session_file.write_bytes(raw)
                print(f"♻️ session restored for {account.phone}")
            except Exception as e:
                print(f"❌ failed restoring session: {e}")
                return False

        return True


    @staticmethod
    def attach_handlers(client: Client):
        dp = client.dispatcher

        @dp.message()
        async def on_message(msg: types.Message):

            # --------------------------------
            # Client not active
            # --------------------------------
            if not getattr(client, "_active", True):
                return

            # --------------------------------
            # Bot not fully logged in
            # --------------------------------
            if not hasattr(client, "me") or not client.me:
                return

            # --------------------------------
            # Ignore own messages
            # --------------------------------
            if msg.sender_id == client.me.id:
                return

            # --------------------------------
            # Basic message data
            # --------------------------------
            chat_id = getattr(msg.chat, "id", None)
            message_id = getattr(msg, "message_id", None)
            text = getattr(msg, "text", None)
            date_unix = getattr(msg, "date", int(time.time()))

            # --------------------------------
            # Debug log
            # --------------------------------
            print(
            f"[{client._phone}] "
            f"chat={chat_id} "
            f"msg={message_id} "
            f"text={str(text)[:40]}"
        )

            # --------------------------------
            # Example command
            # --------------------------------
            if text == "/ping":
                try:
                    await client.send_message(chat_id, "pong ✅")
                except Exception as e:
                    print("send error:", e)

            # --------------------------------
            # Example magazine detection
            # --------------------------------
            if getattr(msg, "is_channel_post", False):

                print(
                f"📰 [Magazine Info] "
                f"ChatID: {chat_id} | "
                f"MsgID: {message_id} | "
                f"Date: {date_unix}"
            )

    # ---------------------------------------------------------
    # START SINGLE ACCOUNT
    # ---------------------------------------------------------
    async def start(self, account_id: int, db: AsyncSession):
        stmt = select(models.Account).where(models.Account.id == account_id)
        res = await db.execute(stmt)
        account = None
        com = False
        ref = False
        async with self.lock:

            # already running?
            if account_id in self.running:
                print(f"⚠️ account {account_id} already running")
                return

            # load account
            account = res.scalar_one_or_none()

            if not account:
                print(f"❌ account {account_id} not found")
                return

            if account.is_blocked:
                print(f"⛔ account {account.phone} blocked, skip")
                return

            if not account.session_data:
                print(f"❌ no session_data for {account.phone}")
                account.status = "dead"
                account.is_blocked = TTru
                com = True
                return

            # restore session file if missing
            ok = await self._restore_session_file(account)
            if not ok:
                account.status = "dead"
                account.is_blocked = True
                com = True
                return

            session_file = SESSION_DIR / f"{account.phone}.bale"

            # create client
            dispatcher = Dispatcher()
            client = Client(dispatcher, session_file=str(session_file))

            # optional attach handlers
            self.attach_handlers(client)

            try:
                await client.start(run_in_background=True)

                me = await client.get_me()
                print(f"🟢 account {account.phone} logged in as {me.name}")

                self.running[account_id] = client

                account.status = "running"
                account.last_seen = datetime.utcnow()
                account.is_blocked = False
                ref = True

            except Exception as e:
                print(f"❌ start error for {account.phone}: {e}")

                try:
                    await client.stop()
                except:
                    pass

                account.status = "dead"
                account.is_blocked = True
                account.last_seen = datetime.utcnow()
        if com:
            await db.commit()
        elif ref:
            await db.commit()
            await db.refresh(account)

    # ---------------------------------------------------------
    # STOP ACCOUNT
    # ---------------------------------------------------------
    async def stop(self, account_id: int, db: AsyncSession):
        updated = False
        account = None
        stmt = select(models.Account).where(models.Account.id == account_id)
        res = await db.execute(stmt)
        async with self.lock:

            client = self.running.pop(account_id, None)
            if client:
                try:
                    await client.stop()
                except:
                    pass

            account = res.scalar_one_or_none()

            if account:
                account.status = "offline"
                account.last_seen = datetime.utcnow()
                await db.commit()
                await db.refresh(account)

    # ---------------------------------------------------------
    # REMOVE ACCOUNT
    # ---------------------------------------------------------
    async def remove(self, account_id: int, db: AsyncSession):
        await self.stop(account_id, db)

        stmt = select(models.Account).where(models.Account.id == account_id)
        res = await db.execute(stmt)
        account = res.scalar_one_or_none()

        if account:
            account.is_blocked = True
            account.status = "dead"
            account.session_data = None
            account.last_seen = datetime.utcnow()
            await db.commit()
            await db.refresh(account)

            print(f"🔕 account {account.phone} removed & blocked")

    # ---------------------------------------------------------
    # START ALL ACCOUNTS
    # ---------------------------------------------------------
    async def start_all(self):
        stmt = select(models.Account).where(
        models.Account.is_blocked == False,
        models.Account.session_data != None
    )

        async with AsyncSessionLocal() as db:
            res = await db.execute(stmt)
            accounts = res.scalars().all()

        tasks = []

        for acc in accounts:
            tasks.append(self._start_with_new_session(acc.id))

        await asyncio.gather(*tasks)

        print(f"🚀 started {len(tasks)} accounts")

    async def _start_with_new_session(self, account_id: int):
        async with AsyncSessionLocal() as db:
            await self.start(account_id, db)

    # ---------------------------------------------------------
    # HEALTH CHECK / UPDATE STATUS
    # ---------------------------------------------------------
    async def heartbeat(self, db: AsyncSession):
        """
        Called periodically to update last_seen + clean broken clients
        """
        updated = False
        stmt = select(models.Account).where(models.Account.id == account_id)
        res = await db.execute(stmt)
        async with self.lock:

            now = datetime.now(timezone.utc)
            dead_ids = []

            for account_id, client in list(self.running.items()):

                account = res.scalar_one_or_none()

                if not account:
                    dead_ids.append(account_id)
                    continue

                if account.is_blocked:
                    print(f"⛔ stopping blocked account {account.phone}")
                    dead_ids.append(account_id)
                    continue

                # update last_seen
                account.last_seen = now
                account.status = "running"
                updated = True

            # stop dead accounts
            for acc_id in dead_ids:
                await self.stop(acc_id, db)

        if updated:
            await db.commit()


# ============================================================
# EXPORT SINGLETON
# ============================================================

account_manager = AccountManager()
