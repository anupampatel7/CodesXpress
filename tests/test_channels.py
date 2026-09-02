"""Tests for 4 Required Channels Verification and Diagnostic Permission Checks."""

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


FOUR_CHANNELS = ["@OfferRaider", "@OfferMate", "@Grabmint", "@offerelite"]


@pytest.mark.asyncio
async def test_four_channel_configuration_and_seeding(db_session: AsyncSession):
    """Verify that CHANNEL_1, CHANNEL_2, CHANNEL_3, CHANNEL_4 default list contains all 4 required channels."""
    channels_configured = settings.default_channel_list
    assert "@OfferRaider" in channels_configured
    assert "@OfferMate" in channels_configured
    assert "@Grabmint" in channels_configured
    assert "@offerelite" in channels_configured
    assert len(channels_configured) >= 4

    # Seed all 4 channels
    for ch_name in FOUR_CHANNELS:
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
    assert len(required) == 4
    ids = [c.channel_id for c in required]
    assert "@OfferRaider" in ids
    assert "@OfferMate" in ids
    assert "@Grabmint" in ids
    assert "@offerelite" in ids


@pytest.mark.asyncio
async def test_channel_verification_all_four_joined(db_session: AsyncSession, mock_bot):
    """Test: When user has joined all 4 channels -> PASS."""
    for ch_name in FOUR_CHANNELS:
        await ChannelService.add_channel(
            session=db_session,
            admin_id=123,
            channel_id=ch_name,
            title=ch_name.lstrip("@"),
            invite_link=f"https://t.me/{ch_name.lstrip('@')}",
            username=ch_name.lstrip("@"),
        )
    await db_session.commit()

    # Mock member status for all 4 channels
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
    for ch_name in FOUR_CHANNELS:
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
    for ch_name in FOUR_CHANNELS:
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
    for ch_name in FOUR_CHANNELS:
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
async def test_channel_verification_offerelite_missing(db_session: AsyncSession, mock_bot):
    """Test: When offerelite is missing -> FAIL and show missing."""
    for ch_name in FOUR_CHANNELS:
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
        if chat_id == "@offerelite":
            return MemberLeft()
        return MemberJoined()

    mock_bot.get_chat_member.side_effect = side_effect

    all_joined, missing = await ChannelService.verify_all_required_channels(
        bot=mock_bot,
        session=db_session,
        user_telegram_id=999005,
    )

    assert all_joined is False
    assert len(missing) == 1
    assert missing[0].channel_id == "@offerelite"


@pytest.mark.asyncio
async def test_channel_verification_retry_success(db_session: AsyncSession, mock_bot):
    """Test: User initially missing offerelite, then joins and retries -> PASS."""
    for ch_name in FOUR_CHANNELS:
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

    # Attempt 1: offerelite missing
    async def side_effect_1(chat_id, user_id):
        if chat_id == "@offerelite":
            return MemberLeft()
        return MemberJoined()

    mock_bot.get_chat_member.side_effect = side_effect_1

    all_joined_1, missing_1 = await ChannelService.verify_all_required_channels(
        bot=mock_bot,
        session=db_session,
        user_telegram_id=999006,
    )
    assert all_joined_1 is False
    assert len(missing_1) == 1
    assert missing_1[0].channel_id == "@offerelite"

    # Attempt 2: After user joins offerelite
    mock_bot.get_chat_member.side_effect = None
    mock_bot.get_chat_member.return_value = MemberJoined()

    all_joined_2, missing_2 = await ChannelService.verify_all_required_channels(
        bot=mock_bot,
        session=db_session,
        user_telegram_id=999006,
    )
    assert all_joined_2 is True
    assert len(missing_2) == 0


@pytest.mark.asyncio
async def test_bot_permission_diagnostic_check(mock_bot):
    """Test that diagnose_channel_setup detects permission errors and produces diagnostic message."""
    test_channel = Channel(
        id=4,
        channel_id="@offerelite",
        title="offerelite",
        invite_link="https://t.me/offerelite",
        is_required=True,
        is_active=True,
    )

    # 1. Success case
    class MockChat:
        title = "Offer Elite Channel"
    mock_bot.get_chat.return_value = MockChat()

    is_valid, msg = await ChannelService.diagnose_channel_setup(mock_bot, test_channel)
    assert is_valid is True
    assert "verified access" in msg

    # 2. Failure case
    mock_bot.get_chat.side_effect = TelegramBadRequest(
        method="getChat",
        message="Bad Request: chat not found",
    )

    is_valid_fail, diag_msg = await ChannelService.diagnose_channel_setup(mock_bot, test_channel)
    assert is_valid_fail is False
    assert "⚠️ <b>Channel Setup Issue</b>" in diag_msg or "⚠️ <b>Channel verification setup problem</b>" in diag_msg
    assert "@offerelite" in diag_msg


