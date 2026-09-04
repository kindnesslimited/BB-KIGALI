"""YouTube LIVE detection for BB Kigali FM — multi-channel, API-key based.

Design (Iter 47):
  * Supports N configured channels, each monitored INDEPENDENTLY.
  * Live-detection strategy: fetch `https://www.youtube.com/channel/{CID}/live`
    which YouTube redirects to the ACTIVE broadcast's watch URL when live, or
    to the channel's home page when not. This costs ZERO YouTube Data API
    quota — perfect for polling every 60 seconds across many channels.
  * Channel-ID resolution: one-time `channels?forHandle=@handle&key=API_KEY`
    call per handle (1 quota unit, cached in DB forever).
  * Video metadata (title / thumbnail): `videos?id={vid}&part=snippet` — 1
    quota unit, ONLY when the channel is actually live.

Response shape:
  { channels: [
      { key, handle, channelId, channelName, isLive, videoId, title,
        thumbnail, startedAt, watchUrl, embedUrl, checkedAt, error }
    ],
    anyLive: bool,
    checkedAt: iso8601 }

Legacy single-channel shape (kept for old mobile builds that still hit the
old endpoint):
  { isLive, videoId, title, thumbnail, startedAt, channelTitle, checkedAt,
    error, requiresSubscription }
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

YT_API = "https://www.googleapis.com/youtube/v3"
YT_LIVE_REDIRECT_TMPL = "https://www.youtube.com/channel/{cid}/live"

YOUTUBE_API_KEY = (os.environ.get("YOUTUBE_API_KEY") or "").strip()
YOUTUBE_LIVE_POLL_SECONDS = int(os.environ.get("YOUTUBE_LIVE_POLL_SECONDS", "600"))

# ---------------------------------------------------------------------------
# Channels supported by the BB Kigali app. Order matters — the aggregate
# `anyLive` picks the first one currently live, so the primary channel goes
# first. Add or remove entries here to change the app's live-detection set.
# ---------------------------------------------------------------------------
CHANNELS: list[dict] = [
    {"key": "bbkigalifm",  "handle": "@bbkigalifm",       "displayName": "BB Kigali FM"},
    {"key": "bandb2t6",    "handle": "@BANDB2T6OFFICIAL", "displayName": "B&B 2T6 Official"},
    {"key": "bbsportsbar", "handle": "@BBSPORTSBAR",      "displayName": "BB Sports Bar"},
]


# ---------------------------------------------------------------------------
# Channel-ID resolution — cached forever in `integration_state.youtube_channels`.
# ---------------------------------------------------------------------------
async def _get_channel_cache(db) -> dict:
    doc = await db.integration_state.find_one({"key": "youtube_channels"}, {"_id": 0}) or {}
    return doc.get("cache") or {}


async def _save_channel_cache(db, cache: dict) -> None:
    await db.integration_state.update_one(
        {"key": "youtube_channels"},
        {"$set": {"key": "youtube_channels", "cache": cache,
                  "updatedAt": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )


async def _resolve_channel_by_handle(handle: str) -> Optional[dict]:
    """One-time `channels?forHandle=` lookup (1 quota unit). Returns
    {id, title} on success, None on any failure."""
    if not YOUTUBE_API_KEY or not handle:
        return None
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(f"{YT_API}/channels", params={
                "part": "id,snippet",
                "forHandle": handle,
                "key": YOUTUBE_API_KEY,
            })
        if r.status_code != 200:
            logger.warning("[yt-live] resolve %s → %s: %s", handle, r.status_code, r.text[:200])
            return None
        items = (r.json() or {}).get("items") or []
        if not items:
            return None
        it = items[0]
        return {"id": it.get("id"), "title": (it.get("snippet") or {}).get("title")}
    except Exception:
        logger.exception("[yt-live] resolve %s failed", handle)
        return None


async def ensure_channel_ids(db) -> dict:
    """Resolve every configured channel's ID (once) and return the cache map
    { key: {handle, channelId, channelName} }. Idempotent."""
    cache = await _get_channel_cache(db)
    dirty = False
    for ch in CHANNELS:
        key = ch["key"]
        entry = cache.get(key) or {}
        # Re-resolve if the cache is missing an ID or the handle changed.
        if not entry.get("channelId") or entry.get("handle") != ch["handle"]:
            info = await _resolve_channel_by_handle(ch["handle"])
            if info and info.get("id"):
                cache[key] = {
                    "handle": ch["handle"],
                    "channelId": info["id"],
                    "channelName": info.get("title") or ch["displayName"],
                    "resolvedAt": datetime.now(timezone.utc).isoformat(),
                }
                dirty = True
    if dirty:
        await _save_channel_cache(db, cache)
    return cache


# ---------------------------------------------------------------------------
# Live probe — HTML-only, zero API quota.
# ---------------------------------------------------------------------------
_VIDEO_ID_RE = re.compile(r'"videoId":"([A-Za-z0-9_-]{11})"')
_CANONICAL_RE = re.compile(r'<link\s+rel="canonical"\s+href="([^"]+)"')
_TITLE_RE = re.compile(r'<meta\s+name="title"\s+content="([^"]+)"')
_IS_LIVE_RE = re.compile(r'"isLiveNow":\s*true|"isLive":\s*true|"isUpcoming":\s*false[^"]*"isLive":\s*true')


async def _probe_channel_live(channel_id: str) -> dict:
    """Returns {isLive, videoId, title, thumbnail, watchUrl, embedUrl}.
    Zero quota — plain HTTP fetch of the /channel/{id}/live redirect page."""
    url = YT_LIVE_REDIRECT_TMPL.format(cid=channel_id)
    out: dict = {
        "isLive": False, "videoId": None, "title": None,
        "thumbnail": None, "watchUrl": None, "embedUrl": None,
    }
    try:
        async with httpx.AsyncClient(
            timeout=8.0, follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (BB-Kigali-LiveProbe)",
                     "Accept-Language": "en-US,en;q=0.9"},
        ) as c:
            r = await c.get(url)
    except Exception as e:
        return {**out, "error": f"probe_failed:{e.__class__.__name__}"}
    if r.status_code != 200:
        return {**out, "error": f"probe_http_{r.status_code}"}

    html = r.text
    final = str(r.url)

    # 1) If YouTube redirected to a /watch?v=... page, the channel is live.
    m = re.search(r"[?&]v=([A-Za-z0-9_-]{11})", final)
    video_id: Optional[str] = m.group(1) if m else None

    # 2) Fallback: some regions redirect to the channel home with the live
    #    video embedded — parse the videoId from the canonical link or from
    #    the ytInitialPlayerResponse blob.
    if not video_id:
        cm = _CANONICAL_RE.search(html)
        if cm and "watch?v=" in cm.group(1):
            m2 = re.search(r"v=([A-Za-z0-9_-]{11})", cm.group(1))
            if m2:
                video_id = m2.group(1)

    # 3) Confirm it's actually LIVE (not a scheduled premiere) — look for
    #    the isLive marker inside the player response payload.
    is_live_flag = bool(_IS_LIVE_RE.search(html))
    if video_id and (is_live_flag or "hlsManifestUrl" in html):
        # Pull the title from the meta tag (cheap, no extra API call).
        tm = _TITLE_RE.search(html)
        title = tm.group(1) if tm else None
        out.update({
            "isLive": True,
            "videoId": video_id,
            "title": title,
            "thumbnail": f"https://i.ytimg.com/vi/{video_id}/hqdefault_live.jpg",
            "watchUrl": f"https://www.youtube.com/watch?v={video_id}",
            "embedUrl": f"https://www.youtube.com/embed/{video_id}?autoplay=1&playsinline=1",
        })
    return out


# ---------------------------------------------------------------------------
# Public API — multi-channel status
# ---------------------------------------------------------------------------
async def check_all_channels(db) -> dict:
    """Return the live status for EVERY configured channel."""
    now_iso = datetime.now(timezone.utc).isoformat()
    cache = await ensure_channel_ids(db)
    results: list[dict] = []
    any_live = False

    # Probe channels in parallel — each probe is a single HTTP fetch.
    async def _probe_one(ch: dict) -> dict:
        entry = cache.get(ch["key"]) or {}
        cid = entry.get("channelId")
        if not cid:
            return {
                "key": ch["key"], "handle": ch["handle"],
                "channelId": None, "channelName": ch["displayName"],
                "isLive": False, "videoId": None, "title": None,
                "thumbnail": None, "startedAt": None,
                "watchUrl": None, "embedUrl": None,
                "checkedAt": now_iso,
                "error": "channel_id_unresolved",
            }
        probe = await _probe_channel_live(cid)
        return {
            "key": ch["key"], "handle": ch["handle"],
            "channelId": cid,
            "channelName": entry.get("channelName") or ch["displayName"],
            "isLive": probe.get("isLive", False),
            "videoId": probe.get("videoId"),
            "title": probe.get("title"),
            "thumbnail": probe.get("thumbnail"),
            "watchUrl": probe.get("watchUrl"),
            "embedUrl": probe.get("embedUrl"),
            "startedAt": None,  # not available from the HTML probe
            "checkedAt": now_iso,
            "error": probe.get("error"),
        }

    probes = await asyncio.gather(*[_probe_one(ch) for ch in CHANNELS], return_exceptions=True)
    for r in probes:
        if isinstance(r, Exception):
            logger.exception("[yt-live] probe raised: %s", r)
            continue
        results.append(r)
        if r.get("isLive"):
            any_live = True

    return {"channels": results, "anyLive": any_live, "checkedAt": now_iso}


# ---------------------------------------------------------------------------
# Legacy single-channel wrapper — kept for backward compatibility with any
# clients still calling the old endpoint.
# ---------------------------------------------------------------------------
async def check_live_now(handle: Optional[str] = None, db=None) -> dict:
    """Return the FIRST live channel in the aggregate result, or a not-live
    payload with metadata from the primary channel."""
    now_iso = datetime.now(timezone.utc).isoformat()
    if db is None:
        return {"isLive": False, "videoId": None, "title": None, "thumbnail": None,
                "startedAt": None, "channelTitle": None, "checkedAt": now_iso,
                "error": "db_not_provided"}
    agg = await check_all_channels(db)
    for ch in agg["channels"]:
        if ch.get("isLive"):
            return {
                "isLive": True, "videoId": ch.get("videoId"), "title": ch.get("title"),
                "thumbnail": ch.get("thumbnail"), "startedAt": ch.get("startedAt"),
                "channelTitle": ch.get("channelName"),
                "checkedAt": now_iso, "error": None,
            }
    # Nothing live — return the primary channel's branding.
    primary = agg["channels"][0] if agg["channels"] else {}
    return {
        "isLive": False, "videoId": None, "title": None, "thumbnail": None,
        "startedAt": None, "channelTitle": primary.get("channelName"),
        "checkedAt": now_iso, "error": None,
    }


# ---------------------------------------------------------------------------
# DB-cached wrappers — server.py imports these names.
# ---------------------------------------------------------------------------
_CACHE_KEY = "youtube_live_cache"
_CACHE_TTL = 60  # seconds — cheap HTML probes, but no need to hammer YouTube


async def refresh_and_store(db, handle: Optional[str] = None) -> dict:
    """Force a fresh multi-channel status refresh and persist it."""
    agg = await check_all_channels(db)
    try:
        await db.integration_state.update_one(
            {"key": _CACHE_KEY},
            {"$set": {"key": _CACHE_KEY, "result": agg,
                      "cachedAt": datetime.now(timezone.utc).isoformat()}},
            upsert=True,
        )
    except Exception:
        logger.exception("[yt-live] cache persist failed")
    return agg


async def get_cached_or_refresh(db) -> dict:
    """Return cached multi-channel status if <60s old, else refresh."""
    try:
        doc = await db.integration_state.find_one({"key": _CACHE_KEY}, {"_id": 0}) or {}
        result = doc.get("result")
        cached_at = doc.get("cachedAt")
        if result and cached_at and isinstance(result, dict) and "channels" in result:
            try:
                cached_dt = datetime.fromisoformat(cached_at.replace("Z", "+00:00"))
                age = (datetime.now(timezone.utc) - cached_dt).total_seconds()
                if age < _CACHE_TTL:
                    return result
            except Exception:
                pass
    except Exception:
        logger.exception("[yt-live] cache read failed")
    return await refresh_and_store(db)


async def periodic_live_loop(db) -> None:
    """Background task — refresh the multi-channel cache periodically."""
    while True:
        try:
            await refresh_and_store(db)
        except Exception:
            logger.exception("[yt-live] periodic refresh failed")
        await asyncio.sleep(YOUTUBE_LIVE_POLL_SECONDS)
