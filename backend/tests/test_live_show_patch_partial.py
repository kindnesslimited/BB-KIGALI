"""Regression test for PATCH /api/admin/live-shows/{id} partial-edit fix.

Previously the PATCH handler required `title` (422 on partial edit).
Now uses LiveShowUpdate where every field is Optional.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "").rstrip("/") or \
           "https://radio-vod-platform.preview.emergentagent.com"
ADMIN_PHONE = "+250794230137"


@pytest.fixture(scope="module")
def admin_token():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/otp/start", json={"phone": ADMIN_PHONE}, timeout=20)
    assert r.status_code == 200, f"otp start failed: {r.status_code} {r.text}"
    body = r.json()
    code = body.get("testCode") or "123456"
    r2 = s.post(f"{BASE_URL}/api/auth/otp/verify",
                json={"phone": ADMIN_PHONE, "code": code}, timeout=20)
    assert r2.status_code == 200, f"otp verify failed: {r2.status_code} {r2.text}"
    body2 = r2.json()
    tok = body2.get("accessToken") or body2.get("token") or body2.get("session_token") or body2.get("access_token")
    assert tok, f"no token in verify response: {r2.json()}"
    return tok


@pytest.fixture(scope="module")
def headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def show_id(headers):
    body = {
        "title": "TEST — original title",
        "scheduledAt": "2026-12-31T20:00:00Z",
        "expectedDurationMin": 60,
    }
    r = requests.post(f"{BASE_URL}/api/admin/live-shows", json=body, headers=headers, timeout=20)
    assert r.status_code in (200, 201), f"create failed: {r.status_code} {r.text}"
    sid = r.json().get("id")
    assert sid
    yield sid
    # cleanup
    requests.delete(f"{BASE_URL}/api/admin/live-shows/{sid}", headers=headers, timeout=15)


def test_patch_description_only_preserves_title(show_id, headers):
    r = requests.patch(f"{BASE_URL}/api/admin/live-shows/{show_id}",
                       json={"description": "updated description only"},
                       headers=headers, timeout=15)
    assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text}"
    doc = r.json()
    assert doc["title"] == "TEST — original title", f"title changed: {doc.get('title')!r}"
    assert doc["description"] == "updated description only"


def test_patch_title_only_preserves_description(show_id, headers):
    r = requests.patch(f"{BASE_URL}/api/admin/live-shows/{show_id}",
                       json={"title": "TEST — new title"},
                       headers=headers, timeout=15)
    assert r.status_code == 200
    doc = r.json()
    assert doc["title"] == "TEST — new title"
    assert doc["description"] == "updated description only"


def test_patch_invalid_status_returns_400(show_id, headers):
    r = requests.patch(f"{BASE_URL}/api/admin/live-shows/{show_id}",
                       json={"status": "invalid_status"},
                       headers=headers, timeout=15)
    assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text}"
    assert "status" in r.text.lower()


def test_patch_valid_status_live(show_id, headers):
    r = requests.patch(f"{BASE_URL}/api/admin/live-shows/{show_id}",
                       json={"status": "live"},
                       headers=headers, timeout=15)
    assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text}"
    assert r.json()["status"] == "live"


def test_patch_empty_body_returns_400(show_id, headers):
    r = requests.patch(f"{BASE_URL}/api/admin/live-shows/{show_id}",
                       json={}, headers=headers, timeout=15)
    assert r.status_code == 400
    assert "no fields" in r.text.lower()


def test_patch_nonexistent_returns_404(headers):
    r = requests.patch(f"{BASE_URL}/api/admin/live-shows/nonexistent-id-xyz",
                       json={"title": "x"}, headers=headers, timeout=15)
    assert r.status_code == 404


def test_list_still_works(headers):
    r = requests.get(f"{BASE_URL}/api/admin/live-shows", headers=headers, timeout=15)
    assert r.status_code == 200
    assert isinstance(r.json(), list)
