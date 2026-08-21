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
type Program = { id: string; name: string; description?: string; coverImage?: string; order: number };
type Settings = { stationName?: string; stationTagline?: string; frequency?: string; logoUrl?: string };

export default function Home() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user } = useAuth();
  const { nowPlaying, isPlaying, toggle, loading: playerLoading } = usePlayer();
  const [schedule, setSchedule] = useState<Sched[]>([]);
  const [news, setNews] = useState<News[]>([]);
  const [programs, setPrograms] = useState<Program[]>([]);
  const [settings, setSettings] = useState<Settings>({});
  const [refreshing, setRefreshing] = useState(false);

  const load = async () => {
    try {
      const [s, n, p, st] = await Promise.all([
        api<Sched[]>("/radio/schedule"),
        api<News[]>("/news"),
        api<Program[]>("/programs"),
        api<Settings>("/settings"),
      ]);
      setSchedule(s); setNews(n.slice(0, 5)); setPrograms(p); setSettings(st);
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
        {settings.logoUrl ? (
          <Image source={{ uri: settings.logoUrl }} style={styles.logoImg} contentFit="contain" testID="home-logo" />
        ) : (
          <View style={{ flex: 1 }}>
            <Text style={styles.hello}>Muraho{user?.displayName ? `, ${user.displayName}` : ""}</Text>
            <Text style={styles.brand}>{settings.stationName?.toUpperCase() || "B&B KIGALI"} {settings.frequency || "89.7 FM"}</Text>
            <Text style={styles.tagline}>{settings.stationTagline || "#MuriSiporonIgitego"}</Text>
          </View>
        )}
        {user?.role === "admin" && (
          <Pressable onPress={() => router.push("/admin")} style={styles.adminBtn} testID="home-admin">
            <Ionicons name="shield-checkmark" size={16} color={colors.brandPrimary} />
            <Text style={styles.adminBtnText}>ADMIN</Text>
          </Pressable>
        )}
        <Pressable onPress={() => router.push("/(tabs)/profile")} style={styles.avatar} testID="home-avatar">
          <Text style={styles.avatarText}>{(user?.displayName?.[0] || user?.phone?.slice(-2) || "?").toUpperCase()}</Text>
        </Pressable>
      </View>
      {settings.logoUrl && (
        <Text style={styles.taglineOnly}>Muraho{user?.displayName ? `, ${user.displayName}` : ""} · {settings.stationTagline || "#MuriSiporonIgitego"}</Text>
      )}

      {/* Quick Actions row */}
      <View style={styles.quickRow}>
        <Pressable onPress={() => router.push("/live-news")} style={styles.quickBtn} testID="home-live-news">
          <View style={styles.quickIcon}><Ionicons name="tv-outline" size={20} color={colors.brandPrimary} /></View>
          <View>
            <Text style={styles.quickLabel}>LIVE NEWS</Text>
            <Text style={styles.quickSub}>Watch on YouTube</Text>
          </View>
        </Pressable>
        <Pressable onPress={() => router.push("/(tabs)/shows")} style={styles.quickBtn} testID="home-shows">
          <View style={styles.quickIcon}><Ionicons name="play-circle-outline" size={20} color={colors.brandPrimary} /></View>
          <View>
            <Text style={styles.quickLabel}>SHOWS</Text>
            <Text style={styles.quickSub}>VOD & podcasts</Text>
          </View>
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

      {/* Programs */}
      {programs.length > 0 && (
        <View style={styles.section}>
          <View style={styles.sectionHead}>
            <Text style={styles.sectionTitle}>PROGRAMS</Text>
            {user?.role === "admin" && (
              <Pressable onPress={() => router.push("/admin/programs")}>
                <Text style={styles.seeAll}>Manage</Text>
              </Pressable>
            )}
          </View>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ paddingHorizontal: spacing.lg, gap: spacing.md }}>
            {programs.map((p, idx) => (
              <Pressable
                key={p.id}
                onPress={() => router.push({ pathname: "/program/[id]", params: { id: p.id } })}
                style={styles.programCard}
                testID={`program-${p.id}`}
              >
                {p.coverImage && <Image source={{ uri: p.coverImage }} style={StyleSheet.absoluteFill} contentFit="cover" />}
                <LinearGradient colors={["rgba(15,15,19,0.1)", "rgba(15,15,19,0.85)"]} style={StyleSheet.absoluteFill} />
                {idx === 0 && (
                  <View style={styles.programBadge}>
                    <Ionicons name="star" size={9} color={colors.onBrandPrimary} />
                    <Text style={styles.programBadgeText}>MOST POPULAR</Text>
                  </View>
                )}
                <View style={styles.programBottom}>
                  <Text style={styles.programOrder}>#{p.order}</Text>
                  <Text style={styles.programName} numberOfLines={2}>{p.name}</Text>
                </View>
              </Pressable>
            ))}
          </ScrollView>
        </View>
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
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, marginBottom: spacing.md, gap: spacing.sm },
  logoImg: { flex: 1, height: 44, marginRight: spacing.sm },
  taglineOnly: { ...type.caption, paddingHorizontal: spacing.lg, marginBottom: spacing.lg, color: colors.onSurfaceSecondary },
  hello: { ...type.bodyMuted },
  brand: { ...type.displayLg, letterSpacing: 1, fontSize: 22 },
  tagline: { ...type.caption, color: colors.brandPrimary, letterSpacing: 1 },
  adminBtn: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: spacing.sm, paddingVertical: 6, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary },
  adminBtnText: { color: colors.brandPrimary, fontFamily: "BarlowCondensed-Bold", fontSize: 11, letterSpacing: 1 },
  avatar: { width: 44, height: 44, borderRadius: 22, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.brandPrimary },
  avatarText: { color: colors.brandPrimary, fontFamily: "BarlowCondensed-Bold", fontSize: 16 },
  quickRow: { flexDirection: "row", gap: spacing.md, paddingHorizontal: spacing.lg, marginBottom: spacing.xl },
  quickBtn: { flex: 1, flexDirection: "row", alignItems: "center", gap: spacing.sm, padding: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border },
  quickIcon: { width: 36, height: 36, borderRadius: radius.sm, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" },
  quickLabel: { ...type.h2, fontSize: 13, letterSpacing: 1 },
  quickSub: { ...type.caption, marginTop: 2, fontSize: 10 },
  programCard: { width: 160, height: 200, borderRadius: radius.md, overflow: "hidden", backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border },
  programBadge: { position: "absolute", top: spacing.sm, left: spacing.sm, flexDirection: "row", alignItems: "center", gap: 3, backgroundColor: colors.brandPrimary, paddingHorizontal: 6, paddingVertical: 3, borderRadius: radius.sm },
  programBadgeText: { color: colors.onBrandPrimary, fontFamily: "BarlowCondensed-Bold", fontSize: 9, letterSpacing: 1 },
  programBottom: { position: "absolute", left: spacing.md, right: spacing.md, bottom: spacing.md },
  programOrder: { color: colors.brandPrimary, fontFamily: "BarlowCondensed-Bold", fontSize: 12, letterSpacing: 1 },
  programName: { ...type.h1, fontSize: 18, lineHeight: 22, marginTop: 2 },
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
