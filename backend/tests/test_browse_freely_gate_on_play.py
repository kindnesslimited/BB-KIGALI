"""
Iteration 14 — Verify "browse freely, gate on play" business rule.

Guests (no Authorization header) must be able to browse shows, categories, programs, news,
and preview show detail. Only playback / purchase requires auth. Admin bearer path also
verified for /shows/{id} and admin protection.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL") or os.environ.get("EXPO_BACKEND_URL")
if not BASE_URL:
    raise RuntimeError("EXPO_PUBLIC_BACKEND_URL / EXPO_BACKEND_URL not set")
BASE_URL = BASE_URL.rstrip("/")

ADMIN_PHONE = "+250798875272"
NON_ADMIN_PHONE = "+250788123456"


@pytest.fixture(scope="module")
def http():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def admin_token(http):
    start = http.post(f"{BASE_URL}/api/auth/otp/start", json={"phone": ADMIN_PHONE}, timeout=30)
    assert start.status_code == 200, start.text
    code = start.json().get("testCode") or "123456"
    verify = http.post(f"{BASE_URL}/api/auth/otp/verify", json={"phone": ADMIN_PHONE, "code": code}, timeout=30)
    assert verify.status_code == 200, verify.text
    data = verify.json()
    assert data.get("user", {}).get("role") == "admin", data
    return data["accessToken"]


@pytest.fixture(scope="module")
def user_token(http):
    start = http.post(f"{BASE_URL}/api/auth/otp/start", json={"phone": NON_ADMIN_PHONE}, timeout=30)
    assert start.status_code == 200, start.text
    code = start.json().get("testCode")
    if not code:
        # Real SMS sent -> we can't intercept. Try direct Mongo lookup.
        try:
            from pymongo import MongoClient
            mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
            db_name = os.environ.get("DB_NAME", "test_database")
            client = MongoClient(mongo_url, serverSelectionTimeoutMS=3000)
            challenge = client[db_name].otp_challenges.find_one({"phone": NON_ADMIN_PHONE})
            if challenge:
                code = challenge.get("code")
        except Exception:
            pass
    if not code:
        pytest.skip("Could not obtain non-admin OTP code (real SMS provider active)")
    verify = http.post(f"{BASE_URL}/api/auth/otp/verify", json={"phone": NON_ADMIN_PHONE, "code": code}, timeout=30)
    assert verify.status_code == 200, verify.text
    data = verify.json()
    return data["accessToken"]


@pytest.fixture(scope="module")
def first_show_id(http):
    r = http.get(f"{BASE_URL}/api/shows", timeout=20)
    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list) and len(items) > 0, "No shows seeded"
    return items[0]["id"]


# -------------- Guest browse (no Authorization header) --------------

class TestGuestBrowse:
    def test_shows_list_public(self, http):
        r = http.get(f"{BASE_URL}/api/shows", timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
        assert len(data) > 0, "shows list is empty"
        # verify entries have id and title
        s0 = data[0]
        assert "id" in s0 and "title" in s0

    def test_show_detail_guest_locked_login_required(self, http, first_show_id):
        r = http.get(f"{BASE_URL}/api/shows/{first_show_id}", timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("locked") is True, f"Expected locked=True, got {data.get('locked')}"
        assert data.get("loginRequired") is True, f"Expected loginRequired=True, got {data.get('loginRequired')}"
        assert data.get("videoUrl") is None, f"Expected videoUrl null, got {data.get('videoUrl')}"
        assert data.get("unlockCurrency") == "EUR"
        assert data.get("unlockPrice") is not None
        assert data.get("unlockPriceRwf") is not None

    def test_categories_public(self, http):
        r = http.get(f"{BASE_URL}/api/categories", timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
        assert len(data) > 0, "categories list is empty"

    def test_programs_public(self, http):
        r = http.get(f"{BASE_URL}/api/programs", timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
        assert len(data) > 0, "programs list is empty"

    def test_news_public(self, http):
        r = http.get(f"{BASE_URL}/api/news", timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)

    def test_show_detail_invalid_token_still_returns_guest_view(self, http, first_show_id):
        # invalid bearer must not raise 401 — get_optional_user returns None
        r = http.get(
            f"{BASE_URL}/api/shows/{first_show_id}",
            headers={"Authorization": "Bearer garbage.token.here"},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("locked") is True
        assert data.get("loginRequired") is True


# -------------- Admin bearer path --------------

class TestAuthenticatedShowDetail:
    def test_show_detail_admin_locked_no_login_required(self, http, admin_token, first_show_id):
        r = http.get(
            f"{BASE_URL}/api/shows/{first_show_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        # admin is free tier by default -> locked True but loginRequired must NOT be set (or falsy)
        assert data.get("locked") is True, f"Admin (free tier) should still see locked=true, got {data}"
        assert not data.get("loginRequired"), (
            f"Authenticated user must NOT see loginRequired=true, got {data.get('loginRequired')}"
        )


# -------------- Protected admin endpoints still gated --------------

class TestAdminProtection:
    def test_admin_users_no_auth_returns_401(self, http):
        r = http.get(f"{BASE_URL}/api/admin/users", timeout=20)
        assert r.status_code == 401, f"Expected 401, got {r.status_code}: {r.text}"

    def test_admin_users_non_admin_returns_403(self, http, user_token):
        r = http.get(
            f"{BASE_URL}/api/admin/users",
            headers={"Authorization": f"Bearer {user_token}"},
            timeout=20,
        )
        assert r.status_code == 403, f"Expected 403, got {r.status_code}: {r.text}"

    def test_admin_users_admin_returns_200(self, http, admin_token):
        r = http.get(
            f"{BASE_URL}/api/admin/users",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        # response can be a list or dict with users
        assert data is not None
