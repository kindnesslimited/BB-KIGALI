import { useEffect, useMemo, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  Pressable,
  TextInput,
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Platform,
  Modal,
  FlatList,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { colors, spacing, type, radius } from "@/src/theme";
import { api } from "@/src/api";
import { useAuth } from "@/src/context/auth";

type AdminUser = {
  id: string;
  phone?: string | null;
  email?: string | null;
  displayName?: string | null;
  picture?: string | null;
  role: "user" | "admin";
  tier: string;
  createdAt?: string;
  provider?: string | null;
};

export default function AdminUsers() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user: me } = useAuth();
  const [items, setItems] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [busyIds, setBusyIds] = useState<Record<string, boolean>>({});
  const [inviting, setInviting] = useState(false);
  const [bulkOpen, setBulkOpen] = useState(false);

  const load = async (q?: string) => {
    try {
      setLoading(true);
      const path = q ? `/admin/users?q=${encodeURIComponent(q)}` : "/admin/users";
      setItems(await api<AdminUser[]>(path, { auth: true }));
    } catch (e: any) {
      Alert.alert("Load failed", e.message);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    void load();
  }, []);

  const filtered = useMemo(() => items, [items]);
  const adminCount = useMemo(() => items.filter((u) => u.role === "admin").length, [items]);

  const setBusy = (id: string, v: boolean) =>
    setBusyIds((prev) => ({ ...prev, [id]: v }));

  const toggleRole = async (u: AdminUser) => {
    const next: "user" | "admin" = u.role === "admin" ? "user" : "admin";
    const label = next === "admin" ? "Make admin" : "Remove admin";
    const displayName = u.displayName || u.phone || u.email || u.id.slice(0, 8);
    Alert.alert(label, `${label} for "${displayName}"?`, [
      { text: "Cancel", style: "cancel" },
      {
        text: label,
        style: next === "user" ? "destructive" : "default",
        onPress: async () => {
          setBusy(u.id, true);
          try {
            const updated = await api<AdminUser>(`/admin/users/${u.id}/role`, {
              method: "PUT",
              auth: true,
              body: { role: next },
            });
            setItems((prev) => prev.map((x) => (x.id === u.id ? { ...x, ...updated } : x)));
          } catch (e: any) {
            Alert.alert("Update failed", e.message);
          } finally {
            setBusy(u.id, false);
          }
        },
      },
    ]);
  };

  const deleteUser = (u: AdminUser) => {
    const displayName = u.displayName || u.phone || u.email || u.id.slice(0, 8);
    Alert.alert("Delete user?", `Permanently delete "${displayName}"? This cannot be undone.`, [
      { text: "Cancel", style: "cancel" },
      {
        text: "Delete",
        style: "destructive",
        onPress: async () => {
          setBusy(u.id, true);
          try {
            await api(`/admin/users/${u.id}`, { method: "DELETE", auth: true });
            setItems((prev) => prev.filter((x) => x.id !== u.id));
          } catch (e: any) {
            Alert.alert("Delete failed", e.message);
          } finally {
            setBusy(u.id, false);
          }
        },
      },
    ]);
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }} testID="admin-users">
      <View style={[styles.top, { paddingTop: insets.top + spacing.md }]}>
        <Pressable
          onPress={() => router.back()}
          hitSlop={12}
          testID="users-back"
          style={styles.iconRound}
        >
          <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>USERS</Text>
        <View style={{ flexDirection: "row", gap: spacing.md }}>
          <Pressable onPress={() => setBulkOpen(true)} testID="users-bulk" hitSlop={8}>
            <Ionicons name="albums" size={22} color={colors.onSurface} />
          </Pressable>
          <Pressable onPress={() => setInviting(true)} testID="users-invite" hitSlop={8}>
            <Ionicons name="person-add" size={24} color={colors.brandPrimary} />
          </Pressable>
        </View>
      </View>

      <View style={styles.searchWrap}>
        <View style={styles.searchBox}>
          <Ionicons name="search" size={16} color={colors.onSurfaceSecondary} />
          <TextInput
            value={query}
            onChangeText={setQuery}
            onSubmitEditing={() => load(query.trim() || undefined)}
            returnKeyType="search"
            placeholder="Search by phone, email, or name"
            placeholderTextColor={colors.onSurfaceSecondary}
            style={styles.searchInput}
            autoCapitalize="none"
            autoCorrect={false}
            testID="users-search"
          />
          {query.length > 0 && (
            <Pressable onPress={() => { setQuery(""); void load(); }} hitSlop={8}>
              <Ionicons name="close-circle" size={16} color={colors.onSurfaceSecondary} />
            </Pressable>
          )}
        </View>
        <View style={styles.statsRow}>
          <Text style={styles.statText}>{items.length} users</Text>
          <View style={styles.dotSep} />
          <Text style={[styles.statText, { color: colors.brandPrimary }]}>{adminCount} admins</Text>
        </View>
      </View>

      {loading ? (
        <View style={styles.loadingWrap}>
          <ActivityIndicator color={colors.brandPrimary} />
        </View>
      ) : (
        <FlatList
          data={filtered}
          keyExtractor={(u) => u.id}
          contentContainerStyle={{ padding: spacing.lg, paddingBottom: 160, gap: spacing.sm }}
          ListEmptyComponent={
            <View style={{ padding: spacing.xl, alignItems: "center" }}>
              <Ionicons name="people-outline" size={40} color={colors.onSurfaceSecondary} />
              <Text style={[type.bodyMuted, { marginTop: spacing.sm }]}>No users found.</Text>
            </View>
          }
          renderItem={({ item: u }) => {
            const isMe = me?.id === u.id;
            const busy = !!busyIds[u.id];
            const displayName = u.displayName || u.phone || u.email || "(no name)";
            const sub = u.phone && u.email ? u.email : (u.phone ? u.email : u.phone) || u.provider || "";
            return (
              <View style={[styles.row, u.role === "admin" && styles.rowAdmin]}>
                <View style={styles.avatar}>
                  <Ionicons
                    name={u.role === "admin" ? "shield-checkmark" : "person"}
                    size={20}
                    color={u.role === "admin" ? colors.brandPrimary : colors.onSurfaceSecondary}
                  />
                </View>
                <View style={{ flex: 1 }}>
                  <View style={styles.nameRow}>
                    <Text style={styles.name} numberOfLines={1}>{displayName}</Text>
                    {isMe && <View style={styles.youBadge}><Text style={styles.youText}>YOU</Text></View>}
                    {u.role === "admin" && !isMe && (
                      <View style={styles.adminBadge}><Text style={styles.adminText}>ADMIN</Text></View>
                    )}
                  </View>
                  {!!sub && <Text style={styles.sub} numberOfLines={1}>{sub}</Text>}
                </View>
                {busy ? (
                  <ActivityIndicator color={colors.brandPrimary} />
                ) : (
                  <>
                    <Pressable
                      onPress={() => toggleRole(u)}
                      hitSlop={8}
                      disabled={isMe && u.role === "admin"}
                      style={{ opacity: (isMe && u.role === "admin") ? 0.35 : 1 }}
                      testID={`role-toggle-${u.id}`}
                    >
                      <Ionicons
                        name={u.role === "admin" ? "shield" : "shield-outline"}
                        size={22}
                        color={u.role === "admin" ? colors.brandPrimary : colors.onSurfaceSecondary}
                      />
                    </Pressable>
                    {!isMe && (
                      <Pressable onPress={() => deleteUser(u)} hitSlop={8} testID={`delete-user-${u.id}`}>
                        <Ionicons name="trash-outline" size={20} color={colors.error} />
                      </Pressable>
                    )}
                  </>
                )}
              </View>
            );
          }}
        />
      )}

      <InviteModal
        visible={inviting}
        onClose={() => setInviting(false)}
        onDone={() => { setInviting(false); void load(); }}
      />

      <BulkInviteModal
        visible={bulkOpen}
        onClose={() => setBulkOpen(false)}
        onDone={() => { setBulkOpen(false); void load(); }}
      />
    </View>
  );
}

