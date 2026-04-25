# models.py
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    ForeignKey,
    Table,
)
from sqlalchemy.orm import relationship, DeclarativeBase, Mapped, mapped_column

# --- تعریف Base ---
class Base(DeclarativeBase):
    pass

# --- جدول واسط برای رابطه چند-به-چند بین Order و Account ---
order_accounts_association = Table(
    "order_accounts_association",
    Base.metadata,
    Column("order_id", Integer, ForeignKey("orders.id", ondelete="CASCADE")),
    Column("account_id", Integer, ForeignKey("accounts.id", ondelete="CASCADE")),
    # اضافه کردن ستون برای زمان پیوستن
    Column(
        "joined_at",
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    ),
)

# --- مدل‌های دیتابیس ---

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    bale_user_id: Mapped[int] = mapped_column(unique=True, index=True) # فرض می‌کنیم bale_user_id منحصر به فرد است
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # رابطه با اکانت‌ها
    accounts: Mapped[List["Account"]] = relationship(back_populates="owner")

    def __repr__(self):
        return f"<User(id={self.id}, bale_user_id={self.bale_user_id})>"


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(50), default="running")
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    session_data: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    coins: Mapped[int] = mapped_column(Integer, default=0)
    invitations_count: Mapped[int] = mapped_column(Integer, default=0)
    vip_status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    gender: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    birthdate: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # رابطه با Owner (User)
    owner: Mapped["User"] = relationship(back_populates="accounts")

    # رابطه با سفارش‌هایی که این اکانت ایجاد کرده
    orders: Mapped[List["Order"]] = relationship(back_populates="account")

    # رابطه با سفارش‌هایی که این اکانت در آنها شرکت کرده (چند-به-چند)
    participated_orders: Mapped[List["Order"]] = relationship(
        secondary=order_accounts_association,
        back_populates="joined_accounts",
        lazy="selectin" # بهینه برای واکشی اطلاعات مرتبط
    )

    def __repr__(self):
        return f"<Account(id={self.id}, phone={self.phone}, owner_id={self.owner_id}, status='{self.status}')>"


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True) # اکانت سفارش دهنده
    order_status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    order_count: Mapped[int] = mapped_column(Integer, default=1)
    username: Mapped[str] = mapped_column(String(100))
    profile_picture_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    differentiation_factors: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # رابطه با اکانت سفارش دهنده
    account: Mapped["Account"] = relationship(back_populates="orders")

    # رابطه با اکانت‌هایی که در این سفارش شرکت کرده‌اند (چند-به-چند)
    joined_accounts: Mapped[List["Account"]] = relationship(
        secondary=order_accounts_association,
        back_populates="participated_orders",
        lazy="selectin" # بهینه برای واکشی اطلاعات مرتبط
    )

    def __repr__(self):
        return f"<Order(id={self.id}, account_id={self.account_id}, username='{self.username}')>"
