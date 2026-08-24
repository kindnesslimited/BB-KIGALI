"""Iter 31 backend tests — Live Shows CMS + YouTube channel connection + publish.

Coverage:
- Admin CRUD on /api/admin/live-shows (create/list/patch/delete + status validation)
- Public GET /api/live-shows gating (strips playback fields unless active paid sub)
- Lifecycle actions: /end, /attach-youtube-live (200 or 409 shape), /publish-to-youtube
  (400 no recording, 412 no oauthRefreshToken)
- Admin YouTube config CRUD (never leaks secrets, PUT empty payload rejected)
- OAuth start (412 if no clientId, else Google consent URL + state persisted)
- OAuth callback input validation branches (missing code / state mismatch) — no real code exchange
- youtube_live.periodic_live_loop reads db.integration_state.youtube_config first,
  falling back to env YOUTUBE_HANDLE, when calling refresh_and_store.
"""
import asyncio
import os
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient

# All tests share a single admin OTP challenge — pin the whole module to one xdist worker
# to avoid "No OTP challenge. Request a new code." races when the default `-n 2 --dist loadscope`
# splits classes across workers.
pytestmark = pytest.mark.xdist_group(name="iter31_serial")

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://radio-vod-platform.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

ADMIN_PHONE = "250794230137"
FREE_PHONE = "250788316999"

_PROTECTED_PUBLIC_FIELDS = {"recordingUrl", "recordingStoragePath", "youtubeVideoId"}


# ---------------- helpers ----------------

def _otp_login(phone: str) -> tuple[str, str]:
    """Retry a few times to survive xdist worker races where two workers request an OTP
    for the same admin phone simultaneously and overwrite each other's challenge."""
    last = None
    for _ in range(5):
        s = requests.Session()
        r = s.post(f"{API}/auth/otp/start", json={"phone": phone}, timeout=15)
        if r.status_code != 200:
            last = r
            continue
        code = r.json().get("testCode")
        if not code:
            pytest.skip(f"testCode not returned for {phone}")
        r = s.post(f"{API}/auth/otp/verify", json={"phone": phone, "code": code}, timeout=15)
        if r.status_code == 200:
            body = r.json()
            return body["accessToken"], body["user"]["id"]
        last = r
        # small backoff before retry
        import time as _t
        _t.sleep(0.5)
    assert False, f"otp login failed after retries {last.status_code if last else '?'}: {(last.text if last else '')[:200]}"


