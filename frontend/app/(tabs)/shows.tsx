import { useEffect, useState, useMemo } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, FlatList, Dimensions } from "react-native";
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

const { width } = Dimensions.get("window");
const COL_GAP = spacing.md;
const H_PAD = spacing.lg;
const COL_W = (width - H_PAD * 2 - COL_GAP) / 2;

export default function Shows() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
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
        keyExtractor={(i) => i.id}
        numColumns={2}
        columnWrapperStyle={{ gap: COL_GAP, paddingHorizontal: H_PAD }}
        contentContainerStyle={{ paddingTop: spacing.md, paddingBottom: 200, gap: spacing.md }}
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
                <Text style={styles.cardCat}>{item.category.toUpperCase()}</Text>
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
