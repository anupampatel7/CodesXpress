"""User lifecycle and points service."""

import logging
from typing import Optional, Tuple, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from models.user import User
from models.referral import Referral, ReferralStatus
from models.point_transaction import PointTransaction, TransactionType
from models.admin_action import AdminAction
from utils.security import generate_referral_code

logger = logging.getLogger(__name__)


class UserService:
    """Service handling user accounts, profile queries, and point modifications."""

    @staticmethod
    async def get_or_create_user(
        session: AsyncSession,
        telegram_id: int,
        username: Optional[str] = None,
        first_name: str = "",
        last_name: Optional[str] = None,
        referral_param: Optional[str] = None,
    ) -> Tuple[User, bool, Optional[Referral]]:
        """Retrieve existing user or register a genuine new user.

        If the user is genuinely new and arrived via a valid referral parameter,
        a PENDING Referral record is created. Existing users never create referral records.

        Returns:
            Tuple of (user, is_created, pending_referral_obj)
        """
        # Check if user already exists
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        if user is not None:
            # Update profile details if changed
            updated = False
            if username and user.username != username:
                user.username = username
                updated = True
            if first_name and user.first_name != first_name:
                user.first_name = first_name
                updated = True
            if last_name and user.last_name != last_name:
                user.last_name = last_name
                updated = True
            if updated:
                await session.flush()
            return user, False, None

        # User is brand new. Generate unique referral code.
        while True:
            code = generate_referral_code(8)
            check_stmt = select(User.id).where(User.referral_code == code)
            exists = (await session.execute(check_stmt)).scalar_one_or_none()
            if not exists:
                break

        # Process referral parameter if supplied on first interaction
        referrer_user: Optional[User] = None
        if referral_param:
            clean_param = referral_param.strip()
            if clean_param.startswith("ref_"):
                clean_param = clean_param[4:]

            # Try finding referrer by referral_code or telegram_id
            if clean_param.isdigit():
                ref_stmt = select(User).where(User.telegram_id == int(clean_param))
            else:
                ref_stmt = select(User).where(User.referral_code == clean_param)

            referrer_res = await session.execute(ref_stmt)
            referrer_user = referrer_res.scalar_one_or_none()

            # Anti-abuse: ensure referrer is not self
            if referrer_user and referrer_user.telegram_id == telegram_id:
                referrer_user = None

        new_user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            points=0,
            referred_by=referrer_user.telegram_id if referrer_user else None,
            referral_code=code,
            is_banned=False,
        )
        session.add(new_user)
        await session.flush()

        pending_referral = None
        if referrer_user:
            pending_referral = Referral(
                referrer_id=referrer_user.id,
                referred_id=new_user.id,
                status=ReferralStatus.PENDING,
                reward_given=False,
            )
            session.add(pending_referral)
            await session.flush()
            logger.info(
                f"Referral captured: Referrer #{referrer_user.telegram_id} -> Referred #{new_user.telegram_id}"
            )

        return new_user, True, pending_referral

    @staticmethod
    async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> Optional[User]:
        """Fetch user by Telegram ID."""
        stmt = select(User).where(User.telegram_id == telegram_id)
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    @staticmethod
    async def get_user_by_id(session: AsyncSession, user_id: int) -> Optional[User]:
        """Fetch user by internal DB primary key."""
        stmt = select(User).where(User.id == user_id)
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    @staticmethod
    async def get_user_points_summary(session: AsyncSession, user_id: int) -> Dict[str, int]:
        """Compute aggregated points earned, spent, and referral count for a user."""
        # Total points earned (positive transactions)
        earned_stmt = select(func.coalesce(func.sum(PointTransaction.amount), 0)).where(
            PointTransaction.user_id == user_id,
            PointTransaction.amount > 0,
        )
        total_earned = (await session.execute(earned_stmt)).scalar() or 0

        # Total points spent (negative transactions)
        spent_stmt = select(func.coalesce(func.sum(PointTransaction.amount), 0)).where(
            PointTransaction.user_id == user_id,
            PointTransaction.amount < 0,
        )
        total_spent_neg = (await session.execute(spent_stmt)).scalar() or 0
        total_spent = abs(total_spent_neg)

        # Count successful referrals
        ref_stmt = select(func.count(Referral.id)).where(
            Referral.referrer_id == user_id,
            Referral.status == ReferralStatus.SUCCESSFUL,
        )
        successful_refs = (await session.execute(ref_stmt)).scalar() or 0

        return {
            "total_earned": total_earned,
            "total_spent": total_spent,
            "successful_referrals": successful_refs,
        }

    @staticmethod
    async def adjust_user_points(
        session: AsyncSession,
        admin_id: int,
        user_id: int,
        amount: int,
        reason: str = "Admin adjustment",
    ) -> Tuple[bool, str, Optional[int]]:
        """Adjust user points with non-negative guarantee and audit logging.

        Returns:
            Tuple of (success, message, new_balance)
        """
        user = await UserService.get_user_by_id(session, user_id)
        if not user:
            return False, "User not found.", None

        new_points = user.points + amount
        if new_points < 0:
            return False, f"Cannot deduct points: current balance is {user.points} ⭐.", user.points

        # Atomic conditional update
        if amount < 0:
            stmt = (
                update(User)
                .where(User.id == user_id, User.points >= abs(amount))
                .values(points=User.points + amount)
            )
        else:
            stmt = (
                update(User)
                .where(User.id == user_id)
                .values(points=User.points + amount)
            )

        res = await session.execute(stmt)
        if res.rowcount == 0:
            return False, "Failed to update points due to concurrent change.", user.points

        # Record ledger transaction
        tx_type = TransactionType.ADMIN_ADD if amount > 0 else TransactionType.ADMIN_REMOVE
        tx = PointTransaction(
            user_id=user_id,
            amount=amount,
            type=tx_type,
            reason=reason,
            reference_id=str(admin_id),
        )
        session.add(tx)

        # Record admin audit log
        action = "ADD_POINTS" if amount > 0 else "REMOVE_POINTS"
        audit = AdminAction(
            admin_id=admin_id,
            action=action,
            target=f"User #{user.telegram_id}",
            details=f"Amount: {amount:+d}, Reason: {reason}, New balance: {new_points}",
        )
        session.add(audit)

        await session.flush()
        return True, f"Successfully adjusted points by {amount:+d} ⭐.", new_points

    @staticmethod
    async def set_user_ban_status(
        session: AsyncSession,
        admin_id: int,
        user_id: int,
        is_banned: bool,
    ) -> Tuple[bool, str]:
        """Update user banned status and log action."""
        user = await UserService.get_user_by_id(session, user_id)
        if not user:
            return False, "User not found."

        user.is_banned = is_banned
        action = "BAN_USER" if is_banned else "UNBAN_USER"
        audit = AdminAction(
            admin_id=admin_id,
            action=action,
            target=f"User #{user.telegram_id}",
            details=f"Set is_banned = {is_banned}",
        )
        session.add(audit)
        await session.flush()
        return True, f"User {'banned' if is_banned else 'unbanned'} successfully."
