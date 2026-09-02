"""Comprehensive anti-fraud device binding, WebApp validation, and referral protection tests."""

import asyncio
import hashlib
import hmac
import json
import time
import urllib.parse
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from config import settings
from models.user import User
from models.device_binding import DeviceBinding, DeviceBindingStatus
from models.referral import Referral, ReferralStatus
from models.point_transaction import PointTransaction, TransactionType
from services.user_service import UserService
from services.device_service import DeviceService
from services.referral_service import ReferralService
from services.channel_service import ChannelService
from utils.security import (
    hash_device_fingerprint,
    validate_telegram_webapp_init_data,
)


@pytest.mark.asyncio
async def test_new_user_new_device_success(db_session: AsyncSession):
    """Case 1: User A on new device binds successfully."""
    user_id = 10001
    fp = {
        "device_id": "9f8a8b8c-1234-5678-90ab-cdef12345678",
        "screen": "1920x1080",
        "timezone": "Asia/Kolkata",
        "language": "en-US",
        "platform": "Win32",
    }

    success, code, binding = await DeviceService.verify_and_bind_device(
        session=db_session,
        telegram_user_id=user_id,
        fingerprint_payload=fp,
    )
    await db_session.commit()

    assert success is True
    assert code == "DEVICE_BOUND_NEW"
    assert binding is not None
    assert binding.telegram_user_id == user_id
    assert binding.status == DeviceBindingStatus.ACTIVE
    assert await DeviceService.is_device_verified(db_session, user_id) is True


@pytest.mark.asyncio
async def test_same_user_same_device_allowed(db_session: AsyncSession):
    """Case 2: Same user returning on previously registered device is allowed."""
    user_id = 15001
    fp = {"device_id": "inst_device_15001_abc"}

    # 1. First binding -> Success
    s1, c1, _ = await DeviceService.verify_and_bind_device(db_session, user_id, fp)
    await db_session.commit()
    assert s1 is True
    assert c1 == "DEVICE_BOUND_NEW"

    # 2. Returning on same device -> Success
    s2, c2, binding2 = await DeviceService.verify_and_bind_device(db_session, user_id, fp)
    await db_session.commit()
    assert s2 is True
    assert c2 == "DEVICE_VERIFIED_EXISTING"
    assert binding2.telegram_user_id == user_id


@pytest.mark.asyncio
async def test_same_user_different_device_rejected(db_session: AsyncSession):
    """Case 3: Same user attempting verification from a SECOND device is rejected."""
    user_id = 16001
    fp_device_1 = {"device_id": "inst_phone_user_16001"}
    fp_device_2 = {"device_id": "inst_laptop_user_16001"}

    # 1. User registers on Device 1
    s1, c1, _ = await DeviceService.verify_and_bind_device(db_session, user_id, fp_device_1)
    await db_session.commit()
    assert s1 is True

    # 2. Same user tries to register from Device 2 -> Rejected
    s2, c2, b2 = await DeviceService.verify_and_bind_device(db_session, user_id, fp_device_2)
    await db_session.commit()
    assert s2 is False
    assert c2 == "USER_ALREADY_BOUND_TO_ANOTHER_DEVICE"
    assert b2.telegram_user_id == user_id


@pytest.mark.asyncio
async def test_same_device_different_user_blocked(db_session: AsyncSession):
    """Case 4: User B on previously verified device is blocked from binding."""
    user_a = 20001
    user_b = 20002

    fp = {
        "device_id": "shared_device_id_20001",
        "screen": "1080x2400",
        "timezone": "Asia/Kolkata",
        "language": "hi-IN",
        "platform": "Android",
    }

    # 1. User A binds device
    s_a, _, _ = await DeviceService.verify_and_bind_device(
        session=db_session,
        telegram_user_id=user_a,
        fingerprint_payload=fp,
    )
    await db_session.commit()
    assert s_a is True

    # 2. User B tries to use the same device
    s_b, code_b, binding_b = await DeviceService.verify_and_bind_device(
        session=db_session,
        telegram_user_id=user_b,
        fingerprint_payload=fp,
    )
    await db_session.commit()

    assert s_b is False
    assert code_b == "DEVICE_ALREADY_BOUND"
    assert binding_b.telegram_user_id == user_a  # Still belongs to User A
    assert await DeviceService.is_device_verified(db_session, user_b) is False


