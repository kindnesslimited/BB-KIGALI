// Lightweight API client
import { storage } from "./utils/storage";

const BASE = process.env.EXPO_PUBLIC_BACKEND_URL as string;
const TOKEN_KEY = "bbfm.token";

// iOS TestFlight hardening: EVERY network call has a hard client-side
// timeout so a slow/dead backend can never block the UI thread indefinitely.
// Choose a value long enough to survive a slow LTE hop but short enough that
// the user sees an error rather than staring at a spinner.
const DEFAULT_TIMEOUT_MS = 15_000;

export async function saveToken(t: string) {
  await storage.secureSet(TOKEN_KEY, t);
}
export async function getToken(): Promise<string | null> {
  return (await storage.secureGet<string | null>(TOKEN_KEY, null)) as string | null;
}
export async function clearToken() {
  await storage.secureRemove(TOKEN_KEY);
}

type ReqInit = { method?: string; body?: any; auth?: boolean; timeoutMs?: number };

export async function api<T = any>(path: string, opts: ReqInit = {}): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (opts.auth) {
    const tok = await getToken();
    if (tok) headers.Authorization = `Bearer ${tok}`;
  }

  // AbortController-based timeout. If the request hasn't completed after the
  // timeout we cancel the socket and throw — the caller decides how to render.
  const controller = new AbortController();
  const timeout = setTimeout(
    () => controller.abort(),
    opts.timeoutMs ?? DEFAULT_TIMEOUT_MS,
  );

  let res: Response;
  try {
    res = await fetch(`${BASE}/api${path}`, {
      method: opts.method || "GET",
      headers,
      body: opts.body ? JSON.stringify(opts.body) : undefined,
      signal: controller.signal,
    });
  } catch (err: any) {
    clearTimeout(timeout);
    if (err?.name === "AbortError") {
      throw new Error("Request timed out. Check your connection and try again.");
    }
    throw err;
  }
  clearTimeout(timeout);

  const txt = await res.text();
  let data: any;
  try { data = txt ? JSON.parse(txt) : {}; } catch { data = { raw: txt }; }
  if (!res.ok) {
    const msg = data?.detail || data?.error || `Request failed (${res.status})`;
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return data as T;
}
