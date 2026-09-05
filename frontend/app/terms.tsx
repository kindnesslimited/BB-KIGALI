/**
 * BB Kigali FM — Terms & Conditions (native fallback).
 *
 * This screen ships inside the app so the Terms are always reachable
 * offline and satisfy the App Store / Play Store requirement for an
 * in-app Terms document accessible from the Settings / Profile menu.
 *
 * The web app (web.bbkigali.com) links here via any of the URLs matched
 * in `onShouldStartLoadWithRequest` in app/index.tsx (e.g. `/terms`,
 * `/legal/terms/current`, or `bbkigali://terms`).
 */
import { ScrollView, StyleSheet, Text, View, Pressable, Image } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";

const BRAND_RED = "#E10600";
const EFFECTIVE_DATE = "September 5, 2026";

export default function TermsScreen() {
  const router = useRouter();
  return (
    <SafeAreaView style={styles.safe} edges={["top", "left", "right"]}>
      <View style={styles.header}>
        <Pressable
          onPress={() => router.back()}
          hitSlop={16}
          testID="terms-back"
          style={styles.backBtn}
        >
          <Text style={styles.backChev}>‹</Text>
          <Text style={styles.backLabel}>Back</Text>
        </Pressable>
        <Text style={styles.headerTitle}>Terms &amp; Conditions</Text>
        <View style={{ width: 60 }} />
      </View>

      <ScrollView
        contentContainerStyle={styles.body}
        showsVerticalScrollIndicator={false}
      >
        <Image
          source={require("../assets/images/bbfm-logo-transparent.png")}
          style={styles.logo}
          resizeMode="contain"
        />
        <Text style={styles.effective}>Effective {EFFECTIVE_DATE}</Text>

        <Text style={styles.p}>
          Welcome to BB Kigali FM. By downloading, installing, or using this
          app, you agree to these Terms &amp; Conditions and our Privacy
          Policy. If you do not agree, please stop using the app.
        </Text>

        <Section title="1. Subscription">
          <P>
            Access to premium features — including live and on-demand video,
            simulcast radio, and exclusive shows — requires an active
            subscription. Subscriptions are billed monthly or annually, in
            advance, and renew automatically until cancelled.
          </P>
          <P>
            You may cancel at any time from the platform where you purchased
            the subscription (App Store, Google Play, or web checkout). Your
            access continues until the end of the current billing period.
          </P>
          <P>
            Prices, plans, and payment methods may change with notice at
            renewal. Existing paid periods are honoured at their original
            price.
          </P>
        </Section>

        <Section title="2. Content Ownership">
          <P>
            All audio, video, images, logos, and text in the BB Kigali FM
            app are the exclusive property of BB Kigali FM Ltd. and its
            content partners. You are granted a personal, non-transferable,
            non-commercial licence to stream this content on devices you
            own, for private use only.
          </P>
          <P>
            You may not download, copy, redistribute, resell, publicly
            broadcast, embed, or otherwise reproduce any part of the content
            without the prior written consent of BB Kigali FM Ltd.
          </P>
        </Section>

        <Section title="3. No-Screenshot & No-Recording Policy">
          <P>
            Premium content in this app is protected. Screen recording,
            screen mirroring (AirPlay / Chromecast to non-authorised
            devices), screenshots, and any other form of screen capture of
            premium playback are strictly prohibited.
          </P>
          <P>
            The app enforces this policy on both Android (FLAG_SECURE) and
            iOS (screen-recording detection). When the app detects capture
            or mirroring, playback is paused and the screen is blocked
            automatically. Repeated attempts to bypass these protections
            may result in permanent account suspension without refund and
            legal action for copyright infringement.
          </P>
        </Section>

        <Section title="4. Refund Policy">
          <P>
            Purchases made through the Apple App Store are governed by
            Apple&apos;s refund policy. Purchases made through Google Play
            are governed by Google&apos;s refund policy. Purchases made
            directly on the web (Stripe, PayPal, MTN Mobile Money) may be
            refunded within 7 days of the initial charge, provided you have
            not consumed more than 1 hour of premium content in that time.
          </P>
          <P>
            To request a refund, email{" "}
            <Text style={styles.link}>support@bbkigali.fm</Text> from the
            email address associated with your subscription. Include your
            order reference (Stripe session id, PayPal transaction id, or
            MTN MoMo reference). We aim to respond within 3 business days.
          </P>
          <P>
            Refunds are issued to the original payment method. Once a
            refund is issued, your subscription is cancelled immediately
            and access is revoked.
          </P>
        </Section>

        <Section title="5. Acceptable Use">
          <P>Users agree not to:</P>
          <Bullet>Share account credentials with anyone else.</Bullet>
          <Bullet>Circumvent geo-restrictions or content protections.</Bullet>
          <Bullet>Use automated tools (bots, scrapers) against the app.</Bullet>
          <Bullet>Attempt to access admin, backend, or moderator features.</Bullet>
          <Bullet>
            Post abusive, illegal, or infringing content in chat, comments,
            or user-generated features.
          </Bullet>
        </Section>

        <Section title="6. Privacy">
          <P>
            We collect and process personal data (phone number, email,
            payment info, device identifiers, listening/viewing history) to
            provide the service, process payments, personalise recommendations,
            and prevent fraud. Full details are in our Privacy Policy at{" "}
            <Text style={styles.link}>web.bbkigali.com/privacy</Text>.
          </P>
        </Section>

        <Section title="7. Limitation of Liability">
          <P>
            The BB Kigali FM app is provided &quot;as is&quot; without
            warranties of any kind. To the maximum extent permitted by law,
            BB Kigali FM Ltd. is not liable for any indirect, incidental,
            special, or consequential damages arising from your use of the
            app, including but not limited to loss of data, loss of
            revenue, or service interruption.
          </P>
        </Section>

        <Section title="8. Changes to These Terms">
          <P>
            We may update these Terms from time to time. Material changes
            will be announced in-app or by email at least 14 days before
            they take effect. Continued use of the app after the effective
            date constitutes acceptance of the updated Terms.
          </P>
        </Section>

        <Section title="9. Contact">
          <P>
            Questions or complaints? Email{" "}
            <Text style={styles.link}>support@bbkigali.fm</Text> or write to
            BB Kigali FM Ltd., Kigali, Rwanda.
          </P>
        </Section>

        <Text style={styles.footer}>
          © {new Date().getFullYear()} BB Kigali FM Ltd. All rights reserved.
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={styles.section}>
      <Text style={styles.h2}>{title}</Text>
      {children}
    </View>
  );
}

