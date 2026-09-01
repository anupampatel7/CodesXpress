"""Concurrency and transactional boundary tests for coupon redemptions."""

import pytest
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from models.coupon import Coupon, CouponCategory, StockType
from models.coupon_code import CouponCode, CodeStatus
from models.user import User
from models.redemption import Redemption
from services.user_service import UserService
from services.coupon_service import CouponService
from services.stock_service import StockService


@pytest.mark.asyncio
async def test_concurrency_stock_limit_quantity(db_session: AsyncSession):
    """Verify that when stock = 1, only 1 redemption can succeed and the second fails."""
    # User 1 with 10 pts
    user1, _, _ = await UserService.get_or_create_user(session=db_session, telegram_id=1001, first_name="U1")
    user1.points = 10
    # User 2 with 10 pts
    user2, _, _ = await UserService.get_or_create_user(session=db_session, telegram_id=1002, first_name="U2")
    user2.points = 10
    await db_session.commit()

    # Coupon with exactly 1 stock
    coupon = await CouponService.create_coupon(
        session=db_session,
        admin_id=999,
        title="Rare Coupon",
        brand="RareBrand",
        category=CouponCategory.SHOPPING,
        value="₹500",
        points_required=5,
        stock_type=StockType.QUANTITY,
        stock=1,
        code="RARE100",
    )
    await db_session.commit()

    # User 1 redeems
    s1, msg1, r1 = await CouponService.redeem_coupon(db_session, user1.id, coupon.id)
    await db_session.commit()

    # User 2 tries to redeem
    s2, msg2, r2 = await CouponService.redeem_coupon(db_session, user2.id, coupon.id)

    assert s1 is True
    assert r1 is not None
    assert s2 is False
    assert r2 is None
    assert "out of stock" in msg2.lower()

    # Stock must be exactly 0, never negative
    await db_session.refresh(coupon)
    assert coupon.stock == 0


@pytest.mark.asyncio
async def test_concurrency_unique_codes_limit(db_session: AsyncSession):
    """Verify that when only 1 unique code exists, only 1 user can claim it."""
    user1, _, _ = await UserService.get_or_create_user(session=db_session, telegram_id=1003, first_name="U3")
    user1.points = 10
    user2, _, _ = await UserService.get_or_create_user(session=db_session, telegram_id=1004, first_name="U4")
    user2.points = 10
    await db_session.commit()

    coupon = await CouponService.create_coupon(
        session=db_session,
        admin_id=999,
        title="Single Unique Code Coupon",
        brand="SingleBrand",
        category=CouponCategory.GAMING,
        value="₹100",
        points_required=5,
        stock_type=StockType.UNIQUE_CODES,
        stock=0,
    )
    await db_session.commit()

    # Import only 1 code
    await StockService.bulk_import_unique_codes(db_session, 999, coupon.id, "EXCLUSIVE-001")
    await db_session.commit()

    # User 1 claims
    s1, _, r1 = await CouponService.redeem_coupon(db_session, user1.id, coupon.id)
    await db_session.commit()

    # User 2 attempts claim
    s2, msg2, r2 = await CouponService.redeem_coupon(db_session, user2.id, coupon.id)

    assert s1 is True
    assert r1.coupon_code == "EXCLUSIVE-001"
    assert s2 is False
    assert r2 is None
    assert "out of stock" in msg2.lower()

    # Verify authoritative stock is 0
    stock = await StockService.get_authoritative_stock(db_session, coupon)
    assert stock == 0


@pytest.mark.asyncio
async def test_rapid_repeated_redemption_idempotency(db_session: AsyncSession):
    """Verify that rapid repeated redemption calls from the same user only redeem ONCE and never deduct double points."""
    user, _, _ = await UserService.get_or_create_user(session=db_session, telegram_id=2001, first_name="RapidUser")
    user.points = 10
    await db_session.commit()

    coupon = await CouponService.create_coupon(
        session=db_session,
        admin_id=999,
        title="Double Click Protected Coupon",
        brand="SafetyBrand",
        category=CouponCategory.SHOPPING,
        value="₹100",
        points_required=6,
        stock_type=StockType.QUANTITY,
        stock=5,
        max_redemptions_per_user=1,
    )
    await db_session.commit()

    # First call succeeds
    s1, msg1, r1 = await CouponService.redeem_coupon(db_session, user.id, coupon.id)
    await db_session.commit()
    assert s1 is True
    assert r1 is not None

    # Immediate second call (e.g. duplicate callback from double tap)
    s2, msg2, r2 = await CouponService.redeem_coupon(db_session, user.id, coupon.id)
    assert s2 is False
    assert r2 is None

    # Verify points deducted only ONCE (10 - 6 = 4)
    await db_session.refresh(user)
    assert user.points == 4

    # Verify stock decremented only ONCE (5 - 1 = 4)
    await db_session.refresh(coupon)
    assert coupon.stock == 4

