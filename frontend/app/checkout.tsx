import { useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, ActivityIndicator, TextInput, KeyboardAvoidingView, Platform } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import * as Haptics from "expo-haptics";
import { colors, spacing, type, radius } from "@/src/theme";
import { api } from "@/src/api";
import { useAuth } from "@/src/context/auth";

type Method = "stripe" | "paypal" | "mtn_momo" | "airtel";
const METHODS: { id: Method; label: string; sub: string; icon: any; needsPhone?: boolean }[] = [
  { id: "stripe", label: "Card (Stripe)", sub: "Visa, Mastercard, Amex", icon: "card-outline" },
  { id: "paypal", label: "PayPal", sub: "Pay with your PayPal balance", icon: "logo-paypal" },
  { id: "mtn_momo", label: "MTN Mobile Money", sub: "Rwanda MTN MoMo", icon: "phone-portrait-outline", needsPhone: true },
  { id: "airtel", label: "Airtel Money", sub: "Rwanda Airtel Money", icon: "phone-portrait-outline", needsPhone: true },
];

export default function Checkout() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { plan, amount } = useLocalSearchParams<{ plan: string; amount: string }>();
  const { refresh, user } = useAuth();
  const [method, setMethod] = useState<Method>("stripe");
  const [phone, setPhone] = useState(user?.phone || "+250");
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const pay = async () => {
    setErr(null); setLoading(true);
    try {
      const chosen = METHODS.find((m) => m.id === method)!;
      if (chosen.needsPhone && phone.replace(/\D/g, "").length < 9) {
        throw new Error("Enter a valid phone number for mobile money");
      }
      await api("/billing/subscribe", { method: "POST", auth: true, body: { plan, method, phone: chosen.needsPhone ? phone : null } });
      await refresh();
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
      setSuccess(true);
    } catch (e: any) {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error).catch(() => {});
      setErr(e.message || "Payment failed");
    } finally { setLoading(false); }
  };

  if (success) {
    return (
      <View style={styles.successWrap} testID="checkout-success">
        <View style={styles.successIcon}>
          <Ionicons name="checkmark" size={56} color={colors.onBrandPrimary} />
        </View>
        <Text style={styles.successTitle}>YOU&apos;RE IN</Text>
        <Text style={styles.successSub}>Your subscription is now active. Enjoy BB FM Kigali!</Text>
        <Pressable onPress={() => router.replace("/(tabs)")} style={styles.doneBtn} testID="checkout-done">
          <Text style={styles.doneText}>START LISTENING</Text>
        </Pressable>
      </View>
    );
  }

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.top, { paddingTop: insets.top + spacing.md }]}>
        <Pressable onPress={() => router.back()} hitSlop={12} testID="checkout-back">
          <Ionicons name="chevron-back" size={28} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.topTitle}>CHECKOUT</Text>
        <View style={{ width: 28 }} />
      </View>

      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 160 }} testID="checkout-screen">
        <View style={styles.summary}>
          <Text style={styles.summaryLabel}>YOU&apos;RE PAYING FOR</Text>
          <Text style={styles.summaryPlan}>{String(plan || "").replace("_", " ").toUpperCase()}</Text>
          <Text style={styles.summaryAmount}>{Number(amount).toLocaleString()} RWF</Text>
        </View>

        <Text style={styles.sectionLabel}>PAYMENT METHOD</Text>
        <View style={{ gap: spacing.sm }}>
          {METHODS.map((m) => {
            const active = method === m.id;
            return (
              <Pressable
                key={m.id}
                onPress={() => { Haptics.selectionAsync().catch(() => {}); setMethod(m.id); }}
                style={[styles.methodRow, active && styles.methodRowActive]}
                testID={`method-${m.id}`}
              >
                <View style={styles.methodIcon}>
                  <Ionicons name={m.icon} size={22} color={active ? colors.brandPrimary : colors.onSurface} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.methodLabel}>{m.label}</Text>
                  <Text style={styles.methodSub}>{m.sub}</Text>
                </View>
                <View style={[styles.radio, active && styles.radioActive]}>
                  {active && <View style={styles.radioDot} />}
                </View>
              </Pressable>
            );
          })}
        </View>

        {METHODS.find((m) => m.id === method)?.needsPhone && (
          <View style={{ marginTop: spacing.lg }}>
            <Text style={styles.sectionLabel}>MOBILE MONEY NUMBER</Text>
            <TextInput
              testID="momo-phone-input"
              value={phone}
              onChangeText={setPhone}
              keyboardType="phone-pad"
              placeholder="+250 78x xxx xxx"
              placeholderTextColor={colors.onSurfaceSecondary}
              style={styles.momoInput}
            />
          </View>
        )}

        <View style={styles.demoBox}>
          <Ionicons name="information-circle-outline" size={16} color={colors.warning} />
          <Text style={styles.demoText}>Demo mode — payments are simulated. No real charge will occur.</Text>
        </View>

        {err && <Text style={styles.err} testID="checkout-error">{err}</Text>}
      </ScrollView>

      <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.md }]}>
        <Pressable onPress={pay} disabled={loading} style={[styles.payBtn, loading && { opacity: 0.6 }]} testID="pay-btn">
          {loading ? <ActivityIndicator color={colors.onBrandPrimary} /> : (
            <>
              <Ionicons name="lock-closed" size={16} color={colors.onBrandPrimary} />
              <Text style={styles.payText}>PAY {Number(amount).toLocaleString()} RWF</Text>
            </>
          )}
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  top: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  topTitle: { ...type.h2, letterSpacing: 1.5 },
  summary: { backgroundColor: colors.brandTertiary, borderRadius: radius.md, padding: spacing.lg, marginBottom: spacing.xl, borderWidth: 1, borderColor: colors.brandPrimary },
  summaryLabel: { ...type.label, color: colors.brandPrimary, letterSpacing: 2 },
  summaryPlan: { ...type.h2, color: colors.onBrandTertiary, marginTop: 4, fontSize: 16 },
  summaryAmount: { ...type.displayXL, fontSize: 36, marginTop: spacing.sm },
  sectionLabel: { ...type.label, letterSpacing: 1.5, marginBottom: spacing.sm, color: colors.onSurfaceSecondary },
  methodRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1.5, borderColor: colors.border },
  methodRowActive: { borderColor: colors.brandPrimary },
  methodIcon: { width: 44, height: 44, borderRadius: radius.sm, backgroundColor: colors.surfaceTertiary, alignItems: "center", justifyContent: "center" },
  methodLabel: { ...type.h2, fontSize: 15 },
  methodSub: { ...type.caption, marginTop: 2 },
  radio: { width: 22, height: 22, borderRadius: 11, borderWidth: 2, borderColor: colors.border, alignItems: "center", justifyContent: "center" },
  radioActive: { borderColor: colors.brandPrimary },
  radioDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: colors.brandPrimary },
  momoInput: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.md, color: colors.onSurface, fontSize: 16, borderWidth: 1, borderColor: colors.border },
  demoBox: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginTop: spacing.lg, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.md, borderWidth: 1, borderColor: colors.warning },
  demoText: { ...type.caption, flex: 1, color: colors.onSurfaceTertiary },
  err: { color: colors.error, marginTop: spacing.md, textAlign: "center" },
  footer: { position: "absolute", left: 0, right: 0, bottom: 0, backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.border, padding: spacing.lg },
  payBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, backgroundColor: colors.brandPrimary, height: 56, borderRadius: radius.md },
  payText: { ...type.h2, color: colors.onBrandPrimary, letterSpacing: 1.5, fontSize: 15 },
  successWrap: { flex: 1, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center", padding: spacing.xl, gap: spacing.md },
  successIcon: { width: 100, height: 100, borderRadius: 50, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", marginBottom: spacing.lg },
  successTitle: { ...type.displayXL, letterSpacing: 2 },
  successSub: { ...type.bodyMuted, textAlign: "center", marginBottom: spacing.xl, lineHeight: 22 },
  doneBtn: { backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.xxl, paddingVertical: spacing.md, borderRadius: radius.pill },
  doneText: { ...type.h2, color: colors.onBrandPrimary, letterSpacing: 1.5, fontSize: 14 },
});
