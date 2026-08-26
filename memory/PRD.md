# BB FM Kigali Radio — PRD

Mobile + web platform for BB FM Kigali (Rwanda). Live radio + VOD + News + Subscriptions + Admin console.

## Latest updates (iter 32)

### 1. Brand palette — RED / BLUE / BLACK / WHITE only
- `theme.ts` refactored: `brandPrimary` now `#E10600` (BB Kigali red), plus `accent`/`accentSoft` blue tokens
- All orange (`#FF6B00`, `#CC5500`, `#40220A`, `#FFB885`) and gold (`#DAA520`) removed
- `success` is now blue (`#1E5FB4`), `warning` is red, `error` unchanged red — no yellow/orange anywhere
- `app.json` notification color updated
- Verified visually: no orange left on Home, Shows, News, Profile, mini-player, tab bar, live badges

### 2. Cloudflare Stream integration (private live streaming + secure recording)
- **New endpoints**:
  - `GET /api/admin/cloudflare-stream/config` — status, never leaks apiToken
  - `PUT /api/admin/cloudflare-stream/config` — save credentials
  - `POST /api/admin/cloudflare-stream/live-input` — creates a new CF Stream live_input (RTMPS URL + stream key + HLS playback)
  - `GET /api/admin/cloudflare-stream/videos` — list uploaded videos
- **New admin UI** `/admin/cloudflare-stream` — status card, credentials form, one-tap create-live-input, copy-to-clipboard RTMP url & stream key
- Admin can now go live from OBS/mobile with private RTMP ingest; recording is automatic; playback via signed HLS
- Live Show recordings can point to CF Stream HLS URL

### 3. Support ticket — Contabo VDS migration
- Draft at `/app/memory/support_ticket_contabo_migration.md` — cut-over plan, third-party webhook updates, backup/DR requirements, and a security note about the leaked password
- Customer must send to support@emergent.sh with their Job ID; SSH access will be granted via SSH keys only, never chat

### 4. Verified
- 10/10 iter-32 backend pytest tests passed
- YouTube LIVE regression check still green (subscription gating intact)
- Full test suite from prior iters still green

## Env vars / creds still expected from customer
- `APPLE_TEAM_ID`, `APPLE_KEY_ID`, `APPLE_CLIENT_ID`, `APPLE_PRIVATE_KEY` — for TestFlight token revocation
- Cloudflare account ID + API token — enter in `/admin/cloudflare-stream`
- (Contabo cut-over will be handled through Emergent support)

## Test credentials
See `/app/memory/test_credentials.md`.
