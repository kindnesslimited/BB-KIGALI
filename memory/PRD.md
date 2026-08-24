# BB FM Kigali Radio — PRD

Mobile + web platform for BB FM Kigali (Rwanda). Live radio + VOD + News + Subscriptions + Admin console.

## Latest updates (iter 28)
1. **YouTube LIVE Auto-Detection** 🔴 — Backend polls `@bbkigalifm` every 10 min and caches the answer for 60 s. New endpoint `GET /api/live/status` returns `{ isLive, videoId, title, thumbnail, watchUrl, embedUrl }`. Home page shows a red "LIVE NOW · YOUTUBE" banner with WATCH ON YOUTUBE button automatically when a broadcast is on-air. Verified in production traffic during test — banner appeared with real live stream #BBSPORTSTALK.
2. **Featured Schedule Slot** ⭐ — Admin `/admin/schedule` has a "Feature at top of Home" switch (only one featured slot at a time, enforced backend-side). Home sort priority: LIVE slot → featured slot → normal order. Featured non-live slot gets an "UP NEXT · FEATURED" pill. Admin schedule list rows show a FEATURED badge.
3. **Program Reminders** 🔔 — Every non-live schedule card on Home shows a REMIND ME button. Uses `expo-notifications` to schedule a local notification 15 min before slot start; state stored in AsyncStorage. Tapping REMIND ME shows "we'll ping you 15 min before" and toggling again cancels. Works on real device builds (Expo Go on iOS has SDK-53+ limitations — see below).
4. **GCP hosting + TestFlight** — Ready-to-send support ticket drafted at `/app/memory/support_ticket_gcp_and_testflight.md` — customer only has to fill in `[YOUR_JOB_ID]` and email it to support@emergent.sh.

## Prior updates
- iter 27: Video upload MIME/magic-byte fix; schedule cover image + status; TODAY'S SCHEDULE on Home
- iter 26: iOS privacy manifests; VOD dedicated checkout modal; News source fields; Web/Desktop maxWidth 1200 + how-app-works + contact
- iter 25 and earlier: full app baseline (auth, live radio, VOD, YouTube sync, Stripe, PayPal, MoMo, admin console, reports).

## Test credentials
See `/app/memory/test_credentials.md`.
