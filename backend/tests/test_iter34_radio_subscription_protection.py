"""Iter 34 — Radio subscription-protection layer backend tests.

Verifies the new gating around /api/radio/*:

  1. Unauthenticated /radio/now-playing: streamUrl* stripped, requiresSubscription=True.
  2. Free-tier user /radio/now-playing: streamUrl* stripped, requiresSubscription=True.
  3. Free user /radio/token: 402 "Active subscription required".
  4. Free user /radio/live (missing/invalid token): 401.
  5. Upgrade via /subscription/rc-sync -> premium_monthly, 200.
  6. Premium user /radio/now-playing: contains streamUrl, streamUrlHttps, proxyStreamUrl,
     requiresSubscription=False. proxyStreamUrl matches ^https://.+/api/radio/live\\?token=.
  7. Premium user /radio/token: 200, {token, expiresIn:1800, streamUrl}. streamUrl ==
     f"{PUBLIC_BASE_URL}/api/radio/live?token=<token>" (any token — endpoint currently signs
     a new token in the URL; assert host+path prefix + non-empty token param).
  8. Premium user /radio/live?token=<good>: 200, streams >= 8KB audio, not HTML 403 page.
  9. Forge attack: JWT with pur!="radio_stream" -> 401. Session accessToken passed
     as ?token= also -> 401.
 10. Regression sanity: /subscription/rc-sync 200 for premium_monthly, /live/status 200,
     /auth/otp/verify returns valid JWT.
"""
import os
import re
import time
import jwt
import pytest
import httpx
import requests
from datetime import datetime, timedelta, timezone


BASE_URL = (
    os.environ.get("EXPO_BACKEND_URL")
    or os.environ.get("EXPO_PUBLIC_BACKEND_URL")
    or "https://radio-vod-platform.preview.emergentagent.com"
).rstrip("/")
PUBLIC_BASE_URL = BASE_URL  # matches backend .env
JWT_SECRET = os.environ.get("JWT_SECRET", "bbfm-kigali-prod-jwt-secret-please-rotate-in-live")
JWT_ALG = "HS256"

ADMIN_PHONE = "250794230137"
OTP_CODE = "123456"

PROXY_URL_RE = re.compile(r"^https://.+/api/radio/live\?token=[^&\s]+$")


# ---------- Shared session-level fixtures ----------

@pytest.fixture(scope="session")
def api_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _login_once(api_client) -> dict:
    """OTP-login as admin phone, with retry to survive xdist race on shared phone."""
    last_err = None
    for _ in range(4):
        try:
            start = api_client.post(f"{BASE_URL}/api/auth/otp/start", json={"phone": ADMIN_PHONE}, timeout=15)
            assert start.status_code == 200, start.text
            verify = api_client.post(f"{BASE_URL}/api/auth/otp/verify", json={"phone": ADMIN_PHONE, "code": OTP_CODE}, timeout=15)
            if verify.status_code == 200:
                data = verify.json()
                assert "accessToken" in data and data["accessToken"]
                assert "user" in data and data["user"].get("id")
                return {"access_token": data["accessToken"], "user": data["user"]}
            last_err = f"{verify.status_code}: {verify.text}"
        except AssertionError as e:
            last_err = str(e)
        time.sleep(0.4)
    raise AssertionError(f"OTP login failed after retries: {last_err}")


@pytest.fixture(scope="module")
def admin_tokens(api_client):
    """OTP-login as admin phone, return {access_token, user}."""
    return _login_once(api_client)


def _reset_user_to_free(user_id: str):
    """Reset user tier to free via direct mongo access — used to guarantee free-tier
    starting state regardless of previous test runs."""
    try:
        from pymongo import MongoClient
        mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "test_database")
        cli = MongoClient(mongo_url, serverSelectionTimeoutMS=3000)
        cli[db_name].users.update_one(
            {"id": user_id},
            {"$set": {"tier": "free", "subscriptionExpiresAt": None, "currentPlan": None}},
        )
        cli.close()
        return True
    except Exception as e:
        print(f"[warn] could not reset user to free: {e}")
        return False


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _reset_to_free(api_client, token):
    """Best-effort reset tier back to free via direct db patch not available — we
    can't demote, but tests order matters: free-first, then premium. Nothing to
    do here; kept for symmetry."""
    return


