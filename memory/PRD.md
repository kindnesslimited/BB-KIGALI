# BB Kigali — Radio/VOD Platform (this workspace)

## Status: 🧊 FROZEN — reference/backup only

**As of 2026-09-06** the owner has decided to rebuild BB Kigali as a single independent system inside the sister workspace **`vod-platform-access`**. This workspace (`radio-vod-platform`) is no longer the source of truth for product features.

### Owner directive (verbatim summary)
> Rebuild BB Kigali from zero as one completely independent system in `vod-platform-access`. Do not depend on `radio-vod-platform` — its backend, MongoDB, 116 APIs, service token, webhooks, background jobs or mobile app. The final system must work fully with `radio-vod-platform` completely unavailable. Do not delete the old project — keep it as a temporary reference/backup until the new one is approved.

### What this workspace does going forward
- ✅ Keep backend + mobile running as-is so the old system is live for reference during the rebuild
- ✅ Handle emergency bug fixes only if the owner explicitly asks
- ❌ NO new features
- ❌ NO new endpoints (even if requested by the `vod-platform-access` agent — the owner banned cross-project dependencies)
- ❌ NO architecture changes
- ❌ NO data migration (owner confirmed there is no production customer data to preserve)

### Corrections applied (post-freeze, owner-requested)
- **2026-09-11** — Live Show edit: `PATCH /api/admin/live-shows/{id}` was rejecting partial updates because `LiveShowIn.title` was required. Introduced `LiveShowUpdate` (all fields Optional) and rewired the PATCH handler. Admins can now reopen any live show and change any subset of fields (title, description, scheduledAt, status, tier, etc.) without deleting and recreating. Empty body → 400. Invalid status → 400. Nonexistent id → 404. Verified: 7/7 backend tests pass (`/app/backend/tests/test_live_show_patch_partial.py`).
- **2026-09-11** — Logo restored: `icon.png`, `adaptive-icon.png`, `splash-image.png`, `bbfm-logo-transparent.png` and `favicon.png` had all been replaced during earlier development with a different design (3D BB letters + microphone + "89.7fm #MURI SPORTS"). Restored to the owner's original circular B&B KIGALI 89.7 FM logo with white background, exactly as provided. Splash dimensions updated to 1:1. Verified visually via web preview.

### Reference documentation produced for the rebuild
- `/app/memory/BB_KIGALI_REBUILD_REFERENCE.md` — master requirements + integration knowledge + gotchas, extracted for the new build. This is the file to hand to `vod-platform-access`.
- `/app/memory/web_admin_api_contract.md` — legacy full API spec (115 endpoints) — useful for feature completeness check
- `/app/memory/payment_policy_per_platform.md` — payment method allowed per platform
- `/app/memory/revenuecat.md`, `/app/memory/security_fixes_iter41.md`, `/app/memory/multi_channel_live_iter47.md` — deep-dive references

### Product history (what this workspace built, for historical context)
Cross-platform (iOS/Android/Web) subscription-gated radio + VOD app for BB Kigali FM:
- 24/7 Icecast radio + now-playing
- YouTube live simulcast (zero-quota multi-channel probe, 3 channels)
- Private live via Cloudflare Stream
- VOD catalog (Cloudflare Stream signed URLs) with per-episode purchases + subscription tiers
- Payments: Stripe, PayPal, MTN MoMo (BeSoft), Apple IAP (RevenueCat)
- SMS OTP (Route Mobile → Africa's Talking → Twilio → WhatsApp fallback chain)
- Admin dashboard (users, payments, content, analytics, audit log)
- Native Terms screen + Sign in with Apple + account deletion (App Store required)
- 115 API endpoints, 24 MongoDB collections
- Security-audited (SEC-001 through SEC-005 applied)

### Test credentials (still valid on old system)
- Admin: `+250794230137` / OTP `123456` (dev bypass, auto-granted premium+admin)
- Regular: `+250788123456` (standard OTP)

### Health of old system as of freeze
- ✅ Backend healthy, all 115 routes responding
- ✅ Mobile WebView shell shipping to TestFlight + Play Internal Testing
- ⚠️ `api.bbkigali.com` returns 403 (Emergent ingress custom-domain not configured; not blocking anything since new system will use its own domain)
- ⚠️ `YOUTUBE_OAUTH_CLIENT_ID/SECRET` empty (blocks admin YouTube connect on old system; not blocking rebuild)
- ⚠️ Route Mobile SMS credentials returning 1703 (WhatsApp fallback covering delivery; not blocking rebuild)

### Rollback plan
If the owner ever wants to reactivate this workspace: nothing to roll back. It is still fully functional.
