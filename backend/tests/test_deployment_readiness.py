"""
Iteration 16 — Deployment-readiness verification.

Verifies:
1. Health probes (root-level /health + /api/health) return correct shape
2. Phone-OTP auth still works with new JWT_SECRET
3. Previously-working endpoints still function (shows, categories, admin/*, billing/*)
"""
import os
import requests
import pytest

BASE_URL = os.environ.get("EXPO_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # Fallback to internal (still uses /api routing via ingress internally on 8001)
    BASE_URL = "http://localhost:8001"

ADMIN_PHONE = "+250798875272"


# ---------- Shared fixtures ----------

@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def admin_token(api):
    """Full OTP login flow -> return accessToken (JWT)."""
    r1 = api.post(f"{BASE_URL}/api/auth/otp/start", json={"phone": ADMIN_PHONE}, timeout=15)
    assert r1.status_code == 200, f"otp/start failed: {r1.status_code} {r1.text}"
    body = r1.json()
    test_code = body.get("testCode") or body.get("code")
    assert test_code, f"testCode not returned (SMS_DEV_RETURN_CODE off?): {body}"

    r2 = api.post(
        f"{BASE_URL}/api/auth/otp/verify",
        json={"phone": ADMIN_PHONE, "code": test_code},
        timeout=15,
    )
    assert r2.status_code == 200, f"otp/verify failed: {r2.status_code} {r2.text}"
    v = r2.json()
    token = v.get("accessToken") or v.get("token") or v.get("session_token")
    assert token and token.startswith("eyJ"), f"JWT not returned (or wrong format): {v}"
    return token


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


# ---------- 1. Health probes ----------

class TestHealthProbes:
    def test_root_health_shape(self, api):
        r = api.get(f"{BASE_URL}/health", timeout=10)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok") is True
        assert data.get("service") == "bb-fm-kigali"
        assert data.get("db") == "ok"

    def test_api_health_shape(self, api):
        r = api.get(f"{BASE_URL}/api/health", timeout=10)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok") is True
        assert data.get("service") == "bb-fm-kigali"
        assert data.get("db") == "ok"
        assert data.get("stripe") is True
        providers = data.get("sms_providers")
        assert isinstance(providers, list)
        assert "route_mobile" in providers
        assert "whatsapp" in providers


# ---------- 2. Auth still works with new JWT_SECRET ----------

class TestAuthAfterJWTChange:
    def test_otp_start_returns_test_code(self, api):
        r = api.post(f"{BASE_URL}/api/auth/otp/start", json={"phone": ADMIN_PHONE}, timeout=15)
        assert r.status_code == 200, r.text
        b = r.json()
        assert b.get("testCode") or b.get("code"), f"testCode missing: {b}"

    def test_otp_verify_returns_jwt(self, api):
        r1 = api.post(f"{BASE_URL}/api/auth/otp/start", json={"phone": ADMIN_PHONE}, timeout=15)
        code = r1.json().get("testCode") or r1.json().get("code")
        r2 = api.post(
            f"{BASE_URL}/api/auth/otp/verify",
            json={"phone": ADMIN_PHONE, "code": code},
            timeout=15,
        )
        assert r2.status_code == 200, r2.text
        tok = r2.json().get("accessToken") or r2.json().get("token")
        assert tok and tok.startswith("eyJ"), f"JWT not valid: {tok}"

    def test_admin_users_with_new_jwt(self, api, admin_headers):
        """Proves JWT signed with new JWT_SECRET validates correctly."""
        r = api.get(f"{BASE_URL}/api/admin/users", headers=admin_headers, timeout=15)
        assert r.status_code == 200, r.text
        # Response should be a list or dict with users
        data = r.json()
        assert data is not None


# ---------- 3. Existing endpoints still work ----------

class TestExistingEndpoints:
    def test_guest_shows(self, api):
        r = api.get(f"{BASE_URL}/api/shows", timeout=15)
        assert r.status_code == 200, r.text

    def test_guest_categories(self, api):
        r = api.get(f"{BASE_URL}/api/categories", timeout=15)
        assert r.status_code == 200, r.text

    def test_admin_sms_providers(self, api, admin_headers):
        r = api.get(f"{BASE_URL}/api/admin/sms/providers", headers=admin_headers, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        # Expect whatsapp.configured:true
        # Handle both dict-of-providers and list shape
        wa = None
        if isinstance(data, dict):
            wa = data.get("whatsapp") or data.get("providers", {}).get("whatsapp")
            if wa is None and "providers" in data and isinstance(data["providers"], list):
                for p in data["providers"]:
                    if p.get("name") == "whatsapp" or p.get("id") == "whatsapp":
                        wa = p
                        break
        elif isinstance(data, list):
            for p in data:
                if p.get("name") == "whatsapp" or p.get("id") == "whatsapp":
                    wa = p
                    break
        assert wa is not None, f"whatsapp not in providers response: {data}"
        assert wa.get("configured") is True, f"whatsapp.configured != true: {wa}"

    def test_admin_payments_summary(self, api, admin_headers):
        r = api.get(
            f"{BASE_URL}/api/admin/payments/summary?days=30",
            headers=admin_headers,
            timeout=15,
        )
        assert r.status_code == 200, r.text

    def test_momo_initiate_safety_guard(self, api, admin_headers):
        r = api.post(
            f"{BASE_URL}/api/billing/momo/initiate",
            json={"plan": "basic_monthly", "phone": ADMIN_PHONE},
            headers=admin_headers,
            timeout=20,
        )
        assert r.status_code == 400, f"expected 400 safety guard, got {r.status_code}: {r.text}"
        body_text = r.text.lower()
        assert "collection" in body_text, f"'collection account' message missing: {r.text}"

    def test_stripe_checkout_creation(self, api, admin_headers):
        r = api.post(
            f"{BASE_URL}/api/billing/stripe/create-checkout",
            json={"purchase_type": "subscription", "plan": "basic_monthly"},
            headers=admin_headers,
            timeout=25,
        )
        assert r.status_code == 200, f"stripe checkout failed: {r.status_code} {r.text}"
        d = r.json()
        session_id = d.get("sessionId") or d.get("session_id") or d.get("id")
        assert session_id, f"sessionId missing: {d}"
        assert session_id.startswith("cs_live_"), f"expected cs_live_ prefix: {session_id}"
