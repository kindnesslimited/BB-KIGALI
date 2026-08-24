import { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, ActivityIndicator, Platform } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { WebView } from "react-native-webview";
import { colors, spacing, type, radius } from "@/src/theme";
import { api } from "@/src/api";
import { useAuth } from "@/src/context/auth";

type LiveSession = {
  videoId: string;
  title?: string;
  thumbnail?: string;
  embedUrl: string;
  startedAt?: string;
};

/**
 * In-app YouTube LIVE player. Only reachable by authenticated subscribers —
 * unauthenticated / unpaid users are bounced to /paywall.
 *
 * The playback URL comes from GET /api/live/session (auth + paid required, 402 otherwise).
 * The raw YouTube URL is NEVER exposed to non-subscribers.
 */
export default function LivePlayer() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user } = useAuth();
  const [session, setSession] = useState<LiveSession | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [needsSub, setNeedsSub] = useState(false);

  useEffect(() => {
    if (!user) {
      router.replace("/auth/phone");
      return;
    }
    (async () => {
      try {
        const s = await api<LiveSession>("/live/session", { auth: true });
        setSession(s);
      } catch (e: any) {
        const msg = e?.message || "";
        if (msg.includes("402") || msg.toLowerCase().includes("subscription")) {
          setNeedsSub(true);
        } else if (msg.includes("404") || msg.toLowerCase().includes("no live")) {
          setError("BB Kigali is not live right now. Come back soon!");
        } else {
          setError(msg || "Could not load the live stream.");
        }
      } finally {
        setLoading(false);
      }
    })();
  }, [user]);

  if (loading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color={colors.brandPrimary} />
        <Text style={styles.centeredHint}>Connecting to LIVE…</Text>
      </View>
    );
  }

  if (needsSub) {
    return (
      <View style={[styles.wrap, { paddingTop: insets.top + spacing.md }]}>
        <View style={styles.topBar}>
          <Pressable onPress={() => router.back()} hitSlop={12}><Ionicons name="close" size={26} color={colors.onSurface} /></Pressable>
          <Text style={styles.topTitle}>LIVE</Text>
          <View style={{ width: 26 }} />
        </View>
        <View style={styles.gateBody}>
          <View style={styles.gateIcon}><Ionicons name="lock-closed" size={38} color={colors.brandPrimary} /></View>
          <Text style={styles.gateTitle}>SUBSCRIPTION REQUIRED</Text>
          <Text style={styles.gateSub}>
            LIVE broadcasts on BB Kigali are for our subscribers. Choose a plan to unlock ad-free live radio, live YouTube shows and the full VOD library.
          </Text>
          <Pressable onPress={() => router.replace("/paywall")} style={styles.gateBtn} testID="live-gate-paywall">
            <Ionicons name="star" size={16} color="#000" />
            <Text style={styles.gateBtnText}>CHOOSE A PACKAGE</Text>
          </Pressable>
          <Pressable onPress={() => router.replace("/(tabs)")} style={styles.gateBtnGhost}>
            <Text style={styles.gateBtnGhostText}>BACK TO APP</Text>
          </Pressable>
        </View>
      </View>
    );
  }

  if (error || !session) {
    return (
      <View style={[styles.wrap, { paddingTop: insets.top + spacing.md }]}>
        <View style={styles.topBar}>
          <Pressable onPress={() => router.back()} hitSlop={12}><Ionicons name="close" size={26} color={colors.onSurface} /></Pressable>
          <Text style={styles.topTitle}>LIVE</Text>
          <View style={{ width: 26 }} />
        </View>
        <View style={styles.gateBody}>
          <Ionicons name="radio-outline" size={44} color={colors.onSurfaceSecondary} />
          <Text style={styles.gateTitle}>{error ? "OFF AIR" : "NO LIVE STREAM"}</Text>
          <Text style={styles.gateSub}>{error || "Check back soon."}</Text>
          <Pressable onPress={() => router.replace("/(tabs)")} style={styles.gateBtn}>
            <Text style={styles.gateBtnText}>BACK TO APP</Text>
          </Pressable>
        </View>
      </View>
    );
  }

  return (
    <View style={[styles.wrap, { paddingTop: insets.top }]}>
      <View style={styles.topBar}>
        <Pressable onPress={() => router.back()} hitSlop={12} testID="live-close">
          <Ionicons name="close" size={26} color={colors.onSurface} />
        </Pressable>
        <View style={styles.livePill}>
          <View style={styles.liveDot} />
          <Text style={styles.livePillText}>LIVE</Text>
        </View>
        <View style={{ width: 26 }} />
      </View>
      <View style={styles.playerBox}>
        {Platform.OS === "web" ? (
          <View style={styles.iframeWrap}>
            {/* @ts-ignore — RN Web supports iframes via the React DOM shim */}
            <iframe
              src={session.embedUrl}
              width="100%"
              height="100%"
              frameBorder="0"
              allow="autoplay; encrypted-media; picture-in-picture"
              allowFullScreen
              style={{ border: 0 }}
            />
          </View>
        ) : (
          <WebView
            source={{ uri: session.embedUrl }}
            style={{ flex: 1, backgroundColor: "#000" }}
            allowsFullscreenVideo
            allowsInlineMediaPlayback
            mediaPlaybackRequiresUserAction={false}
            javaScriptEnabled
            domStorageEnabled
          />
        )}
      </View>
      <View style={styles.meta}>
        <Text numberOfLines={2} style={styles.title}>{session.title || "BB Kigali FM — LIVE"}</Text>
        <Text style={styles.sub}>Streaming inside BB FM Kigali · subscribers only</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: "#000" },
  centered: { flex: 1, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center", gap: spacing.md },
  centeredHint: { ...type.bodyMuted },
  topBar: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingVertical: spacing.md },
  topTitle: { ...type.h2, letterSpacing: 2, fontSize: 14 },
  livePill: { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: "#ff0000", paddingHorizontal: spacing.md, paddingVertical: 4, borderRadius: radius.pill },
  liveDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: "#fff" },
  livePillText: { color: "#fff", fontFamily: "BarlowCondensed-Bold", fontSize: 10, letterSpacing: 1.4 },
  playerBox: { width: "100%", aspectRatio: 16 / 9, backgroundColor: "#000" },
  iframeWrap: { flex: 1, backgroundColor: "#000", overflow: "hidden" },
  meta: { padding: spacing.lg, gap: 4 },
  title: { ...type.h1, fontSize: 18, color: "#fff" },
  sub: { ...type.caption, color: "rgba(255,255,255,0.6)" },
  gateBody: { flex: 1, padding: spacing.xl, alignItems: "center", justifyContent: "center", gap: spacing.md, backgroundColor: colors.surface },
  gateIcon: { width: 84, height: 84, borderRadius: 42, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center", borderWidth: 2, borderColor: colors.brandPrimary },
  gateTitle: { ...type.h1, letterSpacing: 1.4, fontSize: 22, textAlign: "center" },
  gateSub: { ...type.bodyMuted, textAlign: "center", lineHeight: 22, fontSize: 14, maxWidth: 340 },
  gateBtn: { flexDirection: "row", alignItems: "center", gap: 8, backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.xxl, paddingVertical: spacing.md, borderRadius: radius.pill, marginTop: spacing.md },
  gateBtnText: { color: "#000", fontFamily: "BarlowCondensed-Bold", letterSpacing: 1.5, fontSize: 15 },
  gateBtnGhost: { paddingHorizontal: spacing.xl, paddingVertical: spacing.sm },
  gateBtnGhostText: { color: colors.onSurfaceSecondary, fontFamily: "BarlowCondensed-Bold", letterSpacing: 1.2, fontSize: 12 },
});
