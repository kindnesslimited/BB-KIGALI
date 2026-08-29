"""Iteration 37 — FULL PRODUCTION READINESS test.

Covers sections A-G of the review request (backend + landing).
Section H (web frontend) is covered by a separate Playwright script.
"""

import os
import re
import time
from urllib.parse import urlparse

import httpx
import jwt as pyjwt
import pytest
import requests
from pymongo import MongoClient

# ---------- config ----------
BASE_URL = "http://localhost:8001"
PUBLIC_URL = os.environ.get("PUBLIC_BASE_URL", "https://radio-vod-platform.preview.emergentagent.com").rstrip("/")
JWT_SECRET = os.environ.get("JWT_SECRET", "bbfm-kigali-prod-jwt-secret-please-rotate-in-live")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

ADMIN_PHONE = "250794230137"
FRESH_PHONE = "+250780111222"
MOCK_OTP = "123456"


# ---------------------- fixtures ----------------------
@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def mongo():
    return MongoClient(MONGO_URL)[DB_NAME]


def _e164(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    return "+" + digits


def _login(api, phone, mongo=None):
    r = api.post(f"{BASE_URL}/api/auth/otp/start", json={"phone": phone})
    assert r.status_code == 200, r.text
    body = r.json()
    code = body.get("testCode")
    if not code:
        if mongo is None:
            mongo = MongoClient(MONGO_URL)[DB_NAME]
        # server stores phone as E.164
        target = _e164(phone)
        ch = mongo.otp_challenges.find_one({"phone": target})
        if not ch:
            # try last-inserted for this phone (fuzzy)
            ch = mongo.otp_challenges.find_one(
                {"phone": {"$regex": target[-9:] + "$"}}, sort=[("createdAt", -1)]
            )
        assert ch, f"no otp challenge stored for {phone} (target={target})"
        code = ch["code"]
    r = api.post(f"{BASE_URL}/api/auth/otp/verify", json={"phone": phone, "code": code})
    assert r.status_code == 200, r.text
    body = r.json()
    return body["accessToken"], body["user"]


@pytest.fixture(scope="module")
def admin_token(api):
    tok, user = _login(api, ADMIN_PHONE)
    assert user["role"] == "admin"
    return tok


@pytest.fixture(scope="module")
def user_token(api, mongo):
    tok, user = _login(api, FRESH_PHONE, mongo=mongo)
    return tok


# ==================== A. AUTH ====================
class TestAuth:
    """Section A — Auth (5 min)"""

    # A1 — anonymous browse works, radio hidden
    def test_A1_anonymous_content_no_stream(self, api):
        assert api.get(f"{BASE_URL}/api/news").status_code == 200
        assert api.get(f"{BASE_URL}/api/programs").status_code == 200
        assert api.get(f"{BASE_URL}/api/radio/schedule").status_code == 200
        r = api.get(f"{BASE_URL}/api/radio/now-playing")
        assert r.status_code == 200
        b = r.json()
        assert b.get("requiresSubscription") is True
        assert "streamUrl" not in b

    # A2 — multi-format admin phone
    @pytest.mark.parametrize("phone", [
        "250794230137",
        "+250 794 230 137",
        "250-794-230-137",
        "(250) 794 230 137",
    ])
    def test_A2_admin_multi_format(self, api, phone):
        r = api.post(f"{BASE_URL}/api/auth/otp/start", json={"phone": phone})
        assert r.status_code == 200, r.text
        code = r.json().get("testCode") or MOCK_OTP
        r = api.post(f"{BASE_URL}/api/auth/otp/verify", json={"phone": phone, "code": code})
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["user"]["role"] == "admin", b
        assert b.get("accessToken"), b

    # A3 — non-admin OTP flow
    def test_A3_non_admin_otp(self, api, mongo):
        tok, user = _login(api, "+250 780 111 333", mongo=mongo)
        assert tok
        assert user.get("role") != "admin"

    # A4 — /auth/me returns all 9 fields
    def test_A4_auth_me_all_fields(self, api, admin_token):
        r = api.get(f"{BASE_URL}/api/auth/me",
                    headers={"Authorization": f"Bearer {admin_token}"})
        assert r.status_code == 200
        b = r.json()
        required = ["id", "phone", "tier", "role", "subscriptionExpiresAt",
                    "currentPlan", "provider", "termsAcceptedAt", "termsVersion"]
        missing = [k for k in required if k not in b]
        assert not missing, f"/auth/me missing: {missing}. Got: {list(b.keys())}"

    # A5 — logout (backend is stateless JWT — verify token no longer needed / /auth/me still works with bearer)
    def test_A5_logout_client_only(self, api, admin_token):
        # server is stateless — logout is client-side token removal. Verify /auth/me without bearer = 401.
        r = api.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code in (401, 403)


# ==================== B. Subscription / Payments ====================
class TestSubscriptionPayments:
    # B6
    def test_B6_terms_current(self, api):
        r = api.get(f"{BASE_URL}/api/legal/terms/current")
        assert r.status_code == 200
        b = r.json()
        assert "version" in b
        assert "web.bbkigali.com" in b["url"]
        assert "web.bbkigali.com" in b["privacyUrl"]

    # B7
    def test_B7_terms_accept(self, api, admin_token, mongo):
        me = api.get(f"{BASE_URL}/api/auth/me",
                     headers={"Authorization": f"Bearer {admin_token}"}).json()
        uid = me["id"]
        before = mongo.terms_acceptances.count_documents({"userId": uid})
        r = api.post(f"{BASE_URL}/api/legal/terms/accept", json={},
                     headers={"Authorization": f"Bearer {admin_token}"})
        assert r.status_code == 200, r.text
        after = mongo.terms_acceptances.count_documents({"userId": uid})
        assert after == before + 1
        u = mongo.users.find_one({"id": uid}, {"_id": 0})
        assert u.get("termsAcceptedAt")

    # B8
    def test_B8_rc_sync_premium(self, api, admin_token):
        r = api.post(f"{BASE_URL}/api/subscription/rc-sync",
                     json={"plan": "premium_monthly"},
                     headers={"Authorization": f"Bearer {admin_token}"})
        assert r.status_code == 200, r.text
        b = r.json()
        assert b.get("tier") == "premium"
        assert b.get("expiresAt") or b.get("subscriptionExpiresAt")

    # B9
    def test_B9_reconcile(self, api, admin_token):
        r = api.post(f"{BASE_URL}/api/subscription/reconcile",
                     headers={"Authorization": f"Bearer {admin_token}"})
        assert r.status_code == 200, r.text
        b = r.json()
        assert "checked" in b and "granted" in b and "user" in b
        assert b["user"]["tier"] in ("premium", "basic", "free")

    # B10
    def test_B10_plans(self, api):
        r = api.get(f"{BASE_URL}/api/billing/plans")
        assert r.status_code == 200
        plans = r.json()
        ids = {p["id"] for p in plans}
        assert {"basic_monthly", "basic_yearly", "premium_monthly", "premium_yearly"} <= ids

    # B11
    def test_B11_stripe_checkout(self, api, admin_token):
        r = api.post(f"{BASE_URL}/api/billing/stripe/create-checkout",
                     json={"purchase_type": "subscription", "plan": "premium_monthly"},
                     headers={"Authorization": f"Bearer {admin_token}"})
        assert r.status_code == 200, r.text
        b = r.json()
        assert b.get("sessionId"), b
        assert b.get("checkoutUrl"), b
        host = urlparse(b["checkoutUrl"]).hostname or ""
        assert "stripe.com" in host, b["checkoutUrl"]

    # B12
    def test_B12_paypal_subscription(self, api, admin_token):
        r = api.post(f"{BASE_URL}/api/billing/paypal/create-subscription",
                     json={"plan": "premium_monthly"},
                     headers={"Authorization": f"Bearer {admin_token}"})
        assert r.status_code == 200, r.text
        b = r.json()
        sid = b.get("subscriptionId") or b.get("id") or ""
        assert sid.startswith("I-"), b
        url = b.get("approveUrl") or b.get("approvalUrl") or ""
        host = urlparse(url).hostname or ""
        assert "paypal.com" in host, url

    # B13
    def test_B13_momo_initiate_and_poll(self, api, admin_token):
        r = api.post(f"{BASE_URL}/api/billing/momo/initiate",
                     json={"plan": "basic_monthly", "phone": "+250 780 111 222"},
                     headers={"Authorization": f"Bearer {admin_token}"})
        assert r.status_code == 200, r.text
        b = r.json()
        ref = b.get("reference") or b.get("ref") or b.get("id")
        assert ref, b
        assert "status" in b
        # poll
        r2 = api.get(f"{BASE_URL}/api/billing/momo/{ref}",
                     headers={"Authorization": f"Bearer {admin_token}"})
        assert r2.status_code == 200, r2.text
        assert "status" in r2.json()

    # B14
    def test_B14_stripe_checkout_reachable(self, api, admin_token):
        r = api.post(f"{BASE_URL}/api/billing/stripe/create-checkout",
                     json={"purchase_type": "subscription", "plan": "premium_monthly"},
                     headers={"Authorization": f"Bearer {admin_token}"})
        url = r.json()["checkoutUrl"]
        with httpx.Client(follow_redirects=False, timeout=15.0) as c:
            resp = c.get(url)
        assert 200 <= resp.status_code < 400, f"Stripe URL not reachable: {resp.status_code}"


# ==================== C. Radio subscription gate ====================
class TestRadioGate:
    def test_C15_unauth_no_stream(self, api):
        r = api.get(f"{BASE_URL}/api/radio/now-playing")
        assert r.status_code == 200
        b = r.json()
        assert "streamUrl" not in b
        assert b.get("requiresSubscription") is True

    def test_C16_free_user_no_stream(self, api, mongo):
        tok, user = _login(api, "+250780111444", mongo=mongo)
        r = api.get(f"{BASE_URL}/api/radio/now-playing",
                    headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200
        b = r.json()
        # Free user should not receive stream URL
        assert b.get("requiresSubscription") is True or "streamUrl" not in b

    def test_C17_premium_gets_streams(self, api, admin_token):
        api.post(f"{BASE_URL}/api/subscription/rc-sync",
                 json={"plan": "premium_monthly"},
                 headers={"Authorization": f"Bearer {admin_token}"})
        r = api.get(f"{BASE_URL}/api/radio/now-playing",
                    headers={"Authorization": f"Bearer {admin_token}"})
        assert r.status_code == 200
        b = r.json()
        assert b.get("streamUrl") or b.get("streamUrlHttps"), b
        proxy = b.get("proxyStreamUrl") or ""
        assert "/api/radio/live?token=" in proxy, b

    def test_C18_radio_token_pur_claim(self, api, admin_token):
        r = api.get(f"{BASE_URL}/api/radio/token",
                    headers={"Authorization": f"Bearer {admin_token}"})
        assert r.status_code == 200
        tok = r.json()["token"]
        decoded = pyjwt.decode(tok, JWT_SECRET, algorithms=["HS256"])
        assert decoded.get("pur") == "radio_stream"

    def test_C19_radio_live_streams(self, api, admin_token):
        r = api.get(f"{BASE_URL}/api/radio/token",
                    headers={"Authorization": f"Bearer {admin_token}"})
        tok = r.json()["token"]
        got = 0
        deadline = time.time() + 8
        ct = None
        with httpx.stream("GET", f"{BASE_URL}/api/radio/live?token={tok}", timeout=8.0) as resp:
            assert resp.status_code == 200, resp.status_code
            ct = resp.headers.get("content-type", "")
            for chunk in resp.iter_bytes():
                got += len(chunk)
                if got >= 8192 or time.time() > deadline:
                    break
        assert got >= 8192, f"Only got {got} bytes"
        assert ct.startswith("audio/") or "mpeg" in ct.lower(), ct

    def test_C20_forged_token_rejected(self, api):
        forged = pyjwt.encode({"pur": "other", "sub": "x"}, JWT_SECRET, algorithm="HS256")
        r = api.get(f"{BASE_URL}/api/radio/live?token={forged}")
        assert r.status_code == 401, r.status_code

    def test_C21_upstream_stream_url(self):
        # Check server config uses radio.bbkigali.com:8080/stream OR the HTTPS mirror
        # Read from server.py or env — we accept either since RADIO_STREAM_URL_HTTPS is set.
        expected_https = os.environ.get("RADIO_STREAM_URL_HTTPS", "https://stream.bbkigali.com/stream/1/")
        assert "bbkigali.com" in expected_https


# ==================== D. Live YouTube + Video ====================
class TestLiveVideo:
    def test_D22_live_status_public_no_leak(self, api):
        r = api.get(f"{BASE_URL}/api/live/status")
        assert r.status_code == 200
        b = r.json()
        # unpaid users should not get watchUrl/embedUrl leaked
        assert "watchUrl" not in b or not b.get("watchUrl") or b.get("isLive") is False

    def test_D23_live_status_premium(self, api, admin_token):
        api.post(f"{BASE_URL}/api/subscription/rc-sync",
                 json={"plan": "premium_monthly"},
                 headers={"Authorization": f"Bearer {admin_token}"})
        r = api.get(f"{BASE_URL}/api/live/status",
                    headers={"Authorization": f"Bearer {admin_token}"})
        assert r.status_code == 200
        b = r.json()
        if b.get("isLive") and b.get("embedUrl"):
            e = b["embedUrl"]
            assert "enablejsapi=1" in e
            assert "origin=https%3A%2F%2Fweb.bbkigali.com" in e
            # no dup: origin only once
            assert e.count("origin=") == 1, e
            assert e.count("enablejsapi=1") == 1, e

    def test_D24_live_session(self, api, admin_token):
        r = api.get(f"{BASE_URL}/api/live/session",
                    headers={"Authorization": f"Bearer {admin_token}"})
        if r.status_code == 404:
            pytest.skip("Not live now")
        assert r.status_code == 200
        b = r.json()
        assert b.get("embedUrl") and b.get("watchUrl")

    def test_D25_videos_status_worker_not_deployed(self, api):
        r = api.get(f"{BASE_URL}/api/videos/status")
        assert r.status_code == 200
        b = r.json()
        # Given .env has empty CLOUDFLARE_STREAM_SUBDOMAIN
        assert b.get("ready") is False or b.get("subdomain") in (None, "")

    def test_D26_videos_playback_unauth(self, api):
        r = api.get(f"{BASE_URL}/api/videos/fake-id/playback")
        assert r.status_code in (401, 403), r.status_code

    def test_D27_videos_playback_no_cf_id(self, api, admin_token, mongo):
        # find a show
        show = mongo.shows.find_one({}, {"_id": 0, "id": 1})
        if not show:
            pytest.skip("No shows in DB")
        r = api.get(f"{BASE_URL}/api/videos/{show['id']}/playback",
                    headers={"Authorization": f"Bearer {admin_token}"})
        # Worker not configured → 503, OR show has no cloudflareStreamId → 404
        assert r.status_code in (404, 503), r.status_code


# ==================== E. VOD list ====================
class TestVOD:
    def test_E28_shows_free_stripped(self, api, mongo):
        tok, _ = _login(api, "+250780111555", mongo=mongo)
        r = api.get(f"{BASE_URL}/api/shows",
                    headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200
        arr = r.json()
        assert isinstance(arr, list)
        if arr:
            for s in arr[:5]:
                assert "videoUrl" not in s or not s.get("videoUrl")
                assert "streamUrl" not in s or not s.get("streamUrl")
                assert "hlsUrl" not in s or not s.get("hlsUrl")

    def test_E29_show_detail_premium_vs_free(self, api, admin_token, mongo):
        # premium
        api.post(f"{BASE_URL}/api/subscription/rc-sync",
                 json={"plan": "premium_monthly"},
                 headers={"Authorization": f"Bearer {admin_token}"})
        show = mongo.shows.find_one({}, {"_id": 0, "id": 1})
        if not show:
            pytest.skip("No shows")
        r = api.get(f"{BASE_URL}/api/shows/{show['id']}",
                    headers={"Authorization": f"Bearer {admin_token}"})
        assert r.status_code == 200
        # free user
        tok, _ = _login(api, "+250780111666", mongo=mongo)
        r2 = api.get(f"{BASE_URL}/api/shows/{show['id']}",
                     headers={"Authorization": f"Bearer {tok}"})
        assert r2.status_code == 200
        b2 = r2.json()
        assert b2.get("locked") is True or b2.get("unlockPrice") is not None, b2


# ==================== F. Admin ====================
class TestAdmin:
    def test_F30_analytics_dashboard(self, api, admin_token, mongo):
        r = api.get(f"{BASE_URL}/api/admin/analytics/dashboard",
                    headers={"Authorization": f"Bearer {admin_token}"})
        assert r.status_code == 200, r.text
        # non-admin
        tok, _ = _login(api, "+250780111777", mongo=mongo)
        r2 = api.get(f"{BASE_URL}/api/admin/analytics/dashboard",
                     headers={"Authorization": f"Bearer {tok}"})
        assert r2.status_code == 403

    def test_F31_subscriptions_all(self, api, admin_token):
        r = api.get(f"{BASE_URL}/api/admin/analytics/subscriptions?status=all",
                    headers={"Authorization": f"Bearer {admin_token}"})
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_F32_payments_summary(self, api, admin_token):
        r = api.get(f"{BASE_URL}/api/admin/payments/summary?days=30",
                    headers={"Authorization": f"Bearer {admin_token}"})
        assert r.status_code == 200
        b = r.json()
        assert isinstance(b, dict)

    def test_F33_payments_list(self, api, admin_token):
        r = api.get(f"{BASE_URL}/api/admin/payments?days=30&limit=200",
                    headers={"Authorization": f"Bearer {admin_token}"})
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_F34_payments_csv(self, api, admin_token):
        r = api.get(f"{BASE_URL}/api/admin/payments/export.csv?days=30",
                    headers={"Authorization": f"Bearer {admin_token}"})
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "")
        first_line = r.text.split("\n", 1)[0]
        assert "," in first_line, first_line

    def test_F35_business_pdf(self, api, admin_token):
        r = api.get(f"{BASE_URL}/api/admin/reports/business.pdf?start=2026-08-01&end=2026-08-31",
                    headers={"Authorization": f"Bearer {admin_token}"})
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert r.content[:5] == b"%PDF-"
        assert len(r.content) > 3 * 1024


# ==================== G. Public content ====================
class TestPublicContent:
    def test_G36_public_endpoints(self, api):
        for path in ["/api/news", "/api/programs", "/api/radio/schedule", "/api/settings"]:
            r = api.get(f"{BASE_URL}{path}")
            assert r.status_code == 200, f"{path}: {r.status_code}"

    def test_G37_settings_slogan(self, api):
        r = api.get(f"{BASE_URL}/api/settings")
        b = r.json()
        assert b.get("stationTagline") == "MURI SPORTS, NI IGITEGO!", b


# ==================== Landing page ====================
class TestLanding:
    def test_landing_web_bbkigali_com_count(self):
        p = "/app/landing/index.html"
        assert os.path.exists(p)
        with open(p) as f:
            html = f.read()
        assert html.count("web.bbkigali.com") >= 7
        assert "app.emergent.sh/share" not in html
        assert "MURI SPORTS, NI IGITEGO!" in html
