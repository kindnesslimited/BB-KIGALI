/**
 * Desktop-only top navigation bar.
 *
 * Rendered ONLY when running on web AND the viewport is wide enough
 * (≥ 1024 px). On mobile we keep the bottom tab bar.
 *
 * It never navigates via `router.replace()` from inside a link — that
 * would break browser back/forward. Uses `router.push` so history works
 * exactly like a normal desktop website.
 */
import React from "react";
import { View, Text, Pressable, StyleSheet, useWindowDimensions, Platform } from "react-native";
import { useRouter, usePathname } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { colors, spacing, type, radius } from "@/src/theme";
import { useAuth } from "@/src/context/auth";

type NavItem = { label: string; href: string; match: (p: string) => boolean };

const NAV: NavItem[] = [
  { label: "Home",     href: "/(tabs)",       match: (p) => p === "/" || p === "/(tabs)" },
  { label: "Shows",    href: "/(tabs)/shows", match: (p) => p.startsWith("/shows") || p.startsWith("/(tabs)/shows") },
  { label: "News",     href: "/(tabs)/news",  match: (p) => p.startsWith("/news") || p.startsWith("/(tabs)/news") },
  { label: "Schedule", href: "/(tabs)",       match: () => false }, // schedule is on the home page
];

export function useDesktopHeaderVisible() {
  const { width } = useWindowDimensions();
  return Platform.OS === "web" && width >= 1024;
}

export function DesktopHeader() {
  const visible = useDesktopHeaderVisible();
  const router = useRouter();
  const pathname = usePathname();
  const { user } = useAuth();

  if (!visible) return null;

  return (
    <View style={styles.wrap} testID="desktop-header">
      <View style={styles.inner}>
        {/* Brand — always links to home */}
        <Pressable onPress={() => router.push("/(tabs)")} style={styles.brand} testID="nav-brand">
          <View style={styles.brandMark}>
            <Text style={styles.brandMarkText}>B&B</Text>
          </View>
          <View>
            <Text style={styles.brandTitle}>BB FM KIGALI</Text>
            <Text style={styles.brandTagline}>89.7 FM · MURI SPORTS, NI IGITEGO!</Text>
          </View>
        </Pressable>

        {/* Center menu */}
        <View style={styles.menu}>
          {NAV.map((item) => {
            const active = item.match(pathname || "");
            return (
              <Pressable
                key={item.href}
                onPress={() => router.push(item.href as any)}
                style={styles.menuItem}
                testID={`nav-${item.label.toLowerCase()}`}
              >
                <Text style={[styles.menuText, active && styles.menuActive]}>{item.label}</Text>
                {active ? <View style={styles.menuUnderline} /> : null}
              </Pressable>
            );
          })}
        </View>

        {/* Right side actions */}
        <View style={styles.actions}>
          <Pressable
            onPress={() => router.push("/paywall")}
            style={styles.subscribeBtn}
            testID="nav-subscribe"
          >
            <Ionicons name="star" size={14} color={colors.onBrandPrimary} />
            <Text style={styles.subscribeText}>SUBSCRIBE</Text>
          </Pressable>
          {user ? (
            <Pressable
              onPress={() => router.push("/(tabs)/profile")}
              style={styles.profileBtn}
              testID="nav-profile"
            >
              <View style={styles.avatar}>
                <Ionicons name="person" size={16} color={colors.onSurface} />
              </View>
              <Text style={styles.profileName} numberOfLines={1}>
                {user.displayName || user.phone || "Account"}
              </Text>
            </Pressable>
          ) : (
            <Pressable
              onPress={() => router.push("/auth/phone")}
              style={styles.loginBtn}
              testID="nav-login"
            >
              <Ionicons name="log-in-outline" size={16} color={colors.onSurface} />
              <Text style={styles.loginText}>LOG IN</Text>
            </Pressable>
          )}
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    backgroundColor: colors.surface,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
    zIndex: 100,
    // web-only sticky top
    ...(Platform.OS === "web"
      ? ({ position: "sticky" as any, top: 0 })
      : {}),
  },
  inner: {
    width: "100%",
    maxWidth: 1200,
    alignSelf: "center",
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    gap: spacing.xl,
  },
  brand: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  brandMark: {
    backgroundColor: colors.brandPrimary,
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 6,
  },
  brandMarkText: { color: colors.onBrandPrimary, fontWeight: "800", fontSize: 14, letterSpacing: 0.5 },
  brandTitle: { color: colors.onSurface, fontWeight: "800", fontSize: 15, letterSpacing: 1 },
  brandTagline: { color: colors.onSurfaceSecondary, fontSize: 10, letterSpacing: 0.4, marginTop: 1 },
  menu: { flexDirection: "row", alignItems: "center", flex: 1, gap: spacing.xl, justifyContent: "center" },
  menuItem: { paddingVertical: 4 },
  menuText: { ...type.body, fontSize: 14, fontWeight: "600", color: colors.onSurfaceSecondary, letterSpacing: 0.4 },
  menuActive: { color: colors.onSurface },
  menuUnderline: { position: "absolute", left: 0, right: 0, bottom: -6, height: 2, backgroundColor: colors.brandPrimary, borderRadius: 1 },
  actions: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  subscribeBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing.md,
    paddingVertical: 8,
    borderRadius: radius.pill,
  },
  subscribeText: { ...type.caption, color: colors.onBrandPrimary, fontWeight: "700", letterSpacing: 1 },
  loginBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingHorizontal: spacing.md,
    paddingVertical: 8,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
  },
  loginText: { ...type.caption, color: colors.onSurface, fontWeight: "600", letterSpacing: 1 },
  profileBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    paddingHorizontal: spacing.md,
    paddingVertical: 6,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
    maxWidth: 200,
  },
  avatar: {
    width: 24,
    height: 24,
    borderRadius: 12,
    backgroundColor: colors.surfaceSecondary,
    alignItems: "center",
    justifyContent: "center",
  },
  profileName: { ...type.caption, color: colors.onSurface, fontWeight: "600" },
});
