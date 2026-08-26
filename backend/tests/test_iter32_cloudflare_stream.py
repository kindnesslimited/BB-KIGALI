"""Iter 32 backend tests — Cloudflare Stream integration + YouTube LIVE regression.

Coverage:
- GET /api/admin/cloudflare-stream/config (auth=admin) never leaks apiToken; reports hasApiToken + connected + connectedAt
- PUT /api/admin/cloudflare-stream/config: empty payload -> 400; valid payload upserts to db.integration_state.cloudflare_stream_config
- POST /api/admin/cloudflare-stream/live-input: 412 when not configured; 502 when saved apiToken is invalid
- GET /api/admin/cloudflare-stream/videos: 412 when not configured; 502 when saved apiToken invalid
- GET /api/live/status regression: unauth response has NO watchUrl/embedUrl/videoId and includes requiresSubscription=true (when live) or isLive=false path

Notes:
- Do not attempt real Cloudflare calls with real credentials — invalid tokens giving 502 is the expected happy path here.
- YouTube API quota may be exhausted; cached path is treated as normal.
"""
import asyncio
import os
import uuid

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient

# Pin to a single worker to avoid the OTP challenge race across xdist workers
pytestmark = pytest.mark.xdist_group(name="iter32_serial")

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://radio-vod-platform.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

ADMIN_PHONE = "250794230137"

_PROTECTED_LIVE_FIELDS = {"watchUrl", "embedUrl", "videoId"}


# ---------------- helpers ----------------

def _otp_login(phone: str) -> tuple[str, str]:
    last = None
    for _ in range(5):
        s = requests.Session()
        r = s.post(f"{API}/auth/otp/start", json={"phone": phone}, timeout=15)
        if r.status_code != 200:
            last = r
            continue
        code = r.json().get("testCode")
        if not code:
            pytest.skip(f"testCode not returned for {phone}")
        r = s.post(f"{API}/auth/otp/verify", json={"phone": phone, "code": code}, timeout=15)
        if r.status_code == 200:
            body = r.json()
            return body["accessToken"], body["user"]["id"]
        last = r
        import time as _t
        _t.sleep(0.5)
    assert False, f"otp login failed after retries {last.status_code if last else '?'}: {(last.text if last else '')[:200]}"


