"""
Iteration 19 — multi-feature backend regression suite.

Covers:
  - Auth (OTP for admin +250794230137)
  - MoMo subscription /public/payments/debit-credit routing + besoftAttempt field
  - MoMo VOD  /public/payments/debit-credit routing + besoftAttempt field
  - Merchant safety guard (250798875274 in 3 normalization variants) for both endpoints
  - YouTube sync (admin) POST + GET status
  - YouTube sync unauthorized (no token / non-admin)
  - Sign in with Apple (invalid token → 401)
  - Delete Account (throwaway user create + delete + purge check)
  - Delete Account without token → 401
  - PayPal subscription + VOD regressions
  - Health, /shows, /shows/{id} without auth returns locked
"""
import os
import re
import time
import pytest
import requests
from pymongo import MongoClient

BASE = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://radio-vod-platform.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"
ADMIN_PHONE = "+250794230137"
MERCHANT_MSISDN = "250798875274"
TEST_PAYER = "250794230137"
THROWAWAY_PHONE = "+250789000099"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

_admin_token_cache = None


# ---------------- Fixtures ----------------

@pytest.fixture(scope="module")
def db():
    client = MongoClient(MONGO_URL)
    return client[DB_NAME]


@pytest.fixture(scope="module")
def admin_token():
    global _admin_token_cache
    if _admin_token_cache:
        return _admin_token_cache
    r = requests.post(f"{API}/auth/otp/start", json={"phone": ADMIN_PHONE}, timeout=15)
    assert r.status_code == 200, f"OTP start failed: {r.status_code} {r.text}"
    body = r.json()
    code = body.get("testCode") or "123456"
    r2 = requests.post(f"{API}/auth/otp/verify", json={"phone": ADMIN_PHONE, "code": code}, timeout=15)
    assert r2.status_code == 200, f"OTP verify failed: {r2.status_code} {r2.text}"
    d = r2.json()
    token = d.get("accessToken") or d.get("token") or d.get("session_token")
    assert token, f"No token in verify response: {d}"
    assert d.get("user", {}).get("role") == "admin", f"user not admin: {d.get('user')}"
    _admin_token_cache = token
    return token


def auth(token):
    return {"Authorization": f"Bearer {token}"}


# ---------------- Health / basic ----------------