@pytest.mark.asyncio
async def test_channel_keyboard_contains_all_four_and_verify(db_session: AsyncSession):
    """Verify that get_channels_keyboard creates buttons for all 4 channels and Verify button."""
    from keyboards.user import get_channels_keyboard

    channels = [
        Channel(id=1, channel_id="@OfferRaider", title="OfferRaider", invite_link="https://t.me/OfferRaider", is_required=True, is_active=True),
        Channel(id=2, channel_id="@OfferMate", title="OfferMate", invite_link="https://t.me/OfferMate", is_required=True, is_active=True),
        Channel(id=3, channel_id="@Grabmint", title="Grabmint", invite_link="https://t.me/Grabmint", is_required=True, is_active=True),
        Channel(id=4, channel_id="@offerelite", title="offerelite", invite_link="https://t.me/offerelite", is_required=True, is_active=True),
    ]

    kb = get_channels_keyboard(channels)
    button_texts = [btn.text for row in kb.inline_keyboard for btn in row]

    assert any("OfferRaider" in text for text in button_texts)
    assert any("OfferMate" in text for text in button_texts)
    assert any("Grabmint" in text for text in button_texts)
    assert any("offerelite" in text for text in button_texts)
    assert any("Verify" in text for text in button_texts)
    assert len(kb.inline_keyboard) == 5  # 4 channel rows + 1 verify row


@pytest.mark.asyncio
async def test_global_channel_membership_middleware_all_cases(db_session: AsyncSession, mock_bot):
    """Test ChannelMembershipMiddleware across joined, left one, left multiple, and rejoins."""
    from unittest.mock import AsyncMock, MagicMock
    from aiogram.types import Message, CallbackQuery, User as TgUser
    from middlewares.channel_middleware import ChannelMembershipMiddleware
    from services.channel_service import ChannelService

    for ch_name in FOUR_CHANNELS:
        await ChannelService.add_channel(db_session, 123, ch_name, ch_name.lstrip("@"), f"https://t.me/{ch_name.lstrip('@')}", ch_name.lstrip("@"))
    await db_session.commit()

    middleware = ChannelMembershipMiddleware()
    user_id = 888777

    # 1. All 4 channels joined -> handler executes
    class MemberJoined:
        status = ChatMemberStatus.MEMBER

    mock_bot.get_chat_member.return_value = MemberJoined()

    mock_handler = AsyncMock(return_value="OK_CALLED")
    mock_msg = MagicMock(spec=Message)
    mock_msg.from_user = MagicMock(spec=TgUser)
    mock_msg.from_user.id = user_id
    mock_msg.web_app_data = None
    mock_msg.text = "/coupons"
    mock_msg.answer = AsyncMock()

    data = {"bot": mock_bot, "session": db_session, "is_admin": False}
    result = await middleware(mock_handler, mock_msg, data)
    assert result == "OK_CALLED"
    mock_handler.assert_called_once()
    mock_msg.answer.assert_not_called()

    # 2. User leaves one channel (@Grabmint) -> blocked, missing Grabmint shown
    class MemberLeft:
        status = ChatMemberStatus.LEFT

    async def side_effect_one_left(chat_id, user_id):
        if chat_id == "@Grabmint":
            return MemberLeft()
        return MemberJoined()

    mock_bot.get_chat_member.side_effect = side_effect_one_left
    mock_handler.reset_mock()
    mock_msg.answer.reset_mock()

    data_2 = {"bot": mock_bot, "session": db_session, "is_admin": False}
    res_blocked = await middleware(mock_handler, mock_msg, data_2)
    assert res_blocked is None
    mock_handler.assert_not_called()  # Handler blocked
    mock_msg.answer.assert_called_once()
    blocked_text = mock_msg.answer.call_args[0][0]
    assert "Grabmint" in blocked_text
    assert "Almost there" in blocked_text or "You still need to join" in blocked_text

    # 3. User leaves multiple channels (@OfferMate and @offerelite) -> blocked, all missing shown
    async def side_effect_multi_left(chat_id, user_id):
        if chat_id in ("@OfferMate", "@offerelite"):
            return MemberLeft()
        return MemberJoined()

    mock_bot.get_chat_member.side_effect = side_effect_multi_left
    mock_handler.reset_mock()
    mock_msg.answer.reset_mock()

    data_3 = {"bot": mock_bot, "session": db_session, "is_admin": False}
    res_multi = await middleware(mock_handler, mock_msg, data_3)
    assert res_multi is None
    mock_handler.assert_not_called()
    mock_msg.answer.assert_called_once()
    multi_text = mock_msg.answer.call_args[0][0]
    assert "OfferMate" in multi_text
    assert "offerelite" in multi_text

    # 4. User rejoins all channels -> command works again
    mock_bot.get_chat_member.side_effect = None
    mock_bot.get_chat_member.return_value = MemberJoined()
    mock_handler.reset_mock()
    mock_msg.answer.reset_mock()

    data_4 = {"bot": mock_bot, "session": db_session, "is_admin": False}
    res_rejoin = await middleware(mock_handler, mock_msg, data_4)
    assert res_rejoin == "OK_CALLED"
    mock_handler.assert_called_once()

    # 5. Callback query action is also guarded
    mock_cb = MagicMock(spec=CallbackQuery)
    mock_cb.from_user = MagicMock(spec=TgUser)
    mock_cb.from_user.id = user_id
    mock_cb.data = "menu_coupons"
    mock_cb.answer = AsyncMock()
    mock_cb.message = MagicMock(spec=Message)
    mock_cb.message.edit_text = AsyncMock()

    mock_bot.get_chat_member.side_effect = side_effect_one_left
    mock_handler.reset_mock()

    data_cb = {"bot": mock_bot, "session": db_session, "is_admin": False}
    res_cb = await middleware(mock_handler, mock_cb, data_cb)
    assert res_cb is None
    mock_handler.assert_not_called()
    mock_cb.answer.assert_called_once()


