"""YouTube LIVE detection for BB Kigali FM — OAuth-only, zero search.list quota.

Fixes applied (Iter 39):
  * REMOVED: `search.list` calls (100 quota units/call, hit daily cap quickly).
  * REMOVED: channel-handle lookups via `forHandle`.
  * ADDED: OAuth channel-id resolution — `GET /youtube/v3/channels?part=id&mine=true`
    using the stored access_token (auto-refreshed from refresh_token).
  * ADDED: OAuth live-status probe — `GET /youtube/v3/liveBroadcasts?part=snippet,status&broadcastStatus=active`
    which costs only 1 quota unit and returns every active broadcast the OAuth
    user owns. Channel is live when any item has `status.lifeCycleStatus == 'live'`.
  * ADDED: 401 auto-recovery — access_token is refreshed once on 401, then retried.
  * ADDED: Multi-channel support — checks BB Kigali FM main + UCJ0ATFj2Hp03v-kXxh4fV6w
    (B&B Kigali Official) and returns the first one found live.

Response shape is unchanged so the existing frontend keeps working:
  {isLive, videoId, title, thumbnail, startedAt, channelTitle, checkedAt, error}
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

YT_API = "https://www.googleapis.com/youtube/v3"
GOOGLE_OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"

# Env fallbacks — server.py stores the effective client_id/secret in
# integration_state.youtube_config, but we accept env overrides too.
GOOGLE_OAUTH_CLIENT_ID = (
    os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
    or os.environ.get("YOUTUBE_OAUTH_CLIENT_ID")
    or ""
).strip()
GOOGLE_OAUTH_CLIENT_SECRET = (
    os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")
    or os.environ.get("YOUTUBE_OAUTH_CLIENT_SECRET")
    or ""
).strip()

# Channels we care about — user directive: main BB Kigali FM channel + B&B Kigali Official.
# Main channel id resolves dynamically via `channels?mine=true` (kept in DB).
# Second one is pinned by explicit channel id.
SECONDARY_CHANNEL_ID = "UCJ0ATFj2Hp03v-kXxh4fV6w"  # B&B Kigali Official

YOUTUBE_LIVE_POLL_SECONDS = int(os.environ.get("YOUTUBE_LIVE_POLL_SECONDS", "600"))


# ---------------------------------------------------------------------------
# OAuth token helpers
# ---------------------------------------------------------------------------
async def _get_oauth_creds(db) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Return (refresh_token, client_id, client_secret) from DB, falling back
    to env vars for client_id/secret."""
    cfg = await db.integration_state.find_one({"key": "youtube_config"}, {"_id": 0}) or {}
    rt = (cfg.get("oauthRefreshToken") or "").strip() or None
    cid = (cfg.get("oauthClientId") or GOOGLE_OAUTH_CLIENT_ID or "").strip() or None
    csec = (cfg.get("oauthClientSecret") or GOOGLE_OAUTH_CLIENT_SECRET or "").strip() or None
    return rt, cid, csec


async def _refresh_access_token(db) -> Optional[str]:
    """Exchange the stored refresh_token for a fresh access_token."""
    rt, cid, csec = await _get_oauth_creds(db)
    if not (rt and cid and csec):
        return None
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.post(GOOGLE_OAUTH_TOKEN_URL, data={
                "client_id": cid,
                "client_secret": csec,
                "refresh_token": rt,
                "grant_type": "refresh_token",
            })
        if r.status_code == 200:
            tok = (r.json() or {}).get("access_token")
            if tok:
                # Cache in DB for other request-handlers to reuse before expiry.
                await db.integration_state.update_one(
                    {"key": "youtube_config"},
                    {"$set": {
                        "oauthAccessToken": tok,
                        "oauthAccessTokenAt": datetime.now(timezone.utc).isoformat(),
                    }},
                )
                return tok
        logger.warning("[youtube-live] refresh_token exchange %s: %s", r.status_code, r.text[:200])
    except Exception:
        logger.exception("[youtube-live] refresh_token exchange failed")
    return None


async def _get_access_token(db, force_refresh: bool = False) -> Optional[str]:
    """Return a usable access_token. Reuses the DB-cached one if <50 min old,
    otherwise refreshes."""
    if not force_refresh:
        cfg = await db.integration_state.find_one({"key": "youtube_config"}, {"_id": 0}) or {}
        tok = cfg.get("oauthAccessToken")
        at = cfg.get("oauthAccessTokenAt")
        if tok and at:
            try:
                issued = datetime.fromisoformat(at.replace("Z", "+00:00"))
                age = (datetime.now(timezone.utc) - issued).total_seconds()
                if age < 3000:  # <50min — well under Google's 1h token lifetime
                    return tok
            except Exception:
                pass
    return await _refresh_access_token(db)


async def _yt_get(db, path: str, params: dict) -> tuple[int, dict]:
    """Authenticated YouTube API GET with automatic 401→refresh→retry."""
    async def _do(token: str):
        async with httpx.AsyncClient(timeout=15.0) as c:
            return await c.get(f"{YT_API}{path}", params=params,
                               headers={"Authorization": f"Bearer {token}"})

    tok = await _get_access_token(db)
    if not tok:
        return 0, {"error": "oauth_not_connected"}
    r = await _do(tok)
    if r.status_code == 401:
        # access_token expired mid-flight — refresh once and retry.
        tok = await _get_access_token(db, force_refresh=True)
        if not tok:
            return 401, {"error": "oauth_refresh_failed"}
        r = await _do(tok)
    try:
        return r.status_code, r.json() if r.content else {}
    except Exception:
        return r.status_code, {"raw": r.text[:300]}


