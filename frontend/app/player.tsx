import { useEffect, useRef } from "react";
import { View, Text, StyleSheet, Pressable, Dimensions } from "react-native";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Animated, { useSharedValue, useAnimatedStyle, withRepeat, withTiming, cancelAnimation } from "react-native-reanimated";
import * as Haptics from "expo-haptics";
import { colors, spacing, type, radius } from "@/src/theme";
import { usePlayer } from "@/src/context/player";

const { height } = Dimensions.get("window");
const BARS = 32;

function Wave({ playing }: { playing: boolean }) {
  return (
    <View style={styles.wave}>
      {Array.from({ length: BARS }).map((_, i) => <Bar key={i} playing={playing} delay={i * 60} />)}
    </View>
  );
}

function Bar({ playing, delay }: { playing: boolean; delay: number }) {
  const v = useSharedValue(0.3);
  useEffect(() => {
    cancelAnimation(v);
    if (playing) {
      v.value = withRepeat(withTiming(1, { duration: 500 + delay }), -1, true);
    } else {
      v.value = withTiming(0.3, { duration: 300 });
    }
  }, [playing, delay]);
  const style = useAnimatedStyle(() => ({ height: 8 + v.value * 44 }));
  return <Animated.View style={[styles.bar, style]} />;
}

export default function PlayerScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { nowPlaying, isPlaying, loading, toggle } = usePlayer();

  const onToggle = () => { Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {}); void toggle(); };

  if (!nowPlaying) return <View style={styles.container} />;

  return (
    <View style={styles.container} testID="full-player">
      <Image source={{ uri: nowPlaying.coverImage }} style={StyleSheet.absoluteFill} contentFit="cover" blurRadius={20} />
      <LinearGradient colors={["rgba(15,15,19,0.2)", "rgba(15,15,19,0.75)", colors.surface]} locations={[0, 0.4, 1]} style={StyleSheet.absoluteFill} />

      <View style={[styles.top, { paddingTop: insets.top + spacing.md }]}>
        <Pressable onPress={() => router.back()} hitSlop={12} testID="player-close">
          <Ionicons name="chevron-down" size={30} color={colors.onSurface} />
        </Pressable>
        <View style={styles.liveBadge}>
          <View style={styles.dot} />
          <Text style={styles.liveText}>LIVE</Text>
        </View>
        <View style={{ width: 30 }} />
      </View>

      <View style={styles.artWrap}>
        <Image source={{ uri: nowPlaying.coverImage }} style={styles.art} contentFit="cover" />
      </View>

      <View style={[styles.info, { paddingBottom: insets.bottom + spacing.xl }]}>
        <Text style={styles.showLabel}>ON AIR</Text>
        <Text style={styles.showTitle} numberOfLines={2}>{nowPlaying.showTitle.toUpperCase()}</Text>
        <Text style={styles.dj}>with {nowPlaying.djName}</Text>
        <Text style={styles.desc} numberOfLines={2}>{nowPlaying.description}</Text>

        <Wave playing={isPlaying} />

        <View style={styles.controls}>
          <View style={{ width: 56 }} />
          <Pressable onPress={onToggle} disabled={loading} style={styles.playBtn} testID="player-toggle">
            <Ionicons name={loading ? "hourglass" : isPlaying ? "pause" : "play"} size={40} color={colors.onBrandPrimary} />
          </Pressable>
          <Pressable style={styles.iconBtn} testID="player-share">
            <Ionicons name="share-outline" size={22} color={colors.onSurface} />
          </Pressable>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  top: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg },
  liveBadge: { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.md, paddingVertical: 6, borderRadius: radius.pill },
  dot: { width: 6, height: 6, borderRadius: 3, backgroundColor: "#fff" },
  liveText: { color: colors.onBrandPrimary, fontFamily: "BarlowCondensed-Bold", fontSize: 11, letterSpacing: 1.5 },
  artWrap: { alignItems: "center", justifyContent: "center", flex: 1, paddingHorizontal: spacing.xl },
  art: { width: "100%", aspectRatio: 1, borderRadius: radius.lg, maxHeight: height * 0.42 },
  info: { paddingHorizontal: spacing.lg, alignItems: "center" },
  showLabel: { ...type.label, color: colors.brandPrimary, letterSpacing: 2, marginBottom: spacing.sm },
  showTitle: { ...type.displayXL, fontSize: 30, textAlign: "center", marginBottom: 4 },
  dj: { ...type.bodyMuted, marginBottom: spacing.sm },
  desc: { ...type.caption, textAlign: "center", marginBottom: spacing.lg, lineHeight: 18 },
  wave: { flexDirection: "row", alignItems: "center", gap: 3, height: 52, marginBottom: spacing.lg, justifyContent: "center" },
  bar: { width: 3, backgroundColor: colors.brandPrimary, borderRadius: 2 },
  controls: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", width: "100%", paddingHorizontal: spacing.xl },
  playBtn: { width: 80, height: 80, borderRadius: 40, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
  iconBtn: { width: 56, height: 56, borderRadius: 28, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
});
