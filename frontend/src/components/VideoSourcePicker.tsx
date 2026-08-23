import { useState } from "react";
import { View, Text, StyleSheet, Pressable, Platform, TextInput, Alert, ActivityIndicator } from "react-native";
import * as ImagePicker from "expo-image-picker";
import { Ionicons } from "@expo/vector-icons";
import { colors, spacing, type, radius } from "@/src/theme";
import { getToken } from "@/src/api";

const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL || "";

type Props = {
  value: string | null | undefined;
  onChange: (url: string) => void;
  label?: string;
  testID?: string;
};

/**
 * Video source picker for admin VOD creation.
 * - "YouTube link" mode: paste a YouTube URL (converted to embed on backend).
 * - "Upload file" mode: pick an mp4/webm/mov from device library and upload to Emergent Object Storage.
 */
export function VideoSourcePicker({ value, onChange, label = "Video source", testID }: Props) {
  const [mode, setMode] = useState<"youtube" | "file">(
    value && (value.includes("youtube.com") || value.includes("youtu.be")) ? "youtube" : "file"
  );
  const [ytInput, setYtInput] = useState(value && !value.includes("/api/uploads/") ? value : "");
  const [busy, setBusy] = useState(false);

  const applyYt = () => {
    const u = ytInput.trim();
    if (!u) return;
    if (!/^https?:\/\//i.test(u)) { Alert.alert("Invalid URL", "URL must start with http:// or https://"); return; }
    onChange(u);
  };

  const pickAndUpload = async () => {
    try {
      if (Platform.OS !== "web") {
        const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
        if (!perm.granted) { Alert.alert("Permission needed", "Allow media access to upload a video."); return; }
      }
      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ["videos"],
        allowsEditing: false,
        quality: 0.9,
      });
      if (result.canceled || !result.assets?.length) return;
      const asset = result.assets[0];
      setBusy(true);
      const form = new FormData();
      const filename = asset.fileName || `video-${Date.now()}.mp4`;
      const mimeType = asset.mimeType || "video/mp4";
      if (Platform.OS === "web") {
        const blob = await (await fetch(asset.uri)).blob();
        form.append("file", blob, filename);
      } else {
        // @ts-ignore native FormData
        form.append("file", { uri: asset.uri, name: filename, type: mimeType });
      }
      const token = await getToken();
      const r = await fetch(`${BACKEND_URL}/api/admin/uploads/video`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: form,
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data?.detail || `HTTP ${r.status}`);
      onChange(data.url);
      Alert.alert("Uploaded", `Video is ready. It will appear in the VOD section.`);
    } catch (e: any) {
      Alert.alert("Upload failed", e?.message || "Please try again.");
    } finally { setBusy(false); }
  };

  return (
    <View style={styles.wrap} testID={testID}>
      <Text style={styles.label}>{label.toUpperCase()}</Text>
      {value ? (
        <View style={styles.preview}>
          <Ionicons name={value.includes("/uploads/") ? "cloud-done-outline" : "logo-youtube"} size={22} color={value.includes("/uploads/") ? colors.brandPrimary : "#FF0000"} />
          <Text style={styles.previewText} numberOfLines={1}>{value}</Text>
          <Pressable onPress={() => onChange("")} hitSlop={12}>
            <Ionicons name="close-circle" size={20} color={colors.onSurfaceSecondary} />
          </Pressable>
        </View>
      ) : null}
      <View style={styles.tabs}>
        <Pressable onPress={() => setMode("youtube")} style={[styles.tab, mode === "youtube" && styles.tabActive]}>
          <Ionicons name="logo-youtube" size={16} color={mode === "youtube" ? "#000" : colors.onSurfaceSecondary} />
          <Text style={[styles.tabText, mode === "youtube" && styles.tabTextActive]}>YOUTUBE LINK</Text>
        </Pressable>
        <Pressable onPress={() => setMode("file")} style={[styles.tab, mode === "file" && styles.tabActive]}>
          <Ionicons name="cloud-upload-outline" size={16} color={mode === "file" ? "#000" : colors.onSurfaceSecondary} />
          <Text style={[styles.tabText, mode === "file" && styles.tabTextActive]}>UPLOAD FILE</Text>
        </Pressable>
      </View>
      {mode === "youtube" ? (
        <View style={{ flexDirection: "row", gap: spacing.sm }}>
          <TextInput
            style={styles.urlInput}
            placeholder="https://www.youtube.com/watch?v=…"
            placeholderTextColor={colors.onSurfaceSecondary}
            value={ytInput}
            onChangeText={setYtInput}
            autoCapitalize="none"
            autoCorrect={false}
            testID="video-yt-input"
          />
          <Pressable onPress={applyYt} style={styles.applyBtn}>
            <Text style={styles.applyText}>USE</Text>
          </Pressable>
        </View>
      ) : (
        <Pressable onPress={pickAndUpload} disabled={busy} style={[styles.pickBtn, busy && { opacity: 0.6 }]} testID="video-pick-btn">
          {busy ? <ActivityIndicator color="#000" /> : (
            <>
              <Ionicons name="cloud-upload-outline" size={18} color="#000" />
              <Text style={styles.pickText}>{value ? "REPLACE VIDEO" : "CHOOSE VIDEO FILE"}</Text>
            </>
          )}
        </Pressable>
      )}
      <Text style={type.caption}>Max 500 MB · mp4 / webm / mov</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: spacing.sm },
  label: { ...type.label, letterSpacing: 1.5, fontSize: 12, color: colors.onSurfaceSecondary },
  preview: { flexDirection: "row", alignItems: "center", gap: spacing.sm, padding: spacing.sm, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border },
  previewText: { flex: 1, color: colors.onSurface, fontSize: 12 },
  tabs: { flexDirection: "row", backgroundColor: colors.surfaceSecondary, borderRadius: radius.pill, padding: 4, gap: 4, borderWidth: 1, borderColor: colors.border },
  tab: { flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, paddingVertical: 8, borderRadius: radius.pill },
  tabActive: { backgroundColor: colors.brandPrimary },
  tabText: { ...type.label, letterSpacing: 1.2, fontSize: 11, color: colors.onSurfaceSecondary },
  tabTextActive: { color: "#000" },
  pickBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, backgroundColor: colors.brandPrimary, height: 44, borderRadius: radius.md },
  pickText: { color: "#000", fontFamily: "BarlowCondensed-Bold", letterSpacing: 1.5, fontSize: 13 },
  urlInput: { flex: 1, backgroundColor: colors.surfaceSecondary, color: colors.onSurface, borderRadius: radius.md, paddingHorizontal: spacing.md, height: 44, borderWidth: 1, borderColor: colors.border },
  applyBtn: { paddingHorizontal: spacing.lg, backgroundColor: colors.brandPrimary, borderRadius: radius.md, alignItems: "center", justifyContent: "center" },
  applyText: { color: "#000", fontFamily: "BarlowCondensed-Bold", letterSpacing: 1.5, fontSize: 12 },
});
