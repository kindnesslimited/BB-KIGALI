# BB FM Kigali — /api/admin/* Contract for the Web Agent

**Purpose**: The Web Admin panel must use the **same FastAPI backend + MongoDB** that the Mobile Admin uses. Do NOT build a parallel admin API — every endpoint below is production-ready and already used by the mobile admin. All data (customers, payments, subscriptions, reports) is the same physical MongoDB collection, so mobile admin + web admin always see the same numbers.

Read the general integration contract at `/app/memory/web_agent_integration.md` first — this file focuses on the admin surface only.

## 0 — Base

- **Base URL**: `https://web.bbkigali.com/api` (or preview host during dev).
- **Auth**: `Authorization: Bearer <JWT>` where JWT is issued by `POST /api/auth/otp/verify` for a phone in `ADMIN_PHONES` (users with `role: "admin"`).
- Non-admin caller → **HTTP 403** on every endpoint below.
- Missing/expired token → **HTTP 401**.
- All timestamps are ISO 8601 UTC strings.

To sign in as admin:
```
POST /api/auth/otp/start   { "phone": "+250794230137" }
POST /api/auth/otp/verify  { "phone": "+250794230137", "code": "123456" }
→ { accessToken: "<JWT>", user: { role: "admin", ... } }
```

---

## 1 — Reporting & Analytics (business dashboard)

### 1.1 `GET /admin/analytics/dashboard`
Full KPI snapshot rendered on the admin home. Response:
```json
{
  "generatedAt": "2026-08-30T16:10:56Z",
  "users":         { "total": 36, "admins": 8, "newThisWeek": 11 },
  "subscriptions": { "active": 5, "expired": 0 },
  "revenue": {
    "allTime":     { "RWF": 125000, "EUR": 2.0 },
    "last30Days":  { "RWF": 125000, "EUR": 2.0 },
    "last7Days":   { "RWF": 112000 },
    "today":       {}
  },
  "transactions": {
    "successThisMonth": 38, "pending": 66, "failedThisMonth": 114,
    "breakdownByMethod": [
      { "method": "mtn_momo",  "currency": "RWF", "count": 2,  "amount": 6000 },
      { "method": "stripe",    "currency": "RWF", "count": 7,  "amount": 11000 },
      { "method": "paypal",    "currency": "EUR", "count": 2,  "amount": 2.0 },
      { "method": "apple_iap", "currency": "RWF", "count": 26, "amount": 105000 }
    ]
  }
}
```
✅ Contains **payment-method breakdown** and **per-currency amounts** — no need to compute anything client-side.

### 1.2 `GET /admin/analytics/revenue?granularity=day|week|month&days=30`
Time-series revenue for charts:
```json
[
  { "period": "2026-08-01", "currency": "RWF", "count": 5,  "amount": 15000 },
  { "period": "2026-08-01", "currency": "EUR", "count": 1,  "amount": 3.0 },
  ...
]
```

### 1.3 `GET /admin/analytics/subscriptions?status=active|expired|all`
Full subscriber list:
```json
[
  {
    "id":       "u_...",
    "phone":    "+250...",
    "displayName": "Jane",
    "tier":     "premium",
    "currentPlan": "premium_monthly",
    "subscriptionExpiresAt": "2026-09-27T...",
    "provider": "stripe",
    "status":   "active"
  }
]
```

### 1.4 `GET /admin/payments/summary?days=30`
Aggregated payments overview (used by the mobile Payments screen):
```json
{
  "windowDays": 30,
  "totals": { "success": 38, "pending": 66, "failed": 114, "count": 218 },
  "byMethod": [
    { "method": "mtn_momo",  "count": 103, "revenue": { "RWF": 6000.0 } },
    { "method": "stripe",    "count": 59,  "revenue": { "RWF": 11000.0 } },
    { "method": "paypal",    "count": 30,  "revenue": { "RWF": 3000.0, "EUR": 2.0 } },
    { "method": "apple_iap", "count": 26,  "revenue": { "RWF": 105000.0 } }
  ],
  "totalRevenue": { "RWF": 125000.0, "EUR": 2.0 }
}
```

### 1.5 `GET /admin/payments?days=<n>&status=<s>&method=<m>&plan=<p>&limit=<n>`
Individual payment list with filters:
```json
[
  {
    "id": "pmt_...", "reference": "cs_test_...", "userId": "u_...",
    "phone": "+250...", "method": "stripe", "provider": "stripe",
    "plan": "premium_monthly", "planLabel": "Premium Monthly",
    "amount": 3.0, "currency": "EUR",
    "status": "success",
    "createdAt": "2026-08-01T...", "updatedAt": "..."
  }
]
```
All query params optional; `limit` defaults 200, max 1000.

