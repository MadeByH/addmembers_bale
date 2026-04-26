# models.py
from datetime import datetime, timezone
from typing import List, Optional, Literal
from enum import Enum

from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    ForeignKey,
    Table,
    Date,
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

user_accounts = Table(
    "user_accounts",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("account_id", Integer, ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True),
    Column("created_at", DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)),
)

class UserStatus(str, Enum):
    RUNNING = "running"
    ACTIVE = "active"
    LOGGED_OUT = "logged_out"
    BLOCKED = "blocked"
    SLEEP = "sleep"
    ERROR = "error"

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
    
    accounts: Mapped[List["Account"]] = relationship(
    secondary=user_accounts,
    back_populates="users",
)

    def __repr__(self):
        return f"<User(id={self.id}, bale_user_id={self.bale_user_id})>"


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    bale_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    bale_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    bale_username: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    bale_avatar: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    status: Mapped[UserStatus] = mapped_column(String(50), default=UserStatus.RUNNING)
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
    birthdate: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # رابطه با سفارش‌هایی که این اکانت ایجاد کرده
    orders: Mapped[List["Order"]] = relationship(back_populates="account")

    # رابطه با سفارش‌هایی که این اکانت در آنها شرکت کرده (چند-به-چند)
    participated_orders: Mapped[List["Order"]] = relationship(
        secondary=order_accounts_association,
        back_populates="joined_accounts",
        lazy="selectin" # بهینه برای واکشی اطلاعات مرتبط
    )

    users: Mapped[List["User"]] = relationship(
    secondary=user_accounts,
    back_populates="accounts",
)

    def __repr__(self):
        return f"<Account(id={self.id}, phone={self.phone}, status='{self.status}')>"


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
