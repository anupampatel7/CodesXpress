"""Pytest fixtures for asynchronous database and mock bot services."""

import asyncio
from typing import AsyncGenerator
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    create_async_engine,
    async_sessionmaker,
)
from models.base import Base
from models.user import User
from models.coupon import Coupon, CouponCategory, StockType
from models.coupon_code import CouponCode, CodeStatus
from models.channel import Channel


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop per test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(autouse=True)
async def async_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Provide an in-memory SQLite engine for testing and patch database module."""
    import database
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    orig_engine = database.engine
    orig_factory = database.async_session_factory
    database.engine = engine
    database.async_session_factory = session_factory

    yield engine

    database.engine = orig_engine
    database.async_session_factory = orig_factory

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(async_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Yield a transactional async session rolled back or committed per test."""
    session_factory = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest.fixture
def mock_bot() -> AsyncMock:
    """Mock aiogram Bot instance."""
    bot = AsyncMock()
    bot.send_message = AsyncMock()
    bot.get_chat_member = AsyncMock()
    return bot