# ==========================================================================
# 1. Unauthenticated now-playing — strips stream URLs
# ==========================================================================
class TestUnauthenticatedNowPlaying:
    def test_no_auth_now_playing_200_and_stripped(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/radio/now-playing", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "streamUrl" not in data, f"streamUrl must be stripped for guests, got {data.get('streamUrl')!r}"
        assert "streamUrlHttps" not in data, "streamUrlHttps must be stripped for guests"
        assert data.get("requiresSubscription") is True, f"requiresSubscription must be True for guests, got {data.get('requiresSubscription')!r}"
        assert "proxyStreamUrl" not in data, "proxyStreamUrl must NOT be exposed to guests"

    def test_no_auth_now_playing_still_has_metadata(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/radio/now-playing", timeout=15)
        data = r.json()
        # Metadata still returned so client can render paywall CTA.
        assert data.get("showTitle"), "showTitle should still be present"
        assert "isLive" in data


# ==========================================================================
# 2 + 3 + 4. Free-tier user gating
# ==========================================================================
class TestFreeUserGating:
    @classmethod
    @pytest.fixture(autouse=True, scope="class")
    def _force_free(cls, admin_tokens):
        _reset_user_to_free(admin_tokens["user"]["id"])
        yield

    def test_free_user_now_playing_stripped(self, api_client, admin_tokens):
        # This test relies on the admin user still being tier=free (default at first login).
        # We run this test class BEFORE upgrading (class name orders alphabetically before Premium/Regression).
        r = api_client.get(f"{BASE_URL}/api/radio/now-playing", headers=auth_headers(admin_tokens["access_token"]), timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        # Only assert stripping IF the user is currently free. If a previous test run left
        # them premium (subscriptionExpiresAt in the future), skip with a diagnostic.
        me = api_client.get(f"{BASE_URL}/api/auth/me", headers=auth_headers(admin_tokens["access_token"]), timeout=15).json()
        if me.get("tier") in ("basic", "premium"):
            pytest.skip(f"Admin user is already {me.get('tier')} from prior run — skipping free-tier assertion")
        assert "streamUrl" not in data, f"streamUrl must be stripped for free user, got {data}"
        assert "streamUrlHttps" not in data
        assert data.get("requiresSubscription") is True

    def test_free_user_radio_token_402(self, api_client, admin_tokens):
        me = api_client.get(f"{BASE_URL}/api/auth/me", headers=auth_headers(admin_tokens["access_token"]), timeout=15).json()
        if me.get("tier") in ("basic", "premium"):
            pytest.skip("Already paid — skipping free 402 assertion")
        r = api_client.get(f"{BASE_URL}/api/radio/token", headers=auth_headers(admin_tokens["access_token"]), timeout=15)
        assert r.status_code == 402, f"Expected 402 for free user, got {r.status_code}: {r.text}"
        assert "subscription" in r.text.lower()

    def test_free_user_radio_live_missing_token_401(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/radio/live", timeout=15)
        assert r.status_code == 401, f"Expected 401 for missing token, got {r.status_code}: {r.text}"

    def test_free_user_radio_live_invalid_token_401(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/radio/live?token=not-a-real-jwt", timeout=15)
        assert r.status_code == 401, f"Expected 401 for invalid token, got {r.status_code}: {r.text}"


# ==========================================================================
# 5–8. Upgrade to premium + paid access flows
# ==========================================================================
class TestPremiumUserAccess:
    def test_upgrade_via_rc_sync_200(self, api_client, admin_tokens):
        r = api_client.post(
            f"{BASE_URL}/api/subscription/rc-sync",
            json={"plan": "premium_monthly"},
            headers=auth_headers(admin_tokens["access_token"]),
            timeout=15,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("tier") == "premium", f"Expected tier=premium, got {data}"
        assert data.get("ok") is True
        assert data.get("expiresAt"), "expiresAt should be set"
        # Verify via /auth/me
        me = api_client.get(f"{BASE_URL}/api/auth/me", headers=auth_headers(admin_tokens["access_token"]), timeout=15)
        assert me.status_code == 200
        assert me.json().get("tier") == "premium"

    def test_premium_now_playing_full_payload(self, api_client, admin_tokens):
        r = api_client.get(f"{BASE_URL}/api/radio/now-playing", headers=auth_headers(admin_tokens["access_token"]), timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("requiresSubscription") is False, f"requiresSubscription must be False for premium: {data}"
        assert data.get("streamUrl"), f"streamUrl must be present for premium: {data}"
        assert "streamUrlHttps" in data, "streamUrlHttps field must be present for premium"
        assert data.get("proxyStreamUrl"), f"proxyStreamUrl must be present for premium: {data}"
        assert PROXY_URL_RE.match(data["proxyStreamUrl"]), (
            f"proxyStreamUrl must match ^https://.+/api/radio/live\\?token=, got {data['proxyStreamUrl']!r}"
        )

    def test_premium_radio_token_endpoint(self, api_client, admin_tokens):
        r = api_client.get(f"{BASE_URL}/api/radio/token", headers=auth_headers(admin_tokens["access_token"]), timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("expiresIn") == 1800, f"expiresIn must be 1800, got {data.get('expiresIn')!r}"
        assert data.get("token"), "token field must be present and non-empty"
        assert data.get("streamUrl"), "streamUrl field must be present"
        # streamUrl must be of the form PUBLIC_BASE_URL + /api/radio/live?token=...
        assert data["streamUrl"].startswith(f"{PUBLIC_BASE_URL}/api/radio/live?token="), (
            f"streamUrl mismatch: expected prefix {PUBLIC_BASE_URL}/api/radio/live?token=, got {data['streamUrl']!r}"
        )
        # Decode token — should have pur=radio_stream and sub=user.id
        payload = jwt.decode(data["token"], JWT_SECRET, algorithms=[JWT_ALG])
        assert payload.get("pur") == "radio_stream", f"pur claim must be radio_stream, got {payload!r}"
        assert payload.get("sub") == admin_tokens["user"]["id"], "sub claim must match user id"

    def test_premium_radio_live_streams_audio(self, api_client, admin_tokens):
        # Get a fresh token
        tok_r = api_client.get(f"{BASE_URL}/api/radio/token", headers=auth_headers(admin_tokens["access_token"]), timeout=15)
        assert tok_r.status_code == 200
        token = tok_r.json()["token"]
        url = f"{BASE_URL}/api/radio/live?token={token}"

        # Use httpx to stream — close early after receiving > 8KB.
        received = 0
        content_type = None
        first_bytes = b""
        try:
            with httpx.Client(timeout=httpx.Timeout(6.0, connect=6.0), verify=False) as client:
                with client.stream("GET", url) as resp:
                    assert resp.status_code == 200, (
                        f"Expected 200 from /radio/live, got {resp.status_code}: "
                        f"body={resp.read(500)!r}"
                    )
                    content_type = resp.headers.get("content-type", "").lower()
                    for chunk in resp.iter_bytes():
                        received += len(chunk)
                        if len(first_bytes) < 256:
                            first_bytes += chunk[: 256 - len(first_bytes)]
                        if received >= 8192:
                            break
        except httpx.ReadTimeout:
            pass  # slow upstream but we might have already collected enough
        except Exception as e:
            pytest.fail(f"Streaming request failed: {e}")

        assert received >= 8192, f"Expected >=8192 bytes of stream data, got {received} bytes"
        # Content-type sanity: audio/* or application/octet-stream (icecast sometimes returns that);
        # explicitly NOT text/html which would be an upstream error page.
        assert "text/html" not in content_type, (
            f"content-type indicates HTML error page (not audio): {content_type!r}, "
            f"first bytes={first_bytes[:200]!r}"
        )
        # Extra sanity: first bytes should NOT contain '<html' or '403 Forbidden'
        lowered = first_bytes.lower()
        assert b"<html" not in lowered, f"Response body looks like HTML: {first_bytes[:200]!r}"
        assert b"403 forbidden" not in lowered, f"Upstream 403 leaked through: {first_bytes[:200]!r}"


# ==========================================================================
# 9. Forge attack — session JWT + wrong pur claim
# ==========================================================================
class TestForgeAttack:
    def test_session_access_token_rejected_by_radio_live(self, api_client, admin_tokens):
        """The /auth/otp/verify accessToken is a session JWT WITHOUT pur=radio_stream.
        It MUST be rejected as a ?token= on /radio/live even though it's signed by the
        same JWT_SECRET and belongs to a premium user."""
        session_jwt = admin_tokens["access_token"]
        r = api_client.get(f"{BASE_URL}/api/radio/live?token={session_jwt}", timeout=15)
        assert r.status_code == 401, (
            f"Session JWT MUST NOT be usable as a radio token — expected 401, got {r.status_code}: {r.text}"
        )

    def test_forged_jwt_wrong_purpose_rejected(self, api_client, admin_tokens):
        """Sign a JWT with the same secret but with pur='not_radio' — must be 401."""
        payload = {
            "sub": admin_tokens["user"]["id"],
            "pur": "not_radio",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
            "iat": datetime.now(timezone.utc),
        }
        forged = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)
        r = api_client.get(f"{BASE_URL}/api/radio/live?token={forged}", timeout=15)
        assert r.status_code == 401, f"Forged (wrong pur) token MUST be rejected: got {r.status_code}: {r.text}"

    def test_forged_jwt_no_purpose_rejected(self, api_client, admin_tokens):
        """Sign a JWT with the same secret but with NO pur claim at all — must be 401."""
        payload = {
            "sub": admin_tokens["user"]["id"],
            "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
            "iat": datetime.now(timezone.utc),
        }
        forged = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)
        r = api_client.get(f"{BASE_URL}/api/radio/live?token={forged}", timeout=15)
        assert r.status_code == 401, f"Forged (no pur) token MUST be rejected: got {r.status_code}: {r.text}"

    def test_expired_radio_token_rejected(self, api_client, admin_tokens):
        """Signed with correct pur but exp in the past."""
        payload = {
            "sub": admin_tokens["user"]["id"],
            "pur": "radio_stream",
            "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
            "iat": datetime.now(timezone.utc) - timedelta(minutes=61),
        }
        expired = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)
        r = api_client.get(f"{BASE_URL}/api/radio/live?token={expired}", timeout=15)
        assert r.status_code == 401, f"Expired token MUST be rejected: got {r.status_code}: {r.text}"


# ==========================================================================
# 10. Regression sanity
# ==========================================================================
class TestRegressionSanity:
    def test_rc_sync_premium_monthly_still_200(self, api_client, admin_tokens):
        r = api_client.post(
            f"{BASE_URL}/api/subscription/rc-sync",
            json={"plan": "premium_monthly"},
            headers=auth_headers(admin_tokens["access_token"]),
            timeout=15,
        )
        assert r.status_code == 200, r.text
        assert r.json().get("tier") == "premium"

    def test_live_status_200(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/live/status", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        # For unauth call, if live, videoId should be stripped
        assert "isLive" in data or "live" in data or "requiresSubscription" in data, (
            f"live/status response missing gating fields: {data}"
        )

    def test_otp_verify_returns_valid_jwt(self, api_client):
        # Fresh login flow — ensure JWT can be decoded and has sub claim.
        start = api_client.post(f"{BASE_URL}/api/auth/otp/start", json={"phone": ADMIN_PHONE}, timeout=15)
        assert start.status_code == 200
        v = api_client.post(f"{BASE_URL}/api/auth/otp/verify", json={"phone": ADMIN_PHONE, "code": OTP_CODE}, timeout=15)
        assert v.status_code == 200, v.text
        tok = v.json()["accessToken"]
        payload = jwt.decode(tok, JWT_SECRET, algorithms=[JWT_ALG])
        assert payload.get("sub"), "session JWT must have sub claim"
        # And note: session JWT MUST NOT carry pur=radio_stream (see forge test)
        assert payload.get("pur") != "radio_stream", (
            "SECURITY: session JWT accidentally has pur=radio_stream — this would let session tokens play the stream!"
        )
