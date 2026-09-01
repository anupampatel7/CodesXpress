"""Tests for aiohttp WebApp server, HTTP routes, Telegram initData verification, and device binding."""

import hashlib
import hmac
import json
import urllib.parse
import pytest
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop, TestClient, TestServer
from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncSession
from config import settings
from services.webapp_server import create_webapp_application
from models.device_binding import DeviceBinding, DeviceBindingStatus
from database import async_session_factory


def generate_test_init_data(bot_token: str, user_id: int, first_name: str = "Test") -> str:
    """Helper to generate authentic HMAC-SHA256 initData string."""
    user_payload = {"id": user_id, "first_name": first_name, "username": f"user_{user_id}"}
    user_json = json.dumps(user_payload, separators=(",", ":"))
    auth_date = "1700000000"
    query_id = "AAHdF6IQAAAAAN0XohD34"

    data_pairs = [
        f"auth_date={auth_date}",
        f"query_id={query_id}",
        f"user={user_json}",
    ]
    data_check_string = "\n".join(sorted(data_pairs))

    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    correct_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    return f"auth_date={auth_date}&query_id={query_id}&user={urllib.parse.quote(user_json)}&hash={correct_hash}"


@pytest.mark.asyncio
async def test_webapp_get_verify_route():
    """Verify that GET /verify returns 200 OK and HTML document."""
    app = create_webapp_application()
    client = TestClient(TestServer(app))
    await client.start_server()

    try:
        resp = await client.get("/verify")
        assert resp.status == 200
        text = await resp.text()
        assert "Codes Xpress" in text
        assert "Telegram" in text
        assert "Verify" in text
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_webapp_health_route():
    """Verify that GET /health returns status ok."""
    app = create_webapp_application()
    client = TestClient(TestServer(app))
    await client.start_server()

    try:
        resp = await client.get("/health")
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "ok"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_webapp_post_verify_missing_and_invalid_init_data():
    """Verify that POST /api/verify-device rejects missing and forged initData."""
    app = create_webapp_application()
    client = TestClient(TestServer(app))
    await client.start_server()

    try:
        # 1. Missing initData
        resp1 = await client.post("/api/verify-device", json={"init_data": ""})
        assert resp1.status == 401
        data1 = await resp1.json()
        assert data1["code"] == "MISSING_INIT_DATA"

        # 2. Forged initData
        resp2 = await client.post("/api/verify-device", json={"init_data": "auth_date=123&user=fake&hash=deadbeef"})
        assert resp2.status == 401
        data2 = await resp2.json()
        assert data2["code"] == "UNAUTHORIZED"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_webapp_post_verify_genuine_device_binding(db_session: AsyncSession):
    """Verify authentic WebApp request binds device and rejects second user on same device."""
    app = create_webapp_application()
    client = TestClient(TestServer(app))
    await client.start_server()

    user_a_id = 70001
    user_b_id = 70002
    init_data_a = generate_test_init_data(settings.BOT_TOKEN, user_a_id, "UserA")
    init_data_b = generate_test_init_data(settings.BOT_TOKEN, user_b_id, "UserB")

    fp = {
        "screen": "1080x2400@2.75",
        "timezone": "Asia/Kolkata",
        "language": "hi-IN",
        "platform": "Android",
        "canvas": "sample_canvas_hash_12345",
    }

    try:
        # 1. User A binds device -> Success 200
        resp_a = await client.post("/api/verify-device", json={"init_data": init_data_a, "fingerprint": fp})
        assert resp_a.status == 200
        data_a = await resp_a.json()
        assert data_a["success"] is True

        # 2. User A repeats on same device -> Success 200 (Already bound/verified)
        resp_a_repeat = await client.post("/api/verify-device", json={"init_data": init_data_a, "fingerprint": fp})
        assert resp_a_repeat.status == 200
        data_a_rep = await resp_a_repeat.json()
        assert data_a_rep["success"] is True

        # 3. User B tries to use User A's device -> 403 Forbidden (DEVICE_ALREADY_BOUND)
        resp_b = await client.post("/api/verify-device", json={"init_data": init_data_b, "fingerprint": fp})
        assert resp_b.status == 403
        data_b = await resp_b.json()
        assert data_b["success"] is False
        assert data_b["code"] == "DEVICE_ALREADY_BOUND"
    finally:
        await client.close()


def test_health_and_dynamic_port_configuration(monkeypatch):
    """Verify that settings correctly parses Render's dynamic PORT environment variable."""
    from config import Settings

    # Case 1: Default when PORT is not set
    s_default = Settings(BOT_TOKEN="123:abc", ADMIN_ID=1)
    assert s_default.server_port == 8080

    # Case 2: Render supplies PORT=10000
    monkeypatch.setenv("PORT", "10000")
    s_render = Settings(BOT_TOKEN="123:abc", ADMIN_ID=1)
    assert s_render.server_port == 10000

    # Case 3: Explicit PORT parameter passed
    s_custom = Settings(BOT_TOKEN="123:abc", ADMIN_ID=1, PORT=9090)
    assert s_custom.server_port == 9090

