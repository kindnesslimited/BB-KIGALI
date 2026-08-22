"""Backend tests for the multi-provider SMS chain (Route Mobile → AT → Twilio → WhatsApp).

Covers:
- GET  /api/admin/sms/providers (auth / admin / shape)
- POST /api/admin/sms/test       (auth / admin / validation / chain behavior)
- POST /api/auth/otp/start       (chain attempts surfaced when SMS fails, dev testCode returned)
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://radio-vod-platform.preview.emergentagent.com").rstrip("/")

ADMIN_PHONE = "+250798875272"
NON_ADMIN_PHONE = "+250788119955"
NON_EXISTENT_USER_PHONE = "+250788999777"


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


# ---------- GET /admin/sms/providers ----------
class TestSmsProvidersEndpoint:
    def test_no_auth_401(self, api):
        r = api.get(f"{BASE_URL}/api/admin/sms/providers")
        assert r.status_code in (401, 403), r.text

    def test_non_admin_403(self, api, non_admin_headers):
        r = api.get(f"{BASE_URL}/api/admin/sms/providers", headers=non_admin_headers)
        assert r.status_code == 403, r.text

    def test_admin_returns_order_and_providers(self, api, admin_headers):
        r = api.get(f"{BASE_URL}/api/admin/sms/providers", headers=admin_headers)
        assert r.status_code == 200, r.text
        j = r.json()

        # Shape
        assert "order" in j and "providers" in j
        assert j["order"] == ["route_mobile", "africas_talking", "twilio", "whatsapp"]

        providers = j["providers"]
        for key in ("route_mobile", "africas_talking", "twilio", "whatsapp"):
            assert key in providers, f"missing provider {key}"
            p = providers[key]
            assert "configured" in p and isinstance(p["configured"], bool)
            assert p.get("notes"), f"{key} notes should be non-empty"

        # In preview env: route_mobile and whatsapp are configured
        assert providers["route_mobile"]["configured"] is True
        assert providers["africas_talking"]["configured"] is False
        assert providers["twilio"]["configured"] is False
        assert providers["whatsapp"]["configured"] is True

        # senderId surfaced for route_mobile, no secrets leaked
        assert providers["route_mobile"].get("senderId") == "BBKIGALI"
        # Make sure no known secret keys are exposed
        blob = str(j).lower()
        for secret_marker in ("password", "auth_token", "api_key", "musso"):
            assert secret_marker not in blob, f"secret exposed: {secret_marker}"


# ---------- POST /admin/sms/test ----------
class TestSmsTestEndpoint:
    def test_no_auth_401(self, api):
        r = api.post(f"{BASE_URL}/api/admin/sms/test", json={"phone": "+250788999888"})
        assert r.status_code in (401, 403)

    def test_non_admin_403(self, api, non_admin_headers):
        r = api.post(
            f"{BASE_URL}/api/admin/sms/test",
            json={"phone": "+250788999888"},
            headers=non_admin_headers,
        )
        assert r.status_code == 403

    def test_invalid_phone_400(self, api, admin_headers):
        r = api.post(
            f"{BASE_URL}/api/admin/sms/test",
            json={"phone": "1"},
            headers=admin_headers,
        )
        assert r.status_code == 400, r.text

    def test_chain_attempts_all_four_providers(self, api, admin_headers):
        r = api.post(
            f"{BASE_URL}/api/admin/sms/test",
            json={"phone": "+250788999888"},
            headers=admin_headers,
        )
        assert r.status_code == 200, r.text
        j = r.json()
        assert "sent" in j and "provider" in j and "attempts" in j

        # In preview env: route_mobile creds are configured but invalid → returns 1703
        # Other 3 have no creds → "not_configured"
        attempts = j["attempts"]
        assert "route_mobile" in attempts
        assert "africas_talking:not_configured" in attempts
        assert "twilio:not_configured" in attempts
        # whatsapp is now configured (nostress.vip) — expect code=... response
        assert "whatsapp:" in attempts and "not_configured" not in attempts.split("whatsapp:")[1].split("|")[0]

        # Since Route Mobile IP whitelist not effective in preview, expect failure
        # But we do NOT assert sent=False strictly, as this could occasionally pass.
        # However Twilio/AT/WhatsApp being not_configured means they were quickly skipped.
        if not j["sent"]:
            assert j["provider"] is None


# ---------- Chain behavior via /auth/otp/start (non-admin, non-existent user) ----------
class TestOtpStartChainBehavior:
    def test_otp_start_returns_testcode_with_attempts_message(self, api):
        r = api.post(
            f"{BASE_URL}/api/auth/otp/start",
            json={"phone": NON_EXISTENT_USER_PHONE},
        )
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("ok") is True
        # testCode should be returned in dev mode because sms actually failed
        # (route_mobile invalid creds in preview)
        assert "testCode" in j, f"expected testCode fallback; got: {j}"
        assert isinstance(j["testCode"], str) and len(j["testCode"]) == 6
        # Message should mention SMS delivery failure with provider snippet
        msg = (j.get("message") or "").lower()
        assert "sms delivery failed" in msg or "dev mode" in msg, msg

    def test_otp_start_admin_phone_uses_universal_code(self, api):
        r = api.post(f"{BASE_URL}/api/auth/otp/start", json={"phone": ADMIN_PHONE})
        assert r.status_code == 200
        j = r.json()
        # Admin phones always resolve to 123456
        assert j.get("testCode") == "123456"

    def test_otp_start_invalid_phone_400(self, api):
        r = api.post(f"{BASE_URL}/api/auth/otp/start", json={"phone": "12"})
        assert r.status_code == 400
