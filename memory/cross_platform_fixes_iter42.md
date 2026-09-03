# Cross-platform Android + subscription fixes (Iter 42)

## What broke
- Android app: hardening pass — RC init could throw at module scope, cascading crashes
- Cross-platform subscribers: web/Android/iOS user rows lived in isolation — someone who paid on the web was asked to pay again on mobile
- Phone matching: `+250 794 230 137` and `250794230137` created **different DB rows**, so admin/subscription lookups missed
- WebView redirect detection: only checked the custom domain `bbkigali.com/paypal/success` — PayPal's own `PayerID=` return path and Stripe's hosted `/checkout/success` were never caught
- YouTube OAuth: `invalid_client` — env vars unset and refresh_token doc cleared

## Backend changes (`/app/backend/server.py` + `.env`)

### 1. Strict E.164 phone canonicalization
`_canonicalize_phone(raw)` now ALWAYS returns `+` + digits:
```
+250 794 230 137  →  +250794230137
250794230137      →  +250794230137
(250)794-230-137  →  +250794230137
00250794230137    →  +250794230137     # strips international "00" prefix
```
Same logic mirrored in the frontend at `src/utils/phone.ts` so both sides agree byte-for-byte.

### 2. Cross-platform account linking (`_find_linked_user_ids`)
New helper finds every user row that shares this user's real-world identity across ANY sign-in method:
- phone
- email (lowercased)
- appleSub
- googleSub

### 3. Reconcile now walks ALL linked users
`POST /api/subscription/reconcile` now:
1. Resolves linked user_ids (phone/email/apple/google)
2. Calls `_reconcile_user_payments()` for each — checks Stripe sessions, PayPal subs, MoMo references
3. Copies the LATEST active subscription from any linked row onto the caller — so a mobile phone-OTP user inherits their web Google-account subscription without paying again
4. Records `linkedFrom: [...uid]` for traceability

### 4. One-time DB backfill
6 user rows + 102 payment rows normalized to E.164 in-place. Existing accounts continue to work; new user with same phone (any format) merges automatically.

### 5. YouTube OAuth env keys added (empty — operator to fill)
```
YOUTUBE_OAUTH_CLIENT_ID=""
YOUTUBE_OAUTH_CLIENT_SECRET=""
```
Redirect URI to configure in Google Cloud Console (BOTH):
- `https://radio-vod-platform.preview.emergentagent.com/api/admin/youtube/callback`
- `https://radio-vod-platform.emergent.host/api/admin/youtube/callback`

DB doc `integration_state.youtube_config` cleared of any legacy token fields (`oauthRefreshToken`, `oauthAccessToken`, `oauthAccessTokenAt`, `connectedAt`). `hasRefreshToken` → `false`.

## Frontend changes

### 1. `src/utils/phone.ts` (new)
`toE164()` + `isLikelyE164()` helpers — used everywhere we send a phone (OTP request, verify, admin panel).

### 2. `app/auth/phone.tsx`
- Uses `toE164(phone)` before calling `requestOtp`
- Uses `isLikelyE164(phone)` for the Continue button gate

### 3. `src/context/auth.tsx`
- `requestOtp` and `verifyOtp` canonicalize with `toE164()` before hitting the API (defense in depth)

### 4. `src/lib/revenuecat.tsx` — Android crash hardening
- `initializeRevenueCat()` NO LONGER THROWS; returns silently on missing keys or SDK init failure
- New module-scope `rcConfigured` flag → all SDK calls (`getCustomerInfo`, `getOfferings`, `purchasePackage`, `restorePurchases`, `logIn`, `addCustomerInfoUpdateListener`) are guarded behind BOTH `rcEnabled` AND `rcConfigured`
- On Android when init fails, the app continues booting — paywall gracefully shows the fallback state

### 5. `app/checkout.tsx` — broadened WebView redirect detection
**PayPal success markers** (any triggers verify):
- `/paypal/success`, `/paypal/return`, `billing/paypal/return`
- `paymentaction=commit`, `checkoutnow?token=`
- `webscr?cmd=_express-checkout`
- `return_from_paypal=1`, `returnurl=`
- `PayerID=` (PayPal's approval redirect param)
- `subscription_id=`

**PayPal cancel markers:** `/paypal/cancel`, `billing/paypal/cancel`, `?cancel=1`, `cancel_return`

**Stripe success markers:**
- `/billing/stripe/return`, `/billing/stripe/success`
- `checkout/success`, `session_id=cs_`, `checkout_status=complete`

**Stripe cancel markers:** `/billing/stripe/cancel`, `?cancel=1`

## Verification (all passing)
- Home renders cleanly on web preview after all changes ✓
- Backend restart no errors ✓
- OTP: `+250 794 230 137` → verify → gets admin JWT ✓
- `/auth/me` returns E.164 phone + admin role + premium tier ✓
- `/subscription/reconcile` checks 22 payments across all linked user IDs and copies active tier ✓
- `hasRefreshToken: false` for YouTube config ✓

## Operator TODO before deploy
1. **YouTube OAuth** — Google Cloud Console → OAuth 2.0 Web Client
   - Copy the client ID into `.env` `YOUTUBE_OAUTH_CLIENT_ID`
   - Copy the client secret into `.env` `YOUTUBE_OAUTH_CLIENT_SECRET`
   - Add BOTH redirect URIs listed above to "Authorized redirect URIs"
   - After deploy, open `/admin/youtube-config` → click "Connect" → complete consent flow
2. **RevenueCat** — grab `sk_...` from RC dashboard and set `REVENUECAT_API_KEY_V1` in `.env` (from Iter 41)
3. **BeSoft** — set `BESOFT_WEBHOOK_SECRET` in `.env` + BeSoft dashboard (from Iter 41)
