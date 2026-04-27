# models.py
from datetime import datetime, timezone, date
from typing import List, Optional
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
    Index,
)
from sqlalchemy.orm import relationship, DeclarativeBase, Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import Enum as SQLEnum


# =======================================
# Base
# =======================================
class Base(DeclarativeBase):
    pass


# =======================================
# Enums
# =======================================

class OrderStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class OrderType(str, Enum):
    CHANNEL = "channel"
    GROUP = "group"

class OrderSpeed(str, Enum):
    TORTOISE = "tortoise"
    RABBIT = "rabbit"
    CHEETAH = "cheetah"


# =======================================
# Association Tables
# =======================================

# Many-to-many: orders <-> accounts (participants)
order_accounts_association = Table(
    "order_accounts_association",
    Base.metadata,
    Column("order_id", Integer, ForeignKey("orders.id", ondelete="CASCADE"), primary_key=True),
    Column("account_id", Integer, ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "joined_at",
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    ),
)

# Many-to-many: users <-> accounts (multi-account system)
user_accounts = Table(
    "user_accounts",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("account_id", Integer, ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True),
    Column("created_at", DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)),
)

Index("idx_user_account_combo", user_accounts.c.user_id, user_accounts.c.account_id)


# =======================================
# Models
# =======================================

# ---------------------------
# USER
# ---------------------------
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    bale_user_id: Mapped[int] = mapped_column(unique=True, index=True)

    active_account_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("accounts.id"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Many-to-many
    accounts: Mapped[List["Account"]] = relationship(
        secondary=user_accounts,
        back_populates="users",
        lazy="selectin"
    )

    # Account user is currently controlling
    active_account: Mapped[Optional["Account"]] = relationship(
        "Account",
        lazy="joined",
        foreign_keys=[active_account_id]
    )

    def __repr__(self):
        return f"<User(id={self.id}, bale_user_id={self.bale_user_id})>"


# ---------------------------
# BLOCKED PHONE
# ---------------------------
class BlockedPhone(Base):
    __tablename__ = "blocked_phones"

    phone: Mapped[str] = mapped_column(String(20), primary_key=True)
    reason: Mapped[Optional[str]] = mapped_column(String(255))
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self):
        return f"<BlockedPhone(phone={self.phone})>"


# ---------------------------
# ACCOUNT
# ---------------------------
class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    phone: Mapped[str] = mapped_column(String(20), unique=True, index=True)

    bale_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    bale_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    bale_username: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    bale_avatar: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    session_data: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )

    coins: Mapped[int] = mapped_column(Integer, default=0)
    
    # --- Invite & Reward System ---
    has_invited_with_link: Mapped[bool] = mapped_column(Boolean, default=False)
    invitations_count: Mapped[int] = mapped_column(Integer, default=0)
    
    wheel_chances: Mapped[int] = mapped_column(Integer, default=0)
    total_joins_today: Mapped[int] = mapped_column(Integer, default=0)
    last_join_reset_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    last_join_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- VIP ---
    vip_expiry: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    vip_status: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    gender: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    birthdate: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # One-to-many: account -> orders (created)
    orders: Mapped[List["Order"]] = relationship(
        back_populates="account",
        cascade="all, delete"
    )

    # Many-to-many: account -> participated orders
    participated_orders: Mapped[List["Order"]] = relationship(
        secondary=order_accounts_association,
        back_populates="joined_accounts",
        lazy="selectin"
    )

    # Many-to-many: account -> users
    users: Mapped[List["User"]] = relationship(
        secondary=user_accounts,
        back_populates="accounts",
        lazy="selectin"
    )

    def __repr__(self):
        return f"<Account(id={self.id}, phone={self.phone})>"


# ---------------------------
# ORDER
# ---------------------------
class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"),
        index=True
    )

    # اصلاح: استفاده از Enum تعریف شده
    order_status: Mapped[OrderStatus] = mapped_column(
    SQLEnum(OrderStatus),
    default=OrderStatus.PENDING,
    index=True
    )
    
    order_type: Mapped[OrderType] = mapped_column(
    SQLEnum(OrderType),
    default=OrderType.CHANNEL,
    index=True
)
    
    order_count: Mapped[int] = mapped_column(Integer, default=1, index=True)
    join_link: Mapped[str] = mapped_column(String(255), index=True)
    profile_picture_url: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    
    reward_coins: Mapped[int] = mapped_column(Integer, default=1, index=True)
    report_count: Mapped[int] = mapped_column(Integer, default=0)
    
    speed: Mapped[OrderSpeed] = mapped_column(
    SQLEnum(OrderSpeed),
    default=OrderSpeed.TORTOISE,
    index=True
)

    priority_score: Mapped[int] = mapped_column(default=1, index=True)
    
    # اصلاح: تعریف درست Mapped برای JSONB
    differentiation_factors: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    account: Mapped["Account"] = relationship(back_populates="orders")
    joined_accounts: Mapped[List["Account"]] = relationship(
        secondary=order_accounts_association,
        back_populates="participated_orders",
        lazy="selectin"
    )

    def __repr__(self):
        # اصلاح: تغییر username به join_link برای جلوگیری از AttributeError
        return f"<Order(id={self.id}, account_id={self.account_id}, link={self.join_link})>"
