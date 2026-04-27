# useraccounts.py
import asyncio
import base64
from pathlib import Path
from datetime import datetime, timezone
import time
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aiobale import Client, Dispatcher
from aiobale import types

# ---
from aiobale.types import InfoMessage, Peer, ShortPeer, Chat, GiftPacket, StringValue, BoolValue, Report, PeerReport
from aiobale.methods.magazine import UpvotePost, GetMessageUpvoters, RevokeUpvotedPost
from aiobale.methods.abacus import MessageSetReaction, GetMessagesReactions, GetMessageReactionsList, GetMessagesViews
from aiobale.types import OtherMessage
from aiobale.methods.groups import JoinPublicGroup, LeaveGroup
from aiobale.methods import EditName, SendReport
# ---

from . import models
from .db import AsyncSessionLocal

SESSION_DIR = Path("session.bale")
SESSION_DIR.mkdir(exist_ok=True)


class AccountManager:

    def __init__(self):
        self.running: dict[int, Client] = {}
        self.lock = asyncio.Lock()

    # -------------------------------------------------
    # restore session file
    # -------------------------------------------------

    async def _restore_session_file(self, account: models.Account):

        session_file = SESSION_DIR / f"{account.id}.bale"

        if session_file.exists():
            return True

        if not account.session_data:
            return False

        try:
            raw = base64.b64decode(account.session_data)
            session_file.write_bytes(raw)
            print(f"♻️ session restored for {account.phone}")
            return True
        except Exception as e:
            print(f"❌ restore failed {account.phone}: {e}")
            return False

    # -------------------------------------------------
    # handlers
    # -------------------------------------------------

    @staticmethod
    def attach_handlers(client: Client):

        dp = client.dispatcher

        @dp.message()
        async def on_message(msg: types.Message):

            if not getattr(client, "_active", True):
                return

            if not hasattr(client, "me") or not client.me:
                return

            if msg.sender_id == client.me.id:
                return

            chat_id = getattr(msg.chat, "id", None)
            message_id = getattr(msg, "message_id", None)
            text = getattr(msg, "text", None)

            print(
                f"[{client._phone}] "
                f"chat={chat_id} "
                f"msg={message_id} "
                f"text={str(text)[:40]}"
            )

            if text == "/ping":
                try:
                    await client.send_message(chat_id, "pong ✅")
                except Exception as e:
                    print("send error:", e)

    # -------------------------------------------------
    # check blocked phone
    # -------------------------------------------------

    async def _is_phone_blocked(self, phone: str, db: AsyncSession):

        stmt = select(models.BlockedPhone).where(
            models.BlockedPhone.phone == phone
        )

        res = await db.execute(stmt)
        blocked = res.scalar_one_or_none()

        if not blocked:
            return False

        if blocked.expires_at and blocked.expires_at < datetime.now(timezone.utc):
            return False

        return True

    # -------------------------------------------------
    # start account
    # -------------------------------------------------

    async def start(self, account_id: int, db: AsyncSession):

        stmt = select(models.Account).where(models.Account.id == account_id)
        res = await db.execute(stmt)
        account = res.scalar_one_or_none()

        if not account:
            return

        # check blocked phone
        if await self._is_phone_blocked(account.phone, db):
            print(f"⛔ phone blocked {account.phone}")
            await db.commit()
            return

        if not account.session_data:
            await db.delete(account)
            await db.commit()
            return

        ok = await self._restore_session_file(account)

        if not ok:
            await db.commit()
            return

        session_file = SESSION_DIR / f"{account.id}.bale"

        dispatcher = Dispatcher()
        client = Client(dispatcher, session_file=str(session_file))

        self.attach_handlers(client)

        async with self.lock:

            if account_id in self.running:
                return

            self.running[account_id] = client

        try:

            await client.start(run_in_background=True)

            me = await client.get_me()

            print(f"🟢 account {account.phone} logged in")

            account.last_seen = datetime.now(timezone.utc)

            account.bale_id = me.id
            account.bale_name = me.first_name
            account.bale_username = me.username
            account.bale_avatar = me.photo

            await db.commit()

        except Exception as e:

            print(f"❌ start error {account.phone} {e}")

            async with self.lock:
                self.running.pop(account_id, None)

            try:
                await client.stop()
            except:
                pass

            await db.delete(account)

            await db.commit()

    # -------------------------------------------------
    # stop
    # -------------------------------------------------

    async def stop(self, account_id: int, db: AsyncSession):

        async with self.lock:

            client = self.running.pop(account_id, None)

        if client:
            try:
                await client.stop()
            except:
                pass

        stmt = select(models.Account).where(models.Account.id == account_id)
        res = await db.execute(stmt)
        account = res.scalar_one_or_none()

        if account:

            account.last_seen = datetime.now(timezone.utc)

            await db.commit()

    # -------------------------------------------------
    # remove
    # -------------------------------------------------

    async def remove(self, account_id: int, db: AsyncSession):

        await self.stop(account_id, db)

        stmt = select(models.Account).where(models.Account.id == account_id)
        res = await db.execute(stmt)
        account = res.scalar_one_or_none()

        if not account:
            return

        # delete session file
        session_file = SESSION_DIR / f"{account.id}.bale"

        if session_file.exists():
            session_file.unlink()

        await db.delete(account)
        await db.commit()

        print(f"🗑️ account {account.phone} permanently removed")

    # -------------------------------------------------
    # start all
    # -------------------------------------------------

    async def start_all(self):

        async with AsyncSessionLocal() as db:

            stmt = select(models.Account).where(
                models.Account.session_data != None
            )

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

    # -------------------------------------------------
    # heartbeat
    # -------------------------------------------------

    async def heartbeat(self, db: AsyncSession):

        now = datetime.now(timezone.utc)

        async with self.lock:
            running = list(self.running.items())

        for account_id, client in running:

            stmt = select(models.Account).where(models.Account.id == account_id)
            res = await db.execute(stmt)
            account = res.scalar_one_or_none()

            if not account:
                await self.stop(account_id, db)
                continue

            if await self._is_phone_blocked(account.phone, db):
                print(f"⛔ stopping blocked {account.phone}")
                await self.stop(account_id, db)
                continue

            account.last_seen = now

        await db.commit()

        # ------------------------------
        # join chat
        # ------------------------------

        @staticmethod
        def get_link(text: str):
            text = text.strip()

            join_pattern = r"^(?:https?://)?ble\.ir/join/([a-zA-Z0-9_-]+)$"
            username_link_pattern = r"^(?:https?://)?ble\.ir/([a-zA-Z0-9_.-]+)$"
            at_username_pattern = r"^@([a-zA-Z0-9_.-]+)$"

            if match := re.match(join_pattern, text):
                return {"type": "join", "value": match.group(1)}

            elif match := re.match(username_link_pattern, text):
                return {"type": "username", "value": match.group(1)}

            elif match := re.match(at_username_pattern, text):
                return {"type": "username", "value": match.group(1)}

            return None

        async def join_chat(self, account_id: int, link: str, db: AsyncSession):

            # find account
            stmt = select(models.Account).where(models.Account.id == account_id)
            res = await db.execute(stmt)
            account = res.scalar_one_or_none()

            if not account:
                raise Exception("Account not found")

            # account must be running
            client = self.running.get(account_id)
            if not client:
                raise Exception("Account is not running")

            link_data = self.get_link(link)
            if not link_data:
                raise Exception("Invalid link")

            link_type = link_data["type"]
            value = link_data["value"]

            try:
                if link_type == "join":
                    # private link
                    await client.join_chat(value)
                    return True

                else:
                # username
                    result = await client.search_username(value)
                    if result.group is None:
                        raise Exception("Cannot fetch public group/channel")

                    chat_id = result.group.id
                    await client.join_public_chat(chat_id)
                    return True

            except Exception as e:
                print(f"❌ join error {account.phone}: {e}")
                return False


account_manager = AccountManager()
