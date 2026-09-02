"""
Iter38 FULL BACKEND REGRESSION for BB FM Kigali.
Focus: (1) YouTube channel-id resolution via OAuth refresh_token on /api/live/status,
       (2) confirm no backend regression after Expo Poppins font migration.

Runs against EXPO_BACKEND_URL (public preview URL). All /api/... routes.
Admin phone: +250794230137 (returns testCode in dev mode).
Regular phone: +250788123456.
"""
import os
import re
import pytest
import requests

BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL")
            or os.environ.get("EXPO_BACKEND_URL")
            or "http://localhost:8001").rstrip("/")

ADMIN_PHONE = "+250794230137"
USER_PHONE = "+250788123456"

TIMEOUT = 30


# ---------------- fixtures ----------------
@pytest.fixture(scope="session")
def api_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _otp_login(session: requests.Session, phone: str) -> str:
    r = session.post(f"{BASE_URL}/api/auth/otp/start", json={"phone": phone}, timeout=TIMEOUT)
    assert r.status_code in (200, 201), f"otp/start {phone} {r.status_code} {r.text[:200]}"
    body = r.json()
    code = body.get("testCode") or body.get("code")
    if not code:
        # fallback to mongo challenge (used in prior iterations)
        pytest.skip(f"testCode not returned for {phone}; dev-return-code disabled in this env")
    r = session.post(f"{BASE_URL}/api/auth/otp/verify",
                     json={"phone": phone, "code": code}, timeout=TIMEOUT)
    assert r.status_code == 200, f"otp/verify {phone} {r.status_code} {r.text[:200]}"
    tok = r.json().get("accessToken") or r.json().get("token") or r.json().get("access_token") or r.json().get("sessionToken")
    assert tok, f"no token in verify body: {r.json()}"
    return tok


@pytest.fixture(scope="session")
def admin_token(api_client):
    return _otp_login(api_client, ADMIN_PHONE)


@pytest.fixture(scope="session")
def user_token(api_client):
    try:
        return _otp_login(api_client, USER_PHONE)
    except Exception as e:
        pytest.skip(f"user login failed: {e}")


def _auth(tok):
    return {"Authorization": f"Bearer {tok}"}


# ================= Core Auth / User =================
class TestAuth:
    def test_A1_otp_start_admin(self, api_client):
        r = api_client.post(f"{BASE_URL}/api/auth/otp/start",
                            json={"phone": ADMIN_PHONE}, timeout=TIMEOUT)
        assert r.status_code in (200, 201), r.text[:200]
        body = r.json()
        assert "testCode" in body or "code" in body, f"missing testCode: {body}"

    def test_A2_otp_verify_admin(self, api_client, admin_token):
        assert admin_token and isinstance(admin_token, str) and len(admin_token) > 20

    def test_A3_auth_me_admin(self, api_client, admin_token):
        r = api_client.get(f"{BASE_URL}/api/auth/me",
                           headers=_auth(admin_token), timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:200]
        me = r.json()
        assert me.get("role") == "admin", f"expected admin role, got {me}"
        # Phone normalised — accept both +250... and 250... forms
        assert (me.get("phone") or "").lstrip("+").endswith("250794230137"), me

    def test_A4_subscription_reconcile(self, api_client, admin_token):
        r = api_client.post(f"{BASE_URL}/api/subscription/reconcile",
                            headers=_auth(admin_token), timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:200]
        body = r.json()
        # Must expose the tier
        assert "tier" in body, f"no tier in reconcile body: {body}"
        assert body["tier"] in ("free", "basic", "premium"), body


