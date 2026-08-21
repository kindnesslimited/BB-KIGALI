import { useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, TextInput, ActivityIndicator, Alert, KeyboardAvoidingView, Platform } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { Image } from "expo-image";
import { colors, spacing, type, radius } from "@/src/theme";
import { api } from "@/src/api";

type Show = { id: string; title: string; category: string; description?: string; thumbnail?: string; videoUrl: string; duration?: string; premium?: boolean };

const CATS = ["vod", "podcast", "interview"];

export default function AdminShows() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [items, setItems] = useState<Show[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState<Partial<Show>>({ title: "", category: "vod", videoUrl: "", description: "" });

  const load = async () => {
    try { setItems(await api<Show[]>("/shows")); }
    catch { /* noop */ } finally { setLoading(false); }
  };
  useEffect(() => { void load(); }, []);

  const create = async () => {
    if (!form.title || !form.videoUrl) { Alert.alert("Missing fields", "Title and video URL are required."); return; }
    try {
      await api("/admin/shows", { method: "POST", auth: true, body: form });
      setForm({ title: "", category: "vod", videoUrl: "", description: "" });
      setCreating(false);
      await load();
    } catch (e: any) { Alert.alert("Create failed", e.message); }
  };

  const del = (s: Show) => {
    Alert.alert("Delete show?", `"${s.title}" will be removed.`, [
      { text: "Cancel", style: "cancel" },
      { text: "Delete", style: "destructive", onPress: async () => {
        try { await api(`/admin/shows/${s.id}`, { method: "DELETE", auth: true }); await load(); }
        catch (e: any) { Alert.alert("Delete failed", e.message); }
      } },
    ]);
  };

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.top, { paddingTop: insets.top + spacing.md }]}>
        <Pressable onPress={() => router.back()} hitSlop={12} testID="shows-back" style={styles.iconRound}>
          <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>VOD & PODCASTS</Text>
        <Pressable onPress={() => setCreating(!creating)} hitSlop={8} testID="shows-add-toggle">
          <Ionicons name={creating ? "close" : "add"} size={26} color={colors.brandPrimary} />
        </Pressable>
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 160 }} testID="admin-shows">
        {creating && (
          <View style={styles.card} testID="new-show-form">
            <Text style={styles.sectionLabel}>NEW SHOW</Text>
            <TextInput value={form.title || ""} onChangeText={(v) => setForm({ ...form, title: v })} placeholder="Title" placeholderTextColor={colors.onSurfaceSecondary} style={styles.input} testID="new-show-title" />
            <TextInput value={form.videoUrl || ""} onChangeText={(v) => setForm({ ...form, videoUrl: v })} placeholder="YouTube URL (watch or embed)" placeholderTextColor={colors.onSurfaceSecondary} style={[styles.input, { marginTop: spacing.sm }]} autoCapitalize="none" testID="new-show-url" />
            <TextInput value={form.description || ""} onChangeText={(v) => setForm({ ...form, description: v })} placeholder="Description" placeholderTextColor={colors.onSurfaceSecondary} style={[styles.input, { marginTop: spacing.sm, height: 80 }]} multiline testID="new-show-desc" />
            <View style={styles.catRow}>
              {CATS.map((c) => (
                <Pressable key={c} onPress={() => setForm({ ...form, category: c })} style={[styles.catChip, form.category === c && styles.catChipActive]}>
                  <Text style={[styles.catChipText, form.category === c && { color: colors.onBrandPrimary }]}>{c.toUpperCase()}</Text>
                </Pressable>
              ))}
            </View>
            <Pressable onPress={create} style={styles.saveBtn} testID="new-show-save">
              <Text style={styles.saveText}>PUBLISH</Text>
            </Pressable>
          </View>
        )}

        {loading && <ActivityIndicator color={colors.brandPrimary} />}
        <View style={{ gap: spacing.md, marginTop: spacing.md }}>
          {items.map((s) => (
            <View key={s.id} style={styles.showRow}>
              {s.thumbnail ? <Image source={{ uri: s.thumbnail }} style={styles.thumb} contentFit="cover" /> : <View style={[styles.thumb, styles.thumbFallback]}><Ionicons name="videocam" size={20} color={colors.onSurfaceSecondary} /></View>}
              <View style={{ flex: 1 }}>
                <Text numberOfLines={2} style={styles.showTitle}>{s.title}</Text>
                <Text style={styles.showMeta}>{s.category.toUpperCase()} · {s.duration || "—"}</Text>
              </View>
              <Pressable onPress={() => del(s)} hitSlop={8} testID={`del-show-${s.id}`}>
                <Ionicons name="trash-outline" size={22} color={colors.error} />
              </Pressable>
            </View>
          ))}
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  top: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.lg, paddingBottom: spacing.sm, backgroundColor: colors.surface, borderBottomWidth: 1, borderBottomColor: colors.divider },
  iconRound: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
  title: { ...type.h1, flex: 1, textAlign: "center", letterSpacing: 1.5 },
  card: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.lg, borderWidth: 1, borderColor: colors.brandPrimary },
  sectionLabel: { ...type.label, letterSpacing: 1.5, marginBottom: spacing.sm, color: colors.brandPrimary },
  input: { backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.md, color: colors.onSurface, fontSize: 15, borderWidth: 1, borderColor: colors.border },
  catRow: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.md, marginBottom: spacing.md },
  catChip: { paddingHorizontal: spacing.md, paddingVertical: 8, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  catChipActive: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  catChipText: { color: colors.onSurfaceSecondary, fontSize: 12, fontFamily: "BarlowCondensed-Bold", letterSpacing: 1 },
  saveBtn: { backgroundColor: colors.brandPrimary, height: 48, borderRadius: radius.md, alignItems: "center", justifyContent: "center", marginTop: spacing.sm },
  saveText: { ...type.h2, color: colors.onBrandPrimary, letterSpacing: 1.5, fontSize: 14 },
  showRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border },
  thumb: { width: 72, height: 54, borderRadius: radius.sm, backgroundColor: colors.surfaceTertiary },
  thumbFallback: { alignItems: "center", justifyContent: "center" },
  showTitle: { ...type.h2, fontSize: 14, lineHeight: 18 },
  showMeta: { ...type.caption, marginTop: 3 },
});
