# BB FM Kigali Radio — PRD

Mobile + web platform for BB FM Kigali (Rwanda). Live radio + VOD + News + Subscriptions + Admin console.

## Latest updates (iter 31 — Live Shows CMS + Admin-managed YouTube Channel)

### 1. Live Shows Admin CMS
- **New collection `live_shows`** with lifecycle: `scheduled → live → ended → published`
- **CRUD endpoints** — `GET/POST/PATCH/DELETE /api/admin/live-shows` + `/end`, `/attach-youtube-live`, `/recording` (upload), `/publish-to-youtube` actions
- **Fields**: title, description, coverImage, scheduledAt, expectedDurationMin, status, tier, recordingUrl (private storage path), youtubeVideoId (attached live broadcast), youtubePublishedVideoId (after upload), publishToYoutube toggle
- **Recording storage** — Emergent Object Storage, private by default. Reuses the hardened video-upload MIME/magic-byte validator from iter 27
- **Public endpoint `GET /api/live-shows`** — subscribers see recordingUrl + youtubeEmbedUrl; non-subscribers see title/cover only + `requiresSubscription: true`

### 2. Admin-Managed YouTube Channel Config
- **New `integration_state.youtube_config` doc** holding handle, apiKey, oauthClientId, oauthClientSecret, oauthRefreshToken, channelName, channelId — admin can switch channels without touching code or env
- **`GET/PUT /api/admin/youtube/config`** — read/write; GET never leaks secrets/refresh_token, only presence booleans
- **`/api/admin/youtube/oauth-start` + `/callback`** — full OAuth2 authorization_code flow. Opens Google consent, receives code, exchanges for refresh_token, looks up channelName/ID, stores everything encrypted-at-rest in Mongo
- **Periodic YouTube LIVE detection loop** now reads the admin-configured handle first (falls back to `YOUTUBE_HANDLE` env)

### 3. Publish-to-YouTube (auto-upload)
- **New backend module `youtube_publish.py`** — refreshes access_token from stored refresh_token, downloads the recording from our secure host, multipart-uploads to `youtube.upload` API (privacy default `unlisted`)
- **`POST /api/admin/live-shows/{id}/publish-to-youtube`** — 400 if no recording, 412 if channel not connected, else uploads and stamps `youtubePublishedVideoId` + `publishedToYoutubeAt`

### 4. Admin UI
- **`/admin/live-shows`** — CRUD grid with cover thumbnails, colored status pills (LIVE red, ENDED yellow, PUBLISHED green), action buttons per state: ATTACH YOUTUBE LIVE / END LIVE / UPLOAD RECORDING / REPLACE RECORDING / PUBLISH TO YOUTUBE
- **`/admin/youtube-config`** — connection status card (checkmarks for API Key / OAuth Client / Channel Authorized), channel handle input, API-key + OAuth Client ID/Secret fields (secure entry), one-tap "Connect Channel" button that opens Google consent
- Two new tiles in the Admin Dashboard

### 5. Verified by testing agent
- **23/23 backend pytest tests passed** — API contracts, subscription gating, OAuth error branches, config secret-safety
- Recording upload is admin-only + validated by the hardened multipart video validator

## Env vars that unlock advanced features
Existing:
```
YOUTUBE_API_KEY           # already set — used as fallback
YOUTUBE_HANDLE            # already set — used as fallback when admin_config.handle absent
```
Optional fallbacks (admin can supply via /admin/youtube-config instead):
```
YOUTUBE_OAUTH_CLIENT_ID
YOUTUBE_OAUTH_CLIENT_SECRET
```
Apple 5.1.1(v) revocation (still pending user's provisioning):
```
APPLE_TEAM_ID  APPLE_KEY_ID  APPLE_CLIENT_ID  APPLE_PRIVATE_KEY
```

## Test credentials
See `/app/memory/test_credentials.md`.
