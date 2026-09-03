import { Stack, useRouter, useSegments } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import { useEffect } from "react";
import { LogBox, Text as RNText, TextInput as RNTextInput, View } from "react-native";
import { useFonts } from "expo-font";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { StatusBar } from "expo-status-bar";

import { useIconFonts } from "@/src/hooks/use-icon-fonts";
import { useGlobalScreenCaptureBlock } from "@/src/hooks/use-screen-capture-guard";
import { AuthProvider, useAuth } from "@/src/context/auth";
import { PlayerProvider } from "@/src/context/player";
import { ErrorBoundary } from "@/src/components/ErrorBoundary";
import { colors } from "@/src/theme";
import { DesktopHeader } from "@/src/components/DesktopHeader";
import {
  AppQueryClientProvider,
  SubscriptionProvider,
  initializeRevenueCat,
} from "@/src/lib/revenuecat";

LogBox.ignoreAllLogs(true);
// Wrap in try/catch — on iOS TestFlight, if SplashScreen native module isn't
// initialised at this exact millisecond (rare race on React 19), the Promise
// rejects and would otherwise show as an unhandled promise warning and, on
// some devices, freeze the JS bridge. We ignore because if it's already
// hidden or not yet available, we don't care.
try {
  SplashScreen.preventAutoHideAsync().catch(() => { /* ignore */ });
} catch { /* module not ready — splash will auto-hide */ }

// Global font default — makes Poppins the base font for every <Text> and
// <TextInput> across the app without touching each individual style. Any
// explicit fontFamily set on a component still wins.
(RNText as any).defaultProps = (RNText as any).defaultProps || {};
(RNText as any).defaultProps.style = [
  { fontFamily: "Poppins-Regular" },
  (RNText as any).defaultProps.style,
];
(RNTextInput as any).defaultProps = (RNTextInput as any).defaultProps || {};
(RNTextInput as any).defaultProps.style = [
  { fontFamily: "Poppins-Regular" },
  (RNTextInput as any).defaultProps.style,
];

// Module-scope: RevenueCat SDK must initialize exactly once before any
// component renders. If keys are missing or the SDK is unavailable we log a
// warning and continue — the paywall handles the "unavailable" fallback state.
try {
  initializeRevenueCat();
} catch (err) {
  console.warn("RevenueCat unavailable:", err);
}

function AuthGate({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const segments = useSegments();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    const seg0 = segments[0] as string | undefined;
    const inAuth = seg0 === "auth";
    const inOnboarding = seg0 === "onboarding";
    // Screens that REQUIRE an authenticated user (paying/admin/private).
    // Public browsing (tabs, video preview, program details, paywall CTA) is now open to guests.
    const requiresAuth =
      seg0 === "admin" ||
      seg0 === "checkout" ||
      seg0 === "player";

    if (!user && requiresAuth) {
      // Send guest through the fast phone-login flow, then bounce back.
      router.replace("/auth/phone");
      return;
    }
    if (user && (inAuth || inOnboarding)) {
      router.replace("/(tabs)");
    }
    if (!user && !seg0) {
      // Cold-start to landing tabs so listeners immediately see the content.
      router.replace("/(tabs)");
    }
  }, [user, loading, segments, router]);

  return <>{children}</>;
}

export default function RootLayout() {
  useGlobalScreenCaptureBlock();
  const [iconsLoaded, iconsError] = useIconFonts();
  const [fontsLoaded, fontsError] = useFonts({
    "Poppins-Regular": require("../assets/fonts/Poppins-Regular.ttf"),
    "Poppins-Medium": require("../assets/fonts/Poppins-Medium.ttf"),
    "Poppins-SemiBold": require("../assets/fonts/Poppins-SemiBold.ttf"),
    "Poppins-Bold": require("../assets/fonts/Poppins-Bold.ttf"),
    // Legacy aliases — keeps any pre-existing fontFamily references working
    // while we transition the whole app to Poppins.
    "BarlowCondensed-Bold": require("../assets/fonts/Poppins-Bold.ttf"),
    "BarlowCondensed-Medium": require("../assets/fonts/Poppins-SemiBold.ttf"),
  });

  // iOS TestFlight hardening: on cold start we MUST unblock the render tree
  // as quickly as possible. Previously we `return null` while fonts loaded
  // AND kept the splash up until they resolved — if either useFonts hook
  // stalled on iOS (which we've seen happen in TestFlight builds when the
  // .ttf asset resolver races against React 19 concurrent rendering) the app
  // hung on the splash forever. Now:
  //   * The tree ALWAYS mounts (no more `return null`).
  //   * The splash is force-hidden after 3 seconds regardless of font state,
  //     so a stalled font load never traps the user on a black screen.
  useEffect(() => {
    if ((iconsLoaded || iconsError) && (fontsLoaded || fontsError)) {
      SplashScreen.hideAsync().catch(() => { /* already hidden */ });
    }
  }, [iconsLoaded, iconsError, fontsLoaded, fontsError]);

  useEffect(() => {
    // Absolute safety net — after 3s, kill the splash no matter what.
    const t = setTimeout(() => {
      SplashScreen.hideAsync().catch(() => { /* already hidden */ });
    }, 3000);
    return () => clearTimeout(t);
  }, []);

  return (
    <GestureHandlerRootView style={{ flex: 1, backgroundColor: colors.surface }}>
      <SafeAreaProvider>
        <ErrorBoundary>
          <AppQueryClientProvider>
            <AuthProvider>
              <SubscriptionProvider>
                <PlayerProvider>
                  <StatusBar style="light" />
                  <AuthGate>
                    <DesktopHeader />
                    <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.surface } }}>
                      <Stack.Screen name="index" />
                      <Stack.Screen name="onboarding" />
                      <Stack.Screen name="auth/phone" />
                      <Stack.Screen name="auth/otp" />
                      <Stack.Screen name="(tabs)" />
                      <Stack.Screen name="player" options={{ presentation: "modal" }} />
                      <Stack.Screen name="video/[id]" />
                      <Stack.Screen name="paywall" options={{ presentation: "modal" }} />
                      <Stack.Screen name="checkout" options={{ presentation: "modal" }} />
                      <Stack.Screen name="admin/index" />
                      <Stack.Screen name="admin/settings" />
                      <Stack.Screen name="admin/programs" />
                      <Stack.Screen name="admin/shows" />
                      <Stack.Screen name="admin/categories" />
                      <Stack.Screen name="admin/users" />
                      <Stack.Screen name="admin/sms" />
                      <Stack.Screen name="admin/payments" />
                      <Stack.Screen name="admin/schedule" />
                    <Stack.Screen name="admin/live-shows" />
                    <Stack.Screen name="admin/youtube-config" />
                    <Stack.Screen name="admin/cloudflare-stream" />
                    <Stack.Screen name="live" options={{ presentation: "fullScreenModal" }} />
                      <Stack.Screen name="live-news" options={{ presentation: "modal" }} />
                      <Stack.Screen name="program/[id]" />
                    </Stack>
                  </AuthGate>
                </PlayerProvider>
              </SubscriptionProvider>
            </AuthProvider>
          </AppQueryClientProvider>
        </ErrorBoundary>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}