function BulkInviteModal({ visible, onClose, onDone }: { visible: boolean; onClose: () => void; onDone: () => void }) {
  const insets = useSafeAreaInsets();
  const [text, setText] = useState("");
  const [role, setRole] = useState<"user" | "admin">("user");
  const [saving, setSaving] = useState(false);

  const parseRows = (t: string) => {
    // Accepts CSV / newline / mixed: "phone,email,name" per line. Blank cells OK.
    const rows: any[] = [];
    for (const raw of t.split(/\r?\n/)) {
      const line = raw.trim();
      if (!line) continue;
      const parts = line.split(",").map(s => s.trim());
      const phone = parts[0] || null;
      const email = parts[1] || null;
      const name = parts[2] || null;
      if (!phone && !email) continue;
      rows.push({ phone, email, displayName: name, role });
    }
    return rows;
  };

  const submit = async () => {
    const users = parseRows(text);
    if (users.length === 0) { Alert.alert("Nothing to import", "Add at least one phone or email per line."); return; }
    setSaving(true);
    try {
      const r = await api<{ created: number; updated: number; skipped: number; errors: string[] }>(
        "/admin/users/bulk-invite", { method: "POST", auth: true, body: { users } }
      );
      Alert.alert("Bulk invite complete", `Created ${r.created}, updated ${r.updated}, skipped ${r.skipped}.${r.errors?.length ? `\nErrors: ${r.errors.slice(0,3).join('; ')}` : ""}`);
      setText("");
      onDone();
    } catch (e: any) {
      Alert.alert("Bulk invite failed", e.message || "Please try again.");
    } finally { setSaving(false); }
  };

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onClose} presentationStyle="fullScreen">
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1, backgroundColor: colors.surface }}>
        <View style={[bulkStyles.top, { paddingTop: insets.top + spacing.md }]}>
          <Pressable onPress={onClose} hitSlop={12}><Ionicons name="close" size={26} color={colors.onSurface} /></Pressable>
          <Text style={bulkStyles.title}>BULK INVITE</Text>
          <View style={{ width: 26 }} />
        </View>
        <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.md }}>
          <Text style={type.bodyMuted}>
            Paste one row per user in the format below. Phone or email is required — name is optional.
          </Text>
          <View style={bulkStyles.hint}>
            <Text style={bulkStyles.hintText}>phone,email,name</Text>
            <Text style={bulkStyles.hintExample}>+250788123456,jane@bbkigali.com,Jane Uwase</Text>
            <Text style={bulkStyles.hintExample}>250794230137,,Alice Mukamana</Text>
            <Text style={bulkStyles.hintExample}>,bob@bbkigali.com,Bob Habimana</Text>
          </View>
          <Text style={bulkStyles.roleLabel}>ROLE FOR ALL ROWS</Text>
          <View style={{ flexDirection: "row", gap: spacing.sm }}>
            {(["user", "admin"] as const).map((r) => (
              <Pressable key={r} onPress={() => setRole(r)} style={[bulkStyles.roleChip, role === r && bulkStyles.roleChipActive]}>
                <Text style={[bulkStyles.roleChipText, role === r && { color: "#000" }]}>{r.toUpperCase()}</Text>
              </Pressable>
            ))}
          </View>
          <TextInput
            value={text}
            onChangeText={setText}
            multiline
            placeholder="+250788123456,jane@bbkigali.com,Jane Uwase&#10;250794230137,,Alice Mukamana"
            placeholderTextColor={colors.onSurfaceSecondary}
            style={bulkStyles.textarea}
            autoCapitalize="none"
            testID="bulk-invite-textarea"
          />
          <Pressable onPress={submit} disabled={saving} style={[bulkStyles.saveBtn, saving && { opacity: 0.6 }]} testID="bulk-invite-save">
            {saving ? <ActivityIndicator color="#000" /> : <Text style={bulkStyles.saveText}>IMPORT {parseRows(text).length} USER(S)</Text>}
          </Pressable>
        </ScrollView>
      </KeyboardAvoidingView>
    </Modal>
  );
}

