# BB Kigali — Rebuild Reference for `vod-platform-access`

**Purpose**: This document is the **single source of truth for functional requirements + integration knowledge + known pitfalls** extracted from `radio-vod-platform` (the old build). It exists so the new independent BB Kigali platform can be rebuilt in `vod-platform-access` without forgetting anything and without depending on the old system at runtime.

> **Rule**: use this only as *reference*. Do **not** import the old architecture just because it exists. Rebuild cleanly.

**Prepared**: 2026-09-06
**Old system status**: FROZEN. Kept online only as a live reference/backup until the new platform is approved by the owner.
**Owner directive**: "BB Kigali must work fully with `radio-vod-platform` completely unavailable."

---

## 1. Product vision (non-negotiable)

BB Kigali FM is a Rwanda-based media platform:
- **24/7 live radio** (Icecast/HTTPS stream)
- **Live TV shows** (YouTube Live simulcast + Cloudflare Stream private live)
- **Video-on-demand (VOD)** — free clips + paid premium episodes
- **News + programs + schedule** (CMS-driven)
- **Subscription paywall** for premium content (monthly/yearly, multi-currency)
- **Per-episode VOD purchases** (one-off) as an alternative to subscription
- **Multi-region payments**: Stripe (cards, global), PayPal (global), MTN MoMo via **BeSoft** (Rwanda), Apple IAP via **RevenueCat** (iOS)
- **Native iOS + Android apps** + fully responsive Web

Target audience: Rwandan diaspora + Rwanda local, plus East African listeners. Currencies used: **RWF** (local) and **EUR/USD** (diaspora).

---

## 2. User roles

| Role | Access |
|---|---|
| `guest` | Public content only (radio stream, free clips, news, schedule) |
| `user` (free) | Everything a guest has + account, billing history, receipts, VOD ownership |
| `user` with active `tier=basic|premium` | + premium VOD, live TV shows, ad-free experience |
| `admin` | Full CMS + user management + payments + integrations dashboards |

**Subscription tiers** currently in use:
- `free` (default)
- `basic` (monthly/yearly)
- `premium` (monthly/yearly) — full catalog + live TV

Field on user document: `tier`, `subscriptionExpiresAt`, `subscriptionSource` (`stripe|paypal|momo|apple|admin`).

---

## 3. Feature checklist (must exist in new system)

### 3.1 Auth
- [ ] Phone-based OTP registration/login (Rwanda + international phone numbers)
- [ ] SMS OTP via primary provider (Route Mobile) + **automatic WhatsApp fallback** when SMS fails
- [ ] Email OTP as alternate channel (optional but recommended)
- [ ] "Sign in with Apple" (required for iOS App Store approval when other auth methods exist)
- [ ] Admin login (phone OTP + admin allowlist by phone/email)
- [ ] JWT-based session tokens (short-lived access + longer refresh, or single long-lived JWT — current uses long-lived)
- [ ] OTP rate limiting: max 5 attempts per code, max N sends per phone per hour, code TTL 5 min
- [ ] Account deletion endpoint (required by Apple + Play Store)
- [ ] Terms & Conditions acceptance recorded per user (required for App Store)

### 3.2 Radio
- [ ] Play/pause 24/7 Icecast stream (proxy URL for HTTPS)
- [ ] Now-playing metadata endpoint (song title + artist from Icecast `/status-json.xsl`)
- [ ] Schedule endpoint (weekly programming grid, admin-editable)
- [ ] Listen count aggregation (per session, for analytics)

### 3.3 Live TV
- [ ] Detect when configured YouTube channels are LIVE right now (**zero-quota HTML probe** — see §7.2)
- [ ] Multi-channel monitoring (currently 3 channels: BB Kigali FM, sister channels)
- [ ] Auto-attach live show record to detected YouTube live for playback
- [ ] Optional private live via Cloudflare Stream Live Input (signed playback URL, subscriber-gated)
- [ ] Recording of live show → VOD after end

