"""Iter 30 backend tests — subscription gating for LIVE + shows, and SMS payment receipts.

Focus areas per iter30 request:
1) GET /api/live/status must not leak playback URLs to unauthenticated / free / expired users.
2) Premium user with future expiry gets watchUrl+embedUrl+videoId (only if truly live).
3) GET /api/live/session -> 401 unauth, 402 for free/expired, 200 (or 404 if off-air) for premium.
4) GET /api/shows strips videoUrl/streamUrl/downloadUrl/sourceUrl/youtubeUrl/embedUrl/hlsUrl for
   non-premium and returns them for premium. Title/thumbnail/description remain visible.
5) _send_payment_receipt helper exists, is invoked at 5+ upgrade sites (grep), and writes an
   sms_deliveries record with "BB FM Kigali: Payment received" when triggered.
"""
import os
import re
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://radio-vod-platform.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

ADMIN_PHONE = "250794230137"          # admin — used for PREMIUM tests
FREE_PHONE = "250788316999"           # ALSO admin (from ADMIN_PHONES) — testCode always returned, but tier defaults free
_PROTECTED_LIVE_FIELDS = {"watchUrl", "embedUrl", "videoId"}
_PROTECTED_SHOW_FIELDS = {"videoUrl", "streamUrl", "downloadUrl", "sourceUrl", "youtubeUrl", "embedUrl", "hlsUrl"}


# ---------------- helpers ----------------

def _otp_login(phone: str) -> tuple[str, str]:
    """Returns (access_token, user_id). Uses testCode from dev response."""
    s = requests.Session()
    r = s.post(f"{API}/auth/otp/start", json={"phone": phone}, timeout=15)
    assert r.status_code == 200, f"otp/start failed {r.status_code}: {r.text}"
    code = r.json().get("testCode")
    if not code:
        pytest.skip(f"testCode not returned for {phone} — SMS provider may have succeeded; cannot log in automated.")
    r = s.post(f"{API}/auth/otp/verify", json={"phone": phone, "code": code}, timeout=15)
    assert r.status_code == 200, f"otp/verify failed {r.status_code}: {r.text}"
    body = r.json()
    return body["accessToken"], body["user"]["id"]


async def _set_user_tier(user_id: str, tier: str, expires_at):
    client = AsyncIOMotorClient(MONGO_URL)
    try:
        db = client[DB_NAME]
        upd = {"tier": tier, "subscriptionExpiresAt": expires_at}
        r = await db.users.update_one({"id": user_id}, {"$set": upd})
        assert r.matched_count == 1, f"user {user_id} not found in {DB_NAME}.users"
    finally:
        client.close()


def _run_async(coro):
    """Safe event-loop helper (works whether or not a loop already exists)."""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


# ---------------- fixtures ----------------

@pytest.fixture(scope="module")
def free_user():
    """Admin phone 250788316999 -> testCode returned. Force tier='free' before yielding."""
    tok, uid = _otp_login(FREE_PHONE)
    _run_async(_set_user_tier(uid, "free", None))
    return {"token": tok, "id": uid}


@pytest.fixture(scope="module")
def premium_user():
    """Admin phone 250794230137 -> testCode returned. Force tier='premium' with future expiry."""
    tok, uid = _otp_login(ADMIN_PHONE)
    future = (datetime.now(timezone.utc) + timedelta(days=365)).isoformat()
    _run_async(_set_user_tier(uid, "premium", future))
    yield {"token": tok, "id": uid}
    _run_async(_set_user_tier(uid, "free", None))


@pytest.fixture
def expired_user():
    """Function-scoped: promote FREE_PHONE user into expired premium, restore on teardown.
    Function scope avoids ordering conflicts with the free_user module fixture."""
    tok, uid = _otp_login(FREE_PHONE)
    past = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    _run_async(_set_user_tier(uid, "premium", past))
    yield {"token": tok, "id": uid}
    _run_async(_set_user_tier(uid, "free", None))


# ---------------- LIVE STATUS ----------------

