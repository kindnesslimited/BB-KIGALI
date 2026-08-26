import { useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, TextInput, ActivityIndicator, Alert, Linking } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import * as Clipboard from "expo-clipboard";
import { colors, spacing, type, radius } from "@/src/theme";
import { api } from "@/src/api";

type CfCfg = { accountId?: string; customerSubdomain?: string; hasApiToken?: boolean; connected?: boolean; connectedAt?: string };
type LiveInput = { uid?: string; rtmpsUrl?: string; streamKey?: string; playbackHls?: string; webrtcUrl?: string };

export default function AdminCloudflareStream() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [cfg, setCfg] = useState<CfCfg>({});
  const [loading, setLoading] = useState(true);
  const [accountId, setAccountId] = useState("");
  const [apiToken, setApiToken] = useState("");
  const [customerSubdomain, setCustomerSubdomain] = useState("");
  const [saving, setSaving] = useState(false);
  const [creatingLive, setCreatingLive] = useState(false);
  const [liveInput, setLiveInput] = useState<LiveInput | null>(null);

  const load = async () => {
    try { const c = await api<CfCfg>("/admin/cloudflare-stream/config", { auth: true }); setCfg(c); setAccountId(c.accountId || ""); setCustomerSubdomain(c.customerSubdomain || ""); }
    catch (e: any) { Alert.alert("Load failed", e.message); }
    finally { setLoading(false); }
  };
  useEffect(() => { void load(); }, []);

  const save = async () => {
    setSaving(true);
    try {
      const payload: any = {};
      if (accountId.trim()) payload.accountId = accountId.trim();
      if (apiToken.trim()) payload.apiToken = apiToken.trim();
      if (customerSubdomain.trim()) payload.customerSubdomain = customerSubdomain.trim();
      if (!Object.keys(payload).length) { Alert.alert("Nothing to save"); return; }
      await api("/admin/cloudflare-stream/config", { method: "PUT", auth: true, body: payload });
      setApiToken(""); await load();
      Alert.alert("Saved", "Cloudflare Stream configuration updated.");
    } catch (e: any) { Alert.alert("Save failed", e.message); }
    finally { setSaving(false); }
  };

  const createLiveInput = async () => {
    setCreatingLive(true);
    try {
      const r = await api<LiveInput>("/admin/cloudflare-stream/live-input", { method: "POST", auth: true });
      setLiveInput(r);
    } catch (e: any) { Alert.alert("Could not create live input", e.message); }
    finally { setCreatingLive(false); }
  };

  const copy = async (val: string, label: string) => {
    try { await Clipboard.setStringAsync(val); Alert.alert("Copied", `${label} copied to clipboard.`); }
    catch { /* noop */ }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.top, { paddingTop: insets.top + spacing.md }]}>
        <Pressable onPress={() => router.back()} hitSlop={12}><Ionicons name="chevron-back" size={26} color={colors.onSurface} /></Pressable>
        <Text style={styles.title}>CLOUDFLARE STREAM</Text>
        <Pressable onPress={load} hitSlop={12}><Ionicons name="refresh" size={20} color={colors.brandPrimary} /></Pressable>
      </View>

      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 120, gap: spacing.lg }}>
        {loading && <ActivityIndicator color={colors.brandPrimary} />}

        <View style={[styles.card, { borderColor: cfg.connected ? colors.success : colors.border }]}>
          <Text style={styles.sectionLabel}>CONNECTION STATUS</Text>
          <View style={styles.statusRow}>
            <Ionicons name={cfg.accountId ? "checkmark-circle" : "close-circle-outline"} size={18} color={cfg.accountId ? colors.success : colors.onSurfaceSecondary} />
            <Text style={styles.statusText}>Account ID{cfg.accountId ? ` — ${cfg.accountId}` : " — not set"}</Text>
          </View>
          <View style={styles.statusRow}>
            <Ionicons name={cfg.hasApiToken ? "checkmark-circle" : "close-circle-outline"} size={18} color={cfg.hasApiToken ? colors.success : colors.onSurfaceSecondary} />
            <Text style={styles.statusText}>API Token{cfg.hasApiToken ? " — saved (hidden)" : " — required"}</Text>
          </View>
          <View style={styles.statusRow}>
            <Ionicons name={cfg.customerSubdomain ? "checkmark-circle" : "close-circle-outline"} size={18} color={cfg.customerSubdomain ? colors.success : colors.onSurfaceSecondary} />
            <Text style={styles.statusText}>Customer subdomain{cfg.customerSubdomain ? ` — ${cfg.customerSubdomain}` : " — optional"}</Text>
          </View>
        </View>

        <View style={styles.card}>
          <Text style={styles.sectionLabel}>CREDENTIALS</Text>
          <Text style={styles.help}>Get from Cloudflare dashboard → Stream → API. Create a scoped API token with Stream:Edit permission.</Text>
          <TextInput value={accountId} onChangeText={setAccountId} placeholder="Cloudflare Account ID" placeholderTextColor={colors.onSurfaceSecondary} style={styles.input} autoCapitalize="none" testID="cf-account-id" />
          <TextInput value={apiToken} onChangeText={setApiToken} placeholder="API Token (Stream:Edit scope)" placeholderTextColor={colors.onSurfaceSecondary} style={[styles.input, { marginTop: spacing.sm }]} autoCapitalize="none" secureTextEntry testID="cf-api-token" />
          <TextInput value={customerSubdomain} onChangeText={setCustomerSubdomain} placeholder="Customer subdomain (e.g. customer-xxx.cloudflarestream.com)" placeholderTextColor={colors.onSurfaceSecondary} style={[styles.input, { marginTop: spacing.sm }]} autoCapitalize="none" testID="cf-subdomain" />
          <Pressable onPress={save} disabled={saving} style={[styles.saveBtn, saving && { opacity: 0.6 }, { marginTop: spacing.md }]} testID="cf-save">
            {saving ? <ActivityIndicator color="#000" /> : (<Text style={styles.saveBtnText}>SAVE CONFIGURATION</Text>)}
          </Pressable>
        </View>

        {cfg.connected && (
          <View style={styles.card}>
            <Text style={styles.sectionLabel}>PRIVATE LIVE STREAM (RTMP)</Text>
            <Text style={styles.help}>Create a Cloudflare Stream live input to broadcast privately from OBS or the YouTube app. Recording is automatic; playback is via signed HLS URLs served through our app only.</Text>
            <Pressable onPress={createLiveInput} disabled={creatingLive} style={[styles.saveBtn, { backgroundColor: colors.accent, marginTop: spacing.md }, creatingLive && { opacity: 0.6 }]} testID="cf-create-live">
              {creatingLive ? <ActivityIndicator color="#fff" /> : (<Text style={[styles.saveBtnText, { color: "#fff" }]}>CREATE NEW LIVE INPUT</Text>)}
            </Pressable>

            {liveInput && (
              <View style={styles.liveOut}>
                <Text style={styles.liveOutLabel}>RTMPS URL</Text>
                <Pressable onPress={() => copy(liveInput.rtmpsUrl || "", "RTMPS URL")}><Text style={styles.codeText}>{liveInput.rtmpsUrl}</Text></Pressable>
                <Text style={[styles.liveOutLabel, { marginTop: spacing.md }]}>STREAM KEY (secret!)</Text>
                <Pressable onPress={() => copy(liveInput.streamKey || "", "Stream Key")}><Text style={styles.codeText}>{liveInput.streamKey}</Text></Pressable>
                <Text style={[styles.liveOutLabel, { marginTop: spacing.md }]}>PLAYBACK HLS</Text>
                <Pressable onPress={() => copy(liveInput.playbackHls || "", "HLS URL")}><Text style={styles.codeText}>{liveInput.playbackHls}</Text></Pressable>
                <Text style={styles.help}>Paste the RTMPS URL + Stream Key into OBS &quot;Custom&quot; server, then hit Start Streaming. Copy the Playback HLS into a new Live Show so subscribers can watch.</Text>
              </View>
            )}
          </View>
        )}

        <Pressable onPress={() => Linking.openURL("https://dash.cloudflare.com/?to=/:account/stream")} style={styles.docLink}>
          <Ionicons name="open-outline" size={14} color={colors.brandPrimary} />
          <Text style={styles.docLinkText}>Open Cloudflare Stream dashboard</Text>
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
  help: { ...type.caption, fontSize: 12, lineHeight: 16 },
  input: { backgroundColor: colors.surface, color: colors.onSurface, borderRadius: radius.md, padding: spacing.md, borderWidth: 1, borderColor: colors.border },
  saveBtn: { height: 52, borderRadius: radius.pill, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
  saveBtnText: { color: "#000", fontFamily: "BarlowCondensed-Bold", letterSpacing: 1.8, fontSize: 15 },
  liveOut: { marginTop: spacing.md, padding: spacing.md, backgroundColor: colors.surface, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, gap: 4 },
  liveOutLabel: { ...type.label, letterSpacing: 1.4, fontSize: 10, color: colors.onSurfaceSecondary },
  codeText: { fontFamily: "Courier", color: colors.brandPrimary, fontSize: 12 },
  docLink: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, paddingVertical: spacing.md },
  docLinkText: { color: colors.brandPrimary, fontFamily: "BarlowCondensed-Bold", fontSize: 12, letterSpacing: 1 },
});
