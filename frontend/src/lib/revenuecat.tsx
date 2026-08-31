/**
 * RevenueCat (Emergent-managed) — subscription SDK wrapper.
 *
 * Rules (enforced in code and in comments):
 *  - Never initialize the SDK inside a React component. See `initializeRevenueCat()` which
 *    is called at module scope from `app/_layout.tsx`.
 *  - Never fake-grant `pro`; the SDK's `customerInfo.entitlements.active.pro` is the
 *    sole source of truth on-device.
 *  - Never hardcode product IDs or prices — always read from `offerings.current.availablePackages`.
 *  - `Purchases.logIn(user.id)` runs on EVERY auth path (see `useBindRevenueCatIdentity` below).
 *  - A purchase is blocked while `originalAppUserId` starts with `$RCAnonymousID:`.
 */
import React, { createContext, useContext, useEffect, useRef, useState } from "react";
import { Platform } from "react-native";
import Purchases, { LOG_LEVEL } from "react-native-purchases";
import type { CustomerInfo, PurchasesPackage } from "react-native-purchases";
import { useMutation, useQuery, useQueryClient, QueryClient, QueryClientProvider } from "@tanstack/react-query";

const REVENUECAT_TEST_API_KEY = process.env.EXPO_PUBLIC_REVENUECAT_TEST_API_KEY;
const REVENUECAT_IOS_API_KEY = process.env.EXPO_PUBLIC_REVENUECAT_IOS_API_KEY;
const REVENUECAT_ANDROID_API_KEY = process.env.EXPO_PUBLIC_REVENUECAT_ANDROID_API_KEY;

export const REVENUECAT_ENTITLEMENT_IDENTIFIER = "pro";

// SDK is available on native iOS/Android, and via Browser Mode (`purchases-js`) on web
// during development for testing. It is disabled in production web builds.
export const rcEnabled = Platform.OS !== "web" || __DEV__;

function getRevenueCatApiKey(): string {
  if (!REVENUECAT_TEST_API_KEY || !REVENUECAT_IOS_API_KEY || !REVENUECAT_ANDROID_API_KEY) {
    throw new Error(
      "RevenueCat public API keys not found — check EXPO_PUBLIC_REVENUECAT_* env vars",
    );
  }
  // Expo Go / dev / web preview → Test Store
  if (Platform.OS === "web" || __DEV__) return REVENUECAT_TEST_API_KEY;
  if (Platform.OS === "ios") return REVENUECAT_IOS_API_KEY;
  if (Platform.OS === "android") return REVENUECAT_ANDROID_API_KEY;
  return REVENUECAT_TEST_API_KEY;
}

/** MUST be called ONCE at module scope from app/_layout.tsx before any component renders. */
export function initializeRevenueCat(): void {
  if (!rcEnabled) return;
  Purchases.setLogLevel(__DEV__ ? LOG_LEVEL.DEBUG : LOG_LEVEL.WARN);
  Purchases.configure({ apiKey: getRevenueCatApiKey() });
}

// ---------- QueryClient (used by the SubscriptionProvider) ----------
const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 60 * 1000 },
  },
});

