import { useEffect, useState, useMemo } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  Pressable,
  ActivityIndicator,
  RefreshControl,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { colors, spacing, type, radius } from "@/src/theme";
import { api, getToken } from "@/src/api";
import { Alert, Platform } from "react-native";

const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL || "";

type Summary = {
  windowDays: number;
  totals: { success: number; pending: number; failed: number; count: number };
  byMethod: { method: string; count: number; revenue: Record<string, number> }[];
  totalRevenue: Record<string, number>;
  byDay: { day: string; count: number; byCurrency: Record<string, number> }[];
};

type Payment = {
  id: string;
  userId?: string | null;
  userPhone?: string | null;
  userEmail?: string | null;
  userName?: string | null;
  plan?: string | null;
  planLabel?: string | null;
  amount: number;
  currency: string;
  method: string;
  status: string;
  createdAt: string;
};

const METHOD_META: Record<string, { label: string; icon: any; color: string }> = {
  paypal: { label: "PayPal", icon: "logo-paypal", color: "#00457C" },
  stripe: { label: "Card", icon: "card", color: "#635bff" },
  mtn_momo: { label: "MTN MoMo", icon: "phone-portrait", color: "#E10600" },
  airtel: { label: "Airtel", icon: "phone-portrait", color: "#E60000" },
};

const STATUS_COLORS: Record<string, string> = {
  success: "#1E5FB4",   // BLUE
  pending: "#E10600",   // RED (was orange amber)
  failed: "#D9381E",    // RED (error variant)
};

const WINDOWS = [
  { key: 7, label: "7D" },
  { key: 30, label: "30D" },
  { key: 90, label: "90D" },
];

