import { useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, RefreshControl, Linking, Platform, Alert, useWindowDimensions } from "react-native";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { colors, spacing, type, radius } from "@/src/theme";
import { api } from "@/src/api";
import { useAuth } from "@/src/context/auth";
import { usePlayer } from "@/src/context/player";
import { scheduleReminder, cancelReminder, getReminder } from "@/src/utils/reminders";

type Sched = { id: string; time: string; showTitle: string; djName: string; isLive: boolean; coverImage?: string; status?: string; featured?: boolean; description?: string };
type News = { id: string; title: string; excerpt?: string; summary?: string; thumbnail?: string; coverUrl?: string; publishedAt: string };
type Program = { id: string; name: string; description?: string; coverImage?: string; order: number };
type Settings = { stationName?: string; stationTagline?: string; frequency?: string; logoUrl?: string };
type LiveStatus = { isLive: boolean; videoId?: string; title?: string; thumbnail?: string; watchUrl?: string; embedUrl?: string; channelTitle?: string };

export default function Home() {
  const insets = useSafeAreaInsets();
  const { width: winWidth } = useWindowDimensions();
  const isWideDesktop = Platform.OS === "web" && winWidth >= 1024;
  const router = useRouter();
  const { user } = useAuth();
  const { nowPlaying, isPlaying, toggle, loading: playerLoading, requiresSubscription: radioLocked } = usePlayer();
  const [schedule, setSchedule] = useState<Sched[]>([]);
  const [news, setNews] = useState<News[]>([]);
  const [programs, setPrograms] = useState<Program[]>([]);
  const [settings, setSettings] = useState<Settings>({});
  const [refreshing, setRefreshing] = useState(false);
  const [liveStatus, setLiveStatus] = useState<LiveStatus>({ isLive: false });
  const [reminders, setReminders] = useState<Record<string, boolean>>({});

  const load = async () => {
    try {
      const [s, n, p, st, live] = await Promise.all([
        api<Sched[]>("/radio/schedule"),
        api<News[]>("/news"),
        api<Program[]>("/programs"),
        api<Settings>("/settings"),
        api<LiveStatus>("/live/status").catch(() => ({ isLive: false } as LiveStatus)),
      ]);
      setSchedule(s); setNews(n.slice(0, 5)); setPrograms(p); setSettings(st); setLiveStatus(live);
      // Load which slots already have local reminders scheduled.
      if (Platform.OS !== "web") {
        const active: Record<string, boolean> = {};
        for (const slot of s) { if ((await getReminder(slot.id))) active[slot.id] = true; }
        setReminders(active);
      }
    } catch (e) { console.log("home load", e); }
  };
  useEffect(() => { load(); }, []);
  const onRefresh = async () => { setRefreshing(true); await load(); setRefreshing(false); };

  // Priority sort: LIVE first, then FEATURED, then order.
  const sortedSchedule = [...schedule].sort((a, b) => {
    if (a.isLive && !b.isLive) return -1;
    if (!a.isLive && b.isLive) return 1;
    if (a.featured && !b.featured) return -1;
    if (!a.featured && b.featured) return 1;
    return 0;
  });

  const openYouTubeLive = () => {
    // Keep playback inside the app — subscription-gated /live route
    if (!liveStatus.isLive) return;
    router.push("/live");
  };

  const toggleReminder = async (slot: Sched) => {
    if (Platform.OS === "web") {
      Alert.alert("Reminders", "Reminders work on the mobile app (iOS/Android). Open in the BB FM app to set one.");
      return;
    }
    const already = reminders[slot.id];
    if (already) {
      await cancelReminder(slot.id);
      setReminders({ ...reminders, [slot.id]: false });
      Alert.alert("Reminder cancelled", `You won't be reminded about "${slot.showTitle}".`);
      return;
    }
    const ok = await scheduleReminder(slot);
    if (!ok) {
      Alert.alert("Reminder not set", "Please enable notifications for BB FM Kigali in your device settings, or pick an upcoming (future) slot.");
      return;
    }
    setReminders({ ...reminders, [slot.id]: true });
    Alert.alert("Reminder set", `We'll ping you 15 minutes before "${slot.showTitle}" starts.`);
  };

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.surface }}
      contentContainerStyle={{ paddingTop: isWideDesktop ? spacing.md : insets.top + spacing.md, paddingBottom: 200 }}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.brandPrimary} />}
      testID="home-screen"
    >
      {/* Header — hidden on wide desktop because the DesktopHeader is already shown */}
      {!isWideDesktop && (
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
      )}
      {settings.logoUrl && !isWideDesktop && (
        <Text style={styles.taglineOnly}>Muraho{user?.displayName ? `, ${user.displayName}` : ""} · {settings.stationTagline || "#MuriSiporonIgitego"}</Text>
      )}

      {/* YouTube LIVE detection banner — appears automatically when @bbkigalifm is live */}
      {liveStatus.isLive && (
        <Pressable onPress={openYouTubeLive} style={styles.ytLiveBanner} testID="home-yt-live-banner">
          <Image source={{ uri: liveStatus.thumbnail }} style={StyleSheet.absoluteFill} contentFit="cover" />
          <LinearGradient colors={["rgba(15,15,19,0.05)", "rgba(15,15,19,0.55)", "rgba(15,15,19,0.9)"]} locations={[0, 0.55, 1]} style={StyleSheet.absoluteFill} />
          <View style={styles.ytLiveInner}>
            <View style={styles.ytLivePill}>
              <View style={styles.ytLivePulse} />
              <Text style={styles.ytLivePillText}>LIVE NOW · YOUTUBE</Text>
            </View>
            <Text numberOfLines={2} style={styles.ytLiveTitle}>{liveStatus.title || "BB Kigali FM is LIVE"}</Text>
            <View style={styles.ytLiveBtn}>
              <Ionicons name="play-circle" size={16} color="#fff" />
              <Text style={styles.ytLiveBtnText}>WATCH LIVE IN APP</Text>
            </View>
          </View>
        </Pressable>
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
              onPress={(e) => {
                e.stopPropagation();
                if (!user) { router.push("/auth/phone"); return; }
                if (radioLocked) { router.push("/paywall"); return; }
                void toggle();
                router.push("/player");
              }}
              style={styles.heroBtn}
              testID="home-play-live"
            >
              <Ionicons name={radioLocked ? "lock-closed" : playerLoading ? "hourglass" : isPlaying ? "pause" : "play"} size={22} color={colors.onBrandPrimary} />
              <Text style={styles.heroBtnText}>{radioLocked ? "SUBSCRIBE TO LISTEN" : isPlaying ? "PAUSE" : "LISTEN LIVE"}</Text>
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
          {user?.role === "admin" && (
            <Pressable onPress={() => router.push("/admin/schedule")}>
              <Text style={styles.seeAll}>Manage</Text>
            </Pressable>
          )}
        </View>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ paddingHorizontal: spacing.lg, gap: spacing.md }}>
          {sortedSchedule.length === 0 && (
            <View style={[styles.schedCard, { justifyContent: "center", alignItems: "center", minWidth: 200 }]}>
              <Text style={type.bodyMuted}>No slots scheduled yet.</Text>
            </View>
          )}
          {sortedSchedule.map((s) => {
            const showFeatured = !!s.featured && !s.isLive;
            const hasReminder = !!reminders[s.id];
            return (
              <View key={s.id} style={[styles.schedCard, s.isLive && styles.schedCardLive, showFeatured && styles.schedCardFeatured, s.coverImage && { padding: 0, overflow: "hidden" }]}>
                <Pressable
                  onPress={() => { if (s.isLive) router.push("/player"); }}
                  style={{ flex: 1 }}
                  testID={`sched-${s.id}`}
                >
                  {s.coverImage ? (
                    <>
                      <Image source={{ uri: s.coverImage }} style={StyleSheet.absoluteFill} contentFit="cover" />
                      <LinearGradient colors={["rgba(15,15,19,0.05)", "rgba(15,15,19,0.9)"]} style={StyleSheet.absoluteFill} />
                      <View style={{ padding: spacing.md, flex: 1, justifyContent: "flex-end" }}>
                        {s.isLive && (
                          <View style={styles.schedLive}>
                            <View style={styles.liveDot} />
                            <Text style={styles.schedLiveText}>LIVE NOW</Text>
                          </View>
                        )}
                        {showFeatured && (
                          <View style={styles.featuredPill}>
                            <Ionicons name="star" size={9} color="#000" />
                            <Text style={styles.featuredPillText}>UP NEXT · FEATURED</Text>
                          </View>
                        )}
                        <Text style={[styles.schedTime, { color: "#fff", opacity: 0.85 }]}>{s.time}</Text>
                        <Text style={[styles.schedTitle, { color: "#fff" }]} numberOfLines={2}>{s.showTitle}</Text>
                        {!!s.djName && <Text style={[styles.schedDj, { color: "rgba(255,255,255,0.75)" }]}>{s.djName}</Text>}
                      </View>
                    </>
                  ) : (
                    <View style={{ padding: spacing.md, flex: 1 }}>
                      {s.isLive && (
                        <View style={styles.schedLive}>
                          <View style={styles.liveDot} />
                          <Text style={styles.schedLiveText}>LIVE NOW</Text>
                        </View>
                      )}
                      {showFeatured && (
                        <View style={styles.featuredPill}>
                          <Ionicons name="star" size={9} color="#000" />
                          <Text style={styles.featuredPillText}>UP NEXT · FEATURED</Text>
                        </View>
                      )}
                      <Text style={styles.schedTime}>{s.time}</Text>
                      <Text style={styles.schedTitle} numberOfLines={2}>{s.showTitle}</Text>
                      {!!s.djName && <Text style={styles.schedDj}>{s.djName}</Text>}
                    </View>
                  )}
                </Pressable>
                {!s.isLive && (
                  <Pressable
                    onPress={() => toggleReminder(s)}
                    style={[styles.remindBtn, hasReminder && styles.remindBtnOn]}
                    testID={`sched-remind-${s.id}`}
                  >
                    <Ionicons name={hasReminder ? "notifications" : "notifications-outline"} size={14} color={hasReminder ? "#000" : colors.brandPrimary} />
                    <Text style={[styles.remindBtnText, hasReminder && { color: "#000" }]}>{hasReminder ? "REMINDER ON" : "REMIND ME"}</Text>
                  </Pressable>
                )}
              </View>
            );
          })}
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
              <Image source={{ uri: n.coverUrl || n.thumbnail }} style={styles.newsThumb} contentFit="cover" />
              <View style={{ flex: 1 }}>
                <Text numberOfLines={2} style={styles.newsTitle}>{n.title}</Text>
                <Text numberOfLines={2} style={styles.newsExcerpt}>{n.excerpt || n.summary || ""}</Text>
              </View>
            </Pressable>
          ))}
        </View>
      </View>

      {/* How the app works — guidance + contact */}
      <View style={styles.section}>
        <View style={styles.sectionHead}>
          <Text style={styles.sectionTitle}>HOW OUR APP WORKS</Text>
        </View>
        <View style={styles.guideGrid}>
          <View style={styles.guideCard}>
            <View style={styles.guideIcon}><Ionicons name="radio-outline" size={22} color={colors.brandPrimary} /></View>
            <Text style={styles.guideTitle}>LIVE RADIO</Text>
            <Text style={styles.guideDesc}>Stream BB FM 89.7 anywhere in the world — subscribers only.</Text>
          </View>
          <View style={styles.guideCard}>
            <View style={styles.guideIcon}><Ionicons name="videocam-outline" size={22} color={colors.brandPrimary} /></View>
            <Text style={styles.guideTitle}>WATCH VOD</Text>
            <Text style={styles.guideDesc}>Buy a single show for 1€ / 1,000 RWF, or go Premium.</Text>
          </View>
          <View style={styles.guideCard}>
            <View style={styles.guideIcon}><Ionicons name="star-outline" size={22} color={colors.brandPrimary} /></View>
            <Text style={styles.guideTitle}>GO PREMIUM</Text>
            <Text style={styles.guideDesc}>Unlock every show, ad-free, from 1,000 RWF / month.</Text>
          </View>
          <View style={styles.guideCard}>
            <View style={styles.guideIcon}><Ionicons name="card-outline" size={22} color={colors.brandPrimary} /></View>
            <Text style={styles.guideTitle}>PAY YOUR WAY</Text>
            <Text style={styles.guideDesc}>Card (Stripe), PayPal, or MTN MoMo — pick what suits.</Text>
          </View>
        </View>
      </View>

      {/* Contact card */}
      <View style={styles.section}>
        <View style={styles.sectionHead}>
          <Text style={styles.sectionTitle}>NEED HELP?</Text>
        </View>
        <View style={styles.contactCard}>
          <Text style={styles.contactHeadline}>We&apos;re just a message away.</Text>
          <Text style={styles.contactSub}>Our team replies in Kinyarwanda, English & French, Mon–Sat 9:00–20:00 CAT.</Text>
          <View style={styles.contactRow}>
            <Pressable
              onPress={() => Linking.openURL("https://wa.me/250791446979").catch(() => {})}
              style={[styles.contactBtn, { borderColor: "#25D366" }]}
              testID="home-contact-whatsapp"
            >
              <Ionicons name="logo-whatsapp" size={18} color="#25D366" />
              <Text style={styles.contactBtnText}>WHATSAPP</Text>
            </Pressable>
            <Pressable
              onPress={() => Linking.openURL("tel:+250791446979").catch(() => {})}
              style={styles.contactBtn}
              testID="home-contact-call"
            >
              <Ionicons name="call-outline" size={18} color={colors.brandPrimary} />
              <Text style={styles.contactBtnText}>CALL</Text>
            </Pressable>
            <Pressable
              onPress={() => Linking.openURL("mailto:info@besoft.info?subject=BB%20FM%20Kigali%20Support").catch(() => {})}
              style={styles.contactBtn}
              testID="home-contact-email"
            >
              <Ionicons name="mail-outline" size={18} color={colors.brandPrimary} />
              <Text style={styles.contactBtnText}>EMAIL</Text>
            </Pressable>
          </View>
          <Text style={styles.contactMeta}>+250 791 446 979 · info@besoft.info</Text>
          <Text style={styles.contactMeta}>BB FM Kigali · KG 123 St, Kigali, Rwanda</Text>
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
  schedCard: { width: 200, height: 180, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.md, borderWidth: 1, borderColor: colors.border, overflow: "hidden" },
  schedCardLive: { borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary },
  schedCardFeatured: { borderColor: colors.brandPrimary },
  schedLive: { flexDirection: "row", alignItems: "center", gap: 4, marginBottom: spacing.sm },
  schedLiveText: { ...type.label, color: colors.brandPrimary, fontSize: 10 },
  schedTime: { ...type.caption, marginBottom: 4, color: colors.onSurfaceSecondary },
  schedTitle: { ...type.h2, marginBottom: 2 },
  schedDj: { ...type.caption },
  featuredPill: { flexDirection: "row", alignItems: "center", gap: 3, alignSelf: "flex-start", backgroundColor: colors.brandPrimary, paddingHorizontal: 6, paddingVertical: 2, borderRadius: radius.pill, marginBottom: spacing.sm },
  featuredPillText: { color: "#000", fontFamily: "BarlowCondensed-Bold", fontSize: 9, letterSpacing: 1 },
  remindBtn: { position: "absolute", top: 8, right: 8, flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 8, paddingVertical: 4, borderRadius: radius.pill, backgroundColor: "rgba(0,0,0,0.5)", borderWidth: 1, borderColor: colors.brandPrimary },
  remindBtnOn: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  remindBtnText: { color: colors.brandPrimary, fontFamily: "BarlowCondensed-Bold", fontSize: 9, letterSpacing: 0.8 },
  // YouTube LIVE banner
  ytLiveBanner: { height: 200, marginHorizontal: spacing.lg, borderRadius: radius.lg, overflow: "hidden", marginBottom: spacing.xl, borderWidth: 2, borderColor: "#ff0000", backgroundColor: "#0a0a0a" },
  ytLiveInner: { position: "absolute", left: 0, right: 0, bottom: 0, padding: spacing.lg },
  ytLivePill: { flexDirection: "row", alignItems: "center", gap: 6, alignSelf: "flex-start", backgroundColor: "#ff0000", paddingHorizontal: spacing.md, paddingVertical: 6, borderRadius: radius.pill, marginBottom: spacing.sm },
  ytLivePulse: { width: 8, height: 8, borderRadius: 4, backgroundColor: "#fff" },
  ytLivePillText: { color: "#fff", fontFamily: "BarlowCondensed-Bold", fontSize: 11, letterSpacing: 1.5 },
  ytLiveTitle: { fontFamily: "BarlowCondensed-Bold", fontSize: 22, color: "#fff", lineHeight: 24, marginBottom: spacing.md },
  ytLiveBtn: { flexDirection: "row", alignItems: "center", gap: 8, alignSelf: "flex-start", backgroundColor: "#ff0000", paddingHorizontal: spacing.lg, paddingVertical: 10, borderRadius: radius.pill },
  ytLiveBtnText: { color: "#fff", fontFamily: "BarlowCondensed-Bold", fontSize: 13, letterSpacing: 1.5 },
  upsell: { flexDirection: "row", alignItems: "center", marginHorizontal: spacing.lg, backgroundColor: colors.brandTertiary, borderRadius: radius.md, padding: spacing.lg, marginBottom: spacing.xl, borderWidth: 1, borderColor: colors.brandPrimary },
  upsellLabel: { ...type.label, color: colors.brandPrimary, letterSpacing: 2 },
  upsellTitle: { ...type.displayMd, marginTop: 4 },
  upsellSub: { ...type.bodyMuted, marginTop: 2, color: colors.onBrandTertiary },
  newsCard: { flexDirection: "row", gap: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.md, borderWidth: 1, borderColor: colors.border },
  newsThumb: { width: 90, height: 70, borderRadius: radius.sm },
  newsTitle: { ...type.h2, fontSize: 14, lineHeight: 18 },
  newsExcerpt: { ...type.caption, marginTop: 4, lineHeight: 16 },
  // Guide + Contact
  guideGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md, paddingHorizontal: spacing.lg },
  guideCard: { flexBasis: "47%", flexGrow: 1, minWidth: 140, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: spacing.md, gap: 6 },
  guideIcon: { width: 40, height: 40, borderRadius: radius.sm, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center", marginBottom: 4 },
  guideTitle: { ...type.h2, fontSize: 13, letterSpacing: 1 },
  guideDesc: { ...type.bodyMuted, fontSize: 12, lineHeight: 16 },
  contactCard: { marginHorizontal: spacing.lg, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.lg, borderWidth: 1, borderColor: colors.border, gap: spacing.sm },
  contactHeadline: { ...type.h1, fontSize: 18 },
  contactSub: { ...type.bodyMuted, fontSize: 12, lineHeight: 16 },
  contactRow: { flexDirection: "row", gap: spacing.sm, flexWrap: "wrap", marginTop: spacing.sm },
  contactBtn: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: spacing.md, paddingVertical: 10, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary, flexGrow: 1, justifyContent: "center" },
  contactBtnText: { color: colors.brandPrimary, fontFamily: "BarlowCondensed-Bold", fontSize: 12, letterSpacing: 1 },
  contactMeta: { ...type.caption, fontSize: 11 },
});
