import { useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, TextInput, ActivityIndicator, Alert, KeyboardAvoidingView, Platform, Switch } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { colors, spacing, type, radius } from "@/src/theme";
import { api } from "@/src/api";

type Sched = {
  id: string;
  time: string;
  showTitle: string;
  djName?: string;
  days?: string[];
  isLive?: boolean;
  order?: number;
};

const EMPTY: Partial<Sched> = { time: "", showTitle: "", djName: "", days: [], isLive: false, order: 0 };
const ALL_DAYS = [
  { key: "mon", label: "MON" },
  { key: "tue", label: "TUE" },
  { key: "wed", label: "WED" },
  { key: "thu", label: "THU" },
  { key: "fri", label: "FRI" },
  { key: "sat", label: "SAT" },
  { key: "sun", label: "SUN" },
];

export default function AdminSchedule() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [items, setItems] = useState<Sched[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState<Partial<Sched>>(EMPTY);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const load = async () => {
    try {
      const data = await api<Sched[]>("/radio/schedule");
      setItems(data);
    } catch { /* noop */ } finally { setLoading(false); }
  };
  useEffect(() => { void load(); }, []);

  const startEdit = (s: Sched) => {
    setForm({ time: s.time, showTitle: s.showTitle, djName: s.djName, days: s.days || [], isLive: !!s.isLive, order: s.order || 0 });
    setEditingId(s.id);
    setCreating(true);
  };

  const cancel = () => { setCreating(false); setEditingId(null); setForm(EMPTY); };

  const toggleDay = (day: string) => {
    const days = new Set(form.days || []);
    if (days.has(day)) days.delete(day); else days.add(day);
    setForm({ ...form, days: Array.from(days) });
  };

  const save = async () => {
    if (!form.time?.trim() || !form.showTitle?.trim()) {
      Alert.alert("Missing", "Time slot and program name are required.");
      return;
    }
    setSaving(true);
    try {
      const payload = {
        time: form.time,
        showTitle: form.showTitle,
        djName: form.djName || "",
        days: form.days || [],
        isLive: !!form.isLive,
        order: Number(form.order) || 0,
      };
      if (editingId) {
        await api(`/admin/schedule/${editingId}`, { method: "PATCH", auth: true, body: payload });
      } else {
        await api("/admin/schedule", { method: "POST", auth: true, body: payload });
      }
      cancel();
      await load();
    } catch (e: any) { Alert.alert("Save failed", e.message); }
    finally { setSaving(false); }
  };

  const del = (s: Sched) => {
    Alert.alert("Delete slot?", `"${s.showTitle}" (${s.time}) will be removed.`, [
      { text: "Cancel", style: "cancel" },
      { text: "Delete", style: "destructive", onPress: async () => {
        try { await api(`/admin/schedule/${s.id}`, { method: "DELETE", auth: true }); await load(); }
        catch (e: any) { Alert.alert("Delete failed", e.message); }
      } },
    ]);
  };

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.top, { paddingTop: insets.top + spacing.md }]}>
        <Pressable onPress={() => router.back()} hitSlop={12}><Ionicons name="chevron-back" size={26} color={colors.onSurface} /></Pressable>
        <Text style={styles.title}>SCHEDULE</Text>
        <Pressable onPress={() => { cancel(); setCreating(true); }} hitSlop={12} testID="sched-add-btn">
          <Ionicons name={creating ? "close" : "add"} size={26} color={creating ? colors.error : colors.brandPrimary} />
        </Pressable>
      </View>

      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 160 }} testID="admin-schedule">
        {creating && (
          <View style={styles.card}>
            <Text style={styles.sectionLabel}>{editingId ? "EDIT SLOT" : "NEW SLOT"}</Text>
            <TextInput value={form.time || ""} onChangeText={(v) => setForm({ ...form, time: v })} placeholder='Time slot (e.g. "07:00 - 09:00")' placeholderTextColor={colors.onSurfaceSecondary} style={styles.input} testID="sched-time" />
            <TextInput value={form.showTitle || ""} onChangeText={(v) => setForm({ ...form, showTitle: v })} placeholder="Program name" placeholderTextColor={colors.onSurfaceSecondary} style={[styles.input, { marginTop: spacing.sm }]} testID="sched-title" />
            <TextInput value={form.djName || ""} onChangeText={(v) => setForm({ ...form, djName: v })} placeholder="Host / Presenter" placeholderTextColor={colors.onSurfaceSecondary} style={[styles.input, { marginTop: spacing.sm }]} testID="sched-dj" />
            <TextInput
              value={String(form.order ?? 0)}
              onChangeText={(v) => setForm({ ...form, order: parseInt(v.replace(/\D/g, "") || "0", 10) })}
              placeholder="Order (0 first)" placeholderTextColor={colors.onSurfaceSecondary}
              keyboardType="number-pad"
              style={[styles.input, { marginTop: spacing.sm }]}
              testID="sched-order"
            />

            <Text style={[styles.sectionLabel, { marginTop: spacing.md, marginBottom: 6 }]}>DAYS OF WEEK</Text>
            <View style={styles.dayRow}>
              {ALL_DAYS.map((d) => {
                const on = (form.days || []).includes(d.key);
                return (
                  <Pressable key={d.key} onPress={() => toggleDay(d.key)} style={[styles.dayChip, on && styles.dayChipOn]} testID={`sched-day-${d.key}`}>
                    <Text style={[styles.dayChipText, on && styles.dayChipTextOn]}>{d.label}</Text>
                  </Pressable>
                );
              })}
            </View>

            <View style={styles.liveRow}>
              <Text style={styles.liveLabel}>Live now?</Text>
              <Switch value={!!form.isLive} onValueChange={(v) => setForm({ ...form, isLive: v })} thumbColor={form.isLive ? colors.brandPrimary : "#eee"} testID="sched-live" />
            </View>

            <View style={{ flexDirection: "row", gap: spacing.sm, marginTop: spacing.md }}>
              <Pressable onPress={cancel} style={[styles.btn, styles.btnGhost]}>
                <Text style={styles.btnGhostText}>CANCEL</Text>
              </Pressable>
              <Pressable onPress={save} disabled={saving} style={[styles.btn, styles.btnPrimary, saving && { opacity: 0.6 }]} testID="sched-save">
                {saving ? <ActivityIndicator color="#000" /> : (
                  <Text style={styles.btnPrimaryText}>{editingId ? "UPDATE" : "ADD SLOT"}</Text>
                )}
              </Pressable>
            </View>
          </View>
        )}

        {loading && <ActivityIndicator color={colors.brandPrimary} />}
        <View style={{ gap: spacing.md, marginTop: spacing.md }}>
          {items.map((s) => (
            <View key={s.id} style={styles.row}>
              <View style={styles.timeBox}>
                <Text style={styles.timeText}>{s.time}</Text>
                {s.isLive && <View style={styles.liveBadge}><Text style={styles.liveText}>LIVE</Text></View>}
              </View>
              <View style={{ flex: 1 }}>
                <Text numberOfLines={2} style={styles.rowTitle}>{s.showTitle}</Text>
                {s.djName ? <Text numberOfLines={1} style={styles.rowSub}>with {s.djName}</Text> : null}
                {s.days && s.days.length > 0 && (
                  <Text style={styles.rowDays}>{s.days.map((d) => d.toUpperCase()).join(" · ")}</Text>
                )}
              </View>
              <View style={{ gap: 6 }}>
                <Pressable onPress={() => startEdit(s)} hitSlop={12}><Ionicons name="create-outline" size={22} color={colors.brandPrimary} /></Pressable>
                <Pressable onPress={() => del(s)} hitSlop={12}><Ionicons name="trash-outline" size={22} color={colors.error} /></Pressable>
              </View>
            </View>
          ))}
          {!loading && items.length === 0 && (
            <Text style={type.bodyMuted}>No schedule slots yet — tap + to add the first one.</Text>
          )}
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  top: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.border },
  title: { ...type.h2, letterSpacing: 1.5 },
  card: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.md, borderWidth: 1, borderColor: colors.border },
  sectionLabel: { ...type.label, letterSpacing: 1.5, fontSize: 12, marginBottom: spacing.sm, color: colors.onSurfaceSecondary },
  input: { backgroundColor: colors.surface, color: colors.onSurface, borderRadius: radius.md, padding: spacing.md, borderWidth: 1, borderColor: colors.border },
  dayRow: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  dayChip: { paddingVertical: 8, paddingHorizontal: 12, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  dayChipOn: { borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary },
  dayChipText: { color: colors.onSurfaceSecondary, fontFamily: "BarlowCondensed-Bold", fontSize: 11, letterSpacing: 1 },
  dayChipTextOn: { color: colors.brandPrimary },
  liveRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: spacing.md, paddingHorizontal: 6 },
  liveLabel: { ...type.body },
  btn: { flex: 1, height: 48, borderRadius: radius.md, alignItems: "center", justifyContent: "center" },
  btnPrimary: { backgroundColor: colors.brandPrimary },
  btnPrimaryText: { color: "#000", fontFamily: "BarlowCondensed-Bold", letterSpacing: 1.8, fontSize: 15, fontWeight: "900" },
  btnGhost: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  btnGhostText: { color: colors.onSurface, fontFamily: "BarlowCondensed-Bold", letterSpacing: 1.5, fontSize: 13 },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border },
  timeBox: { alignItems: "center", minWidth: 84, gap: 4 },
  timeText: { color: colors.brandPrimary, fontFamily: "BarlowCondensed-Bold", fontSize: 13, letterSpacing: 0.5 },
  liveBadge: { paddingHorizontal: 6, paddingVertical: 2, borderRadius: radius.pill, backgroundColor: colors.brandPrimary },
  liveText: { color: "#000", fontFamily: "BarlowCondensed-Bold", fontSize: 9, letterSpacing: 1 },
  rowTitle: { ...type.h2, fontSize: 14, lineHeight: 18 },
  rowSub: { ...type.caption, marginTop: 3 },
  rowDays: { ...type.caption, marginTop: 4, color: colors.brandPrimary, fontSize: 10, letterSpacing: 0.8 },
});
