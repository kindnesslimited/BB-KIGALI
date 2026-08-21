import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { Platform } from "react-native";
import * as WebBrowser from "expo-web-browser";
import * as Linking from "expo-linking";
import { api, saveToken, getToken, clearToken } from "../api";

WebBrowser.maybeCompleteAuthSession();

export type User = {
  id: string;
  phone?: string | null;
  email?: string | null;
  displayName?: string | null;
  picture?: string | null;
  tier: "free" | "basic" | "premium";
  role?: "user" | "admin";
  subscriptionExpiresAt?: string | null;
};

type Ctx = {
  user: User | null;
  loading: boolean;
  requestOtp: (phone: string) => Promise<{ testCode?: string }>;
  verifyOtp: (phone: string, code: string) => Promise<void>;
  loginWithGoogle: () => Promise<void>;
  refresh: () => Promise<void>;
  updateProfile: (displayName: string) => Promise<void>;
  logout: () => Promise<void>;
};

const AuthCtx = createContext<Ctx | null>(null);
const processedSessions = new Set<string>();

function extractSessionId(url: string | null | undefined): string | null {
  if (!url) return null;
  const m = url.match(/[?#&]session_id=([^&#]+)/);
  return m ? decodeURIComponent(m[1]) : null;
}

async function completeGoogle(sessionId: string, setUser: (u: User) => void) {
  if (processedSessions.has(sessionId)) return;
  processedSessions.add(sessionId);
  const r = await api<{ session_token: string; user: User }>("/auth/session", {
    method: "POST", body: { session_id: sessionId },
  });
  await saveToken(r.session_token);
  setUser(r.user);
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    const tok = await getToken();
    if (!tok) { setUser(null); return; }
    try {
      const u = await api<User>("/auth/me", { auth: true });
      setUser(u);
    } catch {
      await clearToken();
      setUser(null);
    }
  }, []);

  useEffect(() => {
    (async () => {
      // Handle Google Sign-In callback FIRST (before checking existing session)
      if (Platform.OS === "web") {
        const url = typeof window !== "undefined" ? window.location.href : "";
        const sid = extractSessionId(url);
        if (sid) {
          try {
            await completeGoogle(sid, setUser);
            if (typeof window !== "undefined") {
              const cleaned = window.location.origin + window.location.pathname + window.location.search.replace(/[?&]session_id=[^&]+/, "");
              window.history.replaceState(window.history.state, "", cleaned);
              if (window.location.hash.includes("session_id")) {
                window.history.replaceState(window.history.state, "", window.location.href.replace(/#session_id=[^&]+/, ""));
              }
            }
          } catch (e) { console.log("google session err", e); }
        }
      } else {
        try {
          const initial = await Linking.getInitialURL();
          const sid = extractSessionId(initial);
          if (sid) await completeGoogle(sid, setUser);
        } catch (e) { console.log("initial url err", e); }
      }
      await refresh();
      setLoading(false);
    })();

    // Hot deep-links (native only)
    let sub: any;
    if (Platform.OS !== "web") {
      sub = Linking.addEventListener("url", async (e) => {
        const sid = extractSessionId(e.url);
        if (sid) {
          try { await completeGoogle(sid, setUser); }
          catch (err) { console.log("hot link err", err); }
        }
      });
    }
    return () => { try { sub?.remove?.(); } catch {} };
  }, [refresh]);

  const requestOtp = async (phone: string) =>
    api<{ testCode?: string }>("/auth/otp/start", { method: "POST", body: { phone } });

  const verifyOtp = async (phone: string, code: string) => {
    const r = await api<{ accessToken: string; user: User }>("/auth/otp/verify", {
      method: "POST", body: { phone, code },
    });
    await saveToken(r.accessToken);
    setUser(r.user);
  };

  const loginWithGoogle = async () => {
    const redirectUrl = Platform.OS === "web"
      ? (typeof window !== "undefined" ? window.location.origin + "/" : "")
      : Linking.createURL("");
    const authUrl = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
    if (Platform.OS === "web") {
      if (typeof window !== "undefined") window.location.href = authUrl;
      return;
    }
    const result = await WebBrowser.openAuthSessionAsync(authUrl, redirectUrl);
    let sid: string | null = null;
    if (result.type === "success") sid = extractSessionId(result.url);
    if (!sid) sid = extractSessionId(await Linking.getInitialURL());
    if (sid) await completeGoogle(sid, setUser);
  };

  const updateProfile = async (displayName: string) => {
    const u = await api<User>("/auth/me", { method: "PATCH", auth: true, body: { displayName } });
    setUser(u);
  };

  const logout = async () => {
    await clearToken();
    setUser(null);
  };

  return (
    <AuthCtx.Provider value={{ user, loading, requestOtp, verifyOtp, loginWithGoogle, refresh, updateProfile, logout }}>
      {children}
    </AuthCtx.Provider>
  );
}

export const useAuth = () => {
  const v = useContext(AuthCtx);
  if (!v) throw new Error("useAuth outside provider");
  return v;
};
