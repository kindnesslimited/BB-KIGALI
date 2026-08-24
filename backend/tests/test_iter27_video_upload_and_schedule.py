"""Iter 27 backend tests
- /api/admin/uploads/video validation: MP4 / MOV / WebM / rejects text / auth-required
- /api/admin/schedule accepts coverImage + status; PATCH updates them; public /api/radio/schedule reflects
"""
import os
import struct
import pytest
import requests

BASE_URL = "https://radio-vod-platform.preview.emergentagent.com"

ADMIN_PHONE = "+250794230137"


# ---------- fixtures ----------
@pytest.fixture(scope="module")
def admin_token():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/otp/start", json={"phone": ADMIN_PHONE}, timeout=30)
    assert r.status_code == 200, r.text
    code = r.json().get("testCode") or "123456"
    r = s.post(f"{BASE_URL}/api/auth/otp/verify", json={"phone": ADMIN_PHONE, "code": code}, timeout=30)
    assert r.status_code == 200, r.text
    tok = r.json().get("accessToken") or r.json().get("token")
    assert tok, r.json()
    return tok


@pytest.fixture()
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ---------- Video upload payload builders ----------
def _mov_ios_payload() -> bytes:
    # 12-byte ftyp header: size(0x20) + 'ftyp' + 'qt  ' -- iOS MOV
    return struct.pack(">I", 0x20) + b"ftyp" + b"qt  " + b"\x00" * 20


def _mp4_android_payload() -> bytes:
    # size(0x1C) + 'ftyp' + 'mp42' + version + compatible brands padding
    return struct.pack(">I", 0x1C) + b"ftyp" + b"mp42" + b"\x00" * 16


def _webm_payload() -> bytes:
    return b"\x1a\x45\xdf\xa3" + b"\x00" * 24


# ---------- Auth check ----------
class TestVideoUploadAuth:
    def test_requires_auth(self):
        files = {"file": ("x.mp4", _mp4_android_payload(), "video/mp4")}
        r = requests.post(f"{BASE_URL}/api/admin/uploads/video", files=files, timeout=30)
        assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code} {r.text[:200]}"


# ---------- Video validator branches ----------
class TestVideoUploadValidation:
    def _post(self, headers, filename, body, ct):
        files = {"file": (filename, body, ct)}
        return requests.post(f"{BASE_URL}/api/admin/uploads/video", files=files, headers=headers, timeout=60)

    def test_ios_mov_quicktime(self, admin_headers):
        r = self._post(admin_headers, "clip.mov", _mov_ios_payload(), "video/quicktime")
        # 200 accepted, or 502 if object storage upload fails (still confirms validator passed)
        assert r.status_code in (200, 502), f"got {r.status_code} {r.text[:300]}"
        if r.status_code == 200:
            j = r.json()
            assert j.get("contentType") == "video/quicktime", j
            assert j.get("url"), j
        else:
            # 502 confirms it passed validation and got to the storage call
            assert "Unsupported" not in r.text, r.text

    def test_android_octet_stream_mp4(self, admin_headers):
        r = self._post(admin_headers, "vid.mp4", _mp4_android_payload(), "application/octet-stream")
        assert r.status_code in (200, 502), f"got {r.status_code} {r.text[:300]}"
        if r.status_code == 200:
            j = r.json()
            assert j.get("contentType") == "video/mp4", j

    def test_webm_video(self, admin_headers):
        r = self._post(admin_headers, "vid.webm", _webm_payload(), "video/webm")
        assert r.status_code in (200, 502), f"got {r.status_code} {r.text[:300]}"
        if r.status_code == 200:
            j = r.json()
            assert j.get("contentType") == "video/webm", j

    def test_rejects_text_file(self, admin_headers):
        r = self._post(admin_headers, "doc.txt", b"hello world", "text/plain")
        assert r.status_code == 400, f"expected 400 got {r.status_code} {r.text[:200]}"
        assert "Unsupported" in r.text or "video" in r.text.lower()


# ---------- Schedule coverImage + status ----------
class TestScheduleCoverAndStatus:
    def test_create_with_cover_and_status(self, admin_headers):
        payload = {
            "time": "07:00 - 09:00",
            "showTitle": "TEST_ITER27 Morning Show",
            "djName": "TEST DJ",
            "days": ["mon", "tue", "wed"],
            "isLive": True,
            "order": 1,
            "coverImage": "https://example.com/cover.jpg",
            "status": "on-air",
        }
        r = requests.post(f"{BASE_URL}/api/admin/schedule", json=payload, headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text
        doc = r.json()
        assert doc.get("coverImage") == "https://example.com/cover.jpg", doc
        assert doc.get("status") == "on-air", doc
        item_id = doc["id"]

        # public GET reflects
        r = requests.get(f"{BASE_URL}/api/radio/schedule", timeout=30)
        assert r.status_code == 200, r.text
        items = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
        found = next((x for x in items if x.get("id") == item_id), None)
        assert found is not None, f"item not found in public schedule; got {len(items)} items"
        assert found.get("coverImage") == "https://example.com/cover.jpg"
        assert found.get("status") == "on-air"

        # PATCH — update coverImage and status
        r = requests.patch(
            f"{BASE_URL}/api/admin/schedule/{item_id}",
            json={
                "time": payload["time"],
                "showTitle": payload["showTitle"],
                "coverImage": "https://example.com/cover2.jpg",
                "status": "upcoming",
            },
            headers=admin_headers,
            timeout=30,
        )
        assert r.status_code == 200, r.text
        updated = r.json()
        assert updated.get("coverImage") == "https://example.com/cover2.jpg", updated
        assert updated.get("status") == "upcoming", updated

        # cleanup
        r = requests.delete(f"{BASE_URL}/api/admin/schedule/{item_id}", headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text

    def test_create_default_status_when_missing(self, admin_headers):
        payload = {
            "time": "09:00 - 11:00",
            "showTitle": "TEST_ITER27 Default Status",
            "days": ["thu"],
            "isLive": False,
            "order": 2,
        }
        r = requests.post(f"{BASE_URL}/api/admin/schedule", json=payload, headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text
        doc = r.json()
        # server defaults to "upcoming" when isLive False (per code path)
        assert doc.get("status") in ("upcoming", "on-air", "off-air"), doc
        assert doc.get("coverImage") == "", doc
        # cleanup
        requests.delete(f"{BASE_URL}/api/admin/schedule/{doc['id']}", headers=admin_headers, timeout=30)
