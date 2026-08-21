import { useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, ActivityIndicator, Platform, Modal } from "react-native";
import { WebView, type WebViewNavigation } from "react-native-webview";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { colors, spacing, type, radius } from "@/src/theme";
import { api } from "@/src/api";
import { Image } from "expo-image";
import { useAuth } from "@/src/context/auth";
import * as Haptics from "expo-haptics";

type Show = {
  id: string; title: string; category: string; description: string; thumbnail: string;
  videoUrl: string | null; duration: string; premium: boolean;
  locked?: boolean; unlockPrice?: string; unlockCurrency?: string;
};

export default function VideoPlayerScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user } = useAuth();
  const [show, setShow] = useState<Show | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [payUrl, setPayUrl] = useState<string | null>(null);
  const [orderId, setOrderId] = useState<string | null>(null);
  const [buying, setBuying] = useState(false);

  const loadShow = async () => {
    try {
      const s = await api<Show>(`/shows/${id}`, { auth: true });
      setShow(s);
    } catch (e: any) { setErr(e.message); }
    finally { setLoading(false); }
  };
  useEffect(() => { void loadShow(); }, [id]);

  const buyVod = async () => {
    setBuying(true);
    try {
      const r = await api<{ orderId?: string; approveUrl?: string; alreadyUnlocked?: boolean }>(
        `/billing/vod/${id}/create`,
        { method: "POST", auth: true }
      );
      if (r.alreadyUnlocked) { await loadShow(); return; }
      if (r.approveUrl && r.orderId) { setOrderId(r.orderId); setPayUrl(r.approveUrl); }
    } catch (e: any) { setErr(e.message); }
    finally { setBuying(false); }
  };

  const onPayNav = async (nav: WebViewNavigation) => {
    const url = nav.url || "";
    if (url.includes("/paypal/success")) {
      setPayUrl(null);
      setBuying(true);
      try {
        await api(`/billing/vod/${id}/capture/${orderId}`, { method: "POST", auth: true });
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
        await loadShow();
      } catch (e: any) { setErr(e.message); }
      finally { setBuying(false); }
    } else if (url.includes("/paypal/cancel")) {
      setPayUrl(null);
    }
  };

  if (loading) return <View style={styles.center} testID="video-loading"><ActivityIndicator color={colors.brandPrimary} /></View>;
  if (err || !show) {
    return (
      <View style={styles.center}>
        <Ionicons name="alert-circle-outline" size={40} color={colors.error} />
        <Text style={type.bodyMuted}>{err || "Show not found"}</Text>
      </View>
    );
  }

  const embedUrl = show.videoUrl ? `${show.videoUrl}${show.videoUrl.includes("?") ? "&" : "?"}autoplay=0&playsinline=1` : null;
  const price = show.unlockPrice || "1.00";
  const currency = show.unlockCurrency || "EUR";

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }} testID="video-screen">
      <Modal visible={!!payUrl} animationType="slide" onRequestClose={() => setPayUrl(null)}>
        <View style={{ flex: 1, backgroundColor: "#fff" }}>
          <View style={[styles.topBar, { paddingTop: insets.top + spacing.sm, backgroundColor: "#003087" }]}>
            <Pressable onPress={() => setPayUrl(null)} hitSlop={12} testID="vod-pay-close">
              <Ionicons name="close" size={26} color="#fff" />
            </Pressable>
            <Text style={[styles.topTitle, { color: "#fff" }]}>PAY {price} {currency}</Text>
            <View style={{ width: 26 }} />
          </View>
          {payUrl && (
            Platform.OS === "web" ? (
              <iframe src={payUrl} style={{ flex: 1, width: "100%", height: "100%", border: 0 }} />
            ) : (
              <WebView
                source={{ uri: payUrl }}
                onNavigationStateChange={onPayNav}
                onShouldStartLoadWithRequest={(req) => { onPayNav(req as any); return true; }}
                startInLoadingState
                javaScriptEnabled
                domStorageEnabled
                thirdPartyCookiesEnabled
              />
            )
          )}
        </View>
      </Modal>

      <View style={[styles.topBar, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable onPress={() => router.back()} hitSlop={12} testID="video-back">
          <Ionicons name="chevron-back" size={28} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.topTitle} numberOfLines={1}>{show.title}</Text>
        <View style={{ width: 28 }} />
      </View>

      <View style={styles.player}>
        {show.locked ? (
          <View style={styles.lockedBox} testID="locked-box">
            <Image source={{ uri: show.thumbnail }} style={StyleSheet.absoluteFill} contentFit="cover" blurRadius={12} />
            <View style={styles.lockedInner}>
              <Ionicons name="lock-closed" size={36} color={colors.brandPrimary} />
              <Text style={styles.lockedTitle}>UNLOCK THIS VIDEO</Text>
              <Text style={styles.lockedSub}>Watch this VOD for {price} {currency}, or go Premium to watch all VOD unlimited.</Text>
              <View style={styles.lockedActions}>
                <Pressable onPress={buyVod} disabled={buying} style={[styles.buyBtn, buying && { opacity: 0.6 }]} testID="buy-vod-btn">
                  {buying ? <ActivityIndicator color={colors.onBrandPrimary} /> : (
                    <>
                      <Ionicons name="card" size={16} color={colors.onBrandPrimary} />
                      <Text style={styles.buyBtnText}>PAY {price} {currency}</Text>
                    </>
                  )}
                </Pressable>
                <Pressable onPress={() => router.push("/paywall")} style={styles.premBtn} testID="go-premium-btn">
                  <Ionicons name="star" size={14} color={colors.brandPrimary} />
                  <Text style={styles.premBtnText}>OR GO PREMIUM</Text>
                </Pressable>
              </View>
            </View>
          </View>
        ) : embedUrl ? (
          Platform.OS === "web" ? (
            <iframe
              src={embedUrl}
              style={{ width: "100%", height: "100%", border: 0 }}
              allow="autoplay; encrypted-media; picture-in-picture"
              allowFullScreen
            />
          ) : (
            <WebView
              source={{ uri: embedUrl }}
              style={{ flex: 1, backgroundColor: "#000" }}
              allowsFullscreenVideo
              javaScriptEnabled
            />
          )
        ) : (
          <View style={styles.lockedBox}><Text style={type.bodyMuted}>Video unavailable</Text></View>
        )}
      </View>

      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 220 }}>
        <View style={styles.metaRow}>
          <Text style={styles.cat}>{show.category.toUpperCase()}</Text>
          {show.premium && (
            <View style={styles.premBadge}>
              <Ionicons name="star" size={11} color={colors.onBrandPrimary} />
              <Text style={styles.premText}>PREMIUM</Text>
            </View>
          )}
          {user?.tier === "premium" && !show.locked && (
            <View style={[styles.premBadge, { backgroundColor: colors.success }]}>
              <Ionicons name="checkmark-circle" size={11} color="#fff" />
              <Text style={[styles.premText, { color: "#fff" }]}>UNLOCKED</Text>
            </View>
          )}
          <Text style={styles.dur}>{show.duration}</Text>
        </View>
        <Text style={styles.title}>{show.title}</Text>
        <Text style={styles.desc}>{show.description}</Text>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center", gap: spacing.md },
  topBar: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.lg, gap: spacing.md, paddingBottom: spacing.sm, backgroundColor: colors.surface },
  topTitle: { ...type.h2, flex: 1, textAlign: "center", fontSize: 15 },
  player: { aspectRatio: 16 / 9, backgroundColor: "#000" },
  lockedBox: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.surfaceSecondary, overflow: "hidden" },
  lockedInner: { alignItems: "center", padding: spacing.xl, gap: spacing.sm, backgroundColor: "rgba(15,15,19,0.78)", borderRadius: radius.md, maxWidth: "94%" },
  lockedTitle: { ...type.h1, color: colors.brandPrimary, letterSpacing: 1, marginTop: spacing.sm },
  lockedSub: { ...type.bodyMuted, textAlign: "center", marginBottom: spacing.md, fontSize: 13 },
  lockedActions: { flexDirection: "row", gap: spacing.sm, alignItems: "center" },
  buyBtn: { flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.lg, paddingVertical: 12, borderRadius: radius.pill },
  buyBtnText: { ...type.h2, color: colors.onBrandPrimary, letterSpacing: 1.5, fontSize: 13 },
  premBtn: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: spacing.md, paddingVertical: 12, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.brandPrimary },
  premBtnText: { color: colors.brandPrimary, fontFamily: "BarlowCondensed-Bold", fontSize: 12, letterSpacing: 1 },
  metaRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginBottom: spacing.sm, flexWrap: "wrap" },
  cat: { ...type.label, color: colors.brandPrimary, letterSpacing: 1.5 },
  premBadge: { flexDirection: "row", alignItems: "center", gap: 3, backgroundColor: colors.brandPrimary, paddingHorizontal: 6, paddingVertical: 3, borderRadius: radius.sm },
  premText: { color: colors.onBrandPrimary, fontFamily: "BarlowCondensed-Bold", fontSize: 9, letterSpacing: 1 },
  dur: { ...type.caption, marginLeft: "auto" },
  title: { ...type.displayLg, fontSize: 24, marginBottom: spacing.md, lineHeight: 28 },
  desc: { ...type.bodyMuted, lineHeight: 22, fontSize: 14 },
});
