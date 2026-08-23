"""Iter 21 backend regression:
- MoMo switched BACK to POST /public/payments/transfer (was /debit-credit in iter 19).
- Verify auth headers X-API-Key + X-API-Secret NOT causing 401.
- Verify _guard_payer_not_merchant blocks all merchant number variants.
- Verify /api/privacy is served (with & without auth) with HTML content.
- Regression: /api/health, /api/shows count>=50, /api/admin/youtube/sync ok:true & upserted>=1.
"""
import os
import re
import pytest
import requests

BASE = os.environ.get("EXPO_PUBLIC_BACKEND_URL") or "https://radio-vod-platform.preview.emergentagent.com"
BASE = BASE.rstrip("/")
API = f"{BASE}/api"

ADMIN_PHONE = "+250794230137"
PAYER = "250794230137"  # same as admin — this is a real payer
MERCHANT_VARIANTS = [
    "250798875274",
    "+250 798 875 274",
    "0798875274",
    "250 798 875 274",
]


@pytest.fixture(scope="module")
def s():
    return requests.Session()


@pytest.fixture(scope="module")
def admin_token(s):
    r = s.post(f"{API}/auth/otp/start", json={"phone": ADMIN_PHONE})
    assert r.status_code == 200, f"otp/start failed: {r.status_code} {r.text}"
    data = r.json()
    code = data.get("testCode")
    assert code, f"testCode missing in {data}"
    r2 = s.post(f"{API}/auth/otp/verify", json={"phone": ADMIN_PHONE, "code": code})
    assert r2.status_code == 200, f"otp/verify failed: {r2.status_code} {r2.text}"
    tok = r2.json().get("accessToken")
    assert tok
    return tok


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ---- Health ----
def test_health(s):
    r = s.get(f"{API}/health")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("ok") is True


# ---- Privacy served (no auth) ----
def test_privacy_no_auth(s):
    r = s.get(f"{API}/privacy")
    assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
    ct = r.headers.get("content-type", "").lower()
    assert "text/html" in ct, f"Bad content-type: {ct}"
    body = r.text
    assert "Privacy Policy" in body
    assert "BB FM Kigali" in body
    assert "Delete Account" in body


# ---- Privacy served (with auth) ----
def test_privacy_with_auth(s, auth_headers):
    r = s.get(f"{API}/privacy", headers=auth_headers)
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "").lower()
    assert "Privacy Policy" in r.text


# ---- Shows count >=50 ----
def test_shows_count(s):
    r = s.get(f"{API}/shows")
    assert r.status_code == 200, r.text
    items = r.json()
    assert isinstance(items, list)
    assert len(items) >= 50, f"Only {len(items)} shows"


# ---- MoMo initiate (subscription) — should hit /public/payments/transfer ----
def test_momo_initiate_transfer(s, auth_headers):
    r = s.post(
        f"{API}/billing/momo/initiate",
        headers=auth_headers,
        json={"plan": "basic_monthly", "phone": PAYER},
    )
    # 2xx expected — even if BeSoft returns provisioning error, our endpoint should return 200 with status='failed'.
    assert r.status_code == 200, f"{r.status_code} — {r.text[:500]}"
    data = r.json()
    assert "reference" in data
    assert "status" in data
    # Explicitly ensure NOT a 401 regression:
    msg = (data.get("failureReason") or data.get("message") or "").lower()
    assert "x-api-key" not in msg and "x-api-secret" not in msg and "unauthorized" not in msg, \
        f"REGRESSION: BeSoft auth headers missing? {data}"
    # Return reference so we can verify DB state via history endpoint
    return data["reference"]


# ---- MoMo initiate persists besoftAttempt='transfer' in payments collection ----
def test_momo_initiate_besoft_attempt_history(s, auth_headers):
    r = s.post(
        f"{API}/billing/momo/initiate",
        headers=auth_headers,
        json={"plan": "basic_monthly", "phone": PAYER},
    )
    assert r.status_code == 200
    reference = r.json().get("reference")
    assert reference

    # Poll billing history to find the persisted payment
    h = s.get(f"{API}/billing/history", headers=auth_headers)
    assert h.status_code == 200
    items = h.json()
    match = next((p for p in items if p.get("reference") == reference), None)
    assert match, f"reference {reference} not in history"
    # Only if BeSoft responded (2xx or 3xx or captured), besoftAttempt is set
    assert match.get("besoftAttempt") == "transfer", \
        f"REGRESSION: besoftAttempt should be 'transfer' not {match.get('besoftAttempt')}"


# ---- Payer safety guard: merchant number variants must be 400 ----
@pytest.mark.parametrize("merchant_num", MERCHANT_VARIANTS)
def test_momo_initiate_merchant_guard(s, auth_headers, merchant_num):
    r = s.post(
        f"{API}/billing/momo/initiate",
        headers=auth_headers,
        json={"plan": "basic_monthly", "phone": merchant_num},
    )
    assert r.status_code == 400, f"Merchant guard failed for '{merchant_num}': {r.status_code} {r.text}"
    body = r.text.lower()
    assert "collection" in body or "own" in body or "merchant" in body


# ---- VOD MoMo purchase ----
@pytest.fixture(scope="module")
def a_show_id(s):
    r = s.get(f"{API}/shows")
    assert r.status_code == 200
    items = r.json()
    assert items
    # Prefer non-live show
    for it in items:
        if it.get("id"):
            return it["id"]
    raise AssertionError("no show with id")


def test_vod_momo_transfer(s, auth_headers, a_show_id):
    r = s.post(
        f"{API}/billing/vod/{a_show_id}/momo",
        headers=auth_headers,
        json={"phone": PAYER},
    )
    # Response may indicate premium/already unlocked OR go through BeSoft — both are 2xx.
    assert r.status_code == 200, f"{r.status_code} — {r.text[:500]}"
    data = r.json()
    # If not alreadyUnlocked, ensure no auth error and besoft flow happened
    if not data.get("alreadyUnlocked"):
        msg = (data.get("failureReason") or data.get("message") or "").lower()
        assert "x-api-key" not in msg and "unauthorized" not in msg, \
            f"REGRESSION VOD: BeSoft auth headers missing? {data}"
        assert "reference" in data


@pytest.mark.parametrize("merchant_num", MERCHANT_VARIANTS)
def test_vod_momo_merchant_guard(s, auth_headers, a_show_id, merchant_num):
    r = s.post(
        f"{API}/billing/vod/{a_show_id}/momo",
        headers=auth_headers,
        json={"phone": merchant_num},
    )
    # Response may short-circuit with alreadyUnlocked (200) if the test admin is premium — accept either
    if r.status_code == 200 and r.json().get("alreadyUnlocked"):
        pytest.skip("Admin already has VOD unlocked; guard cannot be reached")
    assert r.status_code == 400, f"VOD merchant guard failed for '{merchant_num}': {r.status_code} {r.text[:300]}"


# ---- Admin: youtube sync regression ----
def test_admin_youtube_sync(s, auth_headers):
    r = s.post(f"{API}/admin/youtube/sync", headers=auth_headers)
    assert r.status_code == 200, f"{r.status_code} — {r.text[:400]}"
    data = r.json()
    assert data.get("ok") is True, data
    assert data.get("upserted", 0) >= 1, data
