import React from "react";
import { View, Text, StyleSheet, Pressable, ScrollView } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { colors, spacing, type, radius } from "@/src/theme";

type State = { hasError: boolean; error?: Error };

export class ErrorBoundary extends React.Component<{ children: React.ReactNode }, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    // eslint-disable-next-line no-console
    console.log("[error-boundary]", error?.message, info?.componentStack);
  }

  handleRestart = () => {
    this.setState({ hasError: false, error: undefined });
  };

  render() {
    if (!this.state.hasError) return this.props.children;
    return (
      <View style={styles.wrap}>
        <ScrollView contentContainerStyle={styles.body}>
          <View style={styles.iconCircle}>
            <Ionicons name="alert-circle" size={48} color={colors.error} />
          </View>
          <Text style={styles.title}>SOMETHING WENT WRONG</Text>
          <Text style={styles.sub}>
            The app hit an unexpected error. Please tap the button below to reload — your session is safe.
          </Text>
          {__DEV__ && this.state.error?.message && (
            <View style={styles.errBox}>
              <Text style={styles.errText}>{this.state.error.message}</Text>
            </View>
          )}
          <Pressable style={styles.btn} onPress={this.handleRestart} testID="error-boundary-reload">
            <Ionicons name="refresh" size={18} color="#000" />
            <Text style={styles.btnText}>RELOAD APP</Text>
          </Pressable>
        </ScrollView>
      </View>
    );
  }
}

const styles = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: colors.surface },
  body: { flexGrow: 1, alignItems: "center", justifyContent: "center", padding: spacing.xl, gap: spacing.lg },
  iconCircle: { width: 84, height: 84, borderRadius: 42, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
  title: { ...type.h1, letterSpacing: 1.4, textAlign: "center", fontSize: 22 },
  sub: { ...type.bodyMuted, textAlign: "center", lineHeight: 20, fontSize: 14, maxWidth: 360 },
  errBox: { padding: spacing.md, borderRadius: radius.md, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, alignSelf: "stretch", maxHeight: 200 },
  errText: { ...type.caption, color: colors.onSurfaceSecondary, fontFamily: "Courier" },
  btn: { flexDirection: "row", alignItems: "center", gap: 8, backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.xxl, paddingVertical: spacing.md, borderRadius: radius.pill, marginTop: spacing.md },
  btnText: { color: "#000", fontFamily: "BarlowCondensed-Bold", letterSpacing: 1.5, fontSize: 15 },
});
