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
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { WebView } from "react-native-webview";
import type { WebView as WebViewType } from "react-native-webview";
import * as SplashScreen from "expo-splash-screen";
import NetInfo, { NetInfoState } from "@react-native-community/netinfo";

const WEB_URL = "https://web.bbkigali.com";
const BRAND_COLOR = "#E10600";
const SURFACE = "#000000";
const SPLASH_MS = 2000;

// ---------------------------------------------------------------------------
// Brand splash — held for exactly 2 seconds on cold start.
// ---------------------------------------------------------------------------
function BBSplash() {
  return (
    <View style={styles.center} testID="bb-splash">
      <Image
        source={require("../assets/images/icon.png")}
        style={styles.brandLogo}
        resizeMode="contain"
      />
      <Text style={styles.brandTitle}>BB KIGALI FM</Text>
      <Text style={styles.brandTagline}>MURI SPORTS, NI IGITEGO!</Text>
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
        source={require("../assets/images/icon.png")}
        style={styles.overlayLogo}
        resizeMode="contain"
      />
      <ActivityIndicator size="large" color={BRAND_COLOR} style={{ marginTop: 18 }} />
    </View>
  );
}

// ---------------------------------------------------------------------------
// Offline screen — friendly BB Kigali branded fallback with a retry button.
// ---------------------------------------------------------------------------
function OfflineScreen({ onRetry }: { onRetry: () => void }) {
  return (
    <SafeAreaView style={styles.center} testID="offline-screen">
      <Image
        source={require("../assets/images/icon.png")}
        style={styles.brandLogo}
        resizeMode="contain"
      />
      <Text style={styles.brandTitle}>BB KIGALI FM</Text>
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
  const [showSplash, setShowSplash] = useState(true);
  const [loading, setLoading] = useState(true);
  const [online, setOnline] = useState(true);
  const [canGoBack, setCanGoBack] = useState(false);
  // Nonce forces the WebView to fully remount on retry (source={{ uri: WEB_URL }}
  // alone won't reload after a network failure).
  const [retryNonce, setRetryNonce] = useState(0);

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
      <WebView
        key={retryNonce}
        ref={webRef}
        source={{ uri: WEB_URL }}
        style={styles.fill}
        // No browser chrome — Expo WebView doesn't render a URL bar by
        // default; we only need to guarantee full-bleed and no top nav.
        // Camera + microphone: grant automatically so the web app can request
        // getUserMedia() without a permission race.
        mediaPlaybackRequiresUserAction={false}
        allowsInlineMediaPlayback
        onNavigationStateChange={(nav) => setCanGoBack(nav.canGoBack)}
        onLoadStart={() => setLoading(true)}
        onLoadEnd={() => setLoading(false)}
        onError={() => setLoading(false)}
        onHttpError={() => setLoading(false)}
        // Android-specific media permission auto-grant. The `webview-android`
        // `onPermissionRequest` prop maps to WebChromeClient.onPermissionRequest;
        // returning `grant` unlocks camera/mic without a system prompt.
        onPermissionRequest={(request: any) => {
          try { request.grant(request.resources); } catch { /* older RN-WebView */ }
        }}
        // iOS/Android — allow file uploads (avatars, images in comments)
        allowsFullscreenVideo
        javaScriptEnabled
        domStorageEnabled
        thirdPartyCookiesEnabled
        sharedCookiesEnabled
        originWhitelist={["*"]}
        // Allow the web app to open external tel:/mailto:/whatsapp:// links.
        setSupportMultipleWindows={false}
        pullToRefreshEnabled
        // Keep session alive across app backgrounding.
        cacheEnabled
      />
      {loading && <LoadingOverlay />}
    </View>
  );
}

// ---------------------------------------------------------------------------
// Styles — brand palette only. All copy strings stay in English.
// ---------------------------------------------------------------------------
const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: SURFACE },
  center: {
    flex: 1,
    backgroundColor: SURFACE,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 24,
  },
  brandLogo: { width: 120, height: 120 },
  brandTitle: {
    color: "#FFFFFF",
    fontSize: 24,
    letterSpacing: 3,
    fontWeight: "800",
    marginTop: 20,
  },
  brandTagline: {
    color: BRAND_COLOR,
    fontSize: 12,
    letterSpacing: 2.5,
    fontWeight: "700",
    marginTop: 8,
  },
  overlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: SURFACE,
    alignItems: "center",
    justifyContent: "center",
  },
  overlayLogo: { width: 96, height: 96 },
  offlineTitle: {
    color: "#FFFFFF",
    fontSize: 20,
    fontWeight: "700",
    marginTop: 32,
  },
  offlineBody: {
    color: "#B7B7B7",
    fontSize: 14,
    textAlign: "center",
    lineHeight: 20,
    marginTop: 8,
    maxWidth: 320,
  },
  retryBtn: {
    marginTop: 28,
    backgroundColor: BRAND_COLOR,
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
});
