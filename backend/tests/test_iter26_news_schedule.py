"""Iteration 26 backend tests — News source fields (sourceName/sourceUrl),
coverUrl↔thumbnail mirroring, and new Admin Schedule CRUD.

Skips tests only if OTP/admin auth cannot be established.
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/") or "https://radio-vod-platform.preview.emergentagent.com"
ADMIN_PHONE = "+250794230137"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin JWT via dev OTP flow."""
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/otp/start", json={"phone": ADMIN_PHONE}, timeout=20)
    assert r.status_code == 200, f"otp/start failed: {r.status_code} {r.text}"
    code = r.json().get("testCode")
    if not code:
        # fallback try common dev code
        code = "123456"
    r2 = s.post(f"{BASE_URL}/api/auth/otp/verify", json={"phone": ADMIN_PHONE, "code": code}, timeout=20)
    if r2.status_code != 200:
        pytest.skip(f"OTP verify failed: {r2.status_code} {r2.text}")
    data = r2.json()
    token = data.get("accessToken") or data.get("session_token") or data.get("token")
    if not token:
        pytest.skip(f"No token in verify response: {data}")
    user = data.get("user") or {}
    if user.get("role") != "admin":
        pytest.skip(f"User is not admin: role={user.get('role')}")
    return token


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


# =============== NEWS TESTS ===============
class TestNews:
    def test_get_news_public_normalization(self):
        """GET /api/news must return items where coverUrl==thumbnail and summary==excerpt when present."""
        r = requests.get(f"{BASE_URL}/api/news", timeout=20)
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list)
        # If any items have coverUrl, they should also have thumbnail (mirror)
        for i in items:
            if i.get("coverUrl"):
                assert i.get("thumbnail") == i.get("coverUrl"), f"coverUrl↔thumbnail mismatch: {i.get('id')}"
            if i.get("summary"):
                assert i.get("excerpt") == i.get("summary"), f"summary↔excerpt mismatch: {i.get('id')}"

    def test_create_news_with_source_and_verify_mirror(self, auth_headers):
        """POST /api/admin/news accepts sourceName+sourceUrl; coverUrl mirrors thumbnail."""
        payload = {
            "title": f"TEST_ITER26 News {int(time.time())}",
            "summary": "Iter 26 summary line",
            "body": "Body...",
            "coverUrl": "https://images.pexels.com/photos/26447525/pexels-photo-26447525.jpeg",
            "sourceName": "Kigali Today",
            "sourceUrl": "https://kigalitoday.com/article/xyz",
            "category": "news",
            "published": True,
        }
        r = requests.post(f"{BASE_URL}/api/admin/news", json=payload, headers=auth_headers, timeout=20)
        assert r.status_code == 200, f"create failed: {r.status_code} {r.text}"
        doc = r.json()
        news_id = doc["id"]
        try:
            assert doc["sourceName"] == "Kigali Today"
            assert doc["sourceUrl"] == "https://kigalitoday.com/article/xyz"
            assert doc["coverUrl"] == payload["coverUrl"]
            assert doc["thumbnail"] == payload["coverUrl"], "coverUrl must mirror into thumbnail"
            assert doc["summary"] == payload["summary"]
            assert doc["excerpt"] == payload["summary"], "summary must mirror into excerpt"

            # Verify persistence via public GET
            r2 = requests.get(f"{BASE_URL}/api/news", timeout=20)
            assert r2.status_code == 200
            listed = [i for i in r2.json() if i.get("id") == news_id]
            assert len(listed) == 1, "created news not visible in public feed"
            n = listed[0]
            assert n["coverUrl"] == payload["coverUrl"]
            assert n["thumbnail"] == payload["coverUrl"]
            assert n["sourceName"] == "Kigali Today"
            assert n["sourceUrl"] == "https://kigalitoday.com/article/xyz"
        finally:
            # cleanup
            requests.delete(f"{BASE_URL}/api/admin/news/{news_id}", headers=auth_headers, timeout=20)

    def test_patch_news_source_and_mirror(self, auth_headers):
        # create
        create_payload = {
            "title": f"TEST_ITER26 Patch {int(time.time())}",
            "summary": "orig summary",
            "coverUrl": "https://images.pexels.com/photos/6883808/pexels-photo-6883808.jpeg",
        }
        r = requests.post(f"{BASE_URL}/api/admin/news", json=create_payload, headers=auth_headers, timeout=20)
        assert r.status_code == 200
        news_id = r.json()["id"]
        try:
            patch_payload = {
                "title": create_payload["title"],
                "summary": "updated summary",
                "coverUrl": "https://images.pexels.com/photos/23384428/pexels-photo-23384428.jpeg",
                "sourceName": "The New Times",
                "sourceUrl": "https://newtimes.co.rw/article/abc",
            }
            r2 = requests.patch(f"{BASE_URL}/api/admin/news/{news_id}", json=patch_payload, headers=auth_headers, timeout=20)
            assert r2.status_code == 200, f"patch failed: {r2.status_code} {r2.text}"
            doc = r2.json()
            assert doc["summary"] == "updated summary"
            assert doc["excerpt"] == "updated summary", "excerpt must mirror updated summary"
            assert doc["coverUrl"] == patch_payload["coverUrl"]
            assert doc["thumbnail"] == patch_payload["coverUrl"], "thumbnail must mirror updated coverUrl"
            assert doc["sourceName"] == "The New Times"
            assert doc["sourceUrl"] == "https://newtimes.co.rw/article/abc"
        finally:
            requests.delete(f"{BASE_URL}/api/admin/news/{news_id}", headers=auth_headers, timeout=20)

    def test_admin_news_requires_auth(self):
        """POST /api/admin/news without auth → 401/403."""
        r = requests.post(f"{BASE_URL}/api/admin/news", json={"title": "TEST_no_auth"}, timeout=20)
        assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}"


