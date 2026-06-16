import { request } from './client';

export interface Reminder {
  id: string;
  user_id: string;
  title: string;
  herb_name: string | null;
  formula_name: string | null;
  medicine_name: string | null;
  dosage: string | null;
  frequency: string;
  times: string[];
  start_date: string;
  end_date: string | null;
  notes: string | null;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface TodayReminderSlot {
  reminder_id: string;
  title: string;
  time: string;
  dosage: string | null;
  herb_name: string | null;
  formula_name: string | null;
  medicine_name: string | null;
  status: '待服' | '已服' | '漏服';
  notes: string | null;
}

export interface ReminderCreate {
  title: string;
  herb_name?: string | null;
  formula_name?: string | null;
  medicine_name?: string | null;
  dosage?: string | null;
  frequency?: string;
  times: string[];
  start_date: string;
  end_date?: string | null;
  notes?: string | null;
  enabled?: boolean;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function mapReminder(row: any): Reminder {
  return {
    id: row.id ?? '',
    user_id: row.user_id ?? '',
    title: row.title ?? '',
    herb_name: row.herb_name ?? null,
    formula_name: row.formula_name ?? null,
    medicine_name: row.medicine_name ?? null,
    dosage: row.dosage ?? null,
    frequency: row.frequency ?? 'daily',
    times: row.times ?? [],
    start_date: row.start_date ?? '',
    end_date: row.end_date ?? null,
    notes: row.notes ?? null,
    enabled: row.enabled ?? true,
    created_at: row.created_at ?? '',
    updated_at: row.updated_at ?? '',
  };
}

export async function getReminders(): Promise<Reminder[]> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const data = await request<any>('/api/reminders');
  const items = Array.isArray(data) ? data : data.items ?? [];
  return items.map(mapReminder);
}

export async function getTodayReminders(): Promise<TodayReminderSlot[]> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const data = await request<any>('/api/reminders/today');
  const items = Array.isArray(data) ? data : data.items ?? [];
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return items.map((row: any) => ({
    reminder_id: row.reminder_id ?? row.id ?? '',
    title: row.title ?? '',
    time: row.time ?? '',
    dosage: row.dosage ?? null,
    herb_name: row.herb_name ?? null,
    formula_name: row.formula_name ?? null,
    medicine_name: row.medicine_name ?? null,
    status: row.status ?? '待服',
    notes: row.notes ?? null,
  }));
}

export async function createReminder(data: ReminderCreate): Promise<Reminder> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const row = await request<any>('/api/reminders', {
    method: 'POST',
    body: JSON.stringify(data),
  });
  return mapReminder(row);
}

export async function updateReminder(
  id: string,
  data: Partial<ReminderCreate>,
): Promise<Reminder> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const row = await request<any>(`/api/reminders/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
  return mapReminder(row);
}

export async function deleteReminder(id: string): Promise<void> {
  await request<void>(`/api/reminders/${id}`, { method: 'DELETE' });
}

export async function toggleReminder(id: string): Promise<Reminder> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const row = await request<any>(`/api/reminders/${id}/toggle`, {
    method: 'PUT',
  });
  return mapReminder(row);
}

export async function checkInReminder(
  reminderId: string,
  time: string,
  taken: boolean,
): Promise<void> {
  await request<void>(`/api/reminders/${reminderId}/check-in`, {
    method: 'POST',
    body: JSON.stringify({ time, taken }),
  });
}

export interface CheckInLog {
  id: string;
  date: string;
  reminder_id: string;
  title: string | null;
  herb_name: string | null;
  formula_name: string | null;
  medicine_name: string | null;
  taken: boolean;
  skipped_reason: string | null;
  created_at: string;
}

export interface CheckInHistory {
  items: CheckInLog[];
  total: number;
  taken_count: number;
  adherence_rate: number;
  days: number;
}

export async function getReminderHistory(days: number = 7): Promise<CheckInHistory> {
  const data = await request<CheckInHistory>(`/api/reminders/history?days=${days}`);
  return {
    items: data.items ?? [],
    total: data.total ?? 0,
    taken_count: data.taken_count ?? 0,
    adherence_rate: data.adherence_rate ?? 0,
    days: data.days ?? days,
  };
}
