import { useEffect, useState } from "react";
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
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { colors, spacing, type, radius } from "@/src/theme";
import { api } from "@/src/api";

type Category = {
  id: string;
  name: string;
  slug: string;
  order: number;
  isActive: boolean;
  isDefault?: boolean;
};

export default function AdminCategories() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [items, setItems] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<Category | null>(null);

  const load = async () => {
    try {
      setItems(await api<Category[]>("/admin/categories", { auth: true }));
    } catch {
      /* noop */
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    void load();
  }, []);

  const onSave = async (c: Category) => {
    const isNew = !c.id;
    try {
      if (isNew) {
        await api("/admin/categories", { method: "POST", auth: true, body: c });
      } else {
        await api(`/admin/categories/${c.id}`, { method: "PUT", auth: true, body: c });
      }
      setEditing(null);
      await load();
    } catch (e: any) {
      Alert.alert("Save failed", e.message);
    }
  };

  const onDelete = (c: Category) => {
    Alert.alert("Delete category?", `"${c.name}" will be removed.`, [
      { text: "Cancel", style: "cancel" },
      {
        text: "Delete",
        style: "destructive",
        onPress: async () => {
          try {
            await api(`/admin/categories/${c.id}`, { method: "DELETE", auth: true });
            await load();
          } catch (e: any) {
            Alert.alert("Delete failed", e.message);
          }
        },
      },
    ]);
  };

  const onToggleActive = async (c: Category) => {
    try {
      await api(`/admin/categories/${c.id}`, {
        method: "PUT",
        auth: true,
        body: { ...c, isActive: !c.isActive },
      });
      await load();
    } catch (e: any) {
      Alert.alert("Update failed", e.message);
    }
  };

  if (editing)
    return <EditCategory initial={editing} onCancel={() => setEditing(null)} onSave={onSave} />;

  const nextOrder = (items[items.length - 1]?.order || 0) + 1;

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }} testID="admin-categories">
      <View style={[styles.top, { paddingTop: insets.top + spacing.md }]}>
        <Pressable
          onPress={() => router.back()}
          hitSlop={12}
          testID="categories-back"
          style={styles.iconRound}
        >
          <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>CATEGORIES</Text>
        <Pressable
          onPress={() =>
            setEditing({ id: "", name: "", slug: "", order: nextOrder, isActive: true })
          }
          testID="categories-add"
          hitSlop={8}
        >
          <Ionicons name="add" size={26} color={colors.brandPrimary} />
        </Pressable>
      </View>

      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 160, gap: spacing.md }}>
        <Text style={styles.helper}>
          Categories appear as filters on the Shows tab. Add as many as you want (e.g. News, Sports,
          Music, Talk Shows, Culture, Movies).
        </Text>

        {loading && <ActivityIndicator color={colors.brandPrimary} />}

        {items.map((c) => (
          <View key={c.id} style={[styles.row, !c.isActive && styles.rowInactive]}>
            <View style={styles.orderBadge}>
              <Text style={styles.orderText}>{c.order}</Text>
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.rowName}>{c.name}</Text>
              <Text style={styles.rowSlug} numberOfLines={1}>
                slug: {c.slug}
                {c.isDefault ? " · default" : ""}
              </Text>
            </View>
            <Pressable
              onPress={() => onToggleActive(c)}
              hitSlop={8}
              testID={`toggle-cat-${c.slug}`}
            >
              <Ionicons
                name={c.isActive ? "eye-outline" : "eye-off-outline"}
                size={22}
                color={c.isActive ? colors.brandPrimary : colors.onSurfaceSecondary}
              />
            </Pressable>
            <Pressable
              onPress={() => setEditing(c)}
              hitSlop={8}
              testID={`edit-cat-${c.slug}`}
            >
              <Ionicons name="create-outline" size={22} color={colors.onSurface} />
            </Pressable>
            <Pressable
              onPress={() => onDelete(c)}
              hitSlop={8}
              testID={`delete-cat-${c.slug}`}
            >
              <Ionicons name="trash-outline" size={22} color={colors.error} />
            </Pressable>
          </View>
        ))}

        {!loading && items.length === 0 && (
          <Text style={type.bodyMuted}>No categories yet — tap + to add one.</Text>
        )}
      </ScrollView>
    </View>
  );
}

