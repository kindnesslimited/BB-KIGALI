import { useState } from "react";
import { View, Text, StyleSheet, Pressable, Platform, TextInput, Alert, ActivityIndicator } from "react-native";
import { Image } from "expo-image";
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

export function CoverImagePicker({ value, onChange, label = "Cover image", testID }: Props) {
  const [busy, setBusy] = useState(false);
  const [mode, setMode] = useState<"device" | "url">(value?.startsWith("http") && !value.includes("/api/uploads/") ? "url" : "device");
  const [urlInput, setUrlInput] = useState(value || "");

  const pickAndUpload = async () => {
    try {
      // Ask permission first (iOS)
      if (Platform.OS !== "web") {
        const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
        if (!perm.granted) {
          Alert.alert("Permission needed", "Please allow photo library access to upload a cover image.");
          return;
        }
      }
      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ["images"],
        quality: 0.8,
        allowsEditing: true,
        aspect: [16, 9],
      });
      if (result.canceled || !result.assets?.length) return;
      const asset = result.assets[0];
      setBusy(true);
      const form = new FormData();
      const filename = asset.fileName || `cover-${Date.now()}.jpg`;
      const mimeType = asset.mimeType || "image/jpeg";
      if (Platform.OS === "web") {
        const blob = await (await fetch(asset.uri)).blob();
        form.append("file", blob, filename);
      } else {
        // @ts-ignore native FormData shape
        form.append("file", { uri: asset.uri, name: filename, type: mimeType });
      }
      const token = await getToken();
      const r = await fetch(`${BACKEND_URL}/api/admin/uploads/image`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: form,
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data?.detail || "Upload failed");
      onChange(data.url);
    } catch (e: any) {
      Alert.alert("Upload failed", e?.message || "Please try again");
    } finally {
      setBusy(false);
    }
  };

  const applyUrl = () => {
    const u = urlInput.trim();
    if (!u) return;
    if (!/^https?:\/\//i.test(u)) {
      Alert.alert("Invalid URL", "Image URL must start with http:// or https://");
      return;
    }
    onChange(u);
  };

  return (
    <View style={styles.wrap} testID={testID}>
      <Text style={styles.label}>{label.toUpperCase()}</Text>
      {value ? (
        <View style={styles.preview}>
          <Image source={{ uri: value }} style={styles.previewImg} contentFit="cover" />
          <Pressable onPress={() => onChange("")} style={styles.clear} hitSlop={12}>
            <Ionicons name="close-circle" size={22} color="#fff" />
          </Pressable>
        </View>
      ) : null}

      <View style={styles.tabs}>
        <Pressable onPress={() => setMode("device")} style={[styles.tab, mode === "device" && styles.tabActive]}>
          <Ionicons name="image-outline" size={16} color={mode === "device" ? "#000" : colors.onSurfaceSecondary} />
          <Text style={[styles.tabText, mode === "device" && styles.tabTextActive]}>PICK FROM DEVICE</Text>
        </Pressable>
        <Pressable onPress={() => setMode("url")} style={[styles.tab, mode === "url" && styles.tabActive]}>
          <Ionicons name="link-outline" size={16} color={mode === "url" ? "#000" : colors.onSurfaceSecondary} />
          <Text style={[styles.tabText, mode === "url" && styles.tabTextActive]}>PASTE URL</Text>
        </Pressable>
      </View>

      {mode === "device" ? (
        <Pressable onPress={pickAndUpload} disabled={busy} style={[styles.pickBtn, busy && { opacity: 0.6 }]} testID="cover-pick-btn">
          {busy ? <ActivityIndicator color="#000" /> : (
            <>
              <Ionicons name="cloud-upload-outline" size={18} color="#000" />
              <Text style={styles.pickText}>{value ? "REPLACE IMAGE" : "CHOOSE IMAGE"}</Text>
            </>
          )}
        </Pressable>
      ) : (
        <View style={{ flexDirection: "row", gap: spacing.sm }}>
          <TextInput
            style={styles.urlInput}
            placeholder="https://…"
            placeholderTextColor={colors.onSurfaceSecondary}
            value={urlInput}
            onChangeText={setUrlInput}
            autoCapitalize="none"
            autoCorrect={false}
            testID="cover-url-input"
          />
          <Pressable onPress={applyUrl} style={styles.applyBtn}>
            <Text style={styles.applyText}>USE</Text>
          </Pressable>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: spacing.sm },
  label: { ...type.label, letterSpacing: 1.5, fontSize: 12, color: colors.onSurfaceSecondary },
  preview: { position: "relative", height: 180, borderRadius: radius.md, overflow: "hidden", backgroundColor: colors.surfaceSecondary },
  previewImg: { width: "100%", height: "100%" },
  clear: { position: "absolute", top: 8, right: 8, backgroundColor: "#0007", borderRadius: 20 },
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
