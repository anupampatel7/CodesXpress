"""Channel membership verification callback handler."""

import logging
from aiogram import Router, Bot, F
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from config import settings
from services.user_service import UserService
from services.channel_service import ChannelService
from services.referral_service import ReferralService
from services.device_service import DeviceService
from keyboards.user import (
    get_main_menu_keyboard,
    get_channels_keyboard,
    get_device_verification_keyboard,
)
from utils.formatting import (
    format_user_welcome,
    format_channel_missing,
    format_channel_verified,
    format_account_activated,
    format_device_verification_prompt,
    safe_edit_message,
)

logger = logging.getLogger(__name__)

router = Router(name="channels_router")


@router.callback_query(F.data == "verify_channels_click")
async def handle_channel_verification(
    callback: CallbackQuery,
    session: AsyncSession,
    is_admin: bool,
    bot: Bot,
) -> None:
    """Verify that the user joined all required channels and prompt device verification if needed."""
    from_user = callback.from_user
    if not from_user:
        await callback.answer("User error", show_alert=True)
        return

    user = await UserService.get_user_by_telegram_id(session, from_user.id)
    if not user:
        user, _, _ = await UserService.get_or_create_user(
            session=session,
            telegram_id=from_user.id,
            username=from_user.username,
            first_name=from_user.first_name or "",
            last_name=from_user.last_name,
        )

    # 1. Check channels via Telegram API first
    all_joined, missing = await ChannelService.verify_all_required_channels(
        bot=bot,
        session=session,
        user_telegram_id=from_user.id,
    )

    if not all_joined and missing:
        await callback.answer("⚠️ Please join all required channels.", show_alert=True)
        channel_kb = get_channels_keyboard(missing, is_retry=True)
        missing_text = format_channel_missing(missing)
        await safe_edit_message(callback, missing_text, reply_markup=channel_kb)
        return

    # 2. Channels verified! Check if device verification is completed (Admins are exempt)
    is_device_ok = is_admin or await DeviceService.is_device_verified(session, from_user.id)
    if not is_device_ok:
        await callback.answer("✅ Channels verified! Please verify your device.", show_alert=False)
        device_text = (
            format_channel_verified()
            + "\n\n"
            + format_device_verification_prompt()
        )
        await safe_edit_message(
            callback,
            device_text,
            reply_markup=get_device_verification_keyboard(),
        )
        return

    # 3. Verification fully successful
    await callback.answer("✅ Verification successful.", show_alert=False)

    # Trigger referral fulfillment (awards +1 point to referrer)
    if user.referred_by:
        reward_given, referrer, pts = await ReferralService.process_referral_completion(
            session=session,
            user_id=user.id,
            bot=bot,
        )

    welcome_text = (
        format_account_activated()
        + "\n\n"
        + format_user_welcome(user, settings.BOT_USERNAME)
    )
    menu_kb = get_main_menu_keyboard(is_admin=is_admin)

    await safe_edit_message(callback, welcome_text, reply_markup=menu_kb)