### 3.4 VOD
- [ ] Video catalog (shows) with categories, thumbnails, descriptions, duration, publish date
- [ ] Cloudflare Stream signed URLs for premium videos (short-lived, subscriber-only)
- [ ] Free preview clips (open playback)
- [ ] Per-episode purchase (`vod_purchases` collection)
- [ ] YouTube video sync (import public videos from configured channels as VOD entries automatically)

### 3.5 CMS (admin)
- [ ] Programs (recurring shows: title, host, description, image)
- [ ] Live-shows (scheduled/one-off live broadcasts)
- [ ] News articles (title, body, image, publish date, category)
- [ ] Schedule (weekly grid: day + start + end + program_id)
- [ ] Categories (video/news taxonomy)
- [ ] Settings (site name, contact, social links, radio stream URL)
- [ ] Image uploads (thumbnails, hero images) — Object Storage
- [ ] Video uploads (direct-to-Cloudflare-Stream via one-time upload URL, no server passthrough)

### 3.6 Payments & subscriptions
- [ ] Stripe Checkout (card) — recurring subscription
- [ ] Stripe webhook receiver for lifecycle events (activated/cancelled/failed/renewed)
- [ ] PayPal Subscriptions API — recurring subscription with hosted approval URL
- [ ] PayPal webhook receiver + a "reconcile stranded" cron for approvals that never posted a webhook
- [ ] MTN MoMo via **BeSoft** (Rwanda mobile money) — request-to-pay flow, callback URL, HMAC-verified webhook
- [ ] Apple IAP via **RevenueCat** — webhook receiver + receipt verification
- [ ] Cross-platform subscription linking: a user who paid on web with the same phone/email must be recognised as premium on mobile automatically
- [ ] Billing history per user (payments collection scan)
- [ ] Receipt PDF/email endpoint
- [ ] Free-trial support (optional, currently disabled)
- [ ] Subscription reminder emails (7 days before expiry) — background job
- [ ] Admin can grant a subscription manually (admin action, audit-logged)

### 3.7 Notifications
- [ ] Transactional SMS (OTP, payment confirmation)
- [ ] Transactional WhatsApp fallback
- [ ] Transactional email (via Emergent-managed Resend or self-hosted SMTP)
- [ ] Push notifications (Emergent-managed) — **optional**, only if owner requests

### 3.8 Admin dashboards
- [ ] Analytics: DAU, subscriptions active/new/cancelled, revenue by provider/currency, radio listens, live viewers
- [ ] User list with search/filter, role edit, subscription edit
- [ ] Payments list with filter by provider/status/date
- [ ] Audit log viewer (every admin action logged)
- [ ] SMS analytics (delivery/failure per provider)
- [ ] YouTube integration status (connected channels, token expiry, last sync)

### 3.9 Legal / store requirements
- [ ] Terms & Conditions page (versioned, acceptance tracked)
- [ ] Privacy Policy page
- [ ] Account deletion self-service
- [ ] Data export request (GDPR)
- [ ] Native Terms screen inside the mobile app (offline-visible before login) — App Store rejects if only web
- [ ] Screen-recording/capture protection **on iOS only** (see §11 gotcha)

### 3.10 Security
- [ ] All admin routes require role check
- [ ] Rate limiting on OTP, login, payment initiation
- [ ] Webhook signature validation on ALL 4 payment providers
- [ ] Secrets in env only, never in code, never in frontend bundle
- [ ] Audit log on every state-changing admin action
- [ ] CORS locked to known origins in production

---

## 4. Data model (24 collections from the old system — for reference, redesign as needed)