---

## 2 — Exports

### 2.1 `GET /admin/payments/export.csv?days=<n>&status=<s>`
Returns `text/csv` attachment. Header row:
```
reference,createdAt,userId,phone,method,plan,planLabel,amount,currency,status,failureReason,stripeSessionId,besoftTxId
```

### 2.2 `GET /admin/reports/business.pdf?start=YYYY-MM-DD&end=YYYY-MM-DD`
Returns `application/pdf` attachment. Content:
- KPIs (customers, active/expired subs, purchases, tx success/pending/failed, revenue split by EUR + RWF)
- Revenue by day table
- Subscribers table (up to 200)
- Latest 40 payments (customer-labeled)

Both endpoints send `Content-Disposition: attachment; filename=...` — trigger the browser download in the web UI.

---

## 3 — Customer Management

| Method | Path | Purpose |
|---|---|---|
| GET | `/admin/users?q=<search>` | List users (filter by phone / email / name substring) |
| PATCH | `/admin/users/{id}` | Update `{displayName?, tier?, subscriptionExpiresAt?, phone?, email?}` |
| PUT | `/admin/users/{id}/role` | Change role — body `{ "role": "admin" \| "user" }` |
| POST | `/admin/users/invite` | Invite by phone/email (sends OTP link) |
| POST | `/admin/users/bulk-invite` | Bulk invite — body `{ contacts: [{phone,email?,name?}] }` |
| DELETE | `/admin/users/{id}` | Delete user (also revokes Apple refresh token) |

Grant a complimentary sub without a real payment:
```
PATCH /admin/users/{id}
{ "tier": "premium", "subscriptionExpiresAt": "2027-01-01T00:00:00Z", "currentPlan": "premium_monthly" }
```

---

## 4 — Content Management (Shows / VOD / News / Schedule / Programs / Categories / Live Shows)

| Method | Path | Body / Purpose |
|---|---|---|
| POST/DELETE | `/admin/shows`, `/admin/shows/{id}` | Create / delete VOD show |
| GET | `/admin/programs` | List programs |
| POST/PUT/DELETE | `/admin/programs`, `/admin/programs/{id}` | Program CRUD |
| POST/PATCH/DELETE | `/admin/news`, `/admin/news/{id}` | News CRUD |
| POST/PATCH/DELETE | `/admin/schedule`, `/admin/schedule/{id}` | Schedule CRUD |
| GET | `/admin/live-shows` | List live shows |
| POST/PATCH/DELETE | `/admin/live-shows`, `/admin/live-shows/{id}` | Live show CRUD |
| POST | `/admin/live-shows/{id}/attach-youtube-live` | Bind an active YouTube broadcast |
| POST | `/admin/live-shows/{id}/end` | End a live show |
| POST | `/admin/live-shows/{id}/publish-to-youtube` | Push replay to YouTube |
| POST | `/admin/live-shows/{id}/recording` | Multipart: upload replay video |
| GET | `/admin/categories` | List categories |
| POST/PUT/DELETE | `/admin/categories`, `/admin/categories/{id}` | Category CRUD |

Full request bodies are enforced by Pydantic — the web can call any of these and errors return HTTP 422 with a helpful message. Content changes are immediately visible to mobile + web users via the public `/api/shows`, `/api/news`, etc.

---

## 5 — Media Uploads

| Method | Path | Purpose |
|---|---|---|
| POST | `/admin/uploads/image` | Multipart image → returns hosted URL |
| POST | `/admin/uploads/video` | Multipart video → returns hosted URL |

Files land in Emergent Object Storage — same bucket both admins write to.

---

## 6 — Station Settings

| Method | Path | Purpose |
|---|---|---|
| GET | `/admin/settings` | Full settings object |
| PUT | `/admin/settings` | Update — body accepts: `radioStreamUrl`, `radioStreamUrlHttps`, `youtubeLiveUrl`, `stationName`, `stationTagline`, `frequency`, `logoUrl` |

Slogan is stored here — must be `MURI SPORTS, NI IGITEGO!`.

---

## 7 — YouTube LIVE Integration

| Method | Path | Purpose |
|---|---|---|
| GET | `/admin/youtube/status` | Check OAuth + live-detection state |
| GET | `/admin/youtube/oauth-start` | Begin OAuth (redirects) |
| GET | `/admin/youtube/callback` | OAuth callback (used by Google) |
| GET/PUT | `/admin/youtube/config` | Channel + API keys config |
| POST | `/admin/youtube/sync` | Force-refresh cached live status |

