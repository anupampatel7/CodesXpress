"""Master UI formatting and presentation helpers for Codes Xpress 💎."""

from typing import Optional, List, Any
from datetime import datetime
from html import escape
from models.coupon import Coupon, StockType
from models.user import User


# =========================================================================
# 1. MAIN MENU & ONBOARDING
# =========================================================================

def format_user_welcome(user: User, bot_username: str) -> str:
    """Format premium, minimal, and professional welcome message."""
    pts = user.points
    pt_label = "Point" if pts == 1 else "Points"
    return (
        "👋 <b>Welcome to Codes Xpress</b>\n\n"
        "🎁 <b>Exclusive Coupons</b>\n"
        "Redeem your favourite offers with Points.\n\n"
        "🔗 <b>Refer & Earn</b>\n"
        "Earn <b>1 Point</b> for every successful referral.\n\n"
        f"⭐ <b>Your Balance: {pts} {pt_label}</b>\n\n"
        "<i>Choose an option to continue.</i>"
    )


# =========================================================================
# 2. CHANNELS & VERIFICATION
# =========================================================================

def format_channel_prompt(channels: List) -> str:
    """Format quick verification prompt."""
    return (
        "🔒 <b>Quick Verification</b>\n\n"
        "Join all required channels to activate your referral reward."
    )


def format_channel_missing(missing_channels: List) -> str:
    """Format missing channels friendly prompt showing which channel(s) are still missing."""
    if missing_channels:
        missing_names = []
        for ch in missing_channels:
            name = getattr(ch, "title", None) or getattr(ch, "username", None) or getattr(ch, "channel_id", "")
            if isinstance(name, str) and not name.startswith("@") and not getattr(ch, "title", None):
                name = f"@{name}"
            missing_names.append(f"• <b>{escape(str(name))}</b>")
        joined_list = "\n".join(missing_names)
        return (
            "⚠️ <b>Almost there!</b>\n\n"
            f"You still need to join:\n{joined_list}\n\n"
            "Please join the channel(s) above and click <b>Verify Membership</b>."
        )
    return (
        "⚠️ <b>Almost there!</b>\n\n"
        "Please join all required channels and try again."
    )


def format_channel_verified() -> str:
    """Format channel membership verification success notice."""
    return (
        "📢 <b>Channels Verified!</b>\n\n"
        "You have joined all required channels."
    )


def format_account_activated() -> str:
    """Format final account activation notice after all verifications succeed."""
    return (
        "✅ <b>Verification Complete</b>\n\n"
        "Your device has been verified successfully.\n"
        "Your account is now activated. 🎉"
    )


def format_channel_diagnostic_error(channel_id: str, error_detail: str) -> str:
    """Format diagnostic message when bot cannot access a required channel."""
    return (
        "⚠️ <b>Channel Setup Issue</b>\n\n"
        f"Channel: <code>{escape(channel_id)}</code>\n"
        f"Error: <i>{escape(error_detail)}</i>\n\n"
        "👉 Ensure the bot is added as an administrator in the channel."
    )


def format_device_verification_prompt() -> str:
    """Format device verification initial prompt."""
    return (
        "🔐 <b>Device Verification</b>\n\n"
        "One device can participate in referral rewards with one Telegram account.\n\n"
        "Verify your device to continue."
    )


def format_device_blocked() -> str:
    """Format device already bound / blocked error message."""
    return (
        "⚠️ <b>Verification unavailable</b>\n\n"
        "This device has already been used for referral verification.\n\n"
        "If you believe this is a mistake, contact Support."
    )


def format_device_verification_success() -> str:
    """Format device verification success notice."""
    return (
        "✅ <b>Verification Complete</b>\n\n"
        "Your device has been verified successfully.\n"
        "Your account is now activated. 🎉"
    )


# =========================================================================
# 3. BRAND ICONS & COUPONS FORMATTING
# =========================================================================

BRAND_ICON_MAP = {
    "bigbasket": "🛒",
    "myntra": "👗",
    "shein": "👠",
    "domino's": "🍕",
    "dominos": "🍕",
    "pvr": "🎬",
    "amazon": "📦",
    "flipkart": "🛍️",
    "swiggy": "🍔",
    "zomato": "🍕",
    "uber": "🚕",
    "ola": "🚕",
    "paytm": "💳",
    "phonepe": "💳",
    "gpay": "💳",
    "google play": "🎮",
    "playstore": "🎮",
    "jio": "📱",
    "airtel": "📱",
    "vi": "📱",
    "netflix": "🍿",
    "spotify": "🎵",
    "ajio": "👗",
    "nykaa": "💄",
    "blinkit": "⚡",
    "zepto": "⚡",
    "starbucks": "☕",
    "mcdonalds": "🍔",
    "kfc": "🍗",
}


