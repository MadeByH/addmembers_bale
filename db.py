# db.py
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from config import settings 

# Use ASYNC_DATABASE_URL from settings
# Ensure your ASYNC_DATABASE_URL starts with postgresql+asyncpg://
async_engine = create_async_engine(
    settings.ASYNC_DATABASE_URL,
    pool_pre_ping=True,
    pool_size=20,
    max_overflow=5,
    pool_timeout=30,
    # poolclass=NullPool # فعلا کامنت شده، در صورت نیاز فعال شود
)

AsyncSessionLocal = sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False
)

async def get_async_db():
    """Dependency to get async database session."""
    async with AsyncSessionLocal() as session:
        yield session