| Collection | Purpose | Notable fields |
|---|---|---|
| `users` | Accounts | `id, phone, email, role, tier, subscriptionExpiresAt, subscriptionSource, linkedFrom, createdAt, disabled` |
| `otp_challenges` | Active OTP codes | `phone, codeHash, attempts, expiresAt, deliveredVia` |
| `user_sessions` | Refresh sessions | `userId, jti, expiresAt, revoked` |
| `terms_acceptances` | Legal | `userId, termsVersion, acceptedAt, ip` |
| `payments` | All payment attempts (all providers) | `id, userId, phone, email, provider, providerRef, plan, amount, currency, status, raw` |
| `paypal_plans` | PayPal plan-id cache per (tier×billing_cycle) | `plan, cycle, planId` |
| `stripe_events` | Idempotency store | `eventId, processedAt` |
| `rc_events` | RevenueCat webhook log | `eventId, appUserId, productId, raw` |
| `subscription_reminders` | Sent reminder tracking | `userId, expiresAt, sentAt` |
| `vod_purchases` | Per-episode purchases | `userId, showId, provider, amount, currency, status, purchasedAt` |
| `shows` | VOD catalog | `id, title, description, categoryId, thumbnailUrl, videoId, cloudflareUid, duration, isPremium, price, publishedAt` |
| `live_shows` | Scheduled live broadcasts | `id, title, scheduledAt, endedAt, youtubeVideoId, cloudflareLiveInputUid, recordingUid` |
| `programs` | Recurring shows | `id, title, host, description, imageUrl` |
| `schedule` | Weekly grid | `id, day, startTime, endTime, programId` |
| `news` | Articles | `id, title, body, imageUrl, publishedAt, categoryId` |
| `categories` | Taxonomy | `id, name, kind (video|news)` |
| `settings` | Site config | `key, value` (single-doc pattern) |
| `radio_state` | Now-playing cache | `title, artist, updatedAt` |
| `radio_listens` | Listen sessions | `userId?, sessionId, startedAt, endedAt` |
| `uploads` | Object Storage metadata | `id, userId, key, url, mime, sizeBytes` |
| `sms_deliveries` | SMS/WhatsApp send log | `phone, provider, status, providerRef, cost, sentAt` |
| `audit_log` | Admin actions | `userId, action, target, before, after, ip, at` |
| `integration_state` | Third-party runtime state | `key (e.g., "youtube_config"), value` |
| `command` | (Legacy, safe to drop) | Command queue for background jobs |

---

## 5. External integrations — accounts, keys, and gotchas

### 5.1 Stripe (cards, global)
- **What**: Recurring subscriptions via Checkout, one-off VOD via Payment Intents
- **Owner has account**: Yes
- **Env vars**: `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_CURRENCY`
- **Webhook URL to register in Stripe dashboard**: `https://<new-api>/api/billing/stripe/webhook`
- **Emergent template note**: Emergent provides a **test Stripe key** in the pod env — use it in dev, use owner's live key in prod
- **Gotcha**: Idempotency via `stripe_events` collection is required — Stripe retries webhooks aggressively
- **Emergent library**: `emergentintegrations.payments.stripe.checkout` (server-side SDK, no need for raw Stripe SDK)

### 5.2 PayPal (global)
- **What**: Recurring subscriptions via Subscriptions API
- **Env vars**: `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, `PAYPAL_ENV` (`sandbox|live`), `PAYPAL_CURRENCY`, `PAYPAL_WEBHOOK_ID`, `PAYPAL_RETURN_URL`, `PAYPAL_CANCEL_URL`, and 4 plan IDs (`PAYPAL_PRICE_BASIC_MONTHLY`, `_YEARLY`, `PREMIUM_MONTHLY`, `_YEARLY`)
- **Webhook URL**: `https://<new-api>/api/billing/paypal/webhook`
- **Gotcha**: PayPal is **known to drop webhooks** after user approval. Solution used: a background "reconcile-stranded" job that polls `GET /v1/billing/subscriptions/{id}` for any payments in `pending_approval` older than 5 min. Rebuild this.
- **Gotcha 2**: Plan IDs are per-currency. If you support both RWF and USD you need 8 plan IDs.

