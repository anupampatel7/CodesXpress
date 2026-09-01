"""Admin control panel router for coupons, stock, bulk codes, channels, users, and backups."""

import logging
from typing import Optional
from html import escape
from aiogram import Router, F, Bot
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    FSInputFile,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from config import settings
from models.coupon import Coupon, CouponCategory, StockType
from models.coupon_code import CouponCode, CodeStatus
from models.channel import Channel
from models.user import User
from models.referral import Referral
from models.redemption import Redemption
from models.admin_action import AdminAction
from services.user_service import UserService
from services.coupon_service import CouponService
from services.stock_service import StockService
from services.channel_service import ChannelService
from services.fraud_service import FraudService
from keyboards.admin import (
    AdminCouponCallback,
    AdminChannelCallback,
    AdminUserCallback,
    AdminFraudCallback,
    AdminNavCallback,
    get_admin_main_keyboard,
    get_admin_coupons_keyboard,
    get_admin_coupon_detail_keyboard,
    get_admin_coupon_codes_keyboard,
    get_admin_channels_keyboard,
    get_admin_channel_detail_keyboard,
    get_admin_user_detail_keyboard,
    get_admin_fraud_detail_keyboard,
    get_admin_cancel_keyboard,
)
from utils.formatting import format_admin_dashboard
from utils.validators import (
    validate_positive_int,
    validate_channel_id,
    validate_date,
    sanitize_coupon_code,
    parse_bulk_codes,
)
from sqlalchemy.orm import selectinload
from utils.backup import create_sqlite_backup

logger = logging.getLogger(__name__)

router = Router(name="admin_router")


# FSM States for Admin Flows
class AddCouponState(StatesGroup):
    name = State()
    description = State()
    points = State()
    codes = State()


class EditCouponState(StatesGroup):
    coupon_id = State()
    field = State()
    new_value = State()


class RestockState(StatesGroup):
    coupon_id = State()
    quantity = State()


class BulkAddCodesState(StatesGroup):
    coupon_id = State()
    raw_codes = State()


class AddChannelState(StatesGroup):
    channel_id = State()
    title = State()
    invite_link = State()
    username = State()


class UserSearchState(StatesGroup):
    query = State()


class PointAdjustState(StatesGroup):
    user_id = State()
    is_addition = State()
    amount = State()


# Admin Authorization Guard Helper
async def require_admin(event: Message | CallbackQuery, is_admin: Optional[bool] = None) -> bool:
    """Verify administrator privileges strictly on the server side."""
    user = event.from_user
    user_id = user.id if user else None

    # Check is_admin flag or verify directly against configured admin IDs
    user_is_admin = False
    if is_admin is True:
        user_is_admin = True
    elif user_id is not None and settings.is_admin(user_id):
        user_is_admin = True

    if not user_is_admin:
        if isinstance(event, Message):
            await event.answer("❌ <b>Unauthorized!</b> You do not have admin permissions.", parse_mode="HTML")
        else:
            await event.answer("❌ Unauthorized access.", show_alert=True)
        return False
    return True


