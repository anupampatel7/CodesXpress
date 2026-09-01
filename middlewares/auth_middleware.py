"""Authentication and ban checking middleware."""

from typing import Any, Awaitable, Callable, Dict, Optional
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery, Update, User as TgUser
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from config import settings
from models.user import User


class AuthMiddleware(BaseMiddleware):
    """Middleware checking admin privileges and blocking banned users."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user_tg_id: Optional[int] = None

        # 1. Primary: Extract from aiogram context data
        event_user: Optional[TgUser] = data.get("event_from_user")
        if event_user:
            user_tg_id = event_user.id

        # 2. Fallback: Inspect event structure
        if not user_tg_id:
            if isinstance(event, Update):
                if event.message and event.message.from_user:
                    user_tg_id = event.message.from_user.id
                elif event.callback_query and event.callback_query.from_user:
                    user_tg_id = event.callback_query.from_user.id
                elif event.inline_query and event.inline_query.from_user:
                    user_tg_id = event.inline_query.from_user.id
            elif isinstance(event, Message) and event.from_user:
                user_tg_id = event.from_user.id
            elif isinstance(event, CallbackQuery) and event.from_user:
                user_tg_id = event.from_user.id
            elif hasattr(event, "from_user") and getattr(event, "from_user", None):
                user_tg_id = getattr(event, "from_user").id

        # Flag admin status server-side
        is_admin = False
        if user_tg_id is not None:
            is_admin = settings.is_admin(user_tg_id)
        data["is_admin"] = is_admin

        # Check banned status from database if session is present
        session: Optional[AsyncSession] = data.get("session")
        if session and user_tg_id is not None:
            stmt = select(User.is_banned).where(User.telegram_id == user_tg_id)
            res = await session.execute(stmt)
            is_banned = res.scalar_one_or_none()
            if is_banned:
                ban_msg = "🚫 <b>Account Suspended!</b>\n\nYour account has been suspended for terms violation."
                if isinstance(event, Message):
                    await event.answer(ban_msg, parse_mode="HTML")
                elif isinstance(event, CallbackQuery):
                    await event.answer("Your account has been suspended.", show_alert=True)
                elif isinstance(event, Update) and event.message:
                    await event.message.answer(ban_msg, parse_mode="HTML")
                elif isinstance(event, Update) and event.callback_query:
                    await event.callback_query.answer("Your account has been suspended.", show_alert=True)
                return

        return await handler(event, data)
