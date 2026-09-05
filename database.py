"""Database connection, engine configuration, and session lifecycle management."""

import logging
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy import event
from config import settings, mask_database_url
from models.base import Base

logger = logging.getLogger(__name__)

# Determine if we're running SQLite
is_sqlite = settings.DATABASE_URL.startswith("sqlite")

# Engine configuration arguments
engine_kwargs = {
    "echo": False,
    "future": True,
}

if is_sqlite:
    # SQLite optimizations for file locking and write concurrency
    engine_kwargs["connect_args"] = {
        "check_same_thread": False,
        "timeout": 30,
    }
else:
    # PostgreSQL connection pooling optimizations
    engine_kwargs["pool_size"] = 10
    engine_kwargs["max_overflow"] = 20
    engine_kwargs["pool_pre_ping"] = True
    engine_kwargs["pool_recycle"] = 300

# Create async engine
engine: AsyncEngine = create_async_engine(settings.DATABASE_URL, **engine_kwargs)


# Enforce foreign keys and WAL mode on SQLite connections only
if is_sqlite:
    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()


# Async session factory
async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def init_db() -> None:
    """Initialize database schemas and create tables if they do not exist."""
    logger.info(f"Initializing database schema on {mask_database_url(settings.DATABASE_URL)}...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Ensure display_order column exists on coupons table for persistent ordering
        try:
            from sqlalchemy import text
            await conn.execute(text("ALTER TABLE coupons ADD COLUMN display_order INTEGER DEFAULT 0"))
        except Exception:
            pass  # Column already exists or table freshly created
    logger.info("Database schema initialized successfully.")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency helper to yield an async database session."""
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
