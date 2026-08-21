"""BB FM Kigali backend API tests."""
import os
import pytest
import requests

BASE_URL = "https://radio-vod-platform.preview.emergentagent.com"
TEST_PHONE = "+250788199001"
OTP_CODE = "123456"


@pytest.fixture(scope="session")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def auth_token(api):
    r = api.post(f"{BASE_URL}/api/auth/otp/start", json={"phone": TEST_PHONE})
    assert r.status_code == 200, r.text
    r = api.post(f"{BASE_URL}/api/auth/otp/verify", json={"phone": TEST_PHONE, "code": OTP_CODE})
    assert r.status_code == 200, r.text
    return r.json()["accessToken"]


# ---- Health ----
def test_health(api):
    r = api.get(f"{BASE_URL}/api/")
    assert r.status_code == 200
    assert r.json().get("ok") is True


# ---- Auth ----
def test_otp_start_returns_test_code(api):
    r = api.post(f"{BASE_URL}/api/auth/otp/start", json={"phone": TEST_PHONE})
    assert r.status_code == 200
    j = r.json()
    assert j["testCode"] == "123456"
    assert j["ok"] is True


def test_otp_start_invalid_phone(api):
    r = api.post(f"{BASE_URL}/api/auth/otp/start", json={"phone": "12"})
    assert r.status_code == 400


def test_otp_verify_success(api):
    api.post(f"{BASE_URL}/api/auth/otp/start", json={"phone": TEST_PHONE})
    r = api.post(f"{BASE_URL}/api/auth/otp/verify", json={"phone": TEST_PHONE, "code": OTP_CODE})
    assert r.status_code == 200
    j = r.json()
    assert "accessToken" in j and j["accessToken"]
    assert j["user"]["phone"] == TEST_PHONE
    assert j["user"]["tier"] in ("free", "basic", "premium")


def test_otp_verify_wrong_code(api):
    api.post(f"{BASE_URL}/api/auth/otp/start", json={"phone": TEST_PHONE})
    r = api.post(f"{BASE_URL}/api/auth/otp/verify", json={"phone": TEST_PHONE, "code": "000000"})
    assert r.status_code == 401


def test_me_requires_auth(api):
    r = api.get(f"{BASE_URL}/api/auth/me")
    assert r.status_code == 401


def test_me_with_token(api, auth_token):
    r = api.get(f"{BASE_URL}/api/auth/me", headers={"Authorization": f"Bearer {auth_token}"})
    assert r.status_code == 200
    assert r.json()["phone"] == TEST_PHONE


# ---- Radio ----
def test_now_playing(api):
    r = api.get(f"{BASE_URL}/api/radio/now-playing")
    assert r.status_code == 200
    j = r.json()
    assert "streamUrl" in j and j["streamUrl"]
    assert "showTitle" in j


def test_schedule(api):
    r = api.get(f"{BASE_URL}/api/radio/schedule")
    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list)
    assert len(items) >= 1
    assert "showTitle" in items[0]


# ---- Shows ----
def test_shows_seeded(api):
    r = api.get(f"{BASE_URL}/api/shows")
    assert r.status_code == 200
    items = r.json()
    assert len(items) >= 6, f"expected 6 seeded shows, got {len(items)}"


def test_shows_filter_podcast(api):
    r = api.get(f"{BASE_URL}/api/shows", params={"category": "podcast"})
    assert r.status_code == 200
    items = r.json()
    assert len(items) >= 1
    for it in items:
        assert it["category"] == "podcast"


def test_premium_show_locked_for_free(api, auth_token):
    all_shows = api.get(f"{BASE_URL}/api/shows").json()
    premium = next((s for s in all_shows if s.get("premium")), None)
    assert premium is not None
    r = api.get(f"{BASE_URL}/api/shows/{premium['id']}", headers={"Authorization": f"Bearer {auth_token}"})
    assert r.status_code == 200
    j = r.json()
    # user starts free
    me = api.get(f"{BASE_URL}/api/auth/me", headers={"Authorization": f"Bearer {auth_token}"}).json()
    if me["tier"] == "free":
        assert j["locked"] is True
        assert j["videoUrl"] is None


def test_free_show_unlocked(api, auth_token):
    all_shows = api.get(f"{BASE_URL}/api/shows").json()
    free = next((s for s in all_shows if not s.get("premium")), None)
    assert free is not None
    r = api.get(f"{BASE_URL}/api/shows/{free['id']}", headers={"Authorization": f"Bearer {auth_token}"})
    assert r.status_code == 200
    assert r.json()["locked"] is False


# ---- News ----
def test_news_list(api):
    r = api.get(f"{BASE_URL}/api/news")
    assert r.status_code == 200
    items = r.json()
    assert len(items) >= 1
    assert "title" in items[0]


# ---- Billing ----
def test_plans(api):
    r = api.get(f"{BASE_URL}/api/billing/plans")
    assert r.status_code == 200
    plans = r.json()
    assert len(plans) == 4
    ids = {p["id"] for p in plans}
    assert ids == {"basic_monthly", "basic_yearly", "premium_monthly", "premium_yearly"}
    bm = next(p for p in plans if p["id"] == "basic_monthly")
    assert bm["amount"] == 1000 and bm["currency"] == "RWF"
    pm = next(p for p in plans if p["id"] == "premium_monthly")
    assert pm["amount"] == 3000


def test_subscribe_basic_stripe_and_verify(api, auth_token):
    headers = {"Authorization": f"Bearer {auth_token}"}
    r = api.post(f"{BASE_URL}/api/billing/subscribe",
                 json={"plan": "basic_monthly", "method": "stripe"},
                 headers=headers)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["mocked"] is True
    assert j["tier"] == "basic"
    # verify user upgraded via /me
    me = api.get(f"{BASE_URL}/api/auth/me", headers=headers).json()
    assert me["tier"] == "basic"


def test_subscribe_premium_momo(api, auth_token):
    headers = {"Authorization": f"Bearer {auth_token}"}
    r = api.post(f"{BASE_URL}/api/billing/subscribe",
                 json={"plan": "premium_monthly", "method": "mtn_momo", "phone": TEST_PHONE},
                 headers=headers)
    assert r.status_code == 200
    assert r.json()["tier"] == "premium"


def test_billing_history(api, auth_token):
    headers = {"Authorization": f"Bearer {auth_token}"}
    r = api.get(f"{BASE_URL}/api/billing/history", headers=headers)
    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list)
    assert len(items) >= 1
    assert items[0]["status"] == "success"


def test_premium_show_unlocked_after_upgrade(api, auth_token):
    # after premium upgrade, premium content should unlock
    headers = {"Authorization": f"Bearer {auth_token}"}
    all_shows = api.get(f"{BASE_URL}/api/shows").json()
    premium = next(s for s in all_shows if s.get("premium"))
    r = api.get(f"{BASE_URL}/api/shows/{premium['id']}", headers=headers).json()
    assert r["locked"] is False
    assert r.get("videoUrl")
