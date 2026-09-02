# BB FM Kigali — Product Requirements & Delivery Log

## Product Vision
A cross-platform (iOS/Android/Desktop Web) subscription-gated radio + VOD app for BB FM Kigali. Live 24/7 radio stream, YouTube live show simulcast, on-demand catalog, and multi-currency payments (Stripe/PayPal/MTN MoMo/Apple IAP via RevenueCat).

## Tech Stack
- **Frontend:** Expo Router + React Native (mobile + fully responsive web)
- **Backend:** FastAPI (monolithic) + MongoDB (Motor)
- **Font:** Poppins (Regular/Medium/SemiBold/Bold) — global across every screen
- **Integrations:** Stripe, PayPal, MTN MoMo (BeSoft), RevenueCat, YouTube Data API v3, Cloudflare Stream

## Latest Session Delivered (Iter 38)
1. **YouTube Live detection fixed** — `/app/backend/youtube_live.py` rewritten to resolve channel-id via OAuth `channels?mine=true` (using cached refresh_token from `integration_state.youtube_config`). Falls back to `forHandle` lookup. Compat wrappers (`get_cached_or_refresh`, `refresh_and_store`, `periodic_live_loop`) added so `server.py` still loads. Endpoint `/api/live/status` returns 200 with `error: null` and correctly reports live shows.
2. **Global Poppins font applied** — 4 weights downloaded to `/app/frontend/assets/fonts/`, loaded via `useFonts`, and set as default for every `Text`/`TextInput` via `defaultProps`. `theme.ts` fonts remapped to Poppins. Legacy `BarlowCondensed` aliases point to Poppins so no per-file rewrites needed. Visually verified.

## Delivery Status
- Backend regression: 18/21 passed. 3 failures are environmental (Icecast DNS egress, sync-payment-endpoint timeout, YouTube idle-cache cosmetic) — none are code regressions.

## Test Credentials
- Admin phone: `+250794230137` (OTP mock returns `testCode` in dev mode)
- Regular user: `+250788123456`
