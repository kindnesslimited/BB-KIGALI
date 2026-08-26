"""Iter 34 — BB FM Kigali radio stream wiring backend tests.

Verifies:
  1. GET /api/radio/now-playing returns streamUrl == BB Kigali default URL.
  2. streamUrlHttps is null unless RADIO_STREAM_URL_HTTPS env is set.
  3. showTitle == "BB FM Kigali Live" (from seed or db doc).
  4. Response contains required fields (streamUrl, streamUrlHttps, showTitle, isLive, etc.).
  5. Code path reads RADIO_STREAM_URL / RADIO_STREAM_URL_HTTPS from env (module inspection).
  6. Persistence: on re-fetch (post-migrate), streamUrl still equals the BB Kigali URL.
"""
import os
import pytest
import requests

BASE_URL = os.environ["EXPO_BACKEND_URL"].rstrip("/") if os.environ.get("EXPO_BACKEND_URL") else "https://radio-vod-platform.preview.emergentagent.com"
BB_KIGALI_STREAM = "http://radio.bbkigali.com:8080/stream"


@pytest.fixture
def api_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


class TestRadioNowPlaying:
    """Radio now-playing endpoint contract"""

    def test_now_playing_200(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/radio/now-playing", timeout=15)
        assert r.status_code == 200, r.text

    def test_now_playing_stream_url_is_bb_kigali(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/radio/now-playing", timeout=15)
        data = r.json()
        assert data.get("streamUrl") == BB_KIGALI_STREAM, (
            f"Expected streamUrl={BB_KIGALI_STREAM}, got {data.get('streamUrl')}"
        )

    def test_now_playing_stream_url_https_field_present(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/radio/now-playing", timeout=15)
        data = r.json()
        # Field should exist. Value is None (null) unless RADIO_STREAM_URL_HTTPS env is set.
        assert "streamUrlHttps" in data, "streamUrlHttps field must be present in response"
        # Given .env doesn't set RADIO_STREAM_URL_HTTPS, this should be None or a non-empty string
        val = data["streamUrlHttps"]
        assert val is None or (isinstance(val, str) and val.startswith("https://")), (
            f"streamUrlHttps must be null or an https URL, got {val!r}"
        )

    def test_now_playing_show_title(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/radio/now-playing", timeout=15)
        data = r.json()
        assert data.get("showTitle") == "BB FM Kigali Live", (
            f"Expected showTitle='BB FM Kigali Live', got {data.get('showTitle')!r}"
        )

    def test_now_playing_required_fields(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/radio/now-playing", timeout=15)
        data = r.json()
        for field in ("streamUrl", "streamUrlHttps", "showTitle", "isLive", "coverImage",
                       "djName", "description", "youtubeVideoId", "youtubeEmbedUrl", "youtubeWatchUrl"):
            assert field in data, f"missing field {field!r} in now-playing payload"

    def test_now_playing_is_live_true(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/radio/now-playing", timeout=15)
        assert r.json().get("isLive") is True

    def test_now_playing_no_mongo_id(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/radio/now-playing", timeout=15)
        assert "_id" not in r.json(), "MongoDB _id must never leak to responses"
        assert "key" not in r.json(), "internal 'key' selector must never leak"

    def test_now_playing_stable_across_calls(self, api_client):
        """Ensure the seed migration is idempotent — repeat calls return same URL."""
        r1 = api_client.get(f"{BASE_URL}/api/radio/now-playing", timeout=15).json()
        r2 = api_client.get(f"{BASE_URL}/api/radio/now-playing", timeout=15).json()
        assert r1.get("streamUrl") == r2.get("streamUrl")
        assert r1.get("streamUrl") == BB_KIGALI_STREAM


class TestServerCodePaths:
    """Static inspection of /app/backend/server.py — confirms env-var override paths exist."""

    def test_server_reads_env_radio_stream_url(self):
        with open("/app/backend/server.py", "r") as f:
            src = f.read()
        assert 'os.environ.get("RADIO_STREAM_URL"' in src, (
            "server.py must read RADIO_STREAM_URL from env for override support"
        )
        assert 'os.environ.get("RADIO_STREAM_URL_HTTPS"' in src, (
            "server.py must read RADIO_STREAM_URL_HTTPS from env for HTTPS override"
        )
        assert 'BB_KIGALI_STREAM = "http://radio.bbkigali.com:8080/stream"' in src, (
            "server.py must define BB_KIGALI_STREAM constant"
        )
