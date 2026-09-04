# Multi-channel YouTube Live (Iter 47)

## Problem
The app was monitoring a single YouTube channel. Product owner wants three
channels tracked independently:
- **B&B 2T6 Official** — https://www.youtube.com/@BANDB2T6OFFICIAL
- **BB Kigali FM** — https://www.youtube.com/@bbkigalifm
- **BB Sports Bar** — https://www.youtube.com/@BBSPORTSBAR

Each must have its own live card in the admin dashboard and its own entry
in the subscriber-facing Live TV section.

## What changed

### Backend
- **`youtube_live.py`** completely rewritten:
  - `CHANNELS` array defines the 3 channels (add / remove entries here to
    change what's monitored).
  - `ensure_channel_ids(db)` resolves each `@handle` to a channel ID via
    `channels?forHandle=` (1 quota unit each, cached in DB forever).
  - `_probe_channel_live(channel_id)` fetches `youtube.com/channel/{ID}/live`
    and parses the HTML — **zero YouTube Data API quota** per probe.
  - `check_all_channels(db)` returns `{channels: [...], anyLive, checkedAt}`,
    probing all channels in parallel with `asyncio.gather`.
  - `check_live_now()` kept as a legacy wrapper that returns the FIRST live
    channel in the old single-channel shape.
  - `refresh_and_store` + `get_cached_or_refresh` + `periodic_live_loop`
    now store/return the new multi-channel shape.

- **`server.py`**: new endpoint `GET /api/live/channels` returns the full
  per-channel status. Existing `/api/live/status` coerces the multi-channel
  cache back to the legacy shape for old clients.

### Payload shape (public — non-subscriber)
```json
{
  "channels": [
    {
      "key": "bbkigalifm",
      "handle": "@bbkigalifm",
      "channelId": "UC-6FrLSB7eFVXqEeDNADaQg",
      "channelName": "BB Kigali FM",
      "isLive": false,
      "videoId": null,
      "title": null,
      "thumbnail": null,
      "watchUrl": null,
      "embedUrl": null,
      "startedAt": null,
      "checkedAt": "2026-09-04T21:52Z",
      "error": null
    },
    { "key": "bandb2t6",    "channelName": "B&B 2T6 Official", "...": "..." },
    { "key": "bbsportsbar", "channelName": "BB Sports Bar",    "...": "..." }
  ],
  "anyLive": false,
  "checkedAt": "2026-09-04T21:52Z"
}
```

When a channel goes live:
- `isLive: true`, `title` + `thumbnail` populated from the live watch page.
- `videoId` / `watchUrl` / `embedUrl` returned ONLY to authenticated paid
  subscribers. Non-subscribers see `requiresSubscription: true` (paywall CTA).

## Verified end-to-end
Live-check ran against all 3 channels concurrently:
```
GET https://www.youtube.com/channel/UC-6FrLSB7eFVXqEeDNADaQg/live  → 200
GET https://www.youtube.com/channel/UCJ0ATFj2Hp03v-kXxh4fV6w/live  → 200
GET https://www.youtube.com/channel/UC1eLqOM8gPwEVGRNm2SF4eQ/live  → 200
```
No 401 errors, no YouTube Data API quota consumed.

## Frontend action
The mobile app in this workspace is a WebView wrapper that loads
`https://web.bbkigali.com`. The three-channel live cards + admin Live Control
grid must be built in the **web app codebase** by the Web Agent — see the
updated §7 of `/app/memory/web_admin_api_contract.md`.

## Adding / removing channels later
Edit `CHANNELS` in `/app/backend/youtube_live.py`. Each entry needs:
- `key` — stable UI id (never rename)
- `handle` — @handle to resolve
- `displayName` — fallback name if YouTube's API is unreachable

Restart the backend — channel IDs auto-resolve on next probe cycle.
