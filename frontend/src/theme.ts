// Design tokens from /app/design_guidelines.json
export const colors = {
  surface: "#0F0F13",
  onSurface: "#FFFFFF",
  surfaceSecondary: "#1C1C21",
  onSurfaceSecondary: "#A3A3A8",
  surfaceTertiary: "#27272F",
  onSurfaceTertiary: "#C2C2C7",
  brand: "#FF6B00",
  brandPrimary: "#FF6B00",
  onBrandPrimary: "#0B0400",
  brandSecondary: "#CC5500",
  brandTertiary: "#40220A",
  onBrandTertiary: "#FFB885",
  success: "#2E8B57",
  warning: "#DAA520",
  error: "#D9381E",
  border: "#27272F",
  borderStrong: "#FF6B00",
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
