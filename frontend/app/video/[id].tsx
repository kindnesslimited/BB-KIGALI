import { useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, ActivityIndicator, Platform, Modal, TextInput, KeyboardAvoidingView } from "react-native";
import { WebView, type WebViewNavigation } from "react-native-webview";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { colors, spacing, type, radius } from "@/src/theme";
import { api } from "@/src/api";
import { Image } from "expo-image";
import { useAuth } from "@/src/context/auth";
import * as Haptics from "expo-haptics";
import { useScreenshotDetected } from "@/src/hooks/use-screen-capture-guard";

type Show = {
  id: string; title: string; category: string; description: string; thumbnail: string;
  videoUrl: string | null; duration: string; premium: boolean;
  locked?: boolean; unlockPrice?: string; unlockCurrency?: string; unlockPriceRwf?: string;
};

export default function VideoPlayerScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user } = useAuth();
  const screenshotCount = useScreenshotDetected();
  const [showWarning, setShowWarning] = useState(false);

  useEffect(() => {
    if (screenshotCount === 0) return;
    setShowWarning(true);
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning).catch(() => {});
    const t = setTimeout(() => setShowWarning(false), 4000);
    return () => clearTimeout(t);
  }, [screenshotCount]);
  const [show, setShow] = useState<Show | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [payUrl, setPayUrl] = useState<string | null>(null);
  const [payProvider, setPayProvider] = useState<"paypal" | "stripe">("paypal");
  const [orderId, setOrderId] = useState<string | null>(null);
  const [stripeSessionId, setStripeSessionId] = useState<string | null>(null);
  const [buying, setBuying] = useState(false);
  // Blank prefix so admins never accidentally pay themselves — customer must enter their own MoMo.
  const [momoPhone, setMomoPhone] = useState<string>("+250 ");
  const [showMomo, setShowMomo] = useState(false);
  const [momoStatus, setMomoStatus] = useState<string | null>(null);
  const [suggestStripe, setSuggestStripe] = useState(false);
  const [checkoutOpen, setCheckoutOpen] = useState(false);
  const isIOS = Platform.OS === "ios";

  const loadShow = async () => {
    try {
      // `auth: true` sends the token if we have one, but the backend accepts guest requests too now.
      const s = await api<Show>(`/shows/${id}`, { auth: true });
      setShow(s);
    } catch (e: any) { setErr(e.message); }
    finally { setLoading(false); }
  };
  useEffect(() => { void loadShow(); }, [id]);

  const buyVod = async () => {
    if (!user) { router.push("/auth/phone"); return; }
    setBuying(true);
    try {
      const r = await api<{ orderId?: string; approveUrl?: string; alreadyUnlocked?: boolean }>(
        `/billing/vod/${id}/create`,
        { method: "POST", auth: true }
      );
      if (r.alreadyUnlocked) { await loadShow(); return; }
      if (r.approveUrl && r.orderId) { setOrderId(r.orderId); setPayUrl(r.approveUrl); setPayProvider("paypal"); }
    } catch (e: any) { setErr(e.message); }
    finally { setBuying(false); }
  };

  const buyVodStripe = async () => {
    if (!user) { router.push("/auth/phone"); return; }
    setBuying(true); setErr(null);
    try {
      const r = await api<{ sessionId: string; checkoutUrl: string }>(
        "/billing/stripe/create-checkout",
        { method: "POST", auth: true, body: { purchase_type: "vod", show_id: id } }
      );
      setStripeSessionId(r.sessionId);
      if (Platform.OS === "web") {
        try { (window as any).open(r.checkoutUrl, "_blank"); } catch { /* ignore */ }
        await pollStripe(r.sessionId);
      } else {
        setPayUrl(r.checkoutUrl);
        setPayProvider("stripe");
      }
    } catch (e: any) { setErr(e.message); }
    finally { setBuying(false); }
  };

  const pollStripe = async (sessionId: string) => {
    const started = Date.now();
    while (Date.now() - started < 300_000) {
      try {
        const r = await api<{ paid?: boolean; paymentStatus: string; status: string }>(
          `/billing/stripe/session-status/${sessionId}`,
          { auth: true }
        );
        // STRICT: only unlock the VOD when Stripe confirms payment_status='paid'
        if (r.paid === true || r.paymentStatus === "paid") {
          // Belt-and-suspenders: re-fetch the show and confirm it's now unlocked before dismissing.
          try {
            const fresh = await api<any>(`/shows/${id}`, { auth: true });
            if (fresh && fresh.locked === false) {
              Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
              setCheckoutOpen(false);
              await loadShow();
              return;
            }
          } catch { /* keep polling */ }
        }
        if (r.status === "complete" && r.paymentStatus !== "paid") {
          setErr("Card payment did not go through. Please try again.");
          return;
        }
        if (r.status === "expired") { setErr("Stripe session expired."); return; }
      } catch { /* keep polling */ }
      await new Promise((res) => setTimeout(res, 2500));
    }
    setErr("Stripe timed out. Check Profile → payment history.");
  };

  const buyVodMomo = async () => {
    if (!user) { router.push("/auth/phone"); return; }
    if (momoPhone.replace(/\D/g, "").length < 9) { setErr("Enter a valid MoMo phone"); return; }
    setBuying(true); setErr(null); setSuggestStripe(false);
    try {
      const r = await api<{ reference: string; status: string; message?: string; failureReason?: string }>(
        `/billing/vod/${id}/momo`,
        { method: "POST", auth: true, body: { phone: momoPhone } }
      );
      setMomoStatus(r.status);
      if (r.status === "failed") {
        if (!isIOS) setSuggestStripe(true);
        setErr(r.message || r.failureReason || "Payment was declined by the mobile money provider.");
        return;
      }
      const started = Date.now();
      while (Date.now() - started < 90_000) {
        try {
          const p = await api<{ status: string }>(`/billing/vod/${id}/momo/${r.reference}`, { auth: true });
          setMomoStatus(p.status);
          if (p.status === "success") { Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {}); await loadShow(); setShowMomo(false); setCheckoutOpen(false); return; }
          if (p.status === "failed") { setErr("Payment was declined on the phone."); return; }
        } catch { /* keep polling */ }
        await new Promise((res) => setTimeout(res, 3000));
      }
      setErr("Timed out. Check Profile → payment history.");
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
        setCheckoutOpen(false);
        await loadShow();
      } catch (e: any) { setErr(e.message); }
      finally { setBuying(false); }
    } else if (url.includes("/paypal/cancel")) {
      setPayUrl(null);
    } else if (url.includes("/billing/stripe/return")) {
      setPayUrl(null);
      if (stripeSessionId) {
        setBuying(true);
        await pollStripe(stripeSessionId);
        setBuying(false);
      }
    } else if (url.includes("/billing/stripe/cancel")) {
      setPayUrl(null);
      setErr("Payment cancelled.");
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
  const priceRwf = show.unlockPriceRwf || "1000";

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }} testID="video-screen">
      <Modal visible={!!payUrl} animationType="slide" onRequestClose={() => setPayUrl(null)} presentationStyle="fullScreen">
        <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1, backgroundColor: "#fff" }}>
          <View style={[styles.topBar, { paddingTop: insets.top + spacing.sm, backgroundColor: payProvider === "stripe" ? "#635bff" : "#003087" }]}>
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
              <View style={{ flex: 1, backgroundColor: "#fff" }}>
                <WebView
                  source={{ uri: payUrl }}
                  style={{ flex: 1, backgroundColor: "#fff" }}
                  containerStyle={{ flex: 1 }}
                  onNavigationStateChange={onPayNav}
                  onShouldStartLoadWithRequest={(req) => {
                    const u = req.url || "";
                    if (u.includes("/paypal/success") || u.includes("/paypal/cancel") ||
                        u.includes("/billing/stripe/return") || u.includes("/billing/stripe/cancel")) {
                      onPayNav(req as any);
                      return false;
                    }
                    return true;
                  }}
                  startInLoadingState
                  javaScriptEnabled
                  domStorageEnabled
                  thirdPartyCookiesEnabled
                  keyboardDisplayRequiresUserAction={false}
                  hideKeyboardAccessoryView={false}
                  automaticallyAdjustContentInsets={false}
                  contentInsetAdjustmentBehavior="never"
                  androidLayerType="hardware"
                />
              </View>
            )
          )}
        </KeyboardAvoidingView>
      </Modal>

      <View style={[styles.topBar, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable onPress={() => router.back()} hitSlop={12} testID="video-back">
          <Ionicons name="chevron-back" size={28} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.topTitle} numberOfLines={1}>{show.title}</Text>
        <View style={{ width: 28 }} />
      </View>

      <View style={styles.player}>
        {showWarning && (
          <View style={styles.recordingOverlay} testID="recording-warning">
            <Ionicons name="warning" size={44} color="#fff" />
            <Text style={styles.recordingTitle}>SCREENSHOT DETECTED</Text>
            <Text style={styles.recordingSub}>Please respect our creators — don&apos;t share protected content. Screen recordings are also detected.</Text>
          </View>
        )}
        {show.locked ? (
          <View style={styles.lockedBox} testID="locked-box">
            <Image source={{ uri: show.thumbnail }} style={StyleSheet.absoluteFill} contentFit="cover" blurRadius={12} />
            <View style={styles.lockedInner}>
              <Ionicons name="lock-closed" size={32} color={colors.brandPrimary} />
              <Text style={styles.lockedTitle}>UNLOCK THIS VIDEO</Text>
              <Text style={styles.lockedSub}>{price} EUR / {Number(priceRwf).toLocaleString()} RWF — or go Premium for all VOD free.</Text>
              <Pressable
                onPress={() => { setErr(null); setSuggestStripe(false); setCheckoutOpen(true); }}
                style={styles.buyBtnFull}
                testID="open-vod-checkout-btn"
              >
                <Ionicons name="lock-open" size={16} color="#000" />
                <Text style={styles.buyBtnText}>UNLOCK NOW</Text>
              </Pressable>
              <Pressable onPress={() => router.push("/paywall")} style={{ paddingTop: spacing.sm }} testID="go-premium-btn">
                <Text style={styles.premInline}>OR GO PREMIUM →</Text>
              </Pressable>
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

      {/* Dedicated full-screen checkout modal — clean, no video details */}
      <Modal visible={checkoutOpen} animationType="slide" onRequestClose={() => setCheckoutOpen(false)} presentationStyle="fullScreen">
        <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1, backgroundColor: colors.surface }}>
          <View style={[styles.checkoutTop, { paddingTop: insets.top + spacing.md }]}>
            <Pressable onPress={() => setCheckoutOpen(false)} hitSlop={12} testID="checkout-close">
              <Ionicons name="close" size={26} color={colors.onSurface} />
            </Pressable>
            <Text style={styles.checkoutTopTitle}>CHECKOUT</Text>
            <View style={{ width: 26 }} />
          </View>
          <ScrollView contentContainerStyle={styles.checkoutBody} keyboardShouldPersistTaps="handled">
            <View style={styles.checkoutHero}>
              <Ionicons name="lock-open" size={40} color={colors.brandPrimary} />
              <Text style={styles.checkoutTitle}>UNLOCK VIDEO</Text>
              <Text style={styles.checkoutPrice}>{price} {currency}</Text>
              <Text style={styles.checkoutOr}>· or {Number(priceRwf).toLocaleString()} RWF ·</Text>
            </View>

            <Text style={styles.checkoutSectionLabel}>CHOOSE PAYMENT METHOD</Text>

            {isIOS ? (
              // Apple 3.1.1: no non-IAP digital payments allowed. Direct iPhone
              // buyers to the RevenueCat/Apple IAP subscription which unlocks
              // the whole VOD library, instead of offering per-video purchase.
              <View style={styles.iosVodGate} testID="checkout-ios-gate">
                <Ionicons name="logo-apple" size={40} color={colors.onSurface} />
                <Text style={styles.iosVodGateTitle}>WATCH WITH PREMIUM</Text>
                <Text style={styles.iosVodGateSub}>
                  On iPhone, this show unlocks with a Premium subscription — one Apple in-app
                  purchase gives you every video, live show and ad-free radio for the whole period.
                </Text>
                <Pressable onPress={() => { setCheckoutOpen(false); router.push("/paywall"); }} style={styles.iosVodGateBtn} testID="checkout-ios-subscribe">
                  <Text style={styles.iosVodGateBtnText}>SEE PREMIUM PLANS</Text>
                </Pressable>
              </View>
            ) : !showMomo ? (
              <View style={styles.methodList}>
                <Pressable onPress={buyVodStripe} disabled={buying} style={[styles.method, styles.methodPrimary, buying && { opacity: 0.6 }]} testID="checkout-stripe">
                  <View style={[styles.methodIcon, { backgroundColor: "#635bff" }]}>
                    <Ionicons name="card" size={20} color="#fff" />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.methodTitle}>Card (Stripe)</Text>
                    <Text style={styles.methodSub}>Visa, Mastercard, Apple Pay</Text>
                  </View>
                  {buying ? <ActivityIndicator color={colors.brandPrimary} /> : <Ionicons name="chevron-forward" size={22} color={colors.brandPrimary} />}
                </Pressable>
                <Pressable onPress={buyVod} disabled={buying} style={[styles.method, buying && { opacity: 0.6 }]} testID="checkout-paypal">
                  <View style={[styles.methodIcon, { backgroundColor: "#003087" }]}>
                    <Ionicons name="logo-paypal" size={20} color="#fff" />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.methodTitle}>PayPal</Text>
                    <Text style={styles.methodSub}>Login to PayPal to pay</Text>
                  </View>
                  <Ionicons name="chevron-forward" size={22} color={colors.brandPrimary} />
                </Pressable>
                <Pressable onPress={() => { setErr(null); setShowMomo(true); }} disabled={buying} style={styles.method} testID="checkout-momo">
                  <View style={[styles.methodIcon, { backgroundColor: colors.brandPrimary }]}>
                    <Ionicons name="phone-portrait" size={20} color="#fff" />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.methodTitle}>MTN MoMo</Text>
                    <Text style={styles.methodSub}>{Number(priceRwf).toLocaleString()} RWF · Rwanda only</Text>
                  </View>
                  <Ionicons name="chevron-forward" size={22} color={colors.brandPrimary} />
                </Pressable>
              </View>
            ) : (
              <View style={styles.momoPanel}>
                <Text style={styles.momoPanelLabel}>ENTER YOUR MTN MOMO PHONE</Text>
                <TextInput
                  value={momoPhone}
                  onChangeText={setMomoPhone}
                  keyboardType="phone-pad"
                  placeholder="+250 78x xxx xxx"
                  placeholderTextColor={colors.onSurfaceSecondary}
                  style={styles.momoInput}
                  testID="checkout-momo-phone"
                />
                <Pressable onPress={buyVodMomo} disabled={buying} style={[styles.buyBtnFull, buying && { opacity: 0.6 }, { marginTop: spacing.md }]} testID="checkout-momo-confirm">
                  {buying ? <ActivityIndicator color="#000" /> : (
                    <Text style={styles.buyBtnText}>{err ? "RETRY MOMO REQUEST" : "SEND MOMO REQUEST"}</Text>
                  )}
                </Pressable>
                {momoStatus && buying && <Text style={styles.momoStatus}>Waiting on your phone… ({momoStatus})</Text>}
                <Pressable onPress={() => setShowMomo(false)} style={{ alignItems: "center", paddingTop: spacing.md }}>
                  <Text style={styles.momoBack}>← choose a different method</Text>
                </Pressable>
              </View>
            )}

            {err && <Text style={styles.err}>{err}</Text>}
            {suggestStripe && !isIOS && (
              <Pressable
                onPress={() => { setShowMomo(false); setErr(null); setSuggestStripe(false); void buyVodStripe(); }}
                style={styles.fallbackBanner}
                testID="checkout-fallback-stripe"
              >
                <Ionicons name="card" size={16} color={colors.brandPrimary} />
                <Text style={styles.fallbackText}>Try Card (Stripe) instead →</Text>
              </Pressable>
            )}

            {!isIOS && (
            <Pressable onPress={() => { setCheckoutOpen(false); router.push("/paywall"); }} style={styles.premiumUpsell} testID="checkout-premium">
              <Ionicons name="star" size={16} color={colors.brandPrimary} />
              <Text style={styles.premiumUpsellText}>Or go Premium — unlock ALL VOD from 1,000 RWF/mo →</Text>
            </Pressable>
            )}

            {!isIOS && (
            <View style={styles.trustRow}>
              <Ionicons name="shield-checkmark" size={14} color={colors.success} />
              <Text style={styles.trustText}>Encrypted payment · no card details stored</Text>
            </View>
            )}
          </ScrollView>
        </KeyboardAvoidingView>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center", gap: spacing.md },
  topBar: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.lg, gap: spacing.md, paddingBottom: spacing.sm, backgroundColor: colors.surface },
  topTitle: { ...type.h2, flex: 1, textAlign: "center", fontSize: 15 },
  player: { aspectRatio: 16 / 9, backgroundColor: "#000" },
  recordingOverlay: {
    position: "absolute",
    left: 0, right: 0, top: 0, bottom: 0,
    zIndex: 20,
    backgroundColor: "rgba(15,15,19,0.95)",
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
  },
  recordingTitle: { ...type.h1, color: "#fff", letterSpacing: 1, textAlign: "center", fontSize: 18 },
  recordingSub: { ...type.bodyMuted, color: "rgba(255,255,255,0.7)", textAlign: "center", fontSize: 13, lineHeight: 18 },
  lockedBox: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.surfaceSecondary, overflow: "hidden" },
  lockedInner: { alignItems: "center", padding: spacing.xl, gap: spacing.sm, backgroundColor: "rgba(15,15,19,0.78)", borderRadius: radius.md, maxWidth: "94%" },
  lockedTitle: { ...type.h1, color: colors.brandPrimary, letterSpacing: 1, marginTop: spacing.sm },
  lockedSub: { ...type.bodyMuted, textAlign: "center", marginBottom: spacing.md, fontSize: 13 },
  lockedActions: { flexDirection: "row", gap: spacing.sm, alignItems: "center" },
  lockedActionsCol: { flexDirection: "column", gap: spacing.sm, alignSelf: "stretch", marginTop: spacing.sm },
  buyBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.md, paddingVertical: 12, borderRadius: radius.pill, flex: 1 },
  buyBtnFull: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, backgroundColor: colors.brandPrimary, paddingVertical: 14, borderRadius: radius.pill, alignSelf: "stretch" },
  buyBtnOutlineFull: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, paddingVertical: 12, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.brandPrimary, alignSelf: "stretch" },
  buyBtnText: { color: "#000", fontFamily: "BarlowCondensed-Bold", letterSpacing: 1.5, fontSize: 14, fontWeight: "900" },
  fallbackBanner: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, marginTop: spacing.md, paddingVertical: 10, paddingHorizontal: spacing.md, borderRadius: radius.pill, backgroundColor: colors.brandTertiary, borderWidth: 1, borderColor: colors.brandPrimary },
  fallbackText: { color: colors.brandPrimary, fontFamily: "BarlowCondensed-Bold", fontSize: 12, letterSpacing: 0.5 },
  momoBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 4, paddingHorizontal: spacing.md, paddingVertical: 12, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.brandPrimary, flex: 1 },
  momoBtnText: { color: colors.brandPrimary, fontFamily: "BarlowCondensed-Bold", fontSize: 11, letterSpacing: 1 },
  momoInput: { backgroundColor: colors.surface, borderRadius: radius.md, padding: 12, color: colors.onSurface, fontSize: 14, borderWidth: 1, borderColor: colors.border, textAlign: "center" },
  momoStatus: { ...type.caption, color: colors.brandPrimary, textAlign: "center" },
  momoBack: { color: colors.onSurfaceSecondary, fontSize: 11 },
  retryBanner: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, backgroundColor: colors.brandPrimary, height: 44, borderRadius: radius.md, marginTop: spacing.sm },
  retryText: { color: "#000", fontFamily: "BarlowCondensed-Bold", letterSpacing: 1.8, fontSize: 14, fontWeight: "900" },
  premInline: { color: colors.brandPrimary, fontFamily: "BarlowCondensed-Bold", fontSize: 12, letterSpacing: 1.5 },
  err: { color: colors.error, textAlign: "center", marginTop: 6, fontSize: 12 },
  premBtn: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: spacing.md, paddingVertical: 12, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.brandPrimary },
  premBtnText: { color: colors.brandPrimary, fontFamily: "BarlowCondensed-Bold", fontSize: 12, letterSpacing: 1 },
  metaRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginBottom: spacing.sm, flexWrap: "wrap" },
  cat: { ...type.label, color: colors.brandPrimary, letterSpacing: 1.5 },
  premBadge: { flexDirection: "row", alignItems: "center", gap: 3, backgroundColor: colors.brandPrimary, paddingHorizontal: 6, paddingVertical: 3, borderRadius: radius.sm },
  premText: { color: colors.onBrandPrimary, fontFamily: "BarlowCondensed-Bold", fontSize: 9, letterSpacing: 1 },
  dur: { ...type.caption, marginLeft: "auto" },
  title: { ...type.displayLg, fontSize: 24, marginBottom: spacing.md, lineHeight: 28 },
  desc: { ...type.bodyMuted, lineHeight: 22, fontSize: 14 },
  // Checkout modal styles
  checkoutTop: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.border, backgroundColor: colors.surface },
  checkoutTopTitle: { ...type.h2, letterSpacing: 2, fontSize: 15 },
  checkoutBody: { padding: spacing.lg, paddingBottom: 80, gap: spacing.lg, maxWidth: 560, width: "100%", alignSelf: "center" },
  checkoutHero: { alignItems: "center", padding: spacing.lg, gap: 4, backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border },
  checkoutTitle: { ...type.h1, color: colors.brandPrimary, letterSpacing: 1.2, marginTop: spacing.sm, fontSize: 22 },
  checkoutPrice: { fontFamily: "BarlowCondensed-Bold", fontSize: 40, color: colors.onSurface, letterSpacing: 0.5, marginTop: 4 },
  checkoutOr: { ...type.bodyMuted, fontSize: 12, marginTop: 2 },
  checkoutSectionLabel: { ...type.label, letterSpacing: 1.5, fontSize: 12, color: colors.onSurfaceSecondary },
  methodList: { gap: spacing.sm },
  method: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.surfaceSecondary, padding: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border },
  methodPrimary: { borderColor: colors.brandPrimary },
  methodIcon: { width: 44, height: 44, borderRadius: radius.sm, alignItems: "center", justifyContent: "center" },
  methodTitle: { ...type.h2, fontSize: 15 },
  methodSub: { ...type.caption, marginTop: 2 },
  momoPanel: { padding: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.brandPrimary },
  momoPanelLabel: { ...type.label, letterSpacing: 1.5, fontSize: 11, marginBottom: spacing.sm, color: colors.onSurfaceSecondary },
  premiumUpsell: { flexDirection: "row", alignItems: "center", gap: 8, paddingVertical: spacing.md, paddingHorizontal: spacing.md, borderRadius: radius.md, backgroundColor: colors.brandTertiary, borderWidth: 1, borderColor: colors.brandPrimary, justifyContent: "center" },
  premiumUpsellText: { color: colors.brandPrimary, fontFamily: "BarlowCondensed-Bold", fontSize: 12, letterSpacing: 0.5, textAlign: "center" },
  trustRow: { flexDirection: "row", alignItems: "center", gap: 6, justifyContent: "center", paddingTop: spacing.sm },
  trustText: { ...type.caption, fontSize: 11, color: colors.onSurfaceSecondary },
  // iOS 3.1.1 compliance gate for VOD checkout modal
  iosVodGate: { alignItems: "center", padding: spacing.xl, gap: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border },
  iosVodGateTitle: { ...type.h1, letterSpacing: 1.2, fontSize: 20, textAlign: "center", marginTop: spacing.sm },
  iosVodGateSub: { ...type.bodyMuted, textAlign: "center", lineHeight: 20, fontSize: 13 },
  iosVodGateBtn: { backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.xxl, paddingVertical: spacing.md, borderRadius: radius.pill, marginTop: spacing.sm },
  iosVodGateBtnText: { color: "#000", fontFamily: "BarlowCondensed-Bold", letterSpacing: 1.8, fontSize: 14 },
});
