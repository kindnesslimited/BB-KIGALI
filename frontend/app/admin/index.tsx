import { useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, ActivityIndicator, RefreshControl } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { colors, spacing, type, radius } from "@/src/theme";
import { api } from "@/src/api";
import { useAuth } from "@/src/context/auth";

type Dashboard = {
  users?: { total: number; admins: number; newThisWeek: number };
  subscriptions?: { active: number; expired: number };
  revenue?: { allTime: Record<string, number>; last30Days: Record<string, number>; last7Days: Record<string, number>; today: Record<string, number> };
  transactions?: { successThisMonth: number; pending: number; failedThisMonth: number; breakdownByMethod: any[] };
  content?: { shows: number; programs: number; news: number };
  generatedAt?: string;
};

const CARDS: { key: string; label: string; sub: string; icon: any; route: any }[] = [
  { key: "settings", label: "Live URLs & Branding", sub: "Radio stream, live YouTube URL, station name", icon: "settings-outline", route: "/admin/settings" },
  { key: "payments", label: "Payments & Revenue", sub: "Stripe, PayPal, MoMo — successful, pending, failed", icon: "cash-outline", route: "/admin/payments" },
  { key: "subs", label: "Subscriptions Report", sub: "Active, expired customers with details", icon: "ribbon-outline", route: "/admin/subscriptions" },
  { key: "users", label: "Users & Admins", sub: "Invite single or bulk (CSV), edit, activate/deactivate", icon: "people-outline", route: "/admin/users" },
  { key: "audit", label: "Activity / Audit Log", sub: "Who created, edited or deleted what — and when", icon: "shield-checkmark-outline", route: "/admin/audit" },
  { key: "sms", label: "SMS Providers", sub: "Route Mobile + WhatsApp — analytics + delivery", icon: "chatbubbles-outline", route: "/admin/sms" },
  { key: "categories", label: "Categories", sub: "Manage show/news categories", icon: "pricetags-outline", route: "/admin/categories" },
  { key: "programs", label: "Programs", sub: "BBSPORTSTALK, B&B SPORTS BAR, IMPUMEKOYIWACU", icon: "list-outline", route: "/admin/programs" },
  { key: "schedule", label: "Schedule", sub: "Daily & weekly on-air program slots", icon: "calendar-outline", route: "/admin/schedule" },
  { key: "live-shows", label: "Live Shows", sub: "Create shows, save private recordings, publish to YouTube", icon: "videocam-outline", route: "/admin/live-shows" },
  { key: "youtube-config", label: "YouTube Channel", sub: "Connect / switch the channel used for LIVE + auto-upload", icon: "logo-youtube", route: "/admin/youtube-config" },
  { key: "cloudflare-stream", label: "Cloudflare Stream", sub: "Private RTMP live-streaming + secure recording (bring your own)", icon: "cloud-outline", route: "/admin/cloudflare-stream" },
  { key: "shows", label: "VOD & Podcasts", sub: "Sync @bbkigalifm + @BBSPORTSBAR YouTube", icon: "videocam-outline", route: "/admin/shows" },
  { key: "news", label: "News", sub: "Create, edit and delete news posts", icon: "newspaper-outline", route: "/admin/news" },
];

function fmt(n?: number) { return typeof n === "number" ? n.toLocaleString() : "—"; }
function fmtMoney(m?: Record<string, number>) {
  if (!m || Object.keys(m).length === 0) return "0";
  return Object.entries(m).map(([cur, amt]) => `${amt.toLocaleString(undefined, { maximumFractionDigits: 0 })} ${cur}`).join("  ·  ");
}

