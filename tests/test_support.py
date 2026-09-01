"""Tests for Support System and Admin-User Support Routing."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage, StorageKey
from sqlalchemy.ext.asyncio import AsyncSession
from config import settings
from keyboards.user import (
    get_main_menu_keyboard,
    get_support_cancel_keyboard,
    get_support_admin_keyboard,
    SupportReplyCallback,
)
from handlers.support import (
    handle_support_start,
    handle_support_cancel,
    handle_user_support_message,
    handle_admin_reply_click,
    handle_admin_send_reply,
    UserSupportState,
    AdminSupportReplyState,
)
from models.user import User


class MockTgUser:
    def __init__(self, id: int, first_name: str = "Test", username: str = None, last_name: str = None):
        self.id = id
        self.first_name = first_name
        self.username = username
        self.last_name = last_name


@pytest.fixture
def fsm_storage():
    return MemoryStorage()


def make_fsm_context(storage, bot_id=123, chat_id=1001, user_id=1001):
    key = StorageKey(bot_id=bot_id, chat_id=chat_id, user_id=user_id)
    return FSMContext(storage=storage, key=key)


def test_main_menu_keyboard_has_support_and_no_help():
    """Verify that main menu has 🆘 Support and ℹ️ Help is removed."""
    kb = get_main_menu_keyboard(is_admin=False)
    button_texts = [btn.text for row in kb.inline_keyboard for btn in row]
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]

    assert "🆘 Support" in button_texts
    assert "menu_support" in callbacks
    assert "ℹ️ Help" not in button_texts
    assert "menu_help" not in callbacks


@pytest.mark.asyncio
async def test_user_opens_support(fsm_storage, mock_bot):
    """Test: User opens support -> enters UserSupportState.waiting_for_message."""
    state = make_fsm_context(fsm_storage, user_id=555111)

    message = MagicMock()
    del message.data
    message.from_user = MockTgUser(id=555111, first_name="Rohan", username="rohan_tg")
    message.text = "/support"
    message.answer = AsyncMock()

    await handle_support_start(message, state)

    current_state = await state.get_state()
    assert current_state == UserSupportState.waiting_for_message.state
    message.answer.assert_called_once()
    args, kwargs = message.answer.call_args
    assert "🆘 <b>Support</b>" in args[0]
    assert "reply_markup" in kwargs


@pytest.mark.asyncio
async def test_user_cancel_support(fsm_storage, db_session: AsyncSession):
    """Test: User clicks Cancel -> support state is cleared."""
    state = make_fsm_context(fsm_storage, user_id=555222)
    await state.set_state(UserSupportState.waiting_for_message)

    cb = MagicMock()
    cb.data = "support_cancel"
    cb.from_user = MockTgUser(id=555222, first_name="Pooja")
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()

    await handle_support_cancel(cb, state, db_session, is_admin=False)

    current_state = await state.get_state()
    assert current_state is None
    cb.answer.assert_called_with("Support cancelled.", show_alert=False)


@pytest.mark.asyncio
async def test_user_sends_text_forwarded_to_admin(fsm_storage, db_session: AsyncSession, mock_bot):
    """Test: User in Support state sends text -> delivered to ADMIN_ID with user details & reply button."""
    user_tg_id = 987654321
    state = make_fsm_context(fsm_storage, user_id=user_tg_id)
    await state.set_state(UserSupportState.waiting_for_message)

    message = MagicMock()
    message.from_user = MockTgUser(id=user_tg_id, first_name="Aarav", username="aarav_coder")
    message.text = "Coupon redemption issue on Swiggy coupon"
    message.photo = None
    message.document = None
    message.video = None
    message.caption = None
    message.answer = AsyncMock()

    await handle_user_support_message(
        message=message,
        state=state,
        session=db_session,
        is_admin=False,
        bot=mock_bot,
    )

    # 1. State should be cleared
    assert await state.get_state() is None

    # 2. Admin should receive formatted message
    mock_bot.send_message.assert_called_once()
    call_kwargs = mock_bot.send_message.call_args.kwargs
    assert call_kwargs["chat_id"] == settings.ADMIN_ID
    assert "Support Request" in call_kwargs["text"]
    assert "Aarav" in call_kwargs["text"]
    assert str(user_tg_id) in call_kwargs["text"]
    assert "@aarav_coder" in call_kwargs["text"]
    assert "Coupon redemption issue on Swiggy coupon" in call_kwargs["text"]

    # 3. User receives confirmation
    message.answer.assert_called_once()
    assert "Message Sent" in message.answer.call_args[0][0] or "Message sent" in message.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_admin_reply_flow_success(fsm_storage, mock_bot):
    """Test: Admin clicks Reply -> sets state -> Admin sends message -> User receives reply."""
    admin_tg_id = settings.ADMIN_ID
    user_target_id = 987654321
    admin_state = make_fsm_context(fsm_storage, user_id=admin_tg_id)

    # 1. Admin clicks Reply
    cb = MagicMock()
    cb.from_user = MockTgUser(id=admin_tg_id, first_name="Admin", username="admin_user")
    cb.message = MagicMock()
    cb.message.reply = AsyncMock()
    cb.answer = AsyncMock()

    cb_data = SupportReplyCallback(user_tg_id=user_target_id)
    await handle_admin_reply_click(cb, cb_data, admin_state, is_admin=True)

    assert await admin_state.get_state() == AdminSupportReplyState.waiting_for_reply.state
    data = await admin_state.get_data()
    assert data["target_user_id"] == user_target_id

    # 2. Admin sends reply text
    reply_msg = MagicMock()
    reply_msg.from_user = MockTgUser(id=admin_tg_id, first_name="Admin", username="admin_user")
    reply_msg.text = "Issue resolved! Please check your Swiggy coupon code now."
    reply_msg.photo = None
    reply_msg.caption = None
    reply_msg.answer = AsyncMock()

    await handle_admin_send_reply(reply_msg, admin_state, is_admin=True, bot=mock_bot)

    # 3. Admin state cleared
    assert await admin_state.get_state() is None

    # 4. Message sent to target user
    mock_bot.send_message.assert_called_once()
    user_call_kwargs = mock_bot.send_message.call_args.kwargs
    assert user_call_kwargs["chat_id"] == user_target_id
    assert "🆘 <b>Support</b>" in user_call_kwargs["text"]
    assert "<b>Admin:</b>" in user_call_kwargs["text"]
    assert "Issue resolved! Please check your Swiggy coupon code now." in user_call_kwargs["text"]

    # 5. Admin gets confirmation
    reply_msg.answer.assert_called_once()
    assert "Reply sent to user" in reply_msg.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_non_admin_cannot_use_reply_callback(fsm_storage):
    """Test: Normal user clicking admin Reply callback is rejected server-side."""
    normal_user_id = 11223344
    state = make_fsm_context(fsm_storage, user_id=normal_user_id)

    cb = MagicMock()
    cb.from_user = MockTgUser(id=normal_user_id, first_name="Intruder")
    cb.answer = AsyncMock()

    cb_data = SupportReplyCallback(user_tg_id=987654321)
    await handle_admin_reply_click(cb, cb_data, state, is_admin=False)

    # Must be rejected
    cb.answer.assert_called_with("❌ Unauthorized access.", show_alert=True)
    assert await state.get_state() is None
