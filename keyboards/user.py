"""Master Inline keyboards and callback data definitions for Codes Xpress 💎."""

from typing import List, Optional
from urllib.parse import quote_plus
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters.callback_data import CallbackData
from models.coupon import Coupon
from models.channel import Channel
from models.redemption import Redemption
from utils.formatting import get_brand_icon


# =========================================================================
# CALLBACK DATA DEFINITIONS
# =========================================================================

class BrandNavCallback(CallbackData, prefix="bnav"):
    page: int


class BrandCouponsCallback(CallbackData, prefix="bcoup"):
    brand: str
    page: int


class CouponDetailCallback(CallbackData, prefix="cdet"):
    coupon_id: int
    brand: str = ""
    page: int = 1


class CouponConfirmCallback(CallbackData, prefix="cconf"):
    coupon_id: int
    brand: str = ""
    page: int = 1


class CouponRedeemCallback(CallbackData, prefix="credeem"):
    coupon_id: int


class CouponNavCallback(CallbackData, prefix="cnav"):
    category: str
    page: int


class MyCouponDetailCallback(CallbackData, prefix="mycdet"):
    redemption_id: int


class SupportReplyCallback(CallbackData, prefix="supreply"):
    user_tg_id: int


# Legacy callback aliases
class CategoryCallback(CallbackData, prefix="cat"):
    name: str


class AdminEditCouponCallback(CallbackData, prefix="aedit"):
    coupon_id: int


class AdminDeleteCouponCallback(CallbackData, prefix="adel"):
    coupon_id: int


class AdminViewCodesCallback(CallbackData, prefix="avcodes"):
    coupon_id: int


# =========================================================================
# USER KEYBOARDS
# =========================================================================

def get_main_menu_keyboard(is_admin: bool = False) -> InlineKeyboardMarkup:
    """Create main menu inline keyboard."""
    buttons = [
        [
            InlineKeyboardButton(text="🎁 Coupons", callback_data="menu_coupons"),
            InlineKeyboardButton(text="⭐ My Balance", callback_data="menu_balance"),
        ],
        [
            InlineKeyboardButton(text="🔗 Refer & Earn", callback_data="menu_refer"),
            InlineKeyboardButton(text="🎟️ My Coupons", callback_data="menu_my_coupons"),
        ],
        [
            InlineKeyboardButton(text="🆘 Support", callback_data="menu_support"),
        ],
    ]

    if is_admin:
        buttons.append([
            InlineKeyboardButton(text="👑 Admin Panel", callback_data="admin_dashboard")
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_balance_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for My Balance view."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Refer & Earn", callback_data="menu_refer")],
            [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu_home")],
        ]
    )


def get_insufficient_points_keyboard() -> InlineKeyboardMarkup:
    """Keyboard when user lacks enough points to redeem."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Refer & Earn", callback_data="menu_refer")],
            [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu_home")],
        ]
    )


def get_available_coupons_keyboard(
    coupons: List[Coupon],
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    """Create dynamic list of available coupon buttons with icons and pagination."""
    buttons = []

    for coupon in coupons:
        title_name = coupon.title
        btn_text = f"🎁 {title_name} · {coupon.points_required} ⭐"
        buttons.append([
            InlineKeyboardButton(
                text=btn_text,
                callback_data=CouponDetailCallback(coupon_id=coupon.id, brand=coupon.brand or "Brand", page=page).pack(),
            )
        ])

    # Pagination controls
    nav_row = []
    if page > 1:
        nav_row.append(
            InlineKeyboardButton(
                text="◀️",
                callback_data=BrandNavCallback(page=page - 1).pack(),
            )
        )
    if total_pages > 1:
        nav_row.append(
            InlineKeyboardButton(
                text=f"{page}/{total_pages}",
                callback_data="noop",
            )
        )
    if page < total_pages:
        nav_row.append(
            InlineKeyboardButton(
                text="▶️",
                callback_data=BrandNavCallback(page=page + 1).pack(),
            )
        )

    if nav_row:
        buttons.append(nav_row)

    buttons.append([
        InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu_home"),
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_no_brands_keyboard() -> InlineKeyboardMarkup:
    """Keyboard when no active brands/coupons exist."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Refresh", callback_data="menu_coupons")],
            [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu_home")],
        ]
    )


def get_coupon_detail_keyboard(
    coupon_id: int,
    brand: str = "",
    page: int = 1,
    can_redeem: bool = True,
) -> InlineKeyboardMarkup:
    """Create keyboard for coupon detail view."""
    buttons = []
    if can_redeem:
        buttons.append([
            InlineKeyboardButton(
                text="⭐ Redeem Now",
                callback_data=CouponConfirmCallback(coupon_id=coupon_id, brand=brand, page=page).pack(),
            )
        ])

    buttons.append([
        InlineKeyboardButton(text="🔙 Back", callback_data="menu_coupons"),
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_redeem_confirm_keyboard(
    coupon_id: int,
    brand: str = "",
    page: int = 1,
) -> InlineKeyboardMarkup:
    """Confirmation keyboard before coupon redemption."""
    cancel_callback = (
        CouponDetailCallback(coupon_id=coupon_id, brand=brand, page=page).pack()
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Confirm", callback_data=CouponRedeemCallback(coupon_id=coupon_id).pack()),
                InlineKeyboardButton(text="❌ Cancel", callback_data=cancel_callback),
            ]
        ]
    )


