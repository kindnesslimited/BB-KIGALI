Subject: Migration from Emergent hosting to self-owned Contabo VDS — BB FM Kigali Radio (Job ID: [YOUR_JOB_ID])

Hello Emergent Support,

App: BB FM Kigali Radio (Expo + FastAPI + MongoDB)
Current production URL: https://radio-vod-platform.emergent.host
Custom domain: bbkigali.com
Job ID: [YOUR_JOB_ID]

We now own a Contabo VDS and want the production system deployable on infrastructure under our control. Please advise on the process and cost.

──────────────────────────────────────────────────────────
0)  SECURITY NOTE — root SSH password was inadvertently pasted into agent chat
──────────────────────────────────────────────────────────
The password has been (or is being) rotated before any real access is granted. When ready, we will provide access via SSH KEY only (we will generate the key pair locally and send only the public key). Please **do not** proceed with any deployment attempt using any credential that may have been in prior chat logs.

──────────────────────────────────────────────────────────
1)  Target infrastructure
──────────────────────────────────────────────────────────
- Provider: Contabo
- Type: VDS
- IP: 161.97.156.17
- SSH port: 2202 (root will be disabled; deploy user with sudo will be created)
- OS: (Ubuntu 22.04 LTS recommended if we still have flexibility)

Scope to deploy on this server:
- FastAPI backend / API
- Web application (Expo Router static export)
- Admin Panel (same web bundle)
- MongoDB (single-node with backups; upgrade to replica set later)
- Domain: bbkigali.com + api.bbkigali.com
- SSL/HTTPS via Let's Encrypt (certbot or Traefik/Caddy)
- Secrets management (env-file with 600 perms + optional Vault later)
- Automatic nightly backups (mongodump + object-storage backup)
- Logging + monitoring (loki/promtail + grafana, or just journalctl + Uptime Kuma)
- CDN / WAF: Cloudflare in front (proxied A record)
- Video/object-storage: connect to Cloudflare R2 (or continue Emergent Object Storage if you support it externally)
- Third-party integrations must keep working:
  - YouTube Data API / OAuth (already customer-managed)
  - Payments: Stripe (LIVE), PayPal, BeSoft MTN MoMo — webhook URLs will change to api.bbkigali.com
  - Route Mobile SMS (may require IP whitelist update to Contabo IP)
  - Nostress WhatsApp OTP
  - Google Sign-In / Apple Sign in (redirect URIs to be updated)
- Mobile app: EXPO_BACKEND_URL flipped to api.bbkigali.com — no other change

──────────────────────────────────────────────────────────
2)  Automatic deployment target workflow
──────────────────────────────────────────────────────────
Developer / AI update → Git repo → automated tests → build → deploy to Contabo → production

Please recommend and set up either:
- GitHub Actions → SSH-deploy via docker-compose pull + up (simplest)
- Or Coolify / Dokploy on the VDS (self-hosted PaaS)
- Or ArgoCD if we go with a small K3s cluster

──────────────────────────────────────────────────────────
3)  Data ownership & portability
──────────────────────────────────────────────────────────
We must retain full control + rollback for:
- Source code + git repo (already ours)
- Mongo database (dumps to our own S3-compatible bucket)
- Customer data (users, payments, VOD purchases, live_shows, schedule, news)
- Uploaded content (recordings, cover images)
- Configuration + credentials (env vars + secrets)
- Video/recording data (private live-show recordings)

──────────────────────────────────────────────────────────
4)  Cut-over plan we need from Emergent
──────────────────────────────────────────────────────────
Before we authorize the cut-over please provide:
- Proposed target architecture diagram
- Docker-compose (or K3s) manifests you would deploy
- MongoDB migration path (mongodump from Emergent → mongorestore on Contabo)
- Object Storage migration path (bulk copy of `bb-fm-kigali/*` from Emergent → Cloudflare R2 or our new bucket) with a signed-URL rewrite so existing recording URLs keep resolving
- DNS + TTL plan (drop bbkigali.com TTL to 60s several hours before cut-over)
- Blue/green or maintenance-window plan (target downtime: ≤ 15 min)
- Roll-back plan if the new stack misbehaves (keep Emergent app running for 7 days as fallback)
- Timeline (calendar weeks)
- Cost/scope for Emergent to execute this end-to-end

──────────────────────────────────────────────────────────
5)  Third-party endpoints that will need updating on cut-over
──────────────────────────────────────────────────────────
- Stripe webhook endpoint → api.bbkigali.com/api/billing/stripe/webhook
- PayPal webhook endpoint → api.bbkigali.com/api/billing/paypal/webhook
- BeSoft MoMo callback → api.bbkigali.com/api/billing/momo/callback
- YouTube OAuth authorized redirect URI → api.bbkigali.com/api/admin/youtube/callback
- Apple Sign in — no redirect (native flow) but bundle id stays the same
- Google Sign in — no redirect (native flow) but iOS/Android client IDs stay the same
- Route Mobile SMS — whitelist the new Contabo static IP

──────────────────────────────────────────────────────────
6)  Backups & disaster recovery
──────────────────────────────────────────────────────────
- Nightly `mongodump` to a second location (Cloudflare R2 bucket, or a second Contabo VDS)
- Weekly full VM snapshot (Contabo panel)
- Retain daily backups 14 days, weekly 90 days, monthly 12 months
- Documented restore drill — please share the exact `mongorestore` + object-restore steps
- Alerting on backup failure (email or Discord webhook)

Thank you very much. We can grant SSH-key access as soon as you confirm scope + cost, so please advise.

Best regards,
BB FM Kigali Radio team
