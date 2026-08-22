/**
 * Global screen-capture guard for BB FM Kigali.
 *
 * Behavior per platform (expo-screen-capture v8):
 * - Android: fully blocks screenshots + screen recording via native FLAG_SECURE.
 * - iOS: cannot block screenshots at all (Apple restriction). We DO detect the
 *        moment a screenshot is taken and increment a warning counter so screens
 *        can render a "Screenshot detected — please don't share our content"
 *        banner. iOS 11+ live screen-recording detection is not exposed by
 *        this SDK version.
 * - Web: no-op (admin uses the web).
 */
import { useEffect, useState } from "react";
import { Platform } from "react-native";
import * as ScreenCapture from "expo-screen-capture";

/**
 * Called once at the root. Enables Android screenshot blocking for the lifetime
 * of the app. Also enables the iOS "app-switcher blur" so previews in the task
 * switcher are hidden.
 */
export function useGlobalScreenCaptureBlock() {
  useEffect(() => {
    if (Platform.OS === "web") return;
    let mounted = true;
    (async () => {
      try {
        await ScreenCapture.preventScreenCaptureAsync("bbfm-global");
      } catch { /* older devices — ignore */ }
      try {
        // Blur the preview shown in the iOS/Android task switcher (SDK 54+).
        if (typeof (ScreenCapture as any).enableAppSwitcherProtectionAsync === "function") {
          await (ScreenCapture as any).enableAppSwitcherProtectionAsync(50);
        }
      } catch { /* not available on all platforms */ }
      if (!mounted) {
        await ScreenCapture.allowScreenCaptureAsync("bbfm-global").catch(() => {});
      }
    })();
    return () => {
      mounted = false;
      ScreenCapture.allowScreenCaptureAsync("bbfm-global").catch(() => {});
    };
  }, []);
}

/**
 * Reactive counter that increments every time a screenshot is taken (iOS+Android).
 * Consumers can use it to show a toast/banner: "Screenshot detected — please respect
 * our content." On Android, screenshots are blocked so this rarely fires.
 */
export function useScreenshotDetected(): number {
  const [count, setCount] = useState(0);

  useEffect(() => {
    if (Platform.OS === "web") return;
    let sub: { remove: () => void } | undefined;
    try {
      sub = ScreenCapture.addScreenshotListener(() => setCount((c) => c + 1));
    } catch { /* not available in Expo Go */ }
    return () => sub?.remove();
  }, []);

  return count;
}
