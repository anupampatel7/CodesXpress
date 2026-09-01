"""Configuration settings for Telegram Coupon Referral & Rewards Bot.

Loads environment variables with validation using Pydantic Settings.
"""

from typing import List, Optional, Any, Set
import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Base workspace directory
BASE_DIR = Path(__file__).resolve().parent

# Ensure data directory exists
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Ensure backup directory exists
BACKUP_DIR = BASE_DIR / "backups"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

# Load .env file explicitly if it exists
load_dotenv(dotenv_path=BASE_DIR / ".env")


def normalize_database_url(url: str) -> str:
    """Normalize database connection string for SQLAlchemy async drivers."""
    if not url:
        return url
    cleaned = url.strip().strip('"').strip("'")
    if cleaned.startswith("postgres://"):
        cleaned = "postgresql+asyncpg://" + cleaned[len("postgres://"):]
    elif cleaned.startswith("postgresql://") and not cleaned.startswith("postgresql+"):
        cleaned = "postgresql+asyncpg://" + cleaned[len("postgresql://"):]
    elif cleaned.startswith("postgresql+psycopg2://"):
        cleaned = "postgresql+asyncpg://" + cleaned[len("postgresql+psycopg2://"):]

    if "sslmode=require" in cleaned:
        cleaned = cleaned.replace("sslmode=require", "ssl=require")
    return cleaned


def mask_database_url(url: str) -> str:
    """Mask sensitive database credentials for safe logging."""
    if not url:
        return "Not Configured"
    if url.startswith("sqlite"):
        return "SQLite (local development)"
    try:
        if "@" in url:
            scheme, rest = url.split("://", 1)
            _, host_part = rest.split("@", 1)
            host_clean = host_part.split("?")[0]
            return f"{scheme}://****:****@{host_clean}"
        return "PostgreSQL (configured)"
    except Exception:
        return "Database (configured)"


