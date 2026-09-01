"""Unit tests for PostgreSQL compatibility, DATABASE_URL normalization, and safe logging."""

import pytest
from unittest.mock import MagicMock, AsyncMock
from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import postgresql
from config import normalize_database_url, mask_database_url, Settings
from models.base import Base
from models.user import User
from models.coupon import Coupon
from models.coupon_code import CouponCode
from models.referral import Referral
from models.redemption import Redemption
from models.channel import Channel
from models.point_transaction import PointTransaction
from models.admin_action import AdminAction
from models.device_binding import DeviceBinding
from handlers.admin import handle_admin_backup
from aiogram.types import Message, CallbackQuery


def test_normalize_database_url():
    """Verify normalization of various Render/Heroku PostgreSQL connection string formats."""
    # Standard postgres://
    url1 = "postgres://bot_user:secret_pass@dpg-abc12345.render.com:5432/bot_db"
    assert normalize_database_url(url1) == "postgresql+asyncpg://bot_user:secret_pass@dpg-abc12345.render.com:5432/bot_db"

    # Standard postgresql:// without async driver
    url2 = "postgresql://bot_user:secret_pass@dpg-abc12345.render.com:5432/bot_db"
    assert normalize_database_url(url2) == "postgresql+asyncpg://bot_user:secret_pass@dpg-abc12345.render.com:5432/bot_db"

    # Sync psycopg2 string
    url3 = "postgresql+psycopg2://bot_user:secret_pass@dpg-abc12345.render.com:5432/bot_db"
    assert normalize_database_url(url3) == "postgresql+asyncpg://bot_user:secret_pass@dpg-abc12345.render.com:5432/bot_db"

    # Query parameters with sslmode
    url4 = "postgresql://bot_user:secret_pass@dpg-abc12345.render.com:5432/bot_db?sslmode=require"
    assert normalize_database_url(url4) == "postgresql+asyncpg://bot_user:secret_pass@dpg-abc12345.render.com:5432/bot_db?ssl=require"

    # Already asyncpg string
    url5 = "postgresql+asyncpg://bot_user:secret_pass@dpg-abc12345.render.com:5432/bot_db"
    assert normalize_database_url(url5) == "postgresql+asyncpg://bot_user:secret_pass@dpg-abc12345.render.com:5432/bot_db"

    # Local SQLite unchanged
    url6 = "sqlite+aiosqlite:///data/bot.db"
    assert normalize_database_url(url6) == "sqlite+aiosqlite:///data/bot.db"


def test_mask_database_url():
    """Verify that credentials are never exposed in log outputs."""
    url = "postgresql+asyncpg://my_user:SuperSecretPassword123@dpg-abc12345.oregon-postgres.render.com:5432/bot_db"
    masked = mask_database_url(url)
    assert "SuperSecretPassword123" not in masked
    assert "my_user" not in masked
    assert "dpg-abc12345.oregon-postgres.render.com:5432/bot_db" in masked
    assert masked.startswith("postgresql+asyncpg://****:****@")

    sqlite_masked = mask_database_url("sqlite+aiosqlite:///data/bot.db")
    assert "SQLite" in sqlite_masked


def test_pydantic_settings_normalizes_postgres_url():
    """Verify that Settings pydantic model automatically normalizes DATABASE_URL."""
    custom_settings = Settings(
        BOT_TOKEN="12345:dummy",
        ADMIN_ID=999,
        DATABASE_URL="postgres://render_user:pass123@host:5432/production_db",
    )
    assert custom_settings.DATABASE_URL.startswith("postgresql+asyncpg://")


def test_postgresql_ddl_compilation_for_all_models():
    """Verify that all SQLAlchemy ORM models compile valid DDL under PostgreSQL dialect."""
    pg_dialect = postgresql.dialect()
    models = [
        User,
        Coupon,
        CouponCode,
        Referral,
        Redemption,
        Channel,
        PointTransaction,
        AdminAction,
        DeviceBinding,
    ]

    for model in models:
        ddl_str = str(CreateTable(model.__table__).compile(dialect=pg_dialect))
        assert len(ddl_str) > 0
        assert model.__tablename__ in ddl_str


@pytest.mark.asyncio
async def test_admin_backup_on_postgres(monkeypatch):
    """Verify that /backup gives an informative notice when running on PostgreSQL."""
    from config import settings
    monkeypatch.setattr(settings, "DATABASE_URL", "postgresql+asyncpg://user:pass@host:5432/db")

    mock_msg = MagicMock(spec=Message)
    mock_msg.from_user = MagicMock(id=999)
    mock_msg.answer = AsyncMock()

    await handle_admin_backup(mock_msg, is_admin=True)
    mock_msg.answer.assert_called_once()
    answer_text = mock_msg.answer.call_args[0][0]
    assert "PostgreSQL Production Database" in answer_text
    assert "Render PostgreSQL" in answer_text
