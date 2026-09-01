"""Final end-to-end real-world smoke test simulating full user referral, verification, redemption, and admin lifecycle."""

import pytest
from unittest.mock import AsyncMock
from aiogram.enums import ChatMemberStatus
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.user import User
from models.coupon import Coupon, StockType, CouponCategory
from models.redemption import Redemption
from models.referral import Referral, ReferralStatus
from models.point_transaction import PointTransaction
from services.user_service import UserService
from services.channel_service import ChannelService
from services.referral_service import ReferralService
from services.coupon_service import CouponService
from services.stock_service import StockService


@pytest.mark.asyncio
async def test_full_scenario_smoke_lifecycle(db_session: AsyncSession, mock_bot):
    """Simulate complete 19-step scenario:

    1. User A registers.
    2. User A receives referral link.
    3. User B opens A's referral link.
    4. B is new.
    5. B is shown all 3 required channels.
    6. B joins all 3.
    7. Verification succeeds.
    8. A receives exactly +1.
    9. B cannot trigger another reward for A.
    10. A refers another user (or accumulates 6 points).
    11. A reaches 6 points.
    12. A selects a 6-point coupon.
    13. Redemption succeeds.
    14. A has 0 points.
    15. Stock decreases by 1.
    16. Redemption appears in My Coupons.
    17. Admin can see the redemption.
    18. Admin can restock the coupon.
    19. Stock updates correctly.
    """
    # 0. Setup required channels in DB (@OfferRaider, @OfferMate, @Grabmint, @offerelite)
    for ch_name in ["@OfferRaider", "@OfferMate", "@Grabmint", "@offerelite"]:
        await ChannelService.add_channel(
            session=db_session,
            admin_id=999,
            channel_id=ch_name,
            title=ch_name.lstrip("@"),
            invite_link=f"https://t.me/{ch_name.lstrip('@')}",
            username=ch_name.lstrip("@"),
        )
    await db_session.commit()

    # Step 1: User A registers
    user_a, is_created_a, _ = await UserService.get_or_create_user(
        session=db_session,
        telegram_id=1001,
        username="user_a",
        first_name="Alice",
    )
    await db_session.commit()
    assert is_created_a is True
    assert user_a.points == 0

    # Step 2: User A receives referral link
    assert user_a.referral_code is not None
    ref_code_a = user_a.referral_code
    referral_link_a = f"https://t.me/TestBot?start=ref_{ref_code_a}"

    # Step 3 & 4: User B opens A's referral link (B is new)
    user_b, is_created_b, pending_ref_b = await UserService.get_or_create_user(
        session=db_session,
        telegram_id=1002,
        username="user_b",
        first_name="Bob",
        referral_param=f"ref_{ref_code_a}",
    )
    await db_session.commit()
    assert is_created_b is True
    assert pending_ref_b is not None
    assert pending_ref_b.status == ReferralStatus.PENDING

    from services.device_service import DeviceService
    await DeviceService.verify_and_bind_device(
        session=db_session,
        telegram_user_id=user_b.telegram_id,
        fingerprint_payload={"screen": "1080x1920", "platform": "Android"},
    )
    await db_session.commit()

    # Step 5: B is shown all 4 required channels
    req_channels = await ChannelService.get_required_channels(db_session)
    assert len(req_channels) == 4

    # Step 6 & 7: B joins all 4 and verification succeeds
    class MemberJoined:
        status = ChatMemberStatus.MEMBER

    mock_bot.get_chat_member.return_value = MemberJoined()

    all_joined, missing = await ChannelService.verify_all_required_channels(
        bot=mock_bot,
        session=db_session,
        user_telegram_id=user_b.telegram_id,
    )
    assert all_joined is True
    assert len(missing) == 0

    # Step 8: A receives exactly +1
    reward_given, referrer, pts = await ReferralService.process_referral_completion(
        session=db_session,
        user_id=user_b.id,
        bot=mock_bot,
    )
    await db_session.commit()
    assert reward_given is True
    assert pts == 1

    # Reload User A
    user_a_updated = await UserService.get_user_by_id(db_session, user_a.id)
    assert user_a_updated.points == 1

    # Step 9: B cannot trigger another reward for A
    reward_given_dup, _, _ = await ReferralService.process_referral_completion(
        session=db_session,
        user_id=user_b.id,
        bot=mock_bot,
    )
    assert reward_given_dup is False
    assert user_a_updated.points == 1

    # Step 10 & 11: A earns more points to reach 6 points
    # Let's add 5 more points to A via referrals or point adjustment
    await UserService.adjust_user_points(
        session=db_session,
        admin_id=999,
        user_id=user_a.id,
        amount=5,
        reason="Referral bonus campaign",
    )
    await db_session.commit()

    user_a_reloaded = await UserService.get_user_by_id(db_session, user_a.id)
    assert user_a_reloaded.points == 6

    # Step 12: Admin creates a 6-point coupon with stock = 20
    coupon = await CouponService.create_coupon(
        session=db_session,
        admin_id=999,
        title="₹100 Shopping Voucher",
        brand="Amazon",
        category=CouponCategory.SHOPPING,
        value="₹100",
        points_required=6,
        stock_type=StockType.QUANTITY,
        stock=20,
        code="AMZ-100-OFF",
        terms="Valid on min purchase of ₹500.",
    )
    await db_session.commit()

    # Step 13: A selects and redeems the 6-point coupon
    success, msg, redemption = await CouponService.redeem_coupon(
        session=db_session,
        user_id=user_a.id,
        coupon_id=coupon.id,
    )
    await db_session.commit()
    assert success is True
    assert redemption is not None
    assert redemption.coupon_code == "AMZ-100-OFF"
    assert redemption.points_spent == 6

    # Step 14: A has 0 points
    user_a_after = await UserService.get_user_by_id(db_session, user_a.id)
    assert user_a_after.points == 0

    # Step 15: Stock decreases by 1 (20 -> 19)
    coupon_after = await CouponService.get_coupon_by_id(db_session, coupon.id)
    assert coupon_after.stock == 19

    # Step 16: Redemption appears in My Coupons
    user_redemptions = (
        await db_session.execute(
            select(Redemption).where(Redemption.user_id == user_a.id)
        )
    ).scalars().all()
    assert len(user_redemptions) == 1
    assert user_redemptions[0].coupon_code == "AMZ-100-OFF"

    # Step 17: Admin can see the redemption
    all_redemptions = (
        await db_session.execute(select(Redemption).where(Redemption.id == redemption.id))
    ).scalars().all()
    assert len(all_redemptions) == 1

    # Step 18 & 19: Admin restocks the coupon by +100
    restock_ok, restock_msg, new_stock = await StockService.restock_quantity(
        session=db_session,
        admin_id=999,
        coupon_id=coupon.id,
        quantity_to_add=100,
    )
    await db_session.commit()
    assert restock_ok is True
    assert new_stock == 119

    coupon_final = await CouponService.get_coupon_by_id(db_session, coupon.id)
    assert coupon_final.stock == 119
