"""Tests for coupon creation, brand-first filtering, search, and expiry."""

import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from models.coupon import Coupon, CouponCategory, StockType
from services.coupon_service import CouponService
from keyboards.user import (
    get_brands_paginated_keyboard,
    get_brand_coupons_keyboard,
    get_redeem_confirm_keyboard,
    get_no_brands_keyboard,
)


@pytest.mark.asyncio
async def test_coupon_creation_and_categories(db_session: AsyncSession):
    """Verify coupon creation with categories and stock."""
    coupon = await CouponService.create_coupon(
        session=db_session,
        admin_id=999,
        title="Swiggy ₹150 OFF",
        brand="Swiggy",
        category=CouponCategory.FOOD,
        value="₹150",
        points_required=5,
        stock_type=StockType.QUANTITY,
        stock=25,
        code="SWIGGY150",
        description="Flat 150 off on orders above 499",
    )
    await db_session.commit()

    assert coupon.id is not None
    assert coupon.brand == "Swiggy"
    assert coupon.category == CouponCategory.FOOD
    assert coupon.stock == 25
    assert coupon.is_active is True


@pytest.mark.asyncio
async def test_brand_first_dynamic_filtering(db_session: AsyncSession):
    """Verify that only brands with active, unexpired, in-stock coupons appear."""
    # 1. Myntra: active & in stock
    await CouponService.create_coupon(
        session=db_session,
        admin_id=999,
        title="₹100 OFF",
        brand="Myntra",
        value="₹100",
        points_required=6,
        stock_type=StockType.QUANTITY,
        stock=12,
    )
    # 2. BigBasket: active & in stock
    await CouponService.create_coupon(
        session=db_session,
        admin_id=999,
        title="₹50 OFF",
        brand="BigBasket",
        value="₹50",
        points_required=4,
        stock_type=StockType.QUANTITY,
        stock=5,
    )
    # 3. Domino's: Out of stock (stock=0) -> MUST NOT appear
    await CouponService.create_coupon(
        session=db_session,
        admin_id=999,
        title="Free Garlic Bread",
        brand="Domino's",
        value="Free Item",
        points_required=5,
        stock_type=StockType.QUANTITY,
        stock=0,
    )
    # 4. PVR: Inactive -> MUST NOT appear
    pvr = await CouponService.create_coupon(
        session=db_session,
        admin_id=999,
        title="₹100 Ticket OFF",
        brand="PVR",
        value="₹100",
        points_required=5,
        stock_type=StockType.QUANTITY,
        stock=10,
    )
    pvr.is_active = False

    # 5. SHEIN: Expired -> MUST NOT appear
    await CouponService.create_coupon(
        session=db_session,
        admin_id=999,
        title="20% OFF",
        brand="SHEIN",
        value="20%",
        points_required=8,
        stock_type=StockType.QUANTITY,
        stock=10,
        expiry_date=datetime.now(timezone.utc) - timedelta(days=5),
    )
    await db_session.commit()

    brands, total_brands, _ = await CouponService.get_available_brands(db_session, page=1)
    assert "Myntra" in brands
    assert "BigBasket" in brands
    assert "Domino's" not in brands
    assert "PVR" not in brands
    assert "SHEIN" not in brands
    assert total_brands == 2


@pytest.mark.asyncio
async def test_get_coupons_by_brand(db_session: AsyncSession):
    """Verify fetching coupons for a selected brand."""
    await CouponService.create_coupon(
        session=db_session,
        admin_id=999,
        title="₹100 OFF",
        brand="Myntra",
        value="₹100",
        points_required=6,
        stock_type=StockType.QUANTITY,
        stock=10,
    )
    await CouponService.create_coupon(
        session=db_session,
        admin_id=999,
        title="5% OFF",
        brand="Myntra",
        value="5%",
        points_required=6,
        stock_type=StockType.QUANTITY,
        stock=8,
    )
    await CouponService.create_coupon(
        session=db_session,
        admin_id=999,
        title="₹200 OFF",
        brand="Flipkart",
        value="₹200",
        points_required=10,
        stock_type=StockType.QUANTITY,
        stock=4,
    )
    await db_session.commit()

    myntra_coupons, myntra_count, _ = await CouponService.get_coupons_by_brand(db_session, "Myntra")
    assert myntra_count == 2
    assert all(c.brand == "Myntra" for c in myntra_coupons)
    titles = [c.title for c in myntra_coupons]
    assert "₹100 OFF" in titles
    assert "5% OFF" in titles