def get_brand_icon(brand_name: str) -> str:
    """Return icon/emoji for a brand or extract leading emoji if present."""
    if not brand_name:
        return "🎁"
    clean = brand_name.strip()
    if len(clean) > 0 and ord(clean[0]) > 127:
        return clean.split()[0]
    return BRAND_ICON_MAP.get(clean.lower(), "🎁")


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


def format_coupon_stock_overview(coupon_stocks: List[Any]) -> str:
    """Format coupon inventory stock overview showing coupon name and available count."""
    if not coupon_stocks:
        return "📦 <b>Coupon Stock</b>\n\nNo active coupons currently available."

    lines = ["📦 <b>Coupon Stock</b>\n"]
    for coupon, stock in coupon_stocks:
        indicator = "🟢" if stock > 0 else "🔴"
        title = escape(coupon.title)
        available_count = max(0, stock)
        lines.append(f"{indicator} {title} — {available_count} available")

    return "\n".join(lines)


def format_coupon_detail(coupon: Coupon, available_stock: int = 0, user_points: int = 0) -> str:
    """Format clean, short, and premium coupon details."""
    title = escape(coupon.title)
    desc = escape(coupon.description) if coupon.description else ""

    msg = f"🎟 <b>{title}</b>\n\n"
    if desc:
        msg += f"📝 {desc}\n\n"
    msg += f"⭐ <b>Redeem:</b> {coupon.points_required} Points"
    return msg


def format_redeem_confirm_prompt(coupon: Coupon, user_points: int = 0) -> str:
    """Format confirmation prompt before coupon redemption."""
    title = escape(coupon.title)
    return (
        f"🎟️ <b>Redeem {title}?</b>\n\n"
        f"⭐ {coupon.points_required} Points will be deducted."
    )


def format_redemption_success(
    coupon_title: str,
    code: str,
    points_used: int,
    remaining_points: int,
    expiry_date: Optional[datetime] = None,
    terms: str = "",
) -> str:
    """Format successful redemption card."""
    return (
        "✅ <b>Coupon Redeemed</b>\n\n"
        f"🎟 <b>{escape(coupon_title)}</b>\n\n"
        "🎫 <b>Your Code:</b>\n"
        f"<code>{escape(code)}</code>\n\n"
        f"⭐ <b>Points Used:</b> {points_used}\n"
        f"⭐ <b>Balance:</b> {remaining_points}"
    )


def format_insufficient_points(required: int, balance: int) -> str:
    """Format insufficient points prompt."""
    return (
        "⭐ <b>Not Enough Points</b>\n\n"
        f"You need <b>{required}</b> ⭐ Points.\n"
        f"Your balance: <b>{balance}</b> ⭐\n\n"
        "🔗 Refer friends to earn more Points."
    )


# =========================================================================
# 4. BALANCE, REFER & EARN, PROFILE
# =========================================================================

def format_balance_card(
    balance: int,
    referrals: int,
    redeemed: int,
) -> str:
    """Format compact, clean balance summary card."""
    return (
        "💰 <b>Your Balance</b>\n\n"
        f"⭐ Points: <b>{balance}</b>\n"
        f"🚀 Successful Referrals: <b>{referrals}</b>\n"
        f"🎟️ Coupons Redeemed: <b>{redeemed}</b>"
    )


def format_points_card(
    current_points: int,
    successful_referrals: int,
    total_earned: int,
    total_spent: int,
) -> str:
    """Format legacy points card."""
    return format_balance_card(balance=current_points, referrals=successful_referrals, redeemed=0)


def format_refer_earn(
    referral_link: str,
    successful_referrals: int = 0,
    points_earned: int = 0,
    pending_referrals: int = 0,
    current_points: int = 0,
) -> str:
    """Format clean refer & earn card."""
    return (
        "🔗 <b>Refer & Earn</b>\n\n"
        "Earn <b>1 ⭐ Point</b> for every successful referral.\n\n"
        "Your referral link:\n"
        f"<code>{referral_link}</code>\n\n"
        "🚀 Share your link with friends and earn Points."
    )


