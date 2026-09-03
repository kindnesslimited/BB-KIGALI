import { useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, Modal, Platform, ActivityIndicator } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import * as Haptics from "expo-haptics";
import { colors, spacing, type, radius } from "@/src/theme";
import { useSubscription, rcEnabled } from "@/src/lib/revenuecat";
import { useAuth } from "@/src/context/auth";
import { api } from "@/src/api";

/**
 * Cross-platform payment routing.
 *
 * Business rule (per product owner Sep 2026):
 * "If a user has already paid on ANY platform (web/Android/iOS/previously),
 *  give them full access immediately. Never charge them again."
 *
 * Therefore ALL platforms route through /checkout (Stripe/PayPal/MoMo) — no
 * IAP-only gating on iOS. RevenueCat identity binding is kept so historical
 * Apple IAP purchases can still be RESTORED, but new purchases on iOS go
 * through the same central backend flow as web/Android.
 */

type Plan = { id: string; tier: "basic" | "premium"; label: string; monthly: number; yearly: number; monthlyEur: number; yearlyEur: number; benefits: string[]; recommended?: boolean };

const PLANS: Plan[] = [
  {
    id: "basic",
    tier: "basic",
    label: "BASIC",
    monthly: 1000,
    yearly: 10000,
    monthlyEur: 1,
    yearlyEur: 10,
    benefits: ["24/7 Live Radio access", "Access to all news", "Public podcasts"],
  },
  {
    id: "premium",
    tier: "premium",
    label: "PREMIUM",
    monthly: 3000,
    yearly: 30000,
    monthlyEur: 3,
    yearlyEur: 30,
    recommended: true,
    benefits: ["24/7 Live Radio · ad-free", "ALL VOD & podcasts included", "Live video & exclusive interviews", "Download for offline (soon)"],
  },
];

