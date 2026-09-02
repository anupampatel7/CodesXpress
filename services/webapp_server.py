"""Aiohttp WebApp HTTP server for serving Telegram WebApp Mini App and verifying device identity."""

import json
import logging
from pathlib import Path
from aiohttp import web
from config import settings, BASE_DIR
import database
from services.device_service import DeviceService
from utils.security import validate_telegram_webapp_init_data

logger = logging.getLogger(__name__)

WEBAPP_HTML_PATH = BASE_DIR / "webapp" / "index.html"


async def handle_get_verify(request: web.Request) -> web.Response:
    """Serve the WebApp HTML interface."""
    if not WEBAPP_HTML_PATH.exists():
        return web.Response(text="<h1>WebApp file not found.</h1>", status=404, content_type="text/html")
    html_content = WEBAPP_HTML_PATH.read_text(encoding="utf-8")
    return web.Response(text=html_content, content_type="text/html")


async def handle_post_verify_device(request: web.Request) -> web.Response:
    """Validate Telegram WebApp initData and atomically bind device fingerprint."""
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"success": False, "code": "INVALID_JSON", "message": "Invalid JSON body."}, status=400)

    init_data = data.get("init_data", "")
    fingerprint = data.get("fingerprint", {})

    if not init_data:
        return web.json_response({"success": False, "code": "MISSING_INIT_DATA", "message": "Missing Telegram initData."}, status=401)

    # 1. Cryptographic HMAC validation of Telegram session
    validated_ctx = validate_telegram_webapp_init_data(init_data, settings.BOT_TOKEN)
    if not validated_ctx or "user" not in validated_ctx or "id" not in validated_ctx["user"]:
        logger.warning("Rejected WebApp verification: Forged or invalid Telegram initData")
        return web.json_response({"success": False, "code": "UNAUTHORIZED", "message": "Telegram authentication failed."}, status=401)

    telegram_user_id = int(validated_ctx["user"]["id"])
    user_agent = request.headers.get("User-Agent", "TelegramWebApp/1.0")
    client_ip = request.remote or request.headers.get("X-Forwarded-For", "")

    # 2. Atomic Device Binding & Anti-Fraud check
    async with database.async_session_factory() as session:
        success, code, binding = await DeviceService.verify_and_bind_device(
            session=session,
            telegram_user_id=telegram_user_id,
            fingerprint_payload=fingerprint,
            user_agent=user_agent,
            ip_address=client_ip,
        )
        if success:
            await session.commit()

            # Push real-time Telegram activation message to user if all requirements are satisfied
            bot = request.app.get("bot")
            if bot:
                try:
                    from services.user_service import UserService
                    from services.channel_service import ChannelService
                    from services.referral_service import ReferralService
                    from keyboards.user import get_main_menu_keyboard
                    from utils.formatting import format_user_welcome, format_account_activated

                    user = await UserService.get_user_by_telegram_id(session, telegram_user_id)
                    if user:
                        all_joined, missing = await ChannelService.verify_all_required_channels(
                            bot=bot,
                            session=session,
                            user_telegram_id=telegram_user_id,
                        )
                        if all_joined:
                            if user.referred_by:
                                await ReferralService.process_referral_completion(
                                    session=session,
                                    user_id=user.id,
                                    bot=bot,
                                )
                                await session.commit()
                            welcome_text = (
                                format_account_activated()
                                + "\n\n"
                                + format_user_welcome(user, settings.BOT_USERNAME)
                            )
                            menu_kb = get_main_menu_keyboard(is_admin=settings.is_admin(telegram_user_id))
                            await bot.send_message(
                                chat_id=telegram_user_id,
                                text=welcome_text,
                                reply_markup=menu_kb,
                                parse_mode="HTML",
                            )
                except Exception as e:
                    logger.warning(f"Could not push activation message to user {telegram_user_id}: {e}")

            return web.json_response({"success": True, "code": code, "message": "Device verified successfully."})
        else:
            await session.rollback()
            if code == "DEVICE_ALREADY_BOUND":
                return web.json_response({
                    "success": False,
                    "code": "DEVICE_ALREADY_BOUND",
                    "message": "This device has already been used for referral verification.",
                }, status=403)
            elif code == "USER_ALREADY_BOUND_TO_ANOTHER_DEVICE":
                return web.json_response({
                    "success": False,
                    "code": "USER_ALREADY_BOUND_TO_ANOTHER_DEVICE",
                    "message": "This Telegram account is already registered on another device.",
                }, status=403)
            elif code == "DEVICE_BLOCKED":
                return web.json_response({
                    "success": False,
                    "code": "DEVICE_BLOCKED",
                    "message": "This device is blocked due to suspected abuse.",
                }, status=403)
            return web.json_response({
                "success": False,
                "code": code,
                "message": "Device verification was not approved.",
            }, status=400)


async def handle_health(request: web.Request) -> web.Response:
    """Healthcheck endpoint for Render and UptimeRobot."""
    return web.json_response({"status": "ok"})


def create_webapp_application() -> web.Application:
    """Create and configure the aiohttp web application."""
    app = web.Application()
    app.router.add_get("/verify", handle_get_verify)
    app.router.add_post("/api/verify-device", handle_post_verify_device)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/", handle_get_verify)
    return app
