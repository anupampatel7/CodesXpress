"""Master Inline keyboards and callback data definitions for Codes Xpress 💎."""

from typing import List, Optional, Dict, Tuple
from urllib.parse import quote_plus
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters.callback_data import CallbackData
from config import settings
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


class CouponRedeemCallback(CallbackData, prefix="cred"):
    coupon_id: int


class CouponNavCallback(CallbackData, prefix="cnav"):
    action: str  # next, prev
    category: str
    page: int


class MyCouponDetailCallback(CallbackData, prefix="mycdet"):
    redemption_id: int


class SupportReplyCallback(CallbackData, prefix="supreply"):
    user_tg_id: int


# Legacy callback aliases
class CategoryCallback(CallbackData, prefix="cat"):
    category: str


class AdminUserActionCallback(CallbackData, prefix="auact"):
    action: str  # add_pts, rem_pts, ban, unban
    user_id: int


class AdminEditCouponCallback(CallbackData, prefix="aedit"):
    coupon_id: int


class AdminDeleteCouponCallback(CallbackData, prefix="adel"):
    coupon_id: int


class AdminViewCodesCallback(CallbackData, prefix="avcodes"):
    coupon_id: int


# =========================================================================
# =========================================================================
# USER KEYBOARDS (SINGLETONS FOR STATIC MENUS)
# =========================================================================

_MAIN_MENU_USER_KB = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="🎁 Redeem", callback_data="menu_coupons"),
            InlineKeyboardButton(text="⭐ My Balance", callback_data="menu_balance"),
        ],
        [
            InlineKeyboardButton(text="🔗 Refer & Earn", callback_data="menu_refer"),
            InlineKeyboardButton(text="🎟️ My Coupons", callback_data="menu_my_coupons"),
        ],
        [
            InlineKeyboardButton(text="📦 Check Stock", callback_data="menu_check_stock"),
            InlineKeyboardButton(text="🆘 Support", callback_data="menu_support"),
        ],
    ]
)

_MAIN_MENU_ADMIN_KB = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="🎁 Redeem", callback_data="menu_coupons"),
            InlineKeyboardButton(text="⭐ My Balance", callback_data="menu_balance"),
        ],
        [
            InlineKeyboardButton(text="🔗 Refer & Earn", callback_data="menu_refer"),
            InlineKeyboardButton(text="🎟️ My Coupons", callback_data="menu_my_coupons"),
        ],
        [
            InlineKeyboardButton(text="📦 Check Stock", callback_data="menu_check_stock"),
            InlineKeyboardButton(text="🆘 Support", callback_data="menu_support"),
        ],
        [
            InlineKeyboardButton(text="👑 Admin Panel", callback_data="admin_dashboard"),
        ],
    ]
)

_CHECK_STOCK_KB = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Back", callback_data="menu_home")],
    ]
)

_BALANCE_KB = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Refer & Earn", callback_data="menu_refer")],
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu_home")],
    ]
)

_INSUFFICIENT_POINTS_KB = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Refer & Earn", callback_data="menu_refer")],
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu_home")],
    ]
)

_NO_BRANDS_KB = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Refresh", callback_data="menu_coupons")],
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu_home")],
    ]
)

_BACK_TO_MENU_KB = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu_home")]
    ]
)

_DEVICE_BLOCKED_KB = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="🆘 Support", callback_data="menu_support"),
            InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu_home"),
        ]
    ]
)

_SUPPORT_CANCEL_KB = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="↩️ Cancel", callback_data="support_cancel")]
    ]
)

_ADMIN_SUPPORT_CANCEL_KB = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="↩️ Cancel", callback_data="admin_support_cancel")]
    ]
)


def get_main_menu_keyboard(is_admin: bool = False) -> InlineKeyboardMarkup:
    """Return main menu inline keyboard singleton."""
    return _MAIN_MENU_ADMIN_KB if is_admin else _MAIN_MENU_USER_KB


def get_check_stock_keyboard() -> InlineKeyboardMarkup:
    """Return keyboard for stock check view singleton."""
    return _CHECK_STOCK_KB


def get_balance_keyboard() -> InlineKeyboardMarkup:
    """Return keyboard for My Balance view singleton."""
    return _BALANCE_KB


def get_insufficient_points_keyboard() -> InlineKeyboardMarkup:
    """Return keyboard when user lacks enough points to redeem singleton."""
    return _INSUFFICIENT_POINTS_KB


