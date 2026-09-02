"""Security, authorization, cryptography, and sanitization utilities."""

import hashlib
import hmac
import json
import secrets
import string
import urllib.parse
from typing import Optional, Any, Dict
from config import settings


def generate_referral_code(length: int = 8) -> str:
    """Generate a cryptographically safe alphanumeric referral code."""
    chars = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(chars) for _ in range(length))


def is_admin_user(telegram_id: int) -> bool:
    """Check if the given Telegram ID belongs to a configured admin."""
    return settings.is_admin(telegram_id)


def mask_secret(secret: Optional[str], visible_chars: int = 4) -> str:
    """Mask sensitive string (tokens, keys, etc.) for safe logging."""
    if not secret:
        return "<empty>"
    if len(secret) <= visible_chars * 2:
        return "*" * len(secret)
    return f"{secret[:visible_chars]}...{secret[-visible_chars:]}"


import time


def hash_device_fingerprint(fingerprint_data: Any) -> str:
    """Compute deterministic, privacy-preserving SHA-256 hash of device attributes.

    If a cryptographically random persistent device installation ID is provided,
    it is bound directly. Otherwise, stable browser hardware and canvas entropy are used.
    """
    if isinstance(fingerprint_data, dict):
        device_id = str(fingerprint_data.get("device_id", "")).strip()
        if device_id:
            serialized = f"dev_id:{device_id}"
        else:
            # Pick stable canonical features
            canonical = {
                "screen": str(fingerprint_data.get("screen", "")).strip(),
                "timezone": str(fingerprint_data.get("timezone", "")).strip(),
                "language": str(fingerprint_data.get("language", "")).strip(),
                "platform": str(fingerprint_data.get("platform", "")).strip(),
                "hardware_concurrency": str(fingerprint_data.get("hardware_concurrency", "")).strip(),
                "canvas": str(fingerprint_data.get("canvas", "")).strip(),
                "webgl": str(fingerprint_data.get("webgl", "")).strip(),
                "audio": str(fingerprint_data.get("audio", "")).strip(),
            }
            # If standard keys missing, use sorted items
            if not any(canonical.values()):
                filtered = {k: str(v).strip() for k, v in fingerprint_data.items() if k not in ("ip", "time", "timestamp", "auth_date")}
                serialized = json.dumps(filtered, sort_keys=True, separators=(",", ":"))
            else:
                serialized = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    elif isinstance(fingerprint_data, str):
        serialized = fingerprint_data.strip()
    else:
        serialized = str(fingerprint_data).strip()

    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def validate_telegram_webapp_init_data(
    init_data: str,
    bot_token: str,
    max_age_seconds: Optional[int] = 86400,
) -> Optional[Dict[str, Any]]:
    """Validate Telegram WebApp initData query string using HMAC-SHA256 and expiration check.

    Reference: https://core.telegram.org/bots/webapps#validating-data-received-via-the-web-app
    """
    if not init_data or not bot_token:
        return None

    try:
        parsed = urllib.parse.parse_qs(init_data, keep_blank_values=True)
        if "hash" not in parsed:
            return None

        received_hash = parsed["hash"][0]

        # Build data-check-string (all keys except hash sorted alphabetically)
        data_pairs = []
        for key in sorted(parsed.keys()):
            if key != "hash":
                val = parsed[key][0]
                data_pairs.append(f"{key}={val}")

        data_check_string = "\n".join(data_pairs)

        # secret_key = HMAC_SHA256("WebAppData", bot_token)
        secret_key = hmac.new(
            b"WebAppData",
            bot_token.encode("utf-8"),
            hashlib.sha256,
        ).digest()

        # calculated_hash = HMAC_SHA256(secret_key, data_check_string)
        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        if hmac.compare_digest(calculated_hash, received_hash):
            auth_date_raw = parsed.get("auth_date", [None])[0]
            if max_age_seconds is not None and auth_date_raw:
                try:
                    auth_timestamp = int(auth_date_raw)
                    current_timestamp = int(time.time())
                    # Check if expired or clock skewed into future > 5 minutes
                    if current_timestamp - auth_timestamp > max_age_seconds or auth_timestamp - current_timestamp > 300:
                        return None
                except (ValueError, TypeError):
                    return None

            user_json_str = parsed.get("user", [None])[0]
            result = {
                "auth_date": auth_date_raw,
                "query_id": parsed.get("query_id", [None])[0],
            }
            if user_json_str:
                result["user"] = json.loads(user_json_str)
            return result
        return None
    except Exception:
        return None