export default function AdminHome() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user } = useAuth();
  const [data, setData] = useState<Dashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = async () => {
    try {
      const d = await api<Dashboard>("/admin/analytics/dashboard", { auth: true });
      setData(d);
    } catch (e: any) {
      // Non-admins get 403 — they'll be redirected by the guard anyway.
    } finally { setLoading(false); setRefreshing(false); }
  };
  useEffect(() => { void load(); }, []);
  const onRefresh = () => { setRefreshing(true); void load(); };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.top, { paddingTop: insets.top + spacing.md }]}>
        <Text style={styles.title}>ADMIN CONSOLE</Text>
        <Pressable onPress={() => router.back()} hitSlop={12}><Ionicons name="close" size={26} color={colors.onSurface} /></Pressable>
      </View>

      <ScrollView
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 40, gap: spacing.md }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.brandPrimary} />}
        testID="admin-home"
      >
        <Text style={styles.hi}>Welcome{user?.displayName ? `, ${user.displayName}` : ""}</Text>

        {loading ? (
          <ActivityIndicator color={colors.brandPrimary} />
        ) : (
          <>
            <View style={styles.kpiGrid}>
              <Kpi label="Active subs" value={fmt(data?.subscriptions?.active)} icon="ribbon" accent="#22c55e" />
              <Kpi label="Expired subs" value={fmt(data?.subscriptions?.expired)} icon="alert-circle" accent="#f97316" />
              <Kpi label="Total customers" value={fmt(data?.users?.total)} icon="people" accent={colors.brandPrimary} />
              <Kpi label="New this week" value={fmt(data?.users?.newThisWeek)} icon="trending-up" accent="#3b82f6" />
            </View>

            <View style={styles.revBox}>
              <Text style={styles.revLabel}>REVENUE — LAST 30 DAYS</Text>
              <Text style={styles.revBig}>{fmtMoney(data?.revenue?.last30Days)}</Text>
              <View style={{ flexDirection: "row", justifyContent: "space-between", marginTop: spacing.sm }}>
                <View>
                  <Text style={styles.miniLabel}>TODAY</Text>
                  <Text style={styles.miniValue}>{fmtMoney(data?.revenue?.today)}</Text>
                </View>
                <View>
                  <Text style={styles.miniLabel}>LAST 7 DAYS</Text>
                  <Text style={styles.miniValue}>{fmtMoney(data?.revenue?.last7Days)}</Text>
                </View>
                <View>
                  <Text style={styles.miniLabel}>ALL TIME</Text>
                  <Text style={styles.miniValue}>{fmtMoney(data?.revenue?.allTime)}</Text>
                </View>
              </View>
            </View>

            <View style={styles.txRow}>
              <View style={[styles.txCard, { backgroundColor: "#0f2415", borderColor: "#16a34a" }]}>
                <Ionicons name="checkmark-circle" size={22} color="#22c55e" />
                <Text style={styles.txCount}>{fmt(data?.transactions?.successThisMonth)}</Text>
                <Text style={styles.txLabel}>Paid (30d)</Text>
              </View>
              <View style={[styles.txCard, { backgroundColor: "#2a1f0a", borderColor: "#f59e0b" }]}>
                <Ionicons name="time" size={22} color="#f59e0b" />
                <Text style={styles.txCount}>{fmt(data?.transactions?.pending)}</Text>
                <Text style={styles.txLabel}>Pending</Text>
              </View>
              <View style={[styles.txCard, { backgroundColor: "#2a0f12", borderColor: "#ef4444" }]}>
                <Ionicons name="close-circle" size={22} color="#ef4444" />
                <Text style={styles.txCount}>{fmt(data?.transactions?.failedThisMonth)}</Text>
                <Text style={styles.txLabel}>Failed (30d)</Text>
              </View>
            </View>

            {data?.transactions?.breakdownByMethod && data.transactions.breakdownByMethod.length > 0 && (
              <View style={styles.breakdown}>
                <Text style={styles.revLabel}>BY PAYMENT METHOD (30D SUCCESS)</Text>
                {data.transactions.breakdownByMethod.map((b: any, i: number) => (
                  <View key={i} style={styles.breakdownRow}>
                    <Text style={styles.bMethod}>{(b.method || "?").replace("_", " ").toUpperCase()}</Text>
                    <Text style={styles.bAmount}>{(b.amount || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })} {b.currency}</Text>
                    <Text style={styles.bCount}>{b.count} tx</Text>
                  </View>
                ))}
              </View>
            )}

            <View style={styles.contentRow}>
              <Text style={styles.contentLabel}>CONTENT</Text>
              <Text style={styles.contentValue}>{fmt(data?.content?.shows)} shows · {fmt(data?.content?.programs)} programs · {fmt(data?.content?.news)} news</Text>
            </View>
          </>
        )}

        <View style={styles.divider} />
        <Text style={styles.section}>MANAGEMENT</Text>
        {CARDS.map((c) => (
          <Pressable key={c.key} onPress={() => router.push(c.route)} style={styles.card} testID={`admin-card-${c.key}`}>
            <View style={styles.iconBubble}><Ionicons name={c.icon} size={22} color={colors.brandPrimary} /></View>
            <View style={{ flex: 1 }}>
              <Text style={styles.cardLabel}>{c.label}</Text>
              <Text style={styles.cardSub}>{c.sub}</Text>
            </View>
            <Ionicons name="chevron-forward" size={22} color={colors.onSurfaceSecondary} />
          </Pressable>
        ))}
      </ScrollView>
    </View>
  );
}

