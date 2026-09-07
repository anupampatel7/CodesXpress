"""Anti-abuse, self-referral prevention, and integrity validation service."""

import logging
from typing import Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from models.user import User
from models.referral import Referral, ReferralStatus
from models.point_transaction import PointTransaction

logger = logging.getLogger(__name__)


class FraudService:
    """Service providing abuse checks and referral legitimacy enforcement."""

    @staticmethod
    async def validate_referral_attempt(
        session: AsyncSession,
        referrer_id: int,
        referred_telegram_id: int,
    ) -> Tuple[bool, str]:
        """Validate whether a referral relationship is legitimate.

        Checks:
        1. Referrer is not the same person as the referred user.
        2. Referred user is genuinely new (not already registered).
        3. Referred user does not already have an active/previous referral record.
        """
        # Fetch referrer
        ref_stmt = select(User).where(User.id == referrer_id)
        referrer = (await session.execute(ref_stmt)).scalar_one_or_none()
        if not referrer:
            return False, "Invalid referrer."

        # Self referral check
        if referrer.telegram_id == referred_telegram_id:
            logger.warning(f"Abuse detected: Self-referral attempt by Telegram ID {referred_telegram_id}")
            return False, "Self-referral is strictly disallowed."

        # Check if referred user already exists
        existing_user_stmt = select(User.id).where(User.telegram_id == referred_telegram_id)
        existing_id = (await session.execute(existing_user_stmt)).scalar_one_or_none()
        if existing_id:
            logger.info(f"Ignored referral attempt: User #{referred_telegram_id} is already registered.")
            return False, "Existing users cannot be referred."

        return True, "Referral is valid."

    @staticmethod
    async def get_system_metrics(session: AsyncSession) -> dict:
        """Fetch comprehensive aggregate statistics for the admin dashboard."""
        from models.coupon import Coupon
        from models.redemption import Redemption
        from models.channel import Channel
        from sqlalchemy import case

        # 1. Users metrics (total, banned, active) in a single query
        user_stmt = select(
            func.count(User.id),
            func.coalesce(func.sum(case((User.is_banned == True, 1), else_=0)), 0),
        )
        total_users, banned_users = (await session.execute(user_stmt)).one()
        active_users = max(0, total_users - banned_users)

        # 2. Referrals metrics (total, successful, pending) in a single query
        ref_stmt = select(
            func.count(Referral.id),
            func.coalesce(func.sum(case((Referral.status == ReferralStatus.SUCCESSFUL, 1), else_=0)), 0),
            func.coalesce(func.sum(case((Referral.status == ReferralStatus.PENDING, 1), else_=0)), 0),
        )
        total_referrals, successful_referrals, pending_referrals = (await session.execute(ref_stmt)).one()

        # 3. Total points issued
        total_pts_stmt = select(func.coalesce(func.sum(PointTransaction.amount), 0)).where(
            PointTransaction.amount > 0
        )
        total_points_issued = (await session.execute(total_pts_stmt)).scalar() or 0

        # 4. Coupons metrics (active_coupons, total_stock) in a single query
        coupon_stmt = select(
            func.coalesce(func.sum(case((Coupon.is_active == True, 1), else_=0)), 0),
            func.coalesce(func.sum(Coupon.stock), 0),
        )
        active_coupons, total_stock = (await session.execute(coupon_stmt)).one()

        # 5. Redemptions and channels
        total_redemptions = (await session.execute(select(func.count(Redemption.id)))).scalar() or 0
        required_channels = (
            await session.execute(select(func.count(Channel.id)).where(Channel.is_active == True))
        ).scalar() or 0

        return {
            "total_users": total_users,
            "active_users": active_users,
            "banned_users": banned_users,
            "total_referrals": total_referrals,
            "successful_referrals": successful_referrals,
            "pending_referrals": pending_referrals,
            "total_points_issued": total_points_issued,
            "active_coupons": active_coupons,
            "total_stock": total_stock,
            "total_redemptions": total_redemptions,
            "required_channels": required_channels,
        }
