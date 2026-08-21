import { useEffect, useState } from "react";
import { View, Text, StyleSheet, FlatList, Pressable, RefreshControl } from "react-native";
import { Image } from "expo-image";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { colors, spacing, type, radius } from "@/src/theme";
import { api } from "@/src/api";
import { formatDistanceToNow } from "date-fns";

type News = { id: string; title: string; excerpt: string; body: string; thumbnail: string; publishedAt: string };

export default function NewsTab() {
  const insets = useSafeAreaInsets();
  const [items, setItems] = useState<News[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = async () => { try { setItems(await api<News[]>("/news")); } catch {} };
  useEffect(() => { load(); }, []);
  const onRefresh = async () => { setRefreshing(true); await load(); setRefreshing(false); };

  return (
    <FlatList
      style={{ flex: 1, backgroundColor: colors.surface }}
      contentContainerStyle={{ paddingBottom: 200 }}
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
        return (
          <Pressable
            onPress={() => setExpanded(isOpen ? null : item.id)}
            style={styles.card}
            testID={`news-card-${item.id}`}
          >
            <Image source={{ uri: item.thumbnail }} style={styles.thumb} contentFit="cover" />
            <View style={{ flex: 1 }}>
              <Text style={styles.time}>
                {(() => { try { return formatDistanceToNow(new Date(item.publishedAt), { addSuffix: true }); } catch { return ""; } })()}
              </Text>
              <Text style={styles.cardTitle} numberOfLines={isOpen ? undefined : 2}>{item.title}</Text>
              <Text style={styles.cardBody} numberOfLines={isOpen ? undefined : 2}>{isOpen ? item.body : item.excerpt}</Text>
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
  thumb: { width: 96, height: 96, borderRadius: radius.md },
  time: { ...type.caption, color: colors.brandPrimary, marginBottom: 4, fontSize: 11, letterSpacing: 0.5 },
  cardTitle: { ...type.h2, fontSize: 16, lineHeight: 20 },
  cardBody: { ...type.bodyMuted, marginTop: 4, lineHeight: 20, fontSize: 13 },
  empty: { padding: spacing.xxl, alignItems: "center" },
  emptyText: { ...type.bodyMuted },
});