@router.message(Command("admin"))
@router.callback_query(F.data == "admin_dashboard")
async def handle_admin_dashboard(
    event: Message | CallbackQuery,
    session: AsyncSession,
    is_admin: bool,
    state: FSMContext,
) -> None:
    """Show admin panel dashboard with platform statistics."""
    if not await require_admin(event, is_admin):
        return
    await state.clear()

    metrics = await FraudService.get_system_metrics(session)
    dash_text = format_admin_dashboard(metrics)
    kb = get_admin_main_keyboard()

    if isinstance(event, Message):
        await event.answer(dash_text, reply_markup=kb, parse_mode="HTML")
    else:
        try:
            await event.message.edit_text(dash_text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await event.message.answer(dash_text, reply_markup=kb, parse_mode="HTML")
        await event.answer()


@router.callback_query(F.data == "admin_cancel_fsm")
async def handle_cancel_fsm(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    is_admin: bool,
) -> None:
    """Cancel current multi-step admin wizard."""
    await state.clear()
    await callback.answer("Operation cancelled.")
    metrics = await FraudService.get_system_metrics(session)
    dash_text = "❌ <b>Operation Cancelled.</b>\n\n" + format_admin_dashboard(metrics)
    kb = get_admin_main_keyboard()
    try:
        await callback.message.edit_text(dash_text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(dash_text, reply_markup=kb, parse_mode="HTML")


# =========================================================================
# COUPON MANAGEMENT
# =========================================================================

@router.callback_query(AdminNavCallback.filter(F.section == "coupons"))
async def handle_admin_coupons_list(
    callback: CallbackQuery,
    callback_data: AdminNavCallback,
    session: AsyncSession,
    is_admin: bool,
) -> None:
    """List all coupons for admin."""
    if not await require_admin(callback, is_admin):
        return
    page = max(1, callback_data.page)
    coupons, total, total_pages = await CouponService.get_all_coupons_admin(session, page=page, per_page=8)

    text = f"🎁 <b>Manage Coupons (Total: {total}, Page {page}/{total_pages})</b>\n\nSelect a coupon to edit, restock, or toggle status:"
    kb = get_admin_coupons_keyboard(coupons, page, total_pages)

    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(AdminCouponCallback.filter(F.action == "view"))
async def handle_admin_coupon_view(
    callback: CallbackQuery,
    callback_data: AdminCouponCallback,
    session: AsyncSession,
    is_admin: bool,
) -> None:
    """View detailed information of a coupon in admin panel."""
    if not await require_admin(callback, is_admin):
        return
    coupon = await CouponService.get_coupon_by_id(session, callback_data.coupon_id)
    if not coupon:
        await callback.answer("Coupon not found.", show_alert=True)
        return

    available_stock = await StockService.get_authoritative_stock(session, coupon)
    status_text = "🟢 Active" if coupon.is_active else "🔴 Inactive"
    desc_text = coupon.description.strip() if coupon.description else "<i>No description</i>"

    text = (
        f"🎟 <b>{escape(coupon.title)}</b>\n\n"
        f"📝 {escape(desc_text)}\n\n"
        f"⭐ <b>Points Required:</b> {coupon.points_required}\n"
        f"📦 <b>Available Codes:</b> {available_stock}\n"
        f"{status_text}"
    )
    kb = get_admin_coupon_detail_keyboard(coupon, page=callback_data.page)
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(AdminCouponCallback.filter(F.action == "toggle"))
async def handle_admin_coupon_toggle(
    callback: CallbackQuery,
    callback_data: AdminCouponCallback,
    session: AsyncSession,
    is_admin: bool,
) -> None:
    """Toggle coupon active status."""
    if not await require_admin(callback, is_admin):
        return
    success, msg = await CouponService.toggle_coupon_status(
        session=session,
        admin_id=callback.from_user.id,
        coupon_id=callback_data.coupon_id,
    )
    await session.commit()
    await callback.answer(msg, show_alert=True)

    # Refresh view
    coupon = await CouponService.get_coupon_by_id(session, callback_data.coupon_id)
    if coupon:
        available_stock = await StockService.get_authoritative_stock(session, coupon)
        status_text = "🟢 Active" if coupon.is_active else "🔴 Inactive"
        desc_text = coupon.description.strip() if coupon.description else "<i>No description</i>"
        text = (
            f"🎟 <b>{escape(coupon.title)}</b>\n\n"
            f"📝 {escape(desc_text)}\n\n"
            f"⭐ <b>Points Required:</b> {coupon.points_required}\n"
            f"📦 <b>Available Codes:</b> {available_stock}\n"
            f"{status_text}"
        )
        kb = get_admin_coupon_detail_keyboard(coupon, page=callback_data.page)
        try:
            await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(AdminCouponCallback.filter(F.action == "delete"))
async def handle_admin_coupon_delete(
    callback: CallbackQuery,
    callback_data: AdminCouponCallback,
    session: AsyncSession,
    is_admin: bool,
) -> None:
    """Delete a coupon."""
    if not await require_admin(callback, is_admin):
        return
    success, msg = await CouponService.delete_coupon(
        session=session,
        admin_id=callback.from_user.id,
        coupon_id=callback_data.coupon_id,
    )
    await session.commit()
    await callback.answer(msg, show_alert=True)
    # Return to coupons list
    coupons, total, total_pages = await CouponService.get_all_coupons_admin(session, page=1)
    kb = get_admin_coupons_keyboard(coupons, 1, total_pages)
    await callback.message.edit_text("Coupon deleted.", reply_markup=kb)


@router.callback_query(AdminCouponCallback.filter(F.action == "view_codes"))
async def handle_admin_coupon_view_codes(
    callback: CallbackQuery,
    callback_data: AdminCouponCallback,
    session: AsyncSession,
    is_admin: bool,
) -> None:
    """View unique codes pool status and code entries."""
    if not await require_admin(callback, is_admin):
        return
    coupon = await CouponService.get_coupon_by_id(session, callback_data.coupon_id)
    if not coupon:
        await callback.answer("Coupon not found.", show_alert=True)
        return

    codes, breakdown = await StockService.get_coupon_codes(session, coupon.id, limit=25)
    text = (
        f"🎟️ <b>Manage Codes: {escape(coupon.title)}</b>\n\n"
        f"🟢 Available: <b>{breakdown.get('AVAILABLE', 0)}</b> | "
        f"🔴 Used: <b>{breakdown.get('USED', 0)}</b>\n\n"
        f"<b>Recent Codes:</b>\n"
    )
    if not codes:
        text += "<i>No codes imported yet. Click 'Add Codes' to restock.</i>\n"
    else:
        for c in codes:
            status_tag = "🟢 Available" if c.status == CodeStatus.AVAILABLE else f"🔴 Used (User #{c.assigned_to_user_id})"
            text += f"• <code>{escape(c.code)}</code> — {status_tag}\n"

    kb = get_admin_coupon_codes_keyboard(coupon.id, page=callback_data.page)
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(AdminCouponCallback.filter(F.action == "clear_unused_codes"))
async def handle_admin_coupon_clear_unused_codes(
    callback: CallbackQuery,
    callback_data: AdminCouponCallback,
    session: AsyncSession,
    is_admin: bool,
) -> None:
    """Remove all unused (AVAILABLE) coupon codes for a coupon."""
    if not await require_admin(callback, is_admin):
        return
    success, msg, removed_count = await StockService.remove_unused_codes(
        session=session,
        admin_id=callback.from_user.id,
        coupon_id=callback_data.coupon_id,
    )
    await session.commit()
    await callback.answer(msg, show_alert=True)

    # Refresh view_codes screen
    coupon = await CouponService.get_coupon_by_id(session, callback_data.coupon_id)
    if coupon:
        codes, breakdown = await StockService.get_coupon_codes(session, coupon.id, limit=25)
        text = (
            f"🎟️ <b>Manage Codes: {escape(coupon.title)}</b>\n\n"
            f"🟢 Available: <b>{breakdown.get('AVAILABLE', 0)}</b> | "
            f"🔴 Used: <b>{breakdown.get('USED', 0)}</b>\n\n"
            f"<b>Recent Codes:</b>\n"
        )
        if not codes:
            text += "<i>No codes available. Click 'Add Codes' to restock.</i>\n"
        else:
            for c in codes:
                status_tag = "🟢 Available" if c.status == CodeStatus.AVAILABLE else f"🔴 Used (User #{c.assigned_to_user_id})"
                text += f"• <code>{escape(c.code)}</code> — {status_tag}\n"

        kb = get_admin_coupon_codes_keyboard(coupon.id, page=callback_data.page)
        try:
            await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(AdminCouponCallback.filter(F.action.in_({"edit_name", "edit_desc", "edit_points", "edit"})))
async def handle_admin_coupon_edit_action(
    callback: CallbackQuery,
    callback_data: AdminCouponCallback,
    session: AsyncSession,
    state: FSMContext,
    is_admin: bool,
) -> None:
    """Prompt admin for specific coupon field edit."""
    if not await require_admin(callback, is_admin):
        return
    coupon = await CouponService.get_coupon_by_id(session, callback_data.coupon_id)
    if not coupon:
        await callback.answer("Coupon not found.", show_alert=True)
        return

    action = callback_data.action
    if action == "edit_name":
        field = "title"
    elif action == "edit_desc":
        field = "description"
    elif action == "edit_points":
        field = "points"
    else:
        field = "title"

    await state.set_state(EditCouponState.new_value)
    await state.update_data(coupon_id=coupon.id, field=field, page=callback_data.page)

    prompt_map = {
        "title": f"✏️ <b>Edit Coupon Name:</b>\nCurrent: <b>{escape(coupon.title)}</b>\n\nEnter new Coupon Name:",
        "description": f"📝 <b>Edit Description:</b>\nCurrent:\n{escape(coupon.description or 'None')}\n\nEnter new Coupon Description:",
        "points": f"⭐ <b>Edit Points:</b>\nCurrent: <b>{coupon.points_required} Points</b>\n\nEnter new Points Required (positive integer):",
    }
    prompt = prompt_map.get(field, "Enter new value:")
    kb = get_admin_cancel_keyboard()
    try:
        await callback.message.edit_text(prompt, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(prompt, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.message(EditCouponState.new_value)
async def handle_admin_coupon_edit_value_submit(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    is_admin: bool,
) -> None:
    """Submit updated value for coupon."""
    if not await require_admin(message, is_admin):
        return
    data = await state.get_data()
    coupon_id = data.get("coupon_id")
    field = data.get("field")
    page = data.get("page", 1)
    await state.clear()

    val_text = message.text.strip() if message.text else ""
    update_kwargs = {}

    if field in ("title", "name"):
        if not val_text:
            await message.answer("Name cannot be empty. Edit cancelled.", reply_markup=get_admin_main_keyboard())
            return
        update_kwargs["title"] = val_text
        update_kwargs["brand"] = val_text.split()[0] if val_text.split() else "Brand"
    elif field == "description":
        update_kwargs["description"] = val_text
        update_kwargs["terms"] = val_text
    elif field == "points":
        pts = validate_positive_int(val_text)
        if pts is None:
            await message.answer("Points must be a positive number. Edit cancelled.", reply_markup=get_admin_main_keyboard())
            return
        update_kwargs["points_required"] = pts

    success, msg, coupon = await CouponService.update_coupon(
        session=session,
        admin_id=message.from_user.id,
        coupon_id=coupon_id,
        **update_kwargs,
    )
    await session.commit()

    if success and coupon:
        available_stock = await StockService.get_authoritative_stock(session, coupon)
        status_text = "🟢 Active" if coupon.is_active else "🔴 Inactive"
        desc_text = coupon.description.strip() if coupon.description else "<i>No description</i>"
        text = (
            f"✅ <b>Coupon Updated</b>\n\n"
            f"🎟 <b>{escape(coupon.title)}</b>\n\n"
            f"📝 {escape(desc_text)}\n\n"
            f"⭐ <b>Points Required:</b> {coupon.points_required}\n"
            f"📦 <b>Available Codes:</b> {available_stock}\n"
            f"{status_text}"
        )
        kb = get_admin_coupon_detail_keyboard(coupon, page=page)
        await message.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        await message.answer(f"❌ {msg}", reply_markup=get_admin_main_keyboard())


# =========================================================================
# RESTOCK FLOW (Quantity & Unique Codes)
# =========================================================================

@router.callback_query(AdminCouponCallback.filter(F.action == "restock"))
async def handle_restock_start(
    callback: CallbackQuery,
    callback_data: AdminCouponCallback,
    session: AsyncSession,
    state: FSMContext,
    is_admin: bool,
) -> None:
    """Initiate restock flow for a coupon."""
    if not await require_admin(callback, is_admin):
        return
    coupon = await CouponService.get_coupon_by_id(session, callback_data.coupon_id)
    if not coupon:
        await callback.answer("Coupon not found.", show_alert=True)
        return

    if coupon.stock_type == StockType.UNIQUE_CODES:
        await state.set_state(BulkAddCodesState.raw_codes)
        await state.update_data(coupon_id=coupon.id)
        text = (
            f"🔢 <b>Bulk Add Unique Codes for:</b> {coupon.title}\n\n"
            f"Kripya sabhi coupon codes ko chat me paste karein (<b>Har line par 1 code</b>):\n\n"
            f"Example:\n<code>CODE12345\nCODE67890\nCODE99999</code>"
        )
    else:
        await state.set_state(RestockState.quantity)
        await state.update_data(coupon_id=coupon.id)
        text = (
            f"📦 <b>Restock Coupon:</b> {coupon.title}\n\n"
            f"Current Stock: <code>{coupon.stock}</code>\n\n"
            f"Aap kitna stock add karna chahte hain? Positive number type karein (e.g. <code>50</code>):"
        )

    kb = get_admin_cancel_keyboard()
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.message(RestockState.quantity)
async def handle_restock_quantity_submit(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    is_admin: bool,
) -> None:
    """Process numerical restock quantity submission."""
    if not await require_admin(message, is_admin):
        return
    data = await state.get_data()
    coupon_id = data.get("coupon_id")
    await state.clear()

    qty = validate_positive_int(message.text or "")
    if not qty:
        await message.answer(
            "❌ Invalid number! Restock quantity must be a positive integer > 0.",
            reply_markup=get_admin_main_keyboard(),
        )
        return

    success, msg, new_stock = await StockService.restock_quantity(
        session=session,
        admin_id=message.from_user.id,
        coupon_id=coupon_id,
        quantity_to_add=qty,
    )

    if success:
        await message.answer(
            f"✅ <b>Restock Successful!</b>\n\n{msg}\nNew Stock: <b>{new_stock}</b>",
            reply_markup=get_admin_main_keyboard(),
            parse_mode="HTML",
        )
    else:
        await message.answer(f"❌ {msg}", reply_markup=get_admin_main_keyboard())


@router.callback_query(AdminCouponCallback.filter(F.action == "add_codes"))
async def handle_bulk_codes_prompt(
    callback: CallbackQuery,
    callback_data: AdminCouponCallback,
    state: FSMContext,
    is_admin: bool,
) -> None:
    """Prompt admin to paste bulk codes."""
    if not await require_admin(callback, is_admin):
        return
    await state.set_state(BulkAddCodesState.raw_codes)
    await state.update_data(coupon_id=callback_data.coupon_id)

    text = (
        "📥 <b>Send coupon codes</b>\n\n"
        "Paste one code per line.\n\n"
        "Example:\n"
        "<code>ABC123\n"
        "XYZ456\n"
        "MNTR789</code>"
    )
    kb = get_admin_cancel_keyboard()
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.message(BulkAddCodesState.raw_codes)
async def handle_bulk_codes_submit(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    is_admin: bool,
) -> None:
    """Process multiline bulk codes import."""
    if not await require_admin(message, is_admin):
        return
    data = await state.get_data()
    coupon_id = data.get("coupon_id")
    await state.clear()

    raw_text = message.text or ""
    success, report, stats = await StockService.bulk_import_unique_codes(
        session=session,
        admin_id=message.from_user.id,
        coupon_id=coupon_id,
        raw_text=raw_text,
    )

    if success:
        result_text = (
            f"✅ <b>Codes added: {stats['imported']}</b>\n"
            f"📦 <b>Available: {stats['total_available']}</b>"
        )
    else:
        result_text = f"❌ {report}"

    await message.answer(
        result_text,
        reply_markup=get_admin_main_keyboard(),
        parse_mode="HTML",
    )


# =========================================================================
# ADD NEW COUPON WIZARD (EXACT 4-STEP FLOW: NAME -> DESC -> POINTS -> CODES)
# =========================================================================

@router.callback_query(F.data == "admin_add_coupon")
async def handle_add_coupon_start(
    callback: CallbackQuery,
    state: FSMContext,
    is_admin: bool,
) -> None:
    """Start 4-step Add Coupon wizard."""
    if not await require_admin(callback, is_admin):
        return
    await state.set_state(AddCouponState.name)
    text = (
        "🎟 <b>Coupon Name</b>\n\n"
        "Enter the coupon name (e.g. <code>BIGBASKET ₹60 OFF</code>):"
    )
    kb = get_admin_cancel_keyboard()
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.message(AddCouponState.name)
async def handle_add_coupon_name(message: Message, state: FSMContext) -> None:
    """Handle Step 1: Coupon Name."""
    name = (message.text or "").strip()
    if not name:
        await message.answer("Please enter a valid coupon name:")
        return
    await state.update_data(name=name)
    await state.set_state(AddCouponState.description)
    text = (
        "📝 <b>Coupon Description</b>\n\n"
        "Enter the coupon description (e.g. <code>₹60 OFF on minimum ₹199 order.\nValid for new users.</code>):"
    )
    await message.answer(text, reply_markup=get_admin_cancel_keyboard(), parse_mode="HTML")


@router.message(AddCouponState.description)
async def handle_add_coupon_description(message: Message, state: FSMContext) -> None:
    """Handle Step 2: Coupon Description."""
    desc = (message.text or "").strip()
    if not desc:
        await message.answer("Please enter a valid coupon description:")
        return
    await state.update_data(description=desc)
    await state.set_state(AddCouponState.points)
    text = (
        "⭐ <b>Points Required</b>\n\n"
        "Enter the points required to redeem (e.g. <code>6</code>):"
    )
    await message.answer(text, reply_markup=get_admin_cancel_keyboard(), parse_mode="HTML")


@router.message(AddCouponState.points)
async def handle_add_coupon_points(message: Message, state: FSMContext) -> None:
    """Handle Step 3: Points Required."""
    pts = validate_positive_int(message.text or "")
    if pts is None:
        await message.answer("Points must be a positive number (e.g. 6). Enter again:")
        return
    await state.update_data(points=pts)
    await state.set_state(AddCouponState.codes)
    text = (
        "🎫 <b>Coupon Code(s)</b>\n\n"
        "Enter one or multiple coupon codes (one per line):\n\n"
        "Example:\n"
        "<code>CODE001\nCODE002\nCODE003\nCODE004</code>"
    )
    await message.answer(text, reply_markup=get_admin_cancel_keyboard(), parse_mode="HTML")


@router.message(AddCouponState.codes)
async def handle_add_coupon_codes(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    is_admin: bool,
) -> None:
    """Handle Step 4: Coupon Codes & immediately create coupon."""
    user_id = message.from_user.id if message.from_user else 0
    logger.info(f"[ADD_COUPON] code_state_received from user={user_id}")

    if not await require_admin(message, is_admin):
        logger.warning(f"[ADD_COUPON] Unauthorized access attempt by user={user_id}")
        return

    raw_text = message.text or ""
    parsed_codes, total_raw = parse_bulk_codes(raw_text)
    logger.info(f"[ADD_COUPON] codes_parsed={len(parsed_codes)} (total_raw={total_raw})")

    if not parsed_codes:
        await message.answer("Please enter at least one valid coupon code (one per line):")
        return

    data = await state.get_data()
    name = data.get("name", "Coupon")
    desc = data.get("description", "")
    pts = data.get("points", 6)
    brand = name.split()[0] if name.split() else "Brand"

    try:
        # Create coupon in database
        coupon = await CouponService.create_coupon(
            session=session,
            admin_id=user_id,
            title=name,
            brand=brand,
            category=CouponCategory.OTHER,
            value="",
            points_required=pts,
            stock_type=StockType.UNIQUE_CODES,
            stock=0,
            code=None,
            description=desc,
            terms=desc,
        )
        await session.flush()
        logger.info(f"[ADD_COUPON] coupon_created={coupon.id}")

        # Import unique codes into database
        success, report, stats = await StockService.bulk_import_unique_codes(
            session=session,
            admin_id=user_id,
            coupon_id=coupon.id,
            raw_text=raw_text,
        )
        logger.info(f"[ADD_COUPON] codes_inserted={stats.get('imported', 0)}")

        await session.commit()
        logger.info("[ADD_COUPON] transaction_committed")

        await state.clear()
        logger.info("[ADD_COUPON] fsm_cleared")

        response_text = (
            "✅ <b>Coupon Added</b>\n\n"
            f"🎟 <b>{escape(coupon.title)}</b>\n"
            f"⭐ <b>{coupon.points_required} Points</b>\n"
            f"📦 <b>{stats['imported']} codes added</b>"
        )
        await message.answer(
            response_text,
            reply_markup=get_admin_main_keyboard(),
            parse_mode="HTML",
        )
        logger.info("[ADD_COUPON] success_response_sent")
    except Exception as e:
        logger.error(f"[ADD_COUPON] Error creating coupon with codes: {e}", exc_info=True)
        await session.rollback()
        await state.clear()
        await message.answer(
            f"❌ <b>Error creating coupon:</b> {escape(str(e))}",
            reply_markup=get_admin_main_keyboard(),
            parse_mode="HTML",
        )


# =========================================================================
# REQUIRED CHANNELS MANAGEMENT
# =========================================================================

@router.callback_query(F.data == "admin_channels_list")
async def handle_admin_channels(
    callback: CallbackQuery,
    session: AsyncSession,
    is_admin: bool,
) -> None:
    """List all required channels in admin panel."""
    if not await require_admin(callback, is_admin):
        return
    channels = await ChannelService.get_all_channels(session)
    text = (
        f"📢 <b>Manage Required Channels (Total: {len(channels)})</b>\n\n"
        f"User ko referral reward aur features unlock karne ke liye in channels ko join karna padta hai:\n"
    )
    kb = get_admin_channels_keyboard(channels)
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(AdminChannelCallback.filter(F.action == "view"))
async def handle_admin_channel_view(
    callback: CallbackQuery,
    callback_data: AdminChannelCallback,
    session: AsyncSession,
    is_admin: bool,
) -> None:
    """View details of a specific channel."""
    if not await require_admin(callback, is_admin):
        return
    channel = await ChannelService.get_channel_by_id(session, callback_data.channel_id)
    if not channel:
        await callback.answer("Channel not found.", show_alert=True)
        return

    status_str = "🟢 Active (Required)" if channel.is_active else "🔴 Disabled"
    text = (
        f"📢 <b>Channel Details</b>\n\n"
        f"<b>Title:</b> {channel.title}\n"
        f"<b>Channel ID:</b> <code>{channel.channel_id}</code>\n"
        f"<b>Username:</b> @{channel.username or 'N/A'}\n"
        f"<b>Invite Link:</b> {channel.invite_link}\n"
        f"<b>Status:</b> {status_str}\n"
    )
    kb = get_admin_channel_detail_keyboard(channel)
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(AdminChannelCallback.filter(F.action == "test"))
async def handle_admin_channel_test(
    callback: CallbackQuery,
    callback_data: AdminChannelCallback,
    session: AsyncSession,
    is_admin: bool,
    bot: Bot,
) -> None:
    """Test bot access and admin permissions in this channel."""
    if not await require_admin(callback, is_admin):
        return
    channel = await ChannelService.get_channel_by_id(session, callback_data.channel_id)
    if not channel:
        await callback.answer("Channel not found.", show_alert=True)
        return

    is_valid, msg = await ChannelService.diagnose_channel_setup(bot, channel)
    kb = get_admin_channel_detail_keyboard(channel)
    try:
        await callback.message.edit_text(
            f"📢 <b>Channel Permissions Test</b>\n\n{msg}",
            reply_markup=kb,
            parse_mode="HTML",
        )
    except Exception:
        await callback.message.answer(
            f"📢 <b>Channel Permissions Test</b>\n\n{msg}",
            reply_markup=kb,
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(AdminChannelCallback.filter(F.action == "toggle"))
async def handle_admin_channel_toggle(
    callback: CallbackQuery,
    callback_data: AdminChannelCallback,
    session: AsyncSession,
    is_admin: bool,
) -> None:
    """Toggle channel status."""
    if not await require_admin(callback, is_admin):
        return
    success, msg = await ChannelService.toggle_channel_status(
        session=session,
        admin_id=callback.from_user.id,
        channel_pk=callback_data.channel_id,
    )
    await callback.answer(msg, show_alert=True)
    channels = await ChannelService.get_all_channels(session)
    kb = get_admin_channels_keyboard(channels)
    await callback.message.edit_reply_markup(reply_markup=kb)


@router.callback_query(AdminChannelCallback.filter(F.action == "delete"))
async def handle_admin_channel_delete(
    callback: CallbackQuery,
    callback_data: AdminChannelCallback,
    session: AsyncSession,
    is_admin: bool,
) -> None:
    """Delete a required channel."""
    if not await require_admin(callback, is_admin):
        return
    success, msg = await ChannelService.delete_channel(
        session=session,
        admin_id=callback.from_user.id,
        channel_pk=callback_data.channel_id,
    )
@router.callback_query(F.data == "admin_diag_channels")
async def handle_admin_diagnostics(
    callback: CallbackQuery,
    session: AsyncSession,
    is_admin: bool,
    bot: Bot,
) -> None:
    """Run comprehensive system & channel diagnostics."""
    if not await require_admin(callback, is_admin):
        return

    channels = await ChannelService.get_required_channels(session)
    ch_results = []
    for ch in channels:
        target = ch.username or ch.channel_id
        try:
            member = await bot.get_chat_member(chat_id=ch.channel_id, user_id=bot.id)
            status_text = f"✅ {member.status.value}"
        except Exception:
            status_text = "⚠️ Missing Admin Access"
        ch_results.append(f"• <b>{escape(ch.title or target)}</b>: {status_text}")

    webapp_status = f"✅ <code>{settings.WEBAPP_URL}</code>" if settings.WEBAPP_URL else "⚠️ <i>Not Configured (Using Inline Fallback)</i>"
    local_route = f"http://{settings.WEBAPP_HOST}:{settings.WEBAPP_PORT}/verify"

    report = (
        "🔍 <b>System & Diagnostics Report</b>\n\n"
        f"🌐 <b>Public WebApp URL:</b> {webapp_status}\n"
        f"🖥️ <b>Local Server Route:</b> <code>{local_route}</code>\n"
        f"👑 <b>Active Admins:</b> {len(settings.admin_ids)}\n\n"
        "📢 <b>Required Channels:</b>\n"
        + ("\n".join(ch_results) if ch_results else "• <i>No channels configured</i>")
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Back to Channels", callback_data="admin_channels_list")],
            [InlineKeyboardButton(text="👑 Admin Panel", callback_data="admin_dashboard")],
        ]
    )
    try:
        await callback.message.edit_text(report, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(report, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin_add_channel")
async def handle_add_channel_start(
    callback: CallbackQuery,
    state: FSMContext,
    is_admin: bool,
) -> None:
    """Start Add Channel wizard."""
    if not await require_admin(callback, is_admin):
        return
    await state.set_state(AddChannelState.channel_id)
    text = (
        "➕ <b>Add Required Channel (Step 1/3)</b>\n\n"
        "Channel ka <b>Telegram Chat ID</b> ya <b>@Username</b> enter karein:\n"
        "Example: <code>-1001234567890</code> ya <code>@MyOffersChannel</code>\n\n"
        "⚠️ <i>Note: Bot must be added as administrator in the channel.</i>"
    )
    kb = get_admin_cancel_keyboard()
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.message(AddChannelState.channel_id)
async def handle_channel_step_id(message: Message, state: FSMContext) -> None:
    cid = validate_channel_id(message.text or "")
    if not cid:
        await message.answer("Invalid Channel ID/Username. Example: <code>@MyChannel</code> or <code>-1001234567890</code>:")
        return
    await state.update_data(channel_id=cid)
    await state.set_state(AddChannelState.title)
    await message.answer(
        "<b>Step 2/3:</b> Channel ka Display Title enter karein (e.g. <i>Official Deals Channel</i>):",
        reply_markup=get_admin_cancel_keyboard(),
        parse_mode="HTML",
    )


@router.message(AddChannelState.title)
async def handle_channel_step_title(message: Message, state: FSMContext) -> None:
    title = message.text.strip() if message.text else ""
    if not title:
        await message.answer("Title cannot be empty:")
        return
    await state.update_data(title=title)
    await state.set_state(AddChannelState.invite_link)
    await message.answer(
        "<b>Step 3/3:</b> Channel ka <b>Invite Link</b> enter karein (e.g. <code>https://t.me/MyChannel</code>):",
        reply_markup=get_admin_cancel_keyboard(),
        parse_mode="HTML",
    )


@router.message(AddChannelState.invite_link)
async def handle_channel_step_finalize(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    is_admin: bool,
) -> None:
    """Save new channel to database."""
    if not await require_admin(message, is_admin):
        return
    data = await state.get_data()
    await state.clear()

    invite_link = message.text.strip() if message.text else ""
    channel_id_val = data.get("channel_id")
    title_val = data.get("title")
    username_val = channel_id_val if channel_id_val.startswith("@") else None

    success, msg, ch = await ChannelService.add_channel(
        session=session,
        admin_id=message.from_user.id,
        channel_id=channel_id_val,
        title=title_val,
        invite_link=invite_link,
        username=username_val,
    )

    if success:
        await message.answer(
            f"✅ <b>Channel Successfully Added!</b>\n\n📢 <b>{title_val}</b> ({channel_id_val})",
            reply_markup=get_admin_main_keyboard(),
            parse_mode="HTML",
        )
    else:
        await message.answer(f"❌ {msg}", reply_markup=get_admin_main_keyboard())


# =========================================================================
# USER MANAGEMENT & AUDIT
# =========================================================================

@router.callback_query(F.data == "admin_user_prompt")
async def handle_admin_user_prompt(
    callback: CallbackQuery,
    state: FSMContext,
    is_admin: bool,
) -> None:
    """Prompt admin to enter user Telegram ID."""
    if not await require_admin(callback, is_admin):
        return
    await state.set_state(UserSearchState.query)
    text = "👥 <b>User Lookup</b>\n\nSearch karne ke liye user ka <b>Telegram User ID</b> ya <b>Referral Code</b> chat me type karein:"
    kb = get_admin_cancel_keyboard()
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.message(UserSearchState.query)
async def handle_admin_user_search(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    is_admin: bool,
) -> None:
    """Search and display user details."""
    if not await require_admin(message, is_admin):
        return
    query = (message.text or "").strip()
    await state.clear()

    user = None
    if query.isdigit():
        user = await UserService.get_user_by_telegram_id(session, int(query))
    if not user:
        stmt = select(User).where(User.referral_code == query.upper())
        user = (await session.execute(stmt)).scalar_one_or_none()

    if not user:
        await message.answer(
            f"❌ User '{query}' not found in database.",
            reply_markup=get_admin_main_keyboard(),
        )
        return

    summary = await UserService.get_user_points_summary(session, user.id)
    ban_status = "🔴 BANNED" if user.is_banned else "🟢 Active"

    text = (
        f"👤 <b>User Inspector</b>\n\n"
        f"<b>Name:</b> {user.first_name} {user.last_name or ''}\n"
        f"<b>Telegram ID:</b> <code>{user.telegram_id}</code>\n"
        f"<b>Username:</b> @{user.username or 'N/A'}\n"
        f"<b>Referral Code:</b> <code>{user.referral_code}</code>\n"
        f"<b>Status:</b> {ban_status}\n\n"
        f"💰 <b>Current Balance:</b> <code>{user.points}</code> ⭐\n"
        f"👥 <b>Successful Referrals:</b> {summary['successful_referrals']}\n"
        f"📈 <b>Points Earned:</b> {summary['total_earned']} ⭐\n"
        f"📉 <b>Points Spent:</b> {summary['total_spent']} ⭐\n"
        f"📅 <b>Joined:</b> {user.created_at.strftime('%d %b %Y %H:%M')}\n"
    )
    kb = get_admin_user_detail_keyboard(user)
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(AdminUserCallback.filter(F.action == "toggle_ban"))
async def handle_admin_user_ban_toggle(
    callback: CallbackQuery,
    callback_data: AdminUserCallback,
    session: AsyncSession,
    is_admin: bool,
) -> None:
    """Toggle user ban status."""
    if not await require_admin(callback, is_admin):
        return
    user = await UserService.get_user_by_id(session, callback_data.user_id)
    if not user:
        await callback.answer("User not found.", show_alert=True)
        return

    new_banned_state = not user.is_banned
    success, msg = await UserService.set_user_ban_status(
        session=session,
        admin_id=callback.from_user.id,
        user_id=user.id,
        is_banned=new_banned_state,
    )
    await callback.answer(msg, show_alert=True)
    kb = get_admin_user_detail_keyboard(user)
    await callback.message.edit_reply_markup(reply_markup=kb)


@router.callback_query(AdminUserCallback.filter(F.action.in_(["add_pts", "rem_pts"])))
async def handle_admin_point_adjust_prompt(
    callback: CallbackQuery,
    callback_data: AdminUserCallback,
    state: FSMContext,
    is_admin: bool,
) -> None:
    """Prompt admin for point adjustment amount."""
    if not await require_admin(callback, is_admin):
        return
    is_addition = (callback_data.action == "add_pts")
    await state.set_state(PointAdjustState.amount)
    await state.update_data(user_id=callback_data.user_id, is_addition=is_addition)

    action_label = "ADD" if is_addition else "DEDUCT"
    text = f"💰 <b>Points Adjustment ({action_label})</b>\n\nEnter the number of points to {action_label.lower()} (positive integer):"
    kb = get_admin_cancel_keyboard()
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.message(PointAdjustState.amount)
async def handle_admin_point_adjust_submit(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    is_admin: bool,
) -> None:
    """Execute point adjustment with audit logging."""
    if not await require_admin(message, is_admin):
        return
    data = await state.get_data()
    user_id = data.get("user_id")
    is_addition = data.get("is_addition", True)
    await state.clear()

    qty = validate_positive_int(message.text or "")
    if not qty:
        await message.answer("Invalid amount. Must be positive integer.", reply_markup=get_admin_main_keyboard())
        return

    amount = qty if is_addition else -qty
    success, msg, new_balance = await UserService.adjust_user_points(
        session=session,
        admin_id=message.from_user.id,
        user_id=user_id,
        amount=amount,
        reason="Manual Admin Adjustment",
    )

    if success:
        await message.answer(
            f"✅ {msg}\nNew balance: <b>{new_balance}</b> ⭐",
            reply_markup=get_admin_main_keyboard(),
            parse_mode="HTML",
        )
    else:
        await message.answer(f"❌ {msg}", reply_markup=get_admin_main_keyboard())


# =========================================================================
# REFERRALS & REDEMPTIONS LISTING
# =========================================================================

@router.callback_query(AdminNavCallback.filter(F.section == "referrals"))
async def handle_admin_referrals_view(
    callback: CallbackQuery,
    session: AsyncSession,
    is_admin: bool,
) -> None:
    """View recent referral tracking records."""
    if not await require_admin(callback, is_admin):
        return
    refs = await ReferralService.get_recent_referrals(session, limit=15)
    if not refs:
        text = "🤝 <b>Recent Referrals</b>\n\nNo referral records found yet."
    else:
        text = "🤝 <b>Recent Referrals (Last 15)</b>\n\n"
        for r in refs:
            ref_user = r.referrer.telegram_id if r.referrer else r.referrer_id
            joined_user = r.referred_user.telegram_id if r.referred_user else r.referred_id
            text += f"• Referrer: <code>{ref_user}</code> ➡️ New: <code>{joined_user}</code> | Status: <b>{r.status.value}</b> ({r.created_at.strftime('%d/%m %H:%M')})\n"

    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="👑 Admin Dashboard", callback_data="admin_dashboard")]]
    )
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(AdminNavCallback.filter(F.section == "redemptions"))
async def handle_admin_redemptions_view(
    callback: CallbackQuery,
    session: AsyncSession,
    is_admin: bool,
) -> None:
    """View recent redemption records."""
    if not await require_admin(callback, is_admin):
        return
    stmt = (
        select(Redemption)
        .options(selectinload(Redemption.user), selectinload(Redemption.coupon))
        .order_by(Redemption.id.desc())
        .limit(15)
    )
    redemptions = list((await session.execute(stmt)).scalars().all())

    if not redemptions:
        text = "🎟️ <b>Recent Redemptions</b>\n\nNo redemptions recorded yet."
    else:
        text = "🎟️ <b>Recent Redemptions (Last 15)</b>\n\n"
        for r in redemptions:
            user_tg = r.user.telegram_id if r.user else r.user_id
            coupon_name = r.coupon.title if r.coupon else f"Coupon #{r.coupon_id}"
            text += f"• User: <code>{user_tg}</code> | <b>{coupon_name}</b> | Code: <code>{r.coupon_code}</code> | -{r.points_spent} ⭐ ({r.created_at.strftime('%d/%m')})\n"

    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="👑 Admin Dashboard", callback_data="admin_dashboard")]]
    )
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(AdminNavCallback.filter(F.section == "logs"))
async def handle_admin_logs_view(
    callback: CallbackQuery,
    session: AsyncSession,
    is_admin: bool,
) -> None:
    """View administrative audit actions."""
    if not await require_admin(callback, is_admin):
        return
    stmt = select(AdminAction).order_by(AdminAction.id.desc()).limit(15)
    logs = list((await session.execute(stmt)).scalars().all())

    if not logs:
        text = "📜 <b>Admin Audit Logs</b>\n\nNo audit logs recorded yet."
    else:
        text = "📜 <b>Admin Audit Logs (Last 15)</b>\n\n"
        for l in logs:
            text += f"• [<code>{l.created_at.strftime('%d/%m %H:%M')}</code>] Admin #{l.admin_id} <b>{l.action}</b>: {l.target} - <i>{l.details}</i>\n"

    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="👑 Admin Dashboard", callback_data="admin_dashboard")]]
    )
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


