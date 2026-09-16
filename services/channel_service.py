import asyncio
import logging
import time
from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict, Union
from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramAPIError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from config import settings
from models.channel import Channel
from models.admin_action import AdminAction
from utils.formatting import format_channel_diagnostic_error

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ChannelDTO:
    """Immutable, session-independent representation of a required channel."""
    id: int
    channel_id: str
    title: str
    invite_link: str
    username: Optional[str] = None
    is_required: bool = True
    is_active: bool = True

    def __repr__(self) -> str:
        return f"<ChannelDTO(id={self.id}, title='{self.title}', channel_id='{self.channel_id}', active={self.is_active})>"


# Normalized chat_id cache
_NORMALIZED_CHAT_ID_CACHE: Dict[str, str | int] = {}

# In-memory channels configuration cache: (expiry_monotonic, channels_dto_list)
_REQUIRED_CHANNELS_CACHE: Tuple[float, List[ChannelDTO]] = (0.0, [])
_CHANNELS_CONFIG_TTL = 300.0  # 5 minutes


def invalidate_channel_cache(user_telegram_id: Optional[int] = None) -> None:
    """Invalidate channel configuration and normalized chat ID caches."""
    global _REQUIRED_CHANNELS_CACHE
    _REQUIRED_CHANNELS_CACHE = (0.0, [])
    _NORMALIZED_CHAT_ID_CACHE.clear()


