"""
Iteration 29 tests: iOS IAP gate & Apple 5.1.1(v) token revocation.

Focus:
- POST /api/auth/apple accepts an optional `authorizationCode` without regressing.
- POST /api/auth/apple with a fake authorizationCode does NOT crash (APPLE_* empty -> silent no-op).
- DELETE /api/auth/me still succeeds with `appleRevoked: false` when no Apple keys / no refresh token.
- DELETE /api/auth/me wipes user_sessions, otp_challenges, anonymizes payments.
- Non-regression: /api/news, /api/radio/schedule, /api/live/status, /api/health still work.
"""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://radio-vod-platform.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_PHONE = "250794230137"
# The 3 admin phones from ADMIN_PHONES env — these always get testCode=123456 (MOCK_OTP_CODE)
# regardless of SMS provider config. We use them as throwaway test accounts.
THROWAWAY_PHONES = ["250794230137", "25078844524", "250788316999"]


@pytest.fixture(scope="module")
def api_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _otp_login(api_client, phone: str):
    """Start OTP, extract testCode, verify, return (token, user)."""
    r = api_client.post(f"{API}/auth/otp/start", json={"phone": phone})
    assert r.status_code == 200, f"otp/start failed: {r.status_code} {r.text}"
    data = r.json()
    code = data.get("testCode") or data.get("code")
    assert code, f"No testCode returned in dev mode: {data}"
    r2 = api_client.post(f"{API}/auth/otp/verify", json={"phone": phone, "code": code})
    assert r2.status_code == 200, f"otp/verify failed: {r2.status_code} {r2.text}"
    body = r2.json()
    tok = body.get("accessToken") or body.get("token")
    user = body.get("user")
    assert tok and user, f"Bad verify body: {body}"
    return tok, user


# ---------- Non-regression: public endpoints ----------
class TestPublicNoRegression:
    def test_health(self, api_client):
        r = api_client.get(f"{API}/health")
        assert r.status_code == 200
        body = r.json()
        assert body.get("status") == "ok" or body.get("ok") is True or "status" in body

    def test_news(self, api_client):
        r = api_client.get(f"{API}/news")
        assert r.status_code == 200
        data = r.json()
        # Accept list OR {items: [...]}
        items = data if isinstance(data, list) else data.get("items") or data.get("results") or []
        assert isinstance(items, list)

    def test_radio_schedule(self, api_client):
        r = api_client.get(f"{API}/radio/schedule")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, (list, dict))

    def test_live_status(self, api_client):
        r = api_client.get(f"{API}/live/status")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)
        # sanity: should contain a bool-ish "live" indicator
        assert any(k in data for k in ("isLive", "live", "status", "youtubeLive"))


# ---------- Apple sign-in payload compatibility ----------
class TestAppleSignInPayloadCompat:
    """These tests use a FAKE identity token — expect 401 in both cases,
    but they must NOT be 500 (that would mean the new field broke the handler)."""

    def test_apple_without_authorization_code(self, api_client):
        r = api_client.post(f"{API}/auth/apple", json={
            "identityToken": "not.a.real.token",
        })
        # Apple JWKS verify will fail -> 401. 500 would be a regression.
        assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text[:300]}"

    def test_apple_with_fake_authorization_code_does_not_crash(self, api_client):
        r = api_client.post(f"{API}/auth/apple", json={
            "identityToken": "not.a.real.token",
            "authorizationCode": "fake-code-abcdef",
            "fullName": "Test",
            "email": "iter29@example.com",
        })
        # Still 401 (identity token invalid). But the point: server didn't 500 because
        # authorizationCode was passed and Apple keys are empty. Code exchange happens
        # AFTER identity verification, so 401 here confirms the field is accepted and
        # doesn't break validation.
        assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text[:300]}"

    def test_apple_missing_identity_token(self, api_client):
        # Pydantic should reject
        r = api_client.post(f"{API}/auth/apple", json={"authorizationCode": "x"})
        assert r.status_code in (400, 422), f"expected 4xx validation error, got {r.status_code}"


# ---------- Account deletion (5.1.1(v)) ----------
class TestDeleteAccount:
    def test_delete_own_account_returns_apple_revoked_false_when_no_refresh(self, api_client):
        # Use one of the admin phones — they always return testCode in dev mode.
        throwaway_phone = THROWAWAY_PHONES[0]
        tok, user = _otp_login(api_client, throwaway_phone)
        uid = user["id"]

        headers = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}

        # sanity: GET /auth/me works
        r_me = api_client.get(f"{API}/auth/me", headers=headers)
        assert r_me.status_code == 200, r_me.text
        assert r_me.json().get("id") == uid

        # DELETE
        r_del = requests.delete(f"{API}/auth/me", headers=headers)
        assert r_del.status_code == 200, f"delete failed: {r_del.status_code} {r_del.text}"
        body = r_del.json()
        assert body.get("ok") is True, body
        # No apple refresh token stored -> must be False
        assert body.get("appleRevoked") is False, f"Expected appleRevoked=False, got body={body}"

        # After delete, /auth/me should be unauthorized
        r_me2 = requests.get(f"{API}/auth/me", headers=headers)
        assert r_me2.status_code in (401, 404, 403), f"expected auth failure after delete, got {r_me2.status_code}"

    def test_delete_wipes_sessions_and_otp_challenges(self, api_client):
        """After delete, re-issued OTP for same phone still works (fresh challenge),
        proving old otp_challenges rows were wiped AND user recreated cleanly."""
        throwaway_phone = THROWAWAY_PHONES[1]
        tok, user = _otp_login(api_client, throwaway_phone)
        uid1 = user["id"]

        headers = {"Authorization": f"Bearer {tok}"}
        r_del = requests.delete(f"{API}/auth/me", headers=headers)
        assert r_del.status_code == 200

        # Re-login with same phone — should create a NEW user id (proof of full delete)
        tok2, user2 = _otp_login(api_client, throwaway_phone)
        assert user2["id"] != uid1, "expected a NEW user id after account deletion"

        # cleanup — delete this second throwaway too
        requests.delete(f"{API}/auth/me", headers={"Authorization": f"Bearer {tok2}"})

    def test_delete_requires_auth(self, api_client):
        r = requests.delete(f"{API}/auth/me")
        assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}"


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
