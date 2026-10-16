import { useEffect, useRef, useCallback } from 'react';
import { getTodayReminders, type TodayReminderSlot } from '../api/reminderApi';

const POLL_INTERVAL = 60_000;
const WINDOW_MINUTES = 1;

export type PermissionState = 'granted' | 'denied' | 'default' | 'unsupported';

export function getReminderNotificationPermission(): PermissionState {
  if (typeof window === 'undefined' || !('Notification' in window)) return 'unsupported';
  if (Notification.permission === 'granted') return 'granted';
  if (Notification.permission === 'denied') return 'denied';
  return 'default';
}

function playBeep(): void {
  try {
    const AudioCtx =
      window.AudioContext ||
      (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!AudioCtx) return;
    const ctx = new AudioCtx();
    const oscillator = ctx.createOscillator();
    const gainNode = ctx.createGain();
    oscillator.connect(gainNode);
    gainNode.connect(ctx.destination);
    oscillator.type = 'sine';
    oscillator.frequency.value = 880;
    gainNode.gain.setValueAtTime(0.3, ctx.currentTime);
    gainNode.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.5);
    oscillator.start(ctx.currentTime);
    oscillator.stop(ctx.currentTime + 0.5);
    oscillator.onended = () => ctx.close();
  } catch {
    // Audio not available, silently ignore
  }
}

function formatSlotBody(slot: TodayReminderSlot): string {
  const parts: string[] = [];
  const medName = slot.medicine_name ?? slot.herb_name ?? slot.formula_name;
  if (medName) parts.push(medName);
  if (slot.dosage) parts.push(slot.dosage);
  parts.push(`— ${slot.time}`);
  return parts.join(' ');
}

function isWithinWindow(slotTime: string): boolean {
  const now = new Date();
  const [h, m] = slotTime.split(':').map(Number);
  if (h === undefined || m === undefined) return false;
  const slotDate = new Date();
  slotDate.setHours(h, m, 0, 0);
  const diffMs = Math.abs(now.getTime() - slotDate.getTime());
  return diffMs <= WINDOW_MINUTES * 60 * 1000;
}

export interface UseNotificationsOptions {
  /** 点击通知后的跳转回调（由 Layout 注入 useNavigate，避免 hash 跳转） */
  onOpen?: (path: string) => void;
}

/** Must be called from a user gesture, such as the explicit enable button. */
export async function requestReminderNotificationPermission(): Promise<PermissionState> {
  if (getReminderNotificationPermission() !== 'default') return getReminderNotificationPermission();
  try {
    await Notification.requestPermission();
  } catch {
    // Keep the state as default so the user can retry from the explicit control.
  }
  return getReminderNotificationPermission();
}

export function useNotifications(options?: UseNotificationsOptions): void {
  const notifiedRef = useRef<Set<string>>(new Set());
  const onOpenRef = useRef(options?.onOpen);
  onOpenRef.current = options?.onOpen;

  const checkAndNotify = useCallback(async () => {
    if (getReminderNotificationPermission() !== 'granted') return;

    let slots: TodayReminderSlot[];
    try {
      slots = await getTodayReminders();
    } catch {
      return;
    }

    const todayKey = new Date().toISOString().slice(0, 10);
    for (const slot of slots) {
      if (slot.status !== '待服') continue;
      if (!isWithinWindow(slot.time)) continue;

      const notifyKey = `${todayKey}|${slot.reminder_id}|${slot.time}`;
      if (notifiedRef.current.has(notifyKey)) continue;

      notifiedRef.current.add(notifyKey);

      try {
        const notification = new Notification('吃药提醒', {
          body: formatSlotBody(slot),
          icon: '/favicon.ico',
          tag: notifyKey,
          requireInteraction: false,
        });
        notification.onclick = () => {
          window.focus();
          notification.close();
          onOpenRef.current?.('/reminders');
        };
      } catch {
        // Notification creation failed
      }

      playBeep();
    }

    const maxKeys = 200;
    if (notifiedRef.current.size > maxKeys) {
      const keys = Array.from(notifiedRef.current);
      notifiedRef.current = new Set(keys.slice(-maxKeys));
    }
  }, []);

  useEffect(() => {
    checkAndNotify();
    const interval = setInterval(checkAndNotify, POLL_INTERVAL);
    return () => clearInterval(interval);
  }, [checkAndNotify]);
}
