import { Stack } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import { LogBox } from "react-native";
import { StatusBar } from "expo-status-bar";
import { SafeAreaProvider } from "react-native-safe-area-context";

// Silence dev warnings — this is a WebView wrapper, all business logic lives
// on the web app at https://web.bbkigali.com.
LogBox.ignoreAllLogs(true);

// Keep the native splash screen up until the JS side takes over inside
// app/index.tsx. See BBSplash there for the 2-second brand hold.
try {
  SplashScreen.preventAutoHideAsync().catch(() => { /* ignore */ });
} catch { /* module not ready — splash will auto-hide */ }

export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <StatusBar style="dark" backgroundColor="#FFFFFF" />
      <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: "#FFFFFF" } }}>
        <Stack.Screen name="index" />
        <Stack.Screen
          name="terms"
          options={{ presentation: "modal", animation: "slide_from_bottom" }}
        />
      </Stack>
    </SafeAreaProvider>
  );
}