@pytest.mark.asyncio
async def test_coupon_redemption_and_referrals_blocked_when_channel_left(db_session: AsyncSession, mock_bot):
    """Test that coupon redemption and referral reward completion are blocked when user leaves channel."""
    from unittest.mock import AsyncMock, MagicMock
    from aiogram.types import CallbackQuery, Message, User as TgUser
    from handlers.coupons import handle_coupon_redemption
    from keyboards.user import CouponRedeemCallback
    from services.coupon_service import CouponService
    from services.user_service import UserService
    from services.referral_service import ReferralService
    from services.device_service import DeviceService
    from models.coupon import CouponCategory, StockType

    for ch_name in FOUR_CHANNELS:
        await ChannelService.add_channel(db_session, 123, ch_name, ch_name.lstrip("@"), f"https://t.me/{ch_name.lstrip('@')}", ch_name.lstrip("@"))
    await db_session.commit()

    # Create user with points
    user, _, _ = await UserService.get_or_create_user(db_session, telegram_id=777111, first_name="Redeemer")
    user.points = 10
    await db_session.commit()

    # Create coupon
    coupon = await CouponService.create_coupon(
        session=db_session,
        admin_id=1,
        title="Test Store ₹100",
        brand="Test Store",
        category=CouponCategory.SHOPPING,
        value="₹100",
        points_required=5,
        stock_type=StockType.QUANTITY,
        stock=5,
        code="TEST100",
    )
    await db_session.commit()

    # User left OfferRaider
    class MemberLeft:
        status = ChatMemberStatus.LEFT
    class MemberJoined:
        status = ChatMemberStatus.MEMBER

    async def side_effect_left(chat_id, user_id):
        if chat_id == "@OfferRaider":
            return MemberLeft()
        return MemberJoined()

    mock_bot.get_chat_member.side_effect = side_effect_left

    # Attempt redemption -> blocked by handler channel check
    mock_cb = MagicMock(spec=CallbackQuery)
    mock_cb.from_user = MagicMock(spec=TgUser)
    mock_cb.from_user.id = 777111
    mock_cb.answer = AsyncMock()
    mock_cb.message = MagicMock(spec=Message)
    mock_cb.message.edit_text = AsyncMock()

    cb_data = CouponRedeemCallback(coupon_id=coupon.id, brand="Test Store", page=1)
    await handle_coupon_redemption(mock_cb, cb_data, db_session, mock_bot)

    # Points should remain untouched
    user_check = await UserService.get_user_by_id(db_session, user.id)
    assert user_check.points == 10
    mock_cb.message.edit_text.assert_called_once()
    out_text = mock_cb.message.edit_text.call_args[0][0]
    assert "OfferRaider" in out_text

    # Referral completion test when referred user leaves channel
    referrer, _, _ = await UserService.get_or_create_user(db_session, telegram_id=777222, first_name="Referrer")
    referred_friend, _, _ = await UserService.get_or_create_user(
        db_session,
        telegram_id=777333,
        first_name="Friend",
        referral_param=f"ref_{referrer.referral_code}",
    )
    await DeviceService.verify_and_bind_device(db_session, 777333, {"device_id": "friend_dev_777333"})
    await db_session.commit()

    # Referral completion attempted while friend is missing @OfferRaider -> Held
    res, _, _ = await ReferralService.process_referral_completion(db_session, referred_friend.id, mock_bot)
    assert res is False

    ref_db = await UserService.get_user_by_id(db_session, referrer.id)
    assert ref_db.points == 0
