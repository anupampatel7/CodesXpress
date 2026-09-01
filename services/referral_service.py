"""Referral lifecycle, verification, and points distribution service."""

import logging
from typing import Optional, Tuple, List, Dict, Any
from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from config import settings
from models.user import User
from models.referral import Referral, ReferralStatus
from models.point_transaction import PointTransaction, TransactionType

logger = logging.getLogger(__name__)


class ReferralService:
    """Service handling referral validation, points distribution, and metrics."""

    @staticmethod
    async def process_referral_completion(
        session: AsyncSession,
        user_id: int,
        bot: Optional[Bot] = None,
    ) -> Tuple[bool, Optional[User], int]:
        """Mark pending referral as SUCCESSFUL and award referral point to referrer.

        Executed atomically. Ensures points are only awarded ONCE per referral.

        Returns:
            Tuple of (reward_awarded: bool, referrer: Optional[User], points_awarded: int)
        """
        # Find pending referral record for this referred user
        stmt = (
            select(Referral)
            .where(
                Referral.referred_id == user_id,
                Referral.status == ReferralStatus.PENDING,
                Referral.reward_given == False,
            )
        )
        res = await session.execute(stmt)
        referral = res.scalar_one_or_none()

        if not referral:
            # No pending referral to reward
            return False, None, 0

        # Fetch referred user to verify device binding
        ref_by_stmt = select(User).where(User.id == user_id)
        ref_by_res = await session.execute(ref_by_stmt)
        referred_user = ref_by_res.scalar_one_or_none()

        if not referred_user:
            return False, None, 0

        from services.device_service import DeviceService
        is_device_ok = await DeviceService.is_device_verified(session, referred_user.telegram_id)
        if not is_device_ok:
            logger.info(f"Referral #{referral.id} completion held: User #{referred_user.telegram_id} pending device verification")
            return False, None, 0

        referrer_id = referral.referrer_id
        points_to_award = settings.POINTS_PER_REFERRAL

        # Atomically mark referral as successful
        referral.status = ReferralStatus.SUCCESSFUL
        referral.reward_given = True

        # Fetch and credit referrer
        ref_user_stmt = select(User).where(User.id == referrer_id)
        ref_user_res = await session.execute(ref_user_stmt)
        referrer = ref_user_res.scalar_one_or_none()

        if not referrer:
            logger.warning(f"Referrer #{referrer_id} not found when fulfilling referral #{referral.id}")
            await session.flush()
            return False, None, 0

        # Increment referrer points atomically
        update_stmt = (
            update(User)
            .where(User.id == referrer_id)
            .values(points=User.points + points_to_award)
        )
        await session.execute(update_stmt)

        # Record ledger transaction for auditability
        tx = PointTransaction(
            user_id=referrer_id,
            amount=points_to_award,
            type=TransactionType.REFERRAL_REWARD,
            reason=f"Referral reward for user ID #{user_id}",
            reference_id=str(referral.id),
        )
        session.add(tx)

        await session.flush()
        logger.info(
            f"Awarded {points_to_award} point(s) to Referrer #{referrer.telegram_id} for user #{user_id}"
        )

        # Optional real-time notification to referrer
        if bot and referrer.telegram_id:
            try:
                await bot.send_message(
                    chat_id=referrer.telegram_id,
                    text=(
                        f"🎉 <b>Referral Verified!</b>\n\n"
                        f"⭐ +{points_to_award} point added to your balance."
                    ),
                    parse_mode="HTML",
                )
            except Exception as e:
                logger.warning(f"Could not send notification to referrer {referrer.telegram_id}: {e}")

        return True, referrer, points_to_award

    @staticmethod
    async def get_user_referral_stats(session: AsyncSession, user_id: int) -> Dict[str, int]:
        """Fetch count of successful, pending, and rejected referrals for a user."""
        stmt = (
            select(
                Referral.status,
                func.count(Referral.id),
            )
            .where(Referral.referrer_id == user_id)
            .group_by(Referral.status)
        )
        res = await session.execute(stmt)
        counts = {status: 0 for status in ReferralStatus}
        for status, count in res.all():
            counts[status] = count

        return {
            "successful": counts.get(ReferralStatus.SUCCESSFUL, 0),
            "pending": counts.get(ReferralStatus.PENDING, 0),
            "rejected": counts.get(ReferralStatus.REJECTED, 0),
            "total": sum(counts.values()),
        }

    @staticmethod
    async def get_recent_referrals(
        session: AsyncSession,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Referral]:
        """Admin helper to view recent referrals across the platform."""
        from sqlalchemy.orm import selectinload
        stmt = (
            select(Referral)
            .options(selectinload(Referral.referrer), selectinload(Referral.referred_user))
            .order_by(Referral.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        res = await session.execute(stmt)
        return list(res.scalars().all())
