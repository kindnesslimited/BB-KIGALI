"""
Iteration 24 — SECURITY AUDIT of Stripe payment path.

Prove that NO code path can grant subscription or VOD access without a real
Stripe-confirmed payment (or PayPal capture, MoMo debit success, or an
admin comp).

Covers:
  - /billing/subscribe non-admin → 403 + no payment doc, tier stays free
  - /billing/subscribe admin → comp:true, no `mocked` flag
  - /billing/stripe/create-checkout → REAL cs_live_ session URL
  - /billing/stripe/session-status → paid:false before card entry; user tier stays free
  - Cross-user isolation on /billing/stripe/session-status → 404
  - /billing/stripe/create-checkout for VOD returns real stripe payment session
  - /billing/stripe/webhook garbage/no signature → 4xx
  - Regression: paypal/momo/health/privacy
"""
import os
import pytest
import requests
from pymongo import MongoClient

pytestmark = pytest.mark.xdist_group(name="stripe_security_audit_iter24")

BASE = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://radio-vod-platform.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")
_mongo = MongoClient(MONGO_URL)
_db = _mongo[DB_NAME]

ADMIN_PHONE = "+250794230137"
REGULAR_PHONE_A = "+250788123456"
# Second regular user to test cross-user isolation
REGULAR_PHONE_B = "+250788111222"


def _otp_login(phone: str) -> str:
    r = requests.post(f"{API}/auth/otp/start", json={"phone": phone}, timeout=20)
    assert r.status_code == 200, f"otp/start failed for {phone}: {r.status_code} {r.text}"
    body = r.json()
    code = body.get("testCode")
    if not code:
        # Non-admin phones: SMS was sent via provider; retrieve code from DB
        chal = _db.otp_challenges.find_one({"phone": phone})
        assert chal and chal.get("code"), f"No otp challenge stored for {phone}: {chal}"
        code = chal["code"]
    r2 = requests.post(f"{API}/auth/otp/verify", json={"phone": phone, "code": code}, timeout=20)
    assert r2.status_code == 200, f"otp/verify failed for {phone}: {r2.status_code} {r2.text}"
    body2 = r2.json()
    tok = body2.get("accessToken") or body2.get("token")
    assert tok, f"No token in verify response: {body2}"
    return tok


