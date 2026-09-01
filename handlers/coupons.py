"""Master coupon browsing, details, confirmation, and atomic redemption handlers."""

import logging
import asyncio
from typing import Set, Tuple
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession
from services.user_service import UserService
from services.coupon_service import CouponService
from services.stock_service import StockService
from models.coupon import Coupon
from keyboards.user import (
    BrandNavCallback,
    BrandCouponsCallback,
    CouponDetailCallback,
    CouponConfirmCallback,
    CouponRedeemCallback,
    CouponNavCallback,
    get_available_coupons_keyboard,
    get_no_brands_keyboard,
    get_coupon_detail_keyboard,
    get_redeem_confirm_keyboard,
    get_insufficient_points_keyboard,
    get_back_to_menu_keyboard,
)
from utils.formatting import (
    format_coupon_detail,
    format_redeem_confirm_prompt,
    format_redemption_success,
    format_insufficient_points,
    safe_edit_message,
)

logger = logging.getLogger(__name__)

router = Router(name="coupons_router")

# Concurrency lock set to prevent simultaneous duplicate redemption clicks from the same user
_active_redemptions: Set[Tuple[int, int]] = set()
_redemption_lock = asyncio.Lock()


# =========================================================================
# 1. AVAILABLE COUPONS DIRECT LIST
# =========================================================================

@router.message(Command("coupons"))
@router.callback_query(F.data == "menu_coupons")
async def handle_coupons_menu(
    event: Message | CallbackQuery,
    session: AsyncSession,
) -> None:
    """Display available coupons dynamically based on in-stock inventory."""
    coupons, total_count, total_pages = await CouponService.get_available_coupons(session, page=1, per_page=8)

    if not coupons:
        text = "🎁 <b>No Coupons Available</b>\n\nNew offers will appear here soon. 🚀"
        kb = get_no_brands_keyboard()
    else:
        text = "🎁 <b>Available Coupons</b>\n\n✨ Choose a coupon to view details and redeem it."
        kb = get_available_coupons_keyboard(coupons=coupons, page=1, total_pages=total_pages)

    if isinstance(event, CallbackQuery):
        await event.answer()
    await safe_edit_message(event, text, reply_markup=kb)


@router.callback_query(BrandNavCallback.filter())
async def handle_brand_pagination(
    callback: CallbackQuery,
    callback_data: BrandNavCallback,
    session: AsyncSession,
) -> None:
    """Paginate through available coupons."""
    page = max(1, callback_data.page)
    coupons, total_count, total_pages = await CouponService.get_available_coupons(session, page=page, per_page=8)

    if not coupons:
        text = "🎁 <b>No Coupons Available</b>\n\nNew offers will appear here soon. 🚀"
        kb = get_no_brands_keyboard()
    else:
        text = "🎁 <b>Available Coupons</b>\n\n✨ Choose a coupon to view details and redeem it."
        kb = get_available_coupons_keyboard(coupons=coupons, page=page, total_pages=total_pages)

    await callback.answer()
    await safe_edit_message(callback, text, reply_markup=kb)


# =========================================================================
# 2. COUPON DETAIL VIEW
# =========================================================================

@router.callback_query(CouponDetailCallback.filter())
async def handle_coupon_detail(
    callback: CallbackQuery,
    callback_data: CouponDetailCallback,
    session: AsyncSession,
) -> None:
    """Display full details of a specific coupon."""
    from_user = callback.from_user
    user = await UserService.get_user_by_telegram_id(session, from_user.id)
    if not user:
        user, _, _ = await UserService.get_or_create_user(
            session=session,
            telegram_id=from_user.id,
            username=from_user.username,
            first_name=from_user.first_name or "",
            last_name=from_user.last_name,
        )

    coupon = await CouponService.get_coupon_by_id(session, callback_data.coupon_id)
    if not coupon or not coupon.is_active:
        await callback.answer("⚠️ This coupon is currently unavailable.", show_alert=True)
        return

    available_stock = await StockService.get_authoritative_stock(session, coupon)
    if available_stock <= 0 or coupon.is_expired:
        msg_text = (
            "🔴 <b>Out of Stock</b>\n\n"
            "This coupon is currently unavailable."
        )
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Back", callback_data="menu_coupons")]
            ]
        )
        await callback.answer()
        await safe_edit_message(callback, msg_text, reply_markup=kb)
        return

    msg_text = format_coupon_detail(
        coupon=coupon,
        available_stock=available_stock,
        user_points=user.points,
    )
    brand_name = callback_data.brand or coupon.brand
    kb = get_coupon_detail_keyboard(
        coupon_id=coupon.id,
        brand=brand_name,
        page=callback_data.page,
        can_redeem=True,
    )

    await callback.answer()
    await safe_edit_message(callback, msg_text, reply_markup=kb)


