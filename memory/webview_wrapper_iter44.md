# BB Kigali FM — WebView Wrapper (Iter 44)

## What changed
The entire complex Expo app (RevenueCat, Stripe/PayPal/MoMo checkout, admin panel,
auth flows, subscription reconcile, etc.) was replaced by a lightweight
WebView wrapper that simply loads `https://web.bbkigali.com`. All business
logic (auth, payments, subscriptions, admin) now lives on the web app.

## App behaviour (matches spec exactly)

| # | Requirement | Implementation |
|---|---|---|
| 1 | 2-second splash on cold start | `BBSplash` component held for `SPLASH_MS = 2000` |
| 2 | Fullscreen WebView, no chrome | `<WebView source={{uri: WEB_URL}}>` — no URL bar / nav controls |
| 3 | Android back → WebView back → confirm exit | `BackHandler` listener: `webRef.current.goBack()` when `canGoBack`, else Alert with Cancel/Exit |
| 4 | Loading spinner with logo | `LoadingOverlay` (BB Kigali logo + brand-red spinner) driven by `onLoadStart`/`onLoadEnd` |
| 5 | Offline screen with logo + Retry | `NetInfo` listener; `OfflineScreen` with `retry()` that re-probes NetInfo + reloads WebView (via `retryNonce` remount) |
| 6 | Camera + microphone access | `mediaPlaybackRequiresUserAction={false}`, `onPermissionRequest={r => r.grant(r.resources)}`, Android CAMERA + RECORD_AUDIO permissions, iOS NSCamera/NSMicrophoneUsageDescription |
| 7 | Brand identity preserved | `app.json` name / icon / adaptive icon / splash image unchanged |
| 8 | RevenueCat / native pay code removed | All auth / paywall / checkout / admin / RC screens deleted from `app/` |

## Files
### Kept
- `app/_layout.tsx` — minimal Stack, no providers, no auth
- `app/index.tsx` — the WebView wrapper (~230 LOC, self-contained)
- `app/+html.tsx` — expo-router web helper (unchanged)
- `assets/images/*` — icon, adaptive-icon, splash-image (all originals)
- `app.json` — brand identity preserved; iOS/Android permissions updated

### Deleted
- `app/(tabs)/`, `app/admin/`, `app/auth/`, `app/program/`, `app/video/`
- `app/paywall.tsx`, `app/checkout.tsx`, `app/player.tsx`, `app/live.tsx`, `app/live-news.tsx`, `app/onboarding.tsx`, `app/renew.tsx`

### Untouched
- `src/` — legacy providers/contexts remain but are NOT imported anywhere
- `package.json` — RC packages remain installed but unused (removed only from imports)
- `backend/` — completely untouched; no longer talked to from mobile

## Package changes
Added `@react-native-community/netinfo@11.4.1` via `yarn expo install`.

## Web behaviour
On the web platform (RN-Web), `react-native-webview` is a stub. After the
2-second splash, `Platform.OS === "web"` triggers a `window.location.replace(WEB_URL)`
so opening the mobile app's web build in a browser goes straight to
`web.bbkigali.com` — confirmed working (screenshot: browser URL updated to
`https://web.bbkigali.com/` at T=3.8s).

## Verification
- Splash renders at T=0.8s ✓
- WebView + loading overlay mount at T=2s (native) ✓
- Web fallback redirect at T=3.8s → `https://web.bbkigali.com/` ✓
- No compile errors, no lint errors, backend untouched.

## Deploy notes
- New iOS/Android builds via the Publish button are required — the JS bundle
  is completely different from the previous version.
- App Store & Play Store metadata (name "BB Kigali", icon, splash) remain
  identical — no store-side updates needed.
- Camera + microphone permissions declared and auto-granted to the WebView
  so browser-side `getUserMedia()` works without a native prompt.