# ---------------------------------------------------------------------------
# Channel + live-broadcast probes
# ---------------------------------------------------------------------------
async def _list_mine_channels(db) -> list[dict]:
    """`channels?part=id,snippet&mine=true` — every channel the OAuth user manages."""
    status, body = await _yt_get(db, "/channels", {"part": "id,snippet", "mine": "true"})
    if status != 200:
        return []
    return (body.get("items") or [])


async def _list_active_broadcasts(db) -> list[dict]:
    """`liveBroadcasts?broadcastStatus=active&part=snippet,status&mine=true` —
    every active broadcast across the OAuth user's channels. 1 quota unit."""
    status, body = await _yt_get(db, "/liveBroadcasts", {
        "part": "snippet,status",
        "broadcastStatus": "active",
        "broadcastType": "all",
        "mine": "true",
        "maxResults": 10,
    })
    if status != 200:
        return []
    return (body.get("items") or [])


def _pick_thumbnail(thumbs: dict) -> Optional[str]:
    for k in ("maxres", "standard", "high", "medium", "default"):
        v = (thumbs or {}).get(k)
        if v and v.get("url"):
            return v["url"]
    return None


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------
async def check_live_now(handle: Optional[str] = None, db=None) -> dict:
    """Return the current LIVE status for BB Kigali. Same shape as before.

    Strategy (100% OAuth, zero search.list):
      1. Resolve `channels?mine=true` → collect all channel IDs the OAuth user
         owns. Cache the primary one in `integration_state.youtube_config.channelId`.
      2. Fetch `liveBroadcasts?broadcastStatus=active&mine=true` — returns every
         active broadcast the OAuth user is running.
      3. For each active broadcast, check `status.lifeCycleStatus == 'live'`.
      4. Prefer broadcasts on the target channels (main BB Kigali FM + secondary
         UCJ0ATFj2Hp03v-kXxh4fV6w). Return the first match.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    out: dict = {
        "isLive": False, "videoId": None, "title": None, "thumbnail": None,
        "startedAt": None, "channelTitle": None, "checkedAt": now_iso, "error": None,
    }
    if db is None:
        out["error"] = "db_not_provided"
        return out

    # Confirm OAuth is connected
    rt, cid, csec = await _get_oauth_creds(db)
    if not (rt and cid and csec):
        out["error"] = "OAuth not connected — connect the admin YouTube account in /admin/settings"
        return out

    # 1) Refresh channel-id cache from OAuth (cheap: 1 quota unit)
    channels = await _list_mine_channels(db)
    owned_channel_ids: list[str] = []
    primary_title: Optional[str] = None
    for it in channels:
        cid_ = it.get("id")
        if cid_:
            owned_channel_ids.append(cid_)
        snip = it.get("snippet") or {}
        if not primary_title:
            primary_title = snip.get("title")

    if owned_channel_ids:
        # Persist primary channel_id for other callers/reporting.
        await db.integration_state.update_one(
            {"key": "youtube_config"},
            {"$set": {"channelId": owned_channel_ids[0], "channelName": primary_title}},
        )

    # Target channel filter (main + explicit secondary from spec)
    target_ids = set(owned_channel_ids) | {SECONDARY_CHANNEL_ID}

    # 2) Ask YouTube for active broadcasts
    broadcasts = await _list_active_broadcasts(db)

    # 3) Find the first LIVE broadcast that belongs to a target channel
    for b in broadcasts:
        status_obj = b.get("status") or {}
        if status_obj.get("lifeCycleStatus") != "live":
            continue
        snippet = b.get("snippet") or {}
        ch_id = snippet.get("channelId")
        # Filter to our target channels (main + UCJ0AT…). If channel_id isn't
        # in the target set, skip — keeps unrelated broadcasts out.
        if target_ids and ch_id and ch_id not in target_ids:
            continue
        out.update({
            "isLive": True,
            "videoId": b.get("id"),  # liveBroadcast.id IS the videoId
            "title": snippet.get("title"),
            "thumbnail": _pick_thumbnail(snippet.get("thumbnails") or {}),
            "startedAt": snippet.get("actualStartTime") or snippet.get("scheduledStartTime") or snippet.get("publishedAt"),
            "channelTitle": snippet.get("channelTitle") or primary_title,
        })
        return out

    # No live broadcast — still report channelTitle so the UI can show branding.
    out["channelTitle"] = primary_title
    return out


# ---------------------------------------------------------------------------
# DB-cached wrappers (compat layer — server.py imports these names)
# ---------------------------------------------------------------------------
_CACHE_KEY = "youtube_live_cache"
_CACHE_TTL = 60  # seconds — server-side cache tames quota use


async def refresh_and_store(db, handle: Optional[str] = None) -> dict:
    """Force a fresh live-status check and persist the result."""
    result = await check_live_now(handle=handle, db=db)
    try:
        await db.integration_state.update_one(
            {"key": _CACHE_KEY},
            {"$set": {"key": _CACHE_KEY, "result": result,
                      "cachedAt": datetime.now(timezone.utc).isoformat()}},
            upsert=True,
        )
    except Exception:
        logger.exception("[youtube-live] cache persist failed")
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
    while True:
        try:
            await refresh_and_store(db)
        except Exception:
            logger.exception("[youtube-live] periodic refresh failed")
        await asyncio.sleep(YOUTUBE_LIVE_POLL_SECONDS)
