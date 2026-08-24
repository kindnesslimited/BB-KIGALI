# BB FM Kigali Radio — PRD

Mobile + web platform for BB FM Kigali (Rwanda). Live radio + VOD + News + Subscriptions + Admin console.

## Latest updates (iter 29 — App Store Readiness)
1. **Apple 3.1.1 IAP compliance** ✅ — On iOS, ALL non-IAP payment methods are hidden:
   - `/checkout` shows a clean **"PREMIUM COMING SOON ON iOS"** gate with a feature list of what's already free on iOS and a CONTINUE FREE button.
   - `/video/[id]` locked-video modal shows a **"COMING SOON ON iOS"** gate instead of Stripe/PayPal/MoMo cards.
   - Web and Android continue to show full payment options (PayPal, Stripe, MoMo).
2. **Apple 5.1.1(v) — Sign in with Apple token revocation** ✅ — On account deletion, the backend now calls Apple's `/auth/revoke` endpoint. New helpers in `apple_auth.py`:
   - `exchange_code_for_refresh_token()` — swaps the one-shot `authorizationCode` from `expo-apple-authentication` for a long-lived `refresh_token` stored on the user record.
   - `revoke_apple_refresh_token()` — signs a client_secret JWT (ES256) and posts to Apple's revoke endpoint on delete.
   - If `APPLE_TEAM_ID` / `APPLE_KEY_ID` / `APPLE_CLIENT_ID` / `APPLE_PRIVATE_KEY` env vars aren't provisioned yet (they're currently empty placeholders in `backend/.env`), Apple calls silently no-op and account deletion still completes locally.
   - DELETE /api/auth/me now returns `{ok: true, appleRevoked: bool}`.
3. **Over-declared iOS permissions cleaned up** ✅ — `NSMicrophoneUsageDescription` and `NSUserTrackingUsageDescription` removed from `app.json` (no mic recording or ATT tracking in the app).
4. **"Coming soon" placeholder removed** — Airtel Money row deleted from checkout.
5. **Root ErrorBoundary added** — new `/src/components/ErrorBoundary.tsx` wraps the entire app in `_layout.tsx` with a friendly Reload UI if the JS bundle crashes.
6. **All 10 backend + all frontend flows passed the testing agent** — no regressions.

## Env vars to provision before TestFlight goes live
Add these to `backend/.env` once you have your Apple Developer credentials so token revocation actually reaches Apple's servers:
```
APPLE_TEAM_ID="10-char Team ID from Apple Developer"
APPLE_KEY_ID="Key ID of your Sign in with Apple key"
APPLE_CLIENT_ID="com.emergent.radiovodplatform.reybr3"
APPLE_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\n...contents of AuthKey_XXX.p8...\n-----END PRIVATE KEY-----"
```

## Prior updates
- iter 28: YouTube LIVE auto-detection, Featured Schedule Slot, Program Reminders, GCP+TestFlight support ticket
- iter 27: Video upload MIME/magic-byte fix; schedule cover image + status
- iter 26: iOS privacy manifests; VOD dedicated checkout modal; News source fields; Web responsive layout
- iter 25 and earlier: full app baseline

## Test credentials
See `/app/memory/test_credentials.md`.