@pytest.mark.asyncio
async def test_brand_and_confirmation_keyboards():
    """Verify brand buttons and confirmation keyboard."""
    # Brand keyboard
    kb_brands = get_brands_paginated_keyboard(brands=["Myntra", "BigBasket", "Amazon"], page=1, total_pages=1)
    button_texts = [btn.text for row in kb_brands.inline_keyboard for btn in row]
    assert any("👗 Myntra" in t for t in button_texts)
    assert any("🛒 BigBasket" in t for t in button_texts)
    assert any("📦 Amazon" in t for t in button_texts)

    # Empty brands keyboard
    kb_empty = get_no_brands_keyboard()
    empty_texts = [btn.text for row in kb_empty.inline_keyboard for btn in row]
    assert "🔄 Refresh" in empty_texts
    assert "🏠 Main Menu" in empty_texts

    # Redeem confirm keyboard
    kb_confirm = get_redeem_confirm_keyboard(coupon_id=1, brand="Myntra", page=1)
    confirm_texts = [btn.text for row in kb_confirm.inline_keyboard for btn in row]
    assert "✅ Confirm" in confirm_texts
    assert "↩️ Cancel" in confirm_texts or "❌ Cancel" in confirm_texts


@pytest.mark.asyncio
async def test_direct_available_coupons_query_and_keyboard(db_session: AsyncSession):
    """Verify that get_available_coupons returns active in-stock coupons for direct buttons."""
    from keyboards.user import get_available_coupons_keyboard

    await CouponService.create_coupon(
        session=db_session,
        admin_id=999,
        title="BigBasket ₹60 OFF",
        brand="BigBasket",
        value="₹60",
        points_required=6,
        stock_type=StockType.QUANTITY,
        stock=5,
    )
    await CouponService.create_coupon(
        session=db_session,
        admin_id=999,
        title="Myntra ₹100 OFF",
        brand="Myntra",
        value="₹100",
        points_required=6,
        stock_type=StockType.QUANTITY,
        stock=10,
    )
    await db_session.commit()

    coupons, total_count, _ = await CouponService.get_available_coupons(db_session, page=1)
    assert total_count >= 2
    kb = get_available_coupons_keyboard(coupons, page=1, total_pages=1)
    btn_texts = [btn.text for row in kb.inline_keyboard for btn in row]
    assert any("🟢 BigBasket ₹60 OFF ⭐ 6" in t for t in btn_texts)
    assert any("🟢 Myntra ₹100 OFF ⭐ 6" in t for t in btn_texts)


@pytest.mark.asyncio
async def test_simplified_add_coupon_flow(db_session: AsyncSession):
    """Verify new 4-step coupon creation with Name, Description, Points, and Multiple Codes."""
    from services.stock_service import StockService
    from utils.formatting import format_coupon_detail

    # 1. Create coupon with name, description, points
    coupon = await CouponService.create_coupon(
        session=db_session,
        admin_id=999,
        title="BIGBASKET ₹60 OFF",
        brand="BIGBASKET",
        value="",
        description="₹60 OFF on minimum ₹199 order.\nValid for new users.",
        points_required=6,
        stock_type=StockType.UNIQUE_CODES,
        stock=0,
        code=None,
        terms="₹60 OFF on minimum ₹199 order.\nValid for new users.",
    )
    await db_session.flush()

    # 2. Bulk import 4 unique codes
    success, _, stats = await StockService.bulk_import_unique_codes(
        session=db_session,
        admin_id=999,
        coupon_id=coupon.id,
        raw_text="CODE001\nCODE002\nCODE003\nCODE004",
    )
    await db_session.commit()

    assert coupon.id is not None
    assert coupon.title == "BIGBASKET ₹60 OFF"
    assert coupon.description == "₹60 OFF on minimum ₹199 order.\nValid for new users."
    assert coupon.points_required == 6
    assert stats["imported"] == 4
    assert stats["total_available"] == 4

    # 3. Check user-facing format
    detail_text = format_coupon_detail(coupon, available_stock=4)
    assert "🎟 <b>BIGBASKET ₹60 OFF</b>" in detail_text
    assert "📝 ₹60 OFF on minimum ₹199 order." in detail_text
    assert "⭐ <b>Redeem:</b> 6 Points" in detail_text


