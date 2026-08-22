"""
Backend tests for Stripe LIVE payment integration (iteration 7).

CRITICAL: LIVE mode — these tests only create checkout sessions and read them
back. NO payment method is attached; NO card is entered; NO session is
completed. Only server-side session-creation logic + auth boundaries are
verified.

Covers:
  - GET  /api/billing/stripe/config
  - POST /api/billing/stripe/create-checkout (subscription + vod)
  - GET  /api/billing/stripe/session-status/{session_id} (auth boundary)
  - POST /api/billing/stripe/webhook (structural — no valid signature)
  - GET  /api/billing/stripe/return + /cancel (HTML pages)
"""
import os
import pytest
import requests

# All tests share admin OTP challenge state → same xdist worker
pytestmark = pytest.mark.xdist_group(name="stripe_admin_otp_shared")

BASE_URL = os.environ.get(
    "EXPO_PUBLIC_BACKEND_URL",
    "https://radio-vod-platform.preview.emergentagent.com",
).rstrip("/")

ADMIN_PHONE = "+250798875272"
REGULAR_PHONE = "+250788999888"


# ---------------- auth helper ----------------

def _login(phone: str):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    last_err = None
    for _ in range(3):
        r = s.post(f"{BASE_URL}/api/auth/otp/start", json={"phone": phone}, timeout=30)
        assert r.status_code == 200, f"otp/start failed: {r.status_code} {r.text}"
        code = r.json().get("testCode")
        assert code, f"testCode not in response for {phone}: {r.text}"
        r = s.post(
            f"{BASE_URL}/api/auth/otp/verify",
            json={"phone": phone, "code": code},
            timeout=30,
        )
        if r.status_code == 200:
            body = r.json()
            return body["accessToken"], body["user"]
        last_err = f"{r.status_code} {r.text}"
    raise AssertionError(f"otp/verify failed after retries: {last_err}")


@pytest.fixture(scope="module")
def admin_ctx():
    token, user = _login(ADMIN_PHONE)
    return {"token": token, "user": user}


@pytest.fixture(scope="module")
def regular_ctx():
    token, user = _login(REGULAR_PHONE)
    return {"token": token, "user": user}


def _hdr(ctx):
    return {"Authorization": f"Bearer {ctx['token']}", "Content-Type": "application/json"}


# ---------------- 1) config ----------------

