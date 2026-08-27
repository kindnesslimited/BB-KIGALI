"""Iteration 36 backend test — payment/access reliability layer.

Covers:
- POST /api/subscription/reconcile   (auth + shape + user block)
- GET  /api/legal/terms/current      (public, correct URLs + version)
- POST /api/legal/terms/accept       (auth + persistence in mongo)
- GET  /api/auth/me                  (new fields — see FIELD ASSERTIONS)
- GET  /api/live/session             (enablejsapi + watchUrl)
- GET  /api/admin/reports/business.pdf  (unauth / non-admin / admin happy /
                                         invalid dates / end<start)
- Regression: radio/now-playing, radio/token JWT pur claim,
              subscription/rc-sync still working
"""

import os
import time
from urllib.parse import urlparse

import jwt as pyjwt
import pytest
import requests
from pymongo import MongoClient

BASE_URL = (os.environ.get("EXPO_BACKEND_URL") or os.environ.get("PUBLIC_BASE_URL") or "http://localhost:8001").rstrip("/")
# We test against localhost:8001 by request of the review; still accept public URL via env.
if "EXPO_BACKEND_URL" not in os.environ and "PUBLIC_BASE_URL" not in os.environ:
    BASE_URL = "http://localhost:8001"

JWT_SECRET = os.environ.get("JWT_SECRET", "bbfm-kigali-prod-jwt-secret-please-rotate-in-live")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

ADMIN_PHONE = "250794230137"
FRESH_PHONE = "+250788555777"     # non-admin phone for 403 test
MOCK_OTP = "123456"


# ---------------------- fixtures ----------------------
@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def mongo():
    c = MongoClient(MONGO_URL)
    return c[DB_NAME]


def _otp_login(api, phone, mongo=None):
    """Return (token, user_dict). Falls back to reading challenge from mongo if
    testCode isn't returned (SMS was actually sent to a non-admin number)."""
    r = api.post(f"{BASE_URL}/api/auth/otp/start", json={"phone": phone})
    assert r.status_code == 200, r.text
    body = r.json()
    code = body.get("testCode")
    if not code:
        if mongo is None:
            mongo = MongoClient(MONGO_URL)[DB_NAME]
        ch = mongo.otp_challenges.find_one({"phone": phone})
        assert ch, f"no otp challenge stored for {phone}"
        code = ch["code"]
    r = api.post(f"{BASE_URL}/api/auth/otp/verify", json={"phone": phone, "code": code})
    assert r.status_code == 200, r.text
    body = r.json()
    return body["accessToken"], body["user"]


@pytest.fixture(scope="module")
def admin_token(api):
    token, user = _otp_login(api, ADMIN_PHONE)
    assert user["role"] == "admin", f"expected admin role, got {user}"
    return token


