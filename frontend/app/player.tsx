import { View, Text, StyleSheet, Pressable, Platform } from "react-native";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { WebView } from "react-native-webview";
import { colors, spacing, type, radius } from "@/src/theme";
import { usePlayer } from "@/src/context/player";

export default function PlayerScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { nowPlaying, isPlaying, toggle } = usePlayer();

  if (!nowPlaying) return <View style={styles.container} />;

  const embedUrl = nowPlaying.youtubeEmbedUrl;

  return (
    <View style={styles.container} testID="full-player">
      <View style={[styles.top, { paddingTop: insets.top + spacing.md }]}>
        <Pressable onPress={() => router.back()} hitSlop={12} testID="player-close" style={styles.iconRound}>
          <Ionicons name="chevron-down" size={26} color={colors.onSurface} />
        </Pressable>
        <View style={styles.liveBadge}>
          <View style={styles.dot} />
          <Text style={styles.liveText}>LIVE</Text>
        </View>
        <View style={{ width: 40 }} />
      </View>

      {/* Video area */}
      <View style={styles.videoWrap}>
        {isPlaying && embedUrl ? (
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
              domStorageEnabled
              mediaPlaybackRequiresUserAction={false}
              allowsInlineMediaPlayback
            />
          )
        ) : (
          <Pressable onPress={() => void toggle()} style={styles.poster} testID="player-poster">
            <Image source={{ uri: nowPlaying.coverImage }} style={StyleSheet.absoluteFill} contentFit="cover" />
            <LinearGradient colors={["rgba(0,0,0,0.3)", "rgba(0,0,0,0.7)"]} style={StyleSheet.absoluteFill} />
            <View style={styles.playCircle}>
              <Ionicons name="play" size={40} color={colors.onBrandPrimary} style={{ marginLeft: 4 }} />
            </View>
            <Text style={styles.tapHint}>Tap to watch live</Text>
          </Pressable>
        )}
      </View>

      {/* Info */}
      <View style={[styles.info, { paddingBottom: insets.bottom + spacing.xl }]}>
        <Text style={styles.showLabel}>ON AIR</Text>
        <Text style={styles.showTitle} numberOfLines={2}>{nowPlaying.showTitle.toUpperCase()}</Text>
        <Text style={styles.dj}>{nowPlaying.djName}</Text>
        <Text style={styles.desc}>{nowPlaying.description}</Text>

        <View style={styles.controls}>
          <View style={{ width: 56 }} />
          <Pressable onPress={() => void toggle()} style={styles.playBtn} testID="player-toggle">
            <Ionicons name={isPlaying ? "pause" : "play"} size={36} color={colors.onBrandPrimary} style={{ marginLeft: isPlaying ? 0 : 3 }} />
          </Pressable>
          <Pressable style={styles.iconRound} testID="player-share">
            <Ionicons name="share-outline" size={22} color={colors.onSurface} />
          </Pressable>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  top: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.md, backgroundColor: colors.surface },
  iconRound: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
  liveBadge: { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.md, paddingVertical: 6, borderRadius: radius.pill },
  dot: { width: 6, height: 6, borderRadius: 3, backgroundColor: "#fff" },
  liveText: { color: colors.onBrandPrimary, fontFamily: "BarlowCondensed-Bold", fontSize: 11, letterSpacing: 1.5 },
  videoWrap: { aspectRatio: 16 / 9, backgroundColor: "#000", marginHorizontal: spacing.md, borderRadius: radius.md, overflow: "hidden" },
  poster: { flex: 1, alignItems: "center", justifyContent: "center", gap: spacing.md },
  playCircle: { width: 80, height: 80, borderRadius: 40, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
  tapHint: { color: "#fff", fontFamily: "BarlowCondensed-Bold", fontSize: 14, letterSpacing: 1.5 },
  info: { paddingHorizontal: spacing.lg, alignItems: "center", flex: 1, justifyContent: "center", gap: 6 },
  showLabel: { ...type.label, color: colors.brandPrimary, letterSpacing: 2 },
  showTitle: { ...type.displayXL, fontSize: 28, textAlign: "center" },
  dj: { ...type.bodyMuted },
  desc: { ...type.caption, textAlign: "center", marginBottom: spacing.lg, lineHeight: 18, paddingHorizontal: spacing.md },
  controls: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", width: "100%", marginTop: spacing.md, paddingHorizontal: spacing.xl },
  playBtn: { width: 76, height: 76, borderRadius: 38, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
});
