"""
Backend smoke tests for BB FM Kigali config changes:
- streamUrlHttps propagation on /api/radio/now-playing
- Apple sign-in revocation env readiness + ES256 client_secret generation
- Admin settings PUT round-trip (radioStreamUrlHttps set / clear / restore)
- Regression on public endpoints and OTP flow
"""
import os
import sys
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

# Load backend .env so we can call apple_auth helpers directly
BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env")
sys.path.insert(0, str(BACKEND_DIR))

# Use the same public URL that the frontend uses
BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL") or os.environ.get("PUBLIC_BASE_URL") or "http://localhost:8001"
BASE_URL = BASE_URL.rstrip("/")

ADMIN_PHONE = "250794230137"
DEV_OTP = "123456"
EXPECTED_STREAM_URL = "http://radio.bbkigali.com:8080/stream"
EXPECTED_STREAM_URL_HTTPS = "https://stream.bbkigali.com/stream/1/"


@pytest.fixture(scope="session")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def admin_token(api):
    # Start OTP for admin phone
    r = api.post(f"{BASE_URL}/api/auth/otp/start", json={"phone": ADMIN_PHONE})
    assert r.status_code == 200, f"otp/start failed: {r.status_code} {r.text}"
    body = r.json()
    code = body.get("testCode") or DEV_OTP
    # Verify OTP
    r = api.post(f"{BASE_URL}/api/auth/otp/verify", json={"phone": ADMIN_PHONE, "code": code})
    if r.status_code != 200 and code != DEV_OTP:
        # Fallback to hardcoded dev bypass
        r = api.post(f"{BASE_URL}/api/auth/otp/verify", json={"phone": ADMIN_PHONE, "code": DEV_OTP})
    assert r.status_code == 200, f"otp/verify failed: {r.status_code} {r.text}"
    body = r.json()
    token = body.get("accessToken") or body.get("token")
    assert token, f"no accessToken in response: {body}"
    return token


# ---------- Apple sign-in revocation config ----------

class TestAppleAuthConfig:
    def test_apple_revocation_ready_true(self):
        from apple_auth import apple_revocation_ready
        assert apple_revocation_ready() is True, "APPLE_* env vars not fully configured"

    def test_apple_client_secret_generation(self):
        import jwt
        from apple_auth import _make_apple_client_secret
        secret = _make_apple_client_secret()
        assert isinstance(secret, str) and len(secret) > 0
        header = jwt.get_unverified_header(secret)
        assert header["alg"] == "ES256"
        assert header["kid"] == os.environ["APPLE_KEY_ID"].strip()
        # decode payload without signature verification
        payload = jwt.decode(secret, options={"verify_signature": False})
        assert payload["iss"] == os.environ["APPLE_TEAM_ID"].strip()
        assert payload["sub"] == os.environ["APPLE_CLIENT_ID"].strip()
        assert payload["aud"] == "https://appleid.apple.com"


# ---------- Radio now-playing streamUrlHttps ----------

class TestRadioNowPlaying:
    def test_now_playing_includes_stream_urls(self, api):
        r = api.get(f"{BASE_URL}/api/radio/now-playing")
        assert r.status_code == 200, r.text
        data = r.json()
        assert "streamUrl" in data, "streamUrl missing"
        assert "streamUrlHttps" in data, "streamUrlHttps missing"
        assert data["streamUrl"] == EXPECTED_STREAM_URL
        assert data["streamUrlHttps"] == EXPECTED_STREAM_URL_HTTPS

    def test_now_playing_public_no_auth(self, api):
        # Ensure endpoint is public
        r = requests.get(f"{BASE_URL}/api/radio/now-playing")
        assert r.status_code == 200


# ---------- Admin settings round-trip ----------