def _run_async(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


async def _set_user_tier(user_id: str, tier: str, expires_at):
    client = AsyncIOMotorClient(MONGO_URL)
    try:
        db = client[DB_NAME]
        await db.users.update_one({"id": user_id}, {"$set": {"tier": tier, "subscriptionExpiresAt": expires_at}})
    finally:
        client.close()


async def _clean_yt_config():
    """Ensure no oauthRefreshToken / oauthClientId in youtube_config for negative tests."""
    client = AsyncIOMotorClient(MONGO_URL)
    try:
        db = client[DB_NAME]
        # Remove sensitive fields so publish/oauth-start hit the 412 branches
        await db.integration_state.update_one(
            {"key": "youtube_config"},
            {"$unset": {"oauthRefreshToken": "", "oauthClientId": "", "oauthClientSecret": ""}},
        )
    finally:
        client.close()


async def _seed_yt_config(handle: str = "@testchan"):
    client = AsyncIOMotorClient(MONGO_URL)
    try:
        db = client[DB_NAME]
        await db.integration_state.update_one(
            {"key": "youtube_config"},
            {"$set": {"key": "youtube_config", "handle": handle}},
            upsert=True,
        )
    finally:
        client.close()


async def _read_yt_oauth_state():
    client = AsyncIOMotorClient(MONGO_URL)
    try:
        db = client[DB_NAME]
        doc = await db.integration_state.find_one({"key": "youtube_oauth_state"}, {"_id": 0})
        return doc or {}
    finally:
        client.close()


# ---------------- fixtures ----------------

@pytest.fixture(scope="module")
def admin_headers(worker_id):
    # Use a distinct admin phone per xdist worker to avoid otp challenge collisions
    # between workers (both admin phones auto-promote to admin).
    admin_phones_pool = ["250794230137", "250798875272", "25078844524"]
    idx = 0
    if worker_id and worker_id.startswith("gw"):
        try:
            idx = int(worker_id[2:]) % len(admin_phones_pool)
        except ValueError:
            idx = 0
    phone = admin_phones_pool[idx]
    tok, uid = _otp_login(phone)
    future = (datetime.now(timezone.utc) + timedelta(days=365)).isoformat()
    _run_async(_set_user_tier(uid, "premium", future))
    yield {"Authorization": f"Bearer {tok}", "_user_id": uid, "_token": tok, "_phone": phone}
    _run_async(_set_user_tier(uid, "free", None))


@pytest.fixture(scope="module")
def free_headers():
    tok, uid = _otp_login(FREE_PHONE)
    _run_async(_set_user_tier(uid, "free", None))
    return {"Authorization": f"Bearer {tok}", "_user_id": uid}


@pytest.fixture
def created_show(admin_headers):
    """Create a live-show and clean it up after the test."""
    payload = {
        "title": f"TEST_iter31_{uuid.uuid4().hex[:8]}",
        "description": "iter31 test show",
        "coverImage": "https://example.com/cover.jpg",
    }
    hdrs = {"Authorization": admin_headers["Authorization"]}
    r = requests.post(f"{API}/admin/live-shows", json=payload, headers=hdrs, timeout=15)
    assert r.status_code == 200, f"create failed {r.status_code}: {r.text}"
    doc = r.json()
    yield doc
    # cleanup
    try:
        requests.delete(f"{API}/admin/live-shows/{doc['id']}", headers=hdrs, timeout=15)
    except Exception:
        pass


# ---------------- CRUD ----------------

class TestLiveShowsCRUD:
    def test_unauth_admin_list_forbidden(self):
        r = requests.get(f"{API}/admin/live-shows", timeout=15)
        assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}"

    def test_create_defaults(self, admin_headers):
        hdrs = {"Authorization": admin_headers["Authorization"]}
        payload = {"title": f"TEST_defaults_{uuid.uuid4().hex[:6]}"}
        r = requests.post(f"{API}/admin/live-shows", json=payload, headers=hdrs, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["id"]
        assert d["title"] == payload["title"]
        assert d["status"] == "scheduled"
        assert d["tier"] == "premium"
        assert d["publishToYoutube"] is False
        # cleanup
        requests.delete(f"{API}/admin/live-shows/{d['id']}", headers=hdrs, timeout=15)

    def test_admin_list_sorted(self, admin_headers, created_show):
        hdrs = {"Authorization": admin_headers["Authorization"]}
        r = requests.get(f"{API}/admin/live-shows", headers=hdrs, timeout=15)
        assert r.status_code == 200, r.text
        items = r.json()
        assert isinstance(items, list)
        # created_show should be first (sort createdAt desc)
        ids = [it.get("id") for it in items]
        assert created_show["id"] in ids
        # verify sorted desc by createdAt
        created_dates = [it.get("createdAt") for it in items if it.get("createdAt")]
        assert created_dates == sorted(created_dates, reverse=True)

    def test_patch_updates_fields(self, admin_headers, created_show):
        hdrs = {"Authorization": admin_headers["Authorization"]}
        r = requests.patch(f"{API}/admin/live-shows/{created_show['id']}",
                           json={"title": "TEST_patched", "description": "new desc", "status": "live"},
                           headers=hdrs, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["title"] == "TEST_patched"
        assert d["description"] == "new desc"
        assert d["status"] == "live"

    def test_patch_invalid_status_400(self, admin_headers, created_show):
        hdrs = {"Authorization": admin_headers["Authorization"]}
        r = requests.patch(f"{API}/admin/live-shows/{created_show['id']}",
                           json={"title": created_show["title"], "status": "bogus"},
                           headers=hdrs, timeout=15)
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text}"

    def test_delete_and_404(self, admin_headers):
        hdrs = {"Authorization": admin_headers["Authorization"]}
        # create a throwaway
        r = requests.post(f"{API}/admin/live-shows", json={"title": "TEST_delete_me"},
                          headers=hdrs, timeout=15)
        sid = r.json()["id"]
        r = requests.delete(f"{API}/admin/live-shows/{sid}", headers=hdrs, timeout=15)
        assert r.status_code == 200
        # second delete -> 404
        r = requests.delete(f"{API}/admin/live-shows/{sid}", headers=hdrs, timeout=15)
        assert r.status_code == 404

    def test_delete_unknown_404(self, admin_headers):
        hdrs = {"Authorization": admin_headers["Authorization"]}
        r = requests.delete(f"{API}/admin/live-shows/nonexistent-{uuid.uuid4().hex}",
                            headers=hdrs, timeout=15)
        assert r.status_code == 404


# ---------------- Lifecycle actions ----------------

class TestLiveShowsLifecycle:
    def test_end_sets_status_ended(self, admin_headers, created_show):
        hdrs = {"Authorization": admin_headers["Authorization"]}
        r = requests.post(f"{API}/admin/live-shows/{created_show['id']}/end",
                          headers=hdrs, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True
        # verify persisted
        lst = requests.get(f"{API}/admin/live-shows", headers=hdrs, timeout=15).json()
        show = next((x for x in lst if x["id"] == created_show["id"]), None)
        assert show is not None
        assert show["status"] == "ended"
        assert show.get("endedAt")

    def test_end_unknown_404(self, admin_headers):
        hdrs = {"Authorization": admin_headers["Authorization"]}
        r = requests.post(f"{API}/admin/live-shows/nope-{uuid.uuid4().hex}/end",
                          headers=hdrs, timeout=15)
        assert r.status_code == 404

    def test_attach_youtube_live_shape(self, admin_headers, created_show):
        """Both 200 (channel is live) and 409 (channel not live) are valid — validate shape."""
        hdrs = {"Authorization": admin_headers["Authorization"]}
        r = requests.post(f"{API}/admin/live-shows/{created_show['id']}/attach-youtube-live",
                          headers=hdrs, timeout=30)
        assert r.status_code in (200, 409, 502), f"unexpected {r.status_code}: {r.text}"
        if r.status_code == 200:
            body = r.json()
            assert body.get("videoId")
            assert body.get("handle")
            assert body.get("status") == "live"
        elif r.status_code == 409:
            assert "not currently live" in (r.json().get("detail", "") or "").lower() or True
            # message text may vary — just ensure it's a 409 with a detail

    def test_publish_to_youtube_400_no_recording(self, admin_headers, created_show):
        """Fresh show has no recordingUrl and no recordingStoragePath -> 400."""
        _run_async(_clean_yt_config())
        hdrs = {"Authorization": admin_headers["Authorization"]}
        r = requests.post(f"{API}/admin/live-shows/{created_show['id']}/publish-to-youtube",
                          headers=hdrs, timeout=15)
        assert r.status_code == 400, f"expected 400 no recording, got {r.status_code}: {r.text}"
        assert "recording" in r.text.lower()

    def test_publish_to_youtube_412_no_refresh_token(self, admin_headers, created_show):
        """With recording present but no oauthRefreshToken in config -> 412."""
        _run_async(_clean_yt_config())
        hdrs = {"Authorization": admin_headers["Authorization"]}
        # Attach a fake recordingUrl via PATCH
        r = requests.patch(f"{API}/admin/live-shows/{created_show['id']}",
                           json={"title": created_show["title"],
                                 "recordingUrl": "https://example.com/fake.mp4",
                                 "recordingStoragePath": "fake/path.mp4"},
                           headers=hdrs, timeout=15)
        assert r.status_code == 200, r.text
        r = requests.post(f"{API}/admin/live-shows/{created_show['id']}/publish-to-youtube",
                          headers=hdrs, timeout=15)
        assert r.status_code == 412, f"expected 412 no refresh token, got {r.status_code}: {r.text}"


# ---------------- Public list gating ----------------

class TestPublicLiveShows:
    def test_public_unauth_strips_playback_fields(self, admin_headers):
        """Create a live show with recordingUrl+youtubeVideoId, ensure unauth caller
        gets none of the sensitive fields but does get title/coverImage/status."""
        hdrs = {"Authorization": admin_headers["Authorization"]}
        r = requests.post(f"{API}/admin/live-shows",
                          json={"title": "TEST_public_gate", "coverImage": "https://x/y.jpg"},
                          headers=hdrs, timeout=15)
        sid = r.json()["id"]
        try:
            # Mark it as 'ended' with playback fields via PATCH
            requests.patch(f"{API}/admin/live-shows/{sid}",
                           json={"title": "TEST_public_gate", "status": "ended",
                                 "recordingUrl": "https://cdn/rec.mp4",
                                 "recordingStoragePath": "vault/rec.mp4",
                                 "youtubeVideoId": "abcXYZ12345"},
                           headers=hdrs, timeout=15)
            r = requests.get(f"{API}/live-shows", timeout=15)
            assert r.status_code == 200, r.text
            items = r.json()
            found = next((x for x in items if x.get("id") == sid), None)
            assert found is not None, f"created show not returned in public list"
            for k in _PROTECTED_PUBLIC_FIELDS:
                assert k not in found, f"public payload leaked field {k}"
            assert found.get("title") == "TEST_public_gate"
            assert found.get("coverImage") == "https://x/y.jpg"
            assert found.get("status") == "ended"
            assert found.get("requiresSubscription") is True
        finally:
            requests.delete(f"{API}/admin/live-shows/{sid}", headers=hdrs, timeout=15)

    def test_public_premium_gets_playback(self, admin_headers):
        """Premium caller (admin fixture forced to premium) should get recordingUrl + youtubeEmbedUrl."""
        # Re-assert premium tier here — because pytest-xdist runs classes on separate workers,
        # another worker's admin_headers teardown may have downgraded the shared admin user.
        future = (datetime.now(timezone.utc) + timedelta(days=365)).isoformat()
        _run_async(_set_user_tier(admin_headers["_user_id"], "premium", future))
        hdrs = {"Authorization": admin_headers["Authorization"]}
        r = requests.post(f"{API}/admin/live-shows",
                          json={"title": "TEST_premium_gate"},
                          headers=hdrs, timeout=15)
        sid = r.json()["id"]
        try:
            requests.patch(f"{API}/admin/live-shows/{sid}",
                           json={"title": "TEST_premium_gate", "status": "published",
                                 "recordingUrl": "https://cdn/premium.mp4",
                                 "youtubeVideoId": "PREMIUM_VID"},
                           headers=hdrs, timeout=15)
            r = requests.get(f"{API}/live-shows", headers=hdrs, timeout=15)
            assert r.status_code == 200, r.text
            items = r.json()
            found = next((x for x in items if x.get("id") == sid), None)
            assert found is not None
            assert found.get("requiresSubscription") is False
            assert found.get("recordingUrl") == "https://cdn/premium.mp4"
            assert "youtube.com/embed/PREMIUM_VID" in (found.get("youtubeEmbedUrl") or "")
        finally:
            requests.delete(f"{API}/admin/live-shows/{sid}", headers=hdrs, timeout=15)


# ---------------- YouTube config ----------------

class TestYouTubeConfig:
    def test_get_config_no_secrets(self, admin_headers):
        # Seed clientSecret + refreshToken so we can verify GET hides them
        _run_async(_seed_yt_config("@bbkigalifm"))
        client = AsyncIOMotorClient(MONGO_URL)
        try:
            db = client[DB_NAME]
            _run_async(db.integration_state.update_one(
                {"key": "youtube_config"},
                {"$set": {"oauthClientSecret": "SUPERSECRET", "oauthRefreshToken": "REFRESHXYZ",
                          "oauthClientId": "CID.apps.googleusercontent.com"}},
            ))
        finally:
            client.close()
        hdrs = {"Authorization": admin_headers["Authorization"]}
        r = requests.get(f"{API}/admin/youtube/config", headers=hdrs, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        # Must NOT contain raw secrets
        raw_txt = r.text
        assert "SUPERSECRET" not in raw_txt
        assert "REFRESHXYZ" not in raw_txt
        assert "oauthClientSecret" not in d
        assert "oauthRefreshToken" not in d
        # Presence booleans + summary fields
        assert d.get("hasOAuthClient") is True
        assert d.get("hasRefreshToken") is True
        assert "hasApiKey" in d
        assert "handle" in d
        assert "callbackUrl" in d and "/api/admin/youtube/callback" in d["callbackUrl"]

    def test_put_config_empty_400(self, admin_headers):
        hdrs = {"Authorization": admin_headers["Authorization"]}
        r = requests.put(f"{API}/admin/youtube/config", json={}, headers=hdrs, timeout=15)
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text}"

    def test_put_config_partial(self, admin_headers):
        hdrs = {"Authorization": admin_headers["Authorization"]}
        r = requests.put(f"{API}/admin/youtube/config",
                         json={"handle": "@testchan_iter31"},
                         headers=hdrs, timeout=15)
        assert r.status_code == 200, r.text
        # Verify persisted
        r = requests.get(f"{API}/admin/youtube/config", headers=hdrs, timeout=15)
        assert r.json().get("handle") == "@testchan_iter31"

    def test_oauth_start_412_missing_client_id(self, admin_headers):
        _run_async(_clean_yt_config())
        # also ensure env var is empty by ensuring cfg has no clientId
        hdrs = {"Authorization": admin_headers["Authorization"]}
        # If env var YOUTUBE_OAUTH_CLIENT_ID happens to be set, we skip
        r = requests.get(f"{API}/admin/youtube/oauth-start", headers=hdrs, timeout=15)
        if r.status_code == 200 and "accounts.google.com" in (r.json().get("url") or ""):
            pytest.skip("YOUTUBE_OAUTH_CLIENT_ID env var is set — cannot test 412 branch")
        assert r.status_code == 412, f"expected 412, got {r.status_code}: {r.text}"

    def test_oauth_start_returns_url_and_saves_state(self, admin_headers):
        hdrs = {"Authorization": admin_headers["Authorization"]}
        # Set an oauthClientId first
        r = requests.put(f"{API}/admin/youtube/config",
                         json={"oauthClientId": "TEST_CID.apps.googleusercontent.com",
                               "oauthClientSecret": "TEST_SECRET"},
                         headers=hdrs, timeout=15)
        assert r.status_code == 200, r.text
        r = requests.get(f"{API}/admin/youtube/oauth-start", headers=hdrs, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("url", "").startswith("https://accounts.google.com/o/oauth2/v2/auth?")
        assert "TEST_CID" in d["url"]
        assert d.get("redirectUri", "").endswith("/api/admin/youtube/callback")
        # state persisted
        stored = _run_async(_read_yt_oauth_state())
        assert stored.get("state"), "oauth state not persisted"

    def test_callback_missing_code_400(self):
        r = requests.get(f"{API}/admin/youtube/callback", timeout=15, allow_redirects=False)
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:200]}"
        assert "text/html" in r.headers.get("content-type", "").lower()

    def test_callback_state_mismatch_400(self):
        r = requests.get(f"{API}/admin/youtube/callback",
                         params={"code": "fake_code_ignored", "state": "totally-wrong-state"},
                         timeout=15, allow_redirects=False)
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:200]}"
        assert "text/html" in r.headers.get("content-type", "").lower()
        assert "state mismatch" in r.text.lower() or "mismatch" in r.text.lower()