Live detection is fully automatic — the app fetches every 60 s. Web admin can trigger `/sync` for an immediate refresh.

---

## 8 — Cloudflare Stream (private VOD / live)

| Method | Path | Purpose |
|---|---|---|
| GET/PUT | `/admin/cloudflare-stream/config` | Worker URL, secret, subdomain |
| POST | `/admin/cloudflare-stream/live-input` | Create a new RTMP live input |
| GET | `/admin/cloudflare-stream/videos` | List videos on the Stream account |

---

## 9 — Subscription Reminders

| Method | Path | Purpose |
|---|---|---|
| POST | `/admin/subscriptions/send-reminders` | Blast SMS reminders to users whose sub expires in the next 3 days |
| GET | `/admin/subscriptions/reminders?limit=100` | List reminders that have been sent |

---

## 10 — SMS / Notifications

| Method | Path | Purpose |
|---|---|---|
| GET | `/admin/sms/providers` | List enabled providers + status |
| POST | `/admin/sms/test` | Send a test SMS — body `{ "phone": "+250...", "message": "..." }` |
| GET | `/admin/sms/analytics?days=7` | Success / failure rates per provider |

---

## 11 — Audit Trail

| Method | Path | Purpose |
|---|---|---|
| GET | `/admin/audit-log?limit=200&action=<x>&actor_id=<y>` | Every admin action is logged here (grants, refunds, content edits, user deletions) |

---

## 12 — Rules the Web Admin MUST follow

1. **Same source of truth**. Never write directly to MongoDB — always call these endpoints. Every mutation is audit-logged; direct writes are not.
2. **Same JWT**. Do not issue a separate admin auth. Use `POST /api/auth/otp/verify`.
3. **Do NOT duplicate reporting**. All aggregations exist server-side. Web should render, not recompute.
4. **Do NOT introduce currency assumptions**. Amounts are already returned split by currency (RWF, EUR, …). Display them separately or convert client-side using an ECB/BNR rate if needed.
5. **Do NOT persist secrets** in the web bundle. Stripe/PayPal/MoMo secrets, JWT secret, Mongo URL, Cloudflare token all stay in backend `.env`.
6. **Do NOT bypass Terms**. Every payment must go through `POST /api/legal/terms/accept` before the corresponding `POST /api/billing/…/create-*`.
7. **Enforce access via `/api/subscription/reconcile`** on every session refresh so paid-but-lost-callback customers never end up stranded.

---

## 13 — Quick verification

Anyone can copy-paste this to confirm all admin endpoints are alive on the current backend (`localhost:8001`):

```bash
JWT=$(curl -s -X POST http://localhost:8001/api/auth/otp/verify \
       -H 'Content-Type: application/json' \
       -d '{"phone":"+250794230137","code":"123456"}' \
     | python -c "import sys,json;print(json.load(sys.stdin)['accessToken'])")

curl -sH "Authorization: Bearer $JWT" http://localhost:8001/api/admin/analytics/dashboard
curl -sH "Authorization: Bearer $JWT" http://localhost:8001/api/admin/payments/summary?days=30
curl -sH "Authorization: Bearer $JWT" -o report.pdf \
     "http://localhost:8001/api/admin/reports/business.pdf?start=2026-08-01&end=2026-08-31"
```

If any of these return anything other than a 2xx JSON / PDF, the Web agent should NOT ship — file the issue against this backend, not against a new one.


---

## 6 — Admin UI Responsive Requirements

**Reported issue (Sept 2026)**: On phone-sized screens, the admin dashboard charts and cards take up the full viewport and there is no room for navigation — the top nav is cut off, tables overflow horizontally, and no menu is reachable. The mobile shell (native app at `com.bbkigali.fm`) is a fullscreen WebView loading `https://web.bbkigali.com`, so this is 100% a web-side responsive design fix.

The mobile WebView already handles its side of the contract:
- Injects `<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=5.0, user-scalable=yes, viewport-fit=cover">` **before** the site's own `<head>` runs and re-asserts it via `MutationObserver` on every DOM mutation.
- Reserves the notch / status bar height above the WebView so the site's top nav is never physically covered.
- Enables pinch-to-zoom.
- Auto-grants camera + microphone.

The web admin must meet these requirements so the WebView renders correctly:

### 6.1 Breakpoint
Everything below applies at `@media (max-width: 768px)`. Above that, keep the current desktop layout.