# =========================================================================
# 5. SUPPORT, HELP, TERMS & PRIVACY
# =========================================================================

def format_support_prompt() -> str:
    """Format support entry prompt."""
    return (
        "🆘 <b>Support</b>\n\n"
        "Need help? Send your message below and our support team will review it."
    )


def format_support_sent() -> str:
    """Format support message submitted confirmation."""
    return (
        "✅ <b>Message Sent</b>\n\n"
        "Your message has been forwarded to support."
    )


def format_help_message() -> str:
    """Format concise help message."""
    return (
        "🆘 <b>Help & Overview</b>\n\n"
        "• <b>Points:</b> Earn 1 ⭐ per successful referral.\n"
        "• <b>Coupons:</b> Redeem active vouchers instantly.\n"
        "• <b>Support:</b> Contact our team anytime via 🆘 Support."
    )


def format_privacy_message() -> str:
    """Format structured, clean privacy statement."""
    return (
        "🔐 <b>Privacy Policy</b>\n\n"
        "We collect only minimal data to provide coupon and referral services:\n\n"
        "• <b>Account Info:</b> Telegram user ID and username\n"
        "• <b>Activity:</b> Referral links and reward completion\n"
        "• <b>Redemptions:</b> Voucher claims and points ledger\n\n"
        "We never sell personal data to third parties."
    )


def format_terms_message() -> str:
    """Format structured, clean terms & conditions."""
    return (
        "📄 <b>Terms of Service</b>\n\n"
        "• <b>Points:</b> Awarded upon verified channel join by referrals.\n"
        "• <b>Coupons:</b> Subject to stock availability and brand conditions.\n"
        "• <b>Codes:</b> Unique codes must be saved upon redemption.\n"
        "• <b>Fair Use:</b> Abuse or fake referrals lead to account ban."
    )


# =========================================================================
# 6. ADMIN DASHBOARD & DIAGNOSTICS
# =========================================================================

def format_admin_dashboard(stats: dict) -> str:
    """Format concise admin panel overview."""
    return (
        "🛠️ <b>Admin Dashboard</b>\n\n"
        f"📊 Users: <b>{stats.get('total_users', 0)}</b>\n"
        f"🎁 Active Coupons: <b>{stats.get('active_coupons', 0)}</b>\n"
        f"📦 Total Stock: <b>{stats.get('total_stock', 0)}</b>\n"
        f"📢 Required Channels: <b>{stats.get('required_channels', 0)}</b>\n"
        f"⭐ Points Issued: <b>{stats.get('total_points_issued', 0)}</b>\n"
        f"🎟️ Redemptions: <b>{stats.get('total_redemptions', 0)}</b>\n"
        f"🚀 Pending Referrals: <b>{stats.get('pending_referrals', 0)}</b>"
    )


def format_channel_diagnostic_error(channel_name_or_id: str, error_detail: Optional[str] = None) -> str:
    """Format diagnostic message for admin without dumping raw tracebacks."""
    return (
        "⚠️ <b>Channel verification setup problem</b>\n\n"
        f"<b>Channel:</b> {escape(str(channel_name_or_id))}\n\n"
        "• Bot is not added to the channel\n"
        "• Bot does not have required permissions\n"
        "• Channel ID/username is incorrect"
    )


# =========================================================================
# 7. SAFE MESSAGE EDITING UTILITY (DUPLICATE PROTECTION)
# =========================================================================

async def safe_edit_message(
    event: Any,
    text: str,
    reply_markup: Optional[Any] = None,
    parse_mode: str = "HTML",
) -> None:
    """Safely edit an existing message or answer if not editable, ignoring benign duplicate errors."""
    if not event:
        return

    is_callback = False
    if hasattr(event, "data") and getattr(event, "data", None) is not None:
        is_callback = True
    elif hasattr(event, "message") and getattr(event, "message", None) is not None and getattr(event, "text", None) is None and getattr(event, "caption", None) is None:
        is_callback = True

    if not is_callback:
        if hasattr(event, "answer"):
            await event.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
        return

    msg = getattr(event, "message", None)
    if not msg:
        return

    try:
        await msg.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception as e:
        err_str = str(e).lower()
        if "message is not modified" in err_str or "message to edit not found" in err_str:
            return  # Benign: exact same content already displayed. Do NOT send duplicate message!
        try:
            await msg.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
        except Exception:
            pass