function InviteModal({
  visible,
  onClose,
  onDone,
}: {
  visible: boolean;
  onClose: () => void;
  onDone: () => void;
}) {
  const insets = useSafeAreaInsets();
  const [mode, setMode] = useState<"phone" | "email">("phone");
  const [value, setValue] = useState("");
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);

  const reset = () => {
    setMode("phone");
    setValue("");
    setName("");
  };

  const submit = async () => {
    if (!value.trim()) {
      Alert.alert("Missing", `Enter a ${mode} number`);
      return;
    }
    setSaving(true);
    try {
      const body: any = { role: "admin", displayName: name.trim() || undefined };
      if (mode === "phone") body.phone = value.trim().startsWith("+") ? value.trim() : "+" + value.trim();
      else body.email = value.trim();
      const r = await api<{ created: boolean; phone?: string; email?: string; displayName?: string }>(
        "/admin/users/invite",
        { method: "POST", auth: true, body }
      );
      Alert.alert(
        r.created ? "Admin invited" : "Role updated",
        r.created
          ? `${r.phone || r.email} is now an admin. They can sign in and access the admin console.`
          : `${r.phone || r.email} is now an admin.`
      );
      reset();
      onDone();
    } catch (e: any) {
      Alert.alert("Failed", e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal visible={visible} animationType="slide" transparent onRequestClose={onClose}>
      <View style={styles.modalOverlay}>
        <KeyboardAvoidingView
          behavior={Platform.OS === "ios" ? "padding" : undefined}
          style={{ width: "100%" }}
        >
          <View style={[styles.sheet, { paddingBottom: insets.bottom + spacing.lg }]}>
            <View style={styles.sheetGrab} />
            <View style={styles.sheetHeader}>
              <Text style={styles.sheetTitle}>INVITE ADMIN</Text>
              <Pressable onPress={onClose} hitSlop={12}>
                <Ionicons name="close" size={24} color={colors.onSurface} />
              </Pressable>
            </View>
            <Text style={styles.sheetSub}>
              They will be granted admin access as soon as they sign in with this{" "}
              {mode === "phone" ? "phone number" : "email"}.
            </Text>

            <ScrollView contentContainerStyle={{ paddingBottom: spacing.md }}>
              <View style={styles.segment}>
                <Pressable
                  onPress={() => setMode("phone")}
                  style={[styles.segItem, mode === "phone" && styles.segItemActive]}
                >
                  <Text style={[styles.segText, mode === "phone" && styles.segTextActive]}>PHONE</Text>
                </Pressable>
                <Pressable
                  onPress={() => setMode("email")}
                  style={[styles.segItem, mode === "email" && styles.segItemActive]}
                >
                  <Text style={[styles.segText, mode === "email" && styles.segTextActive]}>EMAIL</Text>
                </Pressable>
              </View>

              <Text style={styles.fieldLabel}>{mode === "phone" ? "Phone (E.164)" : "Email"}</Text>
              <TextInput
                value={value}
                onChangeText={setValue}
                placeholder={mode === "phone" ? "+250 78x xxx xxx" : "name@bbkigali.com"}
                placeholderTextColor={colors.onSurfaceSecondary}
                keyboardType={mode === "phone" ? "phone-pad" : "email-address"}
                autoCapitalize="none"
                autoCorrect={false}
                style={styles.input}
                testID="invite-value"
                autoFocus
              />

              <Text style={[styles.fieldLabel, { marginTop: spacing.md }]}>Display name (optional)</Text>
              <TextInput
                value={name}
                onChangeText={setName}
                placeholder="e.g. Nana J."
                placeholderTextColor={colors.onSurfaceSecondary}
                style={styles.input}
                testID="invite-name"
              />
            </ScrollView>

            <Pressable
              onPress={submit}
              disabled={saving}
              style={[styles.submitBtn, saving && { opacity: 0.5 }]}
              testID="invite-submit"
            >
              {saving ? (
                <ActivityIndicator color={colors.onBrandPrimary} />
              ) : (
                <Text style={styles.submitText}>GRANT ADMIN ACCESS</Text>
              )}
            </Pressable>
          </View>
        </KeyboardAvoidingView>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  top: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.sm,
    backgroundColor: colors.surface,
    borderBottomWidth: 1,
    borderBottomColor: colors.divider,
  },
  iconRound: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.surfaceSecondary,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: colors.border,
  },
  title: { ...type.h1, flex: 1, textAlign: "center", letterSpacing: 1.5 },
  searchWrap: { paddingHorizontal: spacing.lg, paddingVertical: spacing.md, gap: spacing.sm },
  searchBox: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.md,
    height: 44,
    borderWidth: 1,
    borderColor: colors.border,
  },
  searchInput: { flex: 1, color: colors.onSurface, fontSize: 14 },
  statsRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingHorizontal: 4 },
  statText: { ...type.caption },
  dotSep: { width: 3, height: 3, borderRadius: 2, backgroundColor: colors.onSurfaceSecondary },
  loadingWrap: { padding: spacing.xxl, alignItems: "center" },
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    padding: spacing.md,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  rowAdmin: { borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary },
  avatar: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.surfaceTertiary,
    alignItems: "center",
    justifyContent: "center",
  },
  nameRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, flexWrap: "wrap" },
  name: { ...type.h2, fontSize: 14, flexShrink: 1 },
  sub: { ...type.caption, marginTop: 2 },
  youBadge: {
    backgroundColor: colors.success,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: radius.sm,
  },
  youText: { color: "#fff", fontFamily: "BarlowCondensed-Bold", fontSize: 9, letterSpacing: 1 },
  adminBadge: {
    backgroundColor: colors.brandPrimary,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: radius.sm,
  },
  adminText: {
    color: colors.onBrandPrimary,
    fontFamily: "BarlowCondensed-Bold",
    fontSize: 9,
    letterSpacing: 1,
  },
  modalOverlay: { flex: 1, backgroundColor: "rgba(0,0,0,0.55)", justifyContent: "flex-end" },
  sheet: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: radius.lg,
    borderTopRightRadius: radius.lg,
    padding: spacing.lg,
    gap: spacing.sm,
    maxHeight: "88%",
  },
  sheetGrab: {
    alignSelf: "center",
    width: 40,
    height: 4,
    borderRadius: 2,
    backgroundColor: colors.onSurfaceSecondary,
    marginBottom: spacing.sm,
    opacity: 0.5,
  },
  sheetHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: 4,
  },
  sheetTitle: { ...type.h1, letterSpacing: 1.5, fontSize: 18 },
  sheetSub: { ...type.bodyMuted, marginBottom: spacing.md, fontSize: 13 },
  segment: {
    flexDirection: "row",
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.pill,
    padding: 3,
    marginBottom: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  segItem: {
    flex: 1,
    paddingVertical: 10,
    borderRadius: radius.pill,
    alignItems: "center",
  },
  segItemActive: { backgroundColor: colors.brandPrimary },
  segText: { color: colors.onSurfaceSecondary, fontSize: 12, fontFamily: "BarlowCondensed-Bold", letterSpacing: 1.5 },
  segTextActive: { color: colors.onBrandPrimary },
  fieldLabel: { ...type.label, marginBottom: spacing.xs, color: colors.onSurfaceSecondary },
  input: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    padding: spacing.md,
    color: colors.onSurface,
    fontSize: 15,
    borderWidth: 1,
    borderColor: colors.border,
  },
  submitBtn: {
    backgroundColor: colors.brandPrimary,
    height: 52,
    borderRadius: radius.md,
    alignItems: "center",
    justifyContent: "center",
    marginTop: spacing.md,
  },
  submitText: { ...type.h2, color: colors.onBrandPrimary, letterSpacing: 1.5 },
});

