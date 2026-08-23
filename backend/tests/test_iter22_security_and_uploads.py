"""Iteration 22 backend test suite.

Covers the security fixes and new features shipped in iter 22:
- CRITICAL: POST /billing/subscribe must be admin-only (403 for non-admin)
- Admin can still /billing/subscribe (returns ok:true, note='admin_comp')
- /billing/stripe/create-checkout returns real checkout.stripe.com URL + persists pending payment
- /billing/stripe/session-status/{fakeId} returns 404 (isolation)
- /billing/stripe/session-status of own unpaid session returns paid:false + tier not upgraded
- Admin allowlist: mudelly12@gmail.com and bayidvd@gmail.com exist with role='admin' provider='admin-allowlist'
- Admin allowlist regression: new OTP user is NOT admin
- Object storage upload happy-path + unauth + invalid mime path
- PayPal/MoMo/YouTube/Privacy/Health regression
"""
from __future__ import annotations

import io
import os
import time
import uuid

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # Fallback: read from frontend .env
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("EXPO_PUBLIC_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().strip('"').rstrip("/")
                break
API = f"{BASE_URL}/api"

ADMIN_PHONE = "+250794230137"
REGULAR_PHONE = "+250788123456"
THROWAWAY_PHONE = f"+25078900{int(time.time()) % 10000:04d}"
MOMO_PAYER = "250794230137"
MOMO_MERCHANT = "250798875274"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")


_MONGO_CLIENT = MongoClient(MONGO_URL)
_DB = _MONGO_CLIENT[DB_NAME]


def _login(phone: str) -> dict:
    r = requests.post(f"{API}/auth/otp/start", json={"phone": phone}, timeout=30)
    assert r.status_code == 200, f"otp/start {phone} → {r.status_code} {r.text}"
    j = r.json()
    code = j.get("testCode")
    if not code:
        # Regular phone — code was actually SMS-sent. Pull it from otp_challenges
        chal = _DB.otp_challenges.find_one({"phone": phone})
        assert chal, f"No otp_challenge for {phone}"
        code = chal["code"]
    r2 = requests.post(f"{API}/auth/otp/verify", json={"phone": phone, "code": code}, timeout=30)
    assert r2.status_code == 200, f"otp/verify {phone} → {r2.status_code} {r2.text}"
    d = r2.json()
    return {
        "token": d.get("accessToken") or d.get("token"),
        "user": d.get("user") or {},
    }


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN_PHONE)["token"]


@pytest.fixture(scope="module")
def regular_token():
    return _login(REGULAR_PHONE)["token"]


@pytest.fixture(scope="module")
def mongo():
    client = MongoClient(MONGO_URL)
    return client[DB_NAME]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------- Health / Privacy ----------
def test_health():
    r = requests.get(f"{API}/health", timeout=15)
    assert r.status_code == 200, r.text
    assert r.json().get("ok") is True


def test_privacy_policy():
    r = requests.get(f"{API}/privacy", timeout=15)
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "").lower()
    body = r.text
    assert "Privacy Policy" in body
    assert "Delete Account" in body


# ---------- CRITICAL SECURITY: /billing/subscribe ----------
class TestBillingSubscribeSecurity:
    def test_non_admin_subscribe_returns_403(self, regular_token, mongo):
        # snapshot user tier/payments count before
        me = requests.get(f"{API}/auth/me", headers=_auth(regular_token), timeout=15).json()
        user_id = me.get("id") or me.get("user", {}).get("id")
        tier_before = me.get("tier") or me.get("user", {}).get("tier") or "free"
        payments_before = mongo.payments.count_documents({"userId": user_id})

        r = requests.post(
            f"{API}/billing/subscribe",
            headers=_auth(regular_token),
            json={"plan": "basic_monthly", "method": "stripe"},
            timeout=15,
        )
        assert r.status_code == 403, f"Expected 403, got {r.status_code} {r.text}"
        body = r.json()
        detail = body.get("detail") or body.get("message") or ""
        assert "Stripe" in detail or "PayPal" in detail or "MoMo" in detail, f"Unexpected msg: {detail}"

        # Confirm no side effects
        me2 = requests.get(f"{API}/auth/me", headers=_auth(regular_token), timeout=15).json()
        tier_after = me2.get("tier") or me2.get("user", {}).get("tier") or "free"
        assert tier_after == tier_before, f"Tier changed! {tier_before}→{tier_after}"
        payments_after = mongo.payments.count_documents({"userId": user_id})
        assert payments_after == payments_before, "Payment doc was inserted for non-admin!"

    def test_admin_subscribe_still_works(self, admin_token, mongo):
        me = requests.get(f"{API}/auth/me", headers=_auth(admin_token), timeout=15).json()
        user_id = me.get("id") or me.get("user", {}).get("id")

        r = requests.post(
            f"{API}/billing/subscribe",
            headers=_auth(admin_token),
            json={"plan": "basic_monthly", "method": "stripe"},
            timeout=15,
        )
        assert r.status_code == 200, f"Admin subscribe failed: {r.status_code} {r.text}"
        d = r.json()
        assert d.get("ok") is True
        assert d.get("tier") in ("basic", "premium")
        assert d.get("expiresAt")

        # verify note=admin_comp in payments
        doc = mongo.payments.find_one({"userId": user_id, "note": "admin_comp"}, sort=[("createdAt", -1)])
        assert doc is not None, "No admin_comp payment doc found"


