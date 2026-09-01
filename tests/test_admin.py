"""Tests for admin functions: restock, bulk codes, channels, user management, and security."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from config import settings
from models.coupon import Coupon, CouponCategory, StockType
from models.coupon_code import CouponCode, CodeStatus
from models.channel import Channel
from models.user import User
from services.user_service import UserService
from services.coupon_service import CouponService
from services.stock_service import StockService
from services.channel_service import ChannelService
from utils.security import is_admin_user


@pytest.mark.asyncio
async def test_admin_authorization():
    """Verify admin ID checking."""
    settings.ADMIN_ID = 123456789
    settings.ADDITIONAL_ADMINS = "987654321, 555666777"

    assert is_admin_user(123456789) is True
    assert is_admin_user(987654321) is True
    assert is_admin_user(555666777) is True
    assert is_admin_user(111222333) is False


@pytest.mark.asyncio
async def test_admin_restock_quantity(db_session: AsyncSession):
    """Verify restock quantity validation and atomic increase."""
    coupon = await CouponService.create_coupon(
        session=db_session,
        admin_id=999,
        title="Restock Test Coupon",
        brand="BrandR",
        category=CouponCategory.SHOPPING,
        value="₹100",
        points_required=5,
        stock_type=StockType.QUANTITY,
        stock=17,
        code="RESTOCK17",
    )
    await db_session.commit()

    # Reject zero or negative restock
    s_neg, msg_neg, _ = await StockService.restock_quantity(db_session, 999, coupon.id, -10)
    assert s_neg is False

    s_zero, msg_zero, _ = await StockService.restock_quantity(db_session, 999, coupon.id, 0)
    assert s_zero is False

    # Valid restock +100
    s_pos, msg_pos, new_stock = await StockService.restock_quantity(db_session, 999, coupon.id, 100)
    await db_session.commit()

    assert s_pos is True
    assert new_stock == 117
    await db_session.refresh(coupon)
    assert coupon.stock == 117


@pytest.mark.asyncio
async def test_admin_bulk_code_import_deduplication(db_session: AsyncSession):
    """Verify bulk codes import skips duplicates and updates available stock."""
    coupon = await CouponService.create_coupon(
        session=db_session,
        admin_id=999,
        title="Bulk Code Coupon",
        brand="BrandB",
        category=CouponCategory.GAMING,
        value="₹100",
        points_required=5,
        stock_type=StockType.UNIQUE_CODES,
        stock=0,
    )
    await db_session.commit()

    # Import first batch: 3 codes
    raw_1 = "CODE001\nCODE002\nCODE003"
    s1, _, stats1 = await StockService.bulk_import_unique_codes(db_session, 999, coupon.id, raw_1)
    await db_session.commit()

    assert s1 is True
    assert stats1["imported"] == 3
    assert stats1["duplicates"] == 0
    assert stats1["total_available"] == 3

    # Import second batch with 2 overlapping and 1 new
    raw_2 = "CODE002\nCODE003\nCODE004"
    s2, _, stats2 = await StockService.bulk_import_unique_codes(db_session, 999, coupon.id, raw_2)
    await db_session.commit()

    assert s2 is True
    assert stats2["imported"] == 1  # only CODE004
    assert stats2["duplicates"] == 2  # CODE002 and CODE003 skipped
    assert stats2["total_available"] == 4


@pytest.mark.asyncio
async def test_admin_channel_management(db_session: AsyncSession):
    """Verify adding, toggling, and deleting required channels."""
    # Add Channel
    s_add, msg_add, channel = await ChannelService.add_channel(
        session=db_session,
        admin_id=999,
        channel_id="-1001987654321",
        title="Test Channel",
        invite_link="https://t.me/TestChannel",
        username="TestChannel",
    )
    await db_session.commit()

    assert s_add is True
    assert channel.is_active is True
    assert channel.is_required is True

    # Toggle Channel Status (Active -> Inactive)
    s_tog, msg_tog = await ChannelService.toggle_channel_status(db_session, 999, channel.id)
    await db_session.commit()
    assert s_tog is True
    await db_session.refresh(channel)
    assert channel.is_active is False

    # Delete Channel
    s_del, msg_del = await ChannelService.delete_channel(db_session, 999, channel.id)
    await db_session.commit()
    assert s_del is True

    # Verify channel is gone
    ch_fetch = await ChannelService.get_channel_by_id(db_session, channel.id)
    assert ch_fetch is None


@pytest.mark.asyncio
async def test_admin_user_ban_toggle(db_session: AsyncSession):
    """Verify banning and unbanning a user."""
    user, _, _ = await UserService.get_or_create_user(session=db_session, telegram_id=903, first_name="Bannable")
    await db_session.commit()

    assert user.is_banned is False

    # Ban
    s_ban, _ = await UserService.set_user_ban_status(db_session, 999, user.id, is_banned=True)
    await db_session.commit()
    assert s_ban is True
    await db_session.refresh(user)
    assert user.is_banned is True

    # Unban
    s_unban, _ = await UserService.set_user_ban_status(db_session, 999, user.id, is_banned=False)
    await db_session.commit()
    assert s_unban is True
    await db_session.refresh(user)
    assert user.is_banned is False


@pytest.mark.asyncio
async def test_admin_edit_coupon(db_session: AsyncSession):
    """Verify editing coupon attributes."""
    coupon = await CouponService.create_coupon(
        session=db_session,
        admin_id=999,
        title="Original Title",
        brand="OriginalBrand",
        category=CouponCategory.SHOPPING,
        value="₹50",
        points_required=3,
        stock_type=StockType.QUANTITY,
        stock=10,
        code="ORIG50",
    )
    await db_session.commit()

    success, msg, updated = await CouponService.update_coupon(
        session=db_session,
        admin_id=999,
        coupon_id=coupon.id,
        title="Updated Title",
        value="₹100",
        points_required=6,
        code="NEW100",
    )
    await db_session.commit()

    assert success is True
    assert updated.title == "Updated Title"
    assert updated.value == "₹100"
    assert updated.points_required == 6
    assert updated.code == "NEW100"


@pytest.mark.asyncio
async def test_admin_view_codes_breakdown(db_session: AsyncSession):
    """Verify inspecting unique codes pool and status counts."""
    coupon = await CouponService.create_coupon(
        session=db_session,
        admin_id=999,
        title="Codes Pool Coupon",
        brand="PoolBrand",
        category=CouponCategory.GAMING,
        value="₹100",
        points_required=2,
        stock_type=StockType.UNIQUE_CODES,
        stock=0,
    )
    await db_session.commit()

    # Import 3 codes
    await StockService.bulk_import_unique_codes(db_session, 999, coupon.id, "CD1\nCD2\nCD3")
    await db_session.commit()

    codes, breakdown = await StockService.get_coupon_codes(db_session, coupon.id)
    assert len(codes) == 3
    assert breakdown["AVAILABLE"] == 3
    assert breakdown["USED"] == 0


@pytest.mark.asyncio
async def test_admin_authorization_edge_cases():
    """Verify string, whitespace, quotes, missing, and additional admin ID parsing."""
    from config import Settings

    # Case 1: String ADMIN_ID with quotes and whitespace
    s1 = Settings(ADMIN_ID=' "8976799765 " ', ADDITIONAL_ADMINS=' 111222333, "444555666" ')
    assert s1.ADMIN_ID == 8976799765
    assert s1.is_admin(8976799765) is True
    assert s1.is_admin("8976799765") is True
    assert s1.is_admin(111222333) is True
    assert s1.is_admin("444555666") is True
    assert s1.is_admin(999999999) is False

    # Case 2: Missing ADMIN_ID (default 0)
    s2 = Settings(ADMIN_ID=0, ADDITIONAL_ADMINS="")
    assert s2.is_admin(8976799765) is False
    assert s2.is_admin(None) is False
    assert s2.is_admin("") is False


@pytest.mark.asyncio
async def test_auth_middleware_with_update_object():
    """Verify AuthMiddleware correctly sets is_admin for Update objects in aiogram 3."""
    from middlewares.auth_middleware import AuthMiddleware
    from unittest.mock import AsyncMock, MagicMock
    from config import settings

    settings.ADMIN_ID = 8976799765
    middleware = AuthMiddleware()

    # 1. Admin user sends message inside an Update
    admin_user = MagicMock()
    admin_user.id = 8976799765
    msg_admin = MagicMock()
    msg_admin.from_user = admin_user
    update_admin = MagicMock()
    update_admin.message = msg_admin
    update_admin.callback_query = None
    update_admin.inline_query = None

    data_admin = {"event_from_user": admin_user}
    handler_mock = AsyncMock()

    await middleware(handler_mock, update_admin, data_admin)
    assert data_admin["is_admin"] is True

    # 2. Regular unauthorized user
    regular_user = MagicMock()
    regular_user.id = 123456789
    msg_reg = MagicMock()
    msg_reg.from_user = regular_user
    update_reg = MagicMock()
    update_reg.message = msg_reg
    update_reg.callback_query = None
    update_reg.inline_query = None

    data_reg = {"event_from_user": regular_user}
    await middleware(handler_mock, update_reg, data_reg)
    assert data_reg["is_admin"] is False


@pytest.mark.asyncio
async def test_require_admin_guard():
    """Verify require_admin rejects unauthorized and approves authorized users."""
    from handlers.admin import require_admin
    from unittest.mock import AsyncMock, MagicMock
    from aiogram.types import Message, CallbackQuery
    from config import settings

    settings.ADMIN_ID = 8976799765

    # 1. Authorized message
    admin_msg = MagicMock(spec=Message)
    admin_msg.from_user = MagicMock()
    admin_msg.from_user.id = 8976799765
    auth_res = await require_admin(admin_msg, is_admin=None)
    assert auth_res is True

    # 2. Unauthorized message
    unauth_msg = MagicMock(spec=Message)
    unauth_msg.from_user = MagicMock()
    unauth_msg.from_user.id = 111111111
    unauth_msg.answer = AsyncMock()
    unauth_res = await require_admin(unauth_msg, is_admin=False)
    assert unauth_res is False
    unauth_msg.answer.assert_called_once()
    assert "Unauthorized" in unauth_msg.answer.call_args[0][0]

    # 3. Unauthorized callback query
    unauth_cb = MagicMock(spec=CallbackQuery)
    unauth_cb.from_user = MagicMock()
    unauth_cb.from_user.id = 111111111
    unauth_cb.answer = AsyncMock()
    unauth_cb_res = await require_admin(unauth_cb, is_admin=False)
    assert unauth_cb_res is False
    unauth_cb.answer.assert_called_once_with("❌ Unauthorized access.", show_alert=True)

