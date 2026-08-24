"""YouTube video publishing helpers.

Uploads a completed recording from our secure host to the YouTube channel
associated with a stored OAuth2 refresh_token (channel owner authorized
`youtube.upload` scope via the admin OAuth flow).

Requires:
- oauthClientId + oauthClientSecret from Google Cloud Console OAuth2 credentials
- oauthRefreshToken obtained via /api/admin/youtube/oauth-start + /callback
- The recording accessible via an HTTPS URL that our backend can GET (Emergent
  Object Storage returns such URLs).

If the OAuth Client hasn't been configured yet, calling this raises so the
Admin endpoint can return a friendly 412 with next steps.
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
YT_UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"


async def _refresh_access_token(client_id: str, client_secret: str, refresh_token: str) -> str:
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(GOOGLE_TOKEN_URL, data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        })
    if r.is_error:
        raise RuntimeError(f"refresh_token exchange failed: {r.status_code} {r.text[:300]}")
    payload = r.json() or {}
    tok = payload.get("access_token")
    if not tok:
        raise RuntimeError("Google did not return access_token")
    return tok


async def _download_recording(url: str) -> bytes:
    """Stream the recording from our host into memory. For huge files, swap to
    a resumable upload from a stream — this simple implementation is fine up
    to ~500 MB which is our Object Storage cap for videos."""
    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        r = await client.get(url)
    if r.is_error:
        raise RuntimeError(f"Could not fetch recording ({r.status_code})")
    return r.content


async def upload_recording_to_youtube(
    *,
    recording_url: str,
    title: str,
    description: str,
    oauth_client_id: str,
    oauth_client_secret: str,
    refresh_token: str,
    privacy: str = "unlisted",
    category_id: Optional[str] = None,
) -> dict:
    """Upload a completed live-show recording to YouTube. Returns {videoId, url}.

    Default privacy is `unlisted` so admin can review before making it fully
    public. Admin can flip to `public` in YouTube Studio afterwards, or we can
    expose privacy as a param later.
    """
    if not (oauth_client_id and oauth_client_secret and refresh_token):
        raise RuntimeError("YouTube OAuth client not configured — connect the channel in Admin → YouTube first")
    if not recording_url:
        raise RuntimeError("recording_url is required")

    access_token = await _refresh_access_token(oauth_client_id, oauth_client_secret, refresh_token)
    body = await _download_recording(recording_url)

    metadata = {
        "snippet": {
            "title": title[:100],
            "description": description[:4900],
            "tags": ["BB FM Kigali", "BB Kigali FM", "Rwanda", "Kigali"],
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }
    if category_id:
        metadata["snippet"]["categoryId"] = category_id

    # multipart upload — one shot is fine for < 500MB, otherwise switch to resumable
    import json as _json
    boundary = "bbfm-yt-upload-boundary"
    parts = [
        f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{_json.dumps(metadata)}\r\n",
        f"--{boundary}\r\nContent-Type: video/*\r\n\r\n",
    ]
    payload = parts[0].encode() + parts[1].encode() + body + f"\r\n--{boundary}--\r\n".encode()

    async with httpx.AsyncClient(timeout=None) as client:
        r = await client.post(
            YT_UPLOAD_URL,
            params={"part": "snippet,status", "uploadType": "multipart"},
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": f"multipart/related; boundary={boundary}",
            },
            content=payload,
        )
    if r.is_error:
        raise RuntimeError(f"YouTube upload failed: {r.status_code} {r.text[:500]}")
    result = r.json() or {}
    video_id = result.get("id")
    if not video_id:
        raise RuntimeError("YouTube did not return a videoId")
    logger.info("[youtube-publish] uploaded videoId=%s privacy=%s", video_id, privacy)
    return {"videoId": video_id, "url": f"https://www.youtube.com/watch?v={video_id}", "raw": result}
