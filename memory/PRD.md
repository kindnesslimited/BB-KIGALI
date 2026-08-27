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

## 2026-08-27 — HTTPS radio + Apple revocation wired
- `RADIO_STREAM_URL_HTTPS=https://stream.bbkigali.com/stream/1/` set in backend/.env → `GET /api/radio/now-playing` now returns `streamUrlHttps`.
- Admin CMS: `AdminSettingsIn.radioStreamUrlHttps` added so ops can change it without shell access.
- Web player (`src/context/player.tsx`) now ALWAYS prefers `streamUrlHttps` on web (no more mixed-content on HTTPS pages).
- Apple Sign-in revocation is now READY: `APPLE_TEAM_ID`, `APPLE_KEY_ID`, `APPLE_PRIVATE_KEY` all set. `apple_revocation_ready()` returns True. `DELETE /api/auth/me` will now hit Apple `/auth/revoke` for users who signed in with Apple.
- ⚠️ Apple `AuthKey` private key was pasted in chat — user asked to rotate it and re-send. Once rotated, the new key must be placed in `APPLE_PRIVATE_KEY` env var (use \n escapes for newlines).
- Backend smoke: iteration_33.json — 12/12 pass.

## 2026-08-27 — RevenueCat integrated (Emergent-managed)
- **Setup**: `/setup` → `rc_project_id=proj7b23b575`, `entitlement=pro`, `offering=default`, `$rc_monthly=€3/P1M`, `$rc_annual=€30/P1Y` (mirrors web Premium Monthly / Yearly).
- **Frontend**:
  - `src/lib/revenuecat.tsx` (SDK init, `SubscriptionProvider`, `useSubscription`, `useBindRevenueCatIdentity`).
  - `_layout.tsx` — `initializeRevenueCat()` at module scope; wraps app in `AppQueryClientProvider → AuthProvider → SubscriptionProvider`.
  - `context/auth.tsx` — `Purchases.logIn(user.id)` on every auth path; `logOut` on sign-out; exposes `purchaseIdentityError` on context (never swallowed).
  - `app/paywall.tsx` — iOS routes CONTINUE through `Purchases.purchasePackage`; web + Android keep Stripe/PayPal/MoMo. iOS gains a Restore Purchases button (Apple requirement). Success/error modal added.
- **Backend**: `POST /api/subscription/rc-sync` mirrors purchases into Mongo `users.tier=premium` + payments row (`provider=revenuecat / method=apple_iap`).
- **Env**: `EXPO_PUBLIC_REVENUECAT_{TEST,IOS,ANDROID}_API_KEY` written to frontend `.env`.
- Backend tests: iteration_34.json — 11/11 pass.
- **Still needed from user for LIVE App Store purchases**: App Store Connect API key (.p8), Google Play service-account JSON, matching IAP products in ASC + Play Console (same product IDs as RevenueCat dashboard). Docs in `/app/memory/revenuecat.md` §"Taking in-app purchases LIVE".

## Still open (from user's 4-item batch)
- 📻 Radio-behind-subscription protection (needs their confirmation on Free vs. Paywalled model)
- 🍎 Apple `.p8` rotation (their previous paste was full plain-text; same content re-sent, NOT rotated)
- ☁️ Cloudflare Stream signed playback (needs Account ID, API token, signing key, subdomain)

## 2026-08-27 — Radio subscription protection (bypass-proof)
- **`/api/radio/now-playing`** now takes optional bearer:
  - Guests / free users → stripped of `streamUrl` + `streamUrlHttps`, returns `requiresSubscription: true`
  - Paid subscribers → full payload + `proxyStreamUrl` (30-min signed) + `requiresSubscription: false`
- **`/api/radio/token`** (auth) → returns short-lived JWT (`pur="radio_stream"`), 30-min TTL. Free users 402.
- **`/api/radio/live?token=<jwt>`** → verifies token AND re-checks live subscription in Mongo → pipes upstream MP3 via httpx StreamingResponse. Missing/invalid/expired → 401. Non-subscriber → 402. Purpose-isolated: session JWTs cannot be reused as radio tokens.
- Upstream: `http://radio.bbkigali.com:8080/stream` (HTTP origin, avoids Cloudflare bot challenge on `stream.bbkigali.com`). Client only sees our HTTPS backend URL — no mixed-content on web.
- Frontend: `player.tsx` uses `proxyStreamUrl` only; UI shows lock + "SUBSCRIBE TO LISTEN" everywhere the play button used to be. Home, mini-player and full player all route to `/paywall` when locked.
- Paywall copy sharpened: **"UNLOCK BB FM KIGALI · Live radio, on-demand shows and premium video — for paying members only."**
- Backend tests: iteration_35.json — **17/17 PASS** including a forged-JWT bypass attempt (rejected 401) and end-to-end proxy streaming ≥8KB of MP3.

