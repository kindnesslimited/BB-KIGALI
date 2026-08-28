import { useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, TextInput, ActivityIndicator, KeyboardAvoidingView, Platform } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { colors, spacing, type, radius } from "@/src/theme";
import { api } from "@/src/api";

type Settings = {
  stationName?: string;
  stationTagline?: string;
  frequency?: string;
  logoUrl?: string;
  radioStreamUrl?: string;
  youtubeLiveUrl?: string;
};

export default function AdminSettings() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [data, setData] = useState<Settings>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try { setData(await api<Settings>("/admin/settings", { auth: true })); }
      catch (e: any) { setErr(e.message); }
      finally { setLoading(false); }
    })();
  }, []);

  const save = async () => {
    setSaving(true); setErr(null); setSaved(false);
    try {
      const r = await api<Settings>("/admin/settings", { method: "PUT", auth: true, body: data });
      setData(r);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (e: any) { setErr(e.message); }
    finally { setSaving(false); }
  };

  const setField = (key: keyof Settings) => (v: string) => setData((d) => ({ ...d, [key]: v }));

  if (loading) return <View style={styles.center}><ActivityIndicator color={colors.brandPrimary} /></View>;

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.top, { paddingTop: insets.top + spacing.md }]}>
        <Pressable onPress={() => router.back()} hitSlop={12} testID="settings-back" style={styles.iconRound}>
          <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>LIVE URLs</Text>
        <View style={{ width: 40 }} />
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 160 }} testID="admin-settings">
        <Field label="Station name" value={data.stationName || ""} onChange={setField("stationName")} placeholder="B&B Kigali" testID="input-station-name" />
        <Field label="Tagline" value={data.stationTagline || ""} onChange={setField("stationTagline")} placeholder="MURI SPORTS, NI IGITEGO!" testID="input-tagline" />
        <Field label="Frequency" value={data.frequency || ""} onChange={setField("frequency")} placeholder="89.7 FM" testID="input-frequency" />
        <Field label="Logo URL" value={data.logoUrl || ""} onChange={setField("logoUrl")} placeholder="https://..." testID="input-logo-url" />

        <View style={styles.divider} />
        <Text style={styles.sectionLabel}>LIVE FM (AUDIO STREAM)</Text>
        <Field
          label="Radio stream URL"
          value={data.radioStreamUrl || ""}
          onChange={setField("radioStreamUrl")}
          placeholder="https://stream.zeno.fm/xxxx or https://icecast.example/live"
          testID="input-radio-url"
        />

        <View style={styles.divider} />
        <Text style={styles.sectionLabel}>LIVE YOUTUBE (LIVE NEWS)</Text>
        <Field
          label="YouTube live URL"
          value={data.youtubeLiveUrl || ""}
          onChange={setField("youtubeLiveUrl")}
          placeholder="https://www.youtube.com/watch?v=VIDEOID"
          testID="input-youtube-live"
        />
        <Text style={styles.hint}>Paste the full YouTube watch URL. We&apos;ll extract the video ID and embed it automatically.</Text>

        {err && <Text style={styles.err}>{err}</Text>}
        {saved && <Text style={styles.ok} testID="settings-saved">✓ Saved</Text>}
      </ScrollView>
      <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.md }]}>
        <Pressable onPress={save} disabled={saving} style={[styles.saveBtn, saving && { opacity: 0.6 }]} testID="settings-save">
          {saving ? <ActivityIndicator color={colors.onBrandPrimary} /> : <Text style={styles.saveText}>SAVE CHANGES</Text>}
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

function Field({ label, value, onChange, placeholder, testID }: { label: string; value: string; onChange: (v: string) => void; placeholder?: string; testID?: string }) {
  return (
    <View style={{ marginBottom: spacing.lg }}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <TextInput
        value={value}
        onChangeText={onChange}
        placeholder={placeholder}
        placeholderTextColor={colors.onSurfaceSecondary}
        style={styles.input}
        autoCapitalize="none"
        testID={testID}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center" },
  top: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.lg, paddingBottom: spacing.sm, backgroundColor: colors.surface, borderBottomWidth: 1, borderBottomColor: colors.divider },
  iconRound: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
  title: { ...type.h1, flex: 1, textAlign: "center", letterSpacing: 1.5 },
  fieldLabel: { ...type.label, marginBottom: spacing.xs, color: colors.onSurfaceSecondary },
  input: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.md, color: colors.onSurface, fontSize: 15, borderWidth: 1, borderColor: colors.border },
  sectionLabel: { ...type.label, letterSpacing: 1.5, color: colors.brandPrimary, marginBottom: spacing.md },
  divider: { height: 1, backgroundColor: colors.divider, marginVertical: spacing.md },
  hint: { ...type.caption, marginTop: -spacing.md },
  err: { color: colors.error, marginTop: spacing.md },
  ok: { color: colors.success, marginTop: spacing.md, textAlign: "center", fontFamily: "BarlowCondensed-Bold", letterSpacing: 1.5 },
  footer: { position: "absolute", left: 0, right: 0, bottom: 0, backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.border, padding: spacing.lg },
  saveBtn: { backgroundColor: colors.brandPrimary, height: 52, borderRadius: radius.md, alignItems: "center", justifyContent: "center" },
  saveText: { ...type.h2, color: colors.onBrandPrimary, letterSpacing: 1.5 },
});
