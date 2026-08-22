"""Backend tests for WhatsApp OTP integration + SMS analytics dashboard + Stripe webhook secret.

Scope (per iteration 9 review request):
- WhatsApp integration (nostress.vip) — provider config, code format
- POST /api/admin/sms/test records attempt and returns whatsapp response
- GET  /api/admin/sms/analytics — shape, all-4-providers, days range, auth
- GET  /api/billing/stripe/config — still enabled; STRIPE_WEBHOOK_SECRET env set
"""
import os
import inspect
import pytest
import requests

BASE_URL = os.environ.get(
    "EXPO_PUBLIC_BACKEND_URL",
    "https://radio-vod-platform.preview.emergentagent.com",
).rstrip("/")

ADMIN_PHONE = "+250798875272"
NON_ADMIN_PHONE = "+250788446699"


# ---------- fixtures ----------
@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _login(api, phone):
    r = api.post(f"{BASE_URL}/api/auth/otp/start", json={"phone": phone})
    assert r.status_code == 200, r.text
    code = r.json().get("testCode") or "123456"
    r = api.post(f"{BASE_URL}/api/auth/otp/verify", json={"phone": phone, "code": code})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def admin_headers(api):
    j = _login(api, ADMIN_PHONE)
    assert j["user"]["role"] == "admin"
    token = j.get("accessToken") or j.get("token")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def non_admin_headers(api):
    j = _login(api, NON_ADMIN_PHONE)
    assert j["user"]["role"] != "admin"
    token = j.get("accessToken") or j.get("token")
    return {"Authorization": f"Bearer {token}"}


# ---------- WhatsApp provider config ----------
class TestWhatsAppProviderConfig:
    """GET /api/admin/sms/providers should surface WhatsApp as configured with nostress.vip endpoint."""

    def test_whatsapp_configured_and_endpoint_visible(self, api, admin_headers):
        r = api.get(f"{BASE_URL}/api/admin/sms/providers", headers=admin_headers)
        assert r.status_code == 200, r.text
        wa = r.json()["providers"]["whatsapp"]
        assert wa["configured"] is True, "WhatsApp must be configured"
        assert wa["endpoint"], "WhatsApp endpoint must be surfaced in response"
        assert wa["endpoint"].startswith("https://whatsapp.nostress.vip/api_com.php"), (
            f"Unexpected WhatsApp endpoint: {wa['endpoint']}"
        )


# ---------- WhatsApp source code format assertions ----------
class TestWhatsAppRequestFormat:
    """Static inspection of _sms_whatsapp to confirm exact request format required by nostress.vip."""

    def test_source_uses_correct_request_shape(self):
        import sys
        sys.path.insert(0, "/app/backend")
        import server  # noqa: E402
        src = inspect.getsource(server._sms_whatsapp)
        # POST via httpx AsyncClient
        assert "c.post(" in src, "must use POST"
        # URL from env var
        assert "WHATSAPP_API_URL" in src
        # JSON body keys
        for key in ('"action"', '"auth"', '"tel"', '"msg"'):
            assert key in src, f"missing JSON key {key} in _sms_whatsapp"
        # action=send
        assert '"send"' in src
        # tel stripped of +
        assert 'lstrip("+")' in src, "tel must strip leading +"
        # token from env var
        assert "WHATSAPP_API_TOKEN" in src
        # Content-Type json
        assert "application/json" in src
        # Success code 110
        assert '"110"' in src


# ---------- SMS test endpoint records analytics ----------
class TestSmsTestRecordsAttempt:
    """POST /api/admin/sms/test should exercise all 4 providers and record whatsapp response with code=xxx."""

    @pytest.fixture(scope="class")
    def test_result(self, api, admin_headers):
        r = api.post(
            f"{BASE_URL}/api/admin/sms/test",
            json={"phone": ADMIN_PHONE, "message": "TEST_whatsapp_analytics_probe"},
            headers=admin_headers,
        )
        assert r.status_code == 200, r.text
        return r.json()

    def test_response_shape(self, test_result):
        assert "sent" in test_result
        assert "provider" in test_result
        assert "attempts" in test_result

    def test_all_four_providers_attempted(self, test_result):
        attempts = test_result["attempts"]
        for name in ("route_mobile", "africas_talking", "twilio", "whatsapp"):
            assert name in attempts, f"provider {name} not in attempts: {attempts}"

    def test_whatsapp_response_has_code_number(self, test_result):
        """Whatsapp must return either code=110 (success) or code=101 (invalid token) — proving correct format."""
        attempts = test_result["attempts"]
        wa_segment = attempts.split("whatsapp:", 1)[1] if "whatsapp:" in attempts else ""
        assert wa_segment, f"no whatsapp segment: {attempts}"
        # Either accepted (110) or invalid token (101) means the request format is correct
        assert ("code=110" in wa_segment) or ("code=101" in wa_segment), (
            f"whatsapp response format unexpected — got: {wa_segment}. "
            f"Expected code=110 (success) or code=101 (invalid token)."
        )