class TestStripeConfig:
    def test_config_enabled_live(self, admin_ctx):
        r = requests.get(f"{BASE_URL}/api/billing/stripe/config", headers=_hdr(admin_ctx), timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["enabled"] is True, data
        assert data["publishableKey"].startswith("pk_live_"), data
        assert data["currency"] == "eur", data

    def test_config_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/billing/stripe/config", timeout=30)
        assert r.status_code == 401, r.text


# ---------------- 2) subscription checkout ----------------

class TestStripeSubscriptionCheckout:
    @pytest.mark.parametrize("plan", ["basic_monthly", "basic_yearly", "premium_monthly", "premium_yearly"])
    def test_create_subscription_session_all_plans(self, admin_ctx, plan):
        r = requests.post(
            f"{BASE_URL}/api/billing/stripe/create-checkout",
            headers=_hdr(admin_ctx),
            json={"purchase_type": "subscription", "plan": plan},
            timeout=30,
        )
        assert r.status_code == 200, f"plan={plan} → {r.status_code} {r.text}"
        data = r.json()
        assert data["sessionId"].startswith("cs_live_"), data
        assert data["checkoutUrl"].startswith("https://checkout.stripe.com/"), data
        assert data["publishableKey"].startswith("pk_live_"), data

    def test_create_subscription_invalid_plan(self, admin_ctx):
        # Pydantic Literal validation returns 422 before reaching the 400 branch
        # in server.py:1532-1533. Both are 4xx; the runtime branch is
        # unreachable. Accept either to keep the test truthful.
        r = requests.post(
            f"{BASE_URL}/api/billing/stripe/create-checkout",
            headers=_hdr(admin_ctx),
            json={"purchase_type": "subscription", "plan": "bogus"},
            timeout=30,
        )
        assert r.status_code in (400, 422), r.text

    def test_create_subscription_missing_plan(self, admin_ctx):
        r = requests.post(
            f"{BASE_URL}/api/billing/stripe/create-checkout",
            headers=_hdr(admin_ctx),
            json={"purchase_type": "subscription"},
            timeout=30,
        )
        assert r.status_code == 400, r.text

    def test_create_checkout_no_auth(self):
        r = requests.post(
            f"{BASE_URL}/api/billing/stripe/create-checkout",
            json={"purchase_type": "subscription", "plan": "basic_monthly"},
            timeout=30,
        )
        assert r.status_code == 401, r.text

    def test_regular_user_can_create_subscription(self, regular_ctx):
        r = requests.post(
            f"{BASE_URL}/api/billing/stripe/create-checkout",
            headers=_hdr(regular_ctx),
            json={"purchase_type": "subscription", "plan": "basic_monthly"},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["sessionId"].startswith("cs_live_"), data


# ---------------- 3) VOD checkout ----------------

class TestStripeVodCheckout:
    @pytest.fixture(scope="class")
    def show_id(self, admin_ctx):
        r = requests.get(f"{BASE_URL}/api/shows", headers=_hdr(admin_ctx), timeout=30)
        assert r.status_code == 200, r.text
        shows = r.json()
        assert isinstance(shows, list) and len(shows) > 0, f"no shows: {shows!r}"
        return shows[0]["id"]

    def test_create_vod_session(self, admin_ctx, show_id):
        r = requests.post(
            f"{BASE_URL}/api/billing/stripe/create-checkout",
            headers=_hdr(admin_ctx),
            json={"purchase_type": "vod", "show_id": show_id},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["sessionId"].startswith("cs_live_"), data
        assert data["checkoutUrl"].startswith("https://checkout.stripe.com/"), data

    def test_vod_without_show_id(self, admin_ctx):
        r = requests.post(
            f"{BASE_URL}/api/billing/stripe/create-checkout",
            headers=_hdr(admin_ctx),
            json={"purchase_type": "vod"},
            timeout=30,
        )
        assert r.status_code == 400, r.text

    def test_vod_unknown_show_id(self, admin_ctx):
        r = requests.post(
            f"{BASE_URL}/api/billing/stripe/create-checkout",
            headers=_hdr(admin_ctx),
            json={"purchase_type": "vod", "show_id": "does-not-exist-xyz-123"},
            timeout=30,
        )
        assert r.status_code == 404, r.text


# ---------------- 4) session-status auth boundary ----------------

class TestStripeSessionStatusAuth:
    def test_session_status_belongs_to_owner_only(self, admin_ctx, regular_ctx):
        # user A (admin) creates a session
        r = requests.post(
            f"{BASE_URL}/api/billing/stripe/create-checkout",
            headers=_hdr(admin_ctx),
            json={"purchase_type": "subscription", "plan": "basic_monthly"},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        sid = r.json()["sessionId"]

        # user A can fetch status
        r = requests.get(
            f"{BASE_URL}/api/billing/stripe/session-status/{sid}",
            headers=_hdr(admin_ctx),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert "status" in data, data

        # user B cannot fetch A's session status
        r = requests.get(
            f"{BASE_URL}/api/billing/stripe/session-status/{sid}",
            headers=_hdr(regular_ctx),
            timeout=30,
        )
        assert r.status_code == 404, f"expected 404 for other user, got {r.status_code} {r.text}"

    def test_session_status_no_auth(self):
        r = requests.get(
            f"{BASE_URL}/api/billing/stripe/session-status/cs_live_dummy",
            timeout=30,
        )
        assert r.status_code == 401, r.text


# ---------------- 5) webhook structural ----------------

class TestStripeWebhookStructural:
    def test_webhook_endpoint_accepts_post(self):
        # Send a structurally valid JSON payload without a real signature.
        # STRIPE_WEBHOOK_SECRET is empty in .env, so the code path skips
        # signature verification and just parses the JSON body. We only assert
        # that the endpoint doesn't 404/405 and responds with a JSON body.
        payload = {
            "id": "evt_test_wh_placeholder",
            "type": "checkout.session.completed",
            "data": {"object": {"id": "cs_test_placeholder", "mode": "subscription", "payment_status": "paid"}},
        }
        r = requests.post(
            f"{BASE_URL}/api/billing/stripe/webhook",
            json=payload,
            timeout=30,
        )
        # Route exists (not 404/405). Body may be 200 ok or 400 depending on
        # server-side handling of the fake session id — either is acceptable.
        assert r.status_code in (200, 400), f"unexpected status: {r.status_code} {r.text}"


# ---------------- 6) return + cancel HTML pages ----------------

class TestStripeReturnPages:
    def test_cancel_page_html(self):
        r = requests.get(f"{BASE_URL}/api/billing/stripe/cancel", timeout=30)
        assert r.status_code == 200, r.text
        assert "text/html" in r.headers.get("content-type", ""), r.headers
        assert len(r.text) > 0

    def test_return_page_html(self):
        # session_id query param required by signature
        r = requests.get(
            f"{BASE_URL}/api/billing/stripe/return",
            params={"session_id": "cs_live_dummy_return_test"},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        assert "text/html" in r.headers.get("content-type", ""), r.headers
