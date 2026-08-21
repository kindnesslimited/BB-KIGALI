import { useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, RefreshControl } from "react-native";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { colors, spacing, type, radius } from "@/src/theme";
import { api } from "@/src/api";
import { useAuth } from "@/src/context/auth";
import { usePlayer } from "@/src/context/player";

type Sched = { id: string; time: string; showTitle: string; djName: string; isLive: boolean };
type News = { id: string; title: string; excerpt: string; thumbnail: string; publishedAt: string };

export default function Home() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user } = useAuth();
  const { nowPlaying, isPlaying, toggle, loading: playerLoading } = usePlayer();
  const [schedule, setSchedule] = useState<Sched[]>([]);
  const [news, setNews] = useState<News[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const load = async () => {
    try {
      const [s, n] = await Promise.all([api<Sched[]>("/radio/schedule"), api<News[]>("/news")]);
      setSchedule(s); setNews(n.slice(0, 5));
    } catch (e) { console.log("home load", e); }
  };
  useEffect(() => { load(); }, []);
  const onRefresh = async () => { setRefreshing(true); await load(); setRefreshing(false); };

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.surface }}
      contentContainerStyle={{ paddingTop: insets.top + spacing.md, paddingBottom: 200 }}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.brandPrimary} />}
      testID="home-screen"
    >
      {/* Header */}
      <View style={styles.header}>
        <View>
          <Text style={styles.hello}>Muraho{user?.displayName ? `, ${user.displayName}` : ""}</Text>
          <Text style={styles.brand}>BB FM KIGALI</Text>
        </View>
        <Pressable onPress={() => router.push("/(tabs)/profile")} style={styles.avatar} testID="home-avatar">
          <Text style={styles.avatarText}>{(user?.displayName?.[0] || user?.phone?.slice(-2) || "?").toUpperCase()}</Text>
        </Pressable>
      </View>

      {/* Live Hero */}
      {nowPlaying && (
        <Pressable onPress={() => router.push("/player")} style={styles.hero} testID="home-live-hero">
          <Image source={{ uri: nowPlaying.coverImage }} style={StyleSheet.absoluteFill} contentFit="cover" />
          <LinearGradient colors={["rgba(15,15,19,0.1)", "rgba(15,15,19,0.5)", colors.surface]} locations={[0, 0.5, 1]} style={StyleSheet.absoluteFill} />
          <View style={styles.heroContent}>
            <View style={styles.liveBadge}>
              <View style={styles.liveDot} />
              <Text style={styles.liveBadgeText}>ON AIR NOW</Text>
            </View>
            <Text style={styles.heroTitle} numberOfLines={2}>{nowPlaying.showTitle.toUpperCase()}</Text>
            <Text style={styles.heroDj}>with {nowPlaying.djName}</Text>
            <Pressable
              onPress={(e) => { e.stopPropagation(); void toggle(); router.push("/player"); }}
              style={styles.heroBtn}
              testID="home-play-live"
            >
              <Ionicons name={playerLoading ? "hourglass" : isPlaying ? "pause" : "play"} size={22} color={colors.onBrandPrimary} />
              <Text style={styles.heroBtnText}>{isPlaying ? "PAUSE" : "WATCH LIVE"}</Text>
            </Pressable>
          </View>
        </Pressable>
      )}

      {/* Schedule */}
      <View style={styles.section}>
        <View style={styles.sectionHead}>
          <Text style={styles.sectionTitle}>TODAY&apos;S SCHEDULE</Text>
        </View>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ paddingHorizontal: spacing.lg, gap: spacing.md }}>
          {schedule.map((s) => (
            <View key={s.id} style={[styles.schedCard, s.isLive && styles.schedCardLive]} testID={`sched-${s.id}`}>
              {s.isLive && (
                <View style={styles.schedLive}>
                  <View style={styles.liveDot} />
                  <Text style={styles.schedLiveText}>LIVE</Text>
                </View>
              )}
              <Text style={styles.schedTime}>{s.time}</Text>
              <Text style={styles.schedTitle} numberOfLines={2}>{s.showTitle}</Text>
              <Text style={styles.schedDj}>{s.djName}</Text>
            </View>
          ))}
        </ScrollView>
      </View>

      {/* Premium teaser */}
      {user?.tier === "free" && (
        <Pressable onPress={() => router.push("/paywall")} style={styles.upsell} testID="home-upsell">
          <View style={{ flex: 1 }}>
            <Text style={styles.upsellLabel}>GO PREMIUM</Text>
            <Text style={styles.upsellTitle}>Unlock every show, ad-free.</Text>
            <Text style={styles.upsellSub}>From 1,000 RWF / month</Text>
          </View>
          <Ionicons name="chevron-forward" size={22} color={colors.brandPrimary} />
        </Pressable>
      )}

      {/* Latest News */}
      <View style={styles.section}>
        <View style={styles.sectionHead}>
          <Text style={styles.sectionTitle}>LATEST NEWS</Text>
          <Pressable onPress={() => router.push("/(tabs)/news")}><Text style={styles.seeAll}>See all</Text></Pressable>
        </View>
        <View style={{ paddingHorizontal: spacing.lg, gap: spacing.md }}>
          {news.map((n) => (
            <Pressable key={n.id} style={styles.newsCard} testID={`news-${n.id}`} onPress={() => router.push("/(tabs)/news")}>
              <Image source={{ uri: n.thumbnail }} style={styles.newsThumb} contentFit="cover" />
              <View style={{ flex: 1 }}>
                <Text numberOfLines={2} style={styles.newsTitle}>{n.title}</Text>
                <Text numberOfLines={2} style={styles.newsExcerpt}>{n.excerpt}</Text>
              </View>
            </Pressable>
          ))}
        </View>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, marginBottom: spacing.lg },
  hello: { ...type.bodyMuted },
  brand: { ...type.displayLg, letterSpacing: 1 },
  avatar: { width: 44, height: 44, borderRadius: 22, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.brandPrimary },
  avatarText: { color: colors.brandPrimary, fontFamily: "BarlowCondensed-Bold", fontSize: 16 },
  hero: { height: 240, marginHorizontal: spacing.lg, borderRadius: radius.lg, overflow: "hidden", marginBottom: spacing.xl },
  heroContent: { position: "absolute", bottom: 0, left: 0, right: 0, padding: spacing.lg },
  liveBadge: { flexDirection: "row", alignItems: "center", gap: 6, alignSelf: "flex-start", backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.md, paddingVertical: 6, borderRadius: radius.pill, marginBottom: spacing.sm },
  liveDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: "#fff" },
  liveBadgeText: { color: colors.onBrandPrimary, fontFamily: "BarlowCondensed-Bold", fontSize: 11, letterSpacing: 1.5 },
  heroTitle: { ...type.displayXL, fontSize: 32, lineHeight: 34 },
  heroDj: { ...type.bodyMuted, marginTop: 2, marginBottom: spacing.md },
  heroBtn: { flexDirection: "row", alignItems: "center", gap: spacing.sm, alignSelf: "flex-start", backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.lg, paddingVertical: spacing.md, borderRadius: radius.pill },
  heroBtnText: { ...type.h2, color: colors.onBrandPrimary, letterSpacing: 1.5, fontSize: 15 },
  section: { marginBottom: spacing.xl },
  sectionHead: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, marginBottom: spacing.md },
  sectionTitle: { ...type.label, letterSpacing: 1.5, color: colors.onSurfaceSecondary, fontSize: 12 },
  seeAll: { color: colors.brandPrimary, fontFamily: "System", fontSize: 13 },
  schedCard: { width: 180, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.md, borderWidth: 1, borderColor: colors.border },
  schedCardLive: { borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary },
  schedLive: { flexDirection: "row", alignItems: "center", gap: 4, marginBottom: spacing.sm },
  schedLiveText: { ...type.label, color: colors.brandPrimary, fontSize: 10 },
  schedTime: { ...type.caption, marginBottom: 4, color: colors.onSurfaceSecondary },
  schedTitle: { ...type.h2, marginBottom: 2 },
  schedDj: { ...type.caption },
  upsell: { flexDirection: "row", alignItems: "center", marginHorizontal: spacing.lg, backgroundColor: colors.brandTertiary, borderRadius: radius.md, padding: spacing.lg, marginBottom: spacing.xl, borderWidth: 1, borderColor: colors.brandPrimary },
  upsellLabel: { ...type.label, color: colors.brandPrimary, letterSpacing: 2 },
  upsellTitle: { ...type.displayMd, marginTop: 4 },
  upsellSub: { ...type.bodyMuted, marginTop: 2, color: colors.onBrandTertiary },
  newsCard: { flexDirection: "row", gap: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.md, borderWidth: 1, borderColor: colors.border },
  newsThumb: { width: 90, height: 70, borderRadius: radius.sm },
  newsTitle: { ...type.h2, fontSize: 14, lineHeight: 18 },
  newsExcerpt: { ...type.caption, marginTop: 4, lineHeight: 16 },
});