# =========================================================================
# 3. PRE-REDEMPTION CONFIRMATION PROMPT
# =========================================================================

@router.callback_query(CouponConfirmCallback.filter())
async def handle_coupon_confirm(
    callback: CallbackQuery,
    callback_data: CouponConfirmCallback,
    session: AsyncSession,
) -> None:
    """Show confirmation prompt before executing redemption."""
    from_user = callback.from_user
    user = await UserService.get_user_by_telegram_id(session, from_user.id)
    if not user:
        await callback.answer("❌ User not found.", show_alert=True)
        return

    coupon = await CouponService.get_coupon_by_id(session, callback_data.coupon_id)
    if not coupon or not coupon.is_active:
        await callback.answer("⚠️ This coupon is currently unavailable.", show_alert=True)
        return

    if user.points < coupon.points_required:
        await callback.answer()
        insufficient_text = format_insufficient_points(coupon.points_required, user.points)
        kb = get_insufficient_points_keyboard()
        await safe_edit_message(callback, insufficient_text, reply_markup=kb)
        return

    confirm_text = format_redeem_confirm_prompt(coupon, user.points)
    brand_name = callback_data.brand or coupon.brand
    kb = get_redeem_confirm_keyboard(
        coupon_id=coupon.id,
        brand=brand_name,
        page=callback_data.page,
    )

    await callback.answer()
    await safe_edit_message(callback, confirm_text, reply_markup=kb)


# =========================================================================
# 4. ATOMIC REDEMPTION EXECUTION
# =========================================================================

@router.callback_query(CouponRedeemCallback.filter())
async def handle_coupon_redemption(
    callback: CallbackQuery,
    callback_data: CouponRedeemCallback,
    session: AsyncSession,
) -> None:
    """Execute atomic coupon redemption with duplicate-click protection."""
    from_user = callback.from_user
    user = await UserService.get_user_by_telegram_id(session, from_user.id)
    if not user:
        await callback.answer("❌ User not found.", show_alert=True)
        return

    coupon_id = callback_data.coupon_id
    dedup_key = (user.id, coupon_id)

    # In-memory lock to prevent concurrent double-click race condition
    async with _redemption_lock:
        if dedup_key in _active_redemptions:
            await callback.answer("⏳ Processing...", show_alert=False)
            return
        _active_redemptions.add(dedup_key)

    try:
        coupon = await CouponService.get_coupon_by_id(session, coupon_id)
        if not coupon:
            await callback.answer("❌ Coupon not found.", show_alert=True)
            return

        if user.points < coupon.points_required:
            await callback.answer()
            insufficient_text = format_insufficient_points(coupon.points_required, user.points)
            kb = get_insufficient_points_keyboard()
            await safe_edit_message(callback, insufficient_text, reply_markup=kb)
            return

        # Perform atomic redemption
        try:
            success, message, redemption = await CouponService.redeem_coupon(
                session=session,
                user_id=user.id,
                coupon_id=coupon.id,
            )
        except Exception as e:
            logger.error(f"Redemption error: {e}", exc_info=True)
            await callback.answer("❌ Something went wrong. Please try again.", show_alert=True)
            return

        if not success or not redemption:
            error_display = "❌ Currently out of stock." if "stock" in (message or "").lower() else f"❌ {message}"
            await callback.answer(error_display, show_alert=True)
            return

        await callback.answer("✅ Redeemed successfully.", show_alert=False)

        # Refresh user points
        await session.refresh(user)

        coupon_full_name = f"{coupon.brand} {coupon.title}".strip()
        success_text = format_redemption_success(
            coupon_title=coupon_full_name,
            code=redemption.coupon_code,
            points_used=redemption.points_spent,
            remaining_points=user.points,
            expiry_date=coupon.expiry_date,
            terms=coupon.terms,
        )
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🎟️ My Coupons", callback_data="menu_my_coupons")],
                [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu_home")],
            ]
        )
        await safe_edit_message(callback, success_text, reply_markup=kb)

    finally:
        async with _redemption_lock:
            _active_redemptions.discard(dedup_key)


# Legacy handlers for backwards compatibility
@router.callback_query(CouponNavCallback.filter())
@router.callback_query(BrandCouponsCallback.filter())
async def handle_legacy_coupons_list(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    """Redirect legacy coupon category calls to available coupon menu."""
    await handle_coupons_menu(callback, session)
