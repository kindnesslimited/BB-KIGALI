# BB FM Kigali — Payment Policy per Platform (App Store compliant)

This is the customer-facing + reviewer-facing policy that our app enforces in code today (iter 29 IAP gate is live).

## Web / Desktop  (bbkigali.com  or  radio-vod-platform.emergent.host)
- **All payment methods are available**: Card via Stripe, PayPal, MTN Mobile Money
- Subscriptions AND single VOD unlocks purchasable here
- Apple has no jurisdiction over web purchases → we are free to use any provider

## Android app (Google Play + sideload APK)
- **All payment methods are available**: Card via Stripe, PayPal, MTN Mobile Money
- Google Play policy allows external payment for real-world / non-Play-Store digital content in most jurisdictions; MTN MoMo is a common payment rail in Rwanda and is accepted
- If we ever list on the Google Play Store, Google may require Play Billing for some digital goods, but MoMo is generally allowed as an alternate for local markets — we'll re-check at Play submission

## iOS app (App Store + TestFlight)
- **Non-IAP methods are HIDDEN by our code** (iter 29). Stripe / PayPal / MoMo do NOT render on iPhone.
- **Digital content subscriptions and VOD unlocks are Apple 3.1.1** — must use Apple's In-App Purchase (StoreKit / RevenueCat) or NOT be sold in-app at all.
- Current iOS state: we show a **"Premium coming soon on iOS"** gate. Free tier (live radio, news, schedule, free podcasts) works fully on iPhone.
- **Next step to sell on iOS**: integrate Emergent-managed RevenueCat for subscriptions + StoreKit consumable products for VOD unlocks. Product IDs must be created on App Store Connect first.

## Reviewer notes for App Store submission
- Reviewer test account: phone `250794230137` — OTP `123456` (dev-mode auto-accept in TestFlight builds).
- Confirm iOS build hides non-IAP options. All paid content shows a "Coming soon" gate + "Subscribe on the web" is NOT linked (no external buy links).
- No jailbreak / no external purchase circumvention. `Linking.openURL(...)` never routes to a payment provider from iOS.

## Answering the customer's checklist

- ✅ Final Web App URL — **https://radio-vod-platform.emergent.host** (will become **bbkigali.com** once you point the DNS)
- ⏳ Android APK URL — will be generated when you tap **Publish** in the Emergent panel. Landing page currently links to `/downloads/bb-kigali.apk` as a placeholder — update to the real APK URL after the first build
- ⏳ iOS TestFlight/App Store — awaiting your Apple Developer account credentials + first submission via Publish → App Store
- ✅ Payment methods on Web — Stripe (Card) + PayPal + MTN MoMo — all live
- ✅ Payment methods on Android — Stripe (Card) + PayPal + MTN MoMo — all live
- ✅ iOS-compliant payment — currently: free tier only + "Premium coming soon" gate (fully compliant). To enable paid: add RevenueCat.
- ⏳ Emergent share page — production URL `https://radio-vod-platform.emergent.host` bypasses it. Any lingering `app.emergent.sh/share?app=...` link is not something our code generates. To eliminate it entirely from the customer journey, DNS bbkigali.com → the production deploy (or contact Emergent Support to remove the share-page redirect for this project). The landing page's CTAs now all point to production directly.

## Same account everywhere (already true)
- Single FastAPI backend + MongoDB → the same JWT session token is honored by Web, Android and iOS
- Login on any platform, subscription and content entitlement are immediately valid on the other two
- Cross-device tests verified in iter 30 (subscription enforcement covered by 12 backend tests)
