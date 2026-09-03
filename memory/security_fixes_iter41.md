# Security fixes applied — Iter 41 (from audit report)

| ID | Severity | Title | Status |
|---|---|---|---|
| SEC-001 | 🔴 CRITICAL | Admin static OTP "123456" | ✅ FIXED |
| SEC-002 | 🟠 HIGH | Any user self-grants premium via /subscription/rc-sync | ✅ FIXED |
| SEC-003 | 🟠 HIGH | Forgeable MoMo webhook | ✅ FIXED |
| SEC-004 | 🟠 HIGH | OTP echoed to caller + no expiry/attempt cap | ✅ FIXED |
| SEC-005 | 🟡 MEDIUM | BESOFT_VERIFY_SSL=false | ✅ FIXED |

## Backend changes (`/app/backend/server.py`)

### SEC-001 — Admin OTP path
- Removed the `is_admin_phone or not any_provider_ready` shortcut that pinned admin phones to `MOCK_OTP_CODE=123456`.
- Admin phones now receive the same random, single-use, expiring 6-digit code as every other user.
- Mock code is only used when `APP_ENV=development` AND no SMS provider is configured AND the number is not an admin phone.
- Response NO LONGER contains a `testCode` field for admin numbers.

### SEC-002 — RevenueCat sync verification
- `/api/subscription/rc-sync` now performs a server-side verification call to `https://api.revenuecat.com/v1/subscribers/{user_id}` using `REVENUECAT_API_KEY_V1`.
- Grants premium ONLY when the response includes `entitlements.pro` with an `expires_date` still in the future.
- Fails closed with 503 if `REVENUECAT_API_KEY_V1` is not configured.
- Payment log entry now records `note=verified_via_rc_rest` and the RC entitlement expiry.

### SEC-003 — BeSoft webhook signature
- `/api/billing/momo/callback` now enforces HMAC-SHA256 over the raw request body using `BESOFT_WEBHOOK_SECRET`.
- Accepts the signature from `X-BeSoft-Signature`, `X-Signature`, or `Signature` headers (with optional `sha256=` prefix).
- Fails closed with 503 if `BESOFT_WEBHOOK_SECRET` is not configured.
- Fails closed with 401 on signature mismatch.

### SEC-004 — OTP expiry + brute-force cap
- Added `OTP_TTL_SECONDS` (default 600 = 10 min). Verified server rejects expired challenges with 401 and cleans them up.
- Added `OTP_MAX_ATTEMPTS` (default 5). Verified server returns 429 after too many failed attempts and clears the challenge.
- Removed the `MOCK_OTP_CODE` fallback in `otp_verify`. If no code was stored, the user must request a fresh challenge.

## Config changes (`/app/backend/.env`)

```diff
- BESOFT_VERIFY_SSL="false"
+ BESOFT_VERIFY_SSL="true"
+ BESOFT_WEBHOOK_SECRET=""            # ← operator MUST set from BeSoft dashboard
- SMS_DEV_RETURN_CODE="true"
+ SMS_DEV_RETURN_CODE="false"
+ APP_ENV="production"
+ OTP_TTL_SECONDS="600"
+ OTP_MAX_ATTEMPTS="5"
+ REVENUECAT_API_KEY_V1=""            # ← operator MUST set from RC dashboard
```

## Operator TODO before production traffic
1. **Get RevenueCat REST v1 secret key** — RevenueCat dashboard → Project settings → API keys → "Secret keys (v1)" → copy `sk_XXXXXXXX` → set `REVENUECAT_API_KEY_V1` in `.env`.
2. **Get BeSoft webhook signing key** — BeSoft merchant dashboard → Webhook settings → generate/copy the shared secret → set `BESOFT_WEBHOOK_SECRET` in `.env` AND paste the same value in the BeSoft dashboard.
3. **Confirm BeSoft SSL cert is renewed** — if not, temporarily set `BESOFT_VERIFY_SSL=false` again (but keep webhook signature enforcement on).
4. **Add SMS provider if not delivering** — verified admin phones now require real SMS delivery. WhatsApp fallback is working.

## Verification tests (all passing)
- Admin phone gets real WhatsApp OTP (no `testCode` in response).
- Wrong code `123456` on admin phone → 401 "Invalid code".
- Unsigned MoMo callback → 503.
- Signed MoMo callback (correct HMAC) → 200.
- Signed MoMo callback (wrong HMAC) → 401.
- `/subscription/rc-sync` without valid token → 401.