def get_channels_keyboard(channels: List[Channel], is_retry: bool = False) -> InlineKeyboardMarkup:
    """Create keyboard with links to join required channels + verify button."""
    buttons = []
    for i, ch in enumerate(channels, 1):
        clean_title = ch.title or (ch.username or ch.channel_id).lstrip("@")
        label = f"📢 Join {clean_title}"
        link = ch.invite_link
        if not link or not link.startswith("http"):
            username = ch.username or (ch.channel_id.lstrip("@") if ch.channel_id.startswith("@") else None)
            if username:
                link = f"https://t.me/{username}"
            else:
                link = "https://t.me"
        buttons.append([InlineKeyboardButton(text=label, url=link)])

    verify_btn_text = "✅ Verify Membership"
    buttons.append([
        InlineKeyboardButton(text=verify_btn_text, callback_data="verify_channels_click")
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_device_verification_keyboard(webapp_url: Optional[str] = None) -> InlineKeyboardMarkup:
    """Create keyboard for mandatory device verification."""
    target_url = (webapp_url or settings.WEBAPP_URL).strip()
    buttons = []
    if target_url and target_url.startswith("https://"):
        from aiogram.types import WebAppInfo
        buttons.append([
            InlineKeyboardButton(text="🔒 Verify", web_app=WebAppInfo(url=target_url))
        ])
    else:
        buttons.append([
            InlineKeyboardButton(text="🔒 Verify", callback_data="device_verify_action")
        ])
    buttons.append([
        InlineKeyboardButton(text="🆘 Support", callback_data="menu_support"),
        InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu_home"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_device_blocked_keyboard() -> InlineKeyboardMarkup:
    """Create keyboard when device is already bound / blocked."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🆘 Support", callback_data="menu_support"),
                InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu_home"),
            ]
        ]
    )


def get_share_referral_keyboard(bot_username: str, referral_code: str) -> InlineKeyboardMarkup:
    """Create referral share buttons."""
    referral_link = f"https://t.me/{bot_username}?start=ref_{referral_code}"
    share_text = f"🎁 Redeem free coupons with points!\nJoin here: {referral_link}"
    tg_share_url = f"https://t.me/share/url?url={quote_plus(referral_link)}&text={quote_plus(share_text)}"

    buttons = [
        [InlineKeyboardButton(text="📤 Share Link", url=tg_share_url)],
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu_home")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_my_coupons_keyboard(redemptions: List[Redemption]) -> InlineKeyboardMarkup:
    """Create list of user's redeemed coupons."""
    buttons = []
    for r in redemptions[:10]:
        title = r.coupon.title if r.coupon else "Coupon"
        brand = r.coupon.brand if r.coupon else ""
        date_str = r.created_at.strftime("%d %b")
        name = f"{brand} {title}".strip()
        btn_text = f"🎁 {name} ({date_str})"
        buttons.append([
            InlineKeyboardButton(
                text=btn_text,
                callback_data=MyCouponDetailCallback(redemption_id=r.id).pack(),
            )
        ])

    buttons.append([
        InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu_home"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_back_to_menu_keyboard() -> InlineKeyboardMarkup:
    """Standard back to menu keyboard."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu_home")]
        ]
    )


def get_support_cancel_keyboard() -> InlineKeyboardMarkup:
    """Create cancel button for support prompt."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="↩️ Cancel", callback_data="support_cancel")]
        ]
    )


def get_support_admin_keyboard(user_tg_id: int) -> InlineKeyboardMarkup:
    """Create Reply button for admin on support request."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="↩️ Reply", callback_data=SupportReplyCallback(user_tg_id=user_tg_id).pack())]
        ]
    )


def get_admin_reply_cancel_keyboard() -> InlineKeyboardMarkup:
    """Create Cancel button for admin replying to support."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="↩️ Cancel", callback_data="admin_support_cancel")]
        ]
    )


# Legacy helpers for backwards compatibility
def get_categories_keyboard() -> InlineKeyboardMarkup:
    return get_no_brands_keyboard()


def get_brands_paginated_keyboard(brands: List[str], page: int, total_pages: int) -> InlineKeyboardMarkup:
    buttons = []
    for brand in brands:
        icon = get_brand_icon(brand)
        btn_text = f"{icon} {brand}"
        buttons.append([
            InlineKeyboardButton(
                text=btn_text,
                callback_data=BrandCouponsCallback(brand=brand, page=1).pack(),
            )
        ])

    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton(text="◀️", callback_data=BrandNavCallback(page=page - 1).pack()))
    if total_pages > 1:
        nav_row.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton(text="▶️", callback_data=BrandNavCallback(page=page + 1).pack()))

    if nav_row:
        buttons.append(nav_row)

    buttons.append([InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu_home")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_brand_coupons_keyboard(brand: str, coupons: List[Coupon], page: int, total_pages: int) -> InlineKeyboardMarkup:
    return get_available_coupons_keyboard(coupons, page, total_pages)


def get_coupons_paginated_keyboard(coupons: List[Coupon], page: int, total_pages: int, category: str = "ALL") -> InlineKeyboardMarkup:
    return get_available_coupons_keyboard(coupons, page, total_pages)
