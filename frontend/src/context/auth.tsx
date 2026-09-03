import React, { createContext, useContext, useEffect, useState, useCallback, useMemo, useRef } from "react";
import { Platform, AppState, AppStateStatus } from "react-native";
import * as WebBrowser from "expo-web-browser";
import * as Linking from "expo-linking";
import { api, saveToken, getToken, clearToken } from "../api";
import { useBindRevenueCatIdentity } from "../lib/revenuecat";
import { toE164 } from "../utils/phone";

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

type SubscriptionStatus = {
  active: boolean;
  tier: string;
  subscriptionExpiresAt?: string | null;
  currentPlan?: string | null;
  provider?: string | null;
};

type Ctx = {
  user: User | null;
  loading: boolean;
  purchaseIdentityError: string | null;
  hasActiveSubscription: boolean;
  requestOtp: (phone: string) => Promise<{ testCode?: string }>;
  verifyOtp: (phone: string, code: string) => Promise<void>;
  loginWithGoogle: () => Promise<void>;
  loginWithApple: () => Promise<void>;
  refresh: () => Promise<void>;
  syncSubscriptionFromBackend: () => Promise<SubscriptionStatus | null>;
  updateProfile: (displayName: string) => Promise<void>;
  deleteAccount: () => Promise<void>;
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

function isActiveTier(u: User | null | undefined): boolean {
  if (!u) return false;
  if (u.tier !== "basic" && u.tier !== "premium") return false;
  const exp = u.subscriptionExpiresAt || "";
  return exp > new Date().toISOString();
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const appStateRef = useRef<AppStateStatus>(AppState.currentState);
  // Bind RevenueCat identity to the backend user id on EVERY auth path
  // (session-restore, sign-in, sign-up, sign-out). Errors surface via context.
  const purchaseIdentityError = useBindRevenueCatIdentity(user?.id ?? null);

  const refresh = useCallback(async () => {
    const tok = await getToken();
    if (!tok) { setUser(null); return; }
    try {
      // ALWAYS reconcile with the central backend first — cross-platform payments
      // (Web/Android/iOS/prior sessions) get applied to this user before /auth/me
      // reads the tier. Never trust local cache alone.
      try {
        await api<{ granted: unknown[] }>("/subscription/reconcile", { method: "POST", auth: true });
      } catch { /* non-fatal — /auth/me will still return the current state */ }
      const u = await api<User>("/auth/me", { auth: true });
      setUser(u);
    } catch {
      await clearToken();
      setUser(null);
    }
  }, []);

  /**
   * Backend-authoritative subscription check. Callers use this BEFORE showing
   * the paywall/checkout — if the backend already reports an active sub, we
   * skip the payment screens entirely and re-hydrate the local user object.
   */
  const syncSubscriptionFromBackend = useCallback(async (): Promise<SubscriptionStatus | null> => {
    const tok = await getToken();
    if (!tok) return null;
    try {
      // Reconcile first (applies any pending webhooks that missed us).
      try {
        await api<{ granted: unknown[] }>("/subscription/reconcile", { method: "POST", auth: true });
      } catch { /* keep going — status endpoint is still authoritative */ }
      const status = await api<SubscriptionStatus>("/subscription/status", { auth: true });
      // Re-hydrate user object so `tier`/`subscriptionExpiresAt` reflect backend.
      try {
        const u = await api<User>("/auth/me", { auth: true });
        setUser(u);
      } catch { /* status already returned — good enough */ }
      return status;
    } catch {
      return null;
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

    // Hot deep-links (native only) — Google Sign-In return
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

    // AppState listener: when the app returns to foreground (e.g. after the
    // user completed a Stripe/PayPal/MoMo payment in Safari or Chrome), we
    // immediately reconcile with the central backend so their new subscription
    // is applied without any user action. Also runs on Android/web.
    const appStateSub = AppState.addEventListener("change", (next) => {
      const prev = appStateRef.current;
      appStateRef.current = next;
      if (prev !== "active" && next === "active") {
        // fire-and-forget — refresh() itself calls /subscription/reconcile.
        refresh();
      }
    });

    // Web-only: also refresh on tab visibility change (returning from a Stripe
    // tab / PayPal window). AppState only fires 'active' reliably on native.
    let onVis: (() => void) | null = null;
    if (Platform.OS === "web" && typeof document !== "undefined") {
      onVis = () => { if (!document.hidden) refresh(); };
      document.addEventListener("visibilitychange", onVis);
    }

    return () => {
      try { sub?.remove?.(); } catch {}
      try { appStateSub?.remove?.(); } catch {}
      if (onVis && Platform.OS === "web" && typeof document !== "undefined") {
        try { document.removeEventListener("visibilitychange", onVis); } catch {}
      }
    };
  }, [refresh]);

  const requestOtp = async (phone: string) =>
    api<{ testCode?: string }>("/auth/otp/start", { method: "POST", body: { phone: toE164(phone) } });

  const verifyOtp = async (phone: string, code: string) => {
    const r = await api<{ accessToken: string; user: User }>("/auth/otp/verify", {
      method: "POST", body: { phone: toE164(phone), code },
    });
    await saveToken(r.accessToken);
    setUser(r.user);
    // Cross-platform: after sign-in, sync subscription from central backend so
    // any previous payment (any platform) unlocks the app immediately.
    try { await syncSubscriptionFromBackend(); } catch { /* non-fatal */ }
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
    if (sid) {
      await completeGoogle(sid, setUser);
      try { await syncSubscriptionFromBackend(); } catch { /* non-fatal */ }
    }
  };

  const loginWithApple = async () => {
    if (Platform.OS !== "ios") {
      throw new Error("Sign in with Apple is only available on iOS.");
    }
    // Lazy import so Android/web bundles don't crash on the missing native module.
    const AppleAuth = require("expo-apple-authentication");
    const available = await AppleAuth.isAvailableAsync();
    if (!available) {
      throw new Error("Sign in with Apple isn't available on this device.");
    }
    const credential = await AppleAuth.signInAsync({
      requestedScopes: [
        AppleAuth.AppleAuthenticationScope.FULL_NAME,
        AppleAuth.AppleAuthenticationScope.EMAIL,
      ],
    });
    const fullName = credential.fullName?.givenName
      ? `${credential.fullName.givenName}${credential.fullName.familyName ? " " + credential.fullName.familyName : ""}`
      : undefined;
    const r = await api<{ accessToken: string; user: User }>("/auth/apple", {
      method: "POST",
      body: {
        identityToken: credential.identityToken,
        authorizationCode: credential.authorizationCode || undefined,
        fullName,
        email: credential.email || undefined,
      },
    });
    await saveToken(r.accessToken);
    setUser(r.user);
    try { await syncSubscriptionFromBackend(); } catch { /* non-fatal */ }
  };

  const deleteAccount = async () => {
    await api("/auth/me", { method: "DELETE", auth: true });
    await clearToken();
    setUser(null);
  };

  const updateProfile = async (displayName: string) => {
    const u = await api<User>("/auth/me", { method: "PATCH", auth: true, body: { displayName } });
    setUser(u);
  };

  const logout = async () => {
    await clearToken();
    setUser(null);
  };

  const hasActiveSubscription = useMemo(() => isActiveTier(user), [user]);

  return (
    <AuthCtx.Provider value={{
      user, loading, purchaseIdentityError, hasActiveSubscription,
      requestOtp, verifyOtp, loginWithGoogle, loginWithApple,
      refresh, syncSubscriptionFromBackend, updateProfile, deleteAccount, logout,
    }}>
      {children}
    </AuthCtx.Provider>
  );
}

export const useAuth = () => {
  const v = useContext(AuthCtx);
  if (!v) throw new Error("useAuth outside provider");
  return v;
};
