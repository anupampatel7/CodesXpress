"""Tests for Required Channel Verification and Diagnostic Permission Checks."""

import pytest
from unittest.mock import AsyncMock
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from config import settings
from models.channel import Channel
from services.channel_service import ChannelService
from utils.formatting import format_channel_diagnostic_error


@pytest.mark.asyncio
async def test_three_channel_configuration_and_seeding(db_session: AsyncSession):
    """Verify that CHANNEL_1, CHANNEL_2, CHANNEL_3 default list contains the 3 required channels."""
    channels_configured = settings.default_channel_list
    assert "@OfferRaider" in channels_configured
    assert "@OfferMate" in channels_configured
    assert "@Grabmint" in channels_configured
    assert len(channels_configured) >= 3

    # Seed channels
    for ch_name in ["@OfferRaider", "@OfferMate", "@Grabmint"]:
        await ChannelService.add_channel(
            session=db_session,
            admin_id=123,
            channel_id=ch_name,
            title=ch_name.lstrip("@"),
            invite_link=f"https://t.me/{ch_name.lstrip('@')}",
            username=ch_name.lstrip("@"),
        )
    await db_session.commit()

    required = await ChannelService.get_required_channels(db_session)
    assert len(required) == 3
    ids = [c.channel_id for c in required]
    assert "@OfferRaider" in ids
    assert "@OfferMate" in ids
    assert "@Grabmint" in ids


@pytest.mark.asyncio
async def test_channel_verification_all_three_joined(db_session: AsyncSession, mock_bot):
    """Test: When user has joined all 3 channels -> PASS."""
    # Setup 3 channels in DB
    for ch_name in ["@OfferRaider", "@OfferMate", "@Grabmint"]:
        await ChannelService.add_channel(
            session=db_session,
            admin_id=123,
            channel_id=ch_name,
            title=ch_name.lstrip("@"),
            invite_link=f"https://t.me/{ch_name.lstrip('@')}",
            username=ch_name.lstrip("@"),
        )
    await db_session.commit()

    # Mock member status for all 3 channels
    class MockMember:
        status = ChatMemberStatus.MEMBER

    mock_bot.get_chat_member.return_value = MockMember()

    all_joined, missing = await ChannelService.verify_all_required_channels(
        bot=mock_bot,
        session=db_session,
        user_telegram_id=999001,
    )

    assert all_joined is True
    assert len(missing) == 0


@pytest.mark.asyncio
async def test_channel_verification_offerraider_missing(db_session: AsyncSession, mock_bot):
    """Test: When OfferRaider is missing -> FAIL and show missing."""
    for ch_name in ["@OfferRaider", "@OfferMate", "@Grabmint"]:
        await ChannelService.add_channel(
            session=db_session,
            admin_id=123,
            channel_id=ch_name,
            title=ch_name.lstrip("@"),
            invite_link=f"https://t.me/{ch_name.lstrip('@')}",
            username=ch_name.lstrip("@"),
        )
    await db_session.commit()

    class MemberJoined:
        status = ChatMemberStatus.MEMBER

    class MemberLeft:
        status = ChatMemberStatus.LEFT

    async def side_effect(chat_id, user_id):
        if chat_id == "@OfferRaider":
            return MemberLeft()
        return MemberJoined()

    mock_bot.get_chat_member.side_effect = side_effect

    all_joined, missing = await ChannelService.verify_all_required_channels(
        bot=mock_bot,
        session=db_session,
        user_telegram_id=999002,
    )

    assert all_joined is False
    assert len(missing) == 1
    assert missing[0].channel_id == "@OfferRaider"


@pytest.mark.asyncio
async def test_channel_verification_offermate_missing(db_session: AsyncSession, mock_bot):
    """Test: When OfferMate is missing -> FAIL and show missing."""
    for ch_name in ["@OfferRaider", "@OfferMate", "@Grabmint"]:
        await ChannelService.add_channel(
            session=db_session,
            admin_id=123,
            channel_id=ch_name,
            title=ch_name.lstrip("@"),
            invite_link=f"https://t.me/{ch_name.lstrip('@')}",
            username=ch_name.lstrip("@"),
        )
    await db_session.commit()

    class MemberJoined:
        status = ChatMemberStatus.MEMBER

    class MemberLeft:
        status = ChatMemberStatus.LEFT

    async def side_effect(chat_id, user_id):
        if chat_id == "@OfferMate":
            return MemberLeft()
        return MemberJoined()

    mock_bot.get_chat_member.side_effect = side_effect

    all_joined, missing = await ChannelService.verify_all_required_channels(
        bot=mock_bot,
        session=db_session,
        user_telegram_id=999003,
    )

    assert all_joined is False
    assert len(missing) == 1
    assert missing[0].channel_id == "@OfferMate"


