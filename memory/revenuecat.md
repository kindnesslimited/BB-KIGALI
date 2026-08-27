# RevenueCat — integrated (2026-08-27)

This file exists so future agents remember the RevenueCat wiring on this project and can
mutate products/prices via the integration proxy WITHOUT re-fetching the whole playbook.

## Identifiers (from /setup response — copy verbatim)
- rc_project_id: `proj7b23b575`
- apple_app_id: `app0dd519bb13`
- play_app_id: `appa2e68723ab`
- entitlement_lookup_key: `pro`
- offering_lookup_key: `default`
- Packages (package → product_id, current price):
  - `$rc_monthly` → `prod1c20f8c528` (€3.00 / P1M, trial: none) — mirrors web "Premium Monthly"
  - `$rc_annual`  → `prod0a95e9907a` (€30.00 / P1Y, trial: none) — mirrors web "Premium Yearly"
- Dashboard: https://app.revenuecat.com/projects/proj7b23b575

## App identity
- iOS bundleIdentifier: `com.emergent.radiovodplatform.reybr3`
- Android package: `com.emergent.radiovodplatform.reybr3`
- Both mapped to the SAME entitlement `pro` and offering `default`.

## Frontend files (already implemented)
- `/app/frontend/src/lib/revenuecat.tsx` — SDK init, SubscriptionProvider, useSubscription, useBindRevenueCatIdentity.
- `/app/frontend/app/_layout.tsx` — calls `initializeRevenueCat()` at module scope, wraps app in `AppQueryClientProvider` → `AuthProvider` → `SubscriptionProvider`.
- `/app/frontend/src/context/auth.tsx` — calls `useBindRevenueCatIdentity(user?.id)` for `logIn/logOut` on every auth path; exposes `purchaseIdentityError` on context.
- `/app/frontend/app/paywall.tsx` — on iOS the CONTINUE button routes to `Purchases.purchasePackage(...)` (from `useSubscription`); web + Android keep Stripe/PayPal/MoMo. Includes a Restore Purchases button (Apple requirement).

## Backend hook (best-effort)
- `POST /api/subscription/rc-sync` in `/app/backend/server.py` — client calls this AFTER a successful RevenueCat purchase to mirror `tier=premium` + `subscriptionExpiresAt` in Mongo so gated endpoints recognise the user in-session. NOT authoritative — the RevenueCat SDK's `customerInfo.entitlements.active.pro` remains the client source of truth.

## Status check
```bash
curl -sS -H "Authorization: Bearer sk-emergent-bBe3aF0E08502Fa908" \
  "$INTEGRATION_PROXY_URL/internal/revenuecat/projects/1b743885-5dab-4810-a253-aef91fef9f62/status"
# → {"connection_state":"connected","project_state":"...","rc_project_id":"proj7b23b575"}
```
If `project_state` is less than `project_created`, re-fetch the RevenueCat playbook via the integration expert tool.

## Later updates to products (integration proxy APIs ONLY — NEVER call the RevenueCat REST API)
- Change price/duration/trial OR add a package (upsert):
  ```bash
  curl -sS -X POST "$INTEGRATION_PROXY_URL/internal/revenuecat/projects/1b743885-5dab-4810-a253-aef91fef9f62/products" \
    -H "Authorization: Bearer sk-emergent-bBe3aF0E08502Fa908" \
    -H 'Content-Type: application/json' \
    -d '{"products":[{"package":"$rc_monthly","price":3.00,"currency":"EUR","period":"P1M","prices":[{"amount_micros":3000000,"currency":"EUR"}]}]}'
  ```
  (`amount_micros` = price × 1,000,000; omit `trial` for none)
- Remove a package:
  ```bash
  curl -sS -X DELETE "$INTEGRATION_PROXY_URL/internal/revenuecat/projects/1b743885-5dab-4810-a253-aef91fef9f62/products/%24rc_monthly" \
    -H "Authorization: Bearer sk-emergent-bBe3aF0E08502Fa908"
  ```
- Recover identifiers / repopulate `.env`: re-run the idempotent `/setup` call.

## Taking in-app purchases LIVE — user's manual steps
These are required ONLY for REAL purchases in published App Store / Play Store builds.
The Test Store (Expo Go / web preview / dev builds) works today with no store-side config.

1. **Upload store credentials to the RevenueCat dashboard** (Home → project → Apps → App name):
   - iOS: App Store Connect API key + In-App Purchase Key configuration
     - https://www.revenuecat.com/docs/service-credentials/itunesconnect-app-specific-shared-secret/app-store-connect-api-key-configuration
     - https://www.revenuecat.com/docs/service-credentials/itunesconnect-app-specific-shared-secret/in-app-purchase-key-configuration
   - Android: Google Play service-account JSON
     - https://www.revenuecat.com/docs/service-credentials/creating-play-service-credentials

2. **Set up payment profiles** in App Store Connect and Play Console:
   - App Store: https://developer.apple.com/help/app-store-connect/configure-in-app-purchase-settings/overview-for-configuring-in-app-purchases/
   - Play Store: https://support.google.com/googleplay/android-developer/answer/7161426

3. **Create matching IAP products** using the SAME product IDs shown in the RevenueCat dashboard:
   - App Store: https://developer.apple.com/help/app-store-connect/manage-subscriptions/offer-auto-renewable-subscriptions/
   - Play Store: https://support.google.com/googleplay/android-developer/answer/140504

4. Make a release build, test IAP via TestFlight + Play Internal Testing, then submit for review.

All of these steps are documented in the FAQ section of the payments panel inside the Emergent preview.
