import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Settings(BaseSettings):
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://user:password@host/dbname")
    ASYNC_DATABASE_URL: str = os.getenv("ASYNC_DATABASE_URL", "postgresql+asyncpg://user:password@host/dbname")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-super-secret-key")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    BOT_TOKEN: os.getenv("BOT_TOKEN", "2093115437:fnNwB5DcmEFyZ0zN1MDD3I89Fg9LLipQIys")

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
