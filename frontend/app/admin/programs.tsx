import { useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, TextInput, ActivityIndicator, Alert, KeyboardAvoidingView, Platform } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { colors, spacing, type, radius } from "@/src/theme";
import { api } from "@/src/api";

type Program = {
  id: string;
  name: string;
  description?: string;
  coverImage?: string;
  youtubeVideoId?: string;
  embedUrl?: string;
  order: number;
  isActive: boolean;
};

export default function AdminPrograms() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [items, setItems] = useState<Program[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<Program | null>(null);

  const load = async () => {
    try { setItems(await api<Program[]>("/admin/programs", { auth: true })); }
    catch { /* noop */ }
    finally { setLoading(false); }
  };
  useEffect(() => { void load(); }, []);

  const onSave = async (p: Program) => {
    const isNew = !p.id;
    try {
      if (isNew) {
        await api("/admin/programs", { method: "POST", auth: true, body: p });
      } else {
        await api(`/admin/programs/${p.id}`, { method: "PUT", auth: true, body: p });
      }
      setEditing(null);
      await load();
    } catch (e: any) { Alert.alert("Save failed", e.message); }
  };

  const onDelete = (p: Program) => {
    Alert.alert("Delete program?", `"${p.name}" will be removed.`, [
      { text: "Cancel", style: "cancel" },
      { text: "Delete", style: "destructive", onPress: async () => {
        try { await api(`/admin/programs/${p.id}`, { method: "DELETE", auth: true }); await load(); }
        catch (e: any) { Alert.alert("Delete failed", e.message); }
      } },
    ]);
  };

  if (editing) return <EditProgram initial={editing} onCancel={() => setEditing(null)} onSave={onSave} />;

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }} testID="admin-programs">
      <View style={[styles.top, { paddingTop: insets.top + spacing.md }]}>
        <Pressable onPress={() => router.back()} hitSlop={12} testID="programs-back" style={styles.iconRound}>
          <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>PROGRAMS</Text>
        <Pressable onPress={() => setEditing({ id: "", name: "", order: (items[items.length-1]?.order || 0) + 1, isActive: true })} testID="programs-add">
          <Ionicons name="add" size={26} color={colors.brandPrimary} />
        </Pressable>
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 160, gap: spacing.md }}>
        {loading && <ActivityIndicator color={colors.brandPrimary} />}
        {items.map((p) => (
          <View key={p.id} style={styles.row}>
            <View style={styles.orderBadge}><Text style={styles.orderText}>{p.order}</Text></View>
            <View style={{ flex: 1 }}>
              <Text style={styles.rowName}>{p.name}</Text>
              <Text style={styles.rowDesc} numberOfLines={2}>{p.description || "—"}</Text>
            </View>
            <Pressable onPress={() => setEditing(p)} hitSlop={8} testID={`edit-program-${p.name}`}>
              <Ionicons name="create-outline" size={22} color={colors.onSurface} />
            </Pressable>
            <Pressable onPress={() => onDelete(p)} hitSlop={8}>
              <Ionicons name="trash-outline" size={22} color={colors.error} />
            </Pressable>
          </View>
        ))}
        {!loading && items.length === 0 && <Text style={type.bodyMuted}>No programs yet — tap + to add.</Text>}
      </ScrollView>
    </View>
  );
}

function EditProgram({ initial, onCancel, onSave }: { initial: Program; onCancel: () => void; onSave: (p: Program) => void | Promise<void> }) {
  const insets = useSafeAreaInsets();
  const [p, setP] = useState<Program>(initial);
  const set = (k: keyof Program) => (v: string) => setP((prev) => ({ ...prev, [k]: k === "order" ? Number(v) || 0 : v }));

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.top, { paddingTop: insets.top + spacing.md }]}>
        <Pressable onPress={onCancel} hitSlop={12} style={styles.iconRound}>
          <Ionicons name="close" size={22} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>{initial.id ? "EDIT PROGRAM" : "NEW PROGRAM"}</Text>
        <View style={{ width: 40 }} />
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 160 }}>
        <Text style={styles.fieldLabel}>Name</Text>
        <TextInput value={p.name} onChangeText={set("name")} placeholder="BBSPORTSTALK" placeholderTextColor={colors.onSurfaceSecondary} style={styles.input} testID="prog-name" />
        <Text style={[styles.fieldLabel, { marginTop: spacing.lg }]}>Description</Text>
        <TextInput value={p.description || ""} onChangeText={set("description")} placeholder="Weekly sports talk…" placeholderTextColor={colors.onSurfaceSecondary} style={[styles.input, { height: 90 }]} multiline testID="prog-desc" />
        <Text style={[styles.fieldLabel, { marginTop: spacing.lg }]}>Cover image URL</Text>
        <TextInput value={p.coverImage || ""} onChangeText={set("coverImage")} placeholder="https://…" placeholderTextColor={colors.onSurfaceSecondary} style={styles.input} autoCapitalize="none" testID="prog-cover" />
        <Text style={[styles.fieldLabel, { marginTop: spacing.lg }]}>YouTube video ID (optional)</Text>
        <TextInput value={p.youtubeVideoId || ""} onChangeText={set("youtubeVideoId")} placeholder="Jsi8atSWGbg" placeholderTextColor={colors.onSurfaceSecondary} style={styles.input} autoCapitalize="none" testID="prog-vid" />
        <Text style={[styles.fieldLabel, { marginTop: spacing.lg }]}>Embed URL (playlist or search)</Text>
        <TextInput value={p.embedUrl || ""} onChangeText={set("embedUrl")} placeholder="https://www.youtube.com/embed/videoseries?list=PLxxx" placeholderTextColor={colors.onSurfaceSecondary} style={styles.input} autoCapitalize="none" testID="prog-embed" />
        <Text style={[styles.fieldLabel, { marginTop: spacing.lg }]}>Order</Text>
        <TextInput value={String(p.order)} onChangeText={set("order")} placeholder="1" placeholderTextColor={colors.onSurfaceSecondary} style={styles.input} keyboardType="number-pad" testID="prog-order" />
      </ScrollView>
      <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.md }]}>
        <Pressable onPress={() => onSave(p)} style={styles.saveBtn} testID="prog-save">
          <Text style={styles.saveText}>SAVE PROGRAM</Text>
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  top: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.lg, paddingBottom: spacing.sm, backgroundColor: colors.surface, borderBottomWidth: 1, borderBottomColor: colors.divider },
  iconRound: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border },
  title: { ...type.h1, flex: 1, textAlign: "center", letterSpacing: 1.5 },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border },
  orderBadge: { width: 36, height: 36, borderRadius: 18, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" },
  orderText: { color: colors.brandPrimary, fontFamily: "BarlowCondensed-Bold", fontSize: 16 },
  rowName: { ...type.h2, fontSize: 15 },
  rowDesc: { ...type.caption, marginTop: 2, lineHeight: 16 },
  fieldLabel: { ...type.label, marginBottom: spacing.xs, color: colors.onSurfaceSecondary },
  input: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.md, color: colors.onSurface, fontSize: 15, borderWidth: 1, borderColor: colors.border },
  footer: { position: "absolute", left: 0, right: 0, bottom: 0, backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.border, padding: spacing.lg },
  saveBtn: { backgroundColor: colors.brandPrimary, height: 52, borderRadius: radius.md, alignItems: "center", justifyContent: "center" },
  saveText: { ...type.h2, color: colors.onBrandPrimary, letterSpacing: 1.5 },
});