const bulkStyles = StyleSheet.create({
  top: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.border },
  title: { fontFamily: "BarlowCondensed-Bold", letterSpacing: 1.8, fontSize: 18, color: colors.onSurface },
  hint: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.md, borderWidth: 1, borderColor: colors.border },
  hintText: { color: colors.brandPrimary, fontFamily: "BarlowCondensed-Bold", letterSpacing: 1.5, fontSize: 12 },
  hintExample: { color: colors.onSurfaceSecondary, fontSize: 12, marginTop: 4, fontFamily: Platform.OS === "web" ? "monospace" : undefined },
  roleLabel: { color: colors.onSurfaceSecondary, letterSpacing: 1.5, fontSize: 12, fontFamily: "BarlowCondensed-Bold" },
  roleChip: { paddingHorizontal: spacing.lg, paddingVertical: 8, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  roleChipActive: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  roleChipText: { color: colors.onSurfaceSecondary, fontFamily: "BarlowCondensed-Bold", letterSpacing: 1.2, fontSize: 12 },
  textarea: { minHeight: 220, textAlignVertical: "top", backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.md, color: colors.onSurface, borderWidth: 1, borderColor: colors.border },
  saveBtn: { backgroundColor: colors.brandPrimary, height: 52, borderRadius: radius.md, alignItems: "center", justifyContent: "center", marginTop: spacing.md },
  saveText: { color: "#000", fontFamily: "BarlowCondensed-Bold", letterSpacing: 1.8, fontSize: 15, fontWeight: "900" },
});
