import { View, Text, StyleSheet, ScrollView, Pressable, Platform } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter, Stack } from "expo-router";
import { colors, spacing, type, radius } from "@/src/theme";
import { useAuth } from "@/src/context/auth";

const CARDS: { key: string; label: string; sub: string; icon: any; route: any }[] = [
  { key: "settings", label: "Live URLs & Branding", sub: "Radio stream, live YouTube URL, station name",
    icon: "settings-outline", route: "/admin/settings" },
  { key: "programs", label: "Programs", sub: "BBSPORTSTALK, B&B SPORTS BAR, IMPUMEKOYIWACU",
    icon: "list-outline", route: "/admin/programs" },
  { key: "shows", label: "VOD & Podcasts", sub: "Add YouTube videos to the library",
    icon: "videocam-outline", route: "/admin/shows" },
];

export default function AdminHome() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user } = useAuth();

  if (!user) return null;
  if (user.role !== "admin") {
    return (
      <View style={styles.deny} testID="admin-deny">
        <Ionicons name="lock-closed" size={40} color={colors.error} />
        <Text style={styles.denyTitle}>ADMIN ONLY</Text>
        <Text style={styles.denySub}>Sign in with an admin phone number to access this area.</Text>
        <Pressable onPress={() => router.back()} style={styles.denyBtn}>
          <Text style={styles.denyBtnText}>GO BACK</Text>
        </Pressable>
      </View>
    );
  }

  return (
    <>
      <Stack.Screen options={{ headerShown: false }} />
      <ScrollView
        style={{ flex: 1, backgroundColor: colors.surface }}
        contentContainerStyle={{ paddingTop: insets.top + spacing.md, paddingBottom: 200 }}
        testID="admin-home"
      >
        <View style={styles.header}>
          <Pressable onPress={() => router.back()} hitSlop={12} testID="admin-back" style={styles.iconRound}>
            <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
          </Pressable>
          <View style={{ flex: 1, marginLeft: spacing.md }}>
            <Text style={styles.brand}>ADMIN CONSOLE</Text>
            <Text style={styles.sub}>B&B Kigali 89.7 FM</Text>
          </View>
        </View>

        <View style={{ paddingHorizontal: spacing.lg, gap: spacing.md, marginTop: spacing.lg }}>
          {CARDS.map((c) => (
            <Pressable key={c.key} onPress={() => router.push(c.route)} style={styles.card} testID={`admin-card-${c.key}`}>
              <View style={styles.cardIcon}>
                <Ionicons name={c.icon} size={22} color={colors.brandPrimary} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.cardLabel}>{c.label}</Text>
                <Text style={styles.cardSub}>{c.sub}</Text>
              </View>
              <Ionicons name="chevron-forward" size={22} color={colors.onSurfaceSecondary} />
            </Pressable>
          ))}
        </View>

        {Platform.OS === "web" && (
          <View style={styles.webNote}>
            <Ionicons name="desktop-outline" size={16} color={colors.brandPrimary} />
            <Text style={styles.webNoteText}>You&apos;re on the web admin. Any changes here reflect immediately on all listener apps.</Text>
          </View>
        )}
      </ScrollView>
    </>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.lg },
  iconRound: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
  brand: { ...type.displayLg, letterSpacing: 1.5 },
  sub: { ...type.bodyMuted, marginTop: 2 },
  card: { flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.lg, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border },
  cardIcon: { width: 44, height: 44, borderRadius: radius.sm, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" },
  cardLabel: { ...type.h2, fontSize: 16 },
  cardSub: { ...type.caption, marginTop: 3 },
  webNote: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginHorizontal: spacing.lg, marginTop: spacing.xl, backgroundColor: colors.brandTertiary, borderRadius: radius.md, padding: spacing.md, borderWidth: 1, borderColor: colors.brandPrimary },
  webNoteText: { ...type.caption, flex: 1, color: colors.onBrandTertiary },
  deny: { flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.xl, gap: spacing.md, backgroundColor: colors.surface },
  denyTitle: { ...type.displayLg, color: colors.error, letterSpacing: 1.5 },
  denySub: { ...type.bodyMuted, textAlign: "center" },
  denyBtn: { backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.xl, paddingVertical: spacing.md, borderRadius: radius.pill, marginTop: spacing.md },
  denyBtnText: { ...type.h2, color: colors.onBrandPrimary, letterSpacing: 1.5 },
});
