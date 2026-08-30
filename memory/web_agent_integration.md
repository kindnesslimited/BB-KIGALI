# BB FM Kigali — Web Agent Integration Guide

**Audience**: the Web agent (or any additional developer) building the desktop web experience.

**Non-negotiable rule**: The **existing FastAPI + MongoDB backend** in `/app/backend/` is the **single source of truth** for customers, payments, subscriptions, content, and reports. Do NOT create a parallel backend or database — the same records must serve Web, Android and iOS.

---

## 1. Backend base URL

| Environment | Base URL |
|---|---|
| Production (custom domain, after user clicks Publish + CNAME) | `https://web.bbkigali.com` |
| Emergent production host | `https://radio-vod-platform.emergent.host` |
| Preview (dev / staging) | `https://radio-vod-platform.preview.emergentagent.com` |

All API routes are prefixed with `/api`. For example, in production a login call is:
```
POST https://web.bbkigali.com/api/auth/otp/start
```

The Web agent must read the base URL from an env var — never hardcode it. Recommended:
```
NEXT_PUBLIC_BB_API_BASE=https://web.bbkigali.com/api
```

---

## 2. Database

- **Single MongoDB instance** used by the FastAPI backend. Web agent must **NOT** connect to it directly — always go through the FastAPI REST API.
- Reason: authorisation, subscription-gating, terms-acceptance logging, audit trail, PDF report generation and SMS receipts all live in the backend. Bypassing it will silently corrupt entitlement state and admin reports.

---

## 3. Auth flow (identical for Web / Android / iOS)

The backend issues a JSON Web Token (JWT) signed with `HS256`. Store it in the browser (`localStorage` or an HTTP-only cookie set by an edge proxy — your call). Send it as `Authorization: Bearer <token>` on every subsequent call.

### Phone OTP (primary method)
```
POST /api/auth/otp/start
Body: { "phone": "+250 794 230 137" }         # any format — spaces/dashes/parens accepted
Resp: { "ok": true, "provider": "whatsapp", "smsSent": true }
      (Also returns `testCode` when phone is on the ADMIN_PHONES allow-list — dev only.)

POST /api/auth/otp/verify
Body: { "phone": "+250 794 230 137", "code": "123456" }
Resp: {
  "accessToken": "<JWT>",
  "user": { id, phone, role, tier, subscriptionExpiresAt, currentPlan, termsAcceptedAt, ... }
}
```
Phone is canonicalised (all non-digit chars stripped, `+` preserved) so all formats are equivalent.

### Google Sign-In (Emergent-managed)
`POST /api/auth/emergent/session` — pass the `session_id` returned by Emergent auth. Same response shape as OTP verify.

### Apple Sign-In
`POST /api/auth/apple/verify` — pass `identityToken`, `authorizationCode`, `email`, `fullName`.

### Session helpers
```
GET   /api/auth/me       # → current user (with tier + expiry + terms)
PATCH /api/auth/me       # update displayName
DELETE /api/auth/me      # deletes account + revokes Apple refresh token
```

---

## 4. Subscription lifecycle

### Fetch available plans
```
GET /api/billing/plans
→ [
  { id: "basic_monthly",   label: "Basic Monthly",   tier: "basic",   amount: 1,  currency: "EUR", days: 30 },
  { id: "basic_yearly",    label: "Basic Yearly",    tier: "basic",   amount: 10, currency: "EUR", days: 365 },
  { id: "premium_monthly", label: "Premium Monthly", tier: "premium", amount: 3,  currency: "EUR", days: 30 },
  { id: "premium_yearly",  label: "Premium Yearly",  tier: "premium", amount: 30, currency: "EUR", days: 365 },
]
```

### Record Terms & Conditions BEFORE payment (mandatory)
```
GET  /api/legal/terms/current   → { version, url, privacyUrl }
POST /api/legal/terms/accept    (auth)
Body: { "version": "2026-08-27", "context": "subscribe" }
```

### Start a payment
| Method | Endpoint |
|---|---|
| Stripe (card / Apple Pay / Google Pay via Stripe Checkout) | `POST /api/billing/stripe/create-checkout` (auth) → `{ sessionId, checkoutUrl }`. Redirect the user to `checkoutUrl`. |
| PayPal (recurring subscription) | `POST /api/billing/paypal/create-subscription` (auth) → `{ subscriptionId: "I-...", approveUrl }`. Redirect to `approveUrl`. |
| MTN MoMo (Rwanda) | `POST /api/billing/momo/initiate` (auth) → `{ reference, status: "pending" }`. Poll `GET /api/billing/momo/{reference}` every 3 s until status is `success` or `failed`. |
| Apple IAP (iOS only, via RevenueCat) | `POST /api/subscription/rc-sync` (auth) → mirrors an iOS RevenueCat purchase into the backend. |

