import { useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, ActivityIndicator, RefreshControl } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { colors, spacing, type, radius } from "@/src/theme";
import { api } from "@/src/api";

type SubRow = {
  id: string;
  displayName?: string;
  phone?: string;
  email?: string;
  tier: string;
  currentPlan?: string;
  subscriptionExpiresAt?: string;
  provider?: string;
  createdAt?: string;
  status?: "active" | "expired";
};

type Filter = "active" | "expired" | "all";

export default function AdminSubs() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [rows, setRows] = useState<SubRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [filter, setFilter] = useState<Filter>("active");

  const load = async () => {
    try {
      const data = await api<SubRow[]>(`/admin/analytics/subscriptions?status=${filter}`, { auth: true });
      setRows(data);
    } catch {} finally { setLoading(false); setRefreshing(false); }
  };
  useEffect(() => { void load(); }, [filter]);
  const onRefresh = () => { setRefreshing(true); void load(); };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.top, { paddingTop: insets.top + spacing.md }]}>
        <Pressable onPress={() => router.back()} hitSlop={12}><Ionicons name="chevron-back" size={26} color={colors.onSurface} /></Pressable>
        <Text style={styles.title}>SUBSCRIPTIONS</Text>
        <View style={{ width: 26 }} />
      </View>

      <View style={styles.filterRow}>
        {(["active", "expired", "all"] as Filter[]).map((f) => (
          <Pressable key={f} onPress={() => setFilter(f)} style={[styles.chip, filter === f && styles.chipActive]}>
            <Text style={[styles.chipText, filter === f && { color: "#000" }]}>{f.toUpperCase()}</Text>
          </Pressable>
        ))}
      </View>

      <ScrollView
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 40, gap: spacing.sm }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.brandPrimary} />}
        testID="admin-subs"
      >
        <Text style={type.bodyMuted}>{rows.length} customer{rows.length === 1 ? "" : "s"}</Text>
        {loading && <ActivityIndicator color={colors.brandPrimary} />}
        {rows.map((r) => {
          const active = (r.status || "").toLowerCase() === "active";
          const exp = r.subscriptionExpiresAt ? new Date(r.subscriptionExpiresAt).toLocaleDateString() : "—";
          return (
            <View key={r.id} style={styles.row}>
              <View style={[styles.tierBadge, { backgroundColor: r.tier === "premium" ? "#7c3aed" : colors.brandPrimary }]}>
                <Text style={styles.tierText}>{(r.tier || "?").toUpperCase()}</Text>
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.name}>{r.displayName || r.phone || r.email || "—"}</Text>
                <Text style={styles.meta}>{r.phone || "—"}  ·  {r.email || "—"}</Text>
                <Text style={styles.meta}>Plan: {r.currentPlan || "—"}  ·  Expires: {exp}</Text>
              </View>
              <View style={[styles.status, active ? styles.statusActive : styles.statusExpired]}>
                <Text style={[styles.statusText, active ? { color: "#22c55e" } : { color: "#ef4444" }]}>
                  {active ? "ACTIVE" : "EXPIRED"}
                </Text>
              </View>
            </View>
          );
        })}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  top: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.border },
  title: { ...type.h2, letterSpacing: 1.5, fontSize: 16 },
  filterRow: { flexDirection: "row", gap: spacing.sm, paddingHorizontal: spacing.lg, paddingTop: spacing.md },
  chip: { paddingHorizontal: spacing.lg, paddingVertical: 8, borderRadius: radius.pill, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border },
  chipActive: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  chipText: { ...type.label, letterSpacing: 1.2, fontSize: 11, color: colors.onSurfaceSecondary },
  row: { flexDirection: "row", gap: spacing.md, padding: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, alignItems: "center" },
  tierBadge: { paddingHorizontal: 8, paddingVertical: 4, borderRadius: radius.sm },
  tierText: { color: "#000", fontFamily: "BarlowCondensed-Bold", letterSpacing: 1.2, fontSize: 10 },
  name: { ...type.h2, fontSize: 14, lineHeight: 18 },
  meta: { ...type.caption, marginTop: 2 },
  status: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: radius.pill, borderWidth: 1 },
  statusActive: { borderColor: "#22c55e", backgroundColor: "#0f2415" },
  statusExpired: { borderColor: "#ef4444", backgroundColor: "#2a0f12" },
  statusText: { ...type.label, letterSpacing: 1.2, fontSize: 10 },
});
