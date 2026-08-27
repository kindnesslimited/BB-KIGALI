/**
 * BB FM Kigali — Cloudflare Stream Signed Playback Worker
 *
 * Purpose
 *   The BB FM Kigali FastAPI backend calls this Worker to mint a short-lived
 *   signed playback token for a Cloudflare Stream video. The token is bound
 *   to a specific video UID and expires quickly so a leaked URL is worthless.
 *
 *   We use the Workers `STREAM` binding (Cloudflare Stream Bindings) so we do
 *   NOT need an API token, a signing key, or a JWK. Cloudflare mints the token
 *   using the account that owns this Worker.
 *
 * Endpoints
 *   POST /sign
 *     Headers:  Authorization: Bearer <SHARED_SECRET>
 *     Body:     { "videoId": "<Stream UID>", "ttlSeconds": 900,
 *                 "requireOrigin": "https://web.bbkigali.com" }  (all optional except videoId)
 *     Returns:  { "token": "<signed>", "embedUrl": "...", "manifestUrl": "...",
 *                 "expiresAt": "<iso>" }
 *
 *   GET /health
 *     No auth. Returns { ok: true, version: <build> }.
 *
 * Security
 *   - Every request MUST present `Authorization: Bearer $SHARED_SECRET`.
 *   - Use a random 32+ char secret shared ONLY with the FastAPI backend.
 *     Set as a Worker secret via `wrangler secret put SHARED_SECRET`.
 *   - No unauthenticated request path returns a playback token.
 */

const VERSION = "2026-08-27.1";

async function readJson(request) {
  try { return await request.json(); } catch { return {}; }
}

function json(body, init = {}) {
  return new Response(JSON.stringify(body), {
    ...init,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Access-Control-Allow-Origin": "*",
      ...(init.headers || {}),
    },
  });
}

function unauth() {
  return json({ error: "unauthorized" }, { status: 401 });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // CORS preflight — we allow the FastAPI backend to call us
    if (request.method === "OPTIONS") {
      return new Response(null, {
        status: 204,
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
          "Access-Control-Allow-Headers": "Authorization, Content-Type",
          "Access-Control-Max-Age": "86400",
        },
      });
    }

    if (url.pathname === "/health") {
      return json({ ok: true, version: VERSION });
    }

    // Everything else requires the shared secret
    const auth = request.headers.get("authorization") || "";
    const expected = `Bearer ${env.SHARED_SECRET || ""}`;
    if (!env.SHARED_SECRET || auth !== expected) return unauth();

    if (url.pathname === "/sign" && request.method === "POST") {
      const body = await readJson(request);
      const videoId = (body.videoId || "").trim();
      if (!videoId) return json({ error: "videoId required" }, { status: 400 });

      const ttlSeconds = Math.min(Math.max(Number(body.ttlSeconds) || 900, 60), 3600);
      const exp = Math.floor(Date.now() / 1000) + ttlSeconds;

      // Optional pin — restrict where the token can be played
      const opts = { exp };
      if (body.requireOrigin) {
        // See https://developers.cloudflare.com/stream/viewing-videos/securing-your-stream/#pinning-tokens
        opts.accessRules = [
          { type: "allow", country: undefined, action: "allow", origin: body.requireOrigin },
          { type: "block", any: true, action: "block" },
        ];
      }

      // The Workers Stream Binding — no API key required.
      let token;
      try {
        token = await env.STREAM.video(videoId).generateToken(opts);
      } catch (e) {
        return json({ error: "stream_bind_failed", detail: String(e) }, { status: 500 });
      }

      const subdomain = env.STREAM_SUBDOMAIN || ""; // e.g. "customer-abc123.cloudflarestream.com"
      const embedUrl = subdomain
        ? `https://${subdomain}/${token}/iframe`
        : null;
      const manifestUrl = subdomain
        ? `https://${subdomain}/${token}/manifest/video.m3u8`
        : null;

      return json({
        token,
        embedUrl,
        manifestUrl,
        expiresAt: new Date(exp * 1000).toISOString(),
        videoId,
      });
    }

    return json({ error: "not_found" }, { status: 404 });
  },
};
