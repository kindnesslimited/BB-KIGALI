"""Iter 28: YouTube live status + Featured schedule slot + description field."""
import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_BACKEND_URL", "https://radio-vod-platform.preview.emergentagent.com").rstrip("/")
ADMIN_PHONE = "250794230137"


@pytest.fixture(scope="module")
def api_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def admin_token(api_client):
    r = api_client.post(f"{BASE_URL}/api/auth/otp/start", json={"phone": ADMIN_PHONE})
    assert r.status_code == 200, r.text
    code = r.json().get("testCode") or "123456"
    r2 = api_client.post(f"{BASE_URL}/api/auth/otp/verify", json={"phone": ADMIN_PHONE, "code": code})
    assert r2.status_code == 200, r2.text
    data = r2.json()
    assert data["user"]["role"] == "admin"
    return data["accessToken"]


# ---------- /api/live/status ----------
class TestLiveStatus:
    def test_live_status_shape(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/live/status")
        assert r.status_code == 200, r.text
        data = r.json()
        assert "isLive" in data and isinstance(data["isLive"], bool)
        assert "checkedAt" in data
        if data.get("isLive"):
            assert data.get("videoId")
            assert data.get("watchUrl", "").startswith("https://www.youtube.com/watch?v=")
            assert data.get("embedUrl", "").startswith("https://www.youtube.com/embed/")

    def test_live_status_refresh_forces_fresh(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/live/status", params={"refresh": "true"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert "isLive" in data
        assert "checkedAt" in data


# ---------- Featured schedule + description ----------
class TestFeaturedSchedule:
    created_ids: list = []

    def _auth(self, token):
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def test_create_featured_slot(self, api_client, admin_token):
        payload = {
            "time": "07:00 - 09:00",
            "showTitle": "TEST_Iter28 Morning Featured",
            "djName": "TEST DJ",
            "days": ["mon"],
            "order": 0,
            "featured": True,
            "description": "TEST_featured description iter28",
        }
        r = api_client.post(f"{BASE_URL}/api/admin/schedule", json=payload, headers=self._auth(admin_token))
        assert r.status_code == 200, r.text
        doc = r.json()
        assert doc["featured"] is True
        assert doc["description"] == "TEST_featured description iter28"
        assert doc["id"]
        TestFeaturedSchedule.created_ids.append(doc["id"])

    def test_create_second_featured_unfeatures_first(self, api_client, admin_token):
        payload = {
            "time": "09:00 - 10:00",
            "showTitle": "TEST_Iter28 Second Featured",
            "featured": True,
            "description": "second",
        }
        r = api_client.post(f"{BASE_URL}/api/admin/schedule", json=payload, headers=self._auth(admin_token))
        assert r.status_code == 200, r.text
        second = r.json()
        assert second["featured"] is True
        TestFeaturedSchedule.created_ids.append(second["id"])

        # First one should now be un-featured
        r2 = api_client.get(f"{BASE_URL}/api/radio/schedule")
        assert r2.status_code == 200
        items = r2.json()
        featured_ids = [i["id"] for i in items if i.get("featured")]
        assert len(featured_ids) == 1, f"Expected exactly 1 featured slot, got {featured_ids}"
        assert featured_ids[0] == second["id"]

    def test_patch_featured_unfeatures_others(self, api_client, admin_token):
        # Toggle back the first slot as featured via PATCH
        first_id = TestFeaturedSchedule.created_ids[0]
        payload = {
            "time": "07:00 - 09:00",
            "showTitle": "TEST_Iter28 Morning Featured",
            "featured": True,
        }
        r = api_client.patch(f"{BASE_URL}/api/admin/schedule/{first_id}", json=payload, headers=self._auth(admin_token))
        assert r.status_code == 200, r.text
        assert r.json()["featured"] is True

        r2 = api_client.get(f"{BASE_URL}/api/radio/schedule")
        items = r2.json()
        featured = [i for i in items if i.get("featured")]
        assert len(featured) == 1
        assert featured[0]["id"] == first_id

    def test_description_returned_in_public_schedule(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/radio/schedule")
        assert r.status_code == 200
        items = r.json()
        matches = [i for i in items if i["id"] in TestFeaturedSchedule.created_ids]
        assert matches
        # At least one has our description
        first = next((i for i in matches if i["id"] == TestFeaturedSchedule.created_ids[0]), None)
        assert first is not None
        assert first.get("description") == "TEST_featured description iter28"

    def test_cleanup(self, api_client, admin_token):
        for sid in TestFeaturedSchedule.created_ids:
            api_client.delete(f"{BASE_URL}/api/admin/schedule/{sid}", headers=self._auth(admin_token))