Payload examples:
```
{ "plan": "premium_monthly", "returnUrl": "https://web.bbkigali.com/checkout/success" }   # Stripe / PayPal
{ "plan": "premium_monthly", "phone": "+250 780 111 222" }                                # MoMo
```

### After payment
The backend receives Stripe webhooks (`/api/billing/stripe/webhook`) and PayPal callbacks. It writes:
- `payments` collection — one row per transaction (status: `success` / `failed` / `pending`).
- `users.tier` = `basic` or `premium`.
- `users.subscriptionExpiresAt` = ISO datetime.
- `users.currentPlan` = the plan id.
- `users.provider` = `stripe` / `paypal` / `mtn_momo` / `revenuecat`.

### Safety net — reconciliation
Call this **every time the Web app boots or the user logs in**:
```
POST /api/subscription/reconcile   (auth)
→ { checked: N, granted: [...], user: { tier, subscriptionExpiresAt, currentPlan } }
```
This walks every non-final payment for the user, asks each provider for confirmation, and grants access if any is now paid. Idempotent — safe to call repeatedly. **This is how we guarantee "payment → access" even when a webhook is lost or the browser tab is closed early.**

### Access enforcement
The backend automatically:
- Rejects `/api/radio/token`, `/api/radio/live`, `/api/videos/*/playback`, `/api/live/session` with **HTTP 402** when the caller's subscription has expired.
- Returns `requiresSubscription: true` on `/api/radio/now-playing` and `/api/live/status` when caller is free / expired.
- Tier auto-flips back to `free` on read when `subscriptionExpiresAt` is in the past.

The Web agent must NOT duplicate this logic — always trust the backend response.

---

## 5. Notifications (SMS receipts, WhatsApp OTP, program alerts)

- **OTP**: `POST /auth/otp/start` sends the code (WhatsApp via Nostress API; SMS via Route Mobile).
- **Payment receipt SMS**: fires automatically inside `_send_payment_receipt` after every successful Stripe / PayPal / MoMo / RC-sync grant. Message includes plan label, amount, provider, expiry.
- **Renewal reminders**: `POST /api/admin/subscriptions/send-reminders` (admin) blasts a reminder SMS to users whose subs expire in the next 3 days.
- Same phone number in `users.phone` is used for all — Web signup / mobile signup / MoMo payment must all land on the SAME user record. The canonicalise-phone helper enforces this.

---

## 6. Content (Radio / YouTube / VOD)

### Live radio (always the 24/7 FM stream)
```
GET  /api/radio/now-playing      # metadata; hides streamUrl for non-subscribers
GET  /api/radio/token   (auth)   # premium only → 30-min signed JWT
GET  /api/radio/live?token=<jwt> # streams MP3 through our proxy → prevents URL bypass
```
Upstream: `http://radio.bbkigali.com:8080/stream` (backend pulls this; client never sees it).
HTTPS mirror: `https://stream.bbkigali.com/stream/1/` (also available).

### YouTube LIVE (auto-detected)
```
GET /api/live/status    # public — auto-detects when your channel is live. Returns embedUrl only for paid users.
GET /api/live/session   (auth, premium) → { videoId, embedUrl, watchUrl }
```
No manual toggling — driven by the YouTube Data API v3.

### Shows (VOD)
```
GET /api/shows                          # list. `videoUrl`/`hlsUrl` stripped for free users.
GET /api/shows/{id}                     # detail. Adds `locked: true` + `unlockPrice` for free users.
GET /api/videos/{show_id}/playback (auth, premium OR VOD-owner) → signed Cloudflare Stream iframe URL
```

### News, Programs, Schedule (public)
```
GET /api/news
GET /api/programs
GET /api/radio/schedule
GET /api/categories
GET /api/settings           # station name, tagline, logo, brand palette
```

---

## 7. Admin endpoints (role=admin only — 403 otherwise)

- Dashboard: `GET /api/admin/analytics/dashboard` — KPI cards.
- Subscribers: `GET /api/admin/analytics/subscriptions?status=active|expired|all`
- Revenue: `GET /api/admin/analytics/revenue?granularity=day|week|month`
- Payments: `GET /api/admin/payments`, `GET /api/admin/payments/summary`, `GET /api/admin/payments/export.csv`, `GET /api/admin/reports/business.pdf?start=YYYY-MM-DD&end=YYYY-MM-DD`
- Customers: `GET /api/admin/users`, `PATCH /api/admin/users/{id}`, `DELETE /api/admin/users/{id}`
- Content CMS: `POST/GET/PATCH/DELETE /api/admin/shows|news|programs|schedule|live-shows|categories`
- Settings: `GET/PUT /api/admin/settings` (radio URLs, tagline, logo, YouTube URL, station name, frequency)
- SMS: `GET /api/admin/sms/providers`, `POST /api/admin/sms/test`
- YouTube: `GET /api/admin/youtube/status`, `GET /api/admin/youtube/oauth-start`, `GET /api/admin/youtube/config`
- Audit: `GET /api/admin/audit-log`

