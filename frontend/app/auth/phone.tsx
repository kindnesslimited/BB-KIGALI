import { useState } from "react";
import { View, Text, StyleSheet, Pressable, TextInput, KeyboardAvoidingView, Platform, ActivityIndicator } from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import { colors, spacing, type, radius } from "@/src/theme";
import { useAuth } from "@/src/context/auth";

export default function PhoneEntry() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { requestOtp } = useAuth();
  const [phone, setPhone] = useState("+250");
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    setErr(null);
    const p = phone.trim();
    if (p.replace(/\D/g, "").length < 9) { setErr("Enter a valid phone number"); return; }
    setLoading(true);
    try {
      const r = await requestOtp(p);
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
      router.push({ pathname: "/auth/otp", params: { phone: p, testCode: r?.testCode || "123456" } });
    } catch (e: any) {
      setErr(e.message || "Failed to send code");
    } finally { setLoading(false); }
  };

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : "height"} style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.container, { paddingTop: insets.top + spacing.xl }]} testID="phone-entry-screen">
        <Pressable onPress={() => router.back()} style={styles.back} testID="phone-back">
          <Ionicons name="chevron-back" size={26} color={colors.onSurface} />
        </Pressable>
        <View style={styles.brandRow}>
          <View style={styles.liveDot} />
          <Text style={styles.brandLabel}>BB FM KIGALI</Text>
        </View>
        <Text style={styles.title}>WELCOME</Text>
        <Text style={styles.subtitle}>Enter your phone number to get started. We&apos;ll text you a verification code.</Text>

        <View style={styles.inputWrap}>
          <Ionicons name="call-outline" size={20} color={colors.onSurfaceSecondary} />
          <TextInput
            testID="phone-input"
            value={phone}
            onChangeText={setPhone}
            placeholder="+250 78x xxx xxx"
            placeholderTextColor={colors.onSurfaceSecondary}
            keyboardType="phone-pad"
            style={styles.input}
            autoFocus
          />
        </View>
        {err && <Text style={styles.err} testID="phone-error">{err}</Text>}

        <View style={{ flex: 1 }} />
        <View style={{ paddingBottom: insets.bottom + spacing.lg }}>
          <Pressable onPress={submit} disabled={loading} style={[styles.cta, loading && { opacity: 0.6 }]} testID="phone-continue">
            {loading ? <ActivityIndicator color={colors.onBrandPrimary} /> : <Text style={styles.ctaText}>CONTINUE</Text>}
          </Pressable>
          <Text style={styles.legal}>By continuing you accept our Terms & Privacy.</Text>
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, paddingHorizontal: spacing.lg },
  back: { width: 40, height: 40, alignItems: "center", justifyContent: "center", marginLeft: -spacing.sm, marginBottom: spacing.md },
  brandRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginBottom: spacing.md },
  liveDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.brandPrimary },
  brandLabel: { ...type.label, color: colors.brandPrimary, letterSpacing: 2 },
  title: { ...type.displayXL, marginBottom: spacing.sm },
  subtitle: { ...type.bodyMuted, lineHeight: 22, marginBottom: spacing.xl },
  inputWrap: { flexDirection: "row", alignItems: "center", backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, paddingHorizontal: spacing.lg, gap: spacing.md, height: 56, borderWidth: 1, borderColor: colors.border },
  input: { flex: 1, color: colors.onSurface, fontSize: 16, fontFamily: "System" },
  err: { color: colors.error, marginTop: spacing.sm },
  cta: { backgroundColor: colors.brandPrimary, height: 56, borderRadius: radius.md, alignItems: "center", justifyContent: "center" },
  ctaText: { ...type.h2, color: colors.onBrandPrimary, letterSpacing: 1 },
  legal: { ...type.caption, textAlign: "center", marginTop: spacing.md },
});
