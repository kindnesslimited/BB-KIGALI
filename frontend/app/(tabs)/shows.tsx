import { useEffect, useState, useMemo } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, FlatList, useWindowDimensions } from "react-native";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import * as Haptics from "expo-haptics";
import { colors, spacing, type, radius } from "@/src/theme";
import { api } from "@/src/api";

type Show = { id: string; title: string; category: string; description: string; thumbnail: string; duration: string; premium: boolean };
type Category = { id: string; name: string; slug: string; order: number; isActive: boolean };

const COL_GAP = spacing.md;
const H_PAD = spacing.lg;

export default function Shows() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { width: winW } = useWindowDimensions();
  // Responsive: 2 cols on phone, 3 on tablet, 4 on ~1024, 5 on desktop >=1400
  const numColumns = winW >= 1400 ? 5 : winW >= 1024 ? 4 : winW >= 720 ? 3 : 2;
  const contentMaxWidth = Math.min(winW, 1400);
  const COL_W = (contentMaxWidth - H_PAD * 2 - COL_GAP * (numColumns - 1)) / numColumns;
  const [items, setItems] = useState<Show[]>([]);
  const [cats, setCats] = useState<Category[]>([]);
  const [cat, setCat] = useState<string>("all");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const [showsRes, catsRes] = await Promise.all([
          api<Show[]>("/shows"),
          api<Category[]>("/categories"),
        ]);
        setItems(showsRes);
        setCats(catsRes);
      } catch {}
      setLoading(false);
    })();
  }, []);

  const chips = useMemo(
    () => [{ key: "all", label: "All" }, ...cats.map(c => ({ key: c.slug, label: c.name }))],
    [cats]
  );

  const filtered = useMemo(() => cat === "all" ? items : items.filter(i => i.category === cat), [items, cat]);
  const sportsBar = useMemo(() => items.filter(i => i.category === "bbsportsbar-youtube").slice(0, 10), [items]);
  const showFeatured = cat === "all" && sportsBar.length > 0;

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }} testID="shows-screen">
      {/* Sticky header */}
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Text style={styles.title}>SHOWS</Text>
        <Text style={styles.subtitle}>On-demand videos & podcasts</Text>
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={styles.chipRow}
          style={styles.chipScroll}
        >
          {chips.map((c) => {
            const active = cat === c.key;
            return (
              <Pressable
                key={c.key}
                onPress={() => { Haptics.selectionAsync().catch(() => {}); setCat(c.key); }}
                style={[styles.chip, active && styles.chipActive]}
                testID={`chip-${c.key}`}
              >
                <Text style={[styles.chipText, active && styles.chipTextActive]}>{c.label}</Text>
              </Pressable>
            );
          })}
        </ScrollView>
      </View>

      <FlatList
        data={filtered}
        key={`grid-${numColumns}`}
        keyExtractor={(i) => i.id}
        numColumns={numColumns}
        columnWrapperStyle={{ gap: COL_GAP, paddingHorizontal: H_PAD, ...(numColumns > 2 ? { maxWidth: contentMaxWidth, alignSelf: "center", width: "100%" } as any : {}) }}
        contentContainerStyle={{ paddingTop: spacing.md, paddingBottom: 200, gap: spacing.md, ...(winW > 720 ? { maxWidth: contentMaxWidth, alignSelf: "center", width: "100%" } as any : {}) }}
        ListHeaderComponent={
          showFeatured ? (
            <View style={styles.featuredWrap}>
              <View style={styles.featuredHeader}>
                <View style={styles.liveDot} />
                <Text style={styles.featuredTitle}>LIVE @ B&B SPORTS BAR</Text>
                <Pressable onPress={(e: any) => { e?.stopPropagation?.(); setCat("bbsportsbar-youtube"); }} hitSlop={8} testID="featured-see-all">
                  <Text style={styles.featuredMore}>SEE ALL →</Text>
                </Pressable>
              </View>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.md, paddingHorizontal: H_PAD }}>
                {sportsBar.map((s) => (
                  <Pressable
                    key={s.id}
                    style={styles.featuredCard}
                    onPress={() => router.push({ pathname: "/video/[id]", params: { id: s.id } })}
                    testID={`featured-sports-${s.id}`}
                  >
                    <Image source={{ uri: s.thumbnail }} style={StyleSheet.absoluteFill} contentFit="cover" />
                    <LinearGradient colors={["transparent", "rgba(15,15,19,0.95)"]} locations={[0.35, 1]} style={StyleSheet.absoluteFill} />
                    <View style={styles.featuredPill}><Text style={styles.featuredPillText}>SPORTS BAR</Text></View>
                    <View style={styles.featuredBottom}>
                      <Text style={styles.featuredCardTitle} numberOfLines={2}>{s.title}</Text>
                      <Text style={styles.featuredCardMeta}>{s.duration}</Text>
                    </View>
                  </Pressable>
                ))}
              </ScrollView>
            </View>
          ) : null
        }
        ListEmptyComponent={
          <View style={styles.empty}>
            <Ionicons name="tv-outline" size={40} color={colors.onSurfaceSecondary} />
            <Text style={styles.emptyText}>{loading ? "Loading shows..." : "No shows available in this category."}</Text>
          </View>
        }
        renderItem={({ item }) => (
          <Pressable
            style={{ width: COL_W }}
            onPress={() => router.push({ pathname: "/video/[id]", params: { id: item.id } })}
            testID={`show-${item.id}`}
          >
            <View style={styles.card}>
              <Image source={{ uri: item.thumbnail }} style={StyleSheet.absoluteFill} contentFit="cover" />
              <LinearGradient colors={["transparent", "rgba(15,15,19,0.85)"]} locations={[0.4, 1]} style={StyleSheet.absoluteFill} />
              {item.premium && (
                <View style={styles.premBadge}>
                  <Ionicons name="star" size={10} color={colors.onBrandPrimary} />
                  <Text style={styles.premBadgeText}>PREMIUM</Text>
                </View>
              )}
              <View style={styles.dur}>
                <Text style={styles.durText}>{item.duration}</Text>
              </View>
              <View style={styles.cardBottom}>
                <Text numberOfLines={2} style={styles.cardTitle}>{item.title}</Text>
                <Text style={styles.cardCat}>{(item.category || "SHOW").toUpperCase()}</Text>
              </View>
            </View>
          </Pressable>
        )}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  header: { paddingHorizontal: spacing.lg, paddingBottom: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border, backgroundColor: colors.surface },
  title: { ...type.displayLg, letterSpacing: 1 },
  subtitle: { ...type.bodyMuted, marginBottom: spacing.md },
  chipScroll: { marginHorizontal: -spacing.lg, height: 44 },
  chipRow: { paddingHorizontal: spacing.lg, gap: spacing.sm, alignItems: "center" },
  chip: { height: 36, flexShrink: 0, paddingHorizontal: spacing.lg, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center" },
  chipActive: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  chipText: { color: colors.onSurfaceSecondary, fontSize: 13, fontFamily: "System" },
  chipTextActive: { color: colors.onBrandPrimary, fontFamily: "BarlowCondensed-Bold", letterSpacing: 1 },
  card: { aspectRatio: 3 / 4, borderRadius: radius.md, overflow: "hidden", backgroundColor: colors.surfaceSecondary },
  featuredWrap: { marginBottom: spacing.md },
  featuredHeader: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingHorizontal: H_PAD, marginBottom: spacing.sm },
  liveDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: "#ef4444" },
  featuredTitle: { flex: 1, fontFamily: "BarlowCondensed-Bold", letterSpacing: 1.5, fontSize: 14, color: colors.onSurface },
  featuredMore: { color: colors.brandPrimary, fontFamily: "BarlowCondensed-Bold", letterSpacing: 1.2, fontSize: 11 },
  featuredCard: { width: 260, height: 150, borderRadius: radius.md, overflow: "hidden", backgroundColor: colors.surfaceSecondary },
  featuredPill: { position: "absolute", top: 8, left: 8, backgroundColor: "#ef4444", paddingHorizontal: 8, paddingVertical: 3, borderRadius: radius.sm },
  featuredPillText: { color: "#fff", fontFamily: "BarlowCondensed-Bold", letterSpacing: 1.2, fontSize: 10 },
  featuredBottom: { position: "absolute", left: 10, right: 10, bottom: 10 },
  featuredCardTitle: { color: "#fff", fontFamily: "BarlowCondensed-Bold", fontSize: 14, lineHeight: 18 },
  featuredCardMeta: { color: colors.onSurfaceSecondary, fontSize: 11, marginTop: 2 },
  premBadge: { position: "absolute", top: spacing.sm, left: spacing.sm, flexDirection: "row", alignItems: "center", gap: 3, backgroundColor: colors.brandPrimary, paddingHorizontal: 6, paddingVertical: 3, borderRadius: radius.sm },
  premBadgeText: { color: colors.onBrandPrimary, fontFamily: "BarlowCondensed-Bold", fontSize: 9, letterSpacing: 1 },
  dur: { position: "absolute", top: spacing.sm, right: spacing.sm, backgroundColor: "rgba(0,0,0,0.6)", paddingHorizontal: 6, paddingVertical: 3, borderRadius: radius.sm },
  durText: { color: "#fff", fontSize: 10, fontFamily: "System" },
  cardBottom: { position: "absolute", left: spacing.sm, right: spacing.sm, bottom: spacing.sm },
  cardTitle: { ...type.h2, fontSize: 14, lineHeight: 18 },
  cardCat: { ...type.label, color: colors.brandPrimary, fontSize: 9, marginTop: 2 },
  empty: { alignItems: "center", padding: spacing.xxl, gap: spacing.md },
  emptyText: { ...type.bodyMuted },
});
