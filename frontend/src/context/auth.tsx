import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api, saveToken, getToken, clearToken } from "../api";

export type User = {
  id: string;
  phone: string;
  displayName?: string | null;
  tier: "free" | "basic" | "premium";
  role?: "user" | "admin";
  subscriptionExpiresAt?: string | null;
};

type Ctx = {
  user: User | null;
  loading: boolean;
  requestOtp: (phone: string) => Promise<{ testCode?: string }>;
  verifyOtp: (phone: string, code: string) => Promise<void>;
  refresh: () => Promise<void>;
  updateProfile: (displayName: string) => Promise<void>;
  logout: () => Promise<void>;
};

const AuthCtx = createContext<Ctx | null>(null);

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
      await refresh();
      setLoading(false);
    })();
  }, [refresh]);

  const requestOtp = async (phone: string) => {
    return api<{ testCode?: string }>("/auth/otp/start", { method: "POST", body: { phone } });
  };

  const verifyOtp = async (phone: string, code: string) => {
    const r = await api<{ accessToken: string; user: User }>("/auth/otp/verify", {
      method: "POST", body: { phone, code },
    });
    await saveToken(r.accessToken);
    setUser(r.user);
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
    <AuthCtx.Provider value={{ user, loading, requestOtp, verifyOtp, refresh, updateProfile, logout }}>
      {children}
    </AuthCtx.Provider>
  );
}

export const useAuth = () => {
  const v = useContext(AuthCtx);
  if (!v) throw new Error("useAuth outside provider");
  return v;
};
