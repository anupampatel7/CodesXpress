"""Support system handler for user-admin communications."""

import logging
from html import escape
from aiogram import Router, F, Bot
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, ContentType
from sqlalchemy.ext.asyncio import AsyncSession
from config import settings
from services.user_service import UserService
from keyboards.user import (
    SupportReplyCallback,
    get_main_menu_keyboard,
    get_support_cancel_keyboard,
    get_support_admin_keyboard,
    get_admin_reply_cancel_keyboard,
)
from utils.formatting import format_user_welcome

logger = logging.getLogger(__name__)

router = Router(name="support_router")


# FSM States
class UserSupportState(StatesGroup):
    waiting_for_message = State()


class AdminSupportReplyState(StatesGroup):
    waiting_for_reply = State()


# =========================================================================
# USER SUPPORT FLOW
# =========================================================================

@router.message(Command("support"))
@router.callback_query(F.data == "menu_support")
async def handle_support_start(
    event: Message | CallbackQuery,
    state: FSMContext,
) -> None:
    """Prompt user to send support message and enter FSM state."""
    await state.set_state(UserSupportState.waiting_for_message)
    text = (
        "🆘 <b>Support</b>\n\n"
        "Need help? Send your message below and our support team will review it."
    )
    kb = get_support_cancel_keyboard()

    if isinstance(event, CallbackQuery):
        await event.answer()
    from utils.formatting import safe_edit_message
    await safe_edit_message(event, text, reply_markup=kb)


@router.callback_query(F.data == "support_cancel")
async def handle_support_cancel(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    is_admin: bool,
) -> None:
    """Cancel support FSM and return to main menu."""
    await state.clear()
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

    welcome_text = format_user_welcome(user, settings.BOT_USERNAME)
    menu_kb = get_main_menu_keyboard(is_admin=is_admin)

    await callback.answer("Support cancelled.", show_alert=False)
    from utils.formatting import safe_edit_message
    await safe_edit_message(callback, welcome_text, reply_markup=menu_kb)


@router.message(UserSupportState.waiting_for_message)
async def handle_user_support_message(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    is_admin: bool,
    bot: Bot,
) -> None:
    """Process user support request and forward to ADMIN_ID."""
    from_user = message.from_user
    if not from_user:
        return

    admin_id = settings.ADMIN_ID
    if not admin_id or admin_id == 0:
        await message.answer("⚠️ Support is temporarily unavailable. Please try again later.")
        await state.clear()
        return

    user_name = escape(from_user.first_name or "User")
    username_str = f"@{escape(from_user.username)}" if from_user.username else "None"
    user_id = from_user.id
    user_msg_text = escape(message.text or message.caption or "(Media Attachment)")

    admin_notification = (
        "🆘 <b>Support Request</b>\n\n"
        f"👤 {user_name}\n"
        f"🆔 <code>{user_id}</code>\n"
        f"🔗 {username_str}\n\n"
        f"💬 {user_msg_text}"
    )
    admin_kb = get_support_admin_keyboard(user_id)

    # Deliver to ADMIN_ID
    try:
        if message.photo:
            photo_id = message.photo[-1].file_id
            await bot.send_photo(
                chat_id=admin_id,
                photo=photo_id,
                caption=admin_notification,
                reply_markup=admin_kb,
                parse_mode="HTML",
            )
        elif message.document:
            await bot.send_document(
                chat_id=admin_id,
                document=message.document.file_id,
                caption=admin_notification,
                reply_markup=admin_kb,
                parse_mode="HTML",
            )
        elif message.video:
            await bot.send_video(
                chat_id=admin_id,
                video=message.video.file_id,
                caption=admin_notification,
                reply_markup=admin_kb,
                parse_mode="HTML",
            )
        else:
            await bot.send_message(
                chat_id=admin_id,
                text=admin_notification,
                reply_markup=admin_kb,
                parse_mode="HTML",
            )
    except Exception as e:
        logger.error(f"Could not forward support message to admin {admin_id}: {e}", exc_info=True)

    await state.clear()

    # Confirmation to user
    user = await UserService.get_user_by_telegram_id(session, from_user.id)
    menu_kb = get_main_menu_keyboard(is_admin=is_admin)

    await message.answer(
        "✅ <b>Message Sent</b>\n\nYour message has been forwarded to support.",
        reply_markup=menu_kb,
        parse_mode="HTML",
    )


# =========================================================================
# ADMIN REPLY FLOW
# =========================================================================

@router.callback_query(SupportReplyCallback.filter())
async def handle_admin_reply_click(
    callback: CallbackQuery,
    callback_data: SupportReplyCallback,
    state: FSMContext,
    is_admin: bool,
) -> None:
    """Admin clicks Reply button on a support request."""
    # Server-side authorization check
    from_user = callback.from_user
    if not from_user or not settings.is_admin(from_user.id):
        await callback.answer("❌ Unauthorized access.", show_alert=True)
        return

    target_user_id = callback_data.user_tg_id
    await state.set_state(AdminSupportReplyState.waiting_for_reply)
    await state.update_data(target_user_id=target_user_id)

    text = (
        f"↩️ <b>Replying to User <code>{target_user_id}</code></b>\n\n"
        "Type your reply message:"
    )
    kb = get_admin_reply_cancel_keyboard()

    try:
        await callback.message.reply(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin_support_cancel")
async def handle_admin_reply_cancel(
    callback: CallbackQuery,
    state: FSMContext,
    is_admin: bool,
) -> None:
    """Admin cancels support reply."""
    from_user = callback.from_user
    if not from_user or not settings.is_admin(from_user.id):
        await callback.answer("❌ Unauthorized.", show_alert=True)
        return

    await state.clear()
    try:
        await callback.message.edit_text("❌ Reply cancelled.")
    except Exception:
        pass
    await callback.answer("Cancelled.")


@router.message(AdminSupportReplyState.waiting_for_reply)
async def handle_admin_send_reply(
    message: Message,
    state: FSMContext,
    is_admin: bool,
    bot: Bot,
) -> None:
    """Send admin reply directly to target user."""
    from_user = message.from_user
    if not from_user or not settings.is_admin(from_user.id):
        return

    data = await state.get_data()
    target_user_id = data.get("target_user_id")
    await state.clear()

    if not target_user_id:
        await message.answer("❌ Target user not found in state.")
        return

    reply_content = escape(message.text or message.caption or "(Media)")

    user_notification = (
        "🆘 <b>Support</b>\n\n"
        "<b>Admin:</b>\n"
        f"{reply_content}"
    )

    try:
        if message.photo:
            await bot.send_photo(
                chat_id=target_user_id,
                photo=message.photo[-1].file_id,
                caption=user_notification,
                parse_mode="HTML",
            )
        else:
            await bot.send_message(
                chat_id=target_user_id,
                text=user_notification,
                parse_mode="HTML",
            )
        await message.answer(f"✅ <b>Reply sent to user <code>{target_user_id}</code>!</b>", parse_mode="HTML")
    except Exception as e:
        logger.error(f"Could not send reply to user {target_user_id}: {e}")
        await message.answer(f"❌ Failed to send reply to user <code>{target_user_id}</code>: {e}", parse_mode="HTML")
