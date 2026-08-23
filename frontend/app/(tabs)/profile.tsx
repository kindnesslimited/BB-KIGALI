import { useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, Alert, Linking } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { colors, spacing, type, radius } from "@/src/theme";
import { useAuth } from "@/src/context/auth";
import { api } from "@/src/api";

type Payment = { id: string; planLabel: string; amount: number; currency: string; method: string; status: string; createdAt: string };

const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL || "";
const PRIVACY_URL = `${BACKEND_URL}/api/privacy`;

const TIER_META: Record<string, { label: string; color: string }> = {
  free: { label: "Free", color: colors.onSurfaceSecondary },
  basic: { label: "Basic", color: colors.warning },
  premium: { label: "Premium", color: colors.brandPrimary },
};

export default function Profile() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user, logout, refresh, deleteAccount } = useAuth();
  const [payments, setPayments] = useState<Payment[]>([]);

  useEffect(() => {
    refresh();
    (async () => { try { setPayments(await api<Payment[]>("/billing/history", { auth: true })); } catch {} })();
  }, []);

  if (!user) {
    return (
      <ScrollView
        style={{ flex: 1, backgroundColor: colors.surface }}
        contentContainerStyle={{ paddingTop: insets.top + spacing.md, paddingBottom: 220, paddingHorizontal: spacing.lg }}
        testID="profile-guest"
      >
        <View style={styles.header}>
          <Text style={styles.title}>ACCOUNT</Text>
        </View>
        <View style={[styles.userCard, { flexDirection: "column", alignItems: "center", paddingVertical: spacing.xl, marginHorizontal: 0, gap: spacing.sm }]}>
          <Ionicons name="person-circle-outline" size={72} color={colors.brandPrimary} />
          <Text style={[type.h2, { marginTop: spacing.md, textAlign: "center" }]}>
            Sign in to unlock premium content
          </Text>
          <Text style={[type.bodyMuted, { marginTop: spacing.sm, textAlign: "center", paddingHorizontal: spacing.md }]}>
            Browse everything for free. Sign in only when you want to listen live, watch a show, or subscribe.
          </Text>
          <Pressable
            onPress={() => router.push("/auth/phone")}
            style={[styles.signOutBtn, { backgroundColor: colors.brandPrimary, marginTop: spacing.lg, paddingHorizontal: spacing.xl }]}
            testID="profile-guest-signin"
          >
            <Ionicons name="log-in-outline" size={18} color={colors.onBrandPrimary} />
            <Text style={[styles.signOutText, { color: colors.onBrandPrimary }]}>SIGN IN WITH PHONE</Text>
          </Pressable>
        </View>
      </ScrollView>
    );
  }
  const tier = TIER_META[user.tier] || TIER_META.free;
  const exp = user.subscriptionExpiresAt ? new Date(user.subscriptionExpiresAt) : null;

  const doLogout = () => {
    Alert.alert("Sign out?", "You will need to verify your phone again.", [
      { text: "Cancel", style: "cancel" },
      { text: "Sign out", style: "destructive", onPress: async () => { await logout(); router.replace("/onboarding"); } },
    ]);
  };

  const openPrivacy = async () => {
    try { await Linking.openURL(PRIVACY_URL); } catch { Alert.alert("Privacy Policy", "Please visit https://bbkigali.com/privacy"); }
  };

  const doDelete = () => {
    // Two-step confirmation to match Apple's 5.1.1(v) guideline.
    Alert.alert(
      "Delete Account",
      "This permanently removes your account, profile, session, and subscription. Your payment history is anonymized for accounting. This action cannot be undone.",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Delete Account",
          style: "destructive",
          onPress: () => {
            Alert.alert(
              "Are you absolutely sure?",
              "This is your last chance to cancel. Tap 'Yes, delete' to permanently remove your account.",
              [
                { text: "Cancel", style: "cancel" },
                {
                  text: "Yes, delete",
                  style: "destructive",
                  onPress: async () => {
                    try {
                      await deleteAccount();
                      Alert.alert("Account deleted", "Your account has been removed.");
                      router.replace("/(tabs)");
                    } catch (e: any) {
                      Alert.alert("Delete failed", e?.message || "Please try again.");
                    }
                  },
                },
              ]
            );
          },
        },
      ]
    );
  };

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.surface }}
      contentContainerStyle={{ paddingTop: insets.top + spacing.md, paddingBottom: 220 }}
      testID="profile-screen"
    >
      <View style={styles.header}>
        <Text style={styles.title}>ACCOUNT</Text>
      </View>

      <View style={styles.userCard}>
        <View style={styles.avatar}>
          <Text style={styles.avatarText}>{(user.displayName?.[0] || user.phone.slice(-2)).toUpperCase()}</Text>
        </View>
        <View style={{ flex: 1 }}>
          <Text style={styles.userName}>{user.displayName || "BB FM Listener"}</Text>
          <Text style={styles.userPhone}>{user.phone}</Text>
        </View>
      </View>

      {/* Subscription */}
      <View style={styles.section}>
        <Text style={styles.sectionLabel}>SUBSCRIPTION</Text>
        <View style={[styles.subCard, user.tier !== "free" && { borderColor: tier.color }]} testID="sub-card">
          <View style={{ flex: 1 }}>
            <Text style={[styles.subTier, { color: tier.color }]}>{tier.label.toUpperCase()}</Text>
            {exp && user.tier !== "free" ? (
              <Text style={styles.subExp}>Renews {exp.toLocaleDateString()}</Text>
            ) : (
              <Text style={styles.subExp}>No active subscription</Text>
            )}
          </View>
          <Pressable onPress={() => router.push("/paywall")} style={styles.upgradeBtn} testID="upgrade-btn">
            <Text style={styles.upgradeText}>{user.tier === "free" ? "UPGRADE" : "MANAGE"}</Text>
          </Pressable>
        </View>
      </View>

      {/* Payment history */}
      <View style={styles.section}>
        <Text style={styles.sectionLabel}>PAYMENT HISTORY</Text>
        <View style={styles.list}>
          {payments.length === 0 && <Text style={styles.emptyList}>No payments yet</Text>}
          {payments.map((p) => (
            <View key={p.id} style={styles.payRow} testID={`payment-${p.id}`}>
              <View style={{ flex: 1 }}>
                <Text style={styles.payLabel}>{p.planLabel}</Text>
                <Text style={styles.payMeta}>{p.method.toUpperCase()} · {new Date(p.createdAt).toLocaleDateString()}</Text>
              </View>
              <Text style={styles.payAmt}>{p.amount.toLocaleString()} {p.currency}</Text>
            </View>
          ))}
        </View>
      </View>

      {/* Settings */}
      <View style={styles.section}>
        <Text style={styles.sectionLabel}>SETTINGS</Text>
        <View style={styles.list}>
          <Pressable style={styles.settingRow} testID="setting-notifications">
            <Ionicons name="notifications-outline" size={20} color={colors.onSurface} />
            <Text style={styles.settingText}>Notifications</Text>
            <Ionicons name="chevron-forward" size={18} color={colors.onSurfaceSecondary} />
          </Pressable>
          <View style={styles.sep} />
          <Pressable style={styles.settingRow} testID="setting-about">
            <Ionicons name="information-circle-outline" size={20} color={colors.onSurface} />
            <Text style={styles.settingText}>About BB FM Kigali</Text>
            <Ionicons name="chevron-forward" size={18} color={colors.onSurfaceSecondary} />
          </Pressable>
          <View style={styles.sep} />
          <Pressable style={styles.settingRow} onPress={openPrivacy} testID="setting-privacy">
            <Ionicons name="shield-checkmark-outline" size={20} color={colors.onSurface} />
            <Text style={styles.settingText}>Privacy Policy</Text>
            <Ionicons name="open-outline" size={18} color={colors.onSurfaceSecondary} />
          </Pressable>
          <View style={styles.sep} />
          <Pressable style={styles.settingRow} onPress={doLogout} testID="logout-btn">
            <Ionicons name="log-out-outline" size={20} color={colors.error} />
            <Text style={[styles.settingText, { color: colors.error }]}>Sign out</Text>
          </Pressable>
          <View style={styles.sep} />
          <Pressable style={styles.settingRow} onPress={doDelete} testID="delete-account-btn">
            <Ionicons name="trash-outline" size={20} color={colors.error} />
            <Text style={[styles.settingText, { color: colors.error, fontFamily: "BarlowCondensed-Bold" }]}>Delete Account</Text>
          </Pressable>
        </View>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  header: { paddingHorizontal: spacing.lg, marginBottom: spacing.lg },
  title: { ...type.displayLg, letterSpacing: 1 },
  userCard: { flexDirection: "row", alignItems: "center", gap: spacing.md, marginHorizontal: spacing.lg, padding: spacing.lg, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border },
  avatar: { width: 56, height: 56, borderRadius: 28, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.brandPrimary },
  avatarText: { color: colors.brandPrimary, fontFamily: "BarlowCondensed-Bold", fontSize: 20 },
  userName: { ...type.h1, fontSize: 20 },
  userPhone: { ...type.bodyMuted, marginTop: 2 },
  section: { marginTop: spacing.xl },
  sectionLabel: { ...type.label, letterSpacing: 1.5, paddingHorizontal: spacing.lg, marginBottom: spacing.sm },
  subCard: { flexDirection: "row", alignItems: "center", marginHorizontal: spacing.lg, padding: spacing.lg, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border },
  subTier: { fontFamily: "BarlowCondensed-Bold", fontSize: 22, letterSpacing: 1 },
  subExp: { ...type.caption, marginTop: 2 },
  upgradeBtn: { backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.lg, paddingVertical: spacing.md, borderRadius: radius.pill },
  upgradeText: { color: colors.onBrandPrimary, fontFamily: "BarlowCondensed-Bold", fontSize: 13, letterSpacing: 1 },
  list: { marginHorizontal: spacing.lg, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, overflow: "hidden" },
  emptyList: { ...type.bodyMuted, padding: spacing.lg, textAlign: "center" },
  payRow: { flexDirection: "row", alignItems: "center", padding: spacing.md, gap: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.divider },
  payLabel: { ...type.body, fontSize: 14 },
  payMeta: { ...type.caption, marginTop: 2 },
  payAmt: { ...type.h2, color: colors.brandPrimary, fontSize: 14 },
  settingRow: { flexDirection: "row", alignItems: "center", padding: spacing.md, gap: spacing.md },
  settingText: { ...type.body, flex: 1, fontSize: 15 },
  sep: { height: 1, backgroundColor: colors.divider, marginLeft: spacing.xxl },
});