@pytest.mark.asyncio
async def test_exact_coupon_code_inputs_and_persistence(db_session: AsyncSession):
    """Test single code, 4 codes, blank lines, duplicate codes, and subsequent redemption."""
    from sqlalchemy import select
    from models.coupon_code import CouponCode, CodeStatus
    from models.user import User
    from services.user_service import UserService
    from services.stock_service import StockService

    # 1. Single code test
    c1 = await CouponService.create_coupon(
        session=db_session,
        admin_id=999,
        title="Single Code Coupon",
        brand="SingleBrand",
        points_required=5,
        stock_type=StockType.UNIQUE_CODES,
        description="Single code test description",
    )
    await db_session.flush()
    s1, _, stats1 = await StockService.bulk_import_unique_codes(
        session=db_session,
        admin_id=999,
        coupon_id=c1.id,
        raw_text="CODE001",
    )
    await db_session.commit()
    assert s1 is True
    assert stats1["imported"] == 1
    assert stats1["total_available"] == 1

    # Verify directly from DB table
    db_codes_1 = (await db_session.execute(select(CouponCode.code).where(CouponCode.coupon_id == c1.id))).scalars().all()
    assert list(db_codes_1) == ["CODE001"]

    # 2. 4 codes with extra blank lines and duplicates
    c2 = await CouponService.create_coupon(
        session=db_session,
        admin_id=999,
        title="Multi Code Coupon",
        brand="MultiBrand",
        points_required=3,
        stock_type=StockType.UNIQUE_CODES,
        description="4 codes test description",
    )
    await db_session.flush()
    # Input with blank lines and duplicate CODE002
    raw_input = "\n\nCODE002\n\nCODE003\n   \nCODE004\nCODE002\n"
    s2, _, stats2 = await StockService.bulk_import_unique_codes(
        session=db_session,
        admin_id=999,
        coupon_id=c2.id,
        raw_text=raw_input,
    )
    await db_session.commit()
    assert s2 is True
    assert stats2["imported"] == 3  # CODE002, CODE003, CODE004 (duplicate CODE002 skipped)
    assert stats2["duplicates"] == 1
    assert stats2["total_available"] == 3

    # Restock with ABC123 and XYZ456
    s2_restock, _, stats2_restock = await StockService.bulk_import_unique_codes(
        session=db_session,
        admin_id=999,
        coupon_id=c2.id,
        raw_text="ABC123\nXYZ456",
    )
    await db_session.commit()
    assert s2_restock is True
    assert stats2_restock["imported"] == 2
    assert stats2_restock["total_available"] == 5

    # Verify all 5 codes exist in DB
    db_codes_2 = (await db_session.execute(select(CouponCode.code).where(CouponCode.coupon_id == c2.id))).scalars().all()
    assert set(db_codes_2) == {"CODE002", "CODE003", "CODE004", "ABC123", "XYZ456"}

    # 3. Test subsequent redemption consuming one code at a time
    user, _, _ = await UserService.get_or_create_user(session=db_session, telegram_id=777888, first_name="TestBuyer")
    user.points = 20
    await db_session.commit()

    redeem_success, _, redemption = await CouponService.redeem_coupon(
        session=db_session,
        user_id=user.id,
        coupon_id=c2.id,
    )
    await db_session.commit()
    assert redeem_success is True
    assert redemption is not None
    assert redemption.coupon_code in {"CODE002", "CODE003", "CODE004", "ABC123", "XYZ456"}

    # Verify that code is now USED in database
    used_code_obj = (
        await db_session.execute(
            select(CouponCode).where(CouponCode.coupon_id == c2.id, CouponCode.code == redemption.coupon_code)
        )
    ).scalar_one()
    assert used_code_obj.status == CodeStatus.USED
    assert used_code_obj.assigned_to_user_id == user.id

    # Verify remaining stock is 4
    rem_stock = await StockService.get_authoritative_stock(db_session, c2)
    assert rem_stock == 4


