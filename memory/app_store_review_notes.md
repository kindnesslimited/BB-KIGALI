# BB FM Kigali — App Store Connect Review Notes

Copy-paste into **App Store Connect → your app → App Information → App Review → Notes** before submitting for review.

---

## Demo account

To reach every screen in the app, the reviewer can sign in with these credentials:

- **Phone number**: `+250 794 230 137`
- **One-time code**: `123456`

The phone-OTP flow accepts any spacing (`+250 794 230 137`, `250-794-230-137`, `250794230137` — all equivalent). This demo account has the `admin` role so the reviewer can also open the Admin dashboard from the Profile tab.

For a regular customer experience without admin access, please try `+250 780 111 222` with code `123456`.

## What the app does

BB FM Kigali is a Rwandan sports radio + video platform. Free tier includes 24/7 live FM radio, news, program schedule and free podcasts. **Premium** unlocks the private VOD library, ad-free radio and exclusive live video interviews.

Purchases on iPhone go through **Apple In-App Purchase** via RevenueCat (see monthly / annual products in the connected iTunes Connect account). External payment options (Stripe, PayPal, MTN MoMo) are **hidden on iOS** and only offered on Android and the web app at `web.bbkigali.com`, per guideline 3.1.1.

## Notes for the reviewer

- **Background audio** — the radio player continues playing when the screen is locked. This is intentional and declared as `UIBackgroundModes: audio` in Info.plist.
- **HTTP media exception** — the 24/7 FM Icecast origin at `radio.bbkigali.com` is HTTP-only and is scoped in `NSAppTransportSecurity → NSExceptionDomains` for media-only playback. All REST API traffic uses HTTPS. We are actively migrating the stream to HTTPS at `stream.bbkigali.com` and will remove the exception in a future update.
- **Account deletion** — Profile tab → **Delete Account** removes the user record and calls Apple's `auth/revoke` endpoint to revoke the Sign in with Apple refresh token (guideline 5.1.1(v)).
- **Sign in with Apple** — offered alongside phone-OTP because we also offer social sign-in via Google.
- **Live YouTube** — automatically detected via YouTube Data API when the official channel `@BB-FM-Kigali` starts broadcasting; hidden otherwise.
- **VOD encryption** — private videos are served through Cloudflare Stream signed URLs. Signed tokens are single-use and expire after 15 minutes.
- **Privacy manifest** — `PrivacyInfo.xcprivacy` declares 4 required-reason API categories (file timestamp `C617.1`, disk space `E174.1`, system boot time `35F9.1`, user defaults `CA92.1`).

## Contact

For any question during review: **info@besoft.info** (in-app support link on Profile screen).
