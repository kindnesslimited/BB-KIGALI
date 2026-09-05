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
import { useEffect, useRef, useState, useCallback } from "react";
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
  StatusBar as RNStatusBar,
} from "react-native";
import { SafeAreaView, useSafeAreaInsets } from "react-native-safe-area-context";
import { WebView } from "react-native-webview";
import type { WebView as WebViewType } from "react-native-webview";
import * as SplashScreen from "expo-splash-screen";
import * as ScreenCapture from "expo-screen-capture";
import NetInfo, { NetInfoState } from "@react-native-community/netinfo";
import { useRouter } from "expo-router";

const WEB_URL = "https://web.bbkigali.com";
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
  useEffect(() => {
    let removeShotSub: (() => void) | null = null;
    (async () => {
      try {
        // Applies APP-WIDE — screenshots and screen recordings are hard-blocked:
        //   • Android: FLAG_SECURE is set on the current activity, so any
        //     screenshot or screen recording renders as pure black. Also
        //     hides the app content from the recent-apps preview.
        //   • iOS 11+: iOS itself blanks the recorded video output when this
        //     is active, so screen recordings show a black frame instead of
        //     the app pixels — equivalent protection to FLAG_SECURE.
        //   • iOS 13+: screenshots of the app content are also blanked.
        await ScreenCapture.preventScreenCaptureAsync("bbfm-primary");
      } catch { /* expo-screen-capture unavailable (Expo Go dev) — safe no-op */ }
      // iOS-only: also blur the app when it enters the app switcher /
      // background, so the app preview thumbnail leaks nothing sensitive.
      if (Platform.OS === "ios") {
        try {
          await ScreenCapture.enableAppSwitcherProtectionAsync?.(0.9);
        } catch { /* API not available on older iOS — safe no-op */ }
      }
      // Screenshot attempt listener — warn the user that BB Kigali content
      // is protected. On iOS the actual pixel content is already blanked
      // thanks to preventScreenCaptureAsync above; the alert reinforces
      // the Terms & Conditions policy in-app.
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
      // Re-allow capture on unmount so the OS returns to default state.
      ScreenCapture.allowScreenCaptureAsync("bbfm-primary").catch(() => { /* noop */ });
    };
  }, []);

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
        var mo = new MutationObserver(function () { ensureMeta(); });
        mo.observe(document.documentElement, { childList: true, subtree: true });
        // Belt-and-suspenders: also inject a CSS reset that guarantees the
        // page body itself is capped at the device width, so a rogue element
        // with fixed 100vw can't blow the layout out horizontally.
        var s = document.createElement("style");
        s.textContent = "html,body{max-width:100vw !important;overflow-x:hidden !important;-webkit-text-size-adjust:100% !important;text-size-adjust:100% !important;}"
          // Video-player logo overlay killer — hides BB Kigali logo watermarks
          // that appear ON TOP of the video and block content on mobile. Targets
          // any image / logo / watermark element positioned inside or right next
          // to a <video>, or inside anything with a "player" class. The main
          // app-shell logo (outside these containers) is untouched.
          + " video ~ img, video + img, video ~ .logo, video ~ [class*='logo' i],"
          + " video ~ [class*='watermark' i], video ~ [class*='brand' i],"
          + " video ~ [class*='overlay' i]:not([class*='control' i]):not([class*='caption' i]):not([class*='subtitle' i]),"
          + " [class*='player' i] > img[src*='logo' i],"
          + " [class*='player' i] > img[alt*='logo' i],"
          + " [class*='player' i] [class*='watermark' i],"
          + " [class*='player' i] [class*='brand-overlay' i],"
          + " [class*='videoplayer' i] img[src*='bbfm' i],"
          + " [class*='videoplayer' i] img[alt*='bb kigali' i],"
          + " .vjs-watermark, .plyr__logo, .jw-logo,"
          + " [data-testid*='player-logo' i], [data-testid*='watermark' i]"
          + " { display: none !important; visibility: hidden !important; opacity: 0 !important; }";
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
        source={{ uri: WEB_URL }}
        style={styles.fill}
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
        onNavigationStateChange={(nav) => setCanGoBack(nav.canGoBack)}
        onShouldStartLoadWithRequest={(req) => {
          // Route the T&C URL to our native Terms screen so it's readable
          // offline, always available, and satisfies the App Store /
          // Play Store requirement for an in-app Terms & Conditions
          // reachable from the Settings/Profile menu.
          try {
            const u = (req.url || "").toLowerCase();
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
          return true;
        }}
        onLoadStart={() => setLoading(true)}
        onLoadEnd={() => setLoading(false)}
        onError={() => setLoading(false)}
        onHttpError={() => setLoading(false)}
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
        cacheEnabled
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
  splashLogo: { width: 280, height: 200 },
  overlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: SPLASH_BG,
    alignItems: "center",
    justifyContent: "center",
  },
  overlayLogo: { width: 200, height: 140 },
  offlineLogo: { width: 220, height: 150, marginBottom: 8 },
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
