"""Tests for points balance, ledger transactions, and admin adjustments."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.user import User
from models.point_transaction import PointTransaction, TransactionType
from models.admin_action import AdminAction
from services.user_service import UserService


@pytest.mark.asyncio
async def test_admin_add_points_and_ledger(db_session: AsyncSession):
    """Verify adding points manually by admin creates ledger entry and audit log."""
    user, _, _ = await UserService.get_or_create_user(session=db_session, telegram_id=901, first_name="PointUser")
    await db_session.commit()

    success, msg, new_bal = await UserService.adjust_user_points(
        session=db_session,
        admin_id=999,
        user_id=user.id,
        amount=15,
        reason="Loyalty Bonus",
    )
    await db_session.commit()

    assert success is True
    assert new_bal == 15

    # Check user points
    await db_session.refresh(user)
    assert user.points == 15

    # Check PointTransaction ledger
    tx_stmt = select(PointTransaction).where(PointTransaction.user_id == user.id)
    tx = (await db_session.execute(tx_stmt)).scalar_one()
    assert tx.amount == 15
    assert tx.type == TransactionType.ADMIN_ADD
    assert tx.reason == "Loyalty Bonus"

    # Check AdminAction audit log
    audit_stmt = select(AdminAction).where(AdminAction.admin_id == 999)
    audit = (await db_session.execute(audit_stmt)).scalar_one()
    assert audit.action == "ADD_POINTS"
    assert "15" in audit.details


@pytest.mark.asyncio
async def test_admin_remove_points_and_prevent_negative(db_session: AsyncSession):
    """Verify removing points fails if deduction exceeds current balance."""
    user, _, _ = await UserService.get_or_create_user(session=db_session, telegram_id=902, first_name="DeductUser")
    user.points = 5
    await db_session.commit()

    # Attempt to deduct 10 points when user only has 5
    success, msg, bal = await UserService.adjust_user_points(
        session=db_session,
        admin_id=999,
        user_id=user.id,
        amount=-10,
        reason="Correction",
    )
    assert success is False
    assert "Cannot deduct points" in msg
    assert user.points == 5  # Unchanged

    # Deduct valid 3 points
    success2, msg2, bal2 = await UserService.adjust_user_points(
        session=db_session,
        admin_id=999,
        user_id=user.id,
        amount=-3,
        reason="Valid deduction",
    )
    await db_session.commit()

    assert success2 is True
    assert bal2 == 2
    await db_session.refresh(user)
    assert user.points == 2


def test_main_menu_has_balance_and_no_points_or_stats():
    """Verify that Main Menu contains '⭐ My Balance' and NO 'My Points' or 'My Stats'."""
    from keyboards.user import get_main_menu_keyboard
    kb = get_main_menu_keyboard(is_admin=False)
    button_texts = [btn.text for row in kb.inline_keyboard for btn in row]
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]

    assert "⭐ My Balance" in button_texts
    assert "menu_balance" in callbacks
    assert "⭐ My Points" not in button_texts
    assert "💰 My Points" not in button_texts
    assert "📊 My Stats" not in button_texts
    assert "menu_points" not in callbacks
    assert "menu_stats" not in callbacks


@pytest.mark.asyncio
async def test_welcome_message_singular_and_plural():
    """Verify welcome message copy with singular and plural points."""
    from utils.formatting import format_user_welcome
    from models.user import User

    # Singular case (1 Point)
    user_1 = User(id=1, telegram_id=111, points=1)
    msg_1 = format_user_welcome(user_1, "test_bot")
    assert "⭐ <b>Your Balance: 1 Point</b>" in msg_1
    assert "🎁 <b>Exclusive Coupons</b>" in msg_1
    assert "Redeem your favourite offers with Points." in msg_1
    assert "🔗 <b>Refer & Earn</b>" in msg_1
    assert "Earn <b>1 Point</b> for every successful referral." in msg_1
    assert "<i>Choose an option to continue.</i>" in msg_1

    # Plural case (5 Points)
    user_5 = User(id=2, telegram_id=222, points=5)
    msg_5 = format_user_welcome(user_5, "test_bot")
    assert "⭐ <b>Your Balance: 5 Points</b>" in msg_5

    # Zero case (0 Points)
    user_0 = User(id=3, telegram_id=333, points=0)
    msg_0 = format_user_welcome(user_0, "test_bot")
    assert "⭐ <b>Your Balance: 0 Points</b>" in msg_0


@pytest.mark.asyncio
async def test_my_balance_view_format(db_session: AsyncSession):
    """Verify My Balance output format."""
    from utils.formatting import format_balance_card
    card = format_balance_card(balance=10, referrals=5, redeemed=2)
    assert "💰 <b>Your Balance</b>" in card
    assert "⭐ Points: <b>10</b>" in card
    assert "🚀 Successful Referrals: <b>5</b>" in card
    assert "🎟️ Coupons Redeemed: <b>2</b>" in card

