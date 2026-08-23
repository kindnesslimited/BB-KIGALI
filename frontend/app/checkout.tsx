import { useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, ActivityIndicator, TextInput, KeyboardAvoidingView, Platform, Modal } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { WebView, type WebViewNavigation } from "react-native-webview";
import * as Haptics from "expo-haptics";
import { colors, spacing, type, radius } from "@/src/theme";
import { api } from "@/src/api";
import { useAuth } from "@/src/context/auth";

type Method = "stripe" | "paypal" | "mtn_momo" | "airtel";
const isIOS = Platform.OS === "ios";
const ALL_METHODS: { id: Method; label: string; sub: string; icon: any; needsPhone?: boolean; hiddenOnIOS?: boolean; disabled?: boolean }[] = [
  { id: "paypal", label: "PayPal", sub: "Live — Visa/Mastercard or PayPal balance", icon: "logo-paypal" },
  { id: "stripe", label: "Card (Stripe)", sub: "Live — Visa, Mastercard, Amex, Apple Pay & Google Pay", icon: "card-outline", hiddenOnIOS: true },
  { id: "mtn_momo", label: "MTN Mobile Money", sub: "Live — Rwanda MTN MoMo via BeSoft Pay", icon: "phone-portrait-outline", needsPhone: true },
  { id: "airtel", label: "Airtel Money", sub: "Coming soon", icon: "phone-portrait-outline", needsPhone: true, disabled: true },
];
const METHODS = ALL_METHODS.filter((m) => !(isIOS && m.hiddenOnIOS));