@pytest.mark.asyncio
async def test_channel_verification_grabmint_missing(db_session: AsyncSession, mock_bot):
    """Test: When Grabmint is missing -> FAIL and show missing."""
    for ch_name in ["@OfferRaider", "@OfferMate", "@Grabmint"]:
        await ChannelService.add_channel(
            session=db_session,
            admin_id=123,
            channel_id=ch_name,
            title=ch_name.lstrip("@"),
            invite_link=f"https://t.me/{ch_name.lstrip('@')}",
            username=ch_name.lstrip("@"),
        )
    await db_session.commit()

    class MemberJoined:
        status = ChatMemberStatus.MEMBER

    class MemberLeft:
        status = ChatMemberStatus.LEFT

    async def side_effect(chat_id, user_id):
        if chat_id == "@Grabmint":
            return MemberLeft()
        return MemberJoined()

    mock_bot.get_chat_member.side_effect = side_effect

    all_joined, missing = await ChannelService.verify_all_required_channels(
        bot=mock_bot,
        session=db_session,
        user_telegram_id=999004,
    )

    assert all_joined is False
    assert len(missing) == 1
    assert missing[0].channel_id == "@Grabmint"


@pytest.mark.asyncio
async def test_channel_verification_retry_success(db_session: AsyncSession, mock_bot):
    """Test: User initially missing Grabmint, then joins and retries -> PASS."""
    for ch_name in ["@OfferRaider", "@OfferMate", "@Grabmint"]:
        await ChannelService.add_channel(
            session=db_session,
            admin_id=123,
            channel_id=ch_name,
            title=ch_name.lstrip("@"),
            invite_link=f"https://t.me/{ch_name.lstrip('@')}",
            username=ch_name.lstrip("@"),
        )
    await db_session.commit()

    class MemberJoined:
        status = ChatMemberStatus.MEMBER

    class MemberLeft:
        status = ChatMemberStatus.LEFT

    # Attempt 1: Grabmint missing
    async def side_effect_1(chat_id, user_id):
        if chat_id == "@Grabmint":
            return MemberLeft()
        return MemberJoined()

    mock_bot.get_chat_member.side_effect = side_effect_1

    all_joined_1, missing_1 = await ChannelService.verify_all_required_channels(
        bot=mock_bot,
        session=db_session,
        user_telegram_id=999005,
    )
    assert all_joined_1 is False
    assert len(missing_1) == 1

    # Attempt 2: After user joins Grabmint
    mock_bot.get_chat_member.side_effect = None
    mock_bot.get_chat_member.return_value = MemberJoined()

    all_joined_2, missing_2 = await ChannelService.verify_all_required_channels(
        bot=mock_bot,
        session=db_session,
        user_telegram_id=999005,
    )
    assert all_joined_2 is True
    assert len(missing_2) == 0


@pytest.mark.asyncio
async def test_bot_permission_diagnostic_check(mock_bot):
    """Test that diagnose_channel_setup detects permission errors and produces diagnostic message."""
    test_channel = Channel(
        id=1,
        channel_id="@OfferRaider",
        title="OfferRaider",
        invite_link="https://t.me/OfferRaider",
        is_required=True,
        is_active=True,
    )

    # 1. Success case
    class MockChat:
        title = "OfferRaider Official"
    mock_bot.get_chat.return_value = MockChat()

    is_valid, msg = await ChannelService.diagnose_channel_setup(mock_bot, test_channel)
    assert is_valid is True
    assert "verified access" in msg

    # 2. Failure case (e.g. ChatNotFound or Forbidden)
    mock_bot.get_chat.side_effect = TelegramBadRequest(
        method="getChat",
        message="Bad Request: chat not found",
    )

    is_valid_fail, diag_msg = await ChannelService.diagnose_channel_setup(mock_bot, test_channel)
    assert is_valid_fail is False
    assert "⚠️ <b>Channel verification setup problem</b>" in diag_msg
    assert "@OfferRaider" in diag_msg
    assert "Bot is not added to the channel" in diag_msg


@pytest.mark.asyncio
async def test_channel_keyboard_contains_all_three_and_verify(db_session: AsyncSession):
    """Verify that get_channels_keyboard creates buttons for OfferRaider, OfferMate, Grabmint, and Verify."""
    from keyboards.user import get_channels_keyboard

    channels = [
        Channel(id=1, channel_id="@OfferRaider", title="OfferRaider", invite_link="https://t.me/OfferRaider", is_required=True, is_active=True),
        Channel(id=2, channel_id="@OfferMate", title="OfferMate", invite_link="https://t.me/OfferMate", is_required=True, is_active=True),
        Channel(id=3, channel_id="@Grabmint", title="Grabmint", invite_link="https://t.me/Grabmint", is_required=True, is_active=True),
    ]

    kb = get_channels_keyboard(channels)
    button_texts = [btn.text for row in kb.inline_keyboard for btn in row]

    assert any("OfferRaider" in text for text in button_texts)
    assert any("OfferMate" in text for text in button_texts)
    assert any("Grabmint" in text for text in button_texts)
    assert any("Verify" in text for text in button_texts)
    assert len(kb.inline_keyboard) == 4  # 3 channel rows + 1 verify row

