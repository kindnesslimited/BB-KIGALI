# BB FM Kigali — Cloudflare Stream Signed Playback Worker

This tiny Cloudflare Worker mints short-lived signed playback tokens for
videos hosted on your Cloudflare Stream account. The BB FM Kigali FastAPI
backend calls it AFTER verifying that a caller has an active paid
subscription, then embeds the returned signed URL in the app.

**Why a Worker?** We want to gate video playback behind a paid subscription
without leaking a Cloudflare API token or signing key to our backend
env vars. Cloudflare's Workers Stream Binding lets a Worker on YOUR account
generate signed tokens with no external credentials at all.

---

## One-time deployment (≈ 5 minutes)

### Prerequisites

- A Cloudflare account with Stream enabled (Stream is a paid add-on).
- Node.js 18+ and Wrangler CLI:
  ```bash
  npm install -g wrangler
  wrangler login
  ```

### 1) Copy the two files from this folder to a local directory
```
/app/cloudflare-worker/worker.js
/app/cloudflare-worker/wrangler.toml
```

### 2) Set your Stream customer subdomain
Open `wrangler.toml` and replace `customer-CHANGE-ME.cloudflarestream.com`
with your real customer subdomain.

Find it in Cloudflare dashboard → **Stream** → any video → **Playback** tab →
copy the host from the embed URL (looks like `customer-abc123def.cloudflarestream.com`).

### 3) Generate a shared secret (any 32+ character random string)

```bash
openssl rand -hex 32
# example output: a1b2c3d4e5f6...
```

Save this string — you'll paste it into two places:
- `wrangler secret put SHARED_SECRET`  (Cloudflare Worker)
- `CLOUDFLARE_STREAM_WORKER_SECRET=...` in `/app/backend/.env`  (BB FM backend)

### 4) Deploy the Worker

```bash
cd /path/to/cloudflare-worker
wrangler deploy
```

Wrangler will print the Worker URL, e.g.:
```
Deployed bb-stream-signer to https://bb-stream-signer.YOUR-ACCOUNT.workers.dev
```

Copy that URL. Then set the secret:
```bash
wrangler secret put SHARED_SECRET
# paste the string from step 3 when prompted
```

### 5) Test the Worker

```bash
# public health check
curl -s https://bb-stream-signer.YOUR-ACCOUNT.workers.dev/health
# → { "ok": true, "version": "2026-08-27.1" }

# signed playback URL (requires the shared secret AND a real Stream video UID)
curl -s -X POST https://bb-stream-signer.YOUR-ACCOUNT.workers.dev/sign \
     -H "Authorization: Bearer <SHARED_SECRET>" \
     -H "Content-Type: application/json" \
     -d '{"videoId": "<a-real-stream-video-uid>"}'
# → { "token": "...", "embedUrl": "https://customer-XXXX.cloudflarestream.com/<token>/iframe", ... }
```

### 6) Wire the backend

Add to `/app/backend/.env`:

```
CLOUDFLARE_STREAM_WORKER_URL=https://bb-stream-signer.YOUR-ACCOUNT.workers.dev
CLOUDFLARE_STREAM_WORKER_SECRET=<the string from step 3>
CLOUDFLARE_STREAM_SUBDOMAIN=customer-abc123def.cloudflarestream.com
```

Restart the backend:
```bash
sudo supervisorctl restart backend
```

The backend will now call `POST $CLOUDFLARE_STREAM_WORKER_URL/sign` behind
the endpoint `GET /api/videos/{show_id}/playback` and return the signed
`embedUrl` to any authenticated + paid subscriber. Non-subscribers still
get 402.

---

## How it fits together

```
┌────────────┐   1. GET /api/videos/<id>/playback  ┌──────────────────┐
│  BB Kigali │  ─────────────────────────────────► │ FastAPI backend  │
│  Web/App   │                                      │ (checks tier)   │
└────────────┘                                      └────────┬─────────┘
                                                             │ 2. POST /sign
                                                             │    Bearer secret
                                                             ▼
                                              ┌───────────────────────────┐
                                              │ Cloudflare Worker         │
                                              │ (STREAM binding)          │
                                              └────────┬──────────────────┘
                                                       │ 3. mints signed token
                                                       ▼
                                              customer-XXXX.cloudflarestream.com
                                                       │
                                                       │ 4. token in embedUrl
                                                       ▼
                                              ┌───────────────────────────┐
                                              │ App loads signed iframe   │
                                              └───────────────────────────┘
```

Tokens expire in 15 minutes (configurable via `ttlSeconds` on `/sign`). A
customer whose token has expired simply refreshes the page — the app will
re-authenticate and request a new token if their subscription is still
active. If their subscription has expired, no new token is issued and
playback stops after the current 15-minute window.

## Optional: origin-pinning

Pass `requireOrigin: "https://web.bbkigali.com"` to `/sign` and the token
will only be accepted when played from that origin. This prevents someone
who has grabbed a live token from embedding your video on their own site.
