"""Database session middleware for aiogram 3."""

import logging
import time
from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from database import async_session_factory

logger = logging.getLogger(__name__)


class DbSessionMiddleware(BaseMiddleware):
    """Middleware that injects an async SQLAlchemy session into every update handler."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        start_time = time.perf_counter()
        async with async_session_factory() as session:
            data["session"] = session
            try:
                result = await handler(event, data)
                await session.commit()
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                logger.debug(f"[PERF] Update lifecycle processed in {elapsed_ms:.2f}ms")
                return result
            except Exception:
                await session.rollback()
                raise