### 5.3 MTN MoMo via BeSoft (Rwanda)
- **What**: Request-to-pay for Rwandan users (mobile money)
- **Provider**: BeSoft (aggregator on top of MTN MoMo API)
- **Env vars**: `BESOFT_API_KEY`, `BESOFT_API_SECRET`, `BESOFT_BASE_URL`, `BESOFT_PAYOUT_MSISDN`, `BESOFT_WEBHOOK_SECRET`, `BESOFT_VERIFY_SSL`
- **Callback URL**: `https://<new-api>/api/billing/momo/callback`
- **Gotcha**: BeSoft webhook is HMAC-signed with `BESOFT_WEBHOOK_SECRET` in header `X-Signature` — **must be verified** or payments can be spoofed. This was flagged in a security audit (SEC-003).
- **Gotcha 2**: MTN sometimes doesn't callback. Poll `GET /transaction/{ref}` every 10s for up to 2 min after initiation, then mark as `pending_manual_review`.

### 5.4 RevenueCat + Apple IAP (iOS only)
- **What**: Apple mandates that iOS-purchased subscriptions go through IAP. RevenueCat is the wrapper.
- **Env vars**: `REVENUECAT_WEBHOOK_SECRET` (+ RevenueCat public SDK key on client)
- **Webhook URL**: `https://<new-api>/api/webhooks/revenuecat` (or `/api/billing/rc-webhook`)
- **Gotcha**: `RC-Signature` header verification is required (SEC-002 in old audit). Do not accept unsigned webhooks.
- **Gotcha 2**: RevenueCat App User ID **must equal** your internal user id, not the Apple ID. Set it via `Purchases.logIn(userId)` on the mobile client.
- **Owner action**: In new project, create a new RevenueCat "app" (separate from old one) so old app doesn't affect new one.

### 5.5 Cloudflare Stream (video hosting + live)
- **What**: Hosts all premium VOD + optional private live simulcast
- **Env vars**: `CLOUDFLARE_STREAM_SUBDOMAIN`, `CLOUDFLARE_STREAM_WORKER_URL`, `CLOUDFLARE_STREAM_WORKER_SECRET`
- **Architecture used**: A Cloudflare Worker signs HLS URLs on the server's behalf with a shared secret (so the API token doesn't leave the Worker). This is a nice pattern — recommend keeping.
- **Gotcha**: Signed URLs expire fast (5–15 min). Refresh on client via a re-fetch endpoint.
- **Direct-upload flow**: Server calls Cloudflare API for a one-time upload URL, returns to browser, browser uploads directly. Do NOT proxy video bytes through your backend.

### 5.6 YouTube Data API v3 + OAuth
- **What**: (a) live-detection, (b) auto-import public videos as VOD, (c) publish uploaded videos to YouTube
- **Env vars**: `YOUTUBE_API_KEY` (quota-limited public reads), `YOUTUBE_OAUTH_CLIENT_ID`, `YOUTUBE_OAUTH_CLIENT_SECRET`, `YOUTUBE_HANDLE`, `YOUTUBE_EXTRA_HANDLES` (comma-separated for the 3-channel monitor)
- **Owner action**: Create OAuth client in Google Cloud Console with redirect `https://<new-api>/api/admin/youtube/callback`
- **Gotcha (critical)**: YouTube Data API `search` costs **100 quota units per call**, meaning ~3 hours of live-detection can burn the entire daily 10,000-unit quota. Solution used: **zero-quota HTML probe** — fetch `https://www.youtube.com/@{handle}/live` and parse `"isLiveNow":true` from the HTML. This is the ONLY viable approach for multi-channel monitoring. See `/app/backend/youtube_live.py` in old codebase as reference.
- Refresh token is stored in `integration_state.youtube_config` — encrypted at rest recommended.

