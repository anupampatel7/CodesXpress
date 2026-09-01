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
    assert any("BigBasket ₹60 OFF" in t and "6 ⭐" in t for t in btn_texts)
    assert any("Myntra ₹100 OFF" in t and "6 ⭐" in t for t in btn_texts)


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