# =========================================================================
# ANTI-FRAUD DEVICE INSPECTOR
# =========================================================================

class FraudSearchState(StatesGroup):
    query = State()


@router.callback_query(F.data == "admin_fraud_prompt")
async def handle_admin_fraud_prompt(
    callback: CallbackQuery,
    state: FSMContext,
    is_admin: bool,
) -> None:
    """Prompt admin to enter user Telegram ID for anti-fraud device check."""
    if not await require_admin(callback, is_admin):
        return
    await state.set_state(FraudSearchState.query)
    text = (
        "🛡️ <b>Anti-Fraud Device Inspector</b>\n\n"
        "Enter user's <b>Telegram User ID</b> or <b>Referral Code</b> to inspect device binding and risk status:"
    )
    kb = get_admin_cancel_keyboard()
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.message(FraudSearchState.query)
async def handle_admin_fraud_search(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    is_admin: bool,
) -> None:
    """Search user and display anti-fraud / device verification details."""
    if not await require_admin(message, is_admin):
        return
    query = (message.text or "").strip()
    await state.clear()

    user = None
    if query.isdigit():
        user = await UserService.get_user_by_telegram_id(session, int(query))
    if not user:
        stmt = select(User).where(User.referral_code == query.upper())
        user = (await session.execute(stmt)).scalar_one_or_none()

    if not user:
        await message.answer(
            f"❌ User '{query}' not found in database.",
            reply_markup=get_admin_main_keyboard(),
        )
        return

    from services.device_service import DeviceService
    binding = await DeviceService.get_device_binding_by_user(session, user.telegram_id)
    summary = await UserService.get_user_points_summary(session, user.id)

    ban_status = "🔴 BANNED" if user.is_banned else "🟢 Active"
    if binding:
        dev_status = f"🟢 Verified ({binding.status.value})"
        dev_id = f"<code>{binding.fingerprint_hash[:8]}...{binding.fingerprint_hash[-4:]}</code>"
        first_ver = binding.first_verified_at.strftime("%d %b %Y %H:%M")
        last_seen = binding.last_seen_at.strftime("%d %b %Y %H:%M")
        risk = binding.risk_score
    else:
        dev_status = "⚪ Not Verified"
        dev_id = "None"
        first_ver = "N/A"
        last_seen = "N/A"
        risk = 0

    text = (
        f"🛡️ <b>Anti-Fraud User Profile</b>\n\n"
        f"<b>Name:</b> {user.first_name} {user.last_name or ''}\n"
        f"<b>Telegram ID:</b> <code>{user.telegram_id}</code>\n"
        f"<b>Account Status:</b> {ban_status}\n"
        f"<b>Referral Code:</b> <code>{user.referral_code}</code>\n"
        f"<b>Referred By:</b> <code>{user.referred_by or 'None'}</code>\n\n"
        f"📱 <b>Device Status:</b> {dev_status}\n"
        f"🔑 <b>Device ID:</b> {dev_id}\n"
        f"🕒 <b>First Verified:</b> {first_ver}\n"
        f"👁️ <b>Last Seen:</b> {last_seen}\n"
        f"⚠️ <b>Risk Score:</b> {risk}\n\n"
        f"👥 <b>Successful Referrals:</b> {summary['successful_referrals']}\n"
        f"💰 <b>Balance:</b> {user.points} ⭐\n"
    )

    from keyboards.admin import get_admin_fraud_detail_keyboard
    kb = get_admin_fraud_detail_keyboard(user, has_device=(binding is not None))
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(AdminFraudCallback.filter(F.action == "release_device"))
async def handle_admin_release_device(
    callback: CallbackQuery,
    callback_data: AdminFraudCallback,
    session: AsyncSession,
    is_admin: bool,
) -> None:
    """Manually release a user's device binding."""
    if not await require_admin(callback, is_admin):
        return

    from services.device_service import DeviceService
    success, msg = await DeviceService.release_device_binding(
        session=session,
        admin_id=callback.from_user.id,
        telegram_user_id=callback_data.user_tg_id,
    )
    await session.commit()

    if success:
        await callback.answer("✅ Device binding released.", show_alert=True)
    else:
        await callback.answer(f"❌ {msg}", show_alert=True)

    user = await UserService.get_user_by_telegram_id(session, callback_data.user_tg_id)
    if user:
        from keyboards.admin import get_admin_fraud_detail_keyboard
        kb = get_admin_fraud_detail_keyboard(user, has_device=False)
        try:
            await callback.message.edit_reply_markup(reply_markup=kb)
        except Exception:
            pass