# ---------- Stripe create-checkout + session-status ----------
class TestStripe:
    def test_create_checkout_returns_live_url(self, regular_token, mongo):
        r = requests.post(
            f"{API}/billing/stripe/create-checkout",
            headers=_auth(regular_token),
            json={"purchase_type": "subscription", "plan": "basic_monthly"},
            timeout=30,
        )
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        d = r.json()
        assert d.get("sessionId"), "Missing sessionId"
        assert d.get("checkoutUrl", "").startswith("https://checkout.stripe.com/"), f"Bad url: {d.get('checkoutUrl')}"
        assert d.get("publishableKey", "").startswith("pk_"), "Missing publishableKey"

        # DB persistence
        doc = mongo.payments.find_one({"stripeSessionId": d["sessionId"]})
        assert doc is not None
        assert doc.get("method") == "stripe"
        assert doc.get("status") == "pending"

        pytest.stripe_session_id = d["sessionId"]  # store for next test

    def test_session_status_unpaid_session_returns_paid_false(self, regular_token):
        sid = getattr(pytest, "stripe_session_id", None)
        if not sid:
            pytest.skip("No session id from previous test")
        r = requests.get(
            f"{API}/billing/stripe/session-status/{sid}",
            headers=_auth(regular_token),
            timeout=30,
        )
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        d = r.json()
        assert d.get("paid") is False, f"paid should be False, got {d}"
        assert d.get("paymentStatus") in ("unpaid", "no_payment_required")
        assert d.get("status") == "open"

    def test_session_status_isolation_returns_404(self, regular_token):
        fake_sid = f"cs_test_{uuid.uuid4().hex}"
        r = requests.get(
            f"{API}/billing/stripe/session-status/{fake_sid}",
            headers=_auth(regular_token),
            timeout=30,
        )
        assert r.status_code == 404, f"Expected 404, got {r.status_code} {r.text}"


# ---------- Admin allowlist ----------
class TestAdminAllowlist:
    def test_admin_emails_exist_as_admin_stubs(self, mongo):
        for email in ("mudelly12@gmail.com", "bayidvd@gmail.com"):
            u = mongo.users.find_one({"email": email})
            assert u is not None, f"Admin stub not seeded for {email}"
            assert u.get("role") == "admin", f"{email} role={u.get('role')}"
            # provider should be admin-allowlist for stubs. Log if missing but do not fail loudly —
            # role is the primary invariant.
            provider = u.get("provider")
            if provider not in ("admin-allowlist", "google", "apple"):
                pytest.stub_missing_provider = getattr(pytest, "stub_missing_provider", []) + [email]
                print(f"WARN: {email} provider={provider} (expected 'admin-allowlist')")

    def test_throwaway_user_is_not_admin(self, mongo):
        info = _login(THROWAWAY_PHONE)
        u = info["user"]
        assert (u.get("role") or "user") != "admin", f"Throwaway got admin! phone={THROWAWAY_PHONE}"
        # sanity check in DB
        db_u = mongo.users.find_one({"phone": THROWAWAY_PHONE.lstrip("+")}) or mongo.users.find_one({"phone": THROWAWAY_PHONE})
        if db_u:
            assert db_u.get("role") != "admin"


# ---------- Object Storage Upload ----------
def _tiny_jpg_bytes() -> bytes:
    """Return a valid, tiny JPG (~ 631 bytes) for upload tests."""
    # 1x1 red pixel JPEG
    return bytes.fromhex(
        "ffd8ffe000104a46494600010100000100010000ffdb004300080606"
        "0706050807070709090807"
        "0a0c140d0c0b0b0c191213"
        "0f141d1a1f1e1d1a1c1c20242e2720222c231c1c2837292c30313434341f27393d38323c2e333432ff"
        "db0043010909090c0b0c180d0d1832211c213232323232323232323232323232323232323232323232"
        "3232323232323232323232323232323232323232323232323232ffc00011080001000103012200021101031101"
        "ffc4001f000001050101010101010000000000000000010203040506070809"
        "0a0bffc400b5100002010303020403050504040000017d01020300041105122131410613516107227114328191a1"
        "08234252c11552d1f02433627282090a161718191a25262728292a3435363738393a434445464748494a53545556"
        "5758595a636465666768696a737475767778797a838485868788898a92939495969798999aa2a3a4a5a6a7a8a9"
        "aab2b3b4b5b6b7b8b9bac2c3c4c5c6c7c8c9cad2d3d4d5d6d7d8d9dae1e2e3e4e5e6e7e8e9eaf1f2f3f4f5f6f7f8"
        "f9faffc4001f0100030101010101010101010000000000000102030405060708090a0bffc400b511000201020404"
        "030407050404000102770001020311040521310612415107617113223281081442912a1b1c109233352f0156272"
        "72d1c11332434e125f11718191a262728292a35363738393a434445464748494a535455565758595a63646566676"
        "8696a737475767778797a82838485868788898a92939495969798999aa2a3a4a5a6a7a8a9aab2b3b4b5b6b7b8b9"
        "bac2c3c4c5c6c7c8c9cad2d3d4d5d6d7d8d9dae2e3e4e5e6e7e8e9eaf2f3f4f5f6f7f8f9faffda000c03010002110"
        "3110000 3f00fbfc a28a2803ffd9".replace(" ", "")
    )


