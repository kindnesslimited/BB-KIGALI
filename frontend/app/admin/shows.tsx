import { useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, TextInput, ActivityIndicator, Alert, KeyboardAvoidingView, Platform } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { Image } from "expo-image";
import { colors, spacing, type, radius } from "@/src/theme";
import { api } from "@/src/api";
import { CoverImagePicker } from "@/src/components/CoverImagePicker";

type Show = { id: string; title: string; category: string; description?: string; thumbnail?: string; videoUrl: string; duration?: string; premium?: boolean };
type Category = { id: string; name: string; slug: string; order: number; isActive: boolean };

export default function AdminShows() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [items, setItems] = useState<Show[]>([]);
  const [cats, setCats] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState<Partial<Show>>({ title: "", category: "vod", videoUrl: "", description: "" });

  const load = async () => {
    try {
      const [showsRes, catsRes] = await Promise.all([
        api<Show[]>("/shows"),
        api<Category[]>("/categories"),
      ]);
      setItems(showsRes);
      setCats(catsRes);
      // If current form category is not in the list, snap to first active category
      if (catsRes.length && !catsRes.some(c => c.slug === form.category)) {
        setForm(prev => ({ ...prev, category: catsRes[0].slug }));
      }
    } catch { /* noop */ } finally { setLoading(false); }
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

  const [syncing, setSyncing] = useState(false);
  const [ytStatus, setYtStatus] = useState<any>(null);
  const loadYtStatus = async () => {
    try { const s = await api<any>("/admin/youtube/status", { auth: true }); setYtStatus(s); } catch {}
  };
  useEffect(() => { void loadYtStatus(); }, []);
  const syncYouTube = async () => {
    setSyncing(true);
    try {
      const r = await api<any>("/admin/youtube/sync", { method: "POST", auth: true, body: {} });
      if (r?.ok) {
        Alert.alert("YouTube sync complete", `${r.channelTitle || r.handle}\n\nImported ${r.upserted} videos${r.skipped ? `\nSkipped ${r.skipped}` : ""}.`);
      } else {
        Alert.alert("Sync failed", r?.errors || "Unknown error");
      }
      await Promise.all([load(), loadYtStatus()]);
    } catch (e: any) {
      Alert.alert("Sync failed", e?.message || "Could not reach YouTube.");
    } finally {
      setSyncing(false);
    }
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
        <View style={styles.syncCard}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
            <View style={styles.syncIcon}><Ionicons name="logo-youtube" size={22} color="#FF0000" /></View>
            <View style={{ flex: 1 }}>
              <Text style={styles.syncTitle}>@BBKIGALIFM YOUTUBE SYNC</Text>
              <Text style={styles.syncSub}>
                {ytStatus?.lastSyncAt
                  ? `Last synced ${new Date(ytStatus.lastSyncAt).toLocaleString()}${ytStatus?.lastResult ? ` · ${ytStatus.lastResult.upserted} videos` : ""}`
                  : "Pulls the latest 50 videos from the official channel"}
              </Text>
            </View>
          </View>
          <Pressable onPress={syncYouTube} disabled={syncing} style={[styles.syncBtn, syncing && { opacity: 0.6 }]} testID="yt-sync-btn">
            {syncing ? <ActivityIndicator color="#fff" /> : <><Ionicons name="cloud-download-outline" size={18} color="#fff" /><Text style={styles.syncBtnText}>SYNC NOW</Text></>}
          </Pressable>
        </View>

        {creating && (
          <View style={styles.card} testID="new-show-form">
            <Text style={styles.sectionLabel}>NEW SHOW</Text>
            <TextInput value={form.title || ""} onChangeText={(v) => setForm({ ...form, title: v })} placeholder="Title" placeholderTextColor={colors.onSurfaceSecondary} style={styles.input} testID="new-show-title" />
            <TextInput value={form.videoUrl || ""} onChangeText={(v) => setForm({ ...form, videoUrl: v })} placeholder="YouTube URL (watch or embed)" placeholderTextColor={colors.onSurfaceSecondary} style={[styles.input, { marginTop: spacing.sm }]} autoCapitalize="none" testID="new-show-url" />
            <TextInput value={form.description || ""} onChangeText={(v) => setForm({ ...form, description: v })} placeholder="Description" placeholderTextColor={colors.onSurfaceSecondary} style={[styles.input, { marginTop: spacing.sm, height: 80 }]} multiline testID="new-show-desc" />
            <View style={{ marginTop: spacing.md }}>
              <CoverImagePicker
                value={form.thumbnail}
                onChange={(url) => setForm({ ...form, thumbnail: url })}
                label="Cover / thumbnail"
                testID="new-show-cover"
              />
            </View>
            <View style={styles.catRow}>
              {cats.map((c) => (
                <Pressable key={c.slug} onPress={() => setForm({ ...form, category: c.slug })} style={[styles.catChip, form.category === c.slug && styles.catChipActive]} testID={`new-show-cat-${c.slug}`}>
                  <Text style={[styles.catChipText, form.category === c.slug && { color: colors.onBrandPrimary }]}>{c.name.toUpperCase()}</Text>
                </Pressable>
              ))}
              {cats.length === 0 && (
                <Text style={type.bodyMuted}>No categories yet — add some in the Categories screen first.</Text>
              )}
            </View>
            <Pressable onPress={create} style={styles.saveBtn} testID="new-show-save">
              <Text style={styles.saveText}>PUBLISH</Text>
            </Pressable>
          </View>
        )}

        {loading && <ActivityIndicator color={colors.brandPrimary} />}
        <View style={{ gap: spacing.md, marginTop: spacing.md }}>
          {items.map((s) => {
            const catName = cats.find(c => c.slug === s.category)?.name || s.category || "Uncategorized";
            return (
              <View key={s.id} style={styles.showRow}>
                {s.thumbnail ? <Image source={{ uri: s.thumbnail }} style={styles.thumb} contentFit="cover" /> : <View style={[styles.thumb, styles.thumbFallback]}><Ionicons name="videocam" size={20} color={colors.onSurfaceSecondary} /></View>}
                <View style={{ flex: 1 }}>
                  <Text numberOfLines={2} style={styles.showTitle}>{s.title}</Text>
                  <Text style={styles.showMeta}>{(catName || "").toUpperCase()} · {s.duration || "—"}</Text>
                </View>
                <Pressable onPress={() => del(s)} hitSlop={8} testID={`del-show-${s.id}`}>
                  <Ionicons name="trash-outline" size={22} color={colors.error} />
                </Pressable>
              </View>
            );
          })}
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
  syncCard: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.md, borderWidth: 1, borderColor: colors.border, marginBottom: spacing.md, gap: spacing.md },
  syncIcon: { width: 40, height: 40, borderRadius: radius.sm, backgroundColor: "#111", alignItems: "center", justifyContent: "center" },
  syncTitle: { ...type.label, letterSpacing: 1.5, color: colors.onSurface, fontSize: 12 },
  syncSub: { ...type.caption, marginTop: 3 },
  syncBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, backgroundColor: "#FF0000", height: 44, borderRadius: radius.pill },
  syncBtnText: { color: "#fff", fontFamily: "BarlowCondensed-Bold", letterSpacing: 1.5, fontSize: 13 },
});
