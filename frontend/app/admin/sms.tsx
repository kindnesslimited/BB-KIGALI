import { useEffect, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  Pressable,
  TextInput,
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Platform,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { colors, spacing, type, radius } from "@/src/theme";
import { api } from "@/src/api";

type Provider = {
  configured: boolean;
  senderId?: string | null;
  from?: string | null;
  endpoint?: string | null;
  notes?: string;
};

type ProvidersResp = {
  order: string[];
  providers: Record<string, Provider>;
};

type Analytics = {
  windowDays: number;
  totals: { attempts: number; delivered: number; successRate: number };
  providers: { provider: string; attempts: number; delivered: number; skipped: number; successRate: number }[];
  byDay: { day: string; delivered: number; failed: number }[];
};

const PROVIDER_META: Record<string, { label: string; icon: any; signup: string }> = {
  route_mobile: { label: "Route Mobile SMS", icon: "phone-portrait-outline", signup: "https://www.routemobile.com/" },
  twilio: { label: "Twilio", icon: "chatbubbles-outline", signup: "https://www.twilio.com/try-twilio" },
  africas_talking: { label: "Africa's Talking", icon: "globe-outline", signup: "https://account.africastalking.com/auth/register" },
  whatsapp: { label: "WhatsApp", icon: "logo-whatsapp", signup: "https://whatsapp.nostress.vip/" },
};

export default function AdminSmsScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [data, setData] = useState<ProvidersResp | null>(null);
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [testPhone, setTestPhone] = useState("+250");
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<string | null>(null);

  const load = async () => {
    try {
      setLoading(true);
      const [providersRes, analyticsRes] = await Promise.all([
        api<ProvidersResp>("/admin/sms/providers", { auth: true }),
        api<Analytics>("/admin/sms/analytics?days=7", { auth: true }),
      ]);
      setData(providersRes);
      setAnalytics(analyticsRes);
    } catch (e: any) {
      Alert.alert("Load failed", e.message);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    void load();
  }, []);

  const runTest = async () => {
    if (testPhone.replace(/\D/g, "").length < 9) {
      Alert.alert("Missing", "Please enter a valid phone number");
      return;
    }
    setTesting(true);
    setResult(null);
    try {
      const r = await api<{ sent: boolean; provider?: string; attempts: string }>(
        "/admin/sms/test",
        {
          method: "POST",
          auth: true,
          body: { phone: testPhone },
        }
      );
      if (r.sent) {
        setResult(`✅ Delivered via ${r.provider}. Check the target phone.`);
      } else {
        setResult(`❌ All providers failed.\n\n${r.attempts}`);
      }
    } catch (e: any) {
      setResult(`❌ Error: ${e.message}`);
    } finally {
      setTesting(false);
    }
  };

  const configuredCount = data
    ? Object.values(data.providers).filter((p) => p.configured).length
    : 0;

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === "ios" ? "padding" : undefined}
      style={{ flex: 1, backgroundColor: colors.surface }}
    >
      <View style={[styles.top, { paddingTop: insets.top + spacing.md }]}>
        <Pressable
          onPress={() => router.back()}
          hitSlop={12}
          testID="sms-back"
          style={styles.iconRound}
        >
          <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>SMS PROVIDERS</Text>
        <Pressable onPress={load} hitSlop={8}>
          <Ionicons name="refresh" size={22} color={colors.brandPrimary} />
        </Pressable>
      </View>

      <ScrollView
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: 160, gap: spacing.md }}
      >
        <View style={styles.summary}>
          <Ionicons name="link-outline" size={20} color={colors.brandPrimary} />
          <View style={{ flex: 1 }}>
            <Text style={styles.summaryText}>
              {configuredCount} of {data ? Object.keys(data.providers).length : 4} providers configured
            </Text>
            <Text style={styles.summarySub}>
              Providers are tried in order below. First one that succeeds wins.
            </Text>
          </View>
        </View>

        {analytics && analytics.totals.attempts > 0 && (
          <View style={styles.analyticsCard} testID="sms-analytics">
            <Text style={styles.sectionLabel}>LAST {analytics.windowDays} DAYS</Text>
            <View style={styles.statsGrid}>
              <View style={styles.statCell}>
                <Text style={styles.statNum}>{analytics.totals.delivered}</Text>
                <Text style={styles.statLabel}>Delivered</Text>
              </View>
              <View style={styles.statCell}>
                <Text style={styles.statNum}>{analytics.totals.attempts}</Text>
                <Text style={styles.statLabel}>Attempts</Text>
              </View>
              <View style={styles.statCell}>
                <Text style={[styles.statNum, { color: colors.success }]}>
                  {(analytics.totals.successRate * 100).toFixed(0)}%
                </Text>
                <Text style={styles.statLabel}>Success rate</Text>
              </View>
            </View>
            <View style={{ marginTop: spacing.sm, gap: 6 }}>
              {analytics.providers
                .filter((p) => p.attempts + p.skipped > 0)
                .map((p) => {
                  const meta = PROVIDER_META[p.provider] || { label: p.provider };
                  const barW = p.attempts > 0 ? Math.max(2, (p.delivered / p.attempts) * 100) : 0;
                  return (
                    <View key={p.provider} style={styles.analyticsRow}>
                      <Text style={styles.analyticsName}>{meta.label}</Text>
                      <View style={styles.barTrack}>
                        <View style={[styles.barFill, { width: `${barW}%` }]} />
                      </View>
                      <Text style={styles.analyticsCount}>
                        {p.delivered}/{p.attempts}
                      </Text>
                    </View>
                  );
                })}
            </View>
          </View>
        )}

        {loading ? (
          <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.xl }} />
        ) : (
          data?.order.map((name, index) => {
            const meta = PROVIDER_META[name] || { label: name, icon: "help-circle-outline", signup: "" };
            const p = data.providers[name];
            if (!p) return null;
            return (
              <View
                key={name}
                style={[styles.row, p.configured && styles.rowConfigured]}
                testID={`sms-provider-${name}`}
              >
                <View style={styles.priorityBadge}>
                  <Text style={styles.priorityText}>{index + 1}</Text>
                </View>
                <View style={styles.providerIcon}>
                  <Ionicons
                    name={meta.icon}
                    size={22}
                    color={p.configured ? colors.brandPrimary : colors.onSurfaceSecondary}
                  />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.providerName}>{meta.label}</Text>
                  <Text style={styles.providerNotes} numberOfLines={2}>
                    {p.notes}
                  </Text>
                  {p.senderId && (
                    <Text style={styles.providerDetail}>Sender ID: {p.senderId}</Text>
                  )}
                  {p.from && (
                    <Text style={styles.providerDetail}>From: {p.from}</Text>
                  )}
                  {p.endpoint && (
                    <Text style={styles.providerDetail} numberOfLines={1}>Endpoint: {p.endpoint}</Text>
                  )}
                </View>
                <View style={[styles.status, p.configured ? styles.statusOn : styles.statusOff]}>
                  <Text style={styles.statusText}>{p.configured ? "READY" : "OFF"}</Text>
                </View>
              </View>
            );
          })
        )}

        <View style={styles.helpCard}>
          <Ionicons name="information-circle-outline" size={16} color={colors.brandPrimary} />
          <Text style={styles.helpText}>
            To activate more providers, contact <Text style={styles.helpBold}>support@emergent.sh</Text> with the API keys for Twilio,
            Africa&apos;s Talking, or WhatsApp — they will add them to your production environment.
          </Text>
        </View>

        <View style={styles.testBox}>
          <Text style={styles.sectionLabel}>SEND TEST SMS</Text>
          <Text style={styles.helpText}>
            Tries the full provider chain and reports which one delivered.
          </Text>
          <TextInput
            value={testPhone}
            onChangeText={setTestPhone}
            keyboardType="phone-pad"
            placeholder="+250 78x xxx xxx"
            placeholderTextColor={colors.onSurfaceSecondary}
            style={styles.input}
            testID="sms-test-phone"
          />
          <Pressable
            onPress={runTest}
            disabled={testing}
            style={[styles.testBtn, testing && { opacity: 0.6 }]}
            testID="sms-test-run"
          >
            {testing ? (
              <ActivityIndicator color={colors.onBrandPrimary} />
            ) : (
              <>
                <Ionicons name="send" size={16} color={colors.onBrandPrimary} />
                <Text style={styles.testBtnText}>SEND TEST</Text>
              </>
            )}
          </Pressable>
          {result && (
            <View style={styles.resultBox}>
              <Text style={styles.resultText}>{result}</Text>
            </View>
          )}
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  top: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.sm,
    backgroundColor: colors.surface,
    borderBottomWidth: 1,
    borderBottomColor: colors.divider,
  },
  iconRound: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.surfaceSecondary,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: colors.border,
  },
  title: { ...type.h1, flex: 1, textAlign: "center", letterSpacing: 1.5 },
  summary: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    padding: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.brandPrimary,
    backgroundColor: colors.brandTertiary,
  },
  summaryText: { ...type.h2, fontSize: 14, color: colors.onBrandTertiary },
  summarySub: { ...type.caption, marginTop: 2, color: colors.onBrandTertiary },
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    padding: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surfaceSecondary,
  },
  rowConfigured: { borderColor: colors.brandPrimary },
  priorityBadge: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: colors.surfaceTertiary,
    alignItems: "center",
    justifyContent: "center",
  },
  priorityText: { color: colors.brandPrimary, fontFamily: "BarlowCondensed-Bold", fontSize: 14 },
  providerIcon: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.surfaceTertiary,
    alignItems: "center",
    justifyContent: "center",
  },
  providerName: { ...type.h2, fontSize: 14 },
  providerNotes: { ...type.caption, marginTop: 2, lineHeight: 15 },
  providerDetail: { ...type.caption, marginTop: 1, color: colors.brandPrimary, fontSize: 10 },
  status: {
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
    borderRadius: radius.sm,
  },
  statusOn: { backgroundColor: colors.success },
  statusOff: { backgroundColor: colors.surfaceTertiary },
  statusText: { color: "#fff", fontFamily: "BarlowCondensed-Bold", fontSize: 10, letterSpacing: 1 },
  helpCard: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: spacing.sm,
    padding: spacing.md,
    borderRadius: radius.md,
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1,
    borderColor: colors.border,
  },
  helpText: { ...type.caption, flex: 1, lineHeight: 16 },
  helpBold: { color: colors.brandPrimary, fontFamily: "BarlowCondensed-Bold" },
  testBox: {
    padding: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    gap: spacing.sm,
    marginTop: spacing.md,
  },
  sectionLabel: { ...type.label, letterSpacing: 1.5, color: colors.brandPrimary },
  input: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    padding: spacing.md,
    color: colors.onSurface,
    fontSize: 15,
    borderWidth: 1,
    borderColor: colors.border,
  },
  testBtn: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.sm,
    backgroundColor: colors.brandPrimary,
    height: 46,
    borderRadius: radius.md,
    marginTop: spacing.xs,
  },
  testBtnText: { ...type.h2, color: colors.onBrandPrimary, letterSpacing: 1.5, fontSize: 13 },
  resultBox: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  resultText: { ...type.caption, fontFamily: Platform.select({ ios: "Menlo", android: "monospace", default: "monospace" }), lineHeight: 17, color: colors.onSurface },
  analyticsCard: {
    padding: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    gap: spacing.sm,
    backgroundColor: colors.surfaceSecondary,
  },
  statsGrid: { flexDirection: "row", gap: spacing.md },
  statCell: { flex: 1, alignItems: "center" },
  statNum: { ...type.h1, fontSize: 24, color: colors.brandPrimary, letterSpacing: 0.5 },
  statLabel: { ...type.caption, color: colors.onSurfaceSecondary, marginTop: 2 },
  analyticsRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  analyticsName: { ...type.caption, width: 100, color: colors.onSurface, fontFamily: "BarlowCondensed-Bold", fontSize: 11 },
  barTrack: { flex: 1, height: 6, borderRadius: 3, backgroundColor: colors.surfaceTertiary, overflow: "hidden" },
  barFill: { height: "100%", backgroundColor: colors.success, borderRadius: 3 },
  analyticsCount: { ...type.caption, minWidth: 40, textAlign: "right", color: colors.onSurfaceSecondary, fontFamily: Platform.select({ ios: "Menlo", android: "monospace", default: "monospace" }), fontSize: 11 },
});
