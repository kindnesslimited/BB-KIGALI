"""YouTube LIVE detection for BB Kigali FM.

Cheap, on-demand + background poller that tells the app whether an official
YouTube live broadcast is currently on-air. Results are cached in the
`integration_state` collection under key `youtube_live:<handle>` so we don't
burn our daily quota on every user request.

The `search.list` endpoint with `eventType=live` costs 100 quota units per call.
Default `YOUTUBE_LIVE_POLL_SECONDS=180` = ~480 polls/day = 48k units — well
within the default 10k daily quota? No — 48k > 10k, so we bump to 300s (300 polls/day = 30k).
Rounded to 600s for safety in prod (144 polls/day = 14.4k). Config lives in env.
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
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "").strip()
YOUTUBE_HANDLE = os.environ.get("YOUTUBE_HANDLE", "@bbkigalifm").strip()
YOUTUBE_LIVE_POLL_SECONDS = int(os.environ.get("YOUTUBE_LIVE_POLL_SECONDS", "600"))  # 10 min


async def _resolve_channel_id(client: httpx.AsyncClient, handle: str) -> Optional[str]:
    handle = handle if handle.startswith("@") else f"@{handle}"
    r = await client.get(f"{YT_API}/channels", params={
        "part": "id", "forHandle": handle, "key": YOUTUBE_API_KEY,
    })
    if r.is_error:
        return None
    items = (r.json() or {}).get("items") or []
    return items[0]["id"] if items else None


async def _pick_thumbnail(thumbs: dict) -> Optional[str]:
    for k in ("maxres", "standard", "high", "medium", "default"):
        v = (thumbs or {}).get(k)
        if v and v.get("url"):
            return v["url"]
    return None


async def check_live_now(handle: Optional[str] = None) -> dict:
    """Ask YouTube if the given handle is broadcasting right now.

    Returns:
        {
          "isLive": bool,
          "videoId": Optional[str],
          "title": Optional[str],
          "thumbnail": Optional[str],
          "startedAt": Optional[str],  # ISO
          "channelTitle": Optional[str],
          "checkedAt": ISO datetime,
          "error": Optional[str],
        }
    """
    handle = (handle or YOUTUBE_HANDLE).strip()
    now_iso = datetime.now(timezone.utc).isoformat()
    out: dict = {
        "isLive": False, "videoId": None, "title": None, "thumbnail": None,
        "startedAt": None, "channelTitle": None, "checkedAt": now_iso, "error": None,
    }
    if not YOUTUBE_API_KEY:
        out["error"] = "YOUTUBE_API_KEY not configured"
        return out
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            channel_id = await _resolve_channel_id(client, handle)
            if not channel_id:
                out["error"] = f"channel not found: {handle}"
                return out
            # search.list eventType=live returns the currently-live broadcast if any.
            r = await client.get(f"{YT_API}/search", params={
                "part": "snippet",
                "channelId": channel_id,
                "eventType": "live",
                "type": "video",
                "maxResults": 1,
                "key": YOUTUBE_API_KEY,
            })
            if r.is_error:
                try:
                    err = r.json().get("error", {}).get("message")
                except Exception:
                    err = None
                out["error"] = err or f"HTTP {r.status_code}"
                return out
            items = (r.json() or {}).get("items") or []
            if not items:
                return out  # not live
            item = items[0]
            snip = item.get("snippet") or {}
            video_id = (item.get("id") or {}).get("videoId")
            if not video_id:
                return out
            out.update({
                "isLive": True,
                "videoId": video_id,
                "title": snip.get("title") or "LIVE",
                "thumbnail": await _pick_thumbnail(snip.get("thumbnails") or {}) or f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg",
                "startedAt": snip.get("publishTime") or snip.get("publishedAt"),
                "channelTitle": snip.get("channelTitle"),
            })
    except Exception as e:
        out["error"] = str(e)[:300]
        logger.exception("[youtube-live] check failed for %s", handle)
    return out


async def refresh_and_store(db, handle: Optional[str] = None) -> dict:
    """Check live status and cache it in db.integration_state."""
    handle = (handle or YOUTUBE_HANDLE).strip()
    result = await check_live_now(handle)
    key = f"youtube_live:{handle.lstrip('@').lower()}"
    await db.integration_state.update_one(
        {"key": key},
        {"$set": {"key": key, "handle": handle, **result}},
        upsert=True,
    )
    return result


async def get_cached_or_refresh(db, handle: Optional[str] = None, max_age_sec: int = 60) -> dict:
    """Return the cached live status if fresh, otherwise poll YouTube.

    Client endpoints call this to avoid burning quota on every hit.
    """
    handle = (handle or YOUTUBE_HANDLE).strip()
    key = f"youtube_live:{handle.lstrip('@').lower()}"
    doc = await db.integration_state.find_one({"key": key}, {"_id": 0})
    if doc and doc.get("checkedAt"):
        try:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(doc["checkedAt"].replace("Z", "+00:00"))).total_seconds()
            if age < max_age_sec:
                return {k: v for k, v in doc.items() if k not in ("key", "handle")}
        except Exception:
            pass
    return await refresh_and_store(db, handle)


async def periodic_live_loop(db):
    """Background loop refreshing the live-now cache."""
    interval = max(60, YOUTUBE_LIVE_POLL_SECONDS)
    # Slight startup delay so we don't hammer YouTube on cold boot.
    await asyncio.sleep(15)
    while True:
        try:
            await refresh_and_store(db)
        except Exception:
            logger.exception("[youtube-live] periodic loop crashed (will retry)")
        await asyncio.sleep(interval)
