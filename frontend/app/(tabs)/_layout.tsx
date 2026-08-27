import React from "react";
import { Tabs } from "expo-router";
import { View, Text, StyleSheet, Pressable, Platform, useWindowDimensions } from "react-native";
import { BlurView } from "expo-blur";
import { Image } from "expo-image";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { colors, spacing, type, radius } from "@/src/theme";
import { usePlayer } from "@/src/context/player";

function MiniPlayer() {
  const { nowPlaying, isPlaying, loading, toggle, requiresSubscription } = usePlayer();
  const router = useRouter();
  if (!nowPlaying) return null;

  const onPressCard = () => {
    if (requiresSubscription) { router.push("/paywall"); return; }
    router.push("/player");
  };
  const onPressBtn = (e: any) => {
    e.stopPropagation();
    if (requiresSubscription) { router.push("/paywall"); return; }
    void toggle();
    router.push("/player");
  };
  const iconName = requiresSubscription ? "lock-closed" : loading ? "hourglass" : isPlaying ? "pause" : "play";

  return (
    <Pressable onPress={onPressCard} testID="mini-player" style={styles.mp}>
      <BlurView intensity={Platform.OS === "android" ? 90 : 60} tint="dark" style={StyleSheet.absoluteFill} />
      <View style={styles.mpInner}>
        <Image source={{ uri: nowPlaying.coverImage }} style={styles.mpArt} contentFit="cover" />
        <View style={{ flex: 1, marginHorizontal: spacing.md }}>
          <View style={styles.liveRow}>
            <View style={styles.liveDot} />
            <Text style={styles.liveText}>{requiresSubscription ? "PREMIUM · LIVE" : "LIVE"}</Text>
          </View>
          <Text numberOfLines={1} style={styles.mpTitle}>{nowPlaying.showTitle}</Text>
          <Text numberOfLines={1} style={styles.mpDj}>{requiresSubscription ? "Subscribe to listen live" : nowPlaying.djName}</Text>
        </View>
        <Pressable onPress={onPressBtn} hitSlop={10} testID="mini-player-toggle" style={styles.mpBtn}>
          <Ionicons name={iconName as any} size={22} color={colors.onBrandPrimary} />
        </Pressable>
      </View>
    </Pressable>
  );
}

export default function TabsLayout() {
  const insets = useSafeAreaInsets();
  const { width } = useWindowDimensions();
  const isWeb = Platform.OS === "web";
  const isWideDesktop = isWeb && width >= 1024;
  const barHeight = 64 + insets.bottom;

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface, alignItems: isWeb ? "center" : "stretch" }}>
      <View style={{ flex: 1, width: "100%", maxWidth: isWeb ? 1200 : undefined, alignSelf: "center" }}>
      <Tabs
        screenOptions={{
          headerShown: false,
          // Hide the mobile bottom tab bar on wide desktop — the DesktopHeader
          // provides top navigation instead.
          tabBarStyle: isWideDesktop ? { display: "none" } : {
            position: "absolute",
            backgroundColor: colors.surface,
            borderTopColor: colors.border,
            borderTopWidth: 1,
            height: barHeight,
            paddingTop: spacing.sm,
            paddingBottom: insets.bottom,
          },
          tabBarActiveTintColor: colors.brandPrimary,
          tabBarInactiveTintColor: colors.onSurfaceSecondary,
          tabBarLabelStyle: { fontSize: 11, fontFamily: "System", marginTop: 2 },
        }}
      >
        <Tabs.Screen name="index" options={{
          title: "Home",
          tabBarIcon: ({ color, size }) => <Ionicons name="radio" size={size} color={color} />,
          tabBarButtonTestID: "tab-home",
        }} />
        <Tabs.Screen name="shows" options={{
          title: "Shows",
          tabBarIcon: ({ color, size }) => <Ionicons name="play-circle-outline" size={size} color={color} />,
          tabBarButtonTestID: "tab-shows",
        }} />
        <Tabs.Screen name="news" options={{
          title: "News",
          tabBarIcon: ({ color, size }) => <Ionicons name="newspaper-outline" size={size} color={color} />,
          tabBarButtonTestID: "tab-news",
        }} />
        <Tabs.Screen name="profile" options={{
          title: "Profile",
          tabBarIcon: ({ color, size }) => <Ionicons name="person-outline" size={size} color={color} />,
          tabBarButtonTestID: "tab-profile",
        }} />
      </Tabs>
      <View pointerEvents="box-none" style={[styles.mpWrap, { bottom: barHeight + spacing.xs }]}>
        <MiniPlayer />
      </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  mpWrap: { position: "absolute", left: spacing.md, right: spacing.md },
  mp: { height: 64, borderRadius: radius.md, overflow: "hidden", borderWidth: 1, borderColor: colors.border, backgroundColor: "rgba(28,28,33,0.7)" },
  mpInner: { flex: 1, flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.sm },
  mpArt: { width: 48, height: 48, borderRadius: radius.sm },
  liveRow: { flexDirection: "row", alignItems: "center", gap: 4, marginBottom: 2 },
  liveDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: colors.brandPrimary },
  liveText: { fontSize: 9, color: colors.brandPrimary, fontFamily: "BarlowCondensed-Bold", letterSpacing: 1.2 },
  mpTitle: { ...type.h2, fontSize: 15 },
  mpDj: { ...type.caption, fontSize: 11 },
  mpBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
});