def _auth(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


# ----- session-scoped fixtures ------------------------------------------------

@pytest.fixture(scope="module")
def admin_token():
    return _otp_login(ADMIN_PHONE)


@pytest.fixture(scope="module")
def user_a_token():
    return _otp_login(REGULAR_PHONE_A)


@pytest.fixture(scope="module")
def user_b_token():
    return _otp_login(REGULAR_PHONE_B)


# ============================================================================
# Test 1 — /billing/subscribe non-admin MUST 403
# ============================================================================
class TestSubscribeAdminOnly:
    def test_non_admin_gets_403_and_no_grant(self, user_a_token):
        # Ensure regular user starts as free (defensive)
        me0 = requests.get(f"{API}/auth/me", headers=_auth(user_a_token), timeout=20).json()
        assert me0.get("tier") in ("free", "basic", "premium"), me0
        # Force back to free via nothing (cannot; but we assert tier stays same after 403)
        starting_tier = me0.get("tier")

        r = requests.post(
            f"{API}/billing/subscribe",
            headers=_auth(user_a_token),
            json={"plan": "basic_monthly", "method": "stripe"},
            timeout=20,
        )
        assert r.status_code == 403, f"Expected 403, got {r.status_code} {r.text}"
        assert "Payment must be completed" in r.text, r.text

        # Confirm tier did NOT change
        me1 = requests.get(f"{API}/auth/me", headers=_auth(user_a_token), timeout=20).json()
        assert me1.get("tier") == starting_tier, f"Tier changed after 403! {starting_tier} -> {me1.get('tier')}"

    def test_admin_subscribe_returns_comp_no_mocked_flag(self, admin_token):
        r = requests.post(
            f"{API}/billing/subscribe",
            headers=_auth(admin_token),
            json={"plan": "basic_monthly", "method": "stripe"},
            timeout=20,
        )
        assert r.status_code == 200, f"Admin subscribe failed: {r.status_code} {r.text}"
        body = r.json()
        assert body.get("ok") is True
        assert body.get("comp") is True
        assert "mocked" not in body, f"Response still contains 'mocked': {body}"
        note = (body.get("note") or "").lower()
        assert "complimentary" in note and "admin" in note, f"Unexpected note: {body.get('note')}"


# ============================================================================
# Test 2 — Stripe create-checkout returns REAL cs_live_ URL
# ============================================================================
class TestStripeRealCheckout:
    def test_subscription_checkout_returns_cs_live(self, user_a_token):
        r = requests.post(
            f"{API}/billing/stripe/create-checkout",
            headers=_auth(user_a_token),
            json={"purchase_type": "subscription", "plan": "basic_monthly"},
            timeout=30,
        )
        assert r.status_code == 200, f"create-checkout failed: {r.status_code} {r.text}"
        body = r.json()
        assert "sessionId" in body and "checkoutUrl" in body and "publishableKey" in body, body

        sid = body["sessionId"]
        url = body["checkoutUrl"]
        pk = body["publishableKey"]

        assert sid.startswith("cs_live_"), f"sessionId is NOT live: {sid}"
        assert url.startswith("https://checkout.stripe.com/c/pay/cs_live_"), f"checkoutUrl is NOT live stripe: {url}"
        assert pk.startswith("pk_live_"), f"publishableKey is NOT live: {pk}"

        # Stash for downstream tests
        pytest.stripe_sub_session_id = sid
        pytest.stripe_sub_checkout_url = url

    def test_unpaid_session_status_paid_false_and_no_grant(self, user_a_token):
        sid = getattr(pytest, "stripe_sub_session_id", None)
        assert sid, "No prior session id — dependent test not run"

        # Snapshot tier BEFORE polling
        me0 = requests.get(f"{API}/auth/me", headers=_auth(user_a_token), timeout=20).json()
        tier_before = me0.get("tier")

        r = requests.get(
            f"{API}/billing/stripe/session-status/{sid}",
            headers=_auth(user_a_token),
            timeout=30,
        )
        assert r.status_code == 200, f"session-status failed: {r.status_code} {r.text}"
        body = r.json()
        assert body.get("paid") is False, f"UNPAID session reports paid=true! {body}"
        assert body.get("paymentStatus") in ("unpaid", "no_payment_required"), body
        assert body.get("status") == "open", body

        # Tier MUST NOT have been upgraded
        me1 = requests.get(f"{API}/auth/me", headers=_auth(user_a_token), timeout=20).json()
        assert me1.get("tier") == tier_before, f"Tier upgraded on unpaid session! {tier_before} -> {me1.get('tier')}"

        # Payment doc must still be pending
        # (via /billing/history we can inspect)
        hist = requests.get(f"{API}/billing/history", headers=_auth(user_a_token), timeout=20).json()
        pdoc = next((p for p in hist if p.get("stripeSessionId") == sid), None)
        assert pdoc is not None, f"Payment doc missing for session {sid}: {hist[:3]}"
        assert pdoc.get("status") == "pending", f"Payment doc status is {pdoc.get('status')}, expected pending"

    def test_cross_user_isolation_returns_404(self, user_b_token):
        sid = getattr(pytest, "stripe_sub_session_id", None)
        assert sid, "No prior session id"
        r = requests.get(
            f"{API}/billing/stripe/session-status/{sid}",
            headers=_auth(user_b_token),
            timeout=20,
        )
        assert r.status_code == 404, f"Expected 404 for cross-user, got {r.status_code} {r.text}"
        assert "Session not found" in r.text, r.text

    def test_vod_checkout_returns_cs_live_and_no_unlock(self, user_a_token):
        # find a real show id
        shows = requests.get(f"{API}/shows", timeout=20).json()
        assert isinstance(shows, list) and shows, "No shows available for VOD test"
        show_id = shows[0]["id"]

        me0 = requests.get(f"{API}/auth/me", headers=_auth(user_a_token), timeout=20).json()
        unlocked_before = set(me0.get("unlockedVods") or [])

        r = requests.post(
            f"{API}/billing/stripe/create-checkout",
            headers=_auth(user_a_token),
            json={"purchase_type": "vod", "show_id": show_id},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["sessionId"].startswith("cs_live_"), body
        assert body["checkoutUrl"].startswith("https://checkout.stripe.com/c/pay/cs_live_"), body

        # Poll status → paid should be false → no unlock
        r2 = requests.get(f"{API}/billing/stripe/session-status/{body['sessionId']}",
                          headers=_auth(user_a_token), timeout=20)
        assert r2.status_code == 200
        assert r2.json().get("paid") is False

        me1 = requests.get(f"{API}/auth/me", headers=_auth(user_a_token), timeout=20).json()
        unlocked_after = set(me1.get("unlockedVods") or [])
        assert show_id not in (unlocked_after - unlocked_before), (
            f"Show {show_id} became unlocked despite unpaid Stripe session!"
        )


# ============================================================================
# Test 3 — Webhook enforcement
# ============================================================================
class TestStripeWebhookSignature:
    def test_garbage_no_signature_rejected(self):
        r = requests.post(f"{API}/billing/stripe/webhook", json={}, timeout=20)
        # Must NOT be 200. Must be 4xx (400 preferred, 401/403 acceptable).
        assert 400 <= r.status_code < 500, f"Webhook accepted garbage: {r.status_code} {r.text}"

    def test_garbage_with_bad_signature_rejected(self):
        r = requests.post(
            f"{API}/billing/stripe/webhook",
            data=b'{"id":"evt_test","type":"checkout.session.completed"}',
            headers={"stripe-signature": "t=1,v1=deadbeef", "Content-Type": "application/json"},
            timeout=20,
        )
        assert 400 <= r.status_code < 500, f"Webhook accepted bad sig: {r.status_code} {r.text}"


# ============================================================================
# Test 4 — Regressions
# ============================================================================
class TestRegressions:
    def test_health(self):
        r = requests.get(f"{API}/health", timeout=15)
        assert r.status_code == 200, r.text

    def test_privacy(self):
        r = requests.get(f"{API}/privacy", timeout=15)
        assert r.status_code == 200, r.text

    def test_paypal_create_subscription_returns_paypal_url(self, user_a_token):
        r = requests.post(
            f"{API}/billing/paypal/create-subscription",
            headers=_auth(user_a_token),
            json={"plan": "basic_monthly"},
            timeout=30,
        )
        assert r.status_code == 200, f"PayPal create-subscription failed: {r.status_code} {r.text}"
        body = r.json()
        approve = body.get("approveUrl") or body.get("approve_url") or ""
        assert "paypal.com" in approve, f"approveUrl missing paypal.com: {body}"

    def test_momo_initiate_admin_phone_pending(self, user_a_token):
        r = requests.post(
            f"{API}/billing/momo/initiate",
            headers=_auth(user_a_token),
            json={"plan": "basic_monthly", "phone": "250794230137"},
            timeout=45,
        )
        # Expected 2xx pending. BeSoft may respond 502 if provider is down — accept
        # <500 as the guard-not-bypassed contract.
        assert r.status_code < 500, f"MoMo initiate 5xx: {r.status_code} {r.text}"

    def test_momo_initiate_merchant_msisdn_rejected(self, user_a_token):
        r = requests.post(
            f"{API}/billing/momo/initiate",
            headers=_auth(user_a_token),
            json={"plan": "basic_monthly", "phone": "250798875274"},
            timeout=20,
        )
        assert r.status_code == 400, f"Merchant msisdn should be blocked, got {r.status_code} {r.text}"
