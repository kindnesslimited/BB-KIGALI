"""YouTube channel sync for BB Kigali FM.

Pulls latest uploads from the configured YouTube channel handle and upserts them
into the `shows` collection so the app can stop showing seed videos.

Endpoint of interest (registered from server.py):
- POST /api/admin/youtube/sync   → on-demand refresh (admin only)
- Background task refreshes every YOUTUBE_REFRESH_HOURS (default 6h)
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

YT_API = "https://www.googleapis.com/youtube/v3"
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "").strip()
YOUTUBE_HANDLE = os.environ.get("YOUTUBE_HANDLE", "@bbkigalifm").strip()
YOUTUBE_REFRESH_HOURS = int(os.environ.get("YOUTUBE_REFRESH_HOURS", "6"))
YOUTUBE_CATEGORY_SLUG = os.environ.get("YOUTUBE_CATEGORY_SLUG", "bbkigali-youtube").strip()
YOUTUBE_CATEGORY_NAME = os.environ.get("YOUTUBE_CATEGORY_NAME", "BB Kigali on YouTube").strip()
YOUTUBE_MAX_ITEMS = int(os.environ.get("YOUTUBE_MAX_ITEMS", "50"))

_ISO_DUR = re.compile(r"P(?:(\d+)D)?T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")


def iso_duration_to_seconds(value: str | None) -> int:
    if not value:
        return 0
    m = _ISO_DUR.fullmatch(value)
    if not m:
        return 0
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


def format_duration(seconds: int) -> str:
    """Format duration as H:MM:SS or M:SS."""
    if seconds <= 0:
        return "0:00"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _pick_thumbnail(thumbs: dict[str, Any]) -> str | None:
    for k in ("maxres", "standard", "high", "medium", "default"):
        v = thumbs.get(k)
        if v and v.get("url"):
            return v["url"]
    return None


async def _yt_get(client: httpx.AsyncClient, resource: str, **params: Any) -> dict:
    if not YOUTUBE_API_KEY:
        raise RuntimeError("YOUTUBE_API_KEY not configured")
    params["key"] = YOUTUBE_API_KEY
    r = await client.get(f"{YT_API}/{resource}", params=params)
    if r.is_error:
        # Google returns { error: { code, message, errors:[{reason}] } }
        try:
            err = r.json().get("error", {})
        except Exception:
            err = {}
        msg = err.get("message") or r.text[:300]
        logger.error("[youtube] %s failed status=%s msg=%s", resource, r.status_code, msg)
        raise RuntimeError(f"YouTube API {resource} failed: {msg}")
    return r.json()


async def _resolve_channel(client: httpx.AsyncClient, handle: str) -> tuple[str, str, str, str | None]:
    """Return (channelId, uploadsPlaylistId, title, avatarUrl)."""
    handle = handle if handle.startswith("@") else f"@{handle}"
    data = await _yt_get(client, "channels", part="id,snippet,contentDetails", forHandle=handle)
    items = data.get("items") or []
    if not items:
        raise RuntimeError(f"YouTube channel handle not found: {handle}")
    item = items[0]
    ch_id = item["id"]
    uploads = item["contentDetails"]["relatedPlaylists"]["uploads"]
    snip = item.get("snippet") or {}
    title = snip.get("title") or handle.lstrip("@")
    avatar = _pick_thumbnail(snip.get("thumbnails") or {})
    return ch_id, uploads, title, avatar


async def _ensure_category(db) -> str:
    """Return the id of the auto-managed YouTube category, creating it if missing."""
    cat = await db.categories.find_one({"slug": YOUTUBE_CATEGORY_SLUG}, {"_id": 0})
    if cat:
        return cat["id"]
    doc = {
        "id": str(uuid.uuid4()),
        "name": YOUTUBE_CATEGORY_NAME,
        "slug": YOUTUBE_CATEGORY_SLUG,
        "active": True,
        "isDefault": False,
        "autoManaged": True,
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }
    await db.categories.insert_one(doc.copy())
    logger.info("[youtube] created category %s (%s)", doc["name"], doc["id"])
    return doc["id"]


async def sync_channel(db, handle: str | None = None) -> dict:
    """Pull latest uploads from YouTube and upsert them into db.shows.

    Returns a summary dict {ok, channelId, channelTitle, upserted, skipped, errors}.
    Non-throwing: caller handles failure via `ok=False`.
    """
    handle = (handle or YOUTUBE_HANDLE).strip()
    summary = {"ok": False, "handle": handle, "upserted": 0, "skipped": 0, "errors": None}
    if not YOUTUBE_API_KEY:
        summary["errors"] = "YOUTUBE_API_KEY not configured"
        return summary

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            channel_id, uploads_pid, channel_title, channel_avatar = await _resolve_channel(client, handle)
            summary["channelId"] = channel_id
            summary["channelTitle"] = channel_title

            # Page through playlistItems (max 50 per page).
            video_ids: list[str] = []
            page_token: str | None = None
            while len(video_ids) < YOUTUBE_MAX_ITEMS:
                params = {
                    "part": "contentDetails,snippet",
                    "playlistId": uploads_pid,
                    "maxResults": min(50, YOUTUBE_MAX_ITEMS - len(video_ids)),
                }
                if page_token:
                    params["pageToken"] = page_token
                pl = await _yt_get(client, "playlistItems", **params)
                for it in pl.get("items", []):
                    vid = (it.get("contentDetails") or {}).get("videoId") or \
                        ((it.get("snippet") or {}).get("resourceId") or {}).get("videoId")
                    if vid:
                        video_ids.append(vid)
                page_token = pl.get("nextPageToken")
                if not page_token:
                    break
            if not video_ids:
                summary["ok"] = True
                return summary

            # Enrich in batches of 50.
            enriched: dict[str, dict] = {}
            for i in range(0, len(video_ids), 50):
                batch = video_ids[i:i + 50]
                det = await _yt_get(client, "videos", part="snippet,contentDetails,status", id=",".join(batch))
                for v in det.get("items", []):
                    enriched[v["id"]] = v

        category_id = await _ensure_category(db)
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()

        # Preserve YouTube playlist ordering (newest first).
        for order_idx, vid in enumerate(video_ids):
            video = enriched.get(vid)
            if not video:
                summary["skipped"] += 1
                continue
            status = (video.get("status") or {}).get("privacyStatus")
            if status and status != "public":
                summary["skipped"] += 1
                continue
            snip = video.get("snippet") or {}
            cd = video.get("contentDetails") or {}
            title = snip.get("title") or "Untitled"
            desc = snip.get("description") or ""
            published = snip.get("publishedAt")
            duration_iso = cd.get("duration")
            duration_sec = iso_duration_to_seconds(duration_iso)
            thumb = _pick_thumbnail(snip.get("thumbnails") or {}) or channel_avatar
            embed = f"https://www.youtube.com/embed/{vid}"
            existing = await db.shows.find_one({"youtubeId": vid}, {"_id": 0, "id": 1, "isPremium": 1, "isPodcast": 1})

            payload_set = {
                "title": title,
                "description": desc[:2000],
                "category": YOUTUBE_CATEGORY_SLUG,
                "categoryId": category_id,
                "coverUrl": thumb,
                "thumbnail": thumb,
                "videoUrl": embed,
                "youtubeId": vid,
                "youtubeChannelId": channel_id,
                "youtubeChannelTitle": channel_title,
                "durationSeconds": duration_sec,
                "duration": format_duration(duration_sec),
                "durationIso": duration_iso,
                "publishedAt": published,
                "type": "vod",
                "source": "youtube",
                "sortIndex": order_idx,
                "updatedAt": now_iso,
            }
            payload_insert = {
                "id": str(uuid.uuid4()),
                "createdAt": now_iso,
                # First-time defaults — do not overwrite admin overrides on re-sync
                "isPremium": False,
                "isPodcast": False,
                "active": True,
            }
            if existing:
                await db.shows.update_one({"youtubeId": vid}, {"$set": payload_set})
            else:
                await db.shows.insert_one({**payload_insert, **payload_set, "youtubeId": vid})
            summary["upserted"] += 1

        summary["ok"] = True
        # Track last successful sync
        await db.integration_state.update_one(
            {"key": "youtube_sync"},
            {"$set": {
                "key": "youtube_sync",
                "handle": handle,
                "channelId": channel_id,
                "channelTitle": channel_title,
                "lastSyncAt": now_iso,
                "lastResult": {"upserted": summary["upserted"], "skipped": summary["skipped"]},
            }},
            upsert=True,
        )
        logger.info("[youtube] sync ok channel=%s upserted=%s skipped=%s", channel_title, summary["upserted"], summary["skipped"])
    except Exception as e:
        summary["errors"] = str(e)[:500]
        logger.exception("[youtube] sync failed")
        await db.integration_state.update_one(
            {"key": "youtube_sync"},
            {"$set": {
                "key": "youtube_sync",
                "handle": handle,
                "lastAttemptAt": datetime.now(timezone.utc).isoformat(),
                "lastError": summary["errors"],
            }},
            upsert=True,
        )
    return summary


async def periodic_sync_loop(db):
    """Run sync_channel every YOUTUBE_REFRESH_HOURS. Runs as a background task."""
    interval = max(1, YOUTUBE_REFRESH_HOURS) * 3600
    # Initial startup delay so app boot isn't blocked.
    await asyncio.sleep(30)
    while True:
        try:
            await sync_channel(db)
        except Exception:
            logger.exception("[youtube] periodic sync crashed (will retry)")
        await asyncio.sleep(interval)