@pytest.mark.asyncio
async def test_different_device_different_user_allowed(db_session: AsyncSession):
    """Case 5: User B on different device is allowed."""
    user_a = 30001
    user_b = 30002

    fp_a = {"device_id": "dev_30001_a"}
    fp_b = {"device_id": "dev_30002_b"}

    s_a, _, _ = await DeviceService.verify_and_bind_device(db_session, user_a, fp_a)
    s_b, _, _ = await DeviceService.verify_and_bind_device(db_session, user_b, fp_b)
    await db_session.commit()

    assert s_a is True
    assert s_b is True
    assert await DeviceService.is_device_verified(db_session, user_a) is True
    assert await DeviceService.is_device_verified(db_session, user_b) is True


@pytest.mark.asyncio
async def test_referral_reward_held_until_device_verified(db_session: AsyncSession, mock_bot):
    """Referral cannot be completed if referred user has not bound device."""
    # Referrer
    ref_user, _, _ = await UserService.get_or_create_user(db_session, telegram_id=40001, first_name="Referrer")
    await db_session.commit()

    # Referred friend
    friend, _, pending = await UserService.get_or_create_user(
        db_session,
        telegram_id=40002,
        first_name="Friend",
        referral_param=f"ref_{ref_user.referral_code}",
    )
    await db_session.commit()
    assert pending.status == ReferralStatus.PENDING

    # Attempt referral completion WITHOUT device binding -> Held / returns False
    res, _, _ = await ReferralService.process_referral_completion(db_session, friend.id, mock_bot)
    assert res is False

    # Check referrer balance still 0
    ref_check = await UserService.get_user_by_id(db_session, ref_user.id)
    assert ref_check.points == 0

    # Now friend completes device verification
    await DeviceService.verify_and_bind_device(
        db_session,
        friend.telegram_id,
        {"device_id": "friend_dev_40002"},
    )
    await db_session.commit()

    # Now referral completion succeeds
    res_ok, _, pts = await ReferralService.process_referral_completion(db_session, friend.id, mock_bot)
    await db_session.commit()
    assert res_ok is True
    assert pts == 1

    ref_check_after = await UserService.get_user_by_id(db_session, ref_user.id)
    assert ref_check_after.points == 1


@pytest.mark.asyncio
async def test_admin_device_release_and_rebind(db_session: AsyncSession):
    """Admin manually releases device binding, allowing legitimate re-binding."""
    user_a = 50001
    user_b = 50002
    fp = {"device_id": "released_dev_50001"}

    # User A binds device
    await DeviceService.verify_and_bind_device(db_session, user_a, fp)
    await db_session.commit()

    # User B blocked
    s_b1, _, _ = await DeviceService.verify_and_bind_device(db_session, user_b, fp)
    assert s_b1 is False

    # Admin releases device binding for User A
    rel_ok, rel_msg = await DeviceService.release_device_binding(db_session, admin_id=999, telegram_user_id=user_a)
    await db_session.commit()
    assert rel_ok is True

    # User B can now bind this device
    s_b2, code_b2, binding = await DeviceService.verify_and_bind_device(db_session, user_b, fp)
    await db_session.commit()
    assert s_b2 is True
    assert code_b2 == "DEVICE_REBOUND"
    assert binding.telegram_user_id == user_b
    assert binding.status == DeviceBindingStatus.ACTIVE


@pytest.mark.asyncio
async def test_webapp_init_data_hmac_validation():
    """Test cryptographic verification of Telegram WebApp initData string."""
    bot_token = "123456789:ABCDefGhIjKlMnOpQrStUvWxYz"

    # Build genuine initData payload with fresh timestamp
    user_payload = {"id": 60001, "first_name": "TestUser", "username": "testuser"}
    user_json = json.dumps(user_payload, separators=(",", ":"))
    auth_date = str(int(time.time()))
    query_id = "AAHdF6IQAAAAAN0XohD34"

    data_pairs = [
        f"auth_date={auth_date}",
        f"query_id={query_id}",
        f"user={user_json}",
    ]
    data_check_string = "\n".join(sorted(data_pairs))

    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    correct_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    init_data_str = f"auth_date={auth_date}&query_id={query_id}&user={urllib.parse.quote(user_json)}&hash={correct_hash}"

    # 1. Valid data
    result = validate_telegram_webapp_init_data(init_data_str, bot_token)
    assert result is not None
    assert result["user"]["id"] == 60001
    assert result["user"]["first_name"] == "TestUser"

    # 2. Tampered / forged hash
    tampered_str = init_data_str.replace(correct_hash, "deadbeef1234567890abcdefdeadbeef")
    result_tampered = validate_telegram_webapp_init_data(tampered_str, bot_token)
    assert result_tampered is None

    # 3. Missing hash
    result_missing = validate_telegram_webapp_init_data("auth_date=1700000000&user=abc", bot_token)
    assert result_missing is None


