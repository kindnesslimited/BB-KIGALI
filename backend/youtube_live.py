"""YouTube LIVE detection for BB Kigali FM.

Channel-id resolution priority (fix for 'channel not found: @handle' errors):
  1. `integration_state.youtube_config.channelId`  ← populated by OAuth callback
  2. OAuth: refresh the stored refresh_token → call `channels?mine=true`
  3. API-key + `forHandle=<@handle>`  (public fallback, may fail for new handles)

Detection uses `search.list eventType=live` (100 quota units). Cached in
`integration_state` under `youtube_live:<channelId>` to stay within quota.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

YT_API = "https://www.googleapis.com/youtube/v3"
GOOGLE_OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "").strip()
YOUTUBE_HANDLE = os.environ.get("YOUTUBE_HANDLE", "@bbkigalifm").strip()
GOOGLE_OAUTH_CLIENT_ID = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "").strip()
GOOGLE_OAUTH_CLIENT_SECRET = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()
YOUTUBE_LIVE_POLL_SECONDS = int(os.environ.get("YOUTUBE_LIVE_POLL_SECONDS", "600"))


async def _refresh_oauth_access_token(refresh_token: str) -> Optional[str]:
    """Exchange a stored refresh_token for a short-lived access_token."""
    if not (refresh_token and GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET):
        return None
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.post(GOOGLE_OAUTH_TOKEN_URL, data={
                "client_id": GOOGLE_OAUTH_CLIENT_ID,
                "client_secret": GOOGLE_OAUTH_CLIENT_SECRET,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            })
        if r.status_code == 200:
            return (r.json() or {}).get("access_token")
        logger.warning("[youtube-live] refresh_token exchange %s: %s", r.status_code, r.text[:200])
    except Exception:
        logger.exception("[youtube-live] refresh_token exchange failed")
    return None


async def _channel_id_from_oauth(client: httpx.AsyncClient, refresh_token: str) -> tuple[Optional[str], Optional[str]]:
    """Return (channel_id, channel_title) using the admin's OAuth token."""
    access = await _refresh_oauth_access_token(refresh_token)
    if not access:
        return None, None
    try:
        r = await client.get(
            f"{YT_API}/channels",
            params={"part": "id,snippet", "mine": "true"},
            headers={"Authorization": f"Bearer {access}"},
        )
        if r.is_error:
            return None, None
        items = (r.json() or {}).get("items") or []
        if not items:
            return None, None
        return items[0].get("id"), ((items[0].get("snippet") or {}).get("title"))
    except Exception:
        logger.exception("[youtube-live] channels?mine=true failed")
        return None, None


async def _channel_id_from_handle(client: httpx.AsyncClient, handle: str) -> Optional[str]:
    """Public fallback via forHandle — only works when API key is set AND the
    handle resolves (fails for newly-created handles that Google hasn't indexed)."""
    if not YOUTUBE_API_KEY:
        return None
    handle = handle if handle.startswith("@") else f"@{handle}"
    try:
        r = await client.get(f"{YT_API}/channels", params={
            "part": "id", "forHandle": handle, "key": YOUTUBE_API_KEY,
        })
        if r.is_error:
            return None
        items = (r.json() or {}).get("items") or []
        return items[0]["id"] if items else None
    except Exception:
        return None


async def _pick_thumbnail(thumbs: dict) -> Optional[str]:
    for k in ("maxres", "standard", "high", "medium", "default"):
        v = (thumbs or {}).get(k)
        if v and v.get("url"):
            return v["url"]
    return None