### 6.2 Layout — stacked, single column
- All KPI cards and charts stack **vertically, one per row** (`grid-template-columns: 1fr`).
- No horizontal grid columns, no side-by-side charts.
- Card min-height under 768px: max ~200px so multiple cards fit in one viewport scroll.
- Charts: cap height at `200px–240px`, never `100vh` or unconstrained `aspect-ratio`.
- Charts must render at `width: 100%` of their parent card — no fixed pixel widths.

### 6.3 Navigation — collapsible sidebar via hamburger
- The current left sidebar must **hide by default** under 768px (`transform: translateX(-100%)` or `display: none` — off-canvas).
- Add a **hamburger button** in the top-left of the admin header (WCAG-accessible: `<button aria-label="Open menu" aria-expanded="false">`).
- Tapping the hamburger slides the sidebar in as an overlay (`position: fixed; inset: 0 auto 0 0; width: 82vw; max-width: 320px; transform: translateX(0);`).
- A translucent scrim covers the rest of the screen; tapping the scrim closes the sidebar.
- After navigating to a section, close the sidebar automatically.
- Menu items stay full-width, minimum 44px tap target, matching the desktop menu items 1:1 — no hidden sections.

### 6.4 Tables — horizontally scrollable
Payment history, users, subscriptions, audit log, etc. must NOT overflow the viewport.
- Wrap every table in `<div style="overflow-x: auto; -webkit-overflow-scrolling: touch;">`.
- Keep the header row sticky at the top of the scroll container (`position: sticky; top: 0;`) so column meaning is always visible while scrolling horizontally.
- Consider a "card view" fallback for the smallest screens (< 380px) where each row renders as a stacked mini-card of `label: value` pairs — same data, no horizontal scroll needed.

### 6.5 Top-nav / header
- Header height under 768px: fixed 56px (Material-style), sticky at `top: 0`.
- Contents (left → right): hamburger button, BB Kigali logo (compact 32px), spacer, one utility icon max (e.g. sign-out).
- Do NOT stack secondary controls in the header on mobile — move them into the sidebar drawer.

### 6.6 Typography
- Base font-size: 14px on mobile (down from 16px desktop).
- Card titles: 13px, uppercase, letter-spacing 1px.
- Big KPI numbers: `clamp(24px, 6vw, 32px)` — never let them exceed one viewport column.
- Never rely on `-webkit-text-size-adjust: none` — the WebView explicitly overrides it to `100%` for accessibility.

### 6.7 Buttons & inputs
- Minimum touch target 44 × 44 px.
- Filter chips wrap onto multiple rows; never a horizontal scroll strip.
- Date-range picker: use the native `<input type="date">` on mobile so users get the OS picker (much better UX than a custom desktop calendar in a 320px column).

### 6.8 Charts (Recharts / Chart.js / whatever you use)
- Set `<ResponsiveContainer width="100%" height={220}>` — never a fixed pixel width.
- Legend goes BELOW the chart on mobile (`legend={{ position: 'bottom' }}` or equivalent).
- Reduce X-axis tick count so labels don't overlap: `tickCount={4}` under 768px.
- Tooltip should render **inside** the viewport bounds — some libraries need `allowEscapeViewBox={{ x: false, y: false }}`.

### 6.9 Testing checklist for the Web Agent before shipping
Open the admin panel in Chrome DevTools device toolbar at these viewport sizes and confirm each requirement:

| Device                  | Width | Must show                                                                 |
|-------------------------|------:|---------------------------------------------------------------------------|
| iPhone SE               | 375px | Hamburger visible, cards stacked, tables scroll horizontally, no clipping |
| iPhone 15 Pro           | 393px | Same as above                                                             |
| Pixel 8                 | 412px | Same as above                                                             |
| iPad Mini (portrait)    | 768px | Just above the breakpoint — desktop layout kicks in                       |
| Small Android (Nokia 2) | 360px | Everything remains usable, header stays at 56px, KPI numbers don't wrap   |

### 6.10 Non-negotiables
- **Nothing overflows the viewport horizontally.** `body { overflow-x: hidden }` is the mobile WebView's belt-and-suspenders — but the web app must not rely on it. Fix the actual layout.
- **Every admin action must be reachable** without pinch-zoom. Pinch is a bonus for reading fine print, not a required navigation gesture.
- **No fixed viewport heights** (`100vh`) inside admin content — iOS Safari's dynamic toolbar makes those clip.

Once these ship, no mobile-app rebuild is needed — the WebView will render the responsive admin correctly on iOS + Android + desktop web from the same URL.