@pytest.fixture(scope="module")
def admin_user(api, admin_token):
    r = api.get(f"{BASE_URL}/api/auth/me", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    return r.json()


@pytest.fixture(scope="module")
def user_token(api, mongo):
    """Fresh non-admin phone user."""
    token, user = _otp_login(api, FRESH_PHONE, mongo=mongo)
    assert user["role"] != "admin", f"phone {FRESH_PHONE} was admin — pick a different one"
    return token


# ==================== 1. /subscription/reconcile ====================
class TestSubscriptionReconcile:
    def test_unauth_401(self, api):
        r = api.post(f"{BASE_URL}/api/subscription/reconcile")
        assert r.status_code in (401, 403), r.text

    def test_auth_no_pending(self, api, user_token, mongo):
        # Ensure the fresh user has no pending payments — clean slate.
        r = api.post(
            f"{BASE_URL}/api/subscription/reconcile",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["checked"] == 0, f"expected 0 checked, got {body}"
        assert body["granted"] == []
        assert "user" in body
        u = body["user"]
        assert "tier" in u
        assert "subscriptionExpiresAt" in u
        assert "currentPlan" in u


# ==================== 2. /legal/terms/current ====================
class TestLegalTermsCurrent:
    def test_public_shape(self, api):
        r = api.get(f"{BASE_URL}/api/legal/terms/current")
        assert r.status_code == 200, r.text
        b = r.json()
        for k in ("version", "url", "privacyUrl"):
            assert k in b, f"missing key {k} in {b}"
        assert "web.bbkigali.com" in b["url"], b
        assert "web.bbkigali.com" in b["privacyUrl"], b
        assert b["url"].endswith("/terms.html")
        assert b["privacyUrl"].endswith("/privacy.html")


# ==================== 3. /legal/terms/accept ====================
class TestLegalTermsAccept:
    def test_unauth_401(self, api):
        r = api.post(f"{BASE_URL}/api/legal/terms/accept", json={})
        assert r.status_code in (401, 403), r.text

    def test_auth_default_context_persists(self, api, admin_token, admin_user, mongo):
        before = mongo.terms_acceptances.count_documents({"userId": admin_user["id"]})
        # Send with no body (empty JSON) — should use defaults
        r = api.post(
            f"{BASE_URL}/api/legal/terms/accept",
            json={},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert "version" in body and "acceptedAt" in body

        # user doc stamped
        u = mongo.users.find_one({"id": admin_user["id"]}, {"_id": 0})
        assert u.get("termsAcceptedAt")
        assert u.get("termsVersion") == body["version"]

        # doc inserted in terms_acceptances
        after = mongo.terms_acceptances.count_documents({"userId": admin_user["id"]})
        assert after == before + 1, f"expected +1 acceptance, got {before}→{after}"

        # verify default context recorded
        latest = list(mongo.terms_acceptances.find({"userId": admin_user["id"]}).sort("at", -1).limit(1))
        assert latest, "no acceptance doc found"
        assert latest[0].get("context") == "subscribe", latest[0]


# ==================== 4. /auth/me shape ====================
class TestAuthMeShape:
    """Verify /auth/me returns the new fields.

    NB: Current server.py declares `response_model=UserOut` on /auth/me and the
    UserOut pydantic model does NOT include `currentPlan`, `provider`,
    `termsAcceptedAt`, `termsVersion` — so pydantic strips them from the response.
    This test will FAIL until UserOut is updated or response_model is removed.
    """

    REQUIRED = ("id", "phone", "tier", "role", "subscriptionExpiresAt",
                "currentPlan", "provider", "termsAcceptedAt", "termsVersion")

    def test_all_new_fields_present(self, api, admin_token):
        r = api.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 200, r.text
        b = r.json()
        missing = [k for k in self.REQUIRED if k not in b]
        assert not missing, f"/auth/me missing keys {missing}. Got keys: {list(b.keys())}"


# ==================== 5. /live/session ====================
class TestLiveSession:
    def test_premium_returns_correct_urls_or_404(self, api, admin_token):
        # rc-sync first so we know user is premium
        r = api.post(
            f"{BASE_URL}/api/subscription/rc-sync",
            json={"plan": "premium_monthly"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 200, r.text
        assert r.json().get("tier") == "premium"

        r = api.get(
            f"{BASE_URL}/api/live/session",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        # 404 is acceptable per the spec if not live right now
        if r.status_code == 404:
            pytest.skip("Station not live at the moment — 404 is acceptable")
        assert r.status_code == 200, r.text
        b = r.json()
        assert "embedUrl" in b and "watchUrl" in b
        assert "enablejsapi=1" in b["embedUrl"]
        assert "origin=" in b["embedUrl"]
        vid = b.get("videoId")
        assert vid, b
        assert b["watchUrl"] == f"https://www.youtube.com/watch?v={vid}"


# ==================== 6. /admin/reports/business.pdf ====================
class TestBusinessReportPdf:
    URL = "/api/admin/reports/business.pdf"

    def test_unauth_401(self, api):
        r = api.get(f"{BASE_URL}{self.URL}")
        assert r.status_code in (401, 403), r.text

    def test_non_admin_403(self, api, user_token):
        r = api.get(
            f"{BASE_URL}{self.URL}",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert r.status_code == 403, r.text

    def test_admin_ok_pdf(self, api, admin_token):
        r = api.get(
            f"{BASE_URL}{self.URL}?start=2026-08-01&end=2026-08-27",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 200, r.text
        assert r.headers.get("content-type", "").startswith("application/pdf"), r.headers
        cd = r.headers.get("content-disposition", "")
        assert "attachment" in cd and "filename=" in cd, cd
        assert r.content[:5] == b"%PDF-", r.content[:20]
        assert len(r.content) > 3 * 1024, f"PDF too small: {len(r.content)} bytes"

    def test_invalid_start_400(self, api, admin_token):
        r = api.get(
            f"{BASE_URL}{self.URL}?start=hello",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 400, r.text

    def test_end_before_start_400(self, api, admin_token):
        r = api.get(
            f"{BASE_URL}{self.URL}?start=2026-08-27&end=2026-08-01",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 400, r.text


# ==================== 7. Regression sanity ====================
class TestRegressionSanity:
    def test_now_playing_unauth_hides_stream(self, api):
        r = api.get(f"{BASE_URL}/api/radio/now-playing")
        assert r.status_code == 200, r.text
        b = r.json()
        assert b.get("requiresSubscription") is True, b
        assert "streamUrl" not in b, b
        assert "streamUrlHttps" not in b, b

    def test_radio_token_jwt_pur(self, api, admin_token):
        # admin from previous test is premium after rc-sync
        r = api.get(
            f"{BASE_URL}/api/radio/token",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 200, r.text
        b = r.json()
        assert "token" in b
        decoded = pyjwt.decode(b["token"], JWT_SECRET, algorithms=["HS256"])
        assert decoded.get("pur") == "radio_stream", decoded

    def test_rc_sync_still_works(self, api, admin_token):
        r = api.post(
            f"{BASE_URL}/api/subscription/rc-sync",
            json={"plan": "premium_monthly"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 200, r.text
        assert r.json().get("tier") == "premium"

    def test_reconcile_after_rc_sync_premium(self, api, admin_token):
        # rc-sync just above
        r = api.post(
            f"{BASE_URL}/api/subscription/reconcile",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["user"]["tier"] == "premium", b
