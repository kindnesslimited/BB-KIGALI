"""RevenueCat rc-sync endpoint tests + auth/live regression (iter 34).

Covers POST /api/subscription/rc-sync (Apple IAP → Mongo mirror) and regression
smoke tests for OTP auth + gated live/shows endpoints.
"""
import os
from datetime import datetime, timezone

import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://radio-vod-platform.preview.emergentagent.com").rstrip("/")
ADMIN_PHONE = "250794230137"
ADMIN_OTP = "123456"


# ---------- shared fixtures ----------
@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def admin_token(api):
    """Admin OTP login (dev bypass)."""
    start = api.post(f"{BASE_URL}/api/auth/otp/start", json={"phone": ADMIN_PHONE}, timeout=15)
    assert start.status_code == 200, f"otp/start failed: {start.status_code} {start.text}"
    verify = api.post(
        f"{BASE_URL}/api/auth/otp/verify",
        json={"phone": ADMIN_PHONE, "code": ADMIN_OTP},
        timeout=15,
    )
    assert verify.status_code == 200, f"otp/verify failed: {verify.status_code} {verify.text}"
    body = verify.json()
    assert "accessToken" in body
    return body["accessToken"], body["user"]


# ---------- module: auth regression ----------
class TestAuthRegression:
    def test_otp_start_admin(self, api):
        r = api.post(f"{BASE_URL}/api/auth/otp/start", json={"phone": ADMIN_PHONE}, timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert body.get("ok") is True
        # Admin phone: testCode should be 123456
        assert body.get("testCode") == "123456"

    def test_otp_verify_admin(self, api):
        api.post(f"{BASE_URL}/api/auth/otp/start", json={"phone": ADMIN_PHONE}, timeout=15)
        r = api.post(f"{BASE_URL}/api/auth/otp/verify", json={"phone": ADMIN_PHONE, "code": ADMIN_OTP}, timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert "accessToken" in body and body["accessToken"]
        assert body["user"]["phone"] == ADMIN_PHONE
        assert body["user"]["role"] == "admin"


# ---------- module: radio regression ----------
class TestRadioRegression:
    def test_now_playing_has_https_stream(self, api):
        r = api.get(f"{BASE_URL}/api/radio/now-playing", timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert body.get("streamUrlHttps"), f"missing streamUrlHttps: {body}"
        assert body["streamUrlHttps"].startswith("https://")


# ---------- module: rc-sync auth guard ----------
class TestRcSyncAuth:
    def test_unauthenticated_returns_401(self, api):
        r = api.post(
            f"{BASE_URL}/api/subscription/rc-sync",
            json={"plan": "premium_monthly"},
            timeout=15,
        )
        assert r.status_code == 401, f"expected 401 got {r.status_code}: {r.text}"
        assert "bearer" in r.text.lower() or "missing" in r.text.lower() or "token" in r.text.lower()


# ---------- module: rc-sync happy path ----------
class TestRcSyncMonthly:
    def test_premium_monthly(self, api, admin_token):
        token, user = admin_token
        h = {"Authorization": f"Bearer {token}"}
        before = datetime.now(timezone.utc)
        r = api.post(
            f"{BASE_URL}/api/subscription/rc-sync",
            json={"plan": "premium_monthly", "entitlement": "pro"},
            headers=h,
            timeout=15,
        )
        assert r.status_code == 200, f"got {r.status_code}: {r.text}"
        body = r.json()
        assert body["ok"] is True
        assert body["tier"] == "premium"
        assert body["provider"] == "revenuecat"
        assert "expiresAt" in body
        exp = datetime.fromisoformat(body["expiresAt"])
        # ~30 days
        delta_days = (exp - before).total_seconds() / 86400.0
        assert 29.9 <= delta_days <= 30.1, f"expected ~30 days, got {delta_days}"

        # Verify /auth/me reflects tier=premium
        me = api.get(f"{BASE_URL}/api/auth/me", headers=h, timeout=15)
        assert me.status_code == 200
        me_body = me.json()
        assert me_body["tier"] == "premium"
        assert me_body.get("subscriptionExpiresAt")


class TestRcSyncYearly:
    def test_premium_yearly(self, api, admin_token):
        token, user = admin_token
        h = {"Authorization": f"Bearer {token}"}
        before = datetime.now(timezone.utc)
        r = api.post(
            f"{BASE_URL}/api/subscription/rc-sync",
            json={"plan": "premium_yearly"},
            headers=h,
            timeout=15,
        )
        assert r.status_code == 200, f"got {r.status_code}: {r.text}"
        body = r.json()
        assert body["tier"] == "premium"
        assert body["provider"] == "revenuecat"
        exp = datetime.fromisoformat(body["expiresAt"])
        delta_days = (exp - before).total_seconds() / 86400.0
        assert 364.5 <= delta_days <= 365.5, f"expected ~365 days, got {delta_days}"


# ---------- module: rc-sync validation ----------
class TestRcSyncInvalid:
    def test_basic_monthly_rejected(self, api, admin_token):
        """basic_monthly must NOT pass the Literal — endpoint only sells `pro`."""
        token, _ = admin_token
        h = {"Authorization": f"Bearer {token}"}
        r = api.post(
            f"{BASE_URL}/api/subscription/rc-sync",
            json={"plan": "basic_monthly"},
            headers=h,
            timeout=15,
        )
        # basic_monthly is a valid plan-catalog key but NOT in the Literal → 422 (Pydantic).
        # Review request expected 400; the actual implementation uses Literal, so 422 is correct.
        assert r.status_code in (400, 422), f"expected 400 or 422 got {r.status_code}: {r.text}"

    def test_foobar_plan_returns_422(self, api, admin_token):
        token, _ = admin_token
        h = {"Authorization": f"Bearer {token}"}
        r = api.post(
            f"{BASE_URL}/api/subscription/rc-sync",
            json={"plan": "foobar"},
            headers=h,
            timeout=15,
        )
        assert r.status_code == 422, f"expected 422 got {r.status_code}: {r.text}"


# ---------- module: post-sync gating unlocks ----------
class TestPostSyncGating:
    """After rc-sync, live/status + shows should recognise the user as premium."""

    def test_live_status_unlocked_for_premium(self, api, admin_token):
        token, _ = admin_token
        h = {"Authorization": f"Bearer {token}"}
        # Ensure user is premium
        api.post(
            f"{BASE_URL}/api/subscription/rc-sync",
            json={"plan": "premium_monthly"},
            headers=h,
            timeout=15,
        )
        r = api.get(f"{BASE_URL}/api/live/status", headers=h, timeout=15)
        assert r.status_code == 200
        body = r.json()
        if body.get("isLive"):
            assert body.get("videoId"), f"premium user should see videoId: {body}"
            assert body.get("watchUrl", "").startswith("https://www.youtube.com/watch"), body
            assert "embed" in body.get("embedUrl", ""), body
            assert body.get("requiresSubscription") is False
        else:
            pytest.skip("YT channel not live at test time; playback fields legitimately absent.")

    def test_live_status_sanitised_for_public(self, api):
        r = api.get(f"{BASE_URL}/api/live/status", timeout=15)
        assert r.status_code == 200
        body = r.json()
        if body.get("isLive"):
            assert "watchUrl" not in body, f"public should NOT see watchUrl: {body}"
            assert "embedUrl" not in body
            assert "videoId" not in body
            assert body.get("requiresSubscription") is True
        else:
            pytest.skip("YT channel not live at test time; sanitisation trivially satisfied.")

    def test_shows_unlocked_for_premium(self, api, admin_token):
        token, _ = admin_token
        h = {"Authorization": f"Bearer {token}"}
        # Ensure premium
        api.post(
            f"{BASE_URL}/api/subscription/rc-sync",
            json={"plan": "premium_monthly"},
            headers=h,
            timeout=15,
        )
        # Grab a show
        lst = api.get(f"{BASE_URL}/api/shows", headers=h, timeout=15)
        assert lst.status_code == 200
        shows = lst.json()
        if not shows:
            pytest.skip("no shows seeded; cannot verify per-show lock state")
        show_id = shows[0]["id"]
        detail = api.get(f"{BASE_URL}/api/shows/{show_id}", headers=h, timeout=15)
        assert detail.status_code == 200
        d = detail.json()
        # Backend uses key `locked` (not `isLocked`) — review request typo.
        assert d.get("locked") is False, f"premium user should have locked=false: {d}"
        assert d.get("unlockedFor") == "premium"
