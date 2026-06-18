import { useEffect, useRef, useCallback } from 'react';
import { getTodayReminders, type TodayReminderSlot } from '../api/reminderApi';

const PERMISSION_KEY = 'family_doctor_notification_permission';
const POLL_INTERVAL = 60_000;
const WINDOW_MINUTES = 1;

type PermissionState = 'granted' | 'denied' | 'default' | 'unsupported';

function getPermissionState(): PermissionState {
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

export function useNotifications(): void {
  const notifiedRef = useRef<Set<string>>(new Set());

  const requestPermission = useCallback(async () => {
    const stored = localStorage.getItem(PERMISSION_KEY);
    const state = getPermissionState();

    if (state === 'unsupported') return;
    if (state === 'granted') {
      localStorage.setItem(PERMISSION_KEY, 'granted');
      return;
    }
    if (state === 'denied') {
      localStorage.setItem(PERMISSION_KEY, 'denied');
      return;
    }

    if (stored !== 'asked') {
      localStorage.setItem(PERMISSION_KEY, 'asked');
      try {
        const result = await Notification.requestPermission();
        localStorage.setItem(PERMISSION_KEY, result);
      } catch {
        // Some browsers throw if not in user gesture context
      }
    }
  }, []);

  const checkAndNotify = useCallback(async () => {
    if (getPermissionState() !== 'granted') return;

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
          window.location.hash = '#/reminders';
          const navigateEvent = new CustomEvent('homedoctor-navigate', {
            detail: '/reminders',
          });
          window.dispatchEvent(navigateEvent);
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
    requestPermission();
    checkAndNotify();
    const interval = setInterval(checkAndNotify, POLL_INTERVAL);
    return () => clearInterval(interval);
  }, [requestPermission, checkAndNotify]);
}