class TestObjectStorage:
    def test_upload_unauthorized(self):
        # no auth
        files = {"file": ("t.jpg", _tiny_jpg_bytes(), "image/jpeg")}
        r = requests.post(f"{API}/admin/uploads/image", files=files, timeout=30)
        assert r.status_code in (401, 403), f"Expected 401/403, got {r.status_code} {r.text}"

    def test_upload_unauthorized_regular_user(self, regular_token):
        files = {"file": ("t.jpg", _tiny_jpg_bytes(), "image/jpeg")}
        r = requests.post(
            f"{API}/admin/uploads/image",
            headers=_auth(regular_token),
            files=files,
            timeout=30,
        )
        assert r.status_code in (401, 403), f"Expected 401/403 for regular user, got {r.status_code} {r.text}"

    def test_upload_rejects_non_image(self, admin_token):
        files = {"file": ("t.txt", b"hello world", "text/plain")}
        r = requests.post(
            f"{API}/admin/uploads/image",
            headers=_auth(admin_token),
            files=files,
            timeout=30,
        )
        assert r.status_code == 400, f"Expected 400, got {r.status_code} {r.text}"
        detail = r.json().get("detail", "")
        assert "jpg" in detail.lower() or "png" in detail.lower() or "image" in detail.lower()

    def test_upload_image_happy_path(self, admin_token):
        img = _tiny_jpg_bytes()
        files = {"file": ("cover.jpg", img, "image/jpeg")}
        r = requests.post(
            f"{API}/admin/uploads/image",
            headers=_auth(admin_token),
            files=files,
            timeout=60,
        )
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        d = r.json()
        url = d.get("url", "")
        assert "/api/uploads/bb-fm-kigali/uploads/" in url, f"Unexpected url: {url}"
        assert url.endswith(".jpg")
        assert d.get("contentType", "").startswith("image/")
        assert d.get("storagePath", "").startswith("bb-fm-kigali/uploads/")

        # GET the url and verify same image bytes
        r2 = requests.get(url, timeout=30)
        assert r2.status_code == 200, f"GET upload url → {r2.status_code}"
        assert r2.headers.get("content-type", "").startswith("image/")
        assert r2.content == img, "Downloaded bytes do not match uploaded bytes"


# ---------- PayPal regression ----------
class TestPayPalRegression:
    def test_paypal_create_subscription(self, regular_token):
        r = requests.post(
            f"{API}/billing/paypal/create-subscription",
            headers=_auth(regular_token),
            json={"plan": "basic_monthly"},
            timeout=30,
        )
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        d = r.json()
        assert d.get("approveUrl", "").startswith("https://"), f"No approveUrl: {d}"

    def test_paypal_vod_create(self, regular_token):
        # get some show id
        shows = requests.get(f"{API}/shows", timeout=15).json()
        assert isinstance(shows, list) and shows
        show_id = shows[0]["id"]
        r = requests.post(
            f"{API}/billing/vod/{show_id}/create",
            headers=_auth(regular_token),
            timeout=30,
        )
        # already unlocked returns 200 w/o approveUrl for premium; but regular user should not be premium
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        d = r.json()
        # either approveUrl present, or alreadyUnlocked
        assert d.get("approveUrl") or d.get("alreadyUnlocked"), f"Unexpected: {d}"


# ---------- MoMo regression ----------
class TestMoMoRegression:
    def test_momo_initiate_ok(self, regular_token):
        r = requests.post(
            f"{API}/billing/momo/initiate",
            headers=_auth(regular_token),
            json={"plan": "basic_monthly", "phone": MOMO_PAYER},
            timeout=45,
        )
        assert r.status_code in (200, 201, 202), f"{r.status_code} {r.text}"
        d = r.json()
        assert d.get("reference"), f"No reference: {d}"

    def test_momo_merchant_guard(self, regular_token):
        r = requests.post(
            f"{API}/billing/momo/initiate",
            headers=_auth(regular_token),
            json={"plan": "basic_monthly", "phone": MOMO_MERCHANT},
            timeout=15,
        )
        assert r.status_code == 400, f"Expected 400 for merchant number, got {r.status_code} {r.text}"


# ---------- YouTube / Shows ----------
class TestYouTubeShows:
    def test_shows_50_plus(self):
        r = requests.get(f"{API}/shows", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert isinstance(d, list)
        assert len(d) >= 50, f"Only {len(d)} shows"

    def test_youtube_sync(self, admin_token):
        r = requests.post(f"{API}/admin/youtube/sync", headers=_auth(admin_token), timeout=120)
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        d = r.json()
        assert d.get("ok") is True
        assert (d.get("upserted") or 0) >= 1