@pytest.mark.asyncio
async def test_webapp_init_data_expiration():
    """Test that stale/expired initData query string is rejected."""
    bot_token = "123456789:ABCDefGhIjKlMnOpQrStUvWxYz"

    # 48 hours old auth_date
    expired_auth_date = str(int(time.time()) - 172800)
    user_payload = {"id": 60002, "first_name": "OldUser"}
    user_json = json.dumps(user_payload, separators=(",", ":"))

    data_pairs = [
        f"auth_date={expired_auth_date}",
        f"user={user_json}",
    ]
    data_check_string = "\n".join(sorted(data_pairs))

    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    correct_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    expired_init_data = f"auth_date={expired_auth_date}&user={urllib.parse.quote(user_json)}&hash={correct_hash}"

    # Verify that validation fails due to expiration
    res = validate_telegram_webapp_init_data(expired_init_data, bot_token, max_age_seconds=86400)
    assert res is None


@pytest.mark.asyncio
async def test_privacy_preserving_fingerprint_hashing():
    """Verify that fingerprint hashing strips volatile fields and yields deterministic 64-char SHA-256."""
    fp_1 = {
        "screen": "1920x1080",
        "timezone": "Asia/Kolkata",
        "language": "en",
        "platform": "Win32",
        "timestamp": "12345",
        "ip": "1.2.3.4",
    }
    fp_2 = {
        "screen": "1920x1080",
        "timezone": "Asia/Kolkata",
        "language": "en",
        "platform": "Win32",
        "timestamp": "99999",
        "ip": "5.6.7.8",
    }

    hash_1 = hash_device_fingerprint(fp_1)
    hash_2 = hash_device_fingerprint(fp_2)

    assert len(hash_1) == 64
    assert hash_1 == hash_2


@pytest.mark.asyncio
async def test_channels_verified_then_device_verification_flow(db_session: AsyncSession, mock_bot):
    """E2E flow: User joins 4 channels -> clicks verify -> gets 'Verify Device' WebApp button -> completes Mini App -> referral released."""
    from unittest.mock import AsyncMock, MagicMock
    from aiogram.types import CallbackQuery, Message, User as TgUser, WebAppData
    from aiogram.enums import ChatMemberStatus
    from handlers.channels import handle_channel_verification
    from handlers.device import handle_webapp_verification_data

    # 1. Setup channels
    for ch in ["@OfferRaider", "@OfferMate", "@Grabmint", "@offerelite"]:
        await ChannelService.add_channel(db_session, 123, ch, ch.lstrip("@"), f"https://t.me/{ch.lstrip('@')}", ch.lstrip("@"))
    await db_session.commit()

    class MemberJoined:
        status = ChatMemberStatus.MEMBER

    mock_bot.get_chat_member.return_value = MemberJoined()

    # 2. Setup Referrer and Referred User
    referrer, _, _ = await UserService.get_or_create_user(db_session, telegram_id=90001, first_name="Referrer")
    referred_friend, _, _ = await UserService.get_or_create_user(
        db_session,
        telegram_id=90002,
        first_name="ReferredFriend",
        referral_param=f"ref_{referrer.referral_code}",
    )
    await db_session.commit()

    # 3. Friend joins channels and taps 'Verify Membership'
    mock_cb = MagicMock(spec=CallbackQuery)
    mock_cb.from_user = MagicMock(spec=TgUser)
    mock_cb.from_user.id = 90002
    mock_cb.from_user.first_name = "ReferredFriend"
    mock_cb.from_user.last_name = None
    mock_cb.from_user.username = "friend_90002"
    mock_cb.answer = AsyncMock()
    mock_cb.message = MagicMock(spec=Message)
    mock_cb.message.edit_text = AsyncMock()

    await handle_channel_verification(mock_cb, db_session, is_admin=False, bot=mock_bot)
    await db_session.commit()

    # Verify: Safe edit message was called with device verification prompt & keyboard
    mock_cb.message.edit_text.assert_called_once()
    edited_text = mock_cb.message.edit_text.call_args[0][0]
    edited_kb = mock_cb.message.edit_text.call_args[1].get("reply_markup")

    assert "Device Verification" in edited_text
    # Verify button exists in keyboard
    kb_btn_texts = [b.text for row in edited_kb.inline_keyboard for b in row]
    assert any("Verify Device" in b for b in kb_btn_texts)

    # Verify: Referrer reward is still 0 (held)
    ref_db = await UserService.get_user_by_id(db_session, referrer.id)
    assert ref_db.points == 0

    # 4. Now Friend completes Mini App verification (submits web_app_data)
    mock_msg = MagicMock(spec=Message)
    mock_msg.from_user = mock_cb.from_user
    mock_msg.web_app_data = MagicMock(spec=WebAppData)
    mock_msg.web_app_data.data = json.dumps({
        "fingerprint": {"device_id": "friend_unique_phone_90002"},
    })
    mock_msg.answer = AsyncMock()

    await handle_webapp_verification_data(mock_msg, db_session, is_admin=False, bot=mock_bot)
    await db_session.commit()

    # Verify: Friend is now device verified and referral reward (+1) is credited to referrer
    assert await DeviceService.is_device_verified(db_session, 90002) is True
    ref_db_after = await UserService.get_user_by_id(db_session, referrer.id)
    assert ref_db_after.points == 1


