"""Tests for atomic coupon redemptions, stock decrement, and unique codes assignment."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.user import User
from models.coupon import Coupon, CouponCategory, StockType
from models.coupon_code import CouponCode, CodeStatus
from models.redemption import Redemption, RedemptionStatus
from models.point_transaction import PointTransaction, TransactionType
from services.user_service import UserService
from services.coupon_service import CouponService
from services.stock_service import StockService


@pytest.mark.asyncio
async def test_quantity_mode_redemption_success(db_session: AsyncSession):
    """Verify standard QUANTITY mode coupon redemption lifecycle."""
    # 1. Create user with 10 points
    user, _, _ = await UserService.get_or_create_user(session=db_session, telegram_id=801, first_name="Redeemer")
    user.points = 10
    await db_session.commit()

    # 2. Create quantity coupon requiring 6 points with stock 5
    coupon = await CouponService.create_coupon(
        session=db_session,
        admin_id=999,
        title="Amazon ₹100",
        brand="Amazon",
        category=CouponCategory.SHOPPING,
        value="₹100",
        points_required=6,
        stock_type=StockType.QUANTITY,
        stock=5,
        code="AMZ100XXXX",
    )
    await db_session.commit()

    # 3. Perform redemption
    success, msg, redemption = await CouponService.redeem_coupon(
        session=db_session,
        user_id=user.id,
        coupon_id=coupon.id,
    )
    await db_session.commit()

    assert success is True
    assert redemption is not None
    assert redemption.coupon_code == "AMZ100XXXX"
    assert redemption.points_spent == 6
    assert redemption.status == RedemptionStatus.SUCCESS

    # Check remaining points = 4
    stmt_user = select(User).where(User.id == user.id)
    user_updated = (await db_session.execute(stmt_user)).scalar_one()
    assert user_updated.points == 4

    # Check remaining stock = 4
    stmt_coupon = select(Coupon).where(Coupon.id == coupon.id)
    coupon_updated = (await db_session.execute(stmt_coupon)).scalar_one()
    assert coupon_updated.stock == 4

    # Check ledger transaction
    stmt_tx = select(PointTransaction).where(
        PointTransaction.user_id == user.id,
        PointTransaction.type == TransactionType.COUPON_REDEMPTION,
    )
    tx = (await db_session.execute(stmt_tx)).scalar_one()
    assert tx.amount == -6


@pytest.mark.asyncio
async def test_unique_codes_mode_redemption_success(db_session: AsyncSession):
    """Verify UNIQUE_CODES mode where each user receives an individual distinct code."""
    # 1. Create user with 5 points
    user, _, _ = await UserService.get_or_create_user(session=db_session, telegram_id=802, first_name="UniqueRedeemer")
    user.points = 5
    await db_session.commit()

    # 2. Create coupon in UNIQUE_CODES mode
    coupon = await CouponService.create_coupon(
        session=db_session,
        admin_id=999,
        title="Google Play ₹50",
        brand="Google",
        category=CouponCategory.GAMING,
        value="₹50",
        points_required=3,
        stock_type=StockType.UNIQUE_CODES,
        stock=0,
    )
    await db_session.commit()

    # 3. Bulk import 2 unique codes
    await StockService.bulk_import_unique_codes(
        session=db_session,
        admin_id=999,
        coupon_id=coupon.id,
        raw_text="GPLAY-AAA-111\nGPLAY-BBB-222",
    )
    await db_session.commit()

    # Authoritative stock should be 2
    stock = await StockService.get_authoritative_stock(db_session, coupon)
    assert stock == 2

    # 4. User redeems coupon
    success, msg, redemption = await CouponService.redeem_coupon(
        session=db_session,
        user_id=user.id,
        coupon_id=coupon.id,
    )
    await db_session.commit()

    assert success is True
    assert redemption.coupon_code in ["GPLAY-AAA-111", "GPLAY-BBB-222"]
    assert redemption.points_spent == 3

    # Check remaining user points = 2
    await db_session.refresh(user)
    assert user.points == 2

    # Check that 1 code is now USED and 1 is AVAILABLE
    codes_stmt = select(CouponCode).where(CouponCode.coupon_id == coupon.id)
    all_codes = list((await db_session.execute(codes_stmt)).scalars().all())
    used_codes = [c for c in all_codes if c.status == CodeStatus.USED]
    avail_codes = [c for c in all_codes if c.status == CodeStatus.AVAILABLE]

    assert len(used_codes) == 1
    assert len(avail_codes) == 1
    assert used_codes[0].assigned_to_user_id == user.id

    # Check authoritative stock is now 1
    remaining_stock = await StockService.get_authoritative_stock(db_session, coupon)
    assert remaining_stock == 1


@pytest.mark.asyncio
async def test_insufficient_points_blocked(db_session: AsyncSession):
    """Verify that redemption fails when user has fewer points than required."""
    user, _, _ = await UserService.get_or_create_user(session=db_session, telegram_id=803, first_name="LowPoints")
    user.points = 2
    await db_session.commit()

    coupon = await CouponService.create_coupon(
        session=db_session,
        admin_id=999,
        title="Flipkart ₹500",
        brand="Flipkart",
        category=CouponCategory.SHOPPING,
        value="₹500",
        points_required=10,
        stock_type=StockType.QUANTITY,
        stock=10,
        code="FLIP500",
    )
    await db_session.commit()

    success, msg, redemption = await CouponService.redeem_coupon(
        session=db_session,
        user_id=user.id,
        coupon_id=coupon.id,
    )
    assert success is False
    assert "Insufficient points" in msg
    assert redemption is None
    assert user.points == 2
    assert coupon.stock == 10


@pytest.mark.asyncio
async def test_out_of_stock_blocked(db_session: AsyncSession):
    """Verify that redemption fails when coupon stock is 0."""
    user, _, _ = await UserService.get_or_create_user(session=db_session, telegram_id=804, first_name="EagerUser")
    user.points = 10
    await db_session.commit()

    coupon = await CouponService.create_coupon(
        session=db_session,
        admin_id=999,
        title="Zero Stock Coupon",
        brand="BrandX",
        category=CouponCategory.OTHER,
        value="₹100",
        points_required=5,
        stock_type=StockType.QUANTITY,
        stock=0,
        code="ZEROSTOCK",
    )
    await db_session.commit()

    success, msg, redemption = await CouponService.redeem_coupon(
        session=db_session,
        user_id=user.id,
        coupon_id=coupon.id,
    )
    assert success is False
    assert "out of stock" in msg.lower()
    assert redemption is None
    assert user.points == 10


@pytest.mark.asyncio
async def test_max_redemptions_per_user_enforced(db_session: AsyncSession):
    """Verify that a user cannot redeem a coupon beyond max_redemptions_per_user limit."""
    user, _, _ = await UserService.get_or_create_user(session=db_session, telegram_id=805, first_name="LimitTester")
    user.points = 20
    await db_session.commit()

    coupon = await CouponService.create_coupon(
        session=db_session,
        admin_id=999,
        title="Limit 1 Coupon",
        brand="LimitedBrand",
        category=CouponCategory.OTHER,
        value="₹50",
        points_required=5,
        stock_type=StockType.QUANTITY,
        stock=10,
        code="LIMIT1",
        max_redemptions_per_user=1,
    )
    await db_session.commit()

    # First redemption succeeds
    s1, _, r1 = await CouponService.redeem_coupon(db_session, user.id, coupon.id)
    await db_session.commit()
    assert s1 is True

    # Second redemption must be blocked
    s2, msg2, r2 = await CouponService.redeem_coupon(db_session, user.id, coupon.id)
    assert s2 is False
    assert "limit reached" in msg2.lower() or "maximum" in msg2.lower()
    assert r2 is None


@pytest.mark.asyncio
async def test_one_code_per_redemption_and_no_reuse(db_session: AsyncSession):
    """Verify that each redemption assigns exactly 1 unique code and never reuses a USED code."""
    user1, _, _ = await UserService.get_or_create_user(session=db_session, telegram_id=901, first_name="U1")
    user2, _, _ = await UserService.get_or_create_user(session=db_session, telegram_id=902, first_name="U2")
    user3, _, _ = await UserService.get_or_create_user(session=db_session, telegram_id=903, first_name="U3")

    user1.points = 10
    user2.points = 10
    user3.points = 10
    await db_session.commit()

    coupon = await CouponService.create_coupon(
        session=db_session,
        admin_id=999,
        title="Myntra ₹200 OFF",
        brand="Myntra",
        value="₹200 OFF",
        points_required=6,
        stock_type=StockType.UNIQUE_CODES,
        stock=0,
    )
    await db_session.commit()

    # Admin imports 2 unique codes
    await StockService.bulk_import_unique_codes(
        session=db_session,
        admin_id=999,
        coupon_id=coupon.id,
        raw_text="MYN-CODE-001\nMYN-CODE-002",
    )
    await db_session.commit()

    # User 1 redeems -> gets CODE-001
    s1, _, r1 = await CouponService.redeem_coupon(db_session, user1.id, coupon.id)
    await db_session.commit()
    assert s1 is True
    assert r1.coupon_code == "MYN-CODE-001"

    # User 2 redeems -> gets CODE-002 (different code)
    s2, _, r2 = await CouponService.redeem_coupon(db_session, user2.id, coupon.id)
    await db_session.commit()
    assert s2 is True
    assert r2.coupon_code == "MYN-CODE-002"
    assert r1.coupon_code != r2.coupon_code

    # User 3 tries to redeem -> out of stock, no codes available, no points deducted
    s3, msg3, r3 = await CouponService.redeem_coupon(db_session, user3.id, coupon.id)
    assert s3 is False
    assert r3 is None
    await db_session.refresh(user3)
    assert user3.points == 10