class TestAdminSettingsRoundTrip:
    def test_set_and_get_https_stream(self, api, admin_token):
        headers = {"Authorization": f"Bearer {admin_token}"}
        r = api.put(
            f"{BASE_URL}/api/admin/settings",
            json={"radioStreamUrlHttps": EXPECTED_STREAM_URL_HTTPS},
            headers=headers,
        )
        assert r.status_code == 200, f"PUT failed: {r.status_code} {r.text}"
        # Verify via now-playing
        r2 = api.get(f"{BASE_URL}/api/radio/now-playing")
        assert r2.status_code == 200
        assert r2.json().get("streamUrlHttps") == EXPECTED_STREAM_URL_HTTPS

    def test_clear_https_stream(self, api, admin_token):
        headers = {"Authorization": f"Bearer {admin_token}"}
        r = api.put(
            f"{BASE_URL}/api/admin/settings",
            json={"radioStreamUrlHttps": ""},
            headers=headers,
        )
        assert r.status_code == 200, f"clear PUT failed: {r.status_code} {r.text}"
        r2 = api.get(f"{BASE_URL}/api/radio/now-playing")
        assert r2.status_code == 200
        val = r2.json().get("streamUrlHttps")
        assert val in (None, ""), f"expected null/empty streamUrlHttps after clear, got: {val!r}"

    def test_restore_https_stream(self, api, admin_token):
        headers = {"Authorization": f"Bearer {admin_token}"}
        r = api.put(
            f"{BASE_URL}/api/admin/settings",
            json={"radioStreamUrlHttps": EXPECTED_STREAM_URL_HTTPS},
            headers=headers,
        )
        assert r.status_code == 200
        r2 = api.get(f"{BASE_URL}/api/radio/now-playing")
        assert r2.json().get("streamUrlHttps") == EXPECTED_STREAM_URL_HTTPS


# ---------- Regression: public endpoints ----------

class TestRegressionPublicEndpoints:
    def test_live_status_public_hides_playback_fields(self, api):
        r = api.get(f"{BASE_URL}/api/live/status")
        assert r.status_code == 200, r.text
        data = r.json()
        # For unauthenticated users, playback fields should be stripped
        for f in ("watchUrl", "embedUrl", "videoId"):
            assert data.get(f) in (None, ""), f"{f} should not be exposed to unauthenticated users, got: {data.get(f)!r}"

    def test_radio_schedule_public(self, api):
        r = api.get(f"{BASE_URL}/api/radio/schedule")
        assert r.status_code == 200, r.text
        assert isinstance(r.json(), list)

    def test_vod_videos_public(self, api):
        # Note: review request mentioned /api/vod/videos but actual public VOD list
        # endpoint is /api/shows (verified via grep of server.py). Both are checked
        # here so we surface any 404 to the main agent.
        r = api.get(f"{BASE_URL}/api/shows")
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list), f"expected list, got: {type(data).__name__}"

    def test_vod_videos_alt_path_reports_404(self, api):
        # Documenting that /api/vod/videos does not exist (review request typo).
        r = api.get(f"{BASE_URL}/api/vod/videos")
        assert r.status_code == 404


# ---------- Regression: OTP auth flow ----------

class TestOtpAuthFlow:
    def test_otp_start_and_verify_returns_access_token(self, api):
        r = api.post(f"{BASE_URL}/api/auth/otp/start", json={"phone": ADMIN_PHONE})
        assert r.status_code == 200, f"otp/start: {r.status_code} {r.text}"
        code = r.json().get("testCode") or DEV_OTP
        r2 = api.post(f"{BASE_URL}/api/auth/otp/verify", json={"phone": ADMIN_PHONE, "code": code})
        if r2.status_code != 200 and code != DEV_OTP:
            r2 = api.post(f"{BASE_URL}/api/auth/otp/verify", json={"phone": ADMIN_PHONE, "code": DEV_OTP})
        assert r2.status_code == 200, f"otp/verify: {r2.status_code} {r2.text}"
        body = r2.json()
        assert body.get("accessToken"), f"no accessToken: {body}"