export default function AdminPayments() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [days, setDays] = useState(30);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [payments, setPayments] = useState<Payment[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string>("all");

  const downloadCsv = async () => {
    try {
      const params = new URLSearchParams();
      if (statusFilter !== "all") params.set("status", statusFilter);
      params.set("days", String(days));
      const token = await getToken();
      const url = `${BACKEND_URL}/api/admin/payments/export.csv?${params.toString()}`;
      if (Platform.OS === "web") {
        const r = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const blob = await r.blob();
        const objUrl = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = objUrl;
        a.download = `bb-fm-payments-${new Date().toISOString().slice(0,10)}.csv`;
        document.body.appendChild(a); a.click();
        setTimeout(() => { document.body.removeChild(a); URL.revokeObjectURL(objUrl); }, 500);
      } else {
        const FileSystem = require("expo-file-system");
        const Sharing = require("expo-sharing");
        const target = `${FileSystem.cacheDirectory}bb-fm-payments-${Date.now()}.csv`;
        const dl = await FileSystem.downloadAsync(url, target, { headers: { Authorization: `Bearer ${token}` } });
        if (dl.status !== 200) throw new Error(`HTTP ${dl.status}`);
        if (await Sharing.isAvailableAsync()) {
          await Sharing.shareAsync(dl.uri, { UTI: "public.comma-separated-values-text", mimeType: "text/csv" });
        }
      }
    } catch (e: any) {
      Alert.alert("Export failed", e?.message || "Please try again.");
    }
  };

  // Owner business report — full KPI + revenue + subscribers + payments as a PDF.
  const downloadPdfReport = async () => {
    try {
      const end = new Date();
      const start = new Date(end.getTime() - days * 86400 * 1000);
      const toIso = (d: Date) => d.toISOString().slice(0, 10);
      const params = new URLSearchParams({ start: toIso(start), end: toIso(end) });
      const token = await getToken();
      const url = `${BACKEND_URL}/api/admin/reports/business.pdf?${params.toString()}`;
      if (Platform.OS === "web") {
        const r = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const blob = await r.blob();
        const objUrl = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = objUrl;
        a.download = `bb-fm-business-report-${toIso(start)}_${toIso(end)}.pdf`;
        document.body.appendChild(a); a.click();
        setTimeout(() => { document.body.removeChild(a); URL.revokeObjectURL(objUrl); }, 500);
      } else {
        const FileSystem = require("expo-file-system");
        const Sharing = require("expo-sharing");
        const target = `${FileSystem.cacheDirectory}bb-fm-business-report-${Date.now()}.pdf`;
        const dl = await FileSystem.downloadAsync(url, target, { headers: { Authorization: `Bearer ${token}` } });
        if (dl.status !== 200) throw new Error(`HTTP ${dl.status}`);
        if (await Sharing.isAvailableAsync()) {
          await Sharing.shareAsync(dl.uri, { UTI: "com.adobe.pdf", mimeType: "application/pdf" });
        }
      }
    } catch (e: any) {
      Alert.alert("PDF export failed", e?.message || "Please try again.");
    }
  };

  const load = async () => {
    try {
      const [s, p] = await Promise.all([
        api<Summary>(`/admin/payments/summary?days=${days}`, { auth: true }),
        api<Payment[]>(`/admin/payments?days=${days}&limit=200`, { auth: true }),
      ]);
      setSummary(s);
      setPayments(p);
    } catch {
      /* noop */
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    setLoading(true);
    void load();
  }, [days]);

  const filtered = useMemo(
    () => (statusFilter === "all" ? payments : payments.filter((p) => p.status === statusFilter)),
    [payments, statusFilter]
  );

  const fmtMoney = (amount: number, currency: string) => {
    if (!amount) return `${currency} 0`;
    const cur = (currency || "").toUpperCase();
    return `${cur === "EUR" ? "€" : cur === "USD" ? "$" : cur + " "}${Number(amount).toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
  };

  const fmtWhen = (iso: string) => {
    try {
      const d = new Date(iso);
      return `${d.toLocaleDateString()} ${d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
    } catch {
      return iso.slice(0, 16);
    }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }} testID="admin-payments">
      <View style={[styles.top, { paddingTop: insets.top + spacing.md }]}>
        <Pressable
          onPress={() => router.back()}
          hitSlop={12}
          testID="payments-back"
          style={styles.iconRound}
        >
          <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>PAYMENTS</Text>
        <View style={{ flexDirection: "row", gap: spacing.md }}>
          <Pressable onPress={downloadCsv} hitSlop={8} testID="payments-csv" style={styles.csvBtn}>
            <Ionicons name="download-outline" size={16} color="#000" />
            <Text style={styles.csvBtnText}>CSV</Text>
          </Pressable>
          <Pressable onPress={downloadPdfReport} hitSlop={8} testID="payments-pdf" style={styles.pdfBtn}>
            <Ionicons name="document-text-outline" size={16} color="#fff" />
            <Text style={styles.pdfBtnText}>PDF</Text>
          </Pressable>
          <Pressable onPress={() => { setLoading(true); void load(); }} hitSlop={8} testID="payments-refresh">
            <Ionicons name="refresh" size={22} color={colors.brandPrimary} />
          </Pressable>
        </View>
      </View>

      <ScrollView
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: 160, gap: spacing.md }}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={() => { setRefreshing(true); void load(); }}
            tintColor={colors.brandPrimary}
          />
        }
      >
        <View style={styles.windowSegment}>
          {WINDOWS.map((w) => (
            <Pressable
              key={w.key}
              onPress={() => setDays(w.key)}
              style={[styles.windowItem, days === w.key && styles.windowItemActive]}
              testID={`window-${w.key}`}
            >
              <Text style={[styles.windowText, days === w.key && styles.windowTextActive]}>
                {w.label}
              </Text>
            </Pressable>
          ))}
        </View>

        {loading && !summary ? (
          <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.xl }} />
        ) : (
          summary && (
            <>
              {/* Revenue cards */}
              <View style={styles.revenueGrid}>
                {Object.entries(summary.totalRevenue).length === 0 ? (
                  <View style={styles.revCard}>
                    <Text style={styles.revAmount}>—</Text>
                    <Text style={styles.revLabel}>No revenue yet</Text>
                  </View>
                ) : (
                  Object.entries(summary.totalRevenue).map(([currency, amount]) => (
                    <View key={currency} style={styles.revCard}>
                      <Text style={styles.revAmount}>
                        {fmtMoney(amount, currency)}
                      </Text>
                      <Text style={styles.revLabel}>{currency} revenue · {summary.windowDays}D</Text>
                    </View>
                  ))
                )}
              </View>

              {/* Status pills */}
              <View style={styles.statusRow}>
                <View style={[styles.statusPill, { backgroundColor: STATUS_COLORS.success + "22", borderColor: STATUS_COLORS.success }]}>
                  <Ionicons name="checkmark-circle" size={14} color={STATUS_COLORS.success} />
                  <Text style={[styles.statusPillText, { color: STATUS_COLORS.success }]}>{summary.totals.success} success</Text>
                </View>
                <View style={[styles.statusPill, { backgroundColor: STATUS_COLORS.pending + "22", borderColor: STATUS_COLORS.pending }]}>
                  <Ionicons name="time-outline" size={14} color={STATUS_COLORS.pending} />
                  <Text style={[styles.statusPillText, { color: STATUS_COLORS.pending }]}>{summary.totals.pending} pending</Text>
                </View>
                <View style={[styles.statusPill, { backgroundColor: STATUS_COLORS.failed + "22", borderColor: STATUS_COLORS.failed }]}>
                  <Ionicons name="close-circle" size={14} color={STATUS_COLORS.failed} />
                  <Text style={[styles.statusPillText, { color: STATUS_COLORS.failed }]}>{summary.totals.failed} failed</Text>
                </View>
              </View>

              {/* By method */}
              <View style={styles.methodCard}>
                <Text style={styles.sectionLabel}>BY METHOD</Text>
                {summary.byMethod.length === 0 ? (
                  <Text style={type.bodyMuted}>No transactions yet.</Text>
                ) : (
                  summary.byMethod.map((m) => {
                    const meta = METHOD_META[m.method] || { label: m.method, icon: "cash", color: colors.brandPrimary };
                    return (
                      <View key={m.method} style={styles.methodRow}>
                        <View style={[styles.methodIcon, { backgroundColor: meta.color + "22" }]}>
                          <Ionicons name={meta.icon} size={16} color={meta.color} />
                        </View>
                        <View style={{ flex: 1 }}>
                          <Text style={styles.methodName}>{meta.label}</Text>
                          <Text style={styles.methodMeta}>{m.count} transaction{m.count !== 1 ? "s" : ""}</Text>
                        </View>
                        <View style={{ alignItems: "flex-end" }}>
                          {Object.keys(m.revenue).length === 0 ? (
                            <Text style={styles.methodAmount}>—</Text>
                          ) : (
                            Object.entries(m.revenue).map(([cur, amt]) => (
                              <Text key={cur} style={styles.methodAmount}>{fmtMoney(amt, cur)}</Text>
                            ))
                          )}
                        </View>
                      </View>
                    );
                  })
                )}
              </View>

              {/* Transactions list */}
              <View style={styles.txHeader}>
                <Text style={styles.sectionLabel}>TRANSACTIONS ({filtered.length})</Text>
                <View style={styles.filterChips}>
                  {["all", "success", "pending", "failed"].map((s) => (
                    <Pressable
                      key={s}
                      onPress={() => setStatusFilter(s)}
                      style={[styles.chip, statusFilter === s && styles.chipActive]}
                      testID={`filter-${s}`}
                    >
                      <Text style={[styles.chipText, statusFilter === s && styles.chipTextActive]}>{s.toUpperCase()}</Text>
                    </Pressable>
                  ))}
                </View>
              </View>

              <View style={{ gap: spacing.sm }}>
                {filtered.map((p) => {
                  const meta = METHOD_META[p.method] || { label: p.method, icon: "cash", color: colors.brandPrimary };
                  return (
                    <View key={p.id} style={styles.txRow} testID={`tx-${p.id}`}>
                      <View style={[styles.methodIcon, { backgroundColor: meta.color + "22" }]}>
                        <Ionicons name={meta.icon} size={16} color={meta.color} />
                      </View>
                      <View style={{ flex: 1 }}>
                        <Text style={styles.txTitle} numberOfLines={1}>
                          {p.planLabel || p.plan || meta.label}
                        </Text>
                        <Text style={styles.txSub} numberOfLines={1}>
                          {p.userPhone || p.userEmail || "anonymous"} · {fmtWhen(p.createdAt)}
                        </Text>
                      </View>
                      <View style={{ alignItems: "flex-end" }}>
                        <Text style={styles.txAmount}>{fmtMoney(p.amount, p.currency)}</Text>
                        <View style={[styles.txStatus, { backgroundColor: (STATUS_COLORS[p.status] || "#999") + "22" }]}>
                          <Text style={[styles.txStatusText, { color: STATUS_COLORS[p.status] || "#999" }]}>{p.status}</Text>
                        </View>
                      </View>
                    </View>
                  );
                })}
                {filtered.length === 0 && (
                  <View style={{ padding: spacing.xl, alignItems: "center" }}>
                    <Ionicons name="receipt-outline" size={40} color={colors.onSurfaceSecondary} />
                    <Text style={[type.bodyMuted, { marginTop: spacing.sm }]}>No transactions match.</Text>
                  </View>
                )}
              </View>
            </>
          )
        )}
      </ScrollView>
    </View>
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
  csvBtn: { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: colors.brandPrimary, paddingHorizontal: 10, paddingVertical: 6, borderRadius: radius.pill },
  pdfBtn: { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: colors.brandSecondary, paddingHorizontal: 10, paddingVertical: 6, borderRadius: radius.pill },
  pdfBtnText: { color: "#fff", fontFamily: "BarlowCondensed-Bold", letterSpacing: 1.2, fontSize: 12 },
  csvBtnText: { color: "#000", fontFamily: "BarlowCondensed-Bold", letterSpacing: 1.5, fontSize: 11, fontWeight: "900" },
  windowSegment: {
    flexDirection: "row",
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.pill,
    padding: 3,
    borderWidth: 1,
    borderColor: colors.border,
  },
  windowItem: { flex: 1, paddingVertical: 8, alignItems: "center", borderRadius: radius.pill },
  windowItemActive: { backgroundColor: colors.brandPrimary },
  windowText: { fontFamily: "BarlowCondensed-Bold", fontSize: 12, letterSpacing: 1.5, color: colors.onSurfaceSecondary },
  windowTextActive: { color: colors.onBrandPrimary },
  revenueGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  revCard: {
    flex: 1,
    minWidth: 130,
    padding: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.brandPrimary,
    backgroundColor: colors.brandTertiary,
  },
  revAmount: { ...type.h1, color: colors.brandPrimary, fontSize: 22, letterSpacing: 0 },
  revLabel: { ...type.caption, marginTop: 4, color: colors.onBrandTertiary },
  statusRow: { flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" },
  statusPill: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingHorizontal: spacing.sm,
    paddingVertical: 6,
    borderRadius: radius.pill,
    borderWidth: 1,
  },
  statusPillText: { fontSize: 11, fontFamily: "BarlowCondensed-Bold", letterSpacing: 0.5 },
  methodCard: {
    padding: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surfaceSecondary,
    gap: spacing.sm,
  },
  sectionLabel: { ...type.label, letterSpacing: 1.5, color: colors.brandPrimary, marginBottom: 2 },
  methodRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    paddingVertical: 6,
  },
  methodIcon: {
    width: 36,
    height: 36,
    borderRadius: 18,
    alignItems: "center",
    justifyContent: "center",
  },
  methodName: { ...type.h2, fontSize: 14 },
  methodMeta: { ...type.caption, marginTop: 2 },
  methodAmount: { ...type.h2, fontSize: 13, color: colors.brandPrimary },
  txHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: spacing.sm },
  filterChips: { flexDirection: "row", gap: 4, flexWrap: "wrap" },
  chip: {
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
  },
  chipActive: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  chipText: { fontSize: 10, color: colors.onSurfaceSecondary, fontFamily: "BarlowCondensed-Bold", letterSpacing: 1 },
  chipTextActive: { color: colors.onBrandPrimary },
  txRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    padding: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surfaceSecondary,
  },
  txTitle: { ...type.h2, fontSize: 13 },
  txSub: { ...type.caption, marginTop: 2 },
  txAmount: { ...type.h2, fontSize: 13, color: colors.brandPrimary },
  txStatus: { paddingHorizontal: 6, paddingVertical: 2, borderRadius: radius.sm, marginTop: 3 },
  txStatusText: { fontSize: 9, fontFamily: "BarlowCondensed-Bold", letterSpacing: 0.5 },
});
