# BB FM Kigali Radio — PRD

Mobile + web platform for BB FM Kigali (Rwanda). Live radio + VOD + News + Subscriptions + Admin console.

## Latest updates (iter 26 — this session)
1. **iOS App Store readiness** — app.json now has `NSPhotoLibraryUsageDescription`, `NSCameraUsageDescription`, `NSMicrophoneUsageDescription`, and `privacyManifests` with 4 API-type reason codes. Android permissions declared. `expo-image-picker` plugin config added.
2. **Dedicated VOD Checkout Modal** — locked shows now display a compact "UNLOCK NOW" CTA. Tapping it opens a full-screen modal with a clean CHECKOUT header, big price, and three payment method cards (Stripe / PayPal / MTN MoMo). Video details are hidden inside checkout. Modal auto-closes on unlock success (Stripe poll, MoMo callback, PayPal capture).
3. **News — external source + image visibility** — Admin now inputs `sourceName` + `sourceUrl` alongside the story. Backend mirrors `coverUrl → thumbnail` and `summary → excerpt` so uploaded images and text always show on the customer News feed. Customer News tab shows a "Source: {publication}" pill that opens the original article.
4. **Schedule Management (Admin)** — brand new `/admin/schedule` page + backend CRUD (`POST/PATCH/DELETE /api/admin/schedule`). Fields: time slot, program name, host/presenter, days of week (chips), live-now toggle, order.
5. **Web/Desktop responsive** — root Tabs layout now constrains content to `maxWidth: 1200` on web. Added a "HOW OUR APP WORKS" 4-card guide grid and a "NEED HELP?" contact card (WhatsApp/Call/Email + address) on the Home screen.
6. **Direct Video Upload rejection** — deferred at user's request ("skipped, assuming defaults for now").

## Test credentials
See `/app/memory/test_credentials.md`.