class Settings(BaseSettings):
    """Application configuration schema."""

    # Telegram Bot Token
    BOT_TOKEN: str = Field(
        default="1234567890:ABCdefGHIjklMNOpqrsTUVwxyz123456789",
        description="Telegram bot token obtained from @BotFather",
    )

    # Super Admin Telegram ID
    ADMIN_ID: int = Field(
        default=0,
        description="Telegram ID of the primary super admin",
    )

    # Additional Admin Telegram IDs (Optional)
    ADDITIONAL_ADMINS: str = Field(
        default="",
        description="Comma-separated Telegram IDs of additional admins",
    )

    # Bot username (without @)
    BOT_USERNAME: str = Field(
        default="CouponRewardBot",
        description="Telegram bot username without @ symbol",
    )

    # Database URL (SQLite async by default; supports postgresql+asyncpg://...)
    DATABASE_URL: str = Field(
        default=f"sqlite+aiosqlite:///{DATA_DIR.as_posix()}/bot.db",
        description="SQLAlchemy async connection string",
    )

    # Business Rules
    POINTS_PER_REFERRAL: int = Field(
        default=1,
        description="Points rewarded to referrer upon successful referral",
    )

    # Required Channels Configuration (Centralized)
    CHANNEL_1: Optional[str] = Field(
        default="@OfferRaider",
        description="First required Telegram channel for referral verification",
    )
    CHANNEL_2: Optional[str] = Field(
        default="@OfferMate",
        description="Second required Telegram channel for referral verification",
    )
    CHANNEL_3: Optional[str] = Field(
        default="@Grabmint",
        description="Third required Telegram channel for referral verification",
    )
    CHANNEL_4: Optional[str] = Field(
        default="@offerelite",
        description="Fourth required Telegram channel for referral verification",
    )

    # Default initial required channels (Comma separated fallback)
    DEFAULT_REQUIRED_CHANNELS: str = Field(
        default="",
        description="Comma-separated channel usernames or chat IDs",
    )

    # Telegram WebApp & Health HTTP Server
    WEBAPP_URL: str = Field(
        default="",
        description="Public HTTPS URL of the hosted WebApp (e.g. https://domain.com/verify)",
    )
    WEBAPP_HOST: str = Field(
        default="0.0.0.0",
        description="Host address for the aiohttp WebApp and health server",
    )
    PORT: Optional[int] = Field(
        default=None,
        description="Port provided dynamically by cloud host (Render $PORT)",
    )
    WEBAPP_PORT: int = Field(
        default=8080,
        description="Local fallback port for the aiohttp WebApp and health server",
    )

    # Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    LOG_LEVEL: str = Field(
        default="INFO",
        description="Application logging level",
    )

    # Model configuration
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def validate_database_url(cls, v: Any) -> str:
        if not v:
            return f"sqlite+aiosqlite:///{DATA_DIR.as_posix()}/bot.db"
        return normalize_database_url(str(v))

    @field_validator("ADMIN_ID", mode="before")
    @classmethod
    def parse_admin_id(cls, v: Any) -> int:
        if v is None:
            return 0
        if isinstance(v, int):
            return v
        s = str(v).strip().strip('"').strip("'").strip()
        if not s:
            return 0
        try:
            return int(s)
        except ValueError:
            return 0

    @field_validator("ADDITIONAL_ADMINS", mode="before")
    @classmethod
    def parse_additional_admins(cls, v: Any) -> str:
        if v is None:
            return ""
        if isinstance(v, (list, tuple, set)):
            return ",".join(str(x) for x in v)
        return str(v).strip().strip('"').strip("'").strip()

    @field_validator("POINTS_PER_REFERRAL")
    @classmethod
    def validate_points(cls, v: int) -> int:
        if v < 1:
            raise ValueError("POINTS_PER_REFERRAL must be at least 1")
        return v

    @field_validator("PORT", mode="before")
    @classmethod
    def parse_port(cls, v: Any) -> Optional[int]:
        if v is None or v == "":
            env_port = os.getenv("PORT")
            if env_port:
                try:
                    return int(env_port)
                except ValueError:
                    pass
            return None
        try:
            return int(str(v).strip())
        except ValueError:
            return None

    @property
    def server_port(self) -> int:
        """Return dynamic cloud host PORT (Render) if provided, otherwise fallback to WEBAPP_PORT."""
        if self.PORT is not None:
            return self.PORT
        env_port = os.getenv("PORT")
        if env_port:
            try:
                return int(env_port)
            except ValueError:
                pass
        return self.WEBAPP_PORT

    @property
    def admin_ids(self) -> List[int]:
        """Return list of all configured admin IDs as normalized integers."""
        ids: Set[int] = set()
        if self.ADMIN_ID and int(self.ADMIN_ID) != 0:
            ids.add(int(self.ADMIN_ID))
        if self.ADDITIONAL_ADMINS:
            for item in str(self.ADDITIONAL_ADMINS).split(","):
                clean = item.strip().strip('"').strip("'").strip()
                if clean:
                    try:
                        ids.add(int(clean))
                    except ValueError:
                        pass
        return sorted(list(ids))

    @property
    def default_channel_list(self) -> List[str]:
        """Collect all default required channels from CHANNEL_1, CHANNEL_2, CHANNEL_3, CHANNEL_4, and DEFAULT_REQUIRED_CHANNELS."""
        channels: List[str] = []
        for ch in (self.CHANNEL_1, self.CHANNEL_2, self.CHANNEL_3, self.CHANNEL_4):
            if ch and ch.strip():
                clean = ch.strip()
                if clean not in channels:
                    channels.append(clean)
        if self.DEFAULT_REQUIRED_CHANNELS:
            for ch in self.DEFAULT_REQUIRED_CHANNELS.split(","):
                clean = ch.strip()
                if clean and clean not in channels:
                    channels.append(clean)
        return channels

    def is_admin(self, user_id: Any) -> bool:
        """Check whether a given Telegram user ID is an authorized admin."""
        if user_id is None:
            return False
        try:
            numeric_id = int(str(user_id).strip())
            return numeric_id in self.admin_ids
        except (ValueError, TypeError):
            return False


# Global settings instance
settings = Settings()