export function AppQueryClientProvider({ children }: { children: React.ReactNode }) {
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

// ---------- Subscription context ----------
function useSubscriptionContext() {
  const qc = useQueryClient();

  const customerInfoQuery = useQuery({
    queryKey: ["revenuecat", "customer-info"],
    queryFn: () => Purchases.getCustomerInfo(),
    enabled: rcEnabled,
    staleTime: 60 * 1000,
  });

  const offeringsQuery = useQuery({
    queryKey: ["revenuecat", "offerings"],
    queryFn: () => Purchases.getOfferings(),
    enabled: rcEnabled,
    staleTime: 5 * 60 * 1000,
  });

  useEffect(() => {
    if (!rcEnabled) return;
    const listener = (info: CustomerInfo) =>
      qc.setQueryData(["revenuecat", "customer-info"], info);
    Purchases.addCustomerInfoUpdateListener(listener);
    return () => {
      try { Purchases.removeCustomerInfoUpdateListener(listener); } catch { /* noop */ }
    };
  }, [qc]);

  const purchaseMutation = useMutation({
    mutationFn: async (packageToPurchase: PurchasesPackage) => {
      const id = (await Purchases.getCustomerInfo()).originalAppUserId;
      if (id.startsWith("$RCAnonymousID:")) throw new Error("identity_not_ready");

      // Guard: never charge someone who already has an active subscription on
      // ANY platform (Stripe/PayPal/MoMo/other IAP). This is what "one purchase,
      // any platform, unlocks everywhere" looks like on the mobile side.
      try {
        const { api } = await import("../api");
        const status = await api<{ active: boolean; tier?: string; subscriptionExpiresAt?: string }>(
          "/subscription/status",
          { auth: true },
        );
        if (status?.active) {
          throw new Error(
            `You already have an active ${status.tier || "premium"} subscription until ${(status.subscriptionExpiresAt || "").slice(0, 10)}. No need to buy again.`,
          );
        }
      } catch (e: any) {
        // If the pre-flight check itself failed AND it wasn't the "already active"
        // guard message, proceed with the purchase (better UX than blocking on a
        // network hiccup — RevenueCat webhook + reconcile still keeps state honest).
        if (String(e?.message || "").startsWith("You already have an active")) throw e;
      }

      const { customerInfo } = await Purchases.purchasePackage(packageToPurchase);
      return customerInfo;
    },
  });

  const restoreMutation = useMutation({
    mutationFn: () => Purchases.restorePurchases(),
  });

  const isSubscribed =
    customerInfoQuery.data?.entitlements.active?.[REVENUECAT_ENTITLEMENT_IDENTIFIER] !== undefined;

  const originalAppUserId = customerInfoQuery.data?.originalAppUserId;
  const identityReady =
    !!originalAppUserId && !originalAppUserId.startsWith("$RCAnonymousID:");

  return {
    customerInfo: customerInfoQuery.data,
    offerings: offeringsQuery.data,
    isSubscribed,
    identityReady,
    isLoading: customerInfoQuery.isLoading || offeringsQuery.isLoading,
    error: customerInfoQuery.error || offeringsQuery.error || null,
    purchase: purchaseMutation.mutateAsync,
    restore: restoreMutation.mutateAsync,
    isPurchasing: purchaseMutation.isPending,
    isRestoring: restoreMutation.isPending,
    refresh: () => {
      qc.invalidateQueries({ queryKey: ["revenuecat"] });
    },
  };
}

type SubscriptionContextValue = ReturnType<typeof useSubscriptionContext>;
const Ctx = createContext<SubscriptionContextValue | null>(null);

export function SubscriptionProvider({ children }: { children: React.ReactNode }) {
  const value = useSubscriptionContext();
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSubscription() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useSubscription must be used within a SubscriptionProvider");
  return v;
}

// ---------- Identity binding ----------
/** Call at top of AuthProvider to bind RevenueCat identity to the backend user id.
 *  Runs on EVERY auth path: session-restore, sign-in, sign-up, sign-out.
 *  MUST NOT swallow errors — any failure is surfaced via `purchaseIdentityError`.
 */
export function useBindRevenueCatIdentity(userId: string | null | undefined): string | null {
  const [purchaseIdentityError, setError] = useState<string | null>(null);
  const bound = useRef<string | null>(null);

  useEffect(() => {
    if (!rcEnabled) return;
    (async () => {
      try {
        if (userId && bound.current !== userId) {
          const { customerInfo } = await Purchases.logIn(userId);
          bound.current = userId;
          if (__DEV__) {
            console.log("[RevenueCat] identity bound:", customerInfo.originalAppUserId);
          }
          setError(null);
        } else if (!userId && bound.current) {
          await Purchases.logOut();
          bound.current = null;
          setError(null);
        }
      } catch (e: any) {
        // NEVER swallow — surfaces in UI as a purchase-blocker banner.
        setError(String(e?.message || e));
      }
    })();
  }, [userId]);

  return purchaseIdentityError;
}
