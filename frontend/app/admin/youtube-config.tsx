import { useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, TextInput, ActivityIndicator, Alert, Linking, Platform } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { colors, spacing, type, radius } from "@/src/theme";
import { api } from "@/src/api";

type YTConfig = {
  handle?: string;
  apiKey?: string;
  hasApiKey?: boolean;
  hasOAuthClient?: boolean;
  hasRefreshToken?: boolean;
  channelName?: string;
  channelId?: string;
  connectedAt?: string;
  callbackUrl?: string;
};

/**
 * Admin panel: connect or switch the YouTube channel used across the app for
 *  - Public LIVE detection (Home banner)
 *  - Live-show → Publish to YouTube (auto-upload)
 *
 * No code changes needed to switch channels — enter the new handle + OAuth
 * client on this screen, run the OAuth grant, done.
 */
export default function YouTubeConfig() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [cfg, setCfg] = useState<YTConfig>({});
  const [loading, setLoading] = useState(true);
  const [handle, setHandle] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [oauthClientId, setOauthClientId] = useState("");
  const [oauthClientSecret, setOauthClientSecret] = useState("");
  const [saving, setSaving] = useState(false);
  const [connecting, setConnecting] = useState(false);

  const load = async () => {
    try {
      const c = await api<YTConfig>("/admin/youtube/config", { auth: true });
      setCfg(c);
      setHandle(c.handle || "");
    } catch (e: any) { Alert.alert("Load failed", e.message); }
    finally { setLoading(false); }
  };
  useEffect(() => { void load(); }, []);

  const saveConfig = async () => {
    setSaving(true);
    try {
      const payload: any = {};
      if (handle.trim()) payload.handle = handle.trim();
      if (apiKey.trim()) payload.apiKey = apiKey.trim();
      if (oauthClientId.trim()) payload.oauthClientId = oauthClientId.trim();
      if (oauthClientSecret.trim()) payload.oauthClientSecret = oauthClientSecret.trim();
      if (Object.keys(payload).length === 0) { Alert.alert("Nothing to save", "Enter at least one field."); return; }
      await api("/admin/youtube/config", { method: "PUT", auth: true, body: payload });
      // Clear the sensitive inputs after save
      setApiKey(""); setOauthClientId(""); setOauthClientSecret("");
      await load();
      Alert.alert("Saved", "YouTube configuration updated.");
    } catch (e: any) { Alert.alert("Save failed", e.message); }
    finally { setSaving(false); }
  };

  const connectChannel = async () => {
    if (!cfg.hasOAuthClient) {
      Alert.alert("Missing OAuth credentials", "Paste your Google OAuth Client ID + Client Secret and save, then try again.");
      return;
    }
    setConnecting(true);
    try {
      const r = await api<{ url: string; redirectUri: string }>("/admin/youtube/oauth-start", { auth: true });
      Alert.alert(
        "Authorize BB FM to upload to your YouTube channel",
        `1. A YouTube consent page will open in your browser.\n\n2. Sign in with the YouTube channel admin account (@bbkigalifm) and click ALLOW.\n\n3. You will land on a "✅ YouTube Connected" page. Return here and pull to refresh.`,
        [
          { text: "Cancel", style: "cancel" },
          { text: "Open Consent Page", onPress: () => Linking.openURL(r.url) },
        ]
      );
    } catch (e: any) { Alert.alert("Cannot start OAuth", e.message); }
    finally { setConnecting(false); }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.top, { paddingTop: insets.top + spacing.md }]}>
        <Pressable onPress={() => router.back()} hitSlop={12}><Ionicons name="chevron-back" size={26} color={colors.onSurface} /></Pressable>
        <Text style={styles.title}>YOUTUBE CHANNEL</Text>
        <Pressable onPress={load} hitSlop={12}><Ionicons name="refresh" size={20} color={colors.brandPrimary} /></Pressable>
      </View>

      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 120, gap: spacing.lg }}>
        {loading && <ActivityIndicator color={colors.brandPrimary} />}

        {/* Connection status */}
        <View style={[styles.card, { borderColor: cfg.hasRefreshToken ? colors.success : colors.border }]}>
          <Text style={styles.sectionLabel}>CONNECTION STATUS</Text>
          <View style={styles.statusRow}>
            <Ionicons name={cfg.hasApiKey ? "checkmark-circle" : "close-circle-outline"} size={18} color={cfg.hasApiKey ? colors.success : colors.onSurfaceSecondary} />
            <Text style={styles.statusText}>YouTube API Key{cfg.hasApiKey ? ` — ${cfg.apiKey || "configured"}` : " — not set (uses fallback env)"}</Text>
          </View>
          <View style={styles.statusRow}>
            <Ionicons name={cfg.hasOAuthClient ? "checkmark-circle" : "close-circle-outline"} size={18} color={cfg.hasOAuthClient ? colors.success : colors.onSurfaceSecondary} />
            <Text style={styles.statusText}>OAuth Client ID + Secret{cfg.hasOAuthClient ? " — saved" : " — required for auto-upload"}</Text>
          </View>
          <View style={styles.statusRow}>
            <Ionicons name={cfg.hasRefreshToken ? "checkmark-circle" : "close-circle-outline"} size={18} color={cfg.hasRefreshToken ? colors.success : colors.onSurfaceSecondary} />
            <Text style={styles.statusText}>Channel Authorized{cfg.hasRefreshToken ? ` — ${cfg.channelName || "connected"}` : " — not connected"}</Text>
          </View>
          {cfg.channelId && <Text style={styles.channelIdText}>Channel ID: {cfg.channelId}</Text>}
          {cfg.connectedAt && <Text style={styles.channelIdText}>Connected: {cfg.connectedAt}</Text>}

          {cfg.hasOAuthClient && (
            <Pressable onPress={connectChannel} disabled={connecting} style={[styles.connectBtn, connecting && { opacity: 0.6 }]} testID="yt-connect">
              {connecting ? <ActivityIndicator color="#fff" /> : (
                <>
                  <Ionicons name="logo-youtube" size={18} color="#fff" />
                  <Text style={styles.connectBtnText}>{cfg.hasRefreshToken ? "RECONNECT CHANNEL" : "CONNECT YOUTUBE CHANNEL"}</Text>
                </>
              )}
            </Pressable>
          )}
        </View>

        {/* Channel handle + API key */}
        <View style={styles.card}>
          <Text style={styles.sectionLabel}>CHANNEL SETTINGS</Text>
          <Text style={styles.help}>Handle used for LIVE detection. Include the @ sign.</Text>
          <TextInput value={handle} onChangeText={setHandle} placeholder="@bbkigalifm" placeholderTextColor={colors.onSurfaceSecondary} style={styles.input} autoCapitalize="none" testID="yt-handle" />
          <Text style={[styles.help, { marginTop: spacing.md }]}>YouTube Data API Key (optional — falls back to env var). Get from Google Cloud Console → APIs &amp; Services → Credentials.</Text>
          <TextInput value={apiKey} onChangeText={setApiKey} placeholder="Paste new API key to update" placeholderTextColor={colors.onSurfaceSecondary} style={styles.input} autoCapitalize="none" secureTextEntry testID="yt-api-key" />
        </View>

        {/* OAuth client */}
        <View style={styles.card}>
          <Text style={styles.sectionLabel}>OAUTH2 CLIENT (FOR AUTO-UPLOAD)</Text>
          <Text style={styles.help}>Create in Google Cloud Console → APIs &amp; Services → Credentials → &quot;OAuth client ID&quot; → Application type &quot;Web application&quot;.</Text>
          <Text style={[styles.help, { marginTop: 6, color: colors.brandPrimary }]}>Authorized redirect URI to add there:</Text>
          <Pressable onPress={() => { if (cfg.callbackUrl && Platform.OS !== "web") Linking.openURL(cfg.callbackUrl).catch(() => {}); }} style={styles.codeBox}>
            <Text style={styles.codeText}>{cfg.callbackUrl || "…"}</Text>
          </Pressable>
          <TextInput value={oauthClientId} onChangeText={setOauthClientId} placeholder="OAuth Client ID (…apps.googleusercontent.com)" placeholderTextColor={colors.onSurfaceSecondary} style={[styles.input, { marginTop: spacing.md }]} autoCapitalize="none" testID="yt-oauth-cid" />
          <TextInput value={oauthClientSecret} onChangeText={setOauthClientSecret} placeholder="OAuth Client Secret" placeholderTextColor={colors.onSurfaceSecondary} style={[styles.input, { marginTop: spacing.sm }]} autoCapitalize="none" secureTextEntry testID="yt-oauth-cs" />
        </View>

        <Pressable onPress={saveConfig} disabled={saving} style={[styles.saveBtn, saving && { opacity: 0.6 }]} testID="yt-save">
          {saving ? <ActivityIndicator color="#000" /> : (
            <>
              <Ionicons name="save-outline" size={16} color="#000" />
              <Text style={styles.saveBtnText}>SAVE CONFIGURATION</Text>
            </>
          )}
        </Pressable>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  top: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.border },
  title: { ...type.h2, letterSpacing: 1.5 },
  card: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.md, borderWidth: 1, borderColor: colors.border, gap: spacing.sm },
  sectionLabel: { ...type.label, letterSpacing: 1.5, fontSize: 12, marginBottom: spacing.xs, color: colors.onSurfaceSecondary },
  statusRow: { flexDirection: "row", alignItems: "center", gap: 8, paddingVertical: 2 },
  statusText: { ...type.body, fontSize: 13 },
  channelIdText: { ...type.caption, fontSize: 11 },
  help: { ...type.caption, fontSize: 12, lineHeight: 16 },
  input: { backgroundColor: colors.surface, color: colors.onSurface, borderRadius: radius.md, padding: spacing.md, borderWidth: 1, borderColor: colors.border },
  codeBox: { backgroundColor: colors.surface, padding: spacing.sm, borderRadius: radius.sm, borderWidth: 1, borderColor: colors.border },
  codeText: { ...type.caption, fontFamily: "Courier", color: colors.brandPrimary, fontSize: 12 },
  connectBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, backgroundColor: "#ff0000", paddingHorizontal: spacing.lg, paddingVertical: spacing.md, borderRadius: radius.pill, marginTop: spacing.md },
  connectBtnText: { color: "#fff", fontFamily: "BarlowCondensed-Bold", letterSpacing: 1.5, fontSize: 14 },
  saveBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, height: 52, backgroundColor: colors.brandPrimary, borderRadius: radius.pill },
  saveBtnText: { color: "#000", fontFamily: "BarlowCondensed-Bold", letterSpacing: 1.8, fontSize: 15 },
});
