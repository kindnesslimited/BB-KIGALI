import { useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import * as Haptics from "expo-haptics";
import { colors, spacing, type, radius } from "@/src/theme";

type Plan = { id: string; tier: "basic" | "premium"; label: string; monthly: number; yearly: number; benefits: string[]; recommended?: boolean };

const PLANS: Plan[] = [
  {
    id: "basic",
    tier: "basic",
    label: "BASIC",
    monthly: 1000,
    yearly: 10000,
    benefits: ["Live radio (ad-supported)", "Access to all news", "Public podcasts"],
  },
  {
    id: "premium",
    tier: "premium",
    label: "PREMIUM",
    monthly: 3000,
    yearly: 30000,
    recommended: true,
    benefits: ["Ad-free live radio", "All premium VOD & podcasts", "Exclusive interviews", "Download for offline (soon)"],
  },
];

export default function Paywall() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [selectedTier, setSelectedTier] = useState<"basic" | "premium">("premium");
  const [period, setPeriod] = useState<"monthly" | "yearly">("monthly");

  const plan = PLANS.find((p) => p.tier === selectedTier)!;
  const price = period === "monthly" ? plan.monthly : plan.yearly;
  const planKey = `${selectedTier}_${period}` as const;

  const savings = plan.monthly * 12 - plan.yearly;

  const proceed = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {});
    router.push({ pathname: "/checkout", params: { plan: planKey, amount: String(price) } });
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }} testID="paywall-screen">
      <View style={[styles.top, { paddingTop: insets.top + spacing.md }]}>
        <Pressable onPress={() => router.back()} hitSlop={12} testID="paywall-close">
          <Ionicons name="close" size={28} color={colors.onSurface} />
        </Pressable>
        <View />
      </View>

      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 160 }}>
        <Text style={styles.h1}>UPGRADE YOUR{"\n"}LISTENING.</Text>
        <Text style={styles.sub}>Unlock exclusive shows, ad-free radio, and full VOD library.</Text>

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
                  <Text style={styles.price}>{displayPrice.toLocaleString()}</Text>
                  <Text style={styles.priceUnit}>RWF / {period === "monthly" ? "mo" : "yr"}</Text>
                </View>
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
          <Text style={styles.footerLabel}>TOTAL</Text>
          <Text style={styles.footerPrice}>{price.toLocaleString()} RWF</Text>
        </View>
        <Pressable onPress={proceed} style={styles.continueBtn} testID="paywall-continue">
          <Text style={styles.continueText}>CONTINUE</Text>
          <Ionicons name="arrow-forward" size={18} color={colors.onBrandPrimary} />
        </Pressable>
      </View>
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
  priceRow: { flexDirection: "row", alignItems: "baseline", gap: spacing.sm, marginBottom: spacing.md },
  price: { ...type.displayXL, fontSize: 38 },
  priceUnit: { ...type.bodyMuted, fontSize: 14 },
  benefit: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginTop: spacing.xs },
  benefitText: { ...type.body, fontSize: 13, color: colors.onSurfaceTertiary },
  footer: { position: "absolute", left: 0, right: 0, bottom: 0, backgroundColor: colors.surfaceSecondary, borderTopWidth: 1, borderTopColor: colors.border, flexDirection: "row", alignItems: "center", padding: spacing.lg, gap: spacing.md },
  footerLabel: { ...type.label, color: colors.onSurfaceSecondary },
  footerPrice: { ...type.displayLg, fontSize: 22 },
  continueBtn: { flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.xl, paddingVertical: spacing.md, borderRadius: radius.pill },
  continueText: { ...type.h2, color: colors.onBrandPrimary, letterSpacing: 1.5, fontSize: 14 },
});
