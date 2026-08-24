import { useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, TextInput, ActivityIndicator, Alert, KeyboardAvoidingView, Platform, Linking } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { Image } from "expo-image";
import * as DocumentPicker from "expo-document-picker";
import { colors, spacing, type, radius } from "@/src/theme";
import { api } from "@/src/api";
import { CoverImagePicker } from "@/src/components/CoverImagePicker";

type LiveShow = {
  id: string;
  title: string;
  description?: string;
  coverImage?: string;
  scheduledAt?: string;
  expectedDurationMin?: number;
  status: "scheduled" | "live" | "ended" | "published";
  tier?: string;
  recordingUrl?: string;
  youtubeVideoId?: string;
  youtubeChannelHandle?: string;
  youtubePublishedVideoId?: string;
  publishToYoutube?: boolean;
  publishedToYoutubeAt?: string;
};

const EMPTY: Partial<LiveShow> = { title: "", description: "", coverImage: "", scheduledAt: "", expectedDurationMin: 60, status: "scheduled", tier: "premium", publishToYoutube: false };

const STATUS_COLORS: Record<string, string> = {
  scheduled: colors.onSurfaceSecondary,
  live: "#ff0000",
  ended: colors.warning,
  published: colors.success,
};

export default function AdminLiveShows() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [items, setItems] = useState<LiveShow[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState<Partial<LiveShow>>(EMPTY);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState<string | null>(null);
  const [publishing, setPublishing] = useState<string | null>(null);

  const load = async () => {
    try { setItems(await api<LiveShow[]>("/admin/live-shows", { auth: true })); }
    catch (e: any) { Alert.alert("Load failed", e.message); }
    finally { setLoading(false); }
  };
  useEffect(() => { void load(); }, []);

  const cancel = () => { setCreating(false); setEditingId(null); setForm(EMPTY); };
  const startEdit = (s: LiveShow) => { setForm({ ...s }); setEditingId(s.id); setCreating(true); };

  const save = async () => {
    if (!form.title?.trim()) { Alert.alert("Missing", "Title is required."); return; }
    setSaving(true);
    try {
      const payload = { ...form, expectedDurationMin: Number(form.expectedDurationMin) || 60 };
      if (editingId) await api(`/admin/live-shows/${editingId}`, { method: "PATCH", auth: true, body: payload });
      else await api("/admin/live-shows", { method: "POST", auth: true, body: payload });
      cancel(); await load();
    } catch (e: any) { Alert.alert("Save failed", e.message); }
    finally { setSaving(false); }
  };

  const del = (s: LiveShow) => {
    Alert.alert("Delete live show?", `"${s.title}" will be permanently removed.`, [
      { text: "Cancel", style: "cancel" },
      { text: "Delete", style: "destructive", onPress: async () => {
        try { await api(`/admin/live-shows/${s.id}`, { method: "DELETE", auth: true }); await load(); }
        catch (e: any) { Alert.alert("Delete failed", e.message); }
      } },
    ]);
  };

  const attachYouTube = async (s: LiveShow) => {
    try {
      await api(`/admin/live-shows/${s.id}/attach-youtube-live`, { method: "POST", auth: true });
      Alert.alert("Attached", "This live show is now marked LIVE and connected to the current YouTube broadcast.");
      await load();
    } catch (e: any) { Alert.alert("Could not attach", e.message); }
  };

  const endLive = async (s: LiveShow) => {
    try { await api(`/admin/live-shows/${s.id}/end`, { method: "POST", auth: true }); await load(); }
    catch (e: any) { Alert.alert("End failed", e.message); }
  };

  const uploadRecording = async (s: LiveShow) => {
    try {
      const res = await DocumentPicker.getDocumentAsync({ type: "video/*", copyToCacheDirectory: false });
      if (res.canceled || !res.assets?.[0]) return;
      const asset = res.assets[0];
      setUploading(s.id);
      const fd = new FormData();
      // @ts-ignore — RN FormData file shape
      fd.append("file", { uri: asset.uri, name: asset.name || "recording.mp4", type: asset.mimeType || "video/mp4" });
      await api(`/admin/live-shows/${s.id}/recording`, { method: "POST", auth: true, body: fd, headers: {} });
      Alert.alert("Uploaded", "Recording saved privately on our secure host.");
      await load();
    } catch (e: any) { Alert.alert("Upload failed", e.message); }
    finally { setUploading(null); }
  };

  const publishToYouTube = async (s: LiveShow) => {
    Alert.alert(
      "Publish to YouTube?",
      `"${s.title}" will be uploaded to your connected YouTube channel as UNLISTED (you can flip to public in YouTube Studio afterwards).`,
      [
        { text: "Cancel", style: "cancel" },
        { text: "Upload", onPress: async () => {
          setPublishing(s.id);
          try {
            const r = await api<{ videoId: string; watchUrl: string }>(`/admin/live-shows/${s.id}/publish-to-youtube`, { method: "POST", auth: true });
            Alert.alert("Uploaded to YouTube", `Video ID: ${r.videoId}\n\nOpen YouTube Studio to review, tweak thumbnail, or go public.`);
            await load();
          } catch (e: any) { Alert.alert("Publish failed", e.message); }
          finally { setPublishing(null); }
        } },
      ]
    );
  };

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.top, { paddingTop: insets.top + spacing.md }]}>
        <Pressable onPress={() => router.back()} hitSlop={12}><Ionicons name="chevron-back" size={26} color={colors.onSurface} /></Pressable>
        <Text style={styles.title}>LIVE SHOWS</Text>
        <Pressable onPress={() => { cancel(); setCreating(true); }} hitSlop={12} testID="live-add-btn">
          <Ionicons name={creating ? "close" : "add"} size={26} color={creating ? colors.error : colors.brandPrimary} />
        </Pressable>
      </View>

      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 160 }} testID="admin-live-shows">
        <Pressable onPress={() => router.push("/admin/youtube-config")} style={styles.ytBanner} testID="youtube-config-shortcut">
          <Ionicons name="logo-youtube" size={20} color="#ff0000" />
          <View style={{ flex: 1 }}>
            <Text style={styles.ytBannerTitle}>YouTube Channel Connection</Text>
            <Text style={styles.ytBannerSub}>Connect or switch the YouTube channel used for live detection + auto-publish</Text>
          </View>
          <Ionicons name="chevron-forward" size={20} color={colors.onSurfaceSecondary} />
        </Pressable>

        {creating && (
          <View style={styles.card}>
            <Text style={styles.sectionLabel}>{editingId ? "EDIT LIVE SHOW" : "NEW LIVE SHOW"}</Text>
            <TextInput value={form.title || ""} onChangeText={(v) => setForm({ ...form, title: v })} placeholder="Show title" placeholderTextColor={colors.onSurfaceSecondary} style={styles.input} testID="live-title" />
            <TextInput value={form.description || ""} onChangeText={(v) => setForm({ ...form, description: v })} placeholder="Description (optional)" placeholderTextColor={colors.onSurfaceSecondary} style={[styles.input, { marginTop: spacing.sm, height: 90 }]} multiline testID="live-desc" />
            <TextInput value={form.scheduledAt || ""} onChangeText={(v) => setForm({ ...form, scheduledAt: v })} placeholder="Scheduled ISO date (e.g. 2026-09-01T18:00:00Z) — optional" placeholderTextColor={colors.onSurfaceSecondary} style={[styles.input, { marginTop: spacing.sm }]} autoCapitalize="none" testID="live-scheduled" />
            <TextInput value={String(form.expectedDurationMin ?? 60)} onChangeText={(v) => setForm({ ...form, expectedDurationMin: parseInt(v.replace(/\D/g, "") || "0", 10) })} placeholder="Expected duration (minutes)" placeholderTextColor={colors.onSurfaceSecondary} keyboardType="number-pad" style={[styles.input, { marginTop: spacing.sm }]} testID="live-duration" />
            <View style={{ marginTop: spacing.md }}>
              <CoverImagePicker value={form.coverImage} onChange={(url) => setForm({ ...form, coverImage: url })} label="Cover image (optional)" testID="live-cover" />
            </View>
            <View style={{ flexDirection: "row", gap: spacing.sm, marginTop: spacing.md }}>
              <Pressable onPress={cancel} style={[styles.btn, styles.btnGhost]}>
                <Text style={styles.btnGhostText}>CANCEL</Text>
              </Pressable>
              <Pressable onPress={save} disabled={saving} style={[styles.btn, styles.btnPrimary, saving && { opacity: 0.6 }]} testID="live-save">
                {saving ? <ActivityIndicator color="#000" /> : (<Text style={styles.btnPrimaryText}>{editingId ? "UPDATE" : "CREATE"}</Text>)}
              </Pressable>
            </View>
          </View>
        )}

        {loading && <ActivityIndicator color={colors.brandPrimary} />}

        <View style={{ gap: spacing.md, marginTop: spacing.md }}>
          {items.map((s) => (
            <View key={s.id} style={styles.showCard}>
              <View style={{ flexDirection: "row", gap: spacing.md }}>
                {s.coverImage ? (
                  <Image source={{ uri: s.coverImage }} style={styles.thumb} contentFit="cover" />
                ) : (
                  <View style={[styles.thumb, styles.thumbFallback]}><Ionicons name="videocam-outline" size={22} color={colors.onSurfaceSecondary} /></View>
                )}
                <View style={{ flex: 1 }}>
                  <View style={styles.statusRow}>
                    <View style={[styles.statusPill, { backgroundColor: STATUS_COLORS[s.status] }]}>
                      <Text style={styles.statusText}>{s.status.toUpperCase()}</Text>
                    </View>
                    {s.publishToYoutube ? (
                      <View style={[styles.statusPill, { backgroundColor: colors.brandPrimary }]}>
                        <Ionicons name="logo-youtube" size={9} color="#000" />
                        <Text style={[styles.statusText, { color: "#000" }]}>YT ON</Text>
                      </View>
                    ) : null}
                  </View>
                  <Text style={styles.showTitle} numberOfLines={2}>{s.title}</Text>
                  {!!s.scheduledAt && <Text style={styles.showMeta}>Scheduled: {s.scheduledAt}</Text>}
                  {s.recordingUrl ? <Text style={styles.showMeta}>Recording: saved privately ✓</Text> : null}
                  {s.youtubePublishedVideoId ? (
                    <Pressable onPress={() => Linking.openURL(`https://www.youtube.com/watch?v=${s.youtubePublishedVideoId}`)}>
                      <Text style={[styles.showMeta, { color: colors.brandPrimary }]}>Published: youtube.com/watch?v={s.youtubePublishedVideoId}</Text>
                    </Pressable>
                  ) : null}
                </View>
                <View style={{ gap: 8 }}>
                  <Pressable onPress={() => startEdit(s)} hitSlop={10}><Ionicons name="create-outline" size={20} color={colors.brandPrimary} /></Pressable>
                  <Pressable onPress={() => del(s)} hitSlop={10}><Ionicons name="trash-outline" size={20} color={colors.error} /></Pressable>
                </View>
              </View>

              <View style={styles.actionsRow}>
                {s.status === "scheduled" && (
                  <Pressable onPress={() => attachYouTube(s)} style={styles.actionBtn} testID={`attach-yt-${s.id}`}>
                    <Ionicons name="radio" size={14} color={colors.brandPrimary} />
                    <Text style={styles.actionBtnText}>ATTACH YOUTUBE LIVE</Text>
                  </Pressable>
                )}
                {s.status === "live" && (
                  <Pressable onPress={() => endLive(s)} style={styles.actionBtn} testID={`end-live-${s.id}`}>
                    <Ionicons name="stop-circle-outline" size={14} color={colors.error} />
                    <Text style={[styles.actionBtnText, { color: colors.error }]}>END LIVE</Text>
                  </Pressable>
                )}
                {(s.status === "ended" || s.status === "published") && (
                  <Pressable onPress={() => uploadRecording(s)} disabled={uploading === s.id} style={styles.actionBtn} testID={`upload-rec-${s.id}`}>
                    {uploading === s.id ? <ActivityIndicator size="small" color={colors.brandPrimary} /> : (
                      <>
                        <Ionicons name="cloud-upload-outline" size={14} color={colors.brandPrimary} />
                        <Text style={styles.actionBtnText}>{s.recordingUrl ? "REPLACE RECORDING" : "UPLOAD RECORDING"}</Text>
                      </>
                    )}
                  </Pressable>
                )}
                {(s.recordingUrl && !s.youtubePublishedVideoId) && (
                  <Pressable onPress={() => publishToYouTube(s)} disabled={publishing === s.id} style={[styles.actionBtn, { borderColor: "#ff0000" }]} testID={`publish-yt-${s.id}`}>
                    {publishing === s.id ? <ActivityIndicator size="small" color="#ff0000" /> : (
                      <>
                        <Ionicons name="logo-youtube" size={14} color="#ff0000" />
                        <Text style={[styles.actionBtnText, { color: "#ff0000" }]}>PUBLISH TO YOUTUBE</Text>
                      </>
                    )}
                  </Pressable>
                )}
              </View>
            </View>
          ))}
          {!loading && items.length === 0 && (
            <Text style={type.bodyMuted}>No live shows yet — tap + to create the first one.</Text>
          )}
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  top: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.border },
  title: { ...type.h2, letterSpacing: 1.5 },
  ytBanner: { flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, marginBottom: spacing.md },
  ytBannerTitle: { ...type.h2, fontSize: 14 },
  ytBannerSub: { ...type.caption, marginTop: 2 },
  card: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.md, borderWidth: 1, borderColor: colors.border },
  sectionLabel: { ...type.label, letterSpacing: 1.5, fontSize: 12, marginBottom: spacing.sm, color: colors.onSurfaceSecondary },
  input: { backgroundColor: colors.surface, color: colors.onSurface, borderRadius: radius.md, padding: spacing.md, borderWidth: 1, borderColor: colors.border },
  btn: { flex: 1, height: 48, borderRadius: radius.md, alignItems: "center", justifyContent: "center" },
  btnPrimary: { backgroundColor: colors.brandPrimary },
  btnPrimaryText: { color: "#000", fontFamily: "BarlowCondensed-Bold", letterSpacing: 1.8, fontSize: 15 },
  btnGhost: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  btnGhostText: { color: colors.onSurface, fontFamily: "BarlowCondensed-Bold", letterSpacing: 1.5, fontSize: 13 },
  showCard: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.md, borderWidth: 1, borderColor: colors.border, gap: spacing.md },
  thumb: { width: 74, height: 74, borderRadius: radius.sm, backgroundColor: colors.surface },
  thumbFallback: { alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
  statusRow: { flexDirection: "row", gap: 6, marginBottom: 4 },
  statusPill: { flexDirection: "row", alignItems: "center", gap: 3, paddingHorizontal: 6, paddingVertical: 2, borderRadius: radius.pill },
  statusText: { color: "#fff", fontFamily: "BarlowCondensed-Bold", fontSize: 9, letterSpacing: 1 },
  showTitle: { ...type.h2, fontSize: 14, lineHeight: 18 },
  showMeta: { ...type.caption, marginTop: 3, fontSize: 11 },
  actionsRow: { flexDirection: "row", gap: 6, flexWrap: "wrap" },
  actionBtn: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 10, paddingVertical: 6, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary },
  actionBtnText: { color: colors.brandPrimary, fontFamily: "BarlowCondensed-Bold", fontSize: 10, letterSpacing: 0.8 },
});