# =============== SCHEDULE TESTS ===============
class TestSchedule:
    def test_public_schedule_get_ok(self):
        r = requests.get(f"{BASE_URL}/api/radio/schedule", timeout=20)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_admin_schedule_crud_full(self, auth_headers):
        """POST → verify in public GET → PATCH → verify → DELETE → verify 404."""
        payload = {
            "time": "07:00 - 09:00",
            "showTitle": f"TEST_ITER26 Morning Show {int(time.time())}",
            "djName": "DJ Iter26",
            "days": ["mon", "tue", "wed", "thu", "fri"],
            "isLive": True,
            "order": 999,
        }
        r = requests.post(f"{BASE_URL}/api/admin/schedule", json=payload, headers=auth_headers, timeout=20)
        assert r.status_code == 200, f"create failed: {r.status_code} {r.text}"
        doc = r.json()
        sid = doc["id"]
        try:
            assert doc["time"] == payload["time"]
            assert doc["showTitle"] == payload["showTitle"]
            assert doc["djName"] == payload["djName"]
            assert doc["days"] == payload["days"]
            assert doc["isLive"] is True

            # Verify visible in public GET
            r2 = requests.get(f"{BASE_URL}/api/radio/schedule", timeout=20)
            assert r2.status_code == 200
            found = [i for i in r2.json() if i.get("id") == sid]
            assert len(found) == 1, "created schedule item not in /radio/schedule"
            assert found[0]["showTitle"] == payload["showTitle"]

            # PATCH — update title + isLive
            patch = dict(payload)
            patch["showTitle"] = payload["showTitle"] + " (updated)"
            patch["isLive"] = False
            r3 = requests.patch(f"{BASE_URL}/api/admin/schedule/{sid}", json=patch, headers=auth_headers, timeout=20)
            assert r3.status_code == 200, f"patch failed: {r3.status_code} {r3.text}"
            doc3 = r3.json()
            assert doc3["showTitle"] == patch["showTitle"]
            assert doc3["isLive"] is False
        finally:
            rd = requests.delete(f"{BASE_URL}/api/admin/schedule/{sid}", headers=auth_headers, timeout=20)
            assert rd.status_code == 200
            # confirm gone from public feed
            r4 = requests.get(f"{BASE_URL}/api/radio/schedule", timeout=20)
            still = [i for i in r4.json() if i.get("id") == sid]
            assert len(still) == 0

    def test_admin_schedule_requires_auth(self):
        r = requests.post(f"{BASE_URL}/api/admin/schedule",
                          json={"time": "1", "showTitle": "TEST", "isLive": False}, timeout=20)
        assert r.status_code in (401, 403)

    def test_patch_schedule_404_unknown_id(self, auth_headers):
        r = requests.patch(f"{BASE_URL}/api/admin/schedule/nonexistent-id-xyz",
                           json={"time": "x", "showTitle": "y", "isLive": False}, headers=auth_headers, timeout=20)
        assert r.status_code == 404

    def test_delete_schedule_404_unknown_id(self, auth_headers):
        r = requests.delete(f"{BASE_URL}/api/admin/schedule/nonexistent-id-xyz",
                            headers=auth_headers, timeout=20)
        assert r.status_code == 404
