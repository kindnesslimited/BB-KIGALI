# BB FM Kigali Radio — PRD

Mobile + web platform for BB FM Kigali (Rwanda). Live radio + VOD + News + Subscriptions + Admin console.

## Latest updates (iter 33 — Complete Orange Removal Audit)

Customer flagged that iter 32 missed orange in some parts of the system. Full programmatic audit + fix:

- **Programmatic HSL detection** ran across every .ts/.tsx/.py/.html/.json/.md file in frontend, backend, and landing folders. Any hex code whose HSL hue falls in 10°-45° (orange band) was flagged and swapped.
- **Fixed 7 additional orange sites** that iter 32 missed:
  1. `frontend/app/admin/payments.tsx` — MTN MoMo brand color `#FFCC00` → `#E10600` and status `#f59e0b` pending → red
  2. `frontend/app/video/[id].tsx` — MTN MoMo icon background `#ffcc00` → brand red
  3. `frontend/app/admin/index.tsx` — 4 admin dashboard KPI/tx accents (`#22c55e` green, `#f97316` orange, `#3b82f6` blue, `#f59e0b` amber) → brand red + brand blue
  4. `backend/server.py` — YouTube OAuth callback HTML `#ff6600` → red
  5. `backend/server.py` — Stripe cancel/success HTML `#FF6B00` → red (×2)
  6. `backend/admin_analytics.py` — PDF report BRAND color `#FF6B00` → red
  7. `landing/index.html`, `landing/terms.html`, `landing/privacy.html` — all `--brand:#FF6B00` → red
- **Green also removed** from admin dashboard KPIs and status cards (not in the allowed BLUE/RED/BLACK/WHITE palette). Success indicators are now blue, pending is red.
- **Verified**: automated HSL sweep now returns `✅ ZERO orange-hue hex codes remain in frontend/app, frontend/src, backend, or landing`.
- Manual visual verification via screenshots (Home, Shows, Auth, mini-player, tab bar, admin) confirms no orange remains anywhere.

## Prior iters
- iter 32: brand refactor kickoff, Cloudflare Stream integration, Contabo migration ticket
- iter 31: Live Shows CMS + admin-managed YouTube channel
- iter 30: subscription enforcement, SMS receipts, in-app YouTube live, NaN fix
- iters 26-29: iOS App Store readiness, News source fields, Schedule management, etc.

## Test credentials
See `/app/memory/test_credentials.md`.