def _run_async(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


async def _clear_cf_config():
    client = AsyncIOMotorClient(MONGO_URL)
    try:
        db = client[DB_NAME]
        await db.integration_state.delete_one({"key": "cloudflare_stream_config"})
    finally:
        client.close()


async def _get_cf_doc():
    client = AsyncIOMotorClient(MONGO_URL)
    try:
        db = client[DB_NAME]
        return await db.integration_state.find_one({"key": "cloudflare_stream_config"}, {"_id": 0})
    finally:
        client.close()


# ---------------- fixtures ----------------

@pytest.fixture(scope="module")
def admin_headers():
    token, _uid = _otp_login(ADMIN_PHONE)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def _reset_cf_config():
    # Reset before each test so config-dependent flows are deterministic
    _run_async(_clear_cf_config())
    yield
    _run_async(_clear_cf_config())


# ---------------- Cloudflare Stream: /config GET ----------------

class TestCFStreamConfigGet:
    def test_get_returns_default_shape_no_leak(self, admin_headers):
        r = requests.get(f"{API}/admin/cloudflare-stream/config", headers=admin_headers, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        # Required response fields
        for k in ("accountId", "customerSubdomain", "hasApiToken", "connected"):
            assert k in body, f"missing key {k}"
        # apiToken must NEVER be in the response (the core security invariant)
        assert "apiToken" not in body
        # hasApiToken/connected are booleans and consistent (connected implies hasApiToken)
        assert isinstance(body["hasApiToken"], bool)
        assert isinstance(body["connected"], bool)
        if body["connected"]:
            assert body["hasApiToken"] is True

    def test_get_requires_admin(self):
        r = requests.get(f"{API}/admin/cloudflare-stream/config", timeout=15)
        assert r.status_code in (401, 403), r.text


# ---------------- Cloudflare Stream: /config PUT ----------------

class TestCFStreamConfigPut:
    def test_put_empty_body_returns_400(self, admin_headers):
        r = requests.put(f"{API}/admin/cloudflare-stream/config", json={}, headers=admin_headers, timeout=15)
        assert r.status_code == 400, r.text

    def test_put_upserts_and_get_reflects(self, admin_headers):
        payload = {
            "accountId": "test-acct-" + uuid.uuid4().hex[:6],
            "apiToken": "test-token-" + uuid.uuid4().hex[:8],
            "customerSubdomain": "customer-x.cloudflarestream.com",
        }
        r = requests.put(f"{API}/admin/cloudflare-stream/config", json=payload, headers=admin_headers, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True

        # Verify GET reflects the changes (and does NOT leak apiToken)
        r2 = requests.get(f"{API}/admin/cloudflare-stream/config", headers=admin_headers, timeout=15)
        assert r2.status_code == 200
        got = r2.json()
        assert got["accountId"] == payload["accountId"]
        assert got["customerSubdomain"] == payload["customerSubdomain"]
        assert got["hasApiToken"] is True
        assert got["connected"] is True
        assert "apiToken" not in got
        assert got.get("connectedAt")  # timestamp saved

        # Verify persistence in db.integration_state
        doc = _run_async(_get_cf_doc())
        assert doc is not None
        assert doc.get("key") == "cloudflare_stream_config"
        assert doc.get("accountId") == payload["accountId"]
        assert doc.get("apiToken") == payload["apiToken"]  # server does store it (raw token)


# ---------------- Cloudflare Stream: /live-input POST ----------------

class TestCFStreamLiveInput:
    def test_412_when_not_configured(self, admin_headers):
        r = requests.post(f"{API}/admin/cloudflare-stream/live-input", headers=admin_headers, timeout=15)
        assert r.status_code == 412, r.text
        assert "not configured" in r.text.lower()

    def test_502_when_token_invalid(self, admin_headers):
        # Seed a config with fake token, then invoke — should call CF and get 502 back
        payload = {"accountId": "fake-acct", "apiToken": "fake-token-invalid", "customerSubdomain": "customer-x.cloudflarestream.com"}
        requests.put(f"{API}/admin/cloudflare-stream/config", json=payload, headers=admin_headers, timeout=15).raise_for_status()

        r = requests.post(f"{API}/admin/cloudflare-stream/live-input", headers=admin_headers, timeout=30)
        # Acceptable: 502 (CF rejects), or 200 (in the unlikely event CF accepts) — expect 502 in practice
        assert r.status_code == 502, f"expected 502 from CF invalid token, got {r.status_code}: {r.text[:300]}"


# ---------------- Cloudflare Stream: /videos GET ----------------

class TestCFStreamVideos:
    def test_412_when_not_configured(self, admin_headers):
        r = requests.get(f"{API}/admin/cloudflare-stream/videos", headers=admin_headers, timeout=15)
        assert r.status_code == 412, r.text

    def test_502_when_token_invalid(self, admin_headers):
        payload = {"accountId": "fake-acct", "apiToken": "fake-token-invalid"}
        requests.put(f"{API}/admin/cloudflare-stream/config", json=payload, headers=admin_headers, timeout=15).raise_for_status()

        r = requests.get(f"{API}/admin/cloudflare-stream/videos", headers=admin_headers, timeout=30)
        assert r.status_code == 502, f"expected 502 from CF invalid token, got {r.status_code}: {r.text[:300]}"


# ---------------- YouTube LIVE regression ----------------

class TestYouTubeLiveStatusRegression:
    def test_unauth_never_returns_protected_fields(self):
        r = requests.get(f"{API}/live/status", timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        # Whatever the isLive value is, unauthenticated response must NOT include protected fields
        for k in _PROTECTED_LIVE_FIELDS:
            assert k not in body, f"unauth response leaked {k}"
        # If live, must have requiresSubscription
        if body.get("isLive"):
            assert body.get("requiresSubscription") is True

    def test_response_shape_has_at_least_isLive(self):
        r = requests.get(f"{API}/live/status", timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert "isLive" in body
        # checkedAt is present in cached responses (per iter32 note that quota may be exhausted)
        # Not strict-asserting because response can be a fresh non-cached "not live" shape too.