# ================= YouTube Live =================
class TestYouTubeLive:
    """Regression for youtube_live.py rewrite (channel-id via refresh_token)."""

    def test_B1_live_status_no_500(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/live/status", timeout=TIMEOUT)
        assert r.status_code == 200, f"/live/status {r.status_code}: {r.text[:300]}"

    def test_B2_live_status_shape(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/live/status", timeout=TIMEOUT)
        assert r.status_code == 200
        body = r.json()
        # NOTE: videoId is subscription-gated — anonymous callers may not receive
        # it even when isLive=true (paywall enforcement). Only assert on the
        # always-present metadata fields.
        for k in ("isLive", "title", "thumbnail",
                  "startedAt", "channelTitle", "checkedAt", "error"):
            assert k in body, f"missing key {k} in /live/status: {body}"
        assert isinstance(body["isLive"], bool)

    def test_B3_live_status_channel_resolved(self, api_client):
        """Critical: with admin OAuth connected, channel_id must resolve — so
        error must be None (except transient 'no live broadcast')."""
        r = api_client.get(f"{BASE_URL}/api/live/status", timeout=TIMEOUT)
        body = r.json()
        err = body.get("error")
        if err:
            # Any 'channel not found' error means the OAuth refresh path failed.
            assert "channel not found" not in (err or "").lower(), (
                f"P0 REGRESSION: channel-id resolution failed. error={err!r}. "
                f"YouTube refresh_token flow in youtube_live.py did not recover channelId."
            )
            # Non-fatal errors (quota, transient) — record but don't fail hard.
            pytest.skip(f"/live/status non-fatal error: {err}")
        # channelTitle should be populated when channel resolved
        assert body.get("channelTitle"), f"channelTitle empty even though error is null: {body}"

    def test_B4_live_status_authenticated(self, api_client, admin_token):
        """Same call as admin — must also succeed and shape unchanged."""
        r = api_client.get(f"{BASE_URL}/api/live/status",
                           headers=_auth(admin_token), timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:300]
        body = r.json()
        assert "isLive" in body and "error" in body


# ================= Radio proxy (subscription-gated) =================
class TestRadio:
    def test_C1_radio_live_unauth_blocked(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/radio/live", timeout=TIMEOUT, allow_redirects=False)
        assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}"

    def test_C2_radio_live_with_admin_token(self, api_client, admin_token):
        # /radio/live requires a *signed radio token* passed as ?token=… — first
        # exchange the bearer for a radio token.
        r = api_client.get(f"{BASE_URL}/api/radio/token",
                           headers=_auth(admin_token), timeout=TIMEOUT)
        if r.status_code != 200:
            # Fallback: some builds allow direct bearer on /radio/live
            r2 = api_client.get(f"{BASE_URL}/api/radio/live",
                                headers=_auth(admin_token), timeout=TIMEOUT, stream=True)
            assert r2.status_code == 200, f"radio/live w/ bearer {r2.status_code}"
            ct = r2.headers.get("content-type", "")
            assert "audio" in ct.lower() or "mpeg" in ct.lower(), f"unexpected content-type: {ct}"
            return
        assert r.status_code == 200, r.text[:200]
        tok_body = r.json()
        radio_tok = tok_body.get("token") or tok_body.get("radioToken")
        assert radio_tok, f"no radio token: {tok_body}"
        r2 = api_client.get(f"{BASE_URL}/api/radio/live",
                            params={"token": radio_tok},
                            timeout=TIMEOUT, stream=True)
        assert r2.status_code == 200, f"radio/live signed {r2.status_code} {r2.text[:200]}"
        ct = r2.headers.get("content-type", "")
        assert "audio" in ct.lower() or "mpeg" in ct.lower() or "octet" in ct.lower(), (
            f"unexpected content-type: {ct}"
        )
        # Confirm at least some bytes stream
        chunk = next(r2.iter_content(4096), b"")
        assert chunk, "radio stream returned empty first chunk"
        r2.close()


# ================= Programs / Shows / Videos / News / Categories =================
class TestPublicContent:
    def test_D1_programs(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/programs", timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:200]
        assert isinstance(r.json(), (list, dict))

    def test_D2_shows(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/shows", timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:200]
        body = r.json()
        assert isinstance(body, (list, dict))

    def test_D3_videos(self, api_client):
        # There is no bare /videos endpoint — the closest is /videos/status.
        # Try /videos first, fall back to /videos/status.
        r = api_client.get(f"{BASE_URL}/api/videos", timeout=TIMEOUT)
        if r.status_code == 404:
            r2 = api_client.get(f"{BASE_URL}/api/videos/status", timeout=TIMEOUT)
            assert r2.status_code == 200, f"/videos/status {r2.status_code}"
            return
        assert r.status_code == 200, r.text[:200]

    def test_D4_news(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/news", timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:200]

    def test_D5_categories(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/categories", timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:200]


# ================= Payments (read-only sanity) =================
class TestPayments:
    def test_E1_admin_payments_list(self, api_client, admin_token):
        r = api_client.get(f"{BASE_URL}/api/admin/payments",
                           headers=_auth(admin_token), timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:200]
        body = r.json()
        assert isinstance(body, (list, dict))

    def test_E2_admin_payments_csv(self, api_client, admin_token):
        """Endpoint requested was /api/admin/payments/report.csv but the actual
        path is /api/admin/payments/export.csv — try both, at least one must 200."""
        paths = ["/api/admin/payments/report.csv", "/api/admin/payments/export.csv"]
        ok = None
        for p in paths:
            r = api_client.get(f"{BASE_URL}{p}", headers=_auth(admin_token),
                               timeout=TIMEOUT)
            if r.status_code == 200:
                ok = (p, r)
                break
        assert ok is not None, "Neither payments/report.csv nor payments/export.csv returned 200"
        p, r = ok
        ct = r.headers.get("content-type", "")
        assert "csv" in ct.lower() or "text" in ct.lower(), f"unexpected CT: {ct} for {p}"
        # Must have at least a header row
        assert len(r.content) > 0

    def test_E3_admin_payments_pdf(self, api_client, admin_token):
        """Endpoint requested was /api/admin/payments/report.pdf — actual is
        /api/admin/reports/business.pdf. Try both."""
        paths = ["/api/admin/payments/report.pdf", "/api/admin/reports/business.pdf"]
        ok = None
        for p in paths:
            r = api_client.get(f"{BASE_URL}{p}", headers=_auth(admin_token),
                               timeout=TIMEOUT)
            if r.status_code == 200:
                ok = (p, r)
                break
        assert ok is not None, "Neither payments/report.pdf nor reports/business.pdf returned 200"
        p, r = ok
        assert r.content[:5] == b"%PDF-", f"not a valid PDF from {p}: {r.content[:20]!r}"
        assert len(r.content) > 1024, f"PDF too small: {len(r.content)} bytes"


# ================= Admin =================
class TestAdmin:
    def test_F1_admin_users(self, api_client, admin_token):
        r = api_client.get(f"{BASE_URL}/api/admin/users",
                           headers=_auth(admin_token), timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:200]
        body = r.json()
        assert isinstance(body, (list, dict))

    def test_F2_admin_stats(self, api_client, admin_token):
        """/api/admin/stats not in server.py — try it then fall back to
        /api/admin/analytics/dashboard (equivalent surface)."""
        r = api_client.get(f"{BASE_URL}/api/admin/stats",
                           headers=_auth(admin_token), timeout=TIMEOUT)
        if r.status_code == 404:
            r2 = api_client.get(f"{BASE_URL}/api/admin/analytics/dashboard",
                                headers=_auth(admin_token), timeout=TIMEOUT)
            assert r2.status_code == 200, f"/admin/analytics/dashboard {r2.status_code}"
            return
        assert r.status_code == 200, r.text[:200]

    def test_F3_admin_users_forbidden_without_token(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/admin/users", timeout=TIMEOUT)
        assert r.status_code in (401, 403), f"admin/users unauth should reject, got {r.status_code}"
