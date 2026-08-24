/**
 * Program reminders — local scheduled notifications for schedule slots.
 *
 * Storage: AsyncStorage under key `bbfm.reminders.v1` — an object mapping
 * schedule slot id → { notificationId, reminderTime, slot }.
 *
 * NOTE: On Expo Go for iOS, scheduled local notifications are limited in
 * SDK 53+. Full support requires a real development / production build.
 */
import * as Notifications from "expo-notifications";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { Platform } from "react-native";

export type ScheduleSlot = {
  id: string;
  showTitle: string;
  djName?: string;
  time: string;
  coverImage?: string;
};

const STORAGE_KEY = "bbfm.reminders.v1";

type ReminderRecord = {
  slotId: string;
  notificationId: string;
  reminderTime: string; // ISO
  slot: ScheduleSlot;
};

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
    shouldShowBanner: true,
    shouldShowList: true,
  }),
});

export async function ensurePermissions(): Promise<boolean> {
  try {
    if (Platform.OS === "web") return false; // web can't schedule local notifs reliably
    const cur = await Notifications.getPermissionsAsync();
    if (cur.granted) return true;
    if (cur.canAskAgain === false) return false;
    const req = await Notifications.requestPermissionsAsync();
    return !!req.granted;
  } catch {
    return false;
  }
}

async function loadAll(): Promise<Record<string, ReminderRecord>> {
  try {
    const raw = await AsyncStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch { return {}; }
}

async function saveAll(all: Record<string, ReminderRecord>) {
  await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(all));
}

/** Parse "07:00 - 09:00" → today's Date(07:00). Falls back to null. */
function parseSlotStart(timeStr: string): Date | null {
  const m = timeStr.match(/(\d{1,2}):(\d{2})/);
  if (!m) return null;
  const now = new Date();
  const target = new Date(now.getFullYear(), now.getMonth(), now.getDate(), parseInt(m[1], 10), parseInt(m[2], 10), 0, 0);
  // If already past today, schedule for tomorrow at same time
  if (target.getTime() < now.getTime()) target.setDate(target.getDate() + 1);
  return target;
}

/**
 * Schedule a local notification 15 minutes before the slot starts.
 * Returns true on success, false on failure (permission denied, etc.).
 */
export async function scheduleReminder(slot: ScheduleSlot, leadMinutes = 15): Promise<boolean> {
  const ok = await ensurePermissions();
  if (!ok) return false;
  const start = parseSlotStart(slot.time);
  if (!start) return false;
  const trigger = new Date(start.getTime() - leadMinutes * 60_000);
  if (trigger.getTime() <= Date.now()) return false; // too close / already started

  // Remove any existing reminder for the same slot first.
  await cancelReminder(slot.id);
  const notificationId = await Notifications.scheduleNotificationAsync({
    content: {
      title: `📻 ${slot.showTitle} is about to start`,
      body: slot.djName ? `Tune in with ${slot.djName} at ${slot.time.split("-")[0].trim()}` : `Live at ${slot.time.split("-")[0].trim()}`,
      data: { slotId: slot.id, type: "program-reminder" },
      sound: "default",
    },
    // @ts-expect-error — the trigger type is loose across SDK versions
    trigger: { date: trigger },
  });
  const all = await loadAll();
  all[slot.id] = { slotId: slot.id, notificationId, reminderTime: trigger.toISOString(), slot };
  await saveAll(all);
  return true;
}

export async function cancelReminder(slotId: string): Promise<void> {
  const all = await loadAll();
  const rec = all[slotId];
  if (!rec) return;
  try { await Notifications.cancelScheduledNotificationAsync(rec.notificationId); } catch { /* noop */ }
  delete all[slotId];
  await saveAll(all);
}

export async function getReminder(slotId: string): Promise<ReminderRecord | null> {
  const all = await loadAll();
  return all[slotId] || null;
}

export async function listReminders(): Promise<ReminderRecord[]> {
  const all = await loadAll();
  return Object.values(all);
}
