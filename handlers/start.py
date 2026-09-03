"""Start command handler with referral processing, device verification, and channel check."""

import logging
from aiogram import Router, Bot, F
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession
from config import settings
from services.user_service import UserService
from services.channel_service import ChannelService
from services.device_service import DeviceService
from services.referral_service import ReferralService
from keyboards.user import (
    get_main_menu_keyboard,
    get_channels_keyboard,
    get_device_verification_keyboard,
)
from utils.formatting import (
    format_user_welcome,
    format_channel_prompt,
    format_device_verification_prompt,
)

logger = logging.getLogger(__name__)

router = Router(name="start_router")


@router.message(CommandStart())
async def handle_start_command(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    is_admin: bool,
    bot: Bot,
) -> None:
    """Handle /start command with deep-link referral processing, device check, and channel check."""
    from_user = message.from_user
    if not from_user:
        return

    referral_arg = command.args.strip() if command.args else None

    # Get or create user
    user, is_created, pending_referral = await UserService.get_or_create_user(
        session=session,
        telegram_id=from_user.id,
        username=from_user.username,
        first_name=from_user.first_name or "",
        last_name=from_user.last_name,
        referral_param=referral_arg,
    )

    if user.is_banned:
        await message.answer(
            "🚫 <b>Account Suspended!</b>",
            parse_mode="HTML",
        )
        return

    # 1. Check required channels membership first
    all_joined, missing = await ChannelService.verify_all_required_channels(
        bot=bot,
        session=session,
        user_telegram_id=from_user.id,
    )

    if not all_joined and missing:
        channel_kb = get_channels_keyboard(missing, is_retry=False)
        await message.answer(
            format_channel_prompt(missing),
            reply_markup=channel_kb,
            parse_mode="HTML",
        )
        return

    # 2. Check device verification (Admins are always exempt)
    is_device_ok = is_admin or await DeviceService.is_device_verified(session, from_user.id)
    if not is_device_ok:
        await message.answer(
            format_device_verification_prompt(),
            reply_markup=get_device_verification_keyboard(),
            parse_mode="HTML",
        )
        return

    # 3. If all requirements satisfied, complete pending referral if any
    if user.referred_by:
        await ReferralService.process_referral_completion(
            session=session,
            user_id=user.id,
            bot=bot,
        )

    # User is verified or no channels required
    welcome_text = format_user_welcome(user, settings.BOT_USERNAME)
    menu_kb = get_main_menu_keyboard(is_admin=is_admin)

    await message.answer(
        welcome_text,
        reply_markup=menu_kb,
        parse_mode="HTML",
    )