def get_no_brands_keyboard() -> InlineKeyboardMarkup:
    """Return keyboard when no active brands/coupons exist singleton."""
    return _NO_BRANDS_KB


def get_back_to_menu_keyboard() -> InlineKeyboardMarkup:
    """Return standard back to menu keyboard singleton."""
    return _BACK_TO_MENU_KB


def get_device_blocked_keyboard() -> InlineKeyboardMarkup:
    """Return keyboard when device is already bound / blocked singleton."""
    return _DEVICE_BLOCKED_KB


def get_support_cancel_keyboard() -> InlineKeyboardMarkup:
    """Return cancel button for support prompt singleton."""
    return _SUPPORT_CANCEL_KB


def get_admin_reply_cancel_keyboard() -> InlineKeyboardMarkup:
    """Return cancel button for admin replying to support singleton."""
    return _ADMIN_SUPPORT_CANCEL_KB


DIGIT_EMOJI_MAP = {
    "0": "0️⃣",
    "1": "1️⃣",
    "2": "2️⃣",
    "3": "3️⃣",
    "4": "4️⃣",
    "5": "5️⃣",
    "6": "6️⃣",
    "7": "7️⃣",
    "8": "8️⃣",
    "9": "9️⃣",
}


def to_number_emoji(num: int) -> str:
    """Convert integer to number keycap emojis (e.g. 6 -> 6️⃣, 10 -> 🔟)."""
    if num == 10:
        return "🔟"
    return "".join(DIGIT_EMOJI_MAP.get(d, d) for d in str(num))


def get_available_coupons_keyboard(
    coupons: List[Coupon],
    page: int,
    total_pages: int,
    coupon_stocks: Optional[Dict[int, int]] = None,
) -> InlineKeyboardMarkup:
    """Create dynamic list of available coupon buttons with green/red stock indicator and number emoji points."""
    buttons = []

    for coupon in coupons:
        stock = coupon_stocks.get(coupon.id, coupon.stock) if coupon_stocks is not None else coupon.stock
        indicator = "🟢" if stock > 0 else "🔴"
        pts_emoji = to_number_emoji(coupon.points_required)
        btn_text = f"{indicator} {coupon.title} : {pts_emoji}"
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


REQUIRED_CHANNEL_ORDER = [
    "@offermate",
    "@offerraider",
    "@multi_purpose_with_me_sale",
    "@offerelite",
]


def _get_channel_canonical_order_and_label(ch: Channel) -> Tuple[int, str]:
    """Determine canonical order index (1..4) and button label for a required channel."""
    cid = (ch.channel_id or "").strip().lower()
    uname = (ch.username or "").strip().lower()
    if uname and not uname.startswith("@"):
        uname = f"@{uname}"
    for idx, target in enumerate(REQUIRED_CHANNEL_ORDER, 1):
        if cid == target or uname == target:
            return idx, f"📢 Channel {idx}"
    return 999 + (ch.id or 0), f"📢 Channel {ch.id or ''}"


def get_channels_keyboard(channels: List[Channel], is_retry: bool = False) -> InlineKeyboardMarkup:
    """Create keyboard with links to join required channels in exact order + verify button."""
    sorted_channels = sorted(channels, key=lambda c: _get_channel_canonical_order_and_label(c)[0])
    buttons = []
    for ch in sorted_channels:
        _, label = _get_channel_canonical_order_and_label(ch)
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
        verify_url = target_url if target_url.endswith("/verify") else f"{target_url.rstrip('/')}/verify"
        buttons.append([
            InlineKeyboardButton(text="🔒 Verify Device", web_app=WebAppInfo(url=verify_url))
        ])
    else:
        buttons.append([
            InlineKeyboardButton(text="🔒 Verify Device", callback_data="device_verify_action")
        ])
    buttons.append([
        InlineKeyboardButton(text="🔄 Check Verification", callback_data="device_check_refresh")
    ])
    buttons.append([
        InlineKeyboardButton(text="🆘 Support", callback_data="menu_support"),
        InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu_home"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


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


def get_support_admin_keyboard(user_tg_id: int) -> InlineKeyboardMarkup:
    """Create Reply button for admin on support request."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="↩️ Reply", callback_data=SupportReplyCallback(user_tg_id=user_tg_id).pack())]
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
