"""Input and business entity validation utilities."""

from typing import Optional, Tuple
from datetime import datetime, timezone
import re


def validate_positive_int(value: str) -> Optional[int]:
    """Validate that input string is a positive non-zero integer."""
    try:
        val = int(value.strip())
        return val if val > 0 else None
    except (ValueError, AttributeError):
        return None


def validate_non_negative_int(value: str) -> Optional[int]:
    """Validate that input string is a non-negative integer (>= 0)."""
    try:
        val = int(value.strip())
        return val if val >= 0 else None
    except (ValueError, AttributeError):
        return None


def validate_channel_id(value: str) -> Optional[str]:
    """Validate Telegram channel ID (e.g. -1001234567890 or @channelname)."""
    val = value.strip()
    if not val:
        return None
    # Check if standard username format
    if val.startswith("@") and len(val) >= 4 and re.match(r"^@[a-zA-Z0-9_]{3,}$", val):
        return val
    # Check if numeric chat ID
    if val.startswith("-100") and val[1:].isdigit():
        return val
    if val.isdigit() or (val.startswith("-") and val[1:].isdigit()):
        return val
    return None


def validate_date(value: str) -> Optional[datetime]:
    """Validate and parse date string in YYYY-MM-DD or YYYY-MM-DD HH:MM format."""
    val = value.strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            dt = datetime.strptime(val, fmt)
            # Make UTC timezone aware
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def sanitize_coupon_code(code: str) -> str:
    """Sanitize coupon code string removing harmful whitespace and symbols."""
    return code.strip().upper()


def parse_bulk_codes(raw_text: str) -> Tuple[list[str], int]:
    """Parse multiple coupon codes from newline-separated text.

    - Splits only by newline.
    - Trims leading/trailing whitespace per line.
    - Ignores empty lines.
    - Preserves exact code text.
    - Deduplicates safely.

    Returns:
        Tuple of (valid_unique_codes_list, total_raw_count)
    """
    lines = raw_text.splitlines()
    unique_codes: list[str] = []
    seen: set[str] = set()
    total_raw = 0

    for line in lines:
        cleaned = line.strip()
        if not cleaned:
            continue
        total_raw += 1
        key = cleaned.upper()
        if key not in seen:
            seen.add(key)
            unique_codes.append(cleaned)

    return unique_codes, total_raw
