import { useState, useRef } from "react";
import { View, Text, StyleSheet, Pressable, Dimensions, FlatList, NativeSyntheticEvent, NativeScrollEvent } from "react-native";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import * as Haptics from "expo-haptics";
import { colors, spacing, type, radius } from "@/src/theme";

const { width, height } = Dimensions.get("window");

const SLIDES = [
  {
    key: "1",
    image: "https://images.unsplash.com/photo-1485579149621-3123dd979885?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjAzMjV8MHwxfHNlYXJjaHwxfHxsaXZlJTIwcmFkaW8lMjBtaWNyb3Bob25lJTIwZGFya3xlbnwwfHx8fDE3ODczMDcwNjF8MA&ixlib=rb-4.1.0&q=85",
    title: "TUNE INTO KIGALI",
    subtitle: "Stream BB FM live, 24/7 — anywhere in the world.",
  },
  {
    key: "2",
    image: "https://images.pexels.com/photos/26447525/pexels-photo-26447525.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
    title: "WATCH THE MOMENT",
    subtitle: "Exclusive VOD, concerts and behind-the-scenes videos.",
  },
  {
    key: "3",
    image: "https://images.pexels.com/photos/38586686/pexels-photo-38586686.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
    title: "PREMIUM PODCASTS",
    subtitle: "Subscribe to unlock every show, every interview.",
  },
];

export default function Onboarding() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [index, setIndex] = useState(0);
  const listRef = useRef<FlatList>(null);

  const onScroll = (e: NativeSyntheticEvent<NativeScrollEvent>) => {
    const i = Math.round(e.nativeEvent.contentOffset.x / width);
    if (i !== index) setIndex(i);
  };

  const next = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {});
    if (index < SLIDES.length - 1) {
      const nextIdx = index + 1;
      listRef.current?.scrollToOffset({ offset: nextIdx * width, animated: true });
      setIndex(nextIdx);
    } else {
      router.replace("/auth/phone");
    }
  };

  return (
    <View style={styles.container} testID="onboarding-screen">
      <FlatList
        ref={listRef}
        data={SLIDES}
        horizontal
        pagingEnabled
        showsHorizontalScrollIndicator={false}
        onScroll={onScroll}
        scrollEventThrottle={16}
        keyExtractor={(s) => s.key}
        renderItem={({ item }) => (
          <View style={{ width, height }}>
            <Image source={{ uri: item.image }} style={StyleSheet.absoluteFill} contentFit="cover" />
            <LinearGradient
              colors={["rgba(15,15,19,0)", "rgba(15,15,19,0.55)", colors.surface]}
              locations={[0, 0.5, 0.95]}
              style={StyleSheet.absoluteFill}
            />
          </View>
        )}
      />

      <View style={[styles.bottom, { paddingBottom: insets.bottom + spacing.xl }]}>
        <View style={styles.brandRow}>
          <View style={styles.liveDot} />
          <Text style={styles.brandLabel}>BB FM KIGALI</Text>
        </View>
        <Text style={styles.title} testID={`onboarding-title-${index}`}>{SLIDES[index].title}</Text>
        <Text style={styles.subtitle}>{SLIDES[index].subtitle}</Text>

        <View style={styles.dots}>
          {SLIDES.map((_, i) => (
            <View key={i} style={[styles.dot, i === index && styles.dotActive]} />
          ))}
        </View>

        <Pressable onPress={next} style={styles.cta} testID="onboarding-cta">
          <Text style={styles.ctaText}>{index === SLIDES.length - 1 ? "GET STARTED" : "NEXT"}</Text>
        </Pressable>
        <Pressable onPress={() => router.replace("/auth/phone")} testID="onboarding-skip">
          <Text style={styles.skip}>Skip</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  bottom: { position: "absolute", left: 0, right: 0, bottom: 0, paddingHorizontal: spacing.lg },
  brandRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginBottom: spacing.sm },
  liveDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.brandPrimary },
  brandLabel: { ...type.label, color: colors.brandPrimary, letterSpacing: 2 },
  title: { ...type.displayXL, marginBottom: spacing.sm },
  subtitle: { ...type.bodyMuted, marginBottom: spacing.lg, fontSize: 15, lineHeight: 22 },
  dots: { flexDirection: "row", gap: 6, marginBottom: spacing.lg },
  dot: { width: 6, height: 6, borderRadius: 3, backgroundColor: colors.surfaceTertiary },
  dotActive: { width: 24, backgroundColor: colors.brandPrimary },
  cta: { backgroundColor: colors.brandPrimary, height: 56, borderRadius: radius.md, alignItems: "center", justifyContent: "center", marginBottom: spacing.md },
  ctaText: { ...type.h2, color: colors.onBrandPrimary, letterSpacing: 1 },
  skip: { ...type.bodyMuted, textAlign: "center" },
});