## Still open (from user's 4-item batch)
- ☁️ Cloudflare Stream signed playback (need Account ID / API Token / Signing Key ID+JWK PEM / Customer Subdomain)
- 🍎 Apple `.p8` rotation (user re-sent same content — needs actual regeneration in Apple Developer)

## 2026-08-27 — Full Desktop / Web experience
- **DesktopHeader** (`src/components/DesktopHeader.tsx`) — sticky top bar shown ONLY on web ≥ 1024px:
  - Left: B&B brand mark + "BB FM KIGALI · 89.7 FM · #MuriSiporoIgitego"
  - Center: Home / Shows / News / Schedule with active underline
  - Right: red SUBSCRIBE button + LOG IN (or profile chip when authenticated)
- Bottom mobile tab bar auto-hides on wide desktop (`Tabs.tabBarStyle: { display: "none" }`).
- Home page internal header hidden on wide desktop to avoid duplication.
- All routes (home, shows, news, paywall, auth/phone, profile) verified at 1440×900.
- Cross-platform: same backend, DB, RevenueCat entitlement, radio proxy — subscribe on Web → login on iOS/Android → recognised, and vice versa (RevenueCat identity binding + `/subscription/rc-sync` already ensure this).
- Landing page (`/app/landing/index.html`) CTAs point to production `https://radio-vod-platform.emergent.host` — NOT to `app.emergent.sh/share`. The share page only appears when a user opens the preview link; the production URL bypasses it.

## 2026-08-27 — Payment→Access reliability + Terms + Admin PDF + Error 153
### Payment reconciliation safety net
- New `POST /api/subscription/reconcile` (auth). Walks user's non-final payments, verifies each with Stripe/PayPal/BeSoft MoMo, grants tier idempotently if provider confirms paid. Returns fresh user tier.
- `auth.refresh()` in `src/context/auth.tsx` now calls `/subscription/reconcile` BEFORE `/auth/me` on every session-restore — customers who paid-but-lost-callback now land with correct tier on next app open.

### Terms & Conditions gate
- `POST /api/legal/terms/accept` records `terms_acceptances` doc + stamps `users.termsAcceptedAt/Version`. Called from checkout BEFORE payment initiates.
- `GET /api/legal/terms/current` returns `{version, url, privacyUrl}` pointing at `web.bbkigali.com/{terms,privacy}.html`.
- `/auth/me` (UserOut) now exposes `currentPlan`, `provider`, `termsAcceptedAt`, `termsVersion`.
- **Checkout UI**: red-outlined checkbox above PAY button; button label toggles between "ACCEPT TERMS TO PAY" and "PAY X EUR". Explicit plan + amount + expiry-duration shown in the label.

### Admin business reporting
- `GET /api/admin/reports/business.pdf?start=YYYY-MM-DD&end=YYYY-MM-DD` (admin) — full owner PDF with:
  - KPIs: total customers, active/expired subscribers, purchases, tx success/pending/failed, revenue split by currency (EUR + RWF)
  - Revenue rows by day
  - Subscribers table (up to 200)
  - Payments table (last 40, customer-labeled)
- Admin Payments screen now has a new **PDF** button next to CSV. Selects the days-window and downloads the report.

### YouTube Error 153 mitigation
- All YouTube embed URLs now include `enablejsapi=1&origin=https%3A%2F%2Fweb.bbkigali.com` — YouTube treats the embed as first-party, cutting most 153 rejections.
- `/live/session` and `/live/status` return `watchUrl` alongside `embedUrl`.
- Live player (`app/live.tsx`) shows a "WATCH ON YOUTUBE" fallback overlay when the embed fails (WebView `onError`/`onHttpError`).
- **Root cause NOT under our control**: if the video owner explicitly disables embedding on YouTube Studio for a specific stream, Error 153 will still fire. Fallback opens the YouTube app/browser — user still gets to watch, business rule still upheld.

### Production URL update
- `PUBLIC_WEB_URL` env var default = `https://web.bbkigali.com`.
- All 7 landing page URLs migrated from `radio-vod-platform.emergent.host` → `web.bbkigali.com`.
- Terms/Privacy links point at `web.bbkigali.com/terms.html` and `/privacy.html`.

### Backend tests
- Iteration 36: **16/16 pass** after UserOut fix.