class ChannelService:
    """Service for managing required channels and verifying user membership."""

    @staticmethod
    async def get_required_channels(session: AsyncSession, force_refresh: bool = False) -> List[ChannelDTO]:
        """Fetch all active channels that require verification (cached in memory as session-independent DTOs)."""
        global _REQUIRED_CHANNELS_CACHE
        now = time.monotonic()
        if not force_refresh and now < _REQUIRED_CHANNELS_CACHE[0] and _REQUIRED_CHANNELS_CACHE[1]:
            return _REQUIRED_CHANNELS_CACHE[1]

        stmt = (
            select(Channel)
            .where(Channel.is_active == True, Channel.is_required == True)
            .order_by(Channel.id.asc())
        )
        res = await session.execute(stmt)
        channels = [
            ChannelDTO(
                id=c.id,
                channel_id=c.channel_id,
                title=c.title,
                invite_link=c.invite_link,
                username=c.username,
                is_required=c.is_required,
                is_active=c.is_active,
            )
            for c in res.scalars().all()
        ]
        _REQUIRED_CHANNELS_CACHE = (now + _CHANNELS_CONFIG_TTL, channels)
        return channels

    @staticmethod
    async def get_all_channels(session: AsyncSession) -> List[Channel]:
        """Fetch all channels configured in the bot (admin view)."""
        stmt = select(Channel).order_by(Channel.id.asc())
        res = await session.execute(stmt)
        return list(res.scalars().all())

    @staticmethod
    async def get_channel_by_id(session: AsyncSession, channel_pk: int) -> Optional[Channel]:
        """Fetch channel by primary key ID."""
        stmt = select(Channel).where(Channel.id == channel_pk)
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    @staticmethod
    async def add_channel(
        session: AsyncSession,
        admin_id: int,
        channel_id: str,
        title: str,
        invite_link: str,
        username: Optional[str] = None,
    ) -> Tuple[bool, str, Optional[Channel]]:
        """Add a new required channel."""
        invalidate_channel_cache()
        clean_id = channel_id.strip()
        # Check if already exists
        check_stmt = select(Channel).where(Channel.channel_id == clean_id)
        exists = (await session.execute(check_stmt)).scalar_one_or_none()
        if exists:
            return False, "Channel already exists.", None

        channel = Channel(
            channel_id=clean_id,
            username=username.strip("@") if username else None,
            title=title.strip(),
            invite_link=invite_link.strip(),
            is_required=True,
            is_active=True,
        )
        session.add(channel)

        audit = AdminAction(
            admin_id=admin_id,
            action="ADD_CHANNEL",
            target=f"Channel {title} ({clean_id})",
            details=f"Invite: {invite_link}",
        )
        session.add(audit)
        await session.flush()
        return True, "Channel added successfully.", channel

    @staticmethod
    async def delete_channel(session: AsyncSession, admin_id: int, channel_pk: int) -> Tuple[bool, str]:
        """Delete a channel by primary key ID."""
        invalidate_channel_cache()
        channel = await ChannelService.get_channel_by_id(session, channel_pk)
        if not channel:
            return False, "Channel not found."

        channel_title = channel.title
        channel_id_str = channel.channel_id
        await session.delete(channel)

        audit = AdminAction(
            admin_id=admin_id,
            action="DELETE_CHANNEL",
            target=f"Channel {channel_title} ({channel_id_str})",
            details="Deleted channel configuration",
        )
        session.add(audit)
        await session.flush()
        return True, "Channel deleted successfully."

    @staticmethod
    async def toggle_channel_status(session: AsyncSession, admin_id: int, channel_pk: int) -> Tuple[bool, str]:
        """Toggle active status of a channel."""
        invalidate_channel_cache()
        channel = await ChannelService.get_channel_by_id(session, channel_pk)
        if not channel:
            return False, "Channel not found."

        channel.is_active = not channel.is_active
        action = "ENABLE_CHANNEL" if channel.is_active else "DISABLE_CHANNEL"
        audit = AdminAction(
            admin_id=admin_id,
            action=action,
            target=f"Channel {channel.title} ({channel.channel_id})",
            details=f"Set is_active = {channel.is_active}",
        )
        session.add(audit)
        await session.flush()
        status_str = "enabled" if channel.is_active else "disabled"
        return True, f"Channel {status_str} successfully."

    @staticmethod
    def normalize_chat_id(channel_id: str) -> str | int:
        """Normalize channel ID string into Telegram Chat ID parameter (cached)."""
        cached = _NORMALIZED_CHAT_ID_CACHE.get(channel_id)
        if cached is not None:
            return cached
        clean = channel_id.strip()
        if clean.startswith("-100") or (clean.startswith("-") and clean[1:].isdigit()) or clean.isdigit():
            val = int(clean)
        elif not clean.startswith("@"):
            val = f"@{clean}"
        else:
            val = clean
        _NORMALIZED_CHAT_ID_CACHE[channel_id] = val
        return val

    @staticmethod
    async def diagnose_channel_setup(
        bot: Bot,
        channel: Union[Channel, ChannelDTO],
    ) -> Tuple[bool, str]:
        """Test bot access and admin permissions in a configured channel.

        Returns:
            Tuple of (is_valid: bool, diagnostic_message: str)
        """
        chat_param = ChannelService.normalize_chat_id(channel.channel_id)
        try:
            # Check bot access via get_chat
            chat = await bot.get_chat(chat_id=chat_param)
            return True, f"✅ Bot has verified access to channel <b>{chat.title or channel.title}</b> ({channel.channel_id})."
        except TelegramAPIError as e:
            error_msg = format_channel_diagnostic_error(channel.channel_id, str(e))
            logger.warning(f"Diagnostic check failed for channel {channel.channel_id}: {e}")
            return False, error_msg
        except Exception as e:
            error_msg = format_channel_diagnostic_error(channel.channel_id, str(e))
            logger.error(f"Unexpected error diagnosing channel {channel.channel_id}: {e}", exc_info=True)
            return False, error_msg

    @staticmethod
    async def check_user_membership(
        bot: Bot,
        user_telegram_id: int,
        channel: Union[Channel, ChannelDTO],
    ) -> bool:
        """Verify if a user is currently a member of the given channel.

        Acceptable statuses:
        - MEMBER
        - ADMINISTRATOR
        - CREATOR
        - RESTRICTED (with is_member == True)
        """
        chat_id_param = ChannelService.normalize_chat_id(channel.channel_id)
        try:
            member = await bot.get_chat_member(chat_id=chat_id_param, user_id=user_telegram_id)
            
            valid_direct_statuses = {
                ChatMemberStatus.MEMBER,
                ChatMemberStatus.ADMINISTRATOR,
                ChatMemberStatus.CREATOR,
                "member",
                "administrator",
                "creator",
            }

            if member.status in valid_direct_statuses or (
                getattr(member, "status", None) == ChatMemberStatus.RESTRICTED and bool(getattr(member, "is_member", False))
            ):
                return True

            return False
        except TelegramAPIError as e:
            err_text = str(e)
            logger.warning(
                f"Telegram API check failed for user {user_telegram_id} on channel {channel.channel_id}: {err_text}"
            )
            setup_error_markers = [
                "chat not found",
                "not enough rights",
                "bot is not a member",
                "bot was kicked",
                "chat admin required",
                "forbidden",
                "bad request",
            ]
            if any(marker in err_text.lower() for marker in setup_error_markers):
                diag_msg = format_channel_diagnostic_error(channel.channel_id, err_text)
                logger.error(f"⚠️ Channel verification setup problem detected:\n{diag_msg}")
                if settings.ADMIN_ID and settings.ADMIN_ID != 0 and bot:
                    try:
                        await bot.send_message(
                            chat_id=settings.ADMIN_ID,
                            text=diag_msg,
                            parse_mode="HTML",
                        )
                    except Exception as admin_err:
                        logger.debug(f"Could not dispatch diagnostic alert to admin: {admin_err}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error checking channel membership: {e}", exc_info=True)
            return False

    @staticmethod
    async def verify_all_required_channels(
        bot: Bot,
        session: AsyncSession,
        user_telegram_id: int,
        cache: Optional[dict] = None,
        force_refresh: bool = False,
    ) -> Tuple[bool, List[ChannelDTO]]:
        """Verify that user is a member of all active required channels concurrently.

        Returns:
            Tuple of (all_joined: bool, missing_channels: List[ChannelDTO])
        """
        start_time = time.perf_counter()

        # 1. Per-update dict cache check
        cache_key = f"_ch_ver_{user_telegram_id}"
        if not force_refresh and cache is not None and cache_key in cache:
            return cache[cache_key]

        required_channels = await ChannelService.get_required_channels(session)
        if not required_channels:
            res = (True, [])
            if cache is not None:
                cache[cache_key] = res
            return res

        # 2. Concurrent verification of all channels using asyncio.gather
        tasks = [
            ChannelService.check_user_membership(bot, user_telegram_id, ch)
            for ch in required_channels
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        missing = []
        for ch, is_member in zip(required_channels, results):
            if is_member is True:
                continue
            missing.append(ch)

        all_joined = (len(missing) == 0)
        res = (all_joined, missing)

        if cache is not None:
            cache[cache_key] = res

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        logger.debug(
            f"[PERF] Channel verification User #{user_telegram_id}: {elapsed_ms:.2f}ms (all_joined={all_joined})"
        )
        return res
