"""Tests for referral registration, verification, anti-fraud, and point awards."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.user import User
from models.referral import Referral, ReferralStatus
from models.point_transaction import PointTransaction, TransactionType
from services.user_service import UserService
from services.referral_service import ReferralService
from services.fraud_service import FraudService


@pytest.mark.asyncio
async def test_user_registration_and_referral_code(db_session: AsyncSession):
    """Verify that a new user gets created with 0 points and a unique referral code."""
    user, is_created, ref = await UserService.get_or_create_user(
        session=db_session,
        telegram_id=111111,
        username="user1",
        first_name="User One",
    )
    await db_session.commit()

    assert is_created is True
    assert user.telegram_id == 111111
    assert user.points == 0
    assert len(user.referral_code) == 8
    assert ref is None


@pytest.mark.asyncio
async def test_genuine_referral_flow(db_session: AsyncSession, mock_bot):
    """Verify that a genuine referred user creates a PENDING referral and awards +1 point on verification."""
    # 1. Referrer registers
    referrer, _, _ = await UserService.get_or_create_user(
        session=db_session,
        telegram_id=222222,
        username="referrer_user",
        first_name="Referrer",
    )
    await db_session.commit()

    # 2. Friend joins via referrer's code
    friend, is_created, pending_ref = await UserService.get_or_create_user(
        session=db_session,
        telegram_id=333333,
        username="friend_user",
        first_name="Friend",
        referral_param=f"ref_{referrer.referral_code}",
    )
    await db_session.commit()

    assert is_created is True
    assert pending_ref is not None
    assert pending_ref.status == ReferralStatus.PENDING
    assert pending_ref.reward_given is False
    assert friend.referred_by == referrer.telegram_id
    assert referrer.points == 0  # Points not given yet

    from services.device_service import DeviceService
    # 3. Friend completes device verification
    await DeviceService.verify_and_bind_device(
        session=db_session,
        telegram_user_id=friend.telegram_id,
        fingerprint_payload={"screen": "1920x1080", "platform": "Win32"},
    )
    await db_session.commit()

    # 4. Friend completes channel verification
    reward_given, ref_user, pts = await ReferralService.process_referral_completion(
        session=db_session,
        user_id=friend.id,
        bot=mock_bot,
    )
    await db_session.commit()

    assert reward_given is True
    assert pts == 1

    # Reload referrer from DB
    stmt = select(User).where(User.id == referrer.id)
    ref_updated = (await db_session.execute(stmt)).scalar_one()
    assert ref_updated.points == 1

    # Verify point ledger transaction
    tx_stmt = select(PointTransaction).where(
        PointTransaction.user_id == referrer.id,
        PointTransaction.type == TransactionType.REFERRAL_REWARD,
    )
    tx = (await db_session.execute(tx_stmt)).scalar_one_or_none()
    assert tx is not None
    assert tx.amount == 1

    # 5. Re-verifying channels must NOT award duplicate points
    reward_given_2, _, _ = await ReferralService.process_referral_completion(
        session=db_session,
        user_id=friend.id,
        bot=mock_bot,
    )
    assert reward_given_2 is False
    assert ref_updated.points == 1


@pytest.mark.asyncio
async def test_self_referral_prevention(db_session: AsyncSession):
    """Verify that a user cannot refer their own account."""
    user, _, _ = await UserService.get_or_create_user(
        session=db_session,
        telegram_id=444444,
        username="self_ref_user",
        first_name="Self",
    )
    await db_session.commit()

    # Try to re-register with own referral code
    user_again, is_created, pending_ref = await UserService.get_or_create_user(
        session=db_session,
        telegram_id=444444,
        username="self_ref_user",
        first_name="Self",
        referral_param=f"ref_{user.referral_code}",
    )
    await db_session.commit()

    assert is_created is False
    assert pending_ref is None
    assert user_again.referred_by is None


@pytest.mark.asyncio
async def test_existing_user_cannot_be_referred_later(db_session: AsyncSession):
    """Verify that an existing user cannot generate a referral reward by opening another link later."""
    # User A starts bot directly
    user_a, is_created_a, _ = await UserService.get_or_create_user(
        session=db_session,
        telegram_id=555555,
        username="early_user",
        first_name="Early",
    )
    # User B registers as referrer
    user_b, _, _ = await UserService.get_or_create_user(
        session=db_session,
        telegram_id=666666,
        username="referrer_b",
        first_name="ReferrerB",
    )
    await db_session.commit()

    # User A opens User B's referral link days later
    user_a_again, is_created_again, pending_ref = await UserService.get_or_create_user(
        session=db_session,
        telegram_id=555555,
        referral_param=f"ref_{user_b.referral_code}",
    )
    await db_session.commit()

    assert is_created_again is False
    assert pending_ref is None
    assert user_a_again.referred_by is None


@pytest.mark.asyncio
async def test_single_level_referral_isolation(db_session: AsyncSession, mock_bot):
    """Verify that referral rewards are single-level only (no MLM pyramid)."""
    from services.device_service import DeviceService
    # A refers B -> B refers C
    user_a, _, _ = await UserService.get_or_create_user(session=db_session, telegram_id=701, first_name="A")
    await db_session.commit()

    user_b, _, ref_b = await UserService.get_or_create_user(
        session=db_session,
        telegram_id=702,
        first_name="B",
        referral_param=f"ref_{user_a.referral_code}",
    )
    await db_session.commit()
    await DeviceService.verify_and_bind_device(session=db_session, telegram_user_id=702, fingerprint_payload={"dev": "b"})

    user_c, _, ref_c = await UserService.get_or_create_user(
        session=db_session,
        telegram_id=703,
        first_name="C",
        referral_param=f"ref_{user_b.referral_code}",
    )
    await db_session.commit()
    await DeviceService.verify_and_bind_device(session=db_session, telegram_user_id=703, fingerprint_payload={"dev": "c"})

    # Verify B
    await ReferralService.process_referral_completion(session=db_session, user_id=user_b.id, bot=mock_bot)
    # Verify C
    await ReferralService.process_referral_completion(session=db_session, user_id=user_c.id, bot=mock_bot)
    await db_session.commit()

    # Check balances:
    # A should have exactly 1 point (from B)
    # B should have exactly 1 point (from C)
    # C should have 0 points
    stmt_a = select(User.points).where(User.id == user_a.id)
    stmt_b = select(User.points).where(User.id == user_b.id)
    stmt_c = select(User.points).where(User.id == user_c.id)

    pts_a = (await db_session.execute(stmt_a)).scalar()
    pts_b = (await db_session.execute(stmt_b)).scalar()
    pts_c = (await db_session.execute(stmt_c)).scalar()

    assert pts_a == 1
    assert pts_b == 1
    assert pts_c == 0