function P({ children }: { children: React.ReactNode }) {
  return <Text style={styles.p}>{children}</Text>;
}

function Bullet({ children }: { children: React.ReactNode }) {
  return (
    <View style={styles.bulletRow}>
      <Text style={styles.bulletDot}>•</Text>
      <Text style={styles.bulletText}>{children}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: "#FFFFFF" },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: "#E5E5E5",
    backgroundColor: "#FFFFFF",
  },
  backBtn: { flexDirection: "row", alignItems: "center", width: 60 },
  backChev: { fontSize: 26, color: BRAND_RED, marginRight: 4 },
  backLabel: { fontSize: 15, color: BRAND_RED, fontWeight: "600" },
  headerTitle: { fontSize: 16, fontWeight: "800", color: "#111111", letterSpacing: 0.5 },
  body: { paddingHorizontal: 20, paddingBottom: 40, paddingTop: 8 },
  logo: { alignSelf: "center", width: 180, height: 120, marginTop: 8, marginBottom: 8 },
  effective: { textAlign: "center", color: "#888", fontSize: 12, marginBottom: 18 },
  section: { marginBottom: 20 },
  h2: { fontSize: 15, fontWeight: "800", color: "#111", marginTop: 4, marginBottom: 8, letterSpacing: 0.4 },
  p: { fontSize: 14, lineHeight: 21, color: "#333", marginBottom: 10 },
  link: { color: BRAND_RED, textDecorationLine: "underline" },
  bulletRow: { flexDirection: "row", marginBottom: 6, paddingLeft: 4 },
  bulletDot: { color: BRAND_RED, fontSize: 16, lineHeight: 21, width: 16 },
  bulletText: { flex: 1, fontSize: 14, lineHeight: 21, color: "#333" },
  footer: { textAlign: "center", color: "#999", fontSize: 12, marginTop: 24 },
});
