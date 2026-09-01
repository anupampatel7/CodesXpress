"""User balance, redemption history, and coupon voucher details handler."""

import logging
from html import escape
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from services.user_service import UserService
from models.redemption import Redemption
from keyboards.user import (
    get_balance_keyboard,
    get_my_coupons_keyboard,
    get_back_to_menu_keyboard,
    MyCouponDetailCallback,
)
from utils.formatting import format_balance_card, safe_edit_message

logger = logging.getLogger(__name__)

router = Router(name="profile_router")


# =========================================================================
# 1. MY BALANCE
# =========================================================================

@router.message(Command("balance"))
@router.message(Command("points"))
@router.callback_query(F.data.in_({"menu_balance", "menu_points", "menu_stats"}))
async def handle_balance(
    event: Message | CallbackQuery,
    session: AsyncSession,
) -> None:
    """Display short, clean user balance and summary."""
    from_user = event.from_user
    if not from_user:
        return

    user = await UserService.get_user_by_telegram_id(session, from_user.id)
    if not user:
        user, _, _ = await UserService.get_or_create_user(
            session=session,
            telegram_id=from_user.id,
            username=from_user.username,
            first_name=from_user.first_name or "",
            last_name=from_user.last_name,
        )

    summary = await UserService.get_user_points_summary(session, user.id)
    msg_text = format_balance_card(
        balance=user.points,
        referrals=summary.get("successful_referrals", 0),
        redeemed=summary.get("total_redemptions", 0),
    )
    kb = get_balance_keyboard()

    if isinstance(event, CallbackQuery):
        await event.answer()
    await safe_edit_message(event, msg_text, reply_markup=kb)


# =========================================================================
# 2. MY COUPONS
# =========================================================================

@router.message(Command("mycoupons"))
@router.callback_query(F.data == "menu_my_coupons")
async def handle_my_coupons(
    event: Message | CallbackQuery,
    session: AsyncSession,
) -> None:
    """Display list of coupons redeemed by the user directly."""
    from_user = event.from_user
    if not from_user:
        return

    user = await UserService.get_user_by_telegram_id(session, from_user.id)
    if not user:
        user, _, _ = await UserService.get_or_create_user(
            session=session,
            telegram_id=from_user.id,
            username=from_user.username,
            first_name=from_user.first_name or "",
            last_name=from_user.last_name,
        )

    # Fetch user redemptions with eager loaded coupon
    stmt = (
        select(Redemption)
        .options(selectinload(Redemption.coupon))
        .where(Redemption.user_id == user.id)
        .order_by(Redemption.id.desc())
        .limit(20)
    )
    res = await session.execute(stmt)
    redemptions = list(res.scalars().all())

    kb = get_back_to_menu_keyboard()

    if not redemptions:
        text = "🎟️ No redeemed coupons yet."
    else:
        text_lines = ["🎟️ <b>My Coupons</b>\n"]
        for r in redemptions:
            title = r.coupon.title if r.coupon else "Coupon"
            date_str = r.created_at.strftime("%d %b %Y, %I:%M %p")
            text_lines.append(
                f"• <b>{escape(title)}</b>\n"
                f"🎫 Code: <code>{escape(r.coupon_code)}</code>\n"
                f"📅 {date_str}\n"
            )
        text = "\n".join(text_lines)

    if isinstance(event, CallbackQuery):
        await event.answer()
    await safe_edit_message(event, text, reply_markup=kb)


@router.callback_query(MyCouponDetailCallback.filter())
async def handle_my_coupon_detail(
    callback: CallbackQuery,
    callback_data: MyCouponDetailCallback,
    session: AsyncSession,
) -> None:
    """Display individual redeemed coupon code details."""
    from_user = callback.from_user
    if not from_user:
        await callback.answer("❌ User not found.", show_alert=True)
        return

    user = await UserService.get_user_by_telegram_id(session, from_user.id)
    if not user:
        await callback.answer("❌ User not found.", show_alert=True)
        return

    stmt = (
        select(Redemption)
        .options(selectinload(Redemption.coupon))
        .where(Redemption.id == callback_data.redemption_id, Redemption.user_id == user.id)
    )
    res = await session.execute(stmt)
    redemption = res.scalar_one_or_none()

    if not redemption:
        await callback.answer("❌ Coupon not found.", show_alert=True)
        return

    await callback.answer()

    brand = redemption.coupon.brand if redemption.coupon else ""
    title = redemption.coupon.title if redemption.coupon else "Coupon"
    coupon_name = f"{brand} {title}".strip()
    date_str = redemption.created_at.strftime("%d %b %Y")

    msg = (
        f"🎁 <b>{escape(coupon_name)}</b>\n\n"
        f"⭐ {redemption.points_spent} Points\n"
        f"📅 {date_str}\n\n"
        "🔑 <b>Your Code:</b>\n"
        f"<code>{escape(redemption.coupon_code)}</code>"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎟️ My Coupons", callback_data="menu_my_coupons")],
            [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu_home")],
        ]
    )
    await safe_edit_message(callback, msg, reply_markup=kb)