async def check_live_now(handle: Optional[str] = None, db=None) -> dict:
    """Ask YouTube if we are broadcasting right now.

    Channel-id resolution order:
      1. `integration_state.youtube_config.channelId`
      2. OAuth `channels?mine=true` using stored refresh_token
      3. Public `channels?forHandle=<@handle>` (may 404 for new handles)
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    out: dict = {
        "isLive": False, "videoId": None, "title": None, "thumbnail": None,
        "startedAt": None, "channelTitle": None, "checkedAt": now_iso, "error": None,
    }
    handle = (handle or YOUTUBE_HANDLE).strip()

    async with httpx.AsyncClient(timeout=15.0) as client:
        channel_id: Optional[str] = None
        channel_title: Optional[str] = None

        # 1) DB-cached channel_id (populated by OAuth callback)
        if db is not None:
            cfg = await db.integration_state.find_one({"key": "youtube_config"}, {"_id": 0}) or {}
            channel_id = (cfg.get("channelId") or "").strip() or None
            channel_title = cfg.get("channelName") or None
            # 2) OAuth refresh (recovers channel_id if it was ever cleared)
            if not channel_id and cfg.get("oauthRefreshToken"):
                channel_id, channel_title = await _channel_id_from_oauth(client, cfg["oauthRefreshToken"])
                if channel_id:
                    await db.integration_state.update_one(
                        {"key": "youtube_config"},
                        {"$set": {"channelId": channel_id, "channelName": channel_title}},
                    )

        # 3) Public handle-lookup fallback (only if OAuth is not connected)
        if not channel_id:
            channel_id = await _channel_id_from_handle(client, handle)

        if not channel_id:
            out["error"] = (
                f"channel not found — connect the admin YouTube OAuth or set channelId "
                f"in integration_state.youtube_config (handle attempted: {handle})"
            )
            return out

        # search.list eventType=live
        if not YOUTUBE_API_KEY:
            out["error"] = "YOUTUBE_API_KEY not configured"
            return out
        r = await client.get(f"{YT_API}/search", params={
            "part": "snippet", "channelId": channel_id, "eventType": "live",
            "type": "video", "maxResults": 1, "key": YOUTUBE_API_KEY,
        })
        if r.is_error:
            out["error"] = f"search.list {r.status_code}: {r.text[:150]}"
            return out
        items = (r.json() or {}).get("items") or []
        if not items:
            out["channelTitle"] = channel_title
            return out

        item = items[0]
        snippet = item.get("snippet") or {}
        out.update({
            "isLive": True,
            "videoId": (item.get("id") or {}).get("videoId"),
            "title": snippet.get("title"),
            "thumbnail": await _pick_thumbnail(snippet.get("thumbnails") or {}),
            "startedAt": snippet.get("publishedAt"),
            "channelTitle": snippet.get("channelTitle") or channel_title,
        })
    return out


# ---------------------------------------------------------------------------
# DB-cached wrappers (compat layer for server.py imports)
# ---------------------------------------------------------------------------
_CACHE_KEY = "youtube_live_cache"
_CACHE_TTL = 60  # seconds — server-side cache to stay within YouTube quota


async def refresh_and_store(db, handle: Optional[str] = None) -> dict:
    """Force a fresh live-status check and persist the result in
    `integration_state.youtube_live_cache`."""
    result = await check_live_now(handle=handle, db=db)
    try:
        await db.integration_state.update_one(
            {"key": _CACHE_KEY},
            {"$set": {"key": _CACHE_KEY, "result": result, "cachedAt": datetime.now(timezone.utc).isoformat()}},
            upsert=True,
        )
    except Exception:
        logger.exception("[youtube-live] failed to persist cache")
    return result


async def get_cached_or_refresh(db) -> dict:
    """Return the cached live status if <60s old; otherwise refresh."""
    try:
        doc = await db.integration_state.find_one({"key": _CACHE_KEY}, {"_id": 0}) or {}
        result = doc.get("result")
        cached_at = doc.get("cachedAt")
        if result and cached_at:
            try:
                cached_dt = datetime.fromisoformat(cached_at.replace("Z", "+00:00"))
                age = (datetime.now(timezone.utc) - cached_dt).total_seconds()
                if age < _CACHE_TTL:
                    return result
            except Exception:
                pass
    except Exception:
        logger.exception("[youtube-live] cache read failed")
    return await refresh_and_store(db)


async def periodic_live_loop(db) -> None:
    """Background task: refreshes the cache every YOUTUBE_LIVE_POLL_SECONDS."""
    import asyncio as _asyncio
    while True:
        try:
            await refresh_and_store(db)
        except Exception:
            logger.exception("[youtube-live] periodic refresh failed")
        await _asyncio.sleep(YOUTUBE_LIVE_POLL_SECONDS)