# ---------- SMS Analytics endpoint ----------
class TestSmsAnalyticsAuth:
    def test_no_auth_401_or_403(self, api):
        r = api.get(f"{BASE_URL}/api/admin/sms/analytics?days=7")
        assert r.status_code in (401, 403), r.text

    def test_non_admin_403(self, api, non_admin_headers):
        r = api.get(f"{BASE_URL}/api/admin/sms/analytics?days=7", headers=non_admin_headers)
        assert r.status_code == 403, r.text


class TestSmsAnalyticsShape:
    def test_default_response_shape(self, api, admin_headers):
        r = api.get(f"{BASE_URL}/api/admin/sms/analytics", headers=admin_headers)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "windowDays" in j
        assert "totals" in j
        for k in ("attempts", "delivered", "successRate"):
            assert k in j["totals"], f"totals missing {k}"
        assert "providers" in j and isinstance(j["providers"], list)
        assert "byDay" in j and isinstance(j["byDay"], list)

    def test_all_four_providers_present(self, api, admin_headers):
        r = api.get(f"{BASE_URL}/api/admin/sms/analytics?days=7", headers=admin_headers)
        assert r.status_code == 200, r.text
        j = r.json()
        names = {p["provider"] for p in j["providers"]}
        assert names == {"route_mobile", "africas_talking", "twilio", "whatsapp"}, (
            f"expected exactly 4 providers, got {names}"
        )
        for p in j["providers"]:
            for k in ("provider", "attempts", "delivered", "skipped", "successRate"):
                assert k in p, f"provider row missing {k}: {p}"
            assert isinstance(p["successRate"], (int, float))
            assert 0.0 <= p["successRate"] <= 1.0

    def test_days_ranges(self, api, admin_headers):
        for days in (1, 7, 30):
            r = api.get(f"{BASE_URL}/api/admin/sms/analytics?days={days}", headers=admin_headers)
            assert r.status_code == 200, f"days={days}: {r.text}"
            assert r.json()["windowDays"] == days

    def test_whatsapp_attempt_recorded_after_test_sms(self, api, admin_headers):
        # Fire an sms test first
        r = api.post(
            f"{BASE_URL}/api/admin/sms/test",
            json={"phone": ADMIN_PHONE, "message": "TEST_analytics_probe"},
            headers=admin_headers,
        )
        assert r.status_code == 200, r.text
        # Now analytics should reflect at least 1 whatsapp attempt (not skipped)
        r = api.get(f"{BASE_URL}/api/admin/sms/analytics?days=7", headers=admin_headers)
        assert r.status_code == 200
        wa = next(p for p in r.json()["providers"] if p["provider"] == "whatsapp")
        assert wa["attempts"] >= 1, f"expected whatsapp attempts>=1, got {wa}"


# ---------- Stripe webhook secret env ----------
class TestStripeWebhookSecretEnv:
    def test_stripe_config_still_enabled(self, api, admin_headers):
        r = api.get(f"{BASE_URL}/api/billing/stripe/config", headers=admin_headers)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("enabled") is True, f"stripe config not enabled: {j}"

    def test_webhook_secret_env_set(self):
        """STRIPE_WEBHOOK_SECRET must be set in backend process env (do NOT expose value in any response)."""
        # Read backend .env directly (process env not shared with test runner)
        env_path = "/app/backend/.env"
        val = None
        with open(env_path) as f:
            for line in f:
                if line.startswith("STRIPE_WEBHOOK_SECRET="):
                    val = line.strip().split("=", 1)[1].strip('"').strip("'")
                    break
        assert val and val.startswith("whsec_"), "STRIPE_WEBHOOK_SECRET missing or malformed in backend/.env"

    def test_webhook_secret_not_leaked_in_stripe_config(self, api, admin_headers):
        r = api.get(f"{BASE_URL}/api/billing/stripe/config", headers=admin_headers)
        assert r.status_code == 200
        blob = str(r.json()).lower()
        assert "whsec_" not in blob, "webhook secret must not be exposed to clients"