def test_health():
    r = requests.get(f"{API}/health", timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert body.get("status") in ("ok", "healthy") or body.get("ok") is True


def test_shows_list_guest():
    r = requests.get(f"{API}/shows", timeout=15)
    assert r.status_code == 200
    lst = r.json()
    assert isinstance(lst, list)
    assert len(lst) > 0
    return lst


def test_show_detail_guest_locked():
    lst = requests.get(f"{API}/shows", timeout=15).json()
    sid = lst[0]["id"]
    r = requests.get(f"{API}/shows/{sid}", timeout=15)
    assert r.status_code == 200
    body = r.json()
    # guest should get locked flag on VOD
    assert body.get("locked") is True or body.get("videoUrl") is None or body.get("isLive") is True


# ---------------- Auth ----------------

def test_admin_otp_dev_testcode():
    r = requests.post(f"{API}/auth/otp/start", json={"phone": ADMIN_PHONE}, timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is True
    assert body.get("testCode"), "dev OTP should return testCode"
    assert re.match(r"^\d{6}$", body["testCode"])


def test_admin_role_auto_promoted(admin_token):
    r = requests.get(f"{API}/auth/me", headers=auth(admin_token), timeout=10)
    assert r.status_code == 200
    assert r.json().get("role") == "admin"


# ---------------- MoMo subscription /debit-credit ----------------

def test_momo_subscription_debit_credit_routing(admin_token, db):
    r = requests.post(
        f"{API}/billing/momo/initiate",
        headers=auth(admin_token),
        json={"plan": "basic_monthly", "phone": TEST_PAYER},
        timeout=45,
    )
    assert r.status_code in (200, 201), f"Expected 2xx, got {r.status_code}: {r.text}"
    body = r.json()
    ref = body.get("reference")
    assert ref, f"no reference in body: {body}"
    # give backend a beat to write besoftAttempt
    time.sleep(1)
    doc = db.payments.find_one({"reference": ref})
    assert doc is not None, f"payment doc not found for ref {ref}"
    assert doc.get("besoftAttempt") == "debit_credit", (
        f"besoftAttempt must be 'debit_credit', got {doc.get('besoftAttempt')} — endpoint routing broken"
    )


@pytest.mark.parametrize("phone", [
    MERCHANT_MSISDN,             # 250798875274
    "+250 798 875 274",          # spaces
    "0798875274",                # local 10-digit
])
def test_momo_subscription_safety_guard(admin_token, phone):
    r = requests.post(
        f"{API}/billing/momo/initiate",
        headers=auth(admin_token),
        json={"plan": "basic_monthly", "phone": phone},
        timeout=20,
    )
    assert r.status_code == 400, f"Merchant phone {phone!r} MUST return 400, got {r.status_code}: {r.text}"


# ---------------- MoMo VOD /debit-credit ----------------

def _pick_vod_show():
    lst = requests.get(f"{API}/shows", timeout=15).json()
    # prefer non-live shows
    for s in lst:
        if not s.get("isLive"):
            return s["id"]
    return lst[0]["id"]


def test_momo_vod_debit_credit_routing(admin_token, db):
    show_id = _pick_vod_show()
    r = requests.post(
        f"{API}/billing/vod/{show_id}/momo",
        headers=auth(admin_token),
        json={"phone": TEST_PAYER},
        timeout=45,
    )
    assert r.status_code in (200, 201), f"Expected 2xx, got {r.status_code}: {r.text}"
    body = r.json()
    if body.get("alreadyUnlocked"):
        pytest.skip("user already premium / already purchased — cannot exercise MoMo path")
    ref = body.get("reference")
    assert ref
    assert body.get("amount") == 1000
    assert body.get("currency") == "RWF"
    time.sleep(1)
    doc = db.vod_purchases.find_one({"reference": ref})
    assert doc is not None
    assert doc.get("besoftAttempt") == "debit_credit", (
        f"VOD besoftAttempt must be 'debit_credit', got {doc.get('besoftAttempt')}"
    )


@pytest.mark.parametrize("phone", [
    MERCHANT_MSISDN,
    "+250 798 875 274",
    "0798875274",
])
def test_momo_vod_safety_guard(admin_token, phone):
    show_id = _pick_vod_show()
    r = requests.post(
        f"{API}/billing/vod/{show_id}/momo",
        headers=auth(admin_token),
        json={"phone": phone},
        timeout=20,
    )
    assert r.status_code == 400, f"VOD merchant phone {phone!r} MUST return 400, got {r.status_code}: {r.text}"


# ---------------- YouTube sync ----------------

def test_youtube_sync_admin(admin_token, db):
    r = requests.post(f"{API}/admin/youtube/sync", headers=auth(admin_token), json={}, timeout=120)
    assert r.status_code == 200, f"sync failed: {r.status_code} {r.text}"
    body = r.json()
    assert body.get("ok") is True, f"ok not true: {body}"
    assert body.get("upserted", 0) > 0, f"upserted must be > 0: {body}"
    ch = body.get("channelTitle", "")
    assert "B&B Kigali" in ch or "BB Kigali" in ch or "bbkigali" in ch.lower(), f"unexpected channelTitle {ch!r}"
    # DB checks
    n_yt = db.shows.count_documents({"source": "youtube"})
    assert n_yt > 0, "no db.shows docs with source='youtube'"
    sample = db.shows.find_one({"source": "youtube"})
    assert sample.get("youtubeId"), f"youtubeId missing on synced show: {sample}"
    state = db.integration_state.find_one({"key": "youtube_sync"})
    assert state is not None
    assert state.get("lastSyncAt")


def test_youtube_status_admin(admin_token):
    r = requests.get(f"{API}/admin/youtube/status", headers=auth(admin_token), timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert body.get("key") == "youtube_sync"
    assert body.get("lastSyncAt")


def test_youtube_sync_unauthorized_no_token():
    r = requests.post(f"{API}/admin/youtube/sync", json={}, timeout=15)
    assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}: {r.text}"


def test_youtube_sync_unauthorized_non_admin(db):
    # Create a non-admin user via throwaway phone
    tmp_phone = "+250700000123"
    r = requests.post(f"{API}/auth/otp/start", json={"phone": tmp_phone}, timeout=15)
    if r.status_code != 200:
        pytest.skip("cannot create throwaway user for non-admin test")
    code = r.json().get("testCode")
    if not code:
        chal = db.otp_challenges.find_one({"phone": tmp_phone})
        code = chal.get("code") if chal else None
    if not code:
        pytest.skip("no OTP code retrievable")
    v = requests.post(f"{API}/auth/otp/verify", json={"phone": tmp_phone, "code": code}, timeout=15)
    if v.status_code != 200:
        pytest.skip("cannot verify throwaway user")
    tok = v.json().get("accessToken") or v.json().get("token")
    if v.json().get("user", {}).get("role") == "admin":
        pytest.skip("throwaway is admin, cannot test non-admin path")
    r2 = requests.post(f"{API}/admin/youtube/sync", headers=auth(tok), json={}, timeout=15)
    assert r2.status_code in (401, 403), f"non-admin got {r2.status_code}"


# ---------------- Apple Sign-In ----------------

def test_apple_invalid_token():
    r = requests.post(f"{API}/auth/apple", json={"identityToken": "invalid.token.here"}, timeout=20)
    assert r.status_code == 401, f"invalid Apple token should be 401, got {r.status_code}: {r.text}"


# ---------------- Delete Account ----------------

def test_delete_account_no_auth():
    r = requests.delete(f"{API}/auth/me", timeout=15)
    assert r.status_code == 401


def test_delete_account_throwaway_full_flow(db):
    # 1. Create throwaway
    r = requests.post(f"{API}/auth/otp/start", json={"phone": THROWAWAY_PHONE}, timeout=15)
    assert r.status_code == 200
    code = r.json().get("testCode")
    if not code:
        # non-admin phone: read the code from Mongo (WhatsApp/SMS sent the real one to a real number)
        chal = db.otp_challenges.find_one({"phone": THROWAWAY_PHONE})
        assert chal, "otp_challenges not created"
        code = chal.get("code")
    assert code, "no OTP code available"
    v = requests.post(f"{API}/auth/otp/verify", json={"phone": THROWAWAY_PHONE, "code": code}, timeout=15)
    assert v.status_code == 200, f"{v.status_code} {v.text}"
    body = v.json()
    tok = body.get("accessToken") or body.get("token")
    uid = body["user"]["id"]
    # confirm not admin (this phone must NOT be in ADMIN_PHONES)
    assert body["user"].get("role") != "admin", "throwaway must not be admin — check ADMIN_PHONES"

    # optional side data: create a payment doc via merchant guard (fails 400, no db side effect) — skip
    # 2. Delete
    d = requests.delete(f"{API}/auth/me", headers=auth(tok), timeout=15)
    assert d.status_code == 200, f"{d.status_code} {d.text}"
    assert d.json().get("ok") is True

    # 3. Verify purge
    assert db.users.find_one({"id": uid}) is None
    assert db.user_sessions.count_documents({"user_id": uid}) == 0
    assert db.otp_challenges.count_documents({"phone": THROWAWAY_PHONE}) == 0

    # 4. Token should no longer authorize (user gone)
    me = requests.get(f"{API}/auth/me", headers=auth(tok), timeout=10)
    assert me.status_code in (401, 404), f"deleted user still authed: {me.status_code}"


# ---------------- PayPal regressions ----------------

def test_paypal_subscription(admin_token):
    r = requests.post(
        f"{API}/billing/paypal/create-subscription",
        headers=auth(admin_token),
        json={"plan": "basic_monthly"},
        timeout=30,
    )
    assert r.status_code == 200, f"{r.status_code} {r.text}"
    body = r.json()
    assert body.get("subscriptionId")
    approve = body.get("approveUrl", "")
    assert approve.startswith("https://www.paypal.com") or approve.startswith("https://www.sandbox.paypal.com"), \
        f"unexpected approveUrl {approve!r}"


def test_paypal_vod(admin_token):
    show_id = _pick_vod_show()
    r = requests.post(
        f"{API}/billing/vod/{show_id}/create",
        headers=auth(admin_token),
        json={},
        timeout=30,
    )
    assert r.status_code == 200, f"{r.status_code} {r.text}"
    body = r.json()
    if body.get("alreadyUnlocked"):
        pytest.skip("user premium / already purchased")
    assert body.get("orderId")
    approve = body.get("approveUrl", "")
    assert approve.startswith("https://www.paypal.com") or approve.startswith("https://www.sandbox.paypal.com")
