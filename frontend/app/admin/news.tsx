import { useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, TextInput, ActivityIndicator, Alert, KeyboardAvoidingView, Platform } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { Image } from "expo-image";
import { colors, spacing, type, radius } from "@/src/theme";
import { api } from "@/src/api";
import { CoverImagePicker } from "@/src/components/CoverImagePicker";

type News = {
  id: string;
  title: string;
  summary?: string;
  body?: string;
  coverUrl?: string;
  category?: string;
  url?: string;
  published?: boolean;
  publishedAt?: string;
};

const EMPTY: Partial<News> = { title: "", summary: "", body: "", coverUrl: "", category: "news", url: "", published: true };

export default function AdminNews() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [items, setItems] = useState<News[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState<Partial<News>>(EMPTY);
  const [editingId, setEditingId] = useState<string | null>(null);

  const load = async () => {
    try {
      const data = await api<News[]>("/news");
      setItems(data);
    } catch { /* noop */ } finally { setLoading(false); }
  };
  useEffect(() => { void load(); }, []);

  const startEdit = (n: News) => {
    setForm({ title: n.title, summary: n.summary, body: n.body, coverUrl: n.coverUrl, category: n.category, url: n.url, published: n.published !== false });
    setEditingId(n.id);
    setCreating(true);
  };

  const cancel = () => { setCreating(false); setEditingId(null); setForm(EMPTY); };

  const save = async () => {
    if (!form.title?.trim()) { Alert.alert("Missing", "Title is required."); return; }
    try {
      if (editingId) {
        await api(`/admin/news/${editingId}`, { method: "PATCH", auth: true, body: form });
      } else {
        await api("/admin/news", { method: "POST", auth: true, body: form });
      }
      cancel();
      await load();
    } catch (e: any) { Alert.alert("Save failed", e.message); }
  };

  const del = (n: News) => {
    Alert.alert("Delete post?", `"${n.title}" will be removed.`, [
      { text: "Cancel", style: "cancel" },
      { text: "Delete", style: "destructive", onPress: async () => {
        try { await api(`/admin/news/${n.id}`, { method: "DELETE", auth: true }); await load(); }
        catch (e: any) { Alert.alert("Delete failed", e.message); }
      } },
    ]);
  };

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.top, { paddingTop: insets.top + spacing.md }]}>
        <Pressable onPress={() => router.back()} hitSlop={12}><Ionicons name="chevron-back" size={26} color={colors.onSurface} /></Pressable>
        <Text style={styles.title}>NEWS</Text>
        <Pressable onPress={() => { cancel(); setCreating(true); }} hitSlop={12} testID="news-add-btn">
          <Ionicons name={creating ? "close" : "add"} size={26} color={creating ? colors.error : colors.brandPrimary} />
        </Pressable>
      </View>

      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 160 }} testID="admin-news">
        {creating && (
          <View style={styles.card}>
            <Text style={styles.sectionLabel}>{editingId ? "EDIT POST" : "NEW POST"}</Text>
            <TextInput value={form.title || ""} onChangeText={(v) => setForm({ ...form, title: v })} placeholder="Title" placeholderTextColor={colors.onSurfaceSecondary} style={styles.input} testID="news-title" />
            <TextInput value={form.summary || ""} onChangeText={(v) => setForm({ ...form, summary: v })} placeholder="Short summary (1–2 lines)" placeholderTextColor={colors.onSurfaceSecondary} style={[styles.input, { marginTop: spacing.sm }]} testID="news-summary" />
            <TextInput value={form.body || ""} onChangeText={(v) => setForm({ ...form, body: v })} placeholder="Full story…" placeholderTextColor={colors.onSurfaceSecondary} style={[styles.input, { marginTop: spacing.sm, height: 120 }]} multiline testID="news-body" />
            <TextInput value={form.url || ""} onChangeText={(v) => setForm({ ...form, url: v })} placeholder="Optional link (https://…)" placeholderTextColor={colors.onSurfaceSecondary} style={[styles.input, { marginTop: spacing.sm }]} autoCapitalize="none" testID="news-url" />
            <View style={{ marginTop: spacing.md }}>
              <CoverImagePicker
                value={form.coverUrl}
                onChange={(url) => setForm({ ...form, coverUrl: url })}
                label="Cover image"
                testID="news-cover"
              />
            </View>
            <View style={{ flexDirection: "row", gap: spacing.sm, marginTop: spacing.md }}>
              <Pressable onPress={cancel} style={[styles.btn, styles.btnGhost]}>
                <Text style={styles.btnGhostText}>CANCEL</Text>
              </Pressable>
              <Pressable onPress={save} style={[styles.btn, styles.btnPrimary]} testID="news-save">
                <Text style={styles.btnPrimaryText}>{editingId ? "UPDATE" : "PUBLISH"}</Text>
              </Pressable>
            </View>
          </View>
        )}

        {loading && <ActivityIndicator color={colors.brandPrimary} />}
        <View style={{ gap: spacing.md, marginTop: spacing.md }}>
          {items.map((n) => (
            <View key={n.id} style={styles.row}>
              {n.coverUrl ? <Image source={{ uri: n.coverUrl }} style={styles.thumb} contentFit="cover" /> : <View style={[styles.thumb, styles.thumbFallback]}><Ionicons name="newspaper-outline" size={20} color={colors.onSurfaceSecondary} /></View>}
              <View style={{ flex: 1 }}>
                <Text numberOfLines={2} style={styles.rowTitle}>{n.title}</Text>
                {n.summary ? <Text numberOfLines={2} style={styles.rowSub}>{n.summary}</Text> : null}
              </View>
              <View style={{ gap: 6 }}>
                <Pressable onPress={() => startEdit(n)} hitSlop={12}><Ionicons name="create-outline" size={22} color={colors.brandPrimary} /></Pressable>
                <Pressable onPress={() => del(n)} hitSlop={12}><Ionicons name="trash-outline" size={22} color={colors.error} /></Pressable>
              </View>
            </View>
          ))}
          {!loading && items.length === 0 && (
            <Text style={type.bodyMuted}>No news yet — tap + to create the first post.</Text>
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
  btn: { flex: 1, height: 48, borderRadius: radius.md, alignItems: "center", justifyContent: "center" },
  btnPrimary: { backgroundColor: colors.brandPrimary },
  btnPrimaryText: { color: "#000", fontFamily: "BarlowCondensed-Bold", letterSpacing: 1.8, fontSize: 15, fontWeight: "900" },
  btnGhost: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  btnGhostText: { color: colors.onSurface, fontFamily: "BarlowCondensed-Bold", letterSpacing: 1.5, fontSize: 13 },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.sm, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border },
  thumb: { width: 80, height: 60, borderRadius: radius.sm, backgroundColor: colors.surface },
  thumbFallback: { alignItems: "center", justifyContent: "center" },
  rowTitle: { ...type.h2, fontSize: 14, lineHeight: 18 },
  rowSub: { ...type.caption, marginTop: 3 },
});
