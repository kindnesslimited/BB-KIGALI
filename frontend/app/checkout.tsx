import { useEffect, useRef, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, ActivityIndicator, TextInput, KeyboardAvoidingView, Platform, Modal, AppState, AppStateStatus, Linking as RNLinking } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { WebView, type WebViewNavigation } from "react-native-webview";
import * as Haptics from "expo-haptics";
import * as WebBrowser from "expo-web-browser";
import { colors, spacing, type, radius } from "@/src/theme";
import { api } from "@/src/api";
import { useAuth } from "@/src/context/auth";

type Method = "stripe" | "paypal" | "mtn_momo";
const isIOS = Platform.OS === "ios";
// ALL platforms — including iOS — get the same payment options. Payment pages
// open in the EXTERNAL browser (Safari on iOS, Chrome on Android) so users
// pay through the same central backend flow regardless of device.
const METHODS: { id: Method; label: string; sub: string; icon: any; needsPhone?: boolean; disabled?: boolean }[] = [
  { id: "paypal", label: "PayPal", sub: "Live — Visa/Mastercard or PayPal balance", icon: "logo-paypal" },
  { id: "stripe", label: "Card (Stripe)", sub: "Live — Visa, Mastercard, Amex, Apple Pay & Google Pay", icon: "card-outline" },
  { id: "mtn_momo", label: "MTN Mobile Money", sub: "Live — Rwanda MTN MoMo via BeSoft Pay", icon: "phone-portrait-outline", needsPhone: true },
];

