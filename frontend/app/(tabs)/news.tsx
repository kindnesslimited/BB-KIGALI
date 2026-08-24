import { useEffect, useState } from "react";
import { View, Text, StyleSheet, FlatList, Pressable, RefreshControl, Linking } from "react-native";
import { Image } from "expo-image";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { colors, spacing, type, radius } from "@/src/theme";
import { api } from "@/src/api";
import { formatDistanceToNow } from "date-fns";

type News = {
  id: string;
  title: string;
  excerpt?: string;
  summary?: string;
  body?: string;
  thumbnail?: string;
  coverUrl?: string;
  publishedAt: string;
  sourceName?: string;
  sourceUrl?: string;
  url?: string;
};

export default function NewsTab() {
  const insets = useSafeAreaInsets();
  const [items, setItems] = useState<News[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = async () => { try { setItems(await api<News[]>("/news")); } catch {} };
  useEffect(() => { load(); }, []);
  const onRefresh = async () => { setRefreshing(true); await load(); setRefreshing(false); };

  const openSource = (n: News) => {
    const target = n.sourceUrl || n.url;
    if (!target) return;
    Linking.openURL(target).catch(() => {});
  };

  return (
    <FlatList
      style={{ flex: 1, backgroundColor: colors.surface }}
      contentContainerStyle={{ paddingBottom: 200, maxWidth: 900, width: "100%", alignSelf: "center" }}
      data={items}
      keyExtractor={(i) => i.id}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.brandPrimary} />}
      ListHeaderComponent={
        <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
          <Text style={styles.title}>NEWS</Text>
          <Text style={styles.subtitle}>Latest from BB FM & Kigali</Text>
        </View>
      }
      renderItem={({ item }) => {
        const isOpen = expanded === item.id;
        const img = item.coverUrl || item.thumbnail;
        const shortText = item.excerpt || item.summary || "";
        const longText = item.body || shortText;
        const externalTarget = item.sourceUrl || item.url;
        return (
          <Pressable
            onPress={() => setExpanded(isOpen ? null : item.id)}
            style={styles.card}
            testID={`news-card-${item.id}`}
          >
            {img ? (
              <Image source={{ uri: img }} style={styles.thumb} contentFit="cover" />
            ) : (
              <View style={[styles.thumb, styles.thumbFallback]}>
                <Ionicons name="newspaper-outline" size={22} color={colors.onSurfaceSecondary} />
              </View>
            )}
            <View style={{ flex: 1 }}>
              <Text style={styles.time}>
                {(() => { try { return formatDistanceToNow(new Date(item.publishedAt), { addSuffix: true }); } catch { return ""; } })()}
              </Text>
              <Text style={styles.cardTitle} numberOfLines={isOpen ? undefined : 2}>{item.title}</Text>
              <Text style={styles.cardBody} numberOfLines={isOpen ? undefined : 2}>{isOpen ? longText : shortText}</Text>
              {(item.sourceName || externalTarget) && (
                <Pressable
                  onPress={(e) => { e.stopPropagation(); openSource(item); }}
                  style={styles.sourceRow}
                  testID={`news-source-${item.id}`}
                >
                  <Ionicons name="link-outline" size={12} color={colors.brandPrimary} />
                  <Text style={styles.sourceText} numberOfLines={1}>
                    {item.sourceName ? `Source: ${item.sourceName}` : "Read original"}
                  </Text>
                  {externalTarget ? <Ionicons name="open-outline" size={12} color={colors.brandPrimary} /> : null}
                </Pressable>
              )}
            </View>
          </Pressable>
        );
      }}
      ItemSeparatorComponent={() => <View style={{ height: 1, backgroundColor: colors.divider, marginHorizontal: spacing.lg }} />}
      ListEmptyComponent={<View style={styles.empty}><Text style={styles.emptyText}>No news yet</Text></View>}
    />
  );
}

const styles = StyleSheet.create({
  header: { paddingHorizontal: spacing.lg, paddingBottom: spacing.lg },
  title: { ...type.displayLg, letterSpacing: 1 },
  subtitle: { ...type.bodyMuted },
  card: { flexDirection: "row", gap: spacing.md, padding: spacing.lg, backgroundColor: colors.surface },
  thumb: { width: 96, height: 96, borderRadius: radius.md, backgroundColor: colors.surfaceSecondary },
  thumbFallback: { alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
  time: { ...type.caption, color: colors.brandPrimary, marginBottom: 4, fontSize: 11, letterSpacing: 0.5 },
  cardTitle: { ...type.h2, fontSize: 16, lineHeight: 20 },
  cardBody: { ...type.bodyMuted, marginTop: 4, lineHeight: 20, fontSize: 13 },
  sourceRow: { flexDirection: "row", alignItems: "center", gap: 4, marginTop: 8, alignSelf: "flex-start", paddingVertical: 4, paddingHorizontal: 8, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary },
  sourceText: { color: colors.brandPrimary, fontFamily: "BarlowCondensed-Bold", fontSize: 11, letterSpacing: 0.5, maxWidth: 200 },
  empty: { padding: spacing.xxl, alignItems: "center" },
  emptyText: { ...type.bodyMuted },
});
