Subject: GCP Migration Architecture Review + Apple TestFlight Prep — BB FM Kigali Radio (Job ID: [YOUR_JOB_ID])

Hello Emergent Support,

App: BB FM Kigali Radio
Deployment URL: https://radio-vod-platform.emergent.host
Custom Domain: bbkigali.com
Stack: Expo (React Native) frontend · FastAPI backend · MongoDB · Emergent Object Storage
Live integrations: Stripe (LIVE), PayPal, BeSoft MTN MoMo (Rwanda), Route Mobile SMS, Nostress WhatsApp OTP, YouTube Data API v3
Job ID: [YOUR_JOB_ID]

We are preparing for production launch and would like guidance on two topics.

────────────────────────────────────────────────────────
1) GOOGLE CLOUD PLATFORM (GCP) MIGRATION ARCHITECTURE REVIEW
────────────────────────────────────────────────────────

We want a professional production architecture:
Web + Android + iOS → Secure GCP Backend/API → Production Database → Storage + Backup

Please advise whether:
  (a) Staying on Emergent-managed hosting (with documented backup, DR, monitoring, static outbound IP, secret management) fully covers our production requirements below, OR
  (b) Emergent can support migrating our deployed stack to customer-owned GCP with services such as:
        • Cloud Run or GKE — FastAPI backend
        • MongoDB Atlas on GCP (or a documented alternative) — production DB
        • Cloud Storage — uploaded media + coverage art
        • Secret Manager — Stripe / PayPal / MoMo / SMS / OTP keys
        • Cloud Armor + Cloud Load Balancer + Cloud DNS — HTTPS-only ingress + WAF
        • Cloud NAT with reserved static IP — for Route Mobile IP whitelisting
        • Cloud Logging + Cloud Monitoring + Alerting Policies — observability
        • Cloud Build / Artifact Registry — CI/CD
        • Separate production + development GCP projects — environment isolation
        • Documented IAM least-privilege policy
        • Documented DR runbook + restore drill

Our non-negotiable production requirements:
  1. Production backend/API hosted on GCP with HTTPS/SSL only
  2. bbkigali.com and api.bbkigali.com wired to the new stack securely
  3. Automated production database backups (daily + point-in-time recovery)
  4. Regular backup of uploaded files/content (Cloud Storage versioning + retention)
  5. Backup retention policy AND a **documented and rehearsed restore procedure**
  6. All third-party secrets stored in Secret Manager — never in frontend/mobile code
  7. Separate production and dev/testing environments
  8. Firewall + minimum necessary network access
  9. Least-privilege IAM
 10. Logging, monitoring, alerts on server/API failures
 11. Application + database monitoring
 12. Protection against unauthorized admin/backend access
 13. Static outbound IP (Cloud NAT) for Route Mobile SMS IP whitelisting
 14. Horizontal scalability as our audience grows
 15. Documented disaster-recovery runbook

Before we authorize migration, please provide:
  • Proposed GCP architecture diagram
  • Full list of GCP services to be used
  • Estimated monthly infrastructure cost (low/mid/high traffic tiers)
  • Backup frequency, retention window, PITR window
  • Recovery approach + expected RTO/RPO
  • Migration timeline + downtime window
  • Cost/scope for Emergent to perform this migration end-to-end

────────────────────────────────────────────────────────
2) APPLE TESTFLIGHT — FIRST iOS BUILD
────────────────────────────────────────────────────────

We are ready to trigger our first TestFlight build via the Emergent Publish → App Store flow. The app already has the iOS privacy manifests in place (NSPhotoLibraryUsageDescription + PrivacyInfo.xcprivacy API reason codes).

Please confirm the exact prerequisites from our side:
  • Apple Developer account status (individual vs organization) required
  • Whether we need a paid Apple Developer Program membership before you trigger the build
  • The exact Apple sign-in flow you use (Apple ID + 2FA trusted device recommended)
  • Any App Store Connect roles/permissions we must grant
  • Bundle identifier + Team ID handling (ours is com.emergent.radiovodplatform.reybr3 — should we keep it or transfer to our own team?)
  • App icon + screenshot requirements for the first submission
  • Estimated time-to-review once submitted

Thank you very much. We are aiming to have Web + Android + iOS all sharing the same secure production backend with reliable backups, monitoring and recovery procedures before final production launch.

Best regards,
BB FM Kigali Radio team