@router.callback_query(AdminFraudCallback.filter(F.action == "toggle_ban"))
async def handle_admin_fraud_toggle_ban(
    callback: CallbackQuery,
    callback_data: AdminFraudCallback,
    session: AsyncSession,
    is_admin: bool,
) -> None:
    """Toggle user ban status from fraud panel."""
    if not await require_admin(callback, is_admin):
        return

    user = await UserService.get_user_by_telegram_id(session, callback_data.user_tg_id)
    if not user:
        await callback.answer("User not found.", show_alert=True)
        return

    success, msg, new_ban = await UserService.toggle_user_ban(
        session=session,
        admin_id=callback.from_user.id,
        user_id=user.id,
    )
    await session.commit()

    if success:
        status_word = "BANNED" if new_ban else "UNBANNED"
        await callback.answer(f"User {status_word}.", show_alert=True)
    else:
        await callback.answer(f"❌ {msg}", show_alert=True)


# =========================================================================
# DATABASE BACKUP
# =========================================================================

@router.message(Command("backup"))
@router.callback_query(F.data == "admin_backup_db")
async def handle_admin_backup(
    event: Message | CallbackQuery,
    is_admin: bool,
) -> None:
    """Create timestamped SQLite database backup."""
    if not await require_admin(event, is_admin):
        return

    backup_path = create_sqlite_backup()
    if not backup_path or not backup_path.exists():
        msg = "❌ Failed to create database backup or non-SQLite database in use."
        if isinstance(event, Message):
            await event.answer(msg)
        else:
            await event.answer(msg, show_alert=True)
        return

    success_msg = f"✅ <b>Database Backup Created!</b>\n\nFile: <code>{backup_path.name}</code>"
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="👑 Admin Dashboard", callback_data="admin_dashboard")]]
    )

    if isinstance(event, Message):
        await event.answer(success_msg, reply_markup=kb, parse_mode="HTML")
    else:
        try:
            await event.message.edit_text(success_msg, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await event.message.answer(success_msg, reply_markup=kb, parse_mode="HTML")
        await event.answer("Backup created.")
