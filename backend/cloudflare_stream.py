"""
BB FM Kigali — Cloudflare Stream signed-playback client.

This tiny module wraps the BB Stream Signer Worker (see /app/cloudflare-worker).
We do NOT talk to Cloudflare directly — the Worker owns the STREAM binding
and mints tokens. Our backend just:
  1. verifies the caller is an active paid subscriber
  2. POSTs to the Worker with a shared secret to get a signed embedUrl
  3. returns the signed URL to the frontend

If the Worker URL / secret / customer subdomain are not configured, this
module raises HTTPException(503) so the frontend can render a graceful
"video service is temporarily unavailable" state instead of crashing.
"""
from __future__ import annotations

import os
from typing import Optional

import httpx
from fastapi import HTTPException

CLOUDFLARE_STREAM_WORKER_URL = os.environ.get("CLOUDFLARE_STREAM_WORKER_URL", "").strip().rstrip("/")
CLOUDFLARE_STREAM_WORKER_SECRET = os.environ.get("CLOUDFLARE_STREAM_WORKER_SECRET", "").strip()
CLOUDFLARE_STREAM_SUBDOMAIN = os.environ.get("CLOUDFLARE_STREAM_SUBDOMAIN", "").strip()


def stream_ready() -> bool:
    """True when all three env vars are set — used to advertise the feature."""
    return bool(CLOUDFLARE_STREAM_WORKER_URL and CLOUDFLARE_STREAM_WORKER_SECRET)


async def sign_playback(video_id: str, *, ttl_seconds: int = 900, origin: Optional[str] = None) -> dict:
    """Return `{token, embedUrl, manifestUrl, expiresAt, videoId}` for the
    given Cloudflare Stream UID. Caller MUST authorise the user first —
    this function does not know or care about subscription state.

    Raises HTTPException with a friendly detail on failure.
    """
    if not stream_ready():
        raise HTTPException(
            503,
            "Cloudflare Stream is not configured on the server yet — set CLOUDFLARE_STREAM_WORKER_URL/SECRET/SUBDOMAIN.",
        )
    if not video_id:
        raise HTTPException(400, "video_id required")

    payload: dict = {"videoId": video_id, "ttlSeconds": max(60, min(int(ttl_seconds), 3600))}
    if origin:
        payload["requireOrigin"] = origin

    try:
        async with httpx.AsyncClient(timeout=8.0) as c:
            r = await c.post(
                f"{CLOUDFLARE_STREAM_WORKER_URL}/sign",
                headers={
                    "Authorization": f"Bearer {CLOUDFLARE_STREAM_WORKER_SECRET}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
    except httpx.RequestError as e:
        raise HTTPException(502, f"Cannot reach Stream signer: {e}") from e

    if r.status_code == 401:
        raise HTTPException(500, "Stream signer rejected our shared secret — regenerate + redeploy.")
    if r.status_code >= 400:
        raise HTTPException(502, f"Stream signer returned {r.status_code}: {r.text[:200]}")

    data = r.json()
    # If the Worker didn't have the subdomain baked in, use ours as a fallback.
    if not data.get("embedUrl") and CLOUDFLARE_STREAM_SUBDOMAIN and data.get("token"):
        data["embedUrl"] = f"https://{CLOUDFLARE_STREAM_SUBDOMAIN}/{data['token']}/iframe"
        data["manifestUrl"] = f"https://{CLOUDFLARE_STREAM_SUBDOMAIN}/{data['token']}/manifest/video.m3u8"
    return data
