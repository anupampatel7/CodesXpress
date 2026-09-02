"""Global mandatory channel membership guard middleware."""

import logging
from typing import Any, Awaitable, Callable, Dict, Optional
from aiogram import BaseMiddleware, Bot
from aiogram.types import TelegramObject, Message, CallbackQuery, Update, User as TgUser
from sqlalchemy.ext.asyncio import AsyncSession
from config import settings
from services.channel_service import ChannelService
from keyboards.user import get_channels_keyboard
from utils.formatting import format_channel_missing, safe_edit_message

logger = logging.getLogger(__name__)


class ChannelMembershipMiddleware(BaseMiddleware):
    """Global middleware enforcing that users remain members of all required channels."""

    # Exempt callbacks that handle verification, support, or unblocking
    EXEMPT_CALLBACKS = {
        "verify_channels_click",
        "device_verify_action",
        "device_check_refresh",
        "menu_support",
        "support_contact_admin",
        "support_cancel",
    }

    # Exempt command strings
    EXEMPT_COMMANDS = {
        "/start",
        "start",
        "/support",
        "support",
    }

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        # Extract Telegram User ID
        user_tg_id: Optional[int] = None
        event_user: Optional[TgUser] = data.get("event_from_user")
        if event_user:
            user_tg_id = event_user.id

        if not user_tg_id:
            if isinstance(event, Message) and event.from_user:
                user_tg_id = event.from_user.id
            elif isinstance(event, CallbackQuery) and event.from_user:
                user_tg_id = event.from_user.id
            elif isinstance(event, Update):
                if event.message and event.message.from_user:
                    user_tg_id = event.message.from_user.id
                elif event.callback_query and event.callback_query.from_user:
                    user_tg_id = event.callback_query.from_user.id

        if not user_tg_id:
            return await handler(event, data)

        # Configured admins are exempt from user channel membership checks
        is_admin = data.get("is_admin", False) or settings.is_admin(user_tg_id)
        if is_admin:
            return await handler(event, data)

        # 1. Message-based exemptions (/start, web_app_data, support commands)
        if isinstance(event, Message):
            if event.web_app_data:
                return await handler(event, data)
            if event.text:
                cmd = event.text.strip().split()[0].lower()
                if cmd in self.EXEMPT_COMMANDS or cmd.startswith("/start"):
                    return await handler(event, data)

        # 2. CallbackQuery exemptions
        elif isinstance(event, CallbackQuery):
            cb_data = event.data or ""
            if cb_data in self.EXEMPT_CALLBACKS or cb_data.startswith("support_"):
                return await handler(event, data)

        # 3. Update-wrapped event exemptions
        elif isinstance(event, Update):
            if event.message:
                if event.message.web_app_data:
                    return await handler(event, data)
                if event.message.text:
                    cmd = event.message.text.strip().split()[0].lower()
                    if cmd in self.EXEMPT_COMMANDS or cmd.startswith("/start"):
                        return await handler(event, data)
            elif event.callback_query:
                cb_data = event.callback_query.data or ""
                if cb_data in self.EXEMPT_CALLBACKS or cb_data.startswith("support_"):
                    return await handler(event, data)

        bot: Optional[Bot] = data.get("bot")
        session: Optional[AsyncSession] = data.get("session")

        if not bot or not session:
            return await handler(event, data)

        # Verify all required channels with per-update caching
        all_joined, missing = await ChannelService.verify_all_required_channels(
            bot=bot,
            session=session,
            user_telegram_id=user_tg_id,
            cache=data,
        )

        if not all_joined and missing:
            logger.info(
                f"Global Channel Guard: User #{user_tg_id} blocked. Missing channel(s): {[c.channel_id for c in missing]}"
            )
            missing_text = format_channel_missing(missing)
            channel_kb = get_channels_keyboard(missing, is_retry=True)

            if isinstance(event, Message):
                await event.answer(missing_text, reply_markup=channel_kb, parse_mode="HTML")
            elif isinstance(event, CallbackQuery):
                await event.answer("⚠️ Membership required in all channels to proceed.", show_alert=True)
                await safe_edit_message(event, missing_text, reply_markup=channel_kb)
            elif isinstance(event, Update):
                if event.message:
                    await event.message.answer(missing_text, reply_markup=channel_kb, parse_mode="HTML")
                elif event.callback_query:
                    await event.callback_query.answer("⚠️ Membership required in all channels to proceed.", show_alert=True)
                    await safe_edit_message(event.callback_query, missing_text, reply_markup=channel_kb)
            return

        return await handler(event, data)
