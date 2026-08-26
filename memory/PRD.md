# BB FM Kigali Radio — PRD

Mobile + web platform for BB FM Kigali (Rwanda). Live radio + VOD + News + Subscriptions + Admin console.

## Latest updates (iter 34 — Live 24/7 Radio Streaming)

### 1. Real audio streaming wired
- Backend now serves the BB Kigali radio stream URL by default: `http://radio.bbkigali.com:8080/stream`
- Configurable via `RADIO_STREAM_URL` env var
- Optional HTTPS mirror via `RADIO_STREAM_URL_HTTPS` env var (used on HTTPS web pages to avoid mixed-content blocking)
- On restart, existing `radio_state` row is migrated to the new stream URL
- `GET /api/radio/now-playing` returns both `streamUrl` and `streamUrlHttps`

### 2. Frontend PlayerProvider now actually plays audio
- Was UI-only before; now uses `expo-audio`'s `createAudioPlayer` for real playback
- `pickStreamUrl(np)` picks the HTTPS mirror when the web page is HTTPS, falls back to HTTP otherwise
- `setAudioModeAsync({playsInSilentMode: true, shouldPlayInBackground: true})` for background playback + lock screen
- Play / pause / toggle now stream real audio

### 3. Platform permissions for live audio
- **iOS**: `UIBackgroundModes: ['audio']` (background playback), `NSAppTransportSecurity` with an ATS exception for `radio.bbkigali.com` (allows HTTP stream on iOS)
- **Android**: `usesCleartextTraffic: true`, `FOREGROUND_SERVICE` + `FOREGROUND_SERVICE_MEDIA_PLAYBACK` permissions

### 4. Web version confirmed live
- Preview: http://localhost:3000 (Emergent dashboard only)
- Production: https://radio-vod-platform.emergent.host — full-feature web app
- Custom domain bbkigali.com when the DNS points to the deploy

### 5. Verified
- 9/9 iter-34 backend pytest tests passed
- Frontend PlayerProvider actually invokes createAudioPlayer on toggle (browser captures the network request to the stream URL)

### One optional infra follow-up
Web browsers on HTTPS pages block HTTP media streams for security. On mobile builds this is not an issue (ATS + cleartext exceptions handle it). To make audio also work on the HTTPS web page:
- Option A: expose the Icecast stream behind Cloudflare/nginx TLS at e.g. `https://radio.bbkigali.com/stream` and set `RADIO_STREAM_URL_HTTPS` env var to that URL
- Option B: keep HTTP-only (web listeners will get an error; native app listeners will not)

## Test credentials
See `/app/memory/test_credentials.md`.
