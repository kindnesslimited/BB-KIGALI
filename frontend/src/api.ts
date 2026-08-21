// Lightweight API client
import { storage } from "./utils/storage";

const BASE = process.env.EXPO_PUBLIC_BACKEND_URL as string;
const TOKEN_KEY = "bbfm.token";

export async function saveToken(t: string) {
  await storage.secureSet(TOKEN_KEY, t);
}
export async function getToken(): Promise<string | null> {
  return (await storage.secureGet<string | null>(TOKEN_KEY, null)) as string | null;
}
export async function clearToken() {
  await storage.secureRemove(TOKEN_KEY);
}

type ReqInit = { method?: string; body?: any; auth?: boolean };

export async function api<T = any>(path: string, opts: ReqInit = {}): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (opts.auth) {
    const tok = await getToken();
    if (tok) headers.Authorization = `Bearer ${tok}`;
  }
  const res = await fetch(`${BASE}/api${path}`, {
    method: opts.method || "GET",
    headers,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  const txt = await res.text();
  let data: any;
  try { data = txt ? JSON.parse(txt) : {}; } catch { data = { raw: txt }; }
  if (!res.ok) {
    const msg = data?.detail || data?.error || `Request failed (${res.status})`;
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return data as T;
}