export default function Paywall() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user, purchaseIdentityError, syncSubscriptionFromBackend, hasActiveSubscription } = useAuth();
  const {
    offerings,
    isSubscribed,
    identityReady,
    purchase,
    restore,
    isPurchasing,
    isRestoring,
  } = useSubscription();
  const [selectedTier, setSelectedTier] = useState<"basic" | "premium">("premium");
  const [period, setPeriod] = useState<"monthly" | "yearly">("monthly");
  const [rcConfirm, setRcConfirm] = useState<{ visible: boolean; error?: string; success?: boolean }>({ visible: false });
  const [rcBusyLabel, setRcBusyLabel] = useState<string | null>(null);
  const [prechecking, setPrechecking] = useState(true);

  // Backend-first precheck: if the central backend already reports an active
  // subscription (paid on ANY platform — web/Android/iOS/prior device), skip
  // the paywall entirely. Runs on every mount so cached local state can't
  // trick us into charging someone twice.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!user) { setPrechecking(false); return; }
      try {
        const status = await syncSubscriptionFromBackend();
        if (!cancelled && status?.active) {
          router.replace("/(tabs)");
          return;
        }
      } catch { /* fall through — show the paywall */ }
      if (!cancelled) setPrechecking(false);
    })();
    return () => { cancelled = true; };
    // Only run once on mount (or when user changes identity).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id]);

  // Extra safety: if hasActiveSubscription becomes true after any refresh
  // (e.g. AppState listener reconciled a webhook), bounce out immediately.
  useEffect(() => {
    if (hasActiveSubscription) router.replace("/(tabs)");
  }, [hasActiveSubscription, router]);

  const plan = PLANS.find((p) => p.tier === selectedTier)!;
  const price = period === "monthly" ? plan.monthly : plan.yearly;
  const priceEur = period === "monthly" ? plan.monthlyEur : plan.yearlyEur;
  const planKey = `${selectedTier}_${period}` as const;

  const savings = plan.monthly * 12 - plan.yearly;

  // Resolve the RevenueCat package matching the current selection.
  // NOTE: We no longer force iOS through RevenueCat — per the product-owner
  // directive, all platforms route through the central backend (Stripe/PayPal/
  // MoMo). RevenueCat identity + package data are only kept so historical
  // Apple IAP subscribers can RESTORE their previous purchase on iOS.
  const rcOffering = offerings?.current;
  const rcPackage = (() => {
    if (!rcOffering) return null;
    return period === "monthly"
      ? rcOffering.availablePackages.find((p) => p.identifier === "$rc_monthly")
      : rcOffering.availablePackages.find((p) => p.identifier === "$rc_annual");
  })();

  // Restore button is only useful on iOS where legacy Apple IAP receipts exist.
  const rcRestoreAvailable = Platform.OS === "ios" && rcEnabled && !!rcPackage;
  // All new purchases (any platform) go through /checkout — never RC.
  const rcAvailable = false;
  const rcPriceString: string | undefined = undefined;

  const proceed = async () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {});

    if (!user) {
      router.replace("/auth/phone");
      return;
    }

    // Belt-and-suspenders: re-check backend one more time RIGHT before the
    // payment screen opens. If the user got granted access via a webhook in
    // the last few seconds, we don't want to charge them again.
    try {
      const status = await syncSubscriptionFromBackend();
      if (status?.active) {
        router.replace("/(tabs)");
        return;
      }
    } catch { /* proceed to checkout */ }

    // ALL platforms (iOS, Android, Web) → central checkout page with the same
    // Stripe/PayPal/MoMo options.
    //
    // Android modal-on-modal bug: expo-router `push()` from an already-open
    // modal (paywall) to another modal (checkout) is silently ignored on
    // Android in some cases (the second modal never appears). Using
    // `router.replace()` swaps the paywall out for the checkout screen so
    // the transition is a single modal push, which is reliable on all
    // platforms.
    router.replace({ pathname: "/checkout", params: { plan: planKey, amount: String(price) } });
  };

  const onRestore = async () => {
    try {
      setRcBusyLabel("Restoring purchases…");
      // 1) Restore legacy Apple IAP receipts through RevenueCat (iOS only).
      if (Platform.OS === "ios" && rcEnabled) {
        try { await restore(); } catch { /* non-fatal — fall through to backend sync */ }
      }
      // 2) ALWAYS reconcile with the central backend — this is the source of
      //    truth for cross-platform subscriptions (web/Android/iOS/prior).
      await api("/subscription/rc-sync", {
        method: "POST", auth: true,
        body: { plan: `premium_${period}`, entitlement: "pro" },
      }).catch(() => { /* rc-sync is best-effort; reconcile below is authoritative */ });
      const status = await syncSubscriptionFromBackend();
      if (status?.active) {
        setRcConfirm({ visible: true, success: true });
      } else {
        setRcConfirm({ visible: true, error: "No active subscription found on this account. If you paid recently, please wait a moment and try again." });
      }
    } catch (e: any) {
      setRcConfirm({ visible: true, error: String(e?.message || e) });
    } finally {
      setRcBusyLabel(null);
    }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }} testID="paywall-screen">
      {prechecking && (
        <View style={styles.precheckOverlay} testID="paywall-precheck">
          <ActivityIndicator size="large" color={colors.brandPrimary} />
          <Text style={styles.precheckText}>Checking your subscription…</Text>
        </View>
      )}
      <View style={[styles.top, { paddingTop: insets.top + spacing.md }]}>
        <Pressable onPress={() => router.back()} hitSlop={12} testID="paywall-close">
          <Ionicons name="close" size={28} color={colors.onSurface} />
        </Pressable>
        <View />
      </View>

      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 160 }}>
        <Text style={styles.h1}>UNLOCK{"\n"}BB FM KIGALI.</Text>
        <Text style={styles.sub}>Live radio, on-demand shows and premium video — for paying members only.</Text>

        {/* Period toggle */}
        <View style={styles.toggle}>
          {(["monthly", "yearly"] as const).map((p) => (
            <Pressable
              key={p}
              onPress={() => { Haptics.selectionAsync().catch(() => {}); setPeriod(p); }}
              style={[styles.toggleBtn, period === p && styles.toggleBtnActive]}
              testID={`period-${p}`}
            >
              <Text style={[styles.toggleText, period === p && styles.toggleTextActive]}>
                {p === "monthly" ? "MONTHLY" : "YEARLY"}
              </Text>
              {p === "yearly" && (
                <View style={styles.saveTag}>
                  <Text style={styles.saveTagText}>SAVE {Math.round((savings / (plan.monthly * 12)) * 100)}%</Text>
                </View>
              )}
            </Pressable>
          ))}
        </View>

        {/* Plans */}
        <View style={{ gap: spacing.md }}>
          {PLANS.map((p) => {
            const active = selectedTier === p.tier;
            const displayPrice = period === "monthly" ? p.monthly : p.yearly;
            const displayEur = period === "monthly" ? p.monthlyEur : p.yearlyEur;
            return (
              <Pressable
                key={p.id}
                onPress={() => { Haptics.selectionAsync().catch(() => {}); setSelectedTier(p.tier); }}
                style={[
                  styles.planCard,
                  active && styles.planCardActive,
                  p.recommended && !active && { borderColor: colors.brandSecondary },
                ]}
                testID={`plan-${p.tier}`}
              >
                <View style={styles.planHead}>
                  <Text style={[styles.planLabel, active && { color: colors.brandPrimary }]}>{p.label}</Text>
                  {p.recommended && (
                    <View style={styles.recBadge}>
                      <Text style={styles.recBadgeText}>RECOMMENDED</Text>
                    </View>
                  )}
                  <View style={[styles.radio, active && styles.radioActive]}>
                    {active && <View style={styles.radioDot} />}
                  </View>
                </View>
                <View style={styles.priceRow}>
                  <Text style={styles.price}>{displayEur}€</Text>
                  <Text style={styles.priceUnit}>/ {displayPrice.toLocaleString()} RWF</Text>
                  <Text style={[styles.priceUnit, { marginLeft: "auto" }]}>per {period === "monthly" ? "month" : "year"}</Text>
                </View>
                <Text style={styles.parallelHint}>Card charges in EUR · MoMo charges in RWF</Text>
                {p.benefits.map((b, i) => (
                  <View key={i} style={styles.benefit}>
                    <Ionicons name="checkmark-circle" size={16} color={colors.brandPrimary} />
                    <Text style={styles.benefitText}>{b}</Text>
                  </View>
                ))}
              </Pressable>
            );
          })}
        </View>
      </ScrollView>

      <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.md }]}>
        <View style={{ flex: 1 }}>
          <Text style={styles.footerLabel}>{rcAvailable ? "APPLE IAP" : "TOTAL"}</Text>
          <Text style={styles.footerPrice}>
            {rcAvailable && rcPriceString
              ? rcPriceString
              : `${priceEur}€ / ${price.toLocaleString()} RWF`}
          </Text>
          {rcAvailable && (
            <Text style={styles.iapHint} numberOfLines={2}>
              Apple bills your Apple ID{selectedTier === "basic" ? " • iOS grants full Premium" : ""}
            </Text>
          )}
        </View>
        <Pressable
          onPress={proceed}
          disabled={isPurchasing || isRestoring}
          style={[styles.continueBtn, (isPurchasing || isRestoring) && { opacity: 0.5 }]}
          testID="paywall-continue"
        >
          {isPurchasing ? (
            <ActivityIndicator color={colors.onBrandPrimary} />
          ) : (
            <>
              <Text style={styles.continueText}>CONTINUE</Text>
              <Ionicons name="arrow-forward" size={18} color={colors.onBrandPrimary} />
            </>
          )}
        </Pressable>
      </View>

      {/* iOS-only: Apple requires a Restore Purchases entry point for legacy IAP receipts.
          For non-iOS platforms, this same button reconciles with the central backend. */}
      {rcRestoreAvailable && (
        <Pressable
          onPress={onRestore}
          disabled={isPurchasing || isRestoring}
          style={[styles.restoreBtn, { bottom: insets.bottom + 96 }]}
          testID="paywall-restore"
        >
          <Ionicons name="refresh" size={14} color={colors.onSurfaceSecondary} />
          <Text style={styles.restoreText}>
            {isRestoring ? "Restoring…" : "Restore purchases"}
          </Text>
        </Pressable>
      )}

      {/* Confirmation modal (success or error) */}
      <Modal transparent visible={rcConfirm.visible} animationType="fade" onRequestClose={() => setRcConfirm({ visible: false })}>
        <View style={styles.modalOverlay}>
          <View style={styles.modalCard}>
            <Ionicons
              name={rcConfirm.success ? "checkmark-circle" : rcConfirm.error ? "alert-circle" : "hourglass"}
              size={44}
              color={rcConfirm.success ? colors.brandPrimary : rcConfirm.error ? colors.brandSecondary : colors.onSurfaceSecondary}
            />
            <Text style={styles.modalTitle}>
              {rcConfirm.success ? "You're Premium!" : rcConfirm.error ? "Purchase issue" : "Preparing…"}
            </Text>
            <Text style={styles.modalBody}>
              {rcConfirm.success
                ? "Your Apple subscription is active. Enjoy ad-free radio and full VOD."
                : rcConfirm.error || "Setting up your account for Apple purchases."}
            </Text>
            <Pressable
              onPress={() => {
                setRcConfirm({ visible: false });
                if (rcConfirm.success) router.back();
              }}
              style={styles.modalBtn}
            >
              <Text style={styles.modalBtnText}>{rcConfirm.success ? "DONE" : "OK"}</Text>
            </Pressable>
          </View>
        </View>
      </Modal>

      {rcBusyLabel && !isPurchasing && !isRestoring && (
        <View style={[styles.toast, { pointerEvents: "none" }]}>
          <Text style={styles.toastText}>{rcBusyLabel}</Text>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  top: { flexDirection: "row", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  h1: { ...type.displayXL, fontSize: 34, lineHeight: 38, marginBottom: spacing.sm },
  sub: { ...type.bodyMuted, marginBottom: spacing.xl, lineHeight: 22 },
  toggle: { flexDirection: "row", backgroundColor: colors.surfaceSecondary, borderRadius: radius.pill, padding: 4, marginBottom: spacing.lg, borderWidth: 1, borderColor: colors.border },
  toggleBtn: { flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, paddingVertical: spacing.md, borderRadius: radius.pill },
  toggleBtnActive: { backgroundColor: colors.brandPrimary },
  toggleText: { ...type.label, color: colors.onSurfaceSecondary, letterSpacing: 1.5 },
  toggleTextActive: { color: colors.onBrandPrimary },
  saveTag: { backgroundColor: colors.brandTertiary, paddingHorizontal: 6, paddingVertical: 2, borderRadius: radius.sm },
  saveTagText: { color: colors.brandPrimary, fontFamily: "BarlowCondensed-Bold", fontSize: 9 },
  planCard: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.lg, borderWidth: 1.5, borderColor: colors.border },
  planCardActive: { borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary },
  planHead: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginBottom: spacing.sm },
  planLabel: { ...type.displayMd, letterSpacing: 1, flex: 1 },
  recBadge: { backgroundColor: colors.brandSecondary, paddingHorizontal: 8, paddingVertical: 3, borderRadius: radius.sm },
  recBadgeText: { color: "#fff", fontFamily: "BarlowCondensed-Bold", fontSize: 9, letterSpacing: 1.5 },
  radio: { width: 22, height: 22, borderRadius: 11, borderWidth: 2, borderColor: colors.border, alignItems: "center", justifyContent: "center" },
  radioActive: { borderColor: colors.brandPrimary },
  radioDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: colors.brandPrimary },
  priceRow: { flexDirection: "row", alignItems: "baseline", gap: spacing.sm, marginBottom: 4 },
  price: { ...type.displayXL, fontSize: 38 },
  priceUnit: { ...type.bodyMuted, fontSize: 13 },
  parallelHint: { ...type.caption, color: colors.brandPrimary, marginBottom: spacing.md, fontSize: 11 },
  benefit: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginTop: spacing.xs },
  benefitText: { ...type.body, fontSize: 13, color: colors.onSurfaceTertiary },
  footer: { position: "absolute", left: 0, right: 0, bottom: 0, backgroundColor: colors.surfaceSecondary, borderTopWidth: 1, borderTopColor: colors.border, flexDirection: "row", alignItems: "center", padding: spacing.lg, gap: spacing.md },
  footerLabel: { ...type.label, color: colors.onSurfaceSecondary },
  footerPrice: { ...type.displayLg, fontSize: 22 },
  continueBtn: { flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.xl, paddingVertical: spacing.md, borderRadius: radius.pill },
  continueText: { ...type.h2, color: colors.onBrandPrimary, letterSpacing: 1.5, fontSize: 14 },
  iapHint: { ...type.caption, fontSize: 10, color: colors.onSurfaceSecondary, marginTop: 2 },
  restoreBtn: { position: "absolute", left: 0, right: 0, alignItems: "center", flexDirection: "row", justifyContent: "center", gap: 6, paddingVertical: spacing.sm },
  restoreText: { ...type.caption, color: colors.onSurfaceSecondary, textDecorationLine: "underline" },
  modalOverlay: { flex: 1, backgroundColor: "rgba(0,0,0,0.7)", alignItems: "center", justifyContent: "center", padding: spacing.lg },
  modalCard: { width: "100%", maxWidth: 360, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.xl, alignItems: "center", gap: spacing.md, borderWidth: 1, borderColor: colors.border },
  modalTitle: { ...type.displayLg, fontSize: 22, textAlign: "center" },
  modalBody: { ...type.body, textAlign: "center", color: colors.onSurfaceTertiary, lineHeight: 20 },
  modalBtn: { backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.xl, paddingVertical: spacing.md, borderRadius: radius.pill, marginTop: spacing.sm },
  modalBtnText: { ...type.h2, color: colors.onBrandPrimary, letterSpacing: 1.5, fontSize: 13 },
  toast: { position: "absolute", top: 80, left: spacing.lg, right: spacing.lg, backgroundColor: "rgba(0,0,0,0.85)", borderRadius: radius.sm, padding: spacing.md, alignItems: "center" },
  toastText: { ...type.caption, color: "#fff" },
  precheckOverlay: {
    position: "absolute", top: 0, left: 0, right: 0, bottom: 0, zIndex: 100,
    backgroundColor: colors.surface,
    alignItems: "center", justifyContent: "center", gap: spacing.md,
  },
  precheckText: { ...type.bodyMuted, color: colors.onSurfaceSecondary, letterSpacing: 0.5 },
});