function EditCategory({
  initial,
  onCancel,
  onSave,
}: {
  initial: Category;
  onCancel: () => void;
  onSave: (c: Category) => void | Promise<void>;
}) {
  const insets = useSafeAreaInsets();
  const [c, setC] = useState<Category>(initial);
  const isNew = !initial.id;
  const [saving, setSaving] = useState(false);

  const setName = (v: string) => setC((prev) => ({ ...prev, name: v }));
  const setOrder = (v: string) => setC((prev) => ({ ...prev, order: Number(v) || 0 }));

  const submit = async () => {
    if (!c.name.trim()) {
      Alert.alert("Missing name", "Please enter a category name.");
      return;
    }
    setSaving(true);
    try {
      await onSave(c);
    } finally {
      setSaving(false);
    }
  };

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === "ios" ? "padding" : undefined}
      style={{ flex: 1, backgroundColor: colors.surface }}
    >
      <View style={[styles.top, { paddingTop: insets.top + spacing.md }]}>
        <Pressable onPress={onCancel} hitSlop={12} style={styles.iconRound}>
          <Ionicons name="close" size={22} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>{isNew ? "NEW CATEGORY" : "EDIT CATEGORY"}</Text>
        <View style={{ width: 40 }} />
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 160 }}>
        <Text style={styles.fieldLabel}>Name</Text>
        <TextInput
          value={c.name}
          onChangeText={setName}
          placeholder="e.g. News, Sports, Music"
          placeholderTextColor={colors.onSurfaceSecondary}
          style={styles.input}
          autoCapitalize="words"
          testID="cat-name"
          autoFocus
        />

        <Text style={[styles.fieldLabel, { marginTop: spacing.lg }]}>Display order</Text>
        <TextInput
          value={String(c.order)}
          onChangeText={setOrder}
          placeholder="1"
          placeholderTextColor={colors.onSurfaceSecondary}
          style={styles.input}
          keyboardType="number-pad"
          testID="cat-order"
        />
        <Text style={styles.helperSm}>Lower numbers show first in the Shows tab.</Text>

        <Pressable
          onPress={() => setC((prev) => ({ ...prev, isActive: !prev.isActive }))}
          style={[styles.toggleRow, { marginTop: spacing.lg }]}
          testID="cat-toggle-active"
        >
          <View style={{ flex: 1 }}>
            <Text style={styles.fieldLabel}>Visible to listeners</Text>
            <Text style={styles.helperSm}>
              When off, category is hidden from the Shows tab (shows stay in database).
            </Text>
          </View>
          <View style={[styles.switch, c.isActive && styles.switchOn]}>
            <View style={[styles.knob, c.isActive && styles.knobOn]} />
          </View>
        </Pressable>
      </ScrollView>

      <View style={[styles.footer, { paddingBottom: insets.bottom + spacing.md }]}>
        <Pressable
          onPress={submit}
          style={[styles.saveBtn, saving && { opacity: 0.6 }]}
          disabled={saving}
          testID="cat-save"
        >
          {saving ? (
            <ActivityIndicator color={colors.onBrandPrimary} />
          ) : (
            <Text style={styles.saveText}>{isNew ? "CREATE CATEGORY" : "SAVE CATEGORY"}</Text>
          )}
        </Pressable>
      </View>
    </KeyboardAvoidingView>
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
  helper: { ...type.bodyMuted, marginBottom: spacing.sm },
  helperSm: { ...type.caption, marginTop: 4, color: colors.onSurfaceSecondary },
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
  rowInactive: { opacity: 0.55 },
  orderBadge: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: colors.brandTertiary,
    alignItems: "center",
    justifyContent: "center",
  },
  orderText: { color: colors.brandPrimary, fontFamily: "BarlowCondensed-Bold", fontSize: 16 },
  rowName: { ...type.h2, fontSize: 15 },
  rowSlug: { ...type.caption, marginTop: 2 },
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
  toggleRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    padding: spacing.md,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  switch: {
    width: 48,
    height: 28,
    borderRadius: 14,
    backgroundColor: colors.surfaceTertiary,
    padding: 3,
    justifyContent: "center",
  },
  switchOn: { backgroundColor: colors.brandPrimary },
  knob: { width: 22, height: 22, borderRadius: 11, backgroundColor: "#fff" },
  knobOn: { transform: [{ translateX: 20 }] },
  footer: {
    position: "absolute",
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: colors.surface,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    padding: spacing.lg,
  },
  saveBtn: {
    backgroundColor: colors.brandPrimary,
    height: 52,
    borderRadius: radius.md,
    alignItems: "center",
    justifyContent: "center",
  },
  saveText: { ...type.h2, color: colors.onBrandPrimary, letterSpacing: 1.5 },
});
