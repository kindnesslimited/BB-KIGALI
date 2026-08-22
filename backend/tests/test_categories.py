"""Tests for Category Management admin CRUD + public listing.

Feature: admin can add unlimited show categories beyond fixed defaults (VOD, Podcast, Interview).
Categories drive filter chips on public Shows tab and dropdown in Admin > VOD screen.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_BACKEND_URL", "https://radio-vod-platform.preview.emergentagent.com").rstrip("/")
ADMIN_PHONE = "+250798875272"


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def admin_token(api):
    r = api.post(f"{BASE_URL}/api/auth/otp/start", json={"phone": ADMIN_PHONE})
    assert r.status_code == 200, r.text
    code = r.json().get("testCode")
    assert code, f"testCode missing in dev-mode OTP start response: {r.json()}"
    r = api.post(f"{BASE_URL}/api/auth/otp/verify", json={"phone": ADMIN_PHONE, "code": code})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["user"]["role"] == "admin", f"expected admin role for {ADMIN_PHONE}, got: {j['user']}"
    return j["accessToken"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


# -------- Public listing --------
def test_public_categories_returns_defaults(api):
    r = api.get(f"{BASE_URL}/api/categories")
    assert r.status_code == 200
    items = r.json()
    slugs = {c["slug"] for c in items}
    assert {"vod", "podcast", "interview"}.issubset(slugs), f"expected defaults in {slugs}"
    # sorted by order ascending
    orders = [c["order"] for c in items]
    assert orders == sorted(orders), f"categories not sorted by order: {orders}"
    # shape
    for c in items:
        assert "id" in c and "name" in c and "slug" in c
        assert "_id" not in c


def test_public_categories_no_auth_required(api):
    # No Authorization header
    r = requests.get(f"{BASE_URL}/api/categories")
    assert r.status_code == 200


# -------- Admin listing --------
def test_admin_categories_requires_auth(api):
    r = api.get(f"{BASE_URL}/api/admin/categories")
    assert r.status_code in (401, 403)


def test_admin_list_categories(api, admin_headers):
    r = api.get(f"{BASE_URL}/api/admin/categories", headers=admin_headers)
    assert r.status_code == 200, r.text
    items = r.json()
    default_slugs = {c["slug"] for c in items if c.get("isDefault")}
    assert {"vod", "podcast", "interview"}.issubset(default_slugs)


# -------- Create + duplicate --------
def test_create_music_category_and_verify_slug(api, admin_headers):
    # Cleanup: if a prior test run left "Music" or "Live Music", delete it if unreferenced
    listing = api.get(f"{BASE_URL}/api/admin/categories", headers=admin_headers).json()
    for c in listing:
        if c.get("slug") in ("music", "live-music") and not c.get("isDefault"):
            api.delete(f"{BASE_URL}/api/admin/categories/{c['id']}", headers=admin_headers)

    r = api.post(f"{BASE_URL}/api/admin/categories",
                 json={"name": "Music", "order": 20},
                 headers=admin_headers)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["slug"] == "music"
    assert j["name"] == "Music"
    assert j["order"] == 20
    assert j["isActive"] is True
    assert j["isDefault"] is False
    # persist id for downstream tests
    pytest.music_id = j["id"]

    # Verify via GET
    listing = api.get(f"{BASE_URL}/api/admin/categories", headers=admin_headers).json()
    assert any(c["id"] == j["id"] and c["slug"] == "music" for c in listing)


def test_duplicate_category_returns_409(api, admin_headers):
    r = api.post(f"{BASE_URL}/api/admin/categories",
                 json={"name": "music"},   # different case, same slug
                 headers=admin_headers)
    assert r.status_code == 409, r.text


# -------- Update / rename with slug cascade --------
def test_rename_music_to_live_music_slug_becomes_live_music(api, admin_headers):
    cat_id = getattr(pytest, "music_id", None)
    assert cat_id, "music_id fixture missing — create test must run first"
    r = api.put(f"{BASE_URL}/api/admin/categories/{cat_id}",
                json={"name": "Live Music", "order": 20, "isActive": True},
                headers=admin_headers)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["slug"] == "live-music"
    assert j["name"] == "Live Music"

    # Verify persistence
    listing = api.get(f"{BASE_URL}/api/admin/categories", headers=admin_headers).json()
    updated = next((c for c in listing if c["id"] == cat_id), None)
    assert updated is not None
    assert updated["slug"] == "live-music"


# -------- Delete (unreferenced OK) --------
def test_create_and_delete_unreferenced_category(api, admin_headers):
    # create
    r = api.post(f"{BASE_URL}/api/admin/categories",
                 json={"name": "Delete Me TEST", "order": 999},
                 headers=admin_headers)
    assert r.status_code == 200, r.text
    cid = r.json()["id"]

    # delete
    r = api.delete(f"{BASE_URL}/api/admin/categories/{cid}", headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True}

    # verify gone
    listing = api.get(f"{BASE_URL}/api/admin/categories", headers=admin_headers).json()
    assert not any(c["id"] == cid for c in listing)


# -------- Delete referenced default returns 409 --------
def test_delete_vod_category_conflict_because_shows_reference_it(api, admin_headers):
    listing = api.get(f"{BASE_URL}/api/admin/categories", headers=admin_headers).json()
    vod = next(c for c in listing if c["slug"] == "vod")
    r = api.delete(f"{BASE_URL}/api/admin/categories/{vod['id']}", headers=admin_headers)
    assert r.status_code == 409, f"expected 409 (shows still reference vod), got {r.status_code}: {r.text}"


# -------- Cleanup: delete the renamed "Live Music" category --------
def test_final_cleanup_delete_live_music(api, admin_headers):
    cat_id = getattr(pytest, "music_id", None)
    if cat_id:
        r = api.delete(f"{BASE_URL}/api/admin/categories/{cat_id}", headers=admin_headers)
        assert r.status_code in (200, 404)


# -------- Final state sanity --------
def test_final_admin_listing_still_has_defaults(api, admin_headers):
    listing = api.get(f"{BASE_URL}/api/admin/categories", headers=admin_headers).json()
    slugs = {c["slug"] for c in listing}
    assert {"vod", "podcast", "interview"}.issubset(slugs)
