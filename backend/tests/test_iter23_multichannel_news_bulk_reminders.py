"""Iteration 23 backend test suite.

Covers:
- Multi-channel YouTube sync (@bbkigalifm + @BBSPORTSBAR)
- Admin news CRUD (POST/PATCH/DELETE) + role gating
- Bulk invite (idempotent + skip empty)
- Admin user edit (incl. self-demote guard)
- Subscription reminder manual + log + dedup
- Regression: MoMo initiate + merchant guard, Stripe checkout + non-admin subscribe 403,
  Privacy, Object Storage upload
"""
from __future__ import annotations

import io
import os
import time
import uuid
from datetime import datetime, timezone, timedelta

import pytest
import requests
from pymongo import MongoClient

# --------- Config ---------
BASE_URL = ""
with open("/app/frontend/.env") as f:
    for line in f:
        if line.startswith("EXPO_PUBLIC_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip().strip('"').rstrip("/")
            break
API = f"{BASE_URL}/api"

ADMIN_PHONE = "+250794230137"
REGULAR_PHONE = "+250788123456"
MOMO_PAYER = "250794230137"
MOMO_MERCHANT = "250798875274"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

_MONGO = MongoClient(MONGO_URL)
_DB = _MONGO[DB_NAME]


# --------- Helpers ---------
def _login(phone: str) -> dict:
    r = requests.post(f"{API}/auth/otp/start", json={"phone": phone}, timeout=30)
    assert r.status_code == 200, f"otp/start {phone} → {r.status_code} {r.text}"
    j = r.json()
    code = j.get("testCode")
    if not code:
        chal = _DB.otp_challenges.find_one({"phone": phone})
        assert chal, f"No otp_challenge doc for {phone}"
        code = chal["code"]
    r2 = requests.post(f"{API}/auth/otp/verify", json={"phone": phone, "code": code}, timeout=30)
    assert r2.status_code == 200, f"otp/verify {phone} → {r2.status_code} {r2.text}"
    d = r2.json()
    return {
        "token": d.get("accessToken") or d.get("token"),
        "user": d.get("user") or {},
    }


@pytest.fixture(scope="module")
def admin():
    return _login(ADMIN_PHONE)


@pytest.fixture(scope="module")
def regular():
    return _login(REGULAR_PHONE)


def H(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ==========================================================
# 1. MULTI-CHANNEL YOUTUBE SYNC
# ==========================================================
class TestYouTubeMultiChannel:
    def test_sync_returns_both_channels(self, admin):
        r = requests.post(f"{API}/admin/youtube/sync", headers=H(admin["token"]), timeout=120)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("ok") is True, j
        channels = j.get("channels") or []
        assert len(channels) >= 2, f"expected 2 channels, got {len(channels)}: {channels}"
        handles = {c.get("handle", "").lstrip("@").lower() for c in channels}
        assert "bbkigalifm" in handles, handles
        assert "bbsportsbar" in handles, handles
        for c in channels:
            assert c.get("upserted", 0) >= 1, f"channel {c.get('handle')} upserted={c.get('upserted')}"
        # Titles surfaced
        titles = {c.get("channelTitle", "") for c in channels}
        assert any("BB Kigali" in t or "B&B Kigali" in t for t in titles), titles
        assert any("SPORTS BAR" in t.upper() for t in titles), titles

    def test_status_returns_both_channels(self, admin):
        r = requests.get(f"{API}/admin/youtube/status", headers=H(admin["token"]), timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        entries = j.get("channels") or []
        # Only per-channel entries (skip the legacy 'youtube_sync' single-channel row
        # which is kept for backwards compatibility and lacks categorySlug)
        per_channel = [e for e in entries if e.get("key", "").startswith("youtube_sync:")]
        assert len(per_channel) >= 2, entries
        handles = {e.get("handle", "").lstrip("@").lower() for e in per_channel}
        assert "bbkigalifm" in handles and "bbsportsbar" in handles, handles
        for e in per_channel:
            assert e.get("channelTitle"), e
            assert e.get("categorySlug"), e
            assert e.get("lastSyncAt"), e

    def test_sports_bar_category_present(self):
        r = requests.get(f"{API}/categories", timeout=30)
        assert r.status_code == 200, r.text
        cats = r.json()
        slugs = {c.get("slug") for c in cats}
        assert "bbsportsbar-youtube" in slugs, slugs

    def test_sports_bar_shows_listing(self):
        r = requests.get(f"{API}/shows?category=bbsportsbar-youtube", timeout=30)
        assert r.status_code == 200, r.text
        shows = r.json()
        assert len(shows) >= 30, f"only {len(shows)} sports bar shows"
        for s in shows:
            assert s.get("source") == "youtube", s
            assert s.get("youtubeHandle", "").lstrip("@").lower() == "bbsportsbar", s.get("youtubeHandle")


# ==========================================================
# 2. ADMIN NEWS CRUD
# ==========================================================
class TestAdminNewsCRUD:
    news_id = None

    def test_regular_user_cannot_create(self, regular):
        r = requests.post(
            f"{API}/admin/news",
            headers=H(regular["token"]),
            json={"title": "TEST_forbidden", "summary": "x", "body": "y"},
            timeout=15,
        )
        assert r.status_code == 403, f"expected 403 got {r.status_code} {r.text}"

    def test_create_news(self, admin):
        payload = {
            "title": "TEST_Iter23 Post",
            "summary": "hi",
            "body": "body",
            "coverUrl": "https://picsum.photos/400",
            "category": "news",
        }
        r = requests.post(f"{API}/admin/news", headers=H(admin["token"]), json=payload, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("id"), j
        assert j.get("title") == "TEST_Iter23 Post"
        assert j.get("publishedAt"), j
        TestAdminNewsCRUD.news_id = j["id"]

    def test_news_visible_in_public_list(self):
        assert TestAdminNewsCRUD.news_id
        r = requests.get(f"{API}/news", timeout=15)
        assert r.status_code == 200, r.text
        ids = {n.get("id") for n in r.json()}
        assert TestAdminNewsCRUD.news_id in ids, f"created news not in GET /news list"

    def test_patch_news(self, admin):
        assert TestAdminNewsCRUD.news_id
        r = requests.patch(
            f"{API}/admin/news/{TestAdminNewsCRUD.news_id}",
            headers=H(admin["token"]),
            json={"title": "TEST_Updated", "summary": "u", "body": "b"},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        assert r.json().get("title") == "TEST_Updated"

    def test_regular_user_cannot_delete(self, regular):
        assert TestAdminNewsCRUD.news_id
        r = requests.delete(
            f"{API}/admin/news/{TestAdminNewsCRUD.news_id}",
            headers=H(regular["token"]),
            timeout=15,
        )
        assert r.status_code == 403, f"expected 403 got {r.status_code} {r.text}"

    def test_delete_news(self, admin):
        assert TestAdminNewsCRUD.news_id
        r = requests.delete(
            f"{API}/admin/news/{TestAdminNewsCRUD.news_id}",
            headers=H(admin["token"]),
            timeout=15,
        )
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True
        r2 = requests.get(f"{API}/news", timeout=15)
        assert r2.status_code == 200
        ids = {n.get("id") for n in r2.json()}
        assert TestAdminNewsCRUD.news_id not in ids, "news still present after delete"


# ==========================================================
# 3. BULK INVITE
# ==========================================================
class TestBulkInvite:
    """Uses stable throwaway phones so idempotency can be verified across runs.

    Cleanup at teardown removes the created stubs.
    """
    # unique per-run suffix to keep isolation between iterations
    SUFFIX = f"{int(time.time()) % 10000:04d}"
    P1 = f"+2507890{SUFFIX}1"
    P2 = f"+2507890{SUFFIX}2"
    E1 = f"test1_{SUFFIX}@example.com"
    E2 = f"test2_{SUFFIX}@example.com"

    @classmethod
    def _cleanup(cls):
        _DB.users.delete_many({
            "$or": [
                {"phone": {"$in": [cls.P1, cls.P2, cls.P1.lstrip("+"), cls.P2.lstrip("+")]}},
                {"email": {"$in": [cls.E1, cls.E2]}},
            ]
        })

    def test_00_precleanup(self):
        self._cleanup()

    def _payload(self, include_skip: bool = False):
        rows = [
            {"phone": self.P1, "displayName": "Alice", "role": "user"},
            {"email": self.E1, "displayName": "Bob", "role": "user"},
            {"phone": self.P2, "email": self.E2, "displayName": "Charlie", "role": "admin"},
        ]
        if include_skip:
            rows.append({"displayName": "NoContact", "role": "user"})
        return {"users": rows}

    def test_bulk_invite_creates_three(self, admin):
        r = requests.post(
            f"{API}/admin/users/bulk-invite",
            headers=H(admin["token"]),
            json=self._payload(),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("created") >= 3, j
        assert j.get("updated") == 0, j
        assert j.get("skipped") == 0, j
        assert j.get("errors") == [], j

    def test_bulk_invite_idempotent_updates(self, admin):
        r = requests.post(
            f"{API}/admin/users/bulk-invite",
            headers=H(admin["token"]),
            json=self._payload(),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("created") == 0, f"expected 0 created got {j}"
        assert j.get("updated") == 3, f"expected 3 updated got {j}"
        assert j.get("skipped") == 0, j

    def test_bulk_invite_skip_empty_row(self, admin):
        r = requests.post(
            f"{API}/admin/users/bulk-invite",
            headers=H(admin["token"]),
            json=self._payload(include_skip=True),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("skipped") == 1, f"expected 1 skipped got {j}"

    def test_regular_cannot_bulk_invite(self, regular):
        r = requests.post(
            f"{API}/admin/users/bulk-invite",
            headers=H(regular["token"]),
            json=self._payload(),
            timeout=15,
        )
        assert r.status_code == 403, r.text

    def test_zzz_cleanup(self):
        self._cleanup()


# ==========================================================
# 4. USER EDIT + SELF-DEMOTE
# ==========================================================
class TestUserEdit:
    target_id = None

    def test_setup_target(self, admin):
        # Create a throwaway user via invite to edit safely
        r = requests.post(
            f"{API}/admin/users/invite",
            headers=H(admin["token"]),
            json={"phone": f"+2507891{int(time.time())%1000000:06d}", "displayName": "TEST_edit_target", "role": "user"},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        TestUserEdit.target_id = r.json()["id"]

    def test_patch_user(self, admin):
        assert TestUserEdit.target_id
        r = requests.patch(
            f"{API}/admin/users/{TestUserEdit.target_id}",
            headers=H(admin["token"]),
            json={"displayName": "TEST_New Name", "tier": "basic"},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("displayName") == "TEST_New Name", j
        assert j.get("tier") == "basic", j
        # Verify persistence
        u = _DB.users.find_one({"id": TestUserEdit.target_id})
        assert u.get("displayName") == "TEST_New Name"
        assert u.get("tier") == "basic"

    def test_self_demote_forbidden(self, admin):
        aid = admin["user"].get("id")
        assert aid
        r = requests.patch(
            f"{API}/admin/users/{aid}",
            headers=H(admin["token"]),
            json={"role": "user"},
            timeout=15,
        )
        assert r.status_code == 400, r.text
        assert "demote" in r.text.lower(), r.text

    def test_zzz_cleanup(self):
        if TestUserEdit.target_id:
            _DB.users.delete_one({"id": TestUserEdit.target_id})


# ==========================================================
# 5. SUBSCRIPTION REMINDERS
# ==========================================================
class TestSubscriptionReminders:
    FAKE_ID = None
    FAKE_PHONE = "+250789111222"

    @classmethod
    def _cleanup(cls):
        _DB.users.delete_many({"phone": cls.FAKE_PHONE})
        if cls.FAKE_ID:
            _DB.subscription_reminders.delete_many({"userId": cls.FAKE_ID})

    def test_manual_run(self, admin):
        r = requests.post(
            f"{API}/admin/subscriptions/send-reminders",
            headers=H(admin["token"]),
            timeout=60,
        )
        assert r.status_code == 200, r.text
        j = r.json()
        assert "checked" in j and "sent" in j and "failed" in j, j
        assert j["checked"] >= 0 and j["sent"] >= 0 and j["failed"] >= 0

    def test_list_reminders(self, admin):
        r = requests.get(
            f"{API}/admin/subscriptions/reminders",
            headers=H(admin["token"]),
            timeout=15,
        )
        assert r.status_code == 200, r.text
        assert isinstance(r.json(), list)

    def test_dedup_after_second_pass(self, admin):
        # Seed a user expiring in ~3 days
        self._cleanup()
        expires = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
        uid = str(uuid.uuid4())
        _DB.users.insert_one({
            "id": uid,
            "phone": self.FAKE_PHONE,
            "displayName": "TEST_reminder_dedup",
            "role": "user",
            "tier": "basic",
            "subscriptionExpiresAt": expires,
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "provider": "test-seed",
        })
        TestSubscriptionReminders.FAKE_ID = uid

        # 1st pass
        r1 = requests.post(f"{API}/admin/subscriptions/send-reminders",
                           headers=H(admin["token"]), timeout=60)
        assert r1.status_code == 200, r1.text
        count1 = _DB.subscription_reminders.count_documents({"userId": uid})
        assert count1 == 1, f"expected 1 reminder doc after first pass, got {count1}"
        key1 = _DB.subscription_reminders.find_one({"userId": uid}).get("key")

        # 2nd pass — must dedup
        r2 = requests.post(f"{API}/admin/subscriptions/send-reminders",
                           headers=H(admin["token"]), timeout=60)
        assert r2.status_code == 200, r2.text
        count2 = _DB.subscription_reminders.count_documents({"userId": uid})
        assert count2 == 1, f"dedup failed, got {count2} reminder docs after second pass"
        # key stays identical
        docs = list(_DB.subscription_reminders.find({"userId": uid}))
        assert docs[0].get("key") == key1

    def test_zzz_cleanup(self):
        self._cleanup()


# ==========================================================
# 6. REGRESSION
# ==========================================================
class TestRegression:
    def test_momo_initiate_payer(self, admin):
        r = requests.post(
            f"{API}/billing/momo/initiate",
            headers=H(admin["token"]),
            json={"phone": MOMO_PAYER, "plan": "basic_monthly"},
            timeout=60,
        )
        assert 200 <= r.status_code < 300, f"{r.status_code} {r.text}"

    def test_momo_merchant_guard(self, admin):
        r = requests.post(
            f"{API}/billing/momo/initiate",
            headers=H(admin["token"]),
            json={"phone": MOMO_MERCHANT, "plan": "basic_monthly"},
            timeout=30,
        )
        assert r.status_code == 400, f"expected 400 got {r.status_code} {r.text}"

    def test_stripe_create_checkout(self, admin):
        r = requests.post(
            f"{API}/billing/stripe/create-checkout",
            headers=H(admin["token"]),
            json={"purchase_type": "subscription", "plan": "basic_monthly"},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        j = r.json()
        url = j.get("checkoutUrl") or j.get("url", "")
        assert url.startswith("https://checkout.stripe.com/"), j

    def test_non_admin_subscribe_403(self, regular):
        r = requests.post(
            f"{API}/billing/subscribe",
            headers=H(regular["token"]),
            json={"plan": "basic_monthly", "method": "stripe"},
            timeout=15,
        )
        assert r.status_code == 403, r.text

    def test_privacy_html(self):
        r = requests.get(f"{API}/privacy", timeout=15)
        assert r.status_code == 200, r.text
        assert "text/html" in r.headers.get("content-type", ""), r.headers
        assert "Privacy" in r.text

    def test_object_storage_upload(self, admin):
        # Minimal valid 1x1 red JPEG
        jpg = bytes.fromhex(
            "ffd8ffe000104a46494600010100000100010000ffdb004300080606"
            "07060805070707090908 0a0c140d0c0b0b0c1912130f141d1a1f1e1d"
            "1a1c1c20242e2720222c231c1c2837292c30313434341f27393d3832"
            "3c2e333432ffdb0043010909090c0b0c180d0d1832211c213232323232"
            "323232323232323232323232323232323232323232323232323232323232"
            "3232323232323232323232323232ffc00011080001000103012200021101"
            "031101ffc4001f0000010501010101010100000000000000000102030405"
            "060708090a0bffc400b5100002010303020403050504040000017d010203"
            "00041105122131410613516107227114328191a1082342b1c11552d1f024"
            "33627282090a161718191a25262728292a3435363738393a434445464748"
            "494a535455565758595a636465666768696a737475767778797a83848586"
            "8788898a92939495969798999aa2a3a4a5a6a7a8a9aab2b3b4b5b6b7b8b9"
            "bac2c3c4c5c6c7c8c9cad2d3d4d5d6d7d8d9dae1e2e3e4e5e6e7e8e9eaf1"
            "f2f3f4f5f6f7f8f9faffc4001f010003010101010101010101010000000000"
            "000102030405060708090a0bffc400b511000201020404030407050404000"
            "1027700010203110405213106124151076171132232 8108144291a1b1c1"
            "09233352f0156272d10a162434e125f11718191a262728292a35363738393a"
            "434445464748494a535455565758595a636465666768696a73747576777879"
            "7a82838485868788898a92939495969798999aa2a3a4a5a6a7a8a9aab2b3b4"
            "b5b6b7b8b9bac2c3c4c5c6c7c8c9cad2d3d4d5d6d7d8d9dae2e3e4e5e6e7e8"
            "e9eaf2f3f4f5f6f7f8f9faffda000c03010002110311003f00fbfb28a28aff d9".replace(" ", "")
        )
        files = {"file": ("test.jpg", io.BytesIO(jpg), "image/jpeg")}
        r = requests.post(
            f"{API}/admin/uploads/image",
            headers=H(admin["token"]),
            files=files,
            timeout=60,
        )
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("url", "").startswith("http"), j
        assert j.get("storagePath"), j