### 5.7 SMS providers
- **Primary**: Route Mobile (best RW deliverability). Env: `SMS_API_URL`, `SMS_USERNAME`, `SMS_PASSWORD`, `SMS_SENDER_ID`, `SMS_VERIFY_SSL`
- **Fallback 1**: Africa's Talking. Env: `AT_API_KEY`, `AT_USERNAME`, `AT_SENDER_ID`
- **Fallback 2**: Twilio. Env: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM`
- **Fallback 3**: WhatsApp Business API. Env: `WHATSAPP_API_URL`, `WHATSAPP_API_TOKEN`, `WHATSAPP_SESSION_ID`
- **Provider order**: `SMS_PROVIDER_ORDER=routemobile,at,twilio,whatsapp` (comma-separated). Try in order until one returns success.
- **Dev mode**: `SMS_DEV_RETURN_CODE=true` returns the OTP in the API response for local testing. **Never enable in prod.**

### 5.8 Apple "Sign in with Apple"
- **Env vars**: `APPLE_CLIENT_ID`, `APPLE_TEAM_ID`, `APPLE_KEY_ID`, `APPLE_PRIVATE_KEY` (multi-line PEM), `APPLE_AUDIENCES`
- **Required for App Store approval** if you offer any other social login. If you only have phone OTP, technically optional but strongly recommended.

### 5.9 Object Storage (uploads)
- **Use Emergent Managed Object Storage** (default) — the integration expert has a playbook. No user credentials needed.
- Store: user-uploaded avatars, admin-uploaded thumbnails/hero images, invoice PDFs.
- **Do not** store base64 blobs in MongoDB — the old system used object storage properly, keep this pattern.

### 5.10 Email (transactional)
- **Recommended**: Emergent-managed Resend integration (no keys required)
- Templates needed: OTP, payment success, payment failed, subscription expiring (7-day reminder), subscription cancelled, welcome, account deletion confirmed

---

## 6. Auth flow specifics (learned the hard way)

### 6.1 OTP flow
```
POST /auth/otp/start { phone }
  → normalizes phone (E.164, defaults to +250 for RW)
  → generates 6-digit code
  → hashes code (bcrypt or scrypt)
  → stores in otp_challenges with 5-min TTL
  → sends via SMS_PROVIDER_ORDER, first success wins
  → returns { challengeId, deliveredVia }
  → if SMS fails, WhatsApp fallback kicks in automatically

POST /auth/otp/verify { challengeId, code }
  → checks attempts < OTP_MAX_ATTEMPTS (default 5)
  → checks not expired
  → compares hash
  → on success: creates/updates user, issues JWT
  → on failure: increments attempts; after max, invalidates challenge
```

**Static test account convention** (must exist in new system too, or Apple review reviewers can't log in):
- Phone: `+250794230137`
- Fixed OTP: `123456`
- Auto-granted: `role=admin, tier=premium`
- The OTP verify handler special-cases this phone (bypass hash compare) so App Store reviewers can log in without receiving an SMS.

### 6.2 Cross-platform subscription linking
When a user logs in via mobile, scan `payments` collection for **any** record matching `phone` OR `email` OR user's linked email/phone from the same account. If a valid non-expired subscription is found under any of those identifiers, grant the user `tier=premium` on the current login. This is critical because users often pay on the web with email and later log in on mobile with phone.

---

## 7. Live TV specifics

### 7.1 Which channels to monitor
Stored in `integration_state.youtube_channels` — list of `{ handle, name, priority }`. Currently 3 channels. Admin UI must let owner add/remove.

### 7.2 Zero-quota live probe
```
For each channel:
  fetch https://www.youtube.com/@{handle}/live  (no API key)
  if "isLiveNow":true in HTML → channel is LIVE
  extract videoId from response
