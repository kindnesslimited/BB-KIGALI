import { useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, ActivityIndicator, Platform } from "react-native";
import { WebView } from "react-native-webview";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { colors, spacing, type, radius } from "@/src/theme";
import { api } from "@/src/api";
import { Image } from "expo-image";

type Show = { id: string; title: string; category: string; description: string; thumbnail: string; videoUrl: string | null; duration: string; premium: boolean; locked?: boolean };

export default function VideoPlayerScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [show, setShow] = useState<Show | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try { setShow(await api<Show>(`/shows/${id}`, { auth: true })); }
      catch (e: any) { setErr(e.message); }
      finally { setLoading(false); }
    })();
  }, [id]);

  if (loading) {
    return <View style={styles.center} testID="video-loading"><ActivityIndicator color={colors.brandPrimary} /></View>;
  }
  if (err || !show) {
    return (
      <View style={styles.center}>
        <Ionicons name="alert-circle-outline" size={40} color={colors.error} />
        <Text style={type.bodyMuted}>{err || "Show not found"}</Text>
      </View>
    );
  }

  const embedUrl = show.videoUrl ? `${show.videoUrl}${show.videoUrl.includes("?") ? "&" : "?"}autoplay=0&playsinline=1` : null;

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }} testID="video-screen">
      <View style={[styles.topBar, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable onPress={() => router.back()} hitSlop={12} testID="video-back">
          <Ionicons name="chevron-back" size={28} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.topTitle} numberOfLines={1}>{show.title}</Text>
        <View style={{ width: 28 }} />
      </View>

      <View style={styles.player}>
        {show.locked ? (
          <View style={styles.lockedBox} testID="locked-box">
            <Image source={{ uri: show.thumbnail }} style={StyleSheet.absoluteFill} contentFit="cover" blurRadius={12} />
            <View style={styles.lockedInner}>
              <Ionicons name="lock-closed" size={40} color={colors.brandPrimary} />
              <Text style={styles.lockedTitle}>PREMIUM CONTENT</Text>
              <Text style={styles.lockedSub}>Subscribe to unlock this show and more.</Text>
              <Pressable onPress={() => router.push("/paywall")} style={styles.lockedBtn} testID="locked-upgrade">
                <Text style={styles.lockedBtnText}>UPGRADE NOW</Text>
              </Pressable>
            </View>
          </View>
        ) : embedUrl ? (
          Platform.OS === "web" ? (
            <iframe
              src={embedUrl}
              style={{ width: "100%", height: "100%", border: 0 }}
              allow="autoplay; encrypted-media; picture-in-picture"
              allowFullScreen
            />
          ) : (
            <WebView
              source={{ uri: embedUrl }}
              style={{ flex: 1, backgroundColor: "#000" }}
              allowsFullscreenVideo
              javaScriptEnabled
            />
          )
        ) : (
          <View style={styles.lockedBox}>
            <Text style={type.bodyMuted}>Video unavailable</Text>
          </View>
        )}
      </View>

      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 220 }}>
        <View style={styles.metaRow}>
          <Text style={styles.cat}>{show.category.toUpperCase()}</Text>
          {show.premium && (
            <View style={styles.premBadge}>
              <Ionicons name="star" size={11} color={colors.onBrandPrimary} />
              <Text style={styles.premText}>PREMIUM</Text>
            </View>
          )}
          <Text style={styles.dur}>{show.duration}</Text>
        </View>
        <Text style={styles.title}>{show.title}</Text>
        <Text style={styles.desc}>{show.description}</Text>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center", gap: spacing.md },
  topBar: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.lg, gap: spacing.md, paddingBottom: spacing.sm, backgroundColor: colors.surface },
  topTitle: { ...type.h2, flex: 1, textAlign: "center", fontSize: 15 },
  player: { aspectRatio: 16 / 9, backgroundColor: "#000" },
  lockedBox: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.surfaceSecondary, overflow: "hidden" },
  lockedInner: { alignItems: "center", padding: spacing.xl, gap: spacing.sm, backgroundColor: "rgba(15,15,19,0.72)", borderRadius: radius.md },
  lockedTitle: { ...type.h1, color: colors.brandPrimary, letterSpacing: 1, marginTop: spacing.sm },
  lockedSub: { ...type.bodyMuted, textAlign: "center", marginBottom: spacing.md },
  lockedBtn: { backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.xl, paddingVertical: spacing.md, borderRadius: radius.pill },
  lockedBtnText: { ...type.h2, color: colors.onBrandPrimary, letterSpacing: 1.5, fontSize: 14 },
  metaRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginBottom: spacing.sm },
  cat: { ...type.label, color: colors.brandPrimary, letterSpacing: 1.5 },
  premBadge: { flexDirection: "row", alignItems: "center", gap: 3, backgroundColor: colors.brandPrimary, paddingHorizontal: 6, paddingVertical: 3, borderRadius: radius.sm },
  premText: { color: colors.onBrandPrimary, fontFamily: "BarlowCondensed-Bold", fontSize: 9, letterSpacing: 1 },
  dur: { ...type.caption, marginLeft: "auto" },
  title: { ...type.displayLg, fontSize: 24, marginBottom: spacing.md, lineHeight: 28 },
  desc: { ...type.bodyMuted, lineHeight: 22, fontSize: 14 },
});
