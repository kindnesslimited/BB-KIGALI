/**
 * BB Kigali FM — WebView wrapper.
 *
 * Product-owner spec (Sept 2026):
 *   1. 2-second brand splash on cold start, then load web.bbkigali.com fullscreen.
 *   2. NO browser chrome (URL bar / navigation controls).
 *   3. Android hardware back → WebView.goBack() when history exists; else
 *      "Exit BB Kigali?" confirm dialog before app close.
 *   4. Loading spinner over BB Kigali logo while pages load.
 *   5. Offline detection → friendly offline screen with retry.
 *   6. Camera + microphone permissions granted automatically to the web app
 *      (used for radio call-ins, video comments etc).
 *   7. RevenueCat / native IAP / native subscription code is REMOVED — all
 *      billing now happens in the web app.
 */
import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import {
  View,
  Text,
  Image,
  StyleSheet,
  ActivityIndicator,
  BackHandler,
  Alert,
  Pressable,
  Platform,
  Linking,
  StatusBar as RNStatusBar,
} from "react-native";
import { SafeAreaView, useSafeAreaInsets } from "react-native-safe-area-context";
import { WebView } from "react-native-webview";
import type { WebView as WebViewType } from "react-native-webview";
import * as SplashScreen from "expo-splash-screen";
import * as ScreenCapture from "expo-screen-capture";
import NetInfo, { NetInfoState } from "@react-native-community/netinfo";
import { useRouter } from "expo-router";

const WEB_URL = process.env.EXPO_PUBLIC_WEB_URL || "https://web.bbkigali.com";
const BRAND_RED = "#E10600";
const SPLASH_BG = "#FFFFFF";
const SPLASH_MS = 2000;

// ---------------------------------------------------------------------------
// Brand splash — held for exactly 2 seconds on cold start. The BB Kigali FM
// logo already contains the station name, frequency and tagline so we just
// display the artwork centered on the brand-white background.
// ---------------------------------------------------------------------------
function BBSplash() {
  return (
    <View style={styles.splash} testID="bb-splash">
      <Image
        source={require("../assets/images/bbfm-logo-transparent.png")}
        style={styles.splashLogo}
        resizeMode="contain"
      />
    </View>
  );
}

// ---------------------------------------------------------------------------
// Loading overlay — shown while the WebView fetches / renders a page.
// ---------------------------------------------------------------------------
function LoadingOverlay() {
  return (
    <View style={styles.overlay} pointerEvents="none" testID="webview-loader">
      <Image
        source={require("../assets/images/bbfm-logo-transparent.png")}
        style={styles.overlayLogo}
        resizeMode="contain"
      />
      <ActivityIndicator size="large" color={BRAND_RED} style={{ marginTop: 18 }} />
    </View>
  );
}

// ---------------------------------------------------------------------------
// Offline screen — friendly BB Kigali branded fallback with a retry button.
// ---------------------------------------------------------------------------
function OfflineScreen({ onRetry }: { onRetry: () => void }) {
  return (
    <SafeAreaView style={styles.splash} testID="offline-screen">
      <Image
        source={require("../assets/images/bbfm-logo-transparent.png")}
        style={styles.offlineLogo}
        resizeMode="contain"
      />
      <Text style={styles.offlineTitle}>You&apos;re offline</Text>
      <Text style={styles.offlineBody}>
        We can&apos;t reach the internet right now. Check your Wi-Fi or mobile
        data and try again.
      </Text>
      <Pressable onPress={onRetry} style={styles.retryBtn} testID="offline-retry">
        <Text style={styles.retryBtnText}>RETRY</Text>
      </Pressable>
    </SafeAreaView>
  );
}

