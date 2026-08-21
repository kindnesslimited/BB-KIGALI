import { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, Platform } from "react-native";
import { WebView } from "react-native-webview";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { colors, spacing, type } from "@/src/theme";
import { api } from "@/src/api";

export default function LiveNews() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [embedUrl, setEmbedUrl] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      const s = await api<{ youtubeEmbedUrl?: string; youtubeWatchUrl?: string; youtubeVideoId?: string }>("/radio/now-playing");
      setEmbedUrl(s.youtubeEmbedUrl || (s.youtubeVideoId ? `https://www.youtube.com/embed/${s.youtubeVideoId}?autoplay=1&playsinline=1&rel=0` : null));
    })().catch(() => {});
  }, []);

  return (
    <View style={{ flex: 1, backgroundColor: "#000" }} testID="live-news-screen">
      <View style={[styles.top, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable onPress={() => router.back()} hitSlop={12} testID="live-news-close" style={styles.iconRound}>
          <Ionicons name="close" size={22} color="#fff" />
        </Pressable>
        <Text style={styles.title}>LIVE NEWS</Text>
        <View style={{ width: 40 }} />
      </View>
      <View style={{ flex: 1 }}>
        {embedUrl ? (
          Platform.OS === "web" ? (
            <iframe src={embedUrl} style={{ flex: 1, width: "100%", height: "100%", border: 0 }} allow="autoplay; encrypted-media" allowFullScreen />
          ) : (
            <WebView source={{ uri: embedUrl }} style={{ flex: 1, backgroundColor: "#000" }} allowsFullscreenVideo allowsInlineMediaPlayback mediaPlaybackRequiresUserAction={false} />
          )
        ) : (
          <View style={styles.center}><Text style={{ color: "#fff" }}>Loading…</Text></View>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  top: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.lg, paddingBottom: spacing.sm, backgroundColor: "#000" },
  iconRound: { width: 40, height: 40, borderRadius: 20, backgroundColor: "rgba(255,255,255,0.1)", alignItems: "center", justifyContent: "center" },
  title: { ...type.h1, flex: 1, textAlign: "center", color: "#fff", letterSpacing: 1.5 },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
});
