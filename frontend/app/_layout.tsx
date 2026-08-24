import { Stack, useRouter, useSegments } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import { useEffect } from "react";
import { LogBox, View } from "react-native";
import { useFonts } from "expo-font";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { StatusBar } from "expo-status-bar";

import { useIconFonts } from "@/src/hooks/use-icon-fonts";
import { useGlobalScreenCaptureBlock } from "@/src/hooks/use-screen-capture-guard";
import { AuthProvider, useAuth } from "@/src/context/auth";
import { PlayerProvider } from "@/src/context/player";
import { colors } from "@/src/theme";

LogBox.ignoreAllLogs(true);
SplashScreen.preventAutoHideAsync();

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
    "BarlowCondensed-Bold": "https://cdn.jsdelivr.net/npm/@fontsource/barlow-condensed@5.0.13/files/barlow-condensed-latin-700-normal.woff",
    "BarlowCondensed-Medium": "https://cdn.jsdelivr.net/npm/@fontsource/barlow-condensed@5.0.13/files/barlow-condensed-latin-500-normal.woff",
  });

  useEffect(() => {
    if ((iconsLoaded || iconsError) && (fontsLoaded || fontsError)) SplashScreen.hideAsync();
  }, [iconsLoaded, iconsError, fontsLoaded, fontsError]);

  if ((!iconsLoaded && !iconsError) || (!fontsLoaded && !fontsError)) return null;

  return (
    <GestureHandlerRootView style={{ flex: 1, backgroundColor: colors.surface }}>
      <SafeAreaProvider>
        <AuthProvider>
          <PlayerProvider>
            <StatusBar style="light" />
            <AuthGate>
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
                <Stack.Screen name="live-news" options={{ presentation: "modal" }} />
                <Stack.Screen name="program/[id]" />
              </Stack>
            </AuthGate>
          </PlayerProvider>
        </AuthProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}
