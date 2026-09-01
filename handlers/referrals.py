"""Refer & Earn handler showing user referral link and sharing statistics."""

import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from config import settings
from services.user_service import UserService
from services.referral_service import ReferralService
from keyboards.user import get_share_referral_keyboard
from utils.formatting import format_refer_earn, safe_edit_message

logger = logging.getLogger(__name__)

router = Router(name="referrals_router")


@router.message(Command("refer"))
@router.callback_query(F.data == "menu_refer")
async def handle_refer_and_earn(
    event: Message | CallbackQuery,
    session: AsyncSession,
) -> None:
    """Display user referral link and stats."""
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

    # Calculate referral stats
    ref_stats = await ReferralService.get_user_referral_stats(session, user.id)
    referral_link = f"https://t.me/{settings.BOT_USERNAME}?start=ref_{user.referral_code}"

    msg_text = format_refer_earn(
        referral_link=referral_link,
        successful_referrals=ref_stats["successful"],
        points_earned=ref_stats["successful"] * settings.POINTS_PER_REFERRAL,
        pending_referrals=ref_stats["pending"],
        current_points=user.points,
    )

    kb = get_share_referral_keyboard(settings.BOT_USERNAME, user.referral_code)

    if isinstance(event, CallbackQuery):
        await event.answer()
    await safe_edit_message(event, msg_text, reply_markup=kb)
