import { useEffect, useRef, useState } from "react";
import { View, Text, StyleSheet, Pressable, TextInput, KeyboardAvoidingView, Platform, ActivityIndicator } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import { colors, spacing, type, radius } from "@/src/theme";
import { useAuth } from "@/src/context/auth";

const LEN = 6;

export default function OTPVerify() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { phone, testCode } = useLocalSearchParams<{ phone: string; testCode?: string }>();
  const { verifyOtp, requestOtp } = useAuth();
  const [code, setCode] = useState<string[]>(Array(LEN).fill(""));
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const inputs = useRef<Array<TextInput | null>>([]);

  useEffect(() => { inputs.current[0]?.focus(); }, []);

  const setDigit = (i: number, v: string) => {
    const clean = v.replace(/\D/g, "");
    if (!clean) {
      const next = [...code]; next[i] = ""; setCode(next); return;
    }
    const chars = clean.split("");
    const next = [...code];
    for (let j = 0; j < chars.length && i + j < LEN; j++) next[i + j] = chars[j];
    setCode(next);
    const lastFilled = Math.min(i + chars.length, LEN - 1);
    inputs.current[lastFilled]?.focus();
    if (next.every(c => c) && next.join("").length === LEN) {
      void submit(next.join(""));
    }
  };

  const onKey = (i: number, key: string) => {
    if (key === "Backspace" && !code[i] && i > 0) {
      const next = [...code]; next[i - 1] = ""; setCode(next);
      inputs.current[i - 1]?.focus();
    }
  };

  const submit = async (c?: string) => {
    const finalCode = c ?? code.join("");
    if (finalCode.length !== LEN) { setErr("Enter the 6-digit code"); return; }
    setErr(null); setLoading(true);
    try {
      await verifyOtp(String(phone), finalCode);
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
      router.replace("/(tabs)");
    } catch (e: any) {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error).catch(() => {});
      setErr(e.message || "Invalid code");
    } finally { setLoading(false); }
  };

  const resend = async () => {
    try { await requestOtp(String(phone)); setErr(null); } catch (e: any) { setErr(e.message); }
  };

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : "height"} style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.container, { paddingTop: insets.top + spacing.xl }]} testID="otp-screen">
        <Pressable onPress={() => router.back()} style={styles.back} testID="otp-back">
          <Ionicons name="chevron-back" size={26} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>VERIFY</Text>
        <Text style={styles.subtitle}>We sent a 6-digit code to {phone}. Enter it below.</Text>

        <View style={styles.otpRow}>
          {code.map((c, i) => (
            <TextInput
              key={i}
              ref={(r) => { inputs.current[i] = r; }}
              testID={`otp-input-${i}`}
              value={c}
              onChangeText={(v) => setDigit(i, v)}
              onKeyPress={(e) => onKey(i, e.nativeEvent.key)}
              keyboardType="number-pad"
              maxLength={LEN}
              style={[styles.otpCell, c && styles.otpCellFilled]}
              selectionColor={colors.brandPrimary}
            />
          ))}
        </View>

        {testCode && (
          <View style={styles.demoBox} testID="demo-code-box">
            <Ionicons name="information-circle-outline" size={16} color={colors.warning} />
            <Text style={styles.demoText}>Demo mode — use code <Text style={styles.demoCode}>{testCode}</Text></Text>
          </View>
        )}

        {err && <Text style={styles.err} testID="otp-error">{err}</Text>}

        <Pressable onPress={resend} style={{ marginTop: spacing.lg }}>
          <Text style={styles.resend}>Didn&apos;t receive a code? <Text style={{ color: colors.brandPrimary }}>Resend</Text></Text>
        </Pressable>

        <View style={{ flex: 1 }} />
        <View style={{ paddingBottom: insets.bottom + spacing.lg }}>
          <Pressable onPress={() => submit()} disabled={loading} style={[styles.cta, loading && { opacity: 0.6 }]} testID="otp-verify">
            {loading ? <ActivityIndicator color={colors.onBrandPrimary} /> : <Text style={styles.ctaText}>VERIFY & CONTINUE</Text>}
          </Pressable>
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, paddingHorizontal: spacing.lg },
  back: { width: 40, height: 40, alignItems: "center", justifyContent: "center", marginLeft: -spacing.sm, marginBottom: spacing.md },
  title: { ...type.displayXL, marginBottom: spacing.sm },
  subtitle: { ...type.bodyMuted, lineHeight: 22, marginBottom: spacing.xl },
  otpRow: { flexDirection: "row", gap: spacing.sm, justifyContent: "space-between" },
  otpCell: { width: 48, height: 60, borderRadius: radius.md, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, color: colors.onSurface, textAlign: "center", fontSize: 22, fontFamily: "BarlowCondensed-Bold" },
  otpCellFilled: { borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary },
  demoBox: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginTop: spacing.lg, backgroundColor: colors.brandTertiary, borderRadius: radius.md, padding: spacing.md },
  demoText: { ...type.caption, color: colors.onBrandTertiary },
  demoCode: { fontFamily: "BarlowCondensed-Bold", fontSize: 14, color: colors.brandPrimary, letterSpacing: 2 },
  err: { color: colors.error, marginTop: spacing.sm },
  resend: { ...type.bodyMuted, textAlign: "center" },
  cta: { backgroundColor: colors.brandPrimary, height: 56, borderRadius: radius.md, alignItems: "center", justifyContent: "center" },
  ctaText: { ...type.h2, color: colors.onBrandPrimary, letterSpacing: 1 },
});