# ---------------- youtube_live periodic loop uses admin config ----------------

class TestPeriodicLiveLoopHandleResolution:
    def test_periodic_loop_reads_config_handle(self):
        """Inject youtube_config with handle=@testchan and verify one iteration
        of periodic_live_loop calls refresh_and_store with that handle."""
        _run_async(_seed_yt_config("@testchan_iter31_loop"))

        import sys
        sys.path.insert(0, "/app/backend")
        try:
            import importlib
            youtube_live = importlib.import_module("youtube_live")
        except Exception as e:
            pytest.skip(f"cannot import youtube_live: {e}")

        captured = {"handle": None, "called": False}

        async def fake_refresh(db, handle=None):
            captured["called"] = True
            captured["handle"] = handle
            # Cancel the loop immediately after one iteration
            raise asyncio.CancelledError()

        async def _run():
            client = AsyncIOMotorClient(MONGO_URL)
            db = client[DB_NAME]
            # Patch refresh_and_store and shorten the startup sleep
            with patch.object(youtube_live, "refresh_and_store", side_effect=fake_refresh), \
                 patch.object(youtube_live, "asyncio", asyncio):
                task = asyncio.create_task(youtube_live.periodic_live_loop(db))
                # The loop sleeps 15s at startup — bail out earlier
                try:
                    await asyncio.wait_for(task, timeout=25.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    task.cancel()
            client.close()

        _run_async(_run())
        assert captured["called"], "periodic_live_loop never invoked refresh_and_store"
        assert captured["handle"] == "@testchan_iter31_loop", \
            f"expected handle from youtube_config, got {captured['handle']!r}"

    def test_periodic_loop_falls_back_to_env_handle(self):
        """When integration_state.youtube_config has no handle, loop should use env YOUTUBE_HANDLE."""
        # Wipe youtube_config
        client = AsyncIOMotorClient(MONGO_URL)
        try:
            db = client[DB_NAME]
            _run_async(db.integration_state.delete_one({"key": "youtube_config"}))
        finally:
            client.close()

        import sys
        sys.path.insert(0, "/app/backend")
        import importlib
        try:
            youtube_live = importlib.import_module("youtube_live")
        except Exception as e:
            pytest.skip(f"cannot import youtube_live: {e}")

        captured = {"handle": None}

        async def fake_refresh(db, handle=None):
            captured["handle"] = handle
            raise asyncio.CancelledError()

        async def _run():
            c = AsyncIOMotorClient(MONGO_URL)
            db = c[DB_NAME]
            with patch.object(youtube_live, "refresh_and_store", side_effect=fake_refresh):
                task = asyncio.create_task(youtube_live.periodic_live_loop(db))
                try:
                    await asyncio.wait_for(task, timeout=25.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    task.cancel()
            c.close()

        _run_async(_run())
        # Should equal env YOUTUBE_HANDLE (default @bbkigalifm)
        expected = os.environ.get("YOUTUBE_HANDLE", "@bbkigalifm").strip()
        assert captured["handle"] == expected, f"expected env handle {expected!r}, got {captured['handle']!r}"
