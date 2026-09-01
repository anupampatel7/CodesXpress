"""Admin control panel inline keyboards and callback data factories."""

from typing import List, Optional
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters.callback_data import CallbackData
from models.coupon import Coupon, StockType
from models.channel import Channel
from models.user import User


class AdminCouponCallback(CallbackData, prefix="ac"):
    action: str  # view, edit, restock, toggle, delete, add_codes, view_codes
    coupon_id: int
    page: int = 1


class AdminChannelCallback(CallbackData, prefix="ach"):
    action: str  # view, toggle, delete
    channel_id: int


class AdminUserCallback(CallbackData, prefix="au"):
    action: str  # view, add_pts, rem_pts, toggle_ban
    user_id: int


class AdminFraudCallback(CallbackData, prefix="afraud"):
    action: str  # release_device, block_device, toggle_ban
    user_tg_id: int


class AdminNavCallback(CallbackData, prefix="anav"):
    section: str  # coupons, channels, users, referrals, redemptions, logs, fraud
    page: int = 1


def get_admin_main_keyboard() -> InlineKeyboardMarkup:
    """Create admin dashboard main menu keyboard."""
    buttons = [
        [
            InlineKeyboardButton(text="📊 Refresh Dashboard", callback_data="admin_dashboard"),
        ],
        [
            InlineKeyboardButton(text="🎁 Manage Coupons", callback_data=AdminNavCallback(section="coupons", page=1).pack()),
            InlineKeyboardButton(text="➕ Add Coupon", callback_data="admin_add_coupon"),
        ],
        [
            InlineKeyboardButton(text="👥 Manage Users", callback_data="admin_user_prompt"),
            InlineKeyboardButton(text="🛡️ Anti-Fraud", callback_data="admin_fraud_prompt"),
        ],
        [
            InlineKeyboardButton(text="📢 Required Channels", callback_data="admin_channels_list"),
            InlineKeyboardButton(text="🤝 View Referrals", callback_data=AdminNavCallback(section="referrals", page=1).pack()),
        ],
        [
            InlineKeyboardButton(text="🎟️ Redemptions", callback_data=AdminNavCallback(section="redemptions", page=1).pack()),
            InlineKeyboardButton(text="💾 Backup Database", callback_data="admin_backup_db"),
        ],
        [
            InlineKeyboardButton(text="📜 Audit Logs", callback_data=AdminNavCallback(section="logs", page=1).pack()),
            InlineKeyboardButton(text="🏠 User Main Menu", callback_data="menu_home"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_admin_coupons_keyboard(coupons: List[Coupon], page: int, total_pages: int) -> InlineKeyboardMarkup:
    """List of all coupons in admin panel."""
    buttons = []
    for c in coupons:
        status_tag = "🟢" if c.is_active else "🔴"
        mode_tag = "📦" if c.stock_type == StockType.QUANTITY else "🔢"
        btn_text = f"{status_tag} {mode_tag} {c.title} (Stock: {c.stock})"
        buttons.append([
            InlineKeyboardButton(
                text=btn_text,
                callback_data=AdminCouponCallback(action="view", coupon_id=c.id, page=page).pack(),
            )
        ])

    nav_row = []
    if page > 1:
        nav_row.append(
            InlineKeyboardButton(text="◀️", callback_data=AdminNavCallback(section="coupons", page=page - 1).pack())
        )
    if total_pages > 1:
        nav_row.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav_row.append(
            InlineKeyboardButton(text="▶️", callback_data=AdminNavCallback(section="coupons", page=page + 1).pack())
        )

    if nav_row:
        buttons.append(nav_row)

    buttons.append([
        InlineKeyboardButton(text="➕ Add Coupon", callback_data="admin_add_coupon"),
        InlineKeyboardButton(text="👑 Admin Panel", callback_data="admin_dashboard"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_admin_coupon_detail_keyboard(coupon: Coupon, page: int = 1) -> InlineKeyboardMarkup:
    """Action buttons for a single coupon in admin."""
    toggle_text = "🚫 Disable" if coupon.is_active else "🟢 Enable"
    buttons = [
        [
            InlineKeyboardButton(
                text="📦 Restock Coupon",
                callback_data=AdminCouponCallback(action="add_codes", coupon_id=coupon.id, page=page).pack(),
            ),
            InlineKeyboardButton(
                text="📊 Stock",
                callback_data=AdminCouponCallback(action="view_codes", coupon_id=coupon.id, page=page).pack(),
            ),
        ],
        [
            InlineKeyboardButton(
                text="✏️ Edit",
                callback_data=AdminCouponCallback(action="edit", coupon_id=coupon.id, page=page).pack(),
            ),
            InlineKeyboardButton(
                text=toggle_text,
                callback_data=AdminCouponCallback(action="toggle", coupon_id=coupon.id, page=page).pack(),
            ),
        ],
        [
            InlineKeyboardButton(
                text="⬅️ Back to List",
                callback_data=AdminNavCallback(section="coupons", page=page).pack(),
            ),
            InlineKeyboardButton(text="👑 Admin Panel", callback_data="admin_dashboard"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_admin_channels_keyboard(channels: List[Channel]) -> InlineKeyboardMarkup:
    """List of all channels in admin panel."""
    buttons = []
    for ch in channels:
        status_tag = "🟢" if ch.is_active else "🔴"
        req_tag = "🔒" if ch.is_required else "📢"
        btn_text = f"{status_tag} {req_tag} {ch.title or ch.channel_id}"
        buttons.append([
            InlineKeyboardButton(
                text=btn_text,
                callback_data=AdminChannelCallback(action="view", channel_id=ch.id).pack(),
            )
        ])

    buttons.append([
        InlineKeyboardButton(text="➕ Add Channel", callback_data="admin_add_channel"),
        InlineKeyboardButton(text="🔍 Diagnose Setup", callback_data="admin_diag_channels"),
    ])
    buttons.append([
        InlineKeyboardButton(text="👑 Admin Panel", callback_data="admin_dashboard"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_admin_channel_detail_keyboard(channel: Channel) -> InlineKeyboardMarkup:
    """Actions for a single channel in admin panel."""
    toggle_text = "🔴 Deactivate" if channel.is_active else "🟢 Activate"
    buttons = [
        [
            InlineKeyboardButton(
                text="🔗 Test Invite Link",
                url=channel.invite_link if channel.invite_link.startswith("http") else "https://t.me",
            ),
        ],
        [
            InlineKeyboardButton(
                text=toggle_text,
                callback_data=AdminChannelCallback(action="toggle", channel_id=channel.id).pack(),
            ),
            InlineKeyboardButton(
                text="🗑️ Delete Channel",
                callback_data=AdminChannelCallback(action="delete", channel_id=channel.id).pack(),
            ),
        ],
        [
            InlineKeyboardButton(text="⬅️ All Channels", callback_data="admin_channels_list"),
            InlineKeyboardButton(text="👑 Admin Panel", callback_data="admin_dashboard"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_admin_user_detail_keyboard(user: User) -> InlineKeyboardMarkup:
    """Actions for a specific user."""
    ban_text = "✅ Unban User" if user.is_banned else "🚫 Ban User"
    buttons = [
        [
            InlineKeyboardButton(
                text="➕ Add Points",
                callback_data=AdminUserCallback(action="add_pts", user_id=user.id).pack(),
            ),
            InlineKeyboardButton(
                text="➖ Remove Points",
                callback_data=AdminUserCallback(action="rem_pts", user_id=user.id).pack(),
            ),
        ],
        [
            InlineKeyboardButton(
                text=ban_text,
                callback_data=AdminUserCallback(action="toggle_ban", user_id=user.id).pack(),
            ),
        ],
        [
            InlineKeyboardButton(text="🔍 Search Another User", callback_data="admin_user_prompt"),
            InlineKeyboardButton(text="👑 Admin Panel", callback_data="admin_dashboard"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_admin_fraud_detail_keyboard(user: User, has_device: bool) -> InlineKeyboardMarkup:
    """Anti-fraud control actions for a specific user."""
    ban_text = "✅ Unban User" if user.is_banned else "🚫 Ban User"
    buttons = []

    if has_device:
        buttons.append([
            InlineKeyboardButton(
                text="🔓 Release Device Binding",
                callback_data=AdminFraudCallback(action="release_device", user_tg_id=user.telegram_id).pack(),
            ),
        ])

    buttons.append([
        InlineKeyboardButton(
            text=ban_text,
            callback_data=AdminFraudCallback(action="toggle_ban", user_tg_id=user.telegram_id).pack(),
        ),
    ])

    buttons.append([
        InlineKeyboardButton(text="🔍 Check Another User", callback_data="admin_fraud_prompt"),
        InlineKeyboardButton(text="👑 Admin Panel", callback_data="admin_dashboard"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_admin_cancel_keyboard() -> InlineKeyboardMarkup:
    """Standard cancel button during multi-step forms."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Cancel Operation", callback_data="admin_cancel_fsm")]
        ]
    )