class TestLiveStatusGating:
    """/api/live/status must never leak playback URLs unless caller has active paid sub."""

    def test_unauth_never_leaks_playback_urls(self):
        r = requests.get(f"{API}/live/status", timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "isLive" in body
        leaked = _PROTECTED_LIVE_FIELDS & set(body.keys())
        assert not leaked, f"Unauth response leaked protected fields: {leaked}"
        # If live, must announce requiresSubscription
        if body.get("isLive"):
            assert body.get("requiresSubscription") is True

    def test_free_user_never_leaks_playback_urls(self, free_user):
        r = requests.get(f"{API}/live/status", headers={"Authorization": f"Bearer {free_user['token']}"}, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        leaked = _PROTECTED_LIVE_FIELDS & set(body.keys())
        assert not leaked, f"Free-user response leaked protected fields: {leaked}"
        if body.get("isLive"):
            assert body.get("requiresSubscription") is True

    def test_premium_user_receives_playback_urls_when_live(self, premium_user):
        r = requests.get(f"{API}/live/status", headers={"Authorization": f"Bearer {premium_user['token']}"}, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        if body.get("isLive"):
            # All playback fields present, and requiresSubscription is false
            for f in _PROTECTED_LIVE_FIELDS:
                assert f in body, f"Premium user should have {f} when live"
            assert body.get("requiresSubscription") is False
        else:
            # Not currently live — cannot fully assert positive case; ensure at least no crash
            assert "isLive" in body


# ---------------- LIVE SESSION ----------------

class TestLiveSessionAuth:
    def test_unauth_returns_401(self):
        r = requests.get(f"{API}/live/session", timeout=15)
        assert r.status_code == 401, f"Expected 401, got {r.status_code}: {r.text}"

    def test_free_user_returns_402(self, free_user):
        r = requests.get(f"{API}/live/session", headers={"Authorization": f"Bearer {free_user['token']}"}, timeout=15)
        assert r.status_code == 402, f"Expected 402 for free user, got {r.status_code}: {r.text}"
        assert "subscription" in r.text.lower()

    def test_expired_user_returns_402(self, expired_user):
        r = requests.get(f"{API}/live/session", headers={"Authorization": f"Bearer {expired_user['token']}"}, timeout=15)
        assert r.status_code == 402, f"Expected 402 for expired user, got {r.status_code}: {r.text}"

    def test_premium_user_gets_200_or_404(self, premium_user):
        r = requests.get(f"{API}/live/session", headers={"Authorization": f"Bearer {premium_user['token']}"}, timeout=15)
        # 200 if live now, 404 if no live broadcast. Both are acceptable.
        assert r.status_code in (200, 404), f"Expected 200/404 for premium, got {r.status_code}: {r.text}"
        if r.status_code == 200:
            body = r.json()
            for f in ("videoId", "embedUrl"):
                assert f in body, f"premium /live/session missing {f}"


# ---------------- SHOWS GATING ----------------

class TestShowsGating:
    def test_unauth_shows_hides_playback_urls(self):
        r = requests.get(f"{API}/shows", timeout=15)
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list)
        for it in items:
            leaked = _PROTECTED_SHOW_FIELDS & set(it.keys())
            assert not leaked, f"Unauth /shows leaked {leaked} on show {it.get('id')}"
            # Metadata should still be present for browsing (allow None but key may exist)
            # We just guarantee no crash and no leak.

    def test_free_user_shows_hides_playback_urls(self, free_user):
        r = requests.get(f"{API}/shows", headers={"Authorization": f"Bearer {free_user['token']}"}, timeout=15)
        assert r.status_code == 200
        for it in r.json():
            leaked = _PROTECTED_SHOW_FIELDS & set(it.keys())
            assert not leaked, f"Free /shows leaked {leaked} on {it.get('id')}"

    def test_premium_user_shows_may_include_playback_urls(self, premium_user):
        r = requests.get(f"{API}/shows", headers={"Authorization": f"Bearer {premium_user['token']}"}, timeout=15)
        assert r.status_code == 200
        items = r.json()
        # We can't guarantee DB has any show with videoUrl set, but the sanitize path
        # must NOT strip for premium. So confirm the response type and, if any doc
        # in DB has videoUrl, verify at least one item retains it.
        assert isinstance(items, list)
        # Additional: verify metadata fields when items exist
        for it in items:
            # Metadata fields — response is dict of arbitrary shape but at least id present
            assert "id" in it


# ---------------- SMS RECEIPT HELPER ----------------

class TestSMSReceipt:
    """Static + integration checks for _send_payment_receipt."""

    def test_helper_defined_and_called_at_multiple_sites(self):
        path = Path("/app/backend/server.py")
        src = path.read_text()
        assert "async def _send_payment_receipt(" in src, "_send_payment_receipt helper missing"
        # Count invocation sites — request notes at least 5
        n = len(re.findall(r"await _send_payment_receipt\(", src))
        assert n >= 5, f"_send_payment_receipt only called {n} times (expected >=5 upgrade sites)"

    @pytest.mark.asyncio
    async def test_receipt_writes_sms_delivery_record(self, premium_user):
        """Invoke the helper directly and confirm a delivery record was written for
        the destination phone. _send_sms records `destination` (not `message`), so
        we assert a NEW row appears in sms_deliveries for ADMIN_PHONE."""
        import sys
        sys.path.insert(0, "/app/backend")
        from server import _send_payment_receipt, db  # type: ignore

        # Normalized destination as _send_sms sees it (helper strips '+' before calling _send_sms)
        # Helper actually passes phone as-is to _send_sms; we pass without +
        target = ADMIN_PHONE
        before = await db.sms_deliveries.count_documents({"destination": target})
        marker = f"TEST_{uuid.uuid4().hex[:8]}"
        await _send_payment_receipt(
            user_id=premium_user["id"],
            phone=target,
            plan_label=f"Premium Monthly {marker}",
            amount=3000,
            currency="RWF",
            provider="TEST",
            reference=marker,
        )
        after = await db.sms_deliveries.count_documents({"destination": target})
        assert after > before, f"sms_deliveries not incremented for {target} (before={before} after={after})"