Cache result for 60s to avoid hammering YouTube
Run loop every 60s in background
```
Fallback to `search.list?eventType=live` (paid quota) only if the HTML probe fails 3 times in a row.

Full working implementation exists at `/app/backend/youtube_live.py` — study it but rewrite cleanly.

### 7.3 Private live (Cloudflare Stream)
Optional. When admin wants a live show that is NOT on YouTube:
1. Admin clicks "Start live"
2. Backend calls Cloudflare API → creates a **Live Input** → returns RTMP push URL + stream key
3. Admin uses OBS/similar to push
4. Playback URL is signed per-user, subscriber-only
5. On "End live", auto-save recording UID to `live_shows.recordingUid`

---

## 8. Mobile app requirements (learned from App Store + Play Store review)

### 8.1 Store non-negotiables
- **App Store**:
  - "Sign in with Apple" if any other social login exists
  - Account deletion in-app (not "email us")
  - Native Terms + Privacy screens (must render offline)
  - No external payment links for digital goods (must use IAP → RevenueCat)
  - Purpose strings for permissions must clearly state user benefit (see `app.json` in old codebase)
- **Play Store**:
  - Data safety form filled out truthfully
  - Content rating done
  - Account deletion works
  - Target latest API level

### 8.2 iOS gotcha: FLAG_SECURE / screen-capture protection
- On iOS, native screen blanking during subscriber video playback is **safe** and recommended.
- On Android, do **NOT** apply `FLAG_SECURE` when playing HTML5 `<video>` in a WebView. It breaks `SurfaceView` allocation and causes an infinite loading spinner. This was a real bug in Iter 44.

### 8.3 Suggested mobile architecture (open decision)
Old system converted the mobile app to a thin WebView wrapper (Iter 44) because the web app was already complete. For a clean rebuild the choices are:

| Option | Pros | Cons |
|---|---|---|
| **Full native React Native** | Best UX, best App Store approval odds, offline support, native player controls | 2× dev effort, need to duplicate every screen |
| **WebView wrapper** | 1× dev effort, always in sync with web | Apple sometimes rejects thin wrappers ("Guideline 4.2 — minimum functionality"), harder to use native features |
| **Hybrid**: native shell for auth/payment/player, WebView for CMS content | Best of both, App Store safe | More complex |

Recommend **Option 3 (Hybrid)** for the rebuild. Native for anything Apple cares about (auth, IAP, player), WebView for content pages (news, schedule, program info).

### 8.4 Required native screens (offline)
- Splash
- Onboarding
- Login (phone OTP)
- Terms + Privacy (both accessible before login, offline-renderable)
- Account deletion
- Subscription paywall (with correct pricing per platform — Apple takes 30%, so iOS price ≠ web price)

---

## 9. Environment variables (full list, no values)

Group these in the new project's `.env` (backend) or vault:

**Runtime**: `APP_ENV`, `PUBLIC_BASE_URL`, `PUBLIC_WEB_URL`, `CORS_ALLOWED_ORIGINS`
**Database**: `MONGO_URL`, `DB_NAME`
**Auth**: `JWT_SECRET`, `OTP_MAX_ATTEMPTS`, `OTP_TTL_SECONDS`, `ADMIN_EMAILS`, `ADMIN_PHONES`
**Apple**: `APPLE_CLIENT_ID`, `APPLE_TEAM_ID`, `APPLE_KEY_ID`, `APPLE_PRIVATE_KEY`, `APPLE_AUDIENCES`
**Stripe**: `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_CURRENCY`
**PayPal**: `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, `PAYPAL_ENV`, `PAYPAL_CURRENCY`, `PAYPAL_WEBHOOK_ID`, `PAYPAL_RETURN_URL`, `PAYPAL_CANCEL_URL`, `PAYPAL_PRICE_BASIC_MONTHLY`, `PAYPAL_PRICE_BASIC_YEARLY`, `PAYPAL_PRICE_PREMIUM_MONTHLY`, `PAYPAL_PRICE_PREMIUM_YEARLY`
**BeSoft (MoMo)**: `BESOFT_API_KEY`, `BESOFT_API_SECRET`, `BESOFT_BASE_URL`, `BESOFT_PAYOUT_MSISDN`, `BESOFT_WEBHOOK_SECRET`, `BESOFT_VERIFY_SSL`
**RevenueCat**: `REVENUECAT_WEBHOOK_SECRET`
**Cloudflare Stream**: `CLOUDFLARE_STREAM_SUBDOMAIN`, `CLOUDFLARE_STREAM_WORKER_URL`, `CLOUDFLARE_STREAM_WORKER_SECRET`
**Radio**: `RADIO_STREAM_URL_HTTPS`
**YouTube**: `YOUTUBE_API_KEY`, `YOUTUBE_OAUTH_CLIENT_ID`, `YOUTUBE_OAUTH_CLIENT_SECRET`, `YOUTUBE_HANDLE`, `YOUTUBE_EXTRA_HANDLES`
**SMS**: `SMS_API_URL`, `SMS_USERNAME`, `SMS_PASSWORD`, `SMS_SENDER_ID`, `SMS_VERIFY_SSL`, `SMS_PROVIDER_ORDER`, `SMS_DEV_RETURN_CODE`
**Africa's Talking**: `AT_API_KEY`, `AT_USERNAME`, `AT_SENDER_ID`
**Twilio**: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM`
**WhatsApp**: `WHATSAPP_API_URL`, `WHATSAPP_API_TOKEN`, `WHATSAPP_SESSION_ID`
**Pricing (VOD one-off)**: `VOD_PRICE_EUR`, `VOD_PRICE_RWF`
**Emergent (LLM/integrations)**: `EMERGENT_LLM_KEY` (already provided by platform)

> **Do NOT copy any values from the old `.env` into chat or code.** In the new workspace, either recreate accounts (recommended, clean start) or ask the owner to paste each value into the new project's Secrets tab directly.

---

## 10. Security audit fixes to preserve

Old system went through a security audit. These fixes MUST be applied in the new build from day 1 (not as afterthoughts):

- **SEC-001**: Admin OTP hardening — admin login uses a dedicated OTP challenge with shorter TTL, no static bypass in prod
- **SEC-002**: RevenueCat receipt HMAC verification on every webhook
- **SEC-003**: BeSoft webhook HMAC verification (`X-Signature` header)
- **SEC-004**: OTP rate limits — max sends per phone per hour, max attempts per code
- **SEC-005**: Stripe webhook signature verification (already done by Emergent SDK, do not disable)
- **CORS**: locked to production origins only
- **Password/JWT**: never log JWT contents; short-lived if possible
- **Audit log**: every admin action must append an audit_log entry

---

## 11. Test flow checklist (must pass before "go live")

### End-user
1. Register with phone → receive OTP → verify → get JWT
2. Browse free content (radio, news, free clips) without paying
3. Try to play premium clip → paywall
4. Subscribe via Stripe (test card) → webhook activates → premium unlocked
5. Log out, log back in → still premium (JWT + DB check)
6. Subscribe via PayPal → same result
7. Subscribe via MoMo (BeSoft sandbox) → same result
8. On iOS app, subscribe via IAP → RevenueCat webhook → same result
9. Cancel subscription → still active until period end → auto-lock after expiry
10. Renew → back to active
11. Buy single episode via VOD flow → can watch that episode after expiry
12. Delete account → all data anonymised

### Cross-platform
13. Pay on web with email `x@x.com` → open mobile → login with linked phone → premium recognised
14. Sign in with Apple on iOS → same account visible on web after linking email

### Admin
15. Log in as admin → see dashboard
16. Add a program, upload thumbnail
17. Upload a video → appears in catalog
18. Start a live show → auto-attach detected YouTube live
19. Send bulk invite to 10 phones
20. Grant subscription manually to a user
21. See revenue chart update after test payment
22. See audit log entry for every admin action

### Live
23. YouTube goes live → detected within 90s → home page shows LIVE badge
24. YouTube goes offline → LIVE badge cleared within 90s
25. Radio stream plays continuously for 10+ min without dropping

---

## 12. Suggested new architecture (recommendation, not a mandate)

For the rebuild I recommend:

- **Backend**: FastAPI (proven) OR NestJS/Node if the vod-platform-access team prefers TypeScript end-to-end. Keep it modular this time — split into `auth/`, `billing/`, `content/`, `live/`, `admin/`, `webhooks/`, `integrations/`. The old system's 246 KB `server.py` is a maintenance liability.
- **Database**: MongoDB (existing team knowledge) OR Postgres (better for financial data). Payments are relational-shaped; Postgres would be cleaner.
- **Web**: Next.js (SSR-friendly, good SEO for news content)
- **Admin**: Same Next.js app under `/admin` with role gate, OR a separate mini-app
- **Mobile**: Expo (React Native) — hybrid pattern as described in §8.3
- **Object storage**: Emergent-managed
- **Deployment**: Emergent publish button (recommended path)
- **DNS**: One custom domain per environment (`api.bbkigali.com`, `web.bbkigali.com`, `admin.bbkigali.com`)

---

## 13. Files in old workspace worth reading (reference only)

Located at `/app/backend/` and `/app/frontend/` in `radio-vod-platform`:

| File | Why read it |
|---|---|
| `backend/server.py` (246 KB) | All 115 endpoints, all payment webhook handlers, all admin routes — search for `router.post("/billing/`, etc. Use as functional reference, not architectural |
| `backend/youtube_live.py` | Working zero-quota multi-channel probe |
| `backend/cloudflare_stream.py` | Working Cloudflare Worker signed-URL pattern |
| `backend/admin_analytics.py` | Revenue/subscriber aggregation queries |
| `backend/apple_auth.py` | Sign in with Apple JWT verification |
| `backend/subscription_reminders.py` | Background job pattern |
| `frontend/app/index.tsx` | Old WebView wrapper (skip if going native) |
| `frontend/app/terms.tsx` | Native Terms screen — required by App Store |
| `memory/web_admin_api_contract.md` | Full API spec of the old backend (endpoint-by-endpoint) — most detailed reference doc |
| `memory/payment_policy_per_platform.md` | Which payment method is allowed on which platform (Apple 30%, Play 15%, etc.) |
| `memory/revenuecat.md` | RevenueCat integration notes |
| `memory/app_store_review_notes.md` | What Apple reviewers complained about last time |
| `memory/security_fixes_iter41.md` | The 5 SEC-fixes in detail |
| `memory/multi_channel_live_iter47.md` | Why HTML probing is the only viable YouTube live approach |

---

## 14. Test credentials to seed in new database

Must exist for App/Play Store reviewers + owner testing:

| Purpose | Phone | Password / OTP | Role | Tier |
|---|---|---|---|---|
| Store reviewer / owner | `+250794230137` | Fixed OTP `123456` (dev bypass) | `admin` | `premium` |
| Regular test user | `+250788123456` | Standard OTP flow | `user` | `free` |

Convention: **any phone number ending in `230137` bypasses OTP and gets premium** — makes reviewer testing painless. Document this in `/app/memory/test_credentials.md` in the new project.

---

## 15. Owner actions during rebuild (checklist for vod-platform-access agent)

Ask the owner to do these while you build:

1. **Create fresh integration accounts** (recommended over reusing old ones):
   - New Stripe restricted key scoped to the new backend
   - New PayPal app (sandbox first, live later)
   - New BeSoft merchant credentials (or keep existing — ask owner)
   - New RevenueCat project
   - New Cloudflare Stream account or same one, but new API token
   - New Google Cloud OAuth client (redirect URI on new API domain)
2. **DNS**: point `api.bbkigali.com`, `web.bbkigali.com`, `admin.bbkigali.com` to new deploy
3. **App Store**: create new App ID or migrate old one (ask Apple — usually not needed if bundle ID stays the same)
4. **Play Store**: same — new app record OR reuse
5. **Sender ID approval**: Route Mobile sender ID `BBKIGALI` needs approval per country; may take days

---

## 16. Acceptance criteria (owner's final ask)

> "BB Kigali must work fully with `radio-vod-platform` completely unavailable."

Concretely: shut down the old backend, wait 5 min, and confirm:
- Web app loads and functions completely
- Mobile app loads and functions completely
- Users can register, log in, subscribe, and watch premium content
- Payments succeed on all 4 providers
- All webhooks flow into the new backend
- Admin dashboard fully operational

Only then declare Phase 7 complete.

---

## 17. Contact / handoff notes

- Old backend runtime: kept alive as reference until owner explicitly says "kill it"
- Old backend `.env` values: DO NOT copy blindly. Recreate cleanly in new project. Owner will provide fresh credentials.
- Old MongoDB: no production customer data (owner confirmed). Do not migrate. Start fresh.
- Old mobile app builds: continue to exist on TestFlight/Play internal testing but stop distributing once new app is submitted.

**End of reference document.**