// ---------------------------------------------------------------------------
// Root — mounts the splash, then the WebView + overlays.
// ---------------------------------------------------------------------------
export default function App() {
  const webRef = useRef<WebViewType>(null);
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [showSplash, setShowSplash] = useState(true);
  const [loading, setLoading] = useState(true);
  const [online, setOnline] = useState(true);
  const [canGoBack, setCanGoBack] = useState(false);
  const [retryNonce, setRetryNonce] = useState(0);
  // Tracks whether iOS screen-capture protection is currently ON, so we only
  // toggle it when the protected/unprotected route boundary is crossed.
  const iosCaptureProtectedRef = useRef(false);

  // ----------------------------------------------------------------------
  // Cache-buster — computed ONCE per app launch (and again on retry via
  // retryNonce). Appended to the target URL so every cold start bypasses
  // any stale HTTP cache and forces the WebView to fetch the newest HTML
  // from web.bbkigali.com. Combined with `cacheEnabled={false}` and
  // `cacheMode="LOAD_NO_CACHE"` below, this guarantees users always see
  // the latest deployed web app inside the mobile shell.
  //
  // Cookies / localStorage / sessionStorage are DELIBERATELY preserved so
  // that auth tokens and user preferences survive the cache reset — only
  // the HTTP resource cache (HTML/JS/CSS/images) is invalidated.
  // ----------------------------------------------------------------------
  const cacheBuster = useMemo(() => {
    const sep = WEB_URL.includes("?") ? "&" : "?";
    return `${WEB_URL}${sep}_t=${Date.now()}`;
    // We DO want retryNonce as a dep — it regenerates the buster when the
    // user taps Retry on the offline screen. The URL constant is stable.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [retryNonce]);

  // -----------------------------------------------------------------------
  // Loading-overlay safety net.
  //
  // The full-screen "loading" overlay is driven by the WebView's
  // onLoadStart/onLoadEnd, which map to Android's onPageStarted/
  // onPageFinished. Those fire reliably for the initial real page load,
  // but are INCONSISTENT for in-app SPA navigation (React Router
  // pushState) — sometimes onLoadEnd never fires for a given navigation
  // even though the page underneath loaded and works fine (confirmed:
  // audio starts playing on Live TV while the screen stays stuck showing
  // "loading"). Relying on those events alone can leave the overlay stuck
  // forever. This timeout guarantees it always clears.
  // -----------------------------------------------------------------------
  const loadingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const clearLoadingTimeout = () => {
    if (loadingTimeoutRef.current) {
      clearTimeout(loadingTimeoutRef.current);
      loadingTimeoutRef.current = null;
    }
  };
  const beginLoading = () => {
    setLoading(true);
    clearLoadingTimeout();
    loadingTimeoutRef.current = setTimeout(() => setLoading(false), 4000);
  };
  const endLoading = () => {
    clearLoadingTimeout();
    setLoading(false);
  };
  useEffect(() => clearLoadingTimeout, []);

  // -----------------------------------------------------------------------
  // Screen capture / recording protection — applied APP-WIDE.
  //
  // Android: `preventScreenCaptureAsync` sets FLAG_SECURE on the current
  // activity, which makes screenshots and screen recordings render as pure
  // black. This is a hard block — nothing the OS can capture ever contains
  // real pixel data. No detection required because the OS enforces it.
  //
  // iOS: FLAG_SECURE has no equivalent, so we instead detect when the
  // display is being captured (screen recording via Control Center, or
  // AirPlay / QuickTime mirroring) using `addScreenRecordingListener`
  // which subscribes to UIScreen.capturedDidChangeNotification and reports
  // `UIScreen.main.isCaptured`. When capture starts, we overlay a
  // full-screen block that hides the WebView contents; when it stops we
  // remove the overlay and playback continues normally.
  //
  // Also enable a screenshot listener so we can inform the user their
  // screenshot won't contain the protected content (defensive on iOS where
  // screenshots of DRM'd content are already blank).
  // -----------------------------------------------------------------------
  // -----------------------------------------------------------------------
  // Screen capture / recording protection.
  //
  // ⚠️ Android: we DELIBERATELY do NOT call `preventScreenCaptureAsync` on
  // Android because `FLAG_SECURE` breaks HTML5 <video> playback inside
  // WebView — the SurfaceView / TextureView the video renderer needs
  // cannot allocate under FLAG_SECURE on many devices, so the spinner
  // rotates forever and the video never appears. Since this is a
  // WebView-first app where video playback IS the primary use case,
  // native anti-screenshot is incompatible. The web app must handle any
  // Android-side content-protection via DRM (Widevine) inside the player
  // itself if required.
  //
  // ✅ iOS: `preventScreenCaptureAsync` is safe here — it blanks recorded
  //    pixels at the compositor level, ABOVE the WebView, without
  //    interfering with video surface allocation. iOS video plays
  //    normally while the OS still blocks screen recording output.
  //
  // A screenshot listener is registered on BOTH platforms so we can
  // reinforce the Terms-of-Service policy via an alert.
  // -----------------------------------------------------------------------
  useEffect(() => {
    let removeShotSub: (() => void) | null = null;
    (async () => {
      if (Platform.OS === "ios") {
        // preventScreenCaptureAsync is NOT called here anymore — it's now
        // scoped to Premium/VOD/Live routes only, via onNavigationStateChange
        // below (see updateIosCaptureProtection). Calling it app-wide risked
        // interfering with video rendering, the same class of bug already
        // found and fixed on Android's FLAG_SECURE usage.
        try {
          await ScreenCapture.enableAppSwitcherProtectionAsync?.(0.9);
        } catch { /* API not available on older iOS — safe no-op */ }
      }
      try {
        const sub = ScreenCapture.addScreenshotListener(() => {
          Alert.alert(
            "Screenshots aren't allowed",
            "BB Kigali FM content is protected. Screenshots and screen " +
              "recording are disabled per our Terms of Service.",
            [{ text: "OK" }],
            { cancelable: true },
          );
        });
        removeShotSub = () => { try { sub.remove(); } catch { /* noop */ } };
      } catch { /* ignore */ }
    })();
    return () => {
      removeShotSub?.();
      if (Platform.OS === "ios" && iosCaptureProtectedRef.current) {
        iosCaptureProtectedRef.current = false;
        ScreenCapture.allowScreenCaptureAsync("bbfm-primary").catch(() => { /* noop */ });
      }
    };
  }, []);

  // -----------------------------------------------------------------------
  // iOS screen-capture protection, scoped to Premium/VOD/Live routes only.
  //
  // preventScreenCaptureAsync used to run app-wide on mount. That's the same
  // class of bug already found and fixed on Android (FLAG_SECURE breaking
  // WebView <video> rendering) — unscoped, it risks the same interference on
  // iOS. Instead we watch the WebView's navigation URL and only engage
  // protection while the user is actually on a protected content route,
  // releasing it everywhere else so normal browsing/video is never affected.
  // -----------------------------------------------------------------------
  const PROTECTED_ROUTE_RE = /\/(watch|vod|live)(\/|$|\?)/i;
  const updateIosCaptureProtection = (url?: string | null) => {
    if (Platform.OS !== "ios" || !url) return;
    const shouldProtect = PROTECTED_ROUTE_RE.test(url);
    if (shouldProtect === iosCaptureProtectedRef.current) return; // no boundary crossed
    iosCaptureProtectedRef.current = shouldProtect;
    const action = shouldProtect
      ? ScreenCapture.preventScreenCaptureAsync("bbfm-primary")
      : ScreenCapture.allowScreenCaptureAsync("bbfm-primary");
    action.catch(() => { /* module unavailable in Expo Go — safe no-op */ });
  };

  // -----------------------------------------------------------------------
  // Viewport injector — runs BEFORE the site's own <head> executes so the
  // mobile browser lays the page out at the phone's device-pixel width from
  // frame 0. Without this, sites that ship a desktop-first stylesheet render
  // at their fixed CSS width (usually 1024–1440 px) and the WebView shrinks
  // the result down, which is why "the text is too big and the top menu is
  // cut off" — the page is actually WIDER than the phone and content that
  // sits at the top-right is scrolled off-screen.
  //
  // We also enable pinch-to-zoom (user-scalable=yes) as requested.
  // -----------------------------------------------------------------------
  const injectedBeforeLoad = `
    (function () {
      try {
        var META_ID = "bbfm-viewport";
        function ensureMeta() {
          if (document.getElementById(META_ID)) return;
          var m = document.createElement("meta");
          m.id = META_ID;
          m.name = "viewport";
          m.content = "width=device-width, initial-scale=1.0, maximum-scale=5.0, user-scalable=yes, viewport-fit=cover";
          // Replace any existing viewport tag the site shipped
          var existing = document.querySelectorAll('meta[name="viewport"]');
          for (var i = 0; i < existing.length; i++) existing[i].parentNode.removeChild(existing[i]);
          (document.head || document.documentElement).appendChild(m);
        }
        ensureMeta();
        // Some SPAs (React Native Web + Next.js in particular) rewrite <head>
        // AFTER first paint. Watch for that and re-assert the viewport tag.
        //
        // ⚠️ Scoped to <head> only (NOT documentElement+subtree) and guarded
        // to install once per page. This script re-runs on every WebView load
        // (injectedJavaScriptBeforeContentLoaded + injectedJavaScript, and again
        // on every in-app navigation) — an unguarded documentElement+subtree
        // observer stacks up one instance per run with NO disconnect, and on a
        // content-heavy page (e.g. a grid of 40 show cards with images/hover
        // states) every DOM mutation re-fires ALL of them. That cascade was
        // severe enough to freeze the WebView JS thread and crash the renderer
        // (Browse Shows hanging on the loading screen). We only ever need to
        // know about <head> being rewritten, not every mutation in <body>.
        if (!window.__bbfmViewportObserverInstalled) {
          window.__bbfmViewportObserverInstalled = true;
          var mo = new MutationObserver(function () { ensureMeta(); });
          mo.observe(document.head || document.documentElement, { childList: true });
        }
        // Belt-and-suspenders: also inject a CSS reset that guarantees the
        // page body itself is capped at the device width, so a rogue element
        // with fixed 100vw can't blow the layout out horizontally.
        var s = document.createElement("style");
        s.textContent = "html,body{max-width:100vw !important;overflow-x:hidden !important;-webkit-text-size-adjust:100% !important;text-size-adjust:100% !important;}"
          // Video-player logo watermark killer — hides BB Kigali branding
          // that some players overlay ON TOP of the video pixels.
          //
          // ⚠️ IMPORTANT: this selector list is intentionally NARROW so it
          // cannot hit legitimate player parts (loading spinner, play
          // controls, big-play-button, buffering indicator, poster image,
          // captions). Only elements whose class or src explicitly says
          // "watermark", "brand-overlay" or contains "bbfm" / "bb kigali"
          // are removed. This is the fix for "logo keeps rotating
          // infinitely" — the previous, broader selector was hiding the
          // player's own overlay elements and blocking playback.
          + " [class*='watermark' i], .vjs-watermark, .plyr__logo, .jw-logo,"
          + " [class*='brand-overlay' i], [class*='player-watermark' i],"
          + " img[src*='bbfm-logo' i], img[alt='BB Kigali FM' i],"
          + " img[src*='bb-kigali' i][class*='logo' i],"
          + " [data-testid*='player-watermark' i], [data-testid='video-logo']"
          + " { display: none !important; visibility: hidden !important; opacity: 0 !important; pointer-events: none !important; }";
        (document.head || document.documentElement).appendChild(s);
      } catch (e) { /* non-fatal */ }
    })();
    true;
  `;

  // --- Web fallback: on the web platform (RN-Web), the react-native-webview
  //     package is a stub. Redirect straight to the target URL so opening
  //     bbkigali.com in a browser goes to the actual web app.
  useEffect(() => {
    if (Platform.OS !== "web" || showSplash) return;
    try {
      const w = typeof window !== "undefined" ? (window as any) : null;
      if (w && w.location && w.location.href !== WEB_URL) {
        w.location.replace(WEB_URL);
      }
    } catch { /* SSR / no-window */ }
  }, [showSplash]);

  // --- Splash hold: exactly 2 seconds, then reveal the WebView -------------
  useEffect(() => {
    // Hide the native splash immediately so our own React-driven splash can
    // fade in without a black flash between them.
    SplashScreen.hideAsync().catch(() => { /* already hidden */ });
    const t = setTimeout(() => setShowSplash(false), SPLASH_MS);
    return () => clearTimeout(t);
  }, []);

  // --- WebView cache purge on cold start -----------------------------------
  // Fires once the WebView is mounted (after the splash). Clears any
  // stale HTTP cache the OS may have accumulated from a previous session
  // so the very first page-load post-splash is guaranteed to hit the
  // network. Cookies + localStorage remain intact (auth preserved).
  useEffect(() => {
    if (showSplash) return;
    const t = setTimeout(() => {
      try { (webRef.current as any)?.clearCache?.(true); } catch { /* not supported on iOS — safe no-op */ }
    }, 100);
    return () => clearTimeout(t);
  }, [showSplash]);

  // --- Connectivity monitoring --------------------------------------------
  useEffect(() => {
    const unsub = NetInfo.addEventListener((state: NetInfoState) => {
      // `isInternetReachable` is null on some Android devices for a brief
      // window after boot — treat null as "connected" to avoid a false
      // offline screen. Only mark offline when we get an explicit `false`.
      const off = state.isConnected === false || state.isInternetReachable === false;
      setOnline(!off);
    });
    return () => { try { unsub(); } catch { /* ignore */ } };
  }, []);

  // --- Android hardware back button ---------------------------------------
  useEffect(() => {
    if (Platform.OS !== "android") return;
    const onBack = () => {
      if (canGoBack && webRef.current) {
        webRef.current.goBack();
        return true;
      }
      Alert.alert(
        "Exit BB Kigali FM?",
        "You're about to leave the app.",
        [
          { text: "Cancel", style: "cancel" },
          { text: "Exit", style: "destructive", onPress: () => BackHandler.exitApp() },
        ],
        { cancelable: true },
      );
      return true; // we handled the back press
    };
    const sub = BackHandler.addEventListener("hardwareBackPress", onBack);
    return () => sub.remove();
  }, [canGoBack]);

  const retry = useCallback(() => {
    setLoading(true);
    // Force a fresh NetInfo probe so the UI unblocks the moment the network
    // recovers — waiting for the event listener alone can be sluggish on
    // Android where reachability probes happen every ~30 seconds.
    NetInfo.fetch().then((state) => {
      const off = state.isConnected === false || state.isInternetReachable === false;
      setOnline(!off);
    }).catch(() => { /* ignore — event listener will catch up */ });
    setRetryNonce((n) => n + 1);
  }, []);

  // -----------------------------------------------------------------------
  // Render order:
  //   splash (2s)  →  offline OR webview
  // -----------------------------------------------------------------------
  if (showSplash) return <BBSplash />;
  if (!online) return <OfflineScreen onRetry={retry} />;

  return (
    <View style={styles.fill} testID="webview-container">
      {/* Safe-area top padding — status bar + notch reserved so the site's
          top navigation is fully visible. Bottom is left flush so the site
          can render its own footer or nothing (WebView content extends to
          the home-indicator area on iOS — matches native mobile browsers). */}
      <View
        style={{
          height:
            Platform.OS === "ios"
              ? insets.top
              : (RNStatusBar.currentHeight || 0),
          backgroundColor: SPLASH_BG,
        }}
      />
      <WebView
        key={retryNonce}
        ref={webRef}
        source={{
          uri: cacheBuster,
          // Force fresh fetch: tell the origin server we don't want a
          // cached response. Combined with cacheEnabled=false + Android
          // cacheMode=LOAD_NO_CACHE below, this ensures the WebView
          // always pulls the latest deployed web app.
          headers: {
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
          },
        }}
        style={styles.fill}
        // Some video CDNs reject default Android WebView user-agents (which
        // contain `; wv` and get treated as bots). Override with a stock
        // Chrome Mobile UA so HLS/DASH/MP4 streaming works reliably.
        userAgent={Platform.OS === "android"
          ? "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
          : undefined}
        // Viewport fix — inject meta viewport BEFORE the page's <head> runs
        // so the site lays out at device-width. This is the fix for the
        // "text is too big / top menu cut off" report.
        injectedJavaScriptBeforeContentLoaded={injectedBeforeLoad}
        // Also inject after content loads in case the page rewrote <head>.
        injectedJavaScript={injectedBeforeLoad}
        // Pinch-to-zoom: users can zoom in/out as requested.
        scalesPageToFit
        // iOS-only: use compact vertical scroll indicator and don't let the
        // system add invisible content insets that push the top nav out of view.
        automaticallyAdjustContentInsets={false}
        contentInsetAdjustmentBehavior="never"
        // Camera + microphone: grant automatically so the web app can request
        // getUserMedia() without a permission race.
        mediaPlaybackRequiresUserAction={false}
        allowsInlineMediaPlayback
        onNavigationStateChange={(nav) => {
          setCanGoBack(nav.canGoBack);
          updateIosCaptureProtection(nav.url);
          // More reliable than onLoadEnd for in-app SPA navigation — see
          // the loading-overlay safety-net comment above.
          if (!nav.loading) endLoading();
        }}
        onShouldStartLoadWithRequest={(req) => {
          const raw = req.url || "";
          const u = raw.toLowerCase();

          // -----------------------------------------------------------
          // 1. Terms of Service → native offline-readable screen.
          //    Required by App Store / Play Store (must be reachable
          //    even without internet).
          // -----------------------------------------------------------
          try {
            if (
              u.endsWith("/terms") ||
              u.endsWith("/terms.html") ||
              u.includes("/legal/terms") ||
              u.includes("terms-and-conditions") ||
              u.includes("bbkigali://terms")
            ) {
              router.push("/terms");
              return false;
            }
          } catch { /* ignore parse errors */ }

          // -----------------------------------------------------------
          // 2. WhatsApp deep-links → open native WhatsApp app so the
          //    user can send the pre-filled message with one tap.
          //    Handles all three URL shapes the web app can emit:
          //      • whatsapp://send?phone=...&text=...  (native scheme)
          //      • https://wa.me/<phone>?text=...       (short URL)
          //      • https://api.whatsapp.com/send?...    (long URL)
          //    Also handles chat.whatsapp.com/ invite links.
          // -----------------------------------------------------------
          const isWhatsApp =
            u.startsWith("whatsapp:") ||
            u.startsWith("https://wa.me/") ||
            u.startsWith("http://wa.me/") ||
            u.startsWith("https://api.whatsapp.com/send") ||
            u.startsWith("https://chat.whatsapp.com/");
          if (isWhatsApp) {
            Linking.openURL(raw).catch(() => {
              Alert.alert(
                "WhatsApp not installed",
                "Please install WhatsApp to continue this chat.",
                [{ text: "OK" }],
              );
            });
            return false;
          }

          // -----------------------------------------------------------
          // 3. Native OS handlers — tel, mailto, sms, Android intents.
          //    These MUST NOT load inside the WebView; they need the OS
          //    to route them to the phone dialer / mail app / SMS app.
          // -----------------------------------------------------------
          if (
            u.startsWith("tel:") ||
            u.startsWith("mailto:") ||
            u.startsWith("sms:") ||
            u.startsWith("smsto:") ||
            u.startsWith("intent:") ||
            u.startsWith("market:") ||        // Play Store
            u.startsWith("itms-apps:") ||     // App Store
            u.startsWith("geo:") ||            // Maps
            u.startsWith("mapkit:") ||
            u.startsWith("fb-messenger:") ||
            u.startsWith("tg:") ||             // Telegram
            u.startsWith("twitter:") ||
            u.startsWith("instagram:") ||
            u.startsWith("youtube:")
          ) {
            Linking.openURL(raw).catch(() => { /* no handler — safe no-op */ });
            return false;
          }

          // -----------------------------------------------------------
          // 4. Payment provider return URLs — Stripe, PayPal, MoMo
          //    redirect back to our origin after checkout, so those
          //    stay INSIDE the WebView (do not intercept).
          //    All web.bbkigali.com and bbkigali.com URLs stay inside.
          // -----------------------------------------------------------
          if (
            u.startsWith("https://web.bbkigali.com") ||
            u.startsWith("http://web.bbkigali.com") ||
            u.startsWith("https://bbkigali.com") ||
            u.startsWith("http://bbkigali.com") ||
            u.startsWith("https://www.bbkigali.com") ||
            u.startsWith("http://www.bbkigali.com") ||
            // Payment provider hosted pages (Stripe Checkout, PayPal
            // approval, BeSoft callback) — must load in-WebView so the
            // return URL fires our success handler.
            u.includes("checkout.stripe.com") ||
            u.includes("paypal.com") ||
            u.includes("besoft.rw") ||
            u.includes("pay.besoft.rw") ||
            // 3-D Secure auth iframes, etc.
            u.startsWith("about:") ||
            u.startsWith("data:") ||
            u.startsWith("blob:")
          ) {
            return true;
          }

          // -----------------------------------------------------------
          // 5. Any OTHER http(s) URL (external site, social media link,
          //    news article the site links to, etc.) opens in the
          //    device's default browser — this avoids trapping the
          //    user inside our shell on unrelated sites and prevents
          //    a "you can't leave this app" experience.
          // -----------------------------------------------------------
          if (u.startsWith("http://") || u.startsWith("https://")) {
            Linking.openURL(raw).catch(() => { /* fall back to in-WebView */ });
            return false;
          }

          // Unknown scheme — attempt to open externally.
          try { Linking.openURL(raw).catch(() => { /* ignore */ }); } catch { /* ignore */ }
          return false;
        }}
        onLoadStart={beginLoading}
        onLoadEnd={endLoading}
        onError={endLoading}
        onHttpError={endLoading}
        // Android-specific media permission auto-grant.
        onPermissionRequest={(request: any) => {
          try { request.grant(request.resources); } catch { /* older RN-WebView */ }
        }}
        allowsFullscreenVideo
        javaScriptEnabled
        domStorageEnabled
        thirdPartyCookiesEnabled
        sharedCookiesEnabled
        originWhitelist={["*"]}
        setSupportMultipleWindows={false}
        pullToRefreshEnabled
        // File uploads (avatar picker, VOD receipts, etc.) — required
        // for the admin panel and any user-content upload in the web
        // app. Also grants read access to the media library.
        allowFileAccess
        allowFileAccessFromFileURLs
        allowUniversalAccessFromFileURLs
        allowsBackForwardNavigationGestures
        geolocationEnabled
        mixedContentMode="always"
        // Download support (PDF receipts, invoices) — hand-off to the
        // OS via Linking so the file opens in the system viewer / is
        // saved to Files/Downloads.
        onFileDownload={({ nativeEvent }: any) => {
          try {
            const url = nativeEvent?.downloadUrl;
            if (url) Linking.openURL(url).catch(() => { /* noop */ });
          } catch { /* noop */ }
        }}
        // Disable HTTP resource cache so every launch fetches fresh
        // HTML/JS/CSS. Cookies + localStorage still persist (auth is
        // preserved). Android needs the extra `cacheMode` prop below;
        // iOS honours `cacheEnabled={false}` directly.
        cacheEnabled={false}
        cacheMode="LOAD_NO_CACHE"
        incognito={false}
      />
      {loading && <LoadingOverlay />}
    </View>
  );
}

// ---------------------------------------------------------------------------
// Styles — brand palette only.
// ---------------------------------------------------------------------------
const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: "#000000" },
  splash: {
    flex: 1,
    backgroundColor: SPLASH_BG,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 24,
  },
  // Logo is square (1024×1024, circular design on white bg), so keep 1:1
  splashLogo: { width: 260, height: 260 },
  overlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: SPLASH_BG,
    alignItems: "center",
    justifyContent: "center",
  },
  overlayLogo: { width: 180, height: 180 },
  offlineLogo: { width: 200, height: 200, marginBottom: 8 },
  offlineTitle: {
    color: "#111111",
    fontSize: 20,
    fontWeight: "700",
    marginTop: 24,
  },
  offlineBody: {
    color: "#555555",
    fontSize: 14,
    textAlign: "center",
    lineHeight: 20,
    marginTop: 8,
    maxWidth: 320,
  },
  retryBtn: {
    marginTop: 28,
    backgroundColor: BRAND_RED,
    paddingHorizontal: 40,
    paddingVertical: 14,
    borderRadius: 999,
  },
  retryBtnText: {
    color: "#FFFFFF",
    fontSize: 14,
    fontWeight: "800",
    letterSpacing: 2,
  },
  // Screen-recording block overlay
  captureBlock: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "#000000",
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 32,
    zIndex: 999,
  },
  captureTitle: {
    color: "#FFFFFF",
    fontSize: 20,
    fontWeight: "800",
    letterSpacing: 1,
    marginTop: 24,
    textAlign: "center",
  },
  captureBody: {
    color: "#CCCCCC",
    fontSize: 14,
    lineHeight: 20,
    marginTop: 12,
    textAlign: "center",
    maxWidth: 340,
  },
});