**Every action taken through the Web admin will show up in the SAME dashboards and PDF reports the mobile admin sees. There is one Admin — do not build a second.**

---

## 8. Data model at a glance (fields the Web agent will encounter)

```
users {
  id: UUID,
  phone: "+250XXXXXXXXX",   # canonicalised
  email?, displayName?, picture?,
  tier: "free" | "basic" | "premium",
  role: "user" | "admin",
  subscriptionExpiresAt: ISO datetime | null,
  currentPlan: "basic_monthly" | ... | null,
  provider: "stripe" | "paypal" | "mtn_momo" | "revenuecat" | null,
  termsAcceptedAt: ISO | null,
  termsVersion: "2026-08-27" | null,
  appleRefreshToken?: string,   # for Apple Account Deletion
}

payments {
  id: UUID,
  reference: string,          # Stripe session id, PayPal sub id, MoMo tx ref
  userId, phone,
  method: "stripe" | "paypal" | "mtn_momo" | "apple_iap",
  provider: "stripe" | "paypal" | "mtn_momo" | "revenuecat",
  plan, planLabel, amount, currency,
  status: "pending" | "processing" | "success" | "failed",
  stripeSessionId?, besoftTxId?, providerPayload?,
  createdAt, updatedAt,
}

shows { id, title, description, coverImage, videoUrl, hlsUrl,
        cloudflareStreamId?, isPremium, unlockPrice, publishedAt, ... }

schedules { id, title, djName, time, days, coverImage, status, featured }

news { id, title, body, coverImage, sourceUrl, publishedAt, category }

live_shows { id, title, streamKey, status, youtubePublished?, youtubeVideoId? }

terms_acceptances { id, userId, version, context, at }
```

---

## 9. What the Web agent should IMPORT from this project (not rebuild)

| Concern | Source |
|---|---|
| API base URL, auth flow, subscription plans | § 1–4 of this doc |
| Terms of Service HTML | `/app/landing/terms.html` |
| Privacy policy HTML | `/app/landing/privacy.html` |
| Brand colours (Red `#E10600`, Blue `#00A3FF`, Black, White) | `/app/frontend/src/theme.ts` |
| Slogan (must be exact) | `"MURI SPORTS, NI IGITEGO!"` |
| Logo | fetched from `/api/settings.logoUrl` — set once by admin, reused everywhere |

---

## 10. E2E smoke test that MUST pass on the Web build

Run this checklist against the Web app on Chrome / Safari / Edge / Firefox at 1920×1080 AND 1440×900:

1. Register / login by phone OTP → `Authorization: Bearer <JWT>` persists across page reloads.
2. Free user browses home → sees news + schedule but radio/live/VOD show a lock.
3. Free user taps SUBSCRIBE → paywall → picks Premium Monthly → checkbox for Terms → CONTINUE.
4. Pay with **Stripe** (test card `4242 4242 4242 4242 · any future exp · any CVC`) → returns to app → tier flips to premium, expiry set to +30 days.
5. Pay with **PayPal** (sandbox account) → same result.
6. Pay with **MTN MoMo** (`+250 78x xxx xxx` sandbox) → poll succeeds → same result.
7. LISTEN LIVE button now works — MP3 plays through `/api/radio/live?token=…`.
8. LIVE tab: when YouTube is broadcasting, embed loads inside the app.
9. Play a VOD show — signed URL loads from `/api/videos/{id}/playback`.
10. Log out and back in → tier still premium.
11. Force expiry (admin `PATCH /api/admin/users/{id}` with `subscriptionExpiresAt: <past>`) → radio/live/VOD immediately locked on refresh.
12. Renew payment → access restored.
13. Admin dashboard shows the new customer + payment identical to what a mobile admin sees.

---

## 11. Environment variables the Web agent needs

| Var | Value | Purpose |
|---|---|---|
| `NEXT_PUBLIC_BB_API_BASE` (or equivalent) | `https://web.bbkigali.com/api` | All API calls |
| `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY` | (fetch dynamically from `GET /api/billing/stripe/config`) | Stripe.js on the web |
| `NEXT_PUBLIC_PAYPAL_CLIENT_ID` | (fetch dynamically from `GET /api/billing/paypal/config`) | PayPal SDK |

The Web agent should never receive any SECRET keys (Stripe secret, PayPal secret, MoMo secret, MongoDB URI, JWT secret). Those stay in the backend `.env` only.

---

## 12. Contact points

- Payment webhooks — already wired: `/api/billing/stripe/webhook`, PayPal via `_paypal_verify_and_grant`, MoMo via poll.
- Anything the Web agent needs added to the API: file a request describing the endpoint contract and this project's owner will add it here (never in a separate service).

**Any deviation from this document risks fracturing customer accounts across systems. Please treat it as the contract.**
