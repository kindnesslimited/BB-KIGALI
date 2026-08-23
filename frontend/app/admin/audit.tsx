import { useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, ActivityIndicator, RefreshControl, TextInput } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { colors, spacing, type, radius } from "@/src/theme";
import { api } from "@/src/api";

type AuditRow = {
  id: string;
  actorId: string;
  actorName?: string;
  actorEmail?: string;
  actorPhone?: string;
  action: string;
  targetType: string;
  targetId?: string;
  summary?: string;
  metadata?: any;
  createdAt: string;
};

const ACTION_ICONS: Record<string, [string, string]> = {
  create: ["add-circle-outline", "#22c55e"],
  update: ["create-outline", "#3b82f6"],
  delete: ["trash-outline", "#ef4444"],
};

function iconFor(action: string): [string, string] {
  if (action.endsWith(".delete")) return ACTION_ICONS.delete;
  if (action.endsWith(".update")) return ACTION_ICONS.update;
  if (action.endsWith(".create")) return ACTION_ICONS.create;
  return ["ellipse-outline", colors.onSurfaceSecondary];
}

export default function AdminAudit() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [rows, setRows] = useState<AuditRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [filter, setFilter] = useState<string>("");

  const load = async () => {
    try {
      const data = await api<AuditRow[]>("/admin/audit-log?limit=300", { auth: true });
      setRows(data);
    } catch {} finally { setLoading(false); setRefreshing(false); }
  };
  useEffect(() => { void load(); }, []);
  const onRefresh = () => { setRefreshing(true); void load(); };

  const filtered = rows.filter(r => {
    if (!filter.trim()) return true;
    const q = filter.toLowerCase();
    return (r.action.toLowerCase().includes(q) ||
            (r.actorName || "").toLowerCase().includes(q) ||
            (r.actorEmail || "").toLowerCase().includes(q) ||
            (r.summary || "").toLowerCase().includes(q));
  });

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.top, { paddingTop: insets.top + spacing.md }]}>
        <Pressable onPress={() => router.back()} hitSlop={12}><Ionicons name="chevron-back" size={26} color={colors.onSurface} /></Pressable>
        <Text style={styles.title}>ACTIVITY / AUDIT LOG</Text>
        <View style={{ width: 26 }} />
      </View>
      <View style={{ paddingHorizontal: spacing.lg, paddingTop: spacing.md }}>
        <View style={styles.search}>
          <Ionicons name="search" size={18} color={colors.onSurfaceSecondary} />
          <TextInput
            value={filter}
            onChangeText={setFilter}
            placeholder="Search action, actor, target…"
            placeholderTextColor={colors.onSurfaceSecondary}
            style={styles.searchInput}
            autoCapitalize="none"
            testID="audit-search"
          />
        </View>
      </View>
      <ScrollView
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + 40, gap: spacing.sm }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.brandPrimary} />}
        testID="admin-audit"
      >
        {loading && <ActivityIndicator color={colors.brandPrimary} />}
        {!loading && filtered.length === 0 && <Text style={type.bodyMuted}>No audit events yet.</Text>}
        {filtered.map((r) => {
          const [icon, color] = iconFor(r.action);
          return (
            <View key={r.id} style={styles.row}>
              <View style={[styles.iconBubble, { backgroundColor: color + "22", borderColor: color }]}>
                <Ionicons name={icon as any} size={18} color={color} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.action}>{r.action.replace(".", " · ").toUpperCase()}</Text>
                <Text style={styles.summary} numberOfLines={2}>{r.summary || `${r.targetType} ${r.targetId?.slice(0, 8) || ""}`}</Text>
                <Text style={styles.meta}>
                  {new Date(r.createdAt).toLocaleString()}  ·  {r.actorName || r.actorPhone || r.actorEmail || r.actorId?.slice(0,8)}
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
  search: { flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, paddingHorizontal: spacing.md, height: 44 },
  searchInput: { flex: 1, color: colors.onSurface, fontSize: 14, height: "100%" },
  row: { flexDirection: "row", gap: spacing.md, padding: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border },
  iconBubble: { width: 36, height: 36, borderRadius: radius.sm, alignItems: "center", justifyContent: "center", borderWidth: 1 },
  action: { ...type.label, letterSpacing: 1.5, fontSize: 11, color: colors.onSurfaceSecondary },
  summary: { ...type.body, fontSize: 14, marginTop: 4, color: colors.onSurface },
  meta: { ...type.caption, marginTop: 4, fontSize: 11 },
});