@pytest.mark.asyncio
async def test_out_of_stock_coupon_and_my_coupons_ui(db_session: AsyncSession):
    """Verify out-of-stock coupon button format 🔴, detail message, and direct My Coupons rendering."""
    from aiogram.types import Message
    from keyboards.user import get_available_coupons_keyboard
    from handlers.coupons import handle_coupon_detail, CouponDetailCallback
    from handlers.profile import handle_my_coupons
    from services.user_service import UserService
    from unittest.mock import AsyncMock, MagicMock

    # 1. Create 1 in-stock and 1 out-of-stock coupon
    c_in = await CouponService.create_coupon(
        session=db_session,
        admin_id=999,
        title="BigBasket",
        brand="BigBasket",
        points_required=3,
        stock_type=StockType.QUANTITY,
        stock=5,
    )
    c_out = await CouponService.create_coupon(
        session=db_session,
        admin_id=999,
        title="Myntra",
        brand="Myntra",
        points_required=5,
        stock_type=StockType.QUANTITY,
        stock=0,
    )
    await db_session.commit()

    # Verify both are returned by get_available_coupons
    coupons, total, _ = await CouponService.get_available_coupons(db_session)
    assert total >= 2

    # Verify button formats in keyboard
    kb = get_available_coupons_keyboard(coupons, page=1, total_pages=1)
    btn_texts = [btn.text for row in kb.inline_keyboard for btn in row]
    assert any("🟢 BigBasket ⭐ 3" in t for t in btn_texts)
    assert any("🔴 Myntra ⭐ 5" in t for t in btn_texts)

    # 2. Test clicking out of stock coupon
    user, _, _ = await UserService.get_or_create_user(db_session, 666777, first_name="Clicker")
    user.points = 100
    await db_session.commit()

    cb_out = MagicMock()
    cb_out.from_user = MagicMock(id=666777, username="clicker", first_name="Clicker", last_name=None)
    cb_out.message = MagicMock()
    cb_out.message.edit_text = AsyncMock()
    cb_out.answer = AsyncMock()

    await handle_coupon_detail(
        callback=cb_out,
        callback_data=CouponDetailCallback(coupon_id=c_out.id, brand="Myntra", page=1),
        session=db_session,
    )

    cb_out.message.edit_text.assert_called_once()
    shown_text = cb_out.message.edit_text.call_args[0][0]
    assert "🔴 <b>Out of Stock</b>" in shown_text
    assert "This coupon is currently unavailable." in shown_text

    # 3. Test My Coupons empty state
    msg_empty = MagicMock(spec=Message)
    msg_empty.from_user = MagicMock(id=666777, username="clicker", first_name="Clicker", last_name=None)
    msg_empty.text = "/mycoupons"
    msg_empty.answer = AsyncMock()

    await handle_my_coupons(msg_empty, db_session)
    msg_empty.answer.assert_called_once()
    assert "🎟️ No redeemed coupons yet." in msg_empty.answer.call_args[0][0]

    # 4. User redeems in-stock coupon and tests My Coupons populated state
    s_red, _, red = await CouponService.redeem_coupon(db_session, user.id, c_in.id)
    await db_session.commit()
    assert s_red is True

    msg_pop = MagicMock(spec=Message)
    msg_pop.from_user = MagicMock(id=666777, username="clicker", first_name="Clicker", last_name=None)
    msg_pop.text = "/mycoupons"
    msg_pop.answer = AsyncMock()

    await handle_my_coupons(msg_pop, db_session)
    msg_pop.answer.assert_called_once()
    pop_text = msg_pop.answer.call_args[0][0]
    assert "🎟️ <b>My Coupons</b>" in pop_text
    assert "BigBasket" in pop_text
    assert red.coupon_code in pop_text



