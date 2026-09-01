"""Main menu navigation, information commands, and static policy displays."""

import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from config import settings
from services.user_service import UserService
from keyboards.user import get_main_menu_keyboard, get_back_to_menu_keyboard
from utils.formatting import (
    format_user_welcome,
    format_help_message,
    format_privacy_message,
    format_terms_message,
    safe_edit_message,
)

logger = logging.getLogger(__name__)

router = Router(name="menu_router")


@router.callback_query(F.data == "menu_home")
async def handle_menu_home(
    callback: CallbackQuery,
    session: AsyncSession,
    is_admin: bool,
) -> None:
    """Return to main menu."""
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

    await callback.answer()
    await safe_edit_message(callback, welcome_text, reply_markup=menu_kb)


@router.message(Command("help"))
@router.callback_query(F.data == "menu_help")
async def handle_help(event: Message | CallbackQuery) -> None:
    """Show help and guide message."""
    text = format_help_message()
    kb = get_back_to_menu_keyboard()
    if isinstance(event, CallbackQuery):
        await event.answer()
    await safe_edit_message(event, text, reply_markup=kb)


@router.message(Command("privacy"))
async def handle_privacy(message: Message) -> None:
    """Show privacy policy."""
    text = format_privacy_message()
    kb = get_back_to_menu_keyboard()
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.message(Command("terms"))
async def handle_terms(message: Message) -> None:
    """Show terms & disclaimer."""
    text = format_terms_message()
    kb = get_back_to_menu_keyboard()
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("noop"))
async def handle_noop(callback: CallbackQuery) -> None:
    """Handle dummy pagination buttons."""
    await callback.answer()
