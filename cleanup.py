from sqlalchemy import delete, select
from datetime import datetime, timezone, timedelta
from db import async_session
import models


async def cleanup_completed_orders():
    async with async_session() as db:

        # فقط سفارش‌هایی که ۱ ساعت از اتمام‌شان گذشته
        threshold = datetime.now(timezone.utc) - timedelta(hours=1)

        stmt = select(models.Order).where(
            models.Order.order_status == models.OrderStatus.COMPLETED,
            models.Order.completed_at < threshold
        )

        result = await db.execute(stmt)
        orders = result.scalars().all()

        for order in orders:

            # ۱️⃣ حذف association records
            await db.execute(
                delete(models.order_accounts_association).where(
                    models.order_accounts_association.c.order_id == order.id
                )
            )

            # ۲️⃣ سبک کردن رکورد سفارش
            order.order_count = None
            order.speed = None
            order.reward_coins = None
            order.differentiation_factors = None
            order.priority_score = None

        await db.commit()