export default function Checkout() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { plan, amount } = useLocalSearchParams<{ plan: string; amount: string }>();
  const { refresh } = useAuth();
  const [method, setMethod] = useState<Method>("paypal");
  // NOTE: default to blank "+250 " prefix so the admin never accidentally pays THEMSELVES.
  // The customer's MoMo number MUST be entered explicitly; the collection account cannot be debited.
  const [phone, setPhone] = useState("+250 ");
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [paypalUrl, setPaypalUrl] = useState<string | null>(null);
  const [paypalSubId, setPaypalSubId] = useState<string | null>(null);
  const [stripeUrl, setStripeUrl] = useState<string | null>(null);
  const [stripeSessionId, setStripeSessionId] = useState<string | null>(null);
  const [suggestStripe, setSuggestStripe] = useState(false);

  const onPayPalNav = async (nav: WebViewNavigation) => {
    const url = nav.url || "";
    // Detect return / cancel URLs (both go to bbkigali.com/paypal/...)
    if (url.includes("bbkigali.com/paypal/success") || url.includes("/paypal/success")) {
      setPaypalUrl(null);
      setLoading(true);
      try {
        const r = await api<{ status: string }>(`/billing/paypal/verify/${paypalSubId}`, { method: "POST", auth: true });
        if (r.status === "success") {
          await refresh();
          Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
          setSuccess(true);
        } else {
          setErr("PayPal reported the subscription is not yet active. It may take a moment — check your Profile.");
        }
      } catch (e: any) { setErr(e.message || "Verification failed"); }
      finally { setLoading(false); }
    } else if (url.includes("bbkigali.com/paypal/cancel") || url.includes("/paypal/cancel")) {
      setPaypalUrl(null);
      setErr("Payment cancelled.");
    }
  };

  const [momoStatus, setMomoStatus] = useState<string | null>(null);

  const pollStripe = async (sessionId: string) => {
    const started = Date.now();
    while (Date.now() - started < 300_000) {
      try {
        const r = await api<{ paid?: boolean; paymentStatus: string; status: string }>(
          `/billing/stripe/session-status/${sessionId}`,
          { auth: true }
        );
        // STRICT: only count as success when Stripe confirmed payment_status='paid'.
        if (r.paid === true || r.paymentStatus === "paid") {
          await refresh();
          // Belt-and-suspenders: re-fetch /auth/me and confirm the tier actually flipped.
          // If the backend hasn't granted (e.g. race with webhook), keep polling.
          try {
            const me = await api<{ tier?: string }>("/auth/me", { auth: true });
            if (me?.tier && me.tier !== "free") {
              Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
              setSuccess(true);
              return;
            }
          } catch { /* fall through to keep polling */ }
        }
        // Session ended but payment failed / was cancelled by Stripe → surface immediately.
        if (r.status === "complete" && r.paymentStatus !== "paid") {
          setErr("Card payment did not go through. Please try again or use another method.");
          return;
        }
        if (r.status === "expired") {
          setErr("Payment session expired. Please try again.");
          return;
        }
      } catch { /* keep polling */ }
      await new Promise((res) => setTimeout(res, 2500));
    }
    setErr("Timed out waiting for Stripe confirmation. Check Payment History or try again.");
  };

  const onStripeNav = async (nav: WebViewNavigation) => {
    const url = nav.url || "";
    if (url.includes("/billing/stripe/return") || url.includes("/billing/stripe/cancel")) {
      const cancelled = url.includes("/cancel");
      setStripeUrl(null);
      if (cancelled) {
        setErr("Payment cancelled.");
        return;
      }
      if (stripeSessionId) {
        setLoading(true);
        await pollStripe(stripeSessionId);
        setLoading(false);
      }
    }
  };

  const pollMomo = async (reference: string) => {
    const started = Date.now();
    while (Date.now() - started < 90_000) {
      try {
        const r = await api<{ status: string }>(`/billing/momo/${reference}`, { auth: true });
        setMomoStatus(r.status);
        if (r.status === "success") {
          await refresh();
          Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
          setSuccess(true);
          return;
        }
        if (r.status === "failed") {
          setErr("Payment failed or was cancelled on your phone.");
          return;
        }
      } catch { /* keep polling */ }
      await new Promise((res) => setTimeout(res, 3000));
    }
    setErr("Timed out waiting for confirmation. Check Payment History or try again.");
  };

  const pay = async () => {
    setErr(null); setLoading(true); setMomoStatus(null); setSuggestStripe(false);
    try {
      const chosen = METHODS.find((m) => m.id === method)!;
      if (chosen.needsPhone && phone.replace(/\D/g, "").length < 9) {
        throw new Error("Enter a valid phone number for mobile money");
      }
      if (method === "paypal") {
        const r = await api<{ subscriptionId: string; approveUrl: string }>(
          "/billing/paypal/create-subscription",
          { method: "POST", auth: true, body: { plan } }
        );
        setPaypalSubId(r.subscriptionId);
        setPaypalUrl(r.approveUrl);
        return;
      }
      if (method === "stripe") {
        const r = await api<{ sessionId: string; checkoutUrl: string }>(
          "/billing/stripe/create-checkout",
          { method: "POST", auth: true, body: { purchase_type: "subscription", plan } }
        );
        setStripeSessionId(r.sessionId);
        if (Platform.OS === "web") {
          // On web, open in a new tab and poll status
          try { (window as any).open(r.checkoutUrl, "_blank"); } catch { /* ignore */ }
          await pollStripe(r.sessionId);
        } else {
          setStripeUrl(r.checkoutUrl);
        }
        return;
      }
      if (method === "mtn_momo") {
        const r = await api<{ reference: string; status: string; message?: string; failureReason?: string }>(
          "/billing/momo/initiate",
          { method: "POST", auth: true, body: { plan, phone } }
        );
        setMomoStatus(r.status);
        if (r.status === "failed") {
          // Auto-suggest Stripe as fallback (unless we're on iOS where Stripe is hidden)
          if (!isIOS) setSuggestStripe(true);
          throw new Error(r.message || r.failureReason || "MoMo request was declined.");
        }
        await pollMomo(r.reference);
        return;
      }
      // Airtel Money is not yet integrated. Reject the tap so no unpaid access is ever granted.
      throw new Error("Airtel Money is not available yet. Please use Card (Stripe), PayPal, or MTN Mobile Money.");
    } catch (e: any) {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error).catch(() => {});
      setErr(e.message || "Payment failed");
    } finally { setLoading(false); }
  };

  if (success) {
    return (
      <View style={styles.successWrap} testID="checkout-success">
        <View style={styles.successIcon}>
          <Ionicons name="checkmark" size={56} color={colors.onBrandPrimary} />
        </View>
        <Text style={styles.successTitle}>YOU&apos;RE IN</Text>
        <Text style={styles.successSub}>Your subscription is now active. Enjoy BB FM Kigali!</Text>
        <Pressable onPress={() => router.replace("/(tabs)")} style={styles.doneBtn} testID="checkout-done">
          <Text style={styles.doneText}>START LISTENING</Text>
        </Pressable>
      </View>
    );
  }

  // Compute display prices — Card (PayPal or Stripe) uses EUR, MoMo/Airtel use RWF
  const eurPrice: Record<string, string> = {
    basic_monthly: "1.00", basic_yearly: "10.00", premium_monthly: "3.00", premium_yearly: "30.00",
  };
  const isCardMethod = method === "paypal" || method === "stripe";
  const isPayPal = method === "paypal";
  const displayCurrency = isCardMethod ? "EUR" : "RWF";
  const displayAmount = isCardMethod
    ? eurPrice[String(plan)] || "0.00"
    : Number(amount).toLocaleString();
  // Parallel: always show both
  const parallelText = isCardMethod
    ? `≈ ${Number(amount).toLocaleString()} RWF via Mobile Money`
    : `≈ ${eurPrice[String(plan)] || "0"} EUR via Card / PayPal`;

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1, backgroundColor: colors.surface }}>
      <Modal visible={!!stripeUrl} animationType="slide" onRequestClose={() => setStripeUrl(null)} presentationStyle="fullScreen">
        <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1, backgroundColor: "#fff" }}>
          <View style={[styles.top, { paddingTop: insets.top + spacing.md, backgroundColor: "#635bff" }]}>
            <Pressable onPress={() => setStripeUrl(null)} hitSlop={12} testID="stripe-close">
              <Ionicons name="close" size={26} color="#fff" />
            </Pressable>
            <Text style={[styles.topTitle, { color: "#fff" }]}>SECURE CARD PAYMENT</Text>
            <View style={{ width: 26 }} />
          </View>
          {stripeUrl && (
            Platform.OS === "web" ? (
              <iframe src={stripeUrl} style={{ flex: 1, width: "100%", height: "100%", border: 0 }} />
            ) : (
              <View style={{ flex: 1, backgroundColor: "#fff" }}>
                <WebView
                  source={{ uri: stripeUrl }}
                  style={{ flex: 1, backgroundColor: "#fff" }}
                  containerStyle={{ flex: 1 }}
                  onNavigationStateChange={onStripeNav}
                  onShouldStartLoadWithRequest={(req) => {
                    const u = req.url || "";
                    if (u.includes("/billing/stripe/return") || u.includes("/billing/stripe/cancel")) {
                      onStripeNav(req as any);
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
                  testID="stripe-webview"
                />
              </View>
            )
          )}
        </KeyboardAvoidingView>
      </Modal>

      <Modal visible={!!paypalUrl} animationType="slide" onRequestClose={() => setPaypalUrl(null)} presentationStyle="fullScreen">
        <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1, backgroundColor: "#fff" }}>
          <View style={[styles.top, { paddingTop: insets.top + spacing.md, backgroundColor: "#003087" }]}>
            <Pressable onPress={() => setPaypalUrl(null)} hitSlop={12} testID="paypal-close">
              <Ionicons name="close" size={26} color="#fff" />
            </Pressable>
            <Text style={[styles.topTitle, { color: "#fff" }]}>PAYPAL CHECKOUT</Text>
            <View style={{ width: 26 }} />
          </View>
          {paypalUrl && (
            Platform.OS === "web" ? (
              <iframe src={paypalUrl} style={{ flex: 1, width: "100%", height: "100%", border: 0 }} />
            ) : (
              <View style={{ flex: 1, backgroundColor: "#fff" }}>
                <WebView
                  source={{ uri: paypalUrl }}
                  style={{ flex: 1, backgroundColor: "#fff" }}
                  containerStyle={{ flex: 1 }}
                  onNavigationStateChange={onPayPalNav}
                  onShouldStartLoadWithRequest={(req) => {
                    const u = req.url || "";
                    // Intercept our terminal URLs BEFORE the WebView tries to load them
                    // (bbkigali.com may be unreachable / password-protected).
                    if (u.includes("/paypal/success") || u.includes("/paypal/cancel")) {
                      onPayPalNav(req as any);
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
                  testID="paypal-webview"
                />
              </View>
            )
          )}
        </KeyboardAvoidingView>
      </Modal>

      <View style={[styles.top, { paddingTop: insets.top + spacing.md }]}>
        <Pressable onPress={() => router.back()} hitSlop={12} testID="checkout-back">
          <Ionicons name="chevron-back" size={28} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.topTitle}>CHECKOUT</Text>
        <View style={{ width: 28 }} />
      </View>

      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 160 }} testID="checkout-screen">
        <View style={styles.summary}>
          <Text style={styles.summaryLabel}>YOU&apos;RE PAYING FOR</Text>
          <Text style={styles.summaryPlan}>{String(plan || "").replace("_", " ").toUpperCase()}</Text>
          <Text style={styles.summaryAmount}>{displayAmount} {displayCurrency}</Text>
          <Text style={styles.summaryNote}>{parallelText}</Text>
        </View>

        <Text style={styles.sectionLabel}>PAYMENT METHOD</Text>
        <View style={{ gap: spacing.sm }}>
          {METHODS.map((m) => {
            const active = method === m.id;
            return (
              <Pressable
                key={m.id}
                onPress={() => {
                  if (m.disabled) return;
                  Haptics.selectionAsync().catch(() => {});
                  setMethod(m.id);
                }}
                disabled={!!m.disabled}
                style={[styles.methodRow, active && styles.methodRowActive, m.disabled && { opacity: 0.4 }]}
                testID={`method-${m.id}`}
              >
                <View style={styles.methodIcon}>
                  <Ionicons name={m.icon} size={22} color={active ? colors.brandPrimary : colors.onSurface} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.methodLabel}>{m.label}</Text>
                  <Text style={styles.methodSub}>{m.sub}</Text>
                </View>
                <View style={[styles.radio, active && styles.radioActive]}>
                  {active && <View style={styles.radioDot} />}
                </View>
              </Pressable>
            );
          })}
        </View>

        {METHODS.find((m) => m.id === method)?.needsPhone && (
          <View style={{ marginTop: spacing.lg }}>
            <Text style={styles.sectionLabel}>YOUR MOBILE MONEY NUMBER</Text>
            <TextInput
              testID="momo-phone-input"
              value={phone}
              onChangeText={setPhone}
              keyboardType="phone-pad"
              placeholder="+250 78x xxx xxx"
              placeholderTextColor={colors.onSurfaceSecondary}
              style={styles.momoInput}
            />
            <Text style={styles.phoneHint}>
              Enter the MoMo number you want to pay from. You&apos;ll receive a prompt on your phone to confirm.
            </Text>
          </View>
        )}

        {isPayPal && (
          <View style={[styles.demoBox, { borderColor: colors.success }]}>
            <Ionicons name="shield-checkmark-outline" size={16} color={colors.success} />
            <Text style={styles.demoText}>Live PayPal. You will be redirected to PayPal to complete payment.</Text>
          </View>
        )}
        {method === "stripe" && (
          <View style={[styles.demoBox, { borderColor: colors.success }]}>
            <Ionicons name="shield-checkmark-outline" size={16} color={colors.success} />
            <Text style={styles.demoText}>Live Stripe. Pay by Visa, Mastercard, Amex, or wallet — you&apos;ll be redirected to secure Stripe Checkout.</Text>
          </View>
        )}
        {method === "airtel" && (
          <View style={styles.demoBox}>
            <Ionicons name="information-circle-outline" size={16} color={colors.warning} />
            <Text style={styles.demoText}>Airtel Money is coming soon. Please use PayPal, Stripe, or MTN MoMo for now.</Text>
          </View>
        )}
        {method === "mtn_momo" && (
          <View style={[styles.demoBox, { borderColor: colors.success }]}>
            <Ionicons name="shield-checkmark-outline" size={16} color={colors.success} />
            <Text style={styles.demoText}>Live MTN MoMo. You&apos;ll get a prompt on your phone to approve the payment.</Text>
          </View>
        )}
        {momoStatus && loading && (
          <View style={[styles.demoBox, { borderColor: colors.brandPrimary, marginTop: spacing.md }]} testID="momo-status">
            <ActivityIndicator color={colors.brandPrimary} />
            <Text style={styles.demoText}>Waiting for MoMo approval on your phone… (status: {momoStatus})</Text>
          </View>
        )}

        {err && <Text style={styles.err} testID="checkout-error">{err}</Text>}
        {err && method === "mtn_momo" && !loading && (
          <Pressable onPress={pay} style={styles.retryBanner} testID="momo-retry-btn">
            <Ionicons name="refresh" size={20} color="#000" />
            <Text style={styles.retryText}>RETRY MOMO PAYMENT</Text>
          </Pressable>
        )}
        {suggestStripe && !isIOS && (
          <Pressable
            onPress={() => { setMethod("stripe"); setErr(null); setSuggestStripe(false); }}
            style={styles.fallbackBanner}
            testID="momo-fallback-stripe"
          >
            <Ionicons name="card" size={20} color={colors.brandPrimary} />
            <View style={{ flex: 1, marginLeft: spacing.sm }}>
              <Text style={styles.fallbackTitle}>Try card payment instead?</Text>
              <Text style={styles.fallbackSub}>Pay with Visa, Mastercard, Amex, Apple Pay, or Google Pay via Stripe.</Text>
            </View>
            <Ionicons name="chevron-forward" size={20} color={colors.brandPrimary} />
          </Pressable>
        )}
      </ScrollView>

      <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.md }]}>
        <Pressable onPress={pay} disabled={loading} style={[styles.payBtn, loading && { opacity: 0.6 }]} testID="pay-btn">
          {loading ? <ActivityIndicator color="#000" /> : (
            <>
              <Ionicons name="lock-closed" size={18} color="#000" />
              <Text style={styles.payText}>PAY {displayAmount} {displayCurrency}</Text>
            </>
          )}
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  top: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  topTitle: { ...type.h2, letterSpacing: 1.5 },
  summary: { backgroundColor: colors.brandTertiary, borderRadius: radius.md, padding: spacing.lg, marginBottom: spacing.xl, borderWidth: 1, borderColor: colors.brandPrimary },
  summaryLabel: { ...type.label, color: colors.brandPrimary, letterSpacing: 2 },
  summaryPlan: { ...type.h2, color: colors.onBrandTertiary, marginTop: 4, fontSize: 16 },
  summaryAmount: { ...type.displayXL, fontSize: 36, marginTop: spacing.sm },
  summaryNote: { ...type.caption, marginTop: 4, color: colors.onBrandTertiary },
  sectionLabel: { ...type.label, letterSpacing: 1.5, marginBottom: spacing.sm, color: colors.onSurfaceSecondary },
  methodRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1.5, borderColor: colors.border },
  methodRowActive: { borderColor: colors.brandPrimary },
  methodIcon: { width: 44, height: 44, borderRadius: radius.sm, backgroundColor: colors.surfaceTertiary, alignItems: "center", justifyContent: "center" },
  methodLabel: { ...type.h2, fontSize: 15 },
  methodSub: { ...type.caption, marginTop: 2 },
  radio: { width: 22, height: 22, borderRadius: 11, borderWidth: 2, borderColor: colors.border, alignItems: "center", justifyContent: "center" },
  radioActive: { borderColor: colors.brandPrimary },
  radioDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: colors.brandPrimary },
  momoInput: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.md, color: colors.onSurface, fontSize: 16, borderWidth: 1, borderColor: colors.border },
  retryBanner: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, backgroundColor: colors.brandPrimary, height: 48, borderRadius: radius.md, marginTop: spacing.md },
  retryText: { color: "#000", fontFamily: "BarlowCondensed-Bold", letterSpacing: 1.8, fontSize: 15, fontWeight: "900" },
  demoBox: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginTop: spacing.lg, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.md, borderWidth: 1, borderColor: colors.warning },
  demoText: { ...type.caption, flex: 1, color: colors.onSurfaceTertiary },
  err: { color: colors.error, marginTop: spacing.md, textAlign: "center" },
  phoneHint: { ...type.caption, marginTop: 6, color: colors.onSurfaceSecondary, lineHeight: 15 },
  fallbackBanner: {
    flexDirection: "row",
    alignItems: "center",
    marginTop: spacing.md,
    padding: spacing.md,
    backgroundColor: colors.brandTertiary,
    borderRadius: radius.md,
    borderWidth: 1.5,
    borderColor: colors.brandPrimary,
  },
  fallbackTitle: { ...type.h2, fontSize: 14, color: colors.brandPrimary, letterSpacing: 0.5 },
  fallbackSub: { ...type.caption, marginTop: 2, color: colors.onBrandTertiary },
  footer: { position: "absolute", left: 0, right: 0, bottom: 0, backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.border, padding: spacing.lg },
  payBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, backgroundColor: colors.brandPrimary, height: 56, borderRadius: radius.md },
  payText: { ...type.h2, color: "#000", fontFamily: "BarlowCondensed-Bold", letterSpacing: 1.8, fontSize: 17, fontWeight: "900" },
  successWrap: { flex: 1, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center", padding: spacing.xl, gap: spacing.md },
  successIcon: { width: 100, height: 100, borderRadius: 50, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", marginBottom: spacing.lg },
  successTitle: { ...type.displayXL, letterSpacing: 2 },
  successSub: { ...type.bodyMuted, textAlign: "center", marginBottom: spacing.xl, lineHeight: 22 },
  doneBtn: { backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.xxl, paddingVertical: spacing.md, borderRadius: radius.pill },
  doneText: { ...type.h2, color: colors.onBrandPrimary, letterSpacing: 1.5, fontSize: 14 },
});
