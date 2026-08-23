import { useEffect } from "react";
import { View, ActivityIndicator, StyleSheet, Text } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { colors, spacing } from "@/src/theme";
import { useAuth } from "@/src/context/auth";

/**
 * Deep-link landing for the "Renew now" SMS.
 * If the user is signed in, we send them straight to /checkout?plan=… with the plan pre-selected.
 * Otherwise we route them to /auth/phone with a redirect back here after login.
 */
export default function RenewDeepLink() {
  const { plan } = useLocalSearchParams<{ plan?: string }>();
  const router = useRouter();
  const { user, loading } = useAuth();
  const chosenPlan = plan && typeof plan === "string" ? plan : "basic_monthly";

  useEffect(() => {
    if (loading) return;
    if (!user) {
      router.replace({ pathname: "/auth/phone", params: { next: `/renew?plan=${chosenPlan}` } });
      return;
    }
    router.replace({ pathname: "/checkout", params: { plan: chosenPlan } });
  }, [loading, user, chosenPlan, router]);

  return (
    <View style={styles.wrap}>
      <ActivityIndicator color={colors.brandPrimary} />
      <Text style={styles.msg}>Opening renewal for {chosenPlan.replace("_", " ")}…</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center", gap: spacing.md, padding: spacing.lg },
  msg: { color: colors.onSurface, textAlign: "center" },
});
