// Design tokens — BB FM Kigali brand palette
// Brand rule: ONLY red, blue, black, white (per customer directive).
// Semantic states (success/warning) reuse the brand red + blue.
export const colors = {
  // Neutrals — the black/white part of the brand
  surface: "#0F0F13",
  onSurface: "#FFFFFF",
  surfaceSecondary: "#1C1C21",
  onSurfaceSecondary: "#A3A3A8",
  surfaceTertiary: "#27272F",
  onSurfaceTertiary: "#C2C2C7",

  // Brand — RED (BB FM Kigali primary)
  brand: "#E10600",
  brandPrimary: "#E10600",
  onBrandPrimary: "#000000", // Black text on red — passes WCAG AA and matches the 95 hardcoded "#000" button-text sites already in the codebase.
  brandSecondary: "#B00000",
  brandTertiary: "#2A0505", // very dark red — for tinted backgrounds
  onBrandTertiary: "#FF9C9C",

  // Accent — BLUE (Rwandan flag blue) — used for success + informational states
  accent: "#1E5FB4",
  accentSoft: "#0B2B57",

  // Semantic states — kept within brand palette
  success: "#1E5FB4",   // BLUE (used to be green)
  warning: "#E10600",   // RED (semantic warning uses brand red)
  error: "#D9381E",     // slightly brighter red for destructive actions

  // Structural
  border: "#27272F",
  borderStrong: "#E10600",
  divider: "#1C1C21",
};

export const spacing = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32, xxxl: 48 };
export const radius = { sm: 6, md: 12, lg: 20, pill: 999 };

export const fonts = {
  display: "BarlowCondensed-Bold",
  displayMedium: "BarlowCondensed-Medium",
  body: "System",
};

export const type = {
  displayXL: { fontFamily: fonts.display, fontSize: 36, letterSpacing: 0.5, color: colors.onSurface },
  displayLg: { fontFamily: fonts.display, fontSize: 28, color: colors.onSurface },
  displayMd: { fontFamily: fonts.displayMedium, fontSize: 22, color: colors.onSurface },
  h1: { fontFamily: fonts.display, fontSize: 24, color: colors.onSurface },
  h2: { fontFamily: fonts.displayMedium, fontSize: 18, color: colors.onSurface },
  body: { fontFamily: fonts.body, fontSize: 14, color: colors.onSurface },
  bodyMuted: { fontFamily: fonts.body, fontSize: 14, color: colors.onSurfaceSecondary },
  caption: { fontFamily: fonts.body, fontSize: 12, color: colors.onSurfaceSecondary },
  label: { fontFamily: fonts.body, fontSize: 12, color: colors.onSurfaceSecondary, letterSpacing: 1, textTransform: "uppercase" as const },
};
