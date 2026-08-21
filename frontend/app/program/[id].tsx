import { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, Platform, ScrollView } from "react-native";
import { WebView } from "react-native-webview";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { colors, spacing, type, radius } from "@/src/theme";
import { api } from "@/src/api";

type Program = {
  id: string;
  name: string;
  description?: string;
  coverImage?: string;
  youtubeVideoId?: string;
  embedUrl?: string;
};

export default function ProgramView() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [program, setProgram] = useState<Program | null>(null);

  useEffect(() => {
    (async () => {
      const list = await api<Program[]>("/programs");
      setProgram(list.find((p) => p.id === id) || null);
    })().catch(() => {});
  }, [id]);

  if (!program) return <View style={styles.container} />;

  const embedUrl = program.youtubeVideoId
    ? `https://www.youtube.com/embed/${program.youtubeVideoId}?autoplay=0&playsinline=1&rel=0`
    : program.embedUrl;

  return (
    <View style={styles.container} testID="program-screen">
      <View style={[styles.top, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable onPress={() => router.back()} hitSlop={12} testID="program-back" style={styles.iconRound}>
          <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
        </Pressable>
        <Text numberOfLines={1} style={styles.title}>{program.name}</Text>
        <View style={{ width: 40 }} />
      </View>
      <View style={styles.player}>
        {embedUrl ? (
          Platform.OS === "web" ? (
            <iframe src={embedUrl} style={{ width: "100%", height: "100%", border: 0 }} allow="autoplay; encrypted-media" allowFullScreen />
          ) : (
            <WebView source={{ uri: embedUrl }} style={{ flex: 1, backgroundColor: "#000" }} allowsFullscreenVideo allowsInlineMediaPlayback />
          )
        ) : (
          <View style={styles.center}><Text style={type.bodyMuted}>No video linked yet</Text></View>
        )}
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 220 }}>
        <Text style={styles.programName}>{program.name}</Text>
        <Text style={styles.desc}>{program.description || ""}</Text>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  top: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.lg, paddingBottom: spacing.sm, gap: spacing.md, backgroundColor: colors.surface, borderBottomWidth: 1, borderBottomColor: colors.divider },
  iconRound: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
  title: { ...type.h1, flex: 1, textAlign: "center", letterSpacing: 1 },
  player: { aspectRatio: 16 / 9, backgroundColor: "#000" },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  programName: { ...type.displayLg, marginBottom: spacing.md },
  desc: { ...type.bodyMuted, lineHeight: 22 },
});
