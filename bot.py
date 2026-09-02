import sys
import asyncio
import logging

# Ensure UTF-8 stdout/stderr encoding on Windows to prevent UnicodeEncodeError with emojis
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeDefault
from aiogram.client.default import DefaultBotProperties

from config import settings, mask_database_url
from database import init_db, async_session_factory
from handlers import setup_routers
from middlewares import DbSessionMiddleware, AuthMiddleware, ChannelMembershipMiddleware
from models.channel import Channel
from services.channel_service import ChannelService
from utils.security import mask_secret

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


async def set_bot_commands(bot: Bot) -> None:
    """Register standard commands in Telegram menu interface."""
    commands = [
        BotCommand(command="start", description="Start bot / Shuru karein"),
        BotCommand(command="coupons", description="Browse rewards & coupons"),
        BotCommand(command="points", description="Check points balance"),
        BotCommand(command="refer", description="Refer friends & earn points"),
        BotCommand(command="mycoupons", description="View redeemed coupon codes"),
        BotCommand(command="support", description="Contact admin support"),
        BotCommand(command="privacy", description="Privacy policy"),
        BotCommand(command="terms", description="Terms & disclaimer"),
    ]
    try:
        await bot.set_my_commands(commands, scope=BotCommandScopeDefault())
        logger.info("Bot menu commands registered successfully.")
    except Exception as e:
        logger.warning(f"Could not register bot commands with Telegram: {e}")


async def seed_initial_channels() -> None:
    """Ensure all channels configured in settings exist in the database."""
    channel_entries = settings.default_channel_list
    if not channel_entries:
        return

    async with async_session_factory() as session:
        existing = await ChannelService.get_all_channels(session)
        existing_ids = {c.channel_id.strip() for c in existing}

        added_count = 0
        for idx, ch_entry in enumerate(channel_entries, 1):
            clean_entry = ch_entry.strip()
            if clean_entry not in existing_ids:
                clean_username = clean_entry.lstrip("@") if clean_entry.startswith("@") else None
                title = clean_username or f"Required Channel {idx}"
                invite = f"https://t.me/{clean_username}" if clean_username else "https://t.me"
                await ChannelService.add_channel(
                    session=session,
                    admin_id=settings.ADMIN_ID or 0,
                    channel_id=clean_entry,
                    title=title,
                    invite_link=invite,
                    username=clean_username,
                )
                added_count += 1
        if added_count > 0:
            await session.commit()
            logger.info(f"Seeded {added_count} new channel(s) from configuration.")


async def main() -> None:
    """Initialize resources and start bot polling."""
    logger.info("=" * 60)
    logger.info("Starting Codes Xpress Telegram Rewards Bot 💎")
    logger.info(f"Bot Username: @{settings.BOT_USERNAME}")
    logger.info(f"Admin authorization configured: {'YES' if settings.ADMIN_ID else 'NO'}")
    logger.info(f"Primary admin ID configured: {'YES' if settings.ADMIN_ID else 'NO'}")
    logger.info(f"Total admin accounts active: {len(settings.admin_ids)}")
    logger.info(f"Database: {mask_database_url(settings.DATABASE_URL)}")
    logger.info("=" * 60)

    # Validate bot token
    is_placeholder = (
        not settings.BOT_TOKEN
        or "1234567890:ABCdefGHIjklMNOpqrsTUVwxyz123456789" in settings.BOT_TOKEN
        or ":" not in settings.BOT_TOKEN
    )

    # Initialize Database Schema
    await init_db()
    await seed_initial_channels()

    if is_placeholder:
        logger.warning("=" * 60)
        logger.warning("BOT_TOKEN is not set or contains the default placeholder.")
        logger.warning("Please update BOT_TOKEN in your .env file with a token from @BotFather.")
        logger.warning("Database initialized and ready. Safe test mode completed.")
        logger.warning("=" * 60)
        return

    # Initialize Bot & Dispatcher
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Register Middlewares
    dp.update.outer_middleware(DbSessionMiddleware())
    dp.update.outer_middleware(AuthMiddleware())
    dp.update.outer_middleware(ChannelMembershipMiddleware())

    # Register Routers
    root_router = setup_routers()
    dp.include_router(root_router)

    # Start Health & WebApp HTTP Server on dynamic $PORT
    from aiohttp import web
    from services.webapp_server import create_webapp_application

    server_port = settings.server_port
    webapp_app = create_webapp_application()
    webapp_app["bot"] = bot
    runner = web.AppRunner(webapp_app)
    await runner.setup()
    site = web.TCPSite(runner, host=settings.WEBAPP_HOST, port=server_port)
    await site.start()
    logger.info(f"Health & WebApp HTTP server running on http://{settings.WEBAPP_HOST}:{server_port} (/health ready)")
    if settings.WEBAPP_URL:
        logger.info(f"Public WebApp URL configured: {settings.WEBAPP_URL}")
    else:
        logger.warning("WEBAPP_URL is not set. Set WEBAPP_URL to your public HTTPS URL for Telegram Mini App.")

    # Delete existing webhook to enable clean polling
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception as e:
        logger.warning(f"Could not delete webhook: {e}")

    logger.info("Bot is starting Telegram updates polling...")

    async def run_polling():
        """Run aiogram long polling with auto-recovery for network dropouts."""
        retry_delay = 2
        while True:
            try:
                await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
                break
            except asyncio.CancelledError:
                logger.info("Telegram polling task received cancellation request.")
                break
            except Exception as e:
                logger.error(f"Telegram polling error: {e}. Reconnecting in {retry_delay}s...", exc_info=True)
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 30)

    polling_task = asyncio.create_task(run_polling())

    try:
        await polling_task
    except asyncio.CancelledError:
        pass
    finally:
        if not polling_task.done():
            polling_task.cancel()
            try:
                await polling_task
            except (asyncio.CancelledError, Exception):
                pass
        await runner.cleanup()
        await bot.session.close()
        logger.info("Server and Bot session closed gracefully. Goodbye!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped by user.")
