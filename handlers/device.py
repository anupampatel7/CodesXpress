"""Device verification callback and WebApp data handler for anti-fraud referral protection."""

import json
import asyncio
import logging
from aiogram import Router, Bot, F
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession
from config import settings
from services.device_service import DeviceService
from services.user_service import UserService
from services.channel_service import ChannelService
from services.referral_service import ReferralService
from keyboards.user import (
    get_main_menu_keyboard,
    get_channels_keyboard,
    get_device_blocked_keyboard,
)
from utils.formatting import (
    format_device_blocked,
    format_device_verification_success,
    format_account_activated,
    format_channel_missing,
    format_user_welcome,
    safe_edit_message,
)
from utils.security import validate_telegram_webapp_init_data

logger = logging.getLogger(__name__)

router = Router(name="device_router")


@router.callback_query(F.data == "device_verify_action")
async def handle_device_verify_callback(
    callback: CallbackQuery,
    session: AsyncSession,
    is_admin: bool,
    bot: Bot,
) -> None:
    """Enforce real WebApp verification; block fake fallback when WEBAPP_URL is missing."""
    await callback.answer("⚠️ Verification unavailable", show_alert=True)
    text = (
        "⚠️ <b>Verification unavailable</b>\n\n"
        "Admin setup required.\n\n"
        "If you need help, please contact Support."
    )
    await safe_edit_message(
        callback,
        text,
        reply_markup=get_device_blocked_keyboard(),
    )


@router.callback_query(F.data == "device_check_refresh")
async def handle_device_check_refresh(
    callback: CallbackQuery,
    session: AsyncSession,
    is_admin: bool,
    bot: Bot,
) -> None:
    """Check if device verification completed in Mini App and activate account."""
    from_user = callback.from_user
    if not from_user:
        return

    is_device_ok = await DeviceService.is_device_verified(session, from_user.id)
    if not is_device_ok:
        await callback.answer("⚠️ Device not yet verified. Please tap 'Verify Device'.", show_alert=True)
        return

    all_joined, missing = await ChannelService.verify_all_required_channels(
        bot=bot,
        session=session,
        user_telegram_id=from_user.id,
    )
    if not all_joined and missing:
        await callback.answer("⚠️ Please join all required channels first.", show_alert=True)
        channel_kb = get_channels_keyboard(missing, is_retry=True)
        missing_text = format_channel_missing(missing)
        await safe_edit_message(callback, missing_text, reply_markup=channel_kb)
        return

    user = await UserService.get_user_by_telegram_id(session, from_user.id)
    if user and user.referred_by:
        await ReferralService.process_referral_completion(
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
    await asyncio.gather(
        callback.answer("✅ Verification confirmed!", show_alert=False),
        safe_edit_message(callback, welcome_text, reply_markup=menu_kb),
    )


@router.message(F.web_app_data)
async def handle_webapp_verification_data(
    message: Message,
    session: AsyncSession,
    is_admin: bool,
    bot: Bot,
) -> None:
    """Process device verification completion submitted from Telegram WebApp."""
    from_user = message.from_user
    if not from_user or not message.web_app_data:
        return

    raw_data = message.web_app_data.data
    parsed_payload = {}
    try:
        parsed_payload = json.loads(raw_data) if raw_data else {}
    except Exception:
        parsed_payload = {"raw": raw_data}

    # Check if user is already verified in DB or admin
    is_already_verified = is_admin or await DeviceService.is_device_verified(session, from_user.id)

    if not is_already_verified:
        init_data_raw = parsed_payload.get("init_data") if isinstance(parsed_payload, dict) else None
        fp_data = parsed_payload.get("fingerprint") if isinstance(parsed_payload, dict) else None

        # If client passed init_data, cryptographically validate Telegram HMAC
        if init_data_raw:
            validated_ctx = validate_telegram_webapp_init_data(init_data_raw, settings.BOT_TOKEN)
            if not validated_ctx or "user" not in validated_ctx:
                logger.warning(f"Spoofing rejected: Invalid initData for User {from_user.id}")
                await message.answer(
                    format_device_blocked(),
                    reply_markup=get_device_blocked_keyboard(),
                    parse_mode="HTML",
                )
                return
            verified_id = validated_ctx["user"].get("id")
            if verified_id and int(verified_id) != from_user.id:
                logger.warning(f"Spoofing detected: WebApp claimed User {verified_id} but Telegram sender is {from_user.id}")
                await message.answer(
                    format_device_blocked(),
                    reply_markup=get_device_blocked_keyboard(),
                    parse_mode="HTML",
                )
                return

        # If payload only contains client claim {"verified": true} without backend DB binding or fingerprint
        if not fp_data:
            if isinstance(parsed_payload, dict) and any(k in parsed_payload for k in ("device_id", "screen", "canvas", "timezone")):
                fp_data = parsed_payload
            else:
                # No fingerprint and not verified in DB -> reject client-only claim
                logger.warning(f"Verification rejected: Client-only verified claim without backend binding for User {from_user.id}")
                await message.answer(
                    format_device_blocked(),
                    reply_markup=get_device_blocked_keyboard(),
                    parse_mode="HTML",
                )
                return

        # Attempt atomic device binding
        success, code, binding = await DeviceService.verify_and_bind_device(
            session=session,
            telegram_user_id=from_user.id,
            fingerprint_payload=fp_data,
            user_agent="TelegramWebApp/1.0",
        )

        if not success:
            logger.warning(f"Device verification failed for User {from_user.id}: {code}")
            await message.answer(
                format_device_blocked(),
                reply_markup=get_device_blocked_keyboard(),
                parse_mode="HTML",
            )
            return

    # Device is verified! Check channel requirements
    all_joined, missing = await ChannelService.verify_all_required_channels(
        bot=bot,
        session=session,
        user_telegram_id=from_user.id,
    )

    if not all_joined and missing:
        channel_kb = get_channels_keyboard(missing, is_retry=False)
        success_text = (
            format_device_verification_success()
            + "\n\n🔒 <b>Quick Verification</b>\n\nJoin all required channels to activate your referral reward."
        )
        await message.answer(success_text, reply_markup=channel_kb, parse_mode="HTML")
        return

    # Fulfill referral reward atomically if pending
    user = await UserService.get_user_by_telegram_id(session, from_user.id)
    if user and user.referred_by:
        await ReferralService.process_referral_completion(
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
    await message.answer(welcome_text, reply_markup=menu_kb, parse_mode="HTML")