@pytest.mark.asyncio
async def test_device_verification_failure_cases(db_session: AsyncSession, mock_bot):
    """Test failure cases: missing channels blocks device step, and duplicate device blocks verification."""
    from unittest.mock import AsyncMock, MagicMock
    from aiogram.types import CallbackQuery, Message, User as TgUser, WebAppData
    from aiogram.enums import ChatMemberStatus
    from handlers.channels import handle_channel_verification
    from handlers.device import handle_webapp_verification_data

    # Seed 4 channels
    for ch in ["@OfferRaider", "@OfferMate", "@Grabmint", "@offerelite"]:
        await ChannelService.add_channel(db_session, 123, ch, ch.lstrip("@"), f"https://t.me/{ch.lstrip('@')}", ch.lstrip("@"))
    await db_session.commit()

    # Case A: User has NOT joined channels -> shows missing channels prompt, not device prompt
    class MemberLeft:
        status = ChatMemberStatus.LEFT

    mock_bot.get_chat_member.return_value = MemberLeft()

    mock_cb = MagicMock(spec=CallbackQuery)
    mock_cb.from_user = MagicMock(spec=TgUser)
    mock_cb.from_user.id = 91001
    mock_cb.from_user.first_name = "MissingChanUser"
    mock_cb.from_user.last_name = None
    mock_cb.from_user.username = "user_91001"
    mock_cb.answer = AsyncMock()
    mock_cb.message = MagicMock(spec=Message)
    mock_cb.message.edit_text = AsyncMock()

    await handle_channel_verification(mock_cb, db_session, is_admin=False, bot=mock_bot)
    mock_cb.message.edit_text.assert_called_once()
    edited_text = mock_cb.message.edit_text.call_args[0][0]
    assert "Almost there!" in edited_text or "You still need to join" in edited_text
    assert "Device Verification" not in edited_text

    # Case B: User attempts verification on a device already bound to another user
    existing_user_id = 91002
    fraud_user_id = 91003
    shared_fp = {"device_id": "exclusive_device_token_xyz"}

    # Existing user binds device
    s1, _, _ = await DeviceService.verify_and_bind_device(db_session, existing_user_id, shared_fp)
    await db_session.commit()
    assert s1 is True

    # Fraud user submits same device via web_app_data
    mock_msg_fraud = MagicMock(spec=Message)
    mock_msg_fraud.from_user = MagicMock(spec=TgUser)
    mock_msg_fraud.from_user.id = fraud_user_id
    mock_msg_fraud.web_app_data = MagicMock(spec=WebAppData)
    mock_msg_fraud.web_app_data.data = json.dumps({"fingerprint": shared_fp})
    mock_msg_fraud.answer = AsyncMock()

    await handle_webapp_verification_data(mock_msg_fraud, db_session, is_admin=False, bot=mock_bot)
    await db_session.commit()

    mock_msg_fraud.answer.assert_called_once()
    fraud_out = mock_msg_fraud.answer.call_args[0][0]
    assert "Verification unavailable" in fraud_out or "already been used" in fraud_out
    assert await DeviceService.is_device_verified(db_session, fraud_user_id) is False