function Kpi({ label, value, icon, accent }: { label: string; value: string; icon: any; accent: string }) {
  return (
    <View style={[styles.kpi, { borderColor: accent }]}>
      <Ionicons name={icon} size={20} color={accent} />
      <Text style={styles.kpiValue}>{value}</Text>
      <Text style={styles.kpiLabel}>{label.toUpperCase()}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  top: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.border },
  title: { ...type.h2, letterSpacing: 1.5, fontSize: 18 },
  hi: { ...type.body, marginBottom: 4 },
  kpiGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  kpi: { flexBasis: "48%", flexGrow: 1, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.md, borderWidth: 1 },
  kpiValue: { ...type.h1, fontSize: 24, marginTop: 6, color: colors.onSurface },
  kpiLabel: { ...type.caption, letterSpacing: 1.2, fontSize: 10 },
  revBox: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.md, borderWidth: 1, borderColor: colors.brandPrimary },
  revLabel: { ...type.label, letterSpacing: 1.5, fontSize: 11, color: colors.brandPrimary },
  revBig: { fontFamily: "BarlowCondensed-Bold", fontSize: 28, color: colors.onSurface, marginTop: 4, letterSpacing: 1 },
  miniLabel: { ...type.caption, letterSpacing: 1.2, fontSize: 9 },
  miniValue: { ...type.body, fontSize: 12, marginTop: 2 },
  txRow: { flexDirection: "row", gap: spacing.sm },
  txCard: { flex: 1, borderRadius: radius.md, padding: spacing.md, borderWidth: 1, alignItems: "flex-start", gap: 4 },
  txCount: { fontFamily: "BarlowCondensed-Bold", fontSize: 22, color: colors.onSurface },
  txLabel: { ...type.caption, letterSpacing: 1.2, fontSize: 10 },
  breakdown: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.md, borderWidth: 1, borderColor: colors.border },
  breakdownRow: { flexDirection: "row", justifyContent: "space-between", paddingVertical: 6, borderBottomWidth: 0.5, borderBottomColor: colors.border },
  bMethod: { ...type.label, letterSpacing: 1.2, fontSize: 11, color: colors.onSurface },
  bAmount: { ...type.body, fontSize: 12 },
  bCount: { ...type.caption, fontSize: 11 },
  contentRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", padding: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border },
  contentLabel: { ...type.label, letterSpacing: 1.5, fontSize: 11 },
  contentValue: { ...type.body, fontSize: 12 },
  divider: { height: 1, backgroundColor: colors.border, marginVertical: spacing.md },
  section: { ...type.label, letterSpacing: 1.5, fontSize: 12, marginBottom: 4 },
  card: { flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border },
  iconBubble: { width: 40, height: 40, borderRadius: radius.sm, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center" },
  cardLabel: { ...type.h2, fontSize: 14, lineHeight: 18 },
  cardSub: { ...type.caption, marginTop: 3 },
});