export default function Checkout() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { plan, amount } = useLocalSearchParams<{ plan: string; amount: string }>();
  const { refresh, syncSubscriptionFromBackend, hasActiveSubscription } = useAuth();
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
  const [termsAccepted, setTermsAccepted] = useState(false);
  const [terms, setTerms] = useState<{ version?: string; url?: string; privacyUrl?: string }>({});
  // "External browser" flow — when the user pays via Safari/Chrome we show a
  // waiting prompt on top of the checkout page. Cleared when the app foregrounds
  // and reconcile confirms the subscription.
  const [awaitingReturn, setAwaitingReturn] = useState<null | { provider: "stripe" | "paypal"; sessionId?: string; subscriptionId?: string }>(null);
  const appStateRef = useRef<AppStateStatus>(AppState.currentState);

  // Fetch current Terms & Conditions version once for the page
  useEffect(() => { void api<typeof terms>("/legal/terms/current").then(setTerms).catch(() => {}); }, []);

  // Backend-first precheck — if the user already has an active subscription
  // on ANY platform, redirect them straight to the app. Never charge twice.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const status = await syncSubscriptionFromBackend();
        if (!cancelled && status?.active) {
          router.replace("/(tabs)");
        }
      } catch { /* fall through */ }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (hasActiveSubscription) router.replace("/(tabs)");
  }, [hasActiveSubscription, router]);

  const onPayPalNav = async (nav: WebViewNavigation) => {
    const url = nav.url || "";
    const lower = url.toLowerCase();
    // Broaden success detection: cover ALL known PayPal return paths across
    // sandbox/live + our custom domain. If ANY of these markers appear we
    // assume the user completed the flow and verify against PayPal.
    const successMarkers = [
      "/paypal/success",
      "/paypal/return",
      "billing/paypal/return",
      "paymentaction=commit",
      "checkoutnow?token=",  // classic PayPal one-time
      "webscr?cmd=_express-checkout",
      "return_from_paypal=1",
      "returnurl=",
      "payerid=",  // PayPal appends ?PayerID=... on approval
      "subscription_id=",
    ];
    const cancelMarkers = [
      "/paypal/cancel",
      "billing/paypal/cancel",
      "?cancel=1",
      "cancel_return",
    ];
    if (cancelMarkers.some((m) => lower.includes(m))) {
      setPaypalUrl(null);
      setErr("Payment cancelled.");
      return;
    }
    if (successMarkers.some((m) => lower.includes(m))) {
      setPaypalUrl(null);
      setLoading(true);
      try {
        const r = await api<{ status: string }>(`/billing/paypal/verify/${paypalSubId}`, { method: "POST", auth: true });
        if (r.status === "success") {
          // Backend is source of truth — reconcile before flipping UI.
          const status = await syncSubscriptionFromBackend();
          if (status?.active) {
            Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
            setSuccess(true);
            return;
          }
        }
        setErr("PayPal reported the subscription is not yet active. It may take a moment — check your Profile.");
      } catch (e: any) { setErr(e.message || "Verification failed"); }
      finally { setLoading(false); }
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
          // Central backend is the source of truth. Reconcile before flipping UI.
          const status = await syncSubscriptionFromBackend();
          if (status?.active) {
            Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
            setSuccess(true);
            return;
          }
          // Backend hasn't applied the entitlement yet — keep polling.
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
    const lower = url.toLowerCase();
    // Broaden Stripe success/cancel detection: cover our custom return URL,
    // Stripe's hosted success page, and any URL carrying a completed session id.
    const cancelMarkers = [
      "/billing/stripe/cancel",
      "checkout.stripe.com/pay/cs_test_cancel",  // hosted-cancel edge case
      "?cancel=1",
    ];
    const successMarkers = [
      "/billing/stripe/return",
      "/billing/stripe/success",
      "checkout/success",
      "session_id=cs_",
      "checkout_status=complete",
    ];
    if (cancelMarkers.some((m) => lower.includes(m))) {
      setStripeUrl(null);
      setErr("Payment cancelled.");
      return;
    }
    if (successMarkers.some((m) => lower.includes(m))) {
      setStripeUrl(null);
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
          // Reconcile with the central backend — this is what actually flips
          // the user to premium; never trust a local status alone.
          const status = await syncSubscriptionFromBackend();
          if (status?.active) {
            Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
            setSuccess(true);
            return;
          }
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

  // When the app returns to foreground while we're waiting for an external
  // browser payment to complete, immediately reconcile subscription status
  // from the central backend. If the backend confirms an active subscription,
  // the checkout flips to the success state without any user action.
  useEffect(() => {
    const sub = AppState.addEventListener("change", async (next) => {
      const prev = appStateRef.current;
      appStateRef.current = next;
      if (prev === "active" || next !== "active") return;
      if (!awaitingReturn) return;
      try {
        // Try provider-specific verify first (fast path).
        if (awaitingReturn.provider === "paypal" && awaitingReturn.subscriptionId) {
          try {
            const v = await api<{ status: string }>(`/billing/paypal/verify/${awaitingReturn.subscriptionId}`, { method: "POST", auth: true });
            if (v.status !== "success") {
              // fallthrough — backend reconcile might still know
            }
          } catch { /* ignore */ }
        }
        const status = await syncSubscriptionFromBackend();
        if (status?.active) {
          Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
          setSuccess(true);
          setAwaitingReturn(null);
        }
      } catch { /* keep waiting — user can retry */ }
    });
    return () => { try { sub?.remove?.(); } catch {} };
  }, [awaitingReturn, syncSubscriptionFromBackend]);

  const manualCheckReturn = async () => {
    setLoading(true);
    try {
      if (awaitingReturn?.provider === "paypal" && awaitingReturn.subscriptionId) {
        try {
          await api(`/billing/paypal/verify/${awaitingReturn.subscriptionId}`, { method: "POST", auth: true });
        } catch { /* ignore */ }
      } else if (awaitingReturn?.provider === "stripe" && awaitingReturn.sessionId) {
        // Kick off the poll fresh in case the initial poll timed out.
        void pollStripe(awaitingReturn.sessionId);
      }
      const status = await syncSubscriptionFromBackend();
      if (status?.active) {
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
        setSuccess(true);
        setAwaitingReturn(null);
      } else {
        setErr("We couldn't confirm the payment yet. If you completed it, please wait a moment and tap Check again.");
      }
    } finally {
      setLoading(false);
    }
  };

  const pay = async () => {
    setErr(null);
    if (!termsAccepted) {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning).catch(() => {});
      setErr("Please accept the Terms & Conditions before continuing.");
      return;
    }
    setLoading(true); setMomoStatus(null); setSuggestStripe(false);
    try {
      // Record the acceptance server-side BEFORE we take any money.
      try {
        await api("/legal/terms/accept", {
          method: "POST", auth: true,
          body: { version: terms.version, context: "subscribe" },
        });
      } catch (e) { /* non-fatal; keep going — the acceptance is still logged in the UI */ }

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
        if (isIOS) {
          // iOS: open in Safari (external browser), show "Return to app" prompt
          // and auto-verify when the app comes back to foreground.
          setAwaitingReturn({ provider: "paypal", subscriptionId: r.subscriptionId });
          await WebBrowser.openBrowserAsync(r.approveUrl, {
            presentationStyle: WebBrowser.WebBrowserPresentationStyle.FULL_SCREEN,
          }).catch(() => {
            // If WebBrowser isn't available, fall back to system browser.
            return RNLinking.openURL(r.approveUrl);
          });
          // When openBrowserAsync resolves, the sheet closed — try verifying immediately.
          try {
            const v = await api<{ status: string }>(`/billing/paypal/verify/${r.subscriptionId}`, { method: "POST", auth: true });
            if (v.status === "success") {
              const st = await syncSubscriptionFromBackend();
              if (st?.active) {
                Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
                setSuccess(true);
                setAwaitingReturn(null);
                return;
              }
            }
          } catch { /* keep awaitingReturn — AppState listener will retry */ }
          return;
        }
        // Web + Android → in-app WebView
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
        } else if (isIOS) {
          // iOS: open in Safari (external browser). AppState listener + poll
          // together re-sync from backend as soon as the user returns.
          setAwaitingReturn({ provider: "stripe", sessionId: r.sessionId });
          const p = pollStripe(r.sessionId);
          await WebBrowser.openBrowserAsync(r.checkoutUrl, {
            presentationStyle: WebBrowser.WebBrowserPresentationStyle.FULL_SCREEN,
          }).catch(() => RNLinking.openURL(r.checkoutUrl));
          await p;
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
      throw new Error("This payment method is not available right now. Please try another.");
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
  const rwfPrice: Record<string, number> = {
    basic_monthly: 1000, basic_yearly: 10000, premium_monthly: 3000, premium_yearly: 30000,
  };
  // Fallback resolves NaN when amount route param is missing or non-numeric.
  const parsedAmount = Number(amount);
  const safeRwfAmount = Number.isFinite(parsedAmount) && parsedAmount > 0
    ? parsedAmount
    : (rwfPrice[String(plan)] || 0);
  const safeEurAmount = eurPrice[String(plan)] || "0.00";
  const isCardMethod = method === "paypal" || method === "stripe";
  const isPayPal = method === "paypal";
  const displayCurrency = isCardMethod ? "EUR" : "RWF";
  const displayAmount = isCardMethod ? safeEurAmount : safeRwfAmount.toLocaleString();
  // Parallel: always show both
  const parallelText = isCardMethod
    ? `≈ ${safeRwfAmount.toLocaleString()} RWF via Mobile Money`
    : `≈ ${safeEurAmount} EUR via Card / PayPal`;

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1, backgroundColor: colors.surface }}>
      {/* Return-to-app prompt shown while an external Safari/Chrome payment is in progress. */}
      <Modal transparent visible={!!awaitingReturn && !success} animationType="fade" onRequestClose={() => { /* stay open until reconciled or manually dismissed */ }}>
        <View style={styles.awaitOverlay}>
          <View style={styles.awaitCard}>
            <Ionicons name="hourglass-outline" size={44} color={colors.brandPrimary} />
            <Text style={styles.awaitTitle}>Complete payment in your browser</Text>
            <Text style={styles.awaitBody}>
              Your browser has opened {awaitingReturn?.provider === "paypal" ? "PayPal" : "Stripe"}.
              Finish the payment there, then return to this app — we&apos;ll unlock your subscription automatically.
            </Text>
            <Pressable onPress={manualCheckReturn} style={styles.awaitBtn} testID="awaiting-check">
              {loading ? <ActivityIndicator color={colors.onBrandPrimary} /> : <Text style={styles.awaitBtnText}>I&apos;VE COMPLETED PAYMENT — CHECK NOW</Text>}
            </Pressable>
            <Pressable onPress={() => { setAwaitingReturn(null); setErr(null); }} style={styles.awaitCancel}>
              <Text style={styles.awaitCancelText}>Cancel</Text>
            </Pressable>
          </View>
        </View>
      </Modal>

      <>
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

        {/* Terms & Conditions gate — required before any payment can be initiated */}
        <Pressable
          onPress={() => setTermsAccepted((v) => !v)}
          style={[styles.termsRow, termsAccepted && styles.termsRowActive]}
          testID="terms-checkbox"
        >
          <View style={[styles.termsBox, termsAccepted && styles.termsBoxChecked]}>
            {termsAccepted && <Ionicons name="checkmark" size={16} color={colors.onBrandPrimary} />}
          </View>
          <Text style={styles.termsLabel}>
            I have read and accept the{" "}
            <Text style={styles.termsLink} onPress={() => {
              const u = terms.url; if (u) Platform.OS === "web" ? window.open(u, "_blank") : import("expo-linking").then((L) => L.openURL(u));
            }}>Terms & Conditions</Text>
            {" "}and{" "}
            <Text style={styles.termsLink} onPress={() => {
              const u = terms.privacyUrl; if (u) Platform.OS === "web" ? window.open(u, "_blank") : import("expo-linking").then((L) => L.openURL(u));
            }}>Privacy Policy</Text>
            . I understand I am buying{" "}
            <Text style={{ fontWeight: "700" }}>
              {String(plan || "").replace("_", " ").toUpperCase()} — {displayAmount} {displayCurrency}
            </Text>
            . Access lasts exactly the plan period; expires automatically.
          </Text>
        </Pressable>
      </ScrollView>

      <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.md }]}>
        <Pressable
          onPress={pay}
          disabled={loading || !termsAccepted}
          style={[styles.payBtn, (loading || !termsAccepted) && { opacity: 0.4 }]}
          testID="pay-btn"
        >
          {loading ? <ActivityIndicator color="#000" /> : (
            <>
              <Ionicons name="lock-closed" size={18} color="#000" />
              <Text style={styles.payText}>
                {termsAccepted ? `PAY ${displayAmount} ${displayCurrency}` : "ACCEPT TERMS TO PAY"}
              </Text>
            </>
          )}
        </Pressable>
      </View>
      </>
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
  // Terms & Conditions checkbox row
  termsRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: spacing.sm,
    marginTop: spacing.xl,
    padding: spacing.md,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    borderWidth: 1.5,
    borderColor: colors.border,
  },
  termsRowActive: { borderColor: colors.brandPrimary },
  termsBox: {
    width: 22, height: 22, borderRadius: 4,
    borderWidth: 2, borderColor: colors.onSurfaceSecondary,
    alignItems: "center", justifyContent: "center",
    marginTop: 2,
  },
  termsBoxChecked: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  termsLabel: { ...type.caption, flex: 1, color: colors.onSurface, lineHeight: 16 },
  termsLink: { color: colors.brandPrimary, textDecorationLine: "underline", fontWeight: "600" },
  successWrap: { flex: 1, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center", padding: spacing.xl, gap: spacing.md },
  successIcon: { width: 100, height: 100, borderRadius: 50, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", marginBottom: spacing.lg },
  successTitle: { ...type.displayXL, letterSpacing: 2 },
  successSub: { ...type.bodyMuted, textAlign: "center", marginBottom: spacing.xl, lineHeight: 22 },
  doneBtn: { backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.xxl, paddingVertical: spacing.md, borderRadius: radius.pill },
  doneText: { ...type.h2, color: colors.onBrandPrimary, letterSpacing: 1.5, fontSize: 14 },
  // iOS App Store 3.1.1 compliance gate
  iosGate: { flex: 1, backgroundColor: colors.surface },
  iosGateBody: { padding: spacing.xl, gap: spacing.lg, alignItems: "center", paddingBottom: 80 },
  iosGateIconWrap: { width: 80, height: 80, borderRadius: 40, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center", marginTop: spacing.lg, borderWidth: 1, borderColor: colors.border },
  iosGateTitle: { ...type.h1, letterSpacing: 1.2, fontSize: 22, textAlign: "center", marginTop: spacing.md },
  iosGateSub: { ...type.bodyMuted, textAlign: "center", lineHeight: 22, fontSize: 14, paddingHorizontal: spacing.sm },
  iosGateFeatureCard: { width: "100%", backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.lg, borderWidth: 1, borderColor: colors.border, gap: 10 },
  iosGateFeatureTitle: { ...type.h2, fontSize: 14, marginBottom: 4, color: colors.onSurface },
  iosGateFeatureRow: { flexDirection: "row", alignItems: "center", gap: 8 },
  iosGateFeatureText: { ...type.body, fontSize: 13, color: colors.onSurface, flex: 1 },
  iosGateBtn: { backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.xxl, paddingVertical: spacing.md, borderRadius: radius.pill, marginTop: spacing.md },
  iosGateBtnText: { ...type.h2, color: "#000", letterSpacing: 1.8, fontSize: 15, fontFamily: "BarlowCondensed-Bold" },
  // Return-to-app prompt shown while external Safari/Chrome payment is in progress.
  awaitOverlay: { flex: 1, backgroundColor: "rgba(0,0,0,0.85)", alignItems: "center", justifyContent: "center", padding: spacing.lg },
  awaitCard: { width: "100%", maxWidth: 380, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.xl, alignItems: "center", gap: spacing.md, borderWidth: 1, borderColor: colors.border },
  awaitTitle: { ...type.h1, fontSize: 20, textAlign: "center" },
  awaitBody: { ...type.body, textAlign: "center", color: colors.onSurfaceTertiary, lineHeight: 20 },
  awaitBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.xl, paddingVertical: spacing.md, borderRadius: radius.pill, minHeight: 48 },
  awaitBtnText: { ...type.h2, color: colors.onBrandPrimary, letterSpacing: 1.2, fontSize: 12, textAlign: "center" },
  awaitCancel: { paddingVertical: spacing.sm },
  awaitCancelText: { ...type.caption, color: colors.onSurfaceSecondary, textDecorationLine: "underline" },
});
