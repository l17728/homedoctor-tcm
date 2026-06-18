import { request } from './client';

export type Mood = '好' | '一般' | '差';

export const MOOD_EMOJI: Record<Mood, string> = {
  好: '😊',
  一般: '😐',
  差: '😞',
};

export interface HealthLog {
  id: string;
  user_id: string;
  family_member_id: string | null;
  log_date: string;
  systolic: number | null;
  diastolic: number | null;
  blood_sugar: number | null;
  weight: number | null;
  sleep_hours: number | null;
  mood: Mood | null;
  notes: string | null;
  created_at: string;
}

export interface HealthLogInput {
  log_date: string;
  family_member_id?: string | null;
  systolic?: number | null;
  diastolic?: number | null;
  blood_sugar?: number | null;
  weight?: number | null;
  sleep_hours?: number | null;
  mood?: Mood | null;
  notes?: string | null;
}

export interface HealthLogUpdateInput {
  log_date?: string;
  systolic?: number | null;
  diastolic?: number | null;
  blood_sugar?: number | null;
  weight?: number | null;
  sleep_hours?: number | null;
  mood?: Mood | null;
  notes?: string | null;
}

interface HealthLogRow {
  id?: string;
  user_id?: string;
  family_member_id?: string | null;
  log_date?: string;
  systolic?: number | null;
  diastolic?: number | null;
  blood_sugar?: number | null;
  weight?: number | null;
  sleep_hours?: number | null;
  mood?: Mood | null;
  notes?: string | null;
  created_at?: string;
}

function mapLog(row: HealthLogRow): HealthLog {
  return {
    id: row.id ?? '',
    user_id: row.user_id ?? '',
    family_member_id: row.family_member_id ?? null,
    log_date: row.log_date ?? '',
    systolic: row.systolic ?? null,
    diastolic: row.diastolic ?? null,
    blood_sugar: row.blood_sugar ?? null,
    weight: row.weight ?? null,
    sleep_hours: row.sleep_hours ?? null,
    mood: row.mood ?? null,
    notes: row.notes ?? null,
    created_at: row.created_at ?? '',
  };
}

export async function listHealthLogs(days: number = 30): Promise<HealthLog[]> {
  const data = await request<{ items: HealthLogRow[]; total: number; days: number }>(
    `/api/health-logs?days=${days}`,
  );
  return (data.items ?? []).map(mapLog);
}

export async function getLatestHealthLog(): Promise<HealthLog | null> {
  const data = await request<{ item: HealthLogRow | null }>(
    '/api/health-logs/latest',
  );
  return data.item ? mapLog(data.item) : null;
}

export async function createHealthLog(input: HealthLogInput): Promise<HealthLog> {
  const row = await request<HealthLogRow>('/api/health-logs', {
    method: 'POST',
    body: JSON.stringify(input),
  });
  return mapLog(row);
}

export async function updateHealthLog(
  id: string,
  input: HealthLogUpdateInput,
): Promise<HealthLog> {
  const row = await request<HealthLogRow>(`/api/health-logs/${id}`, {
    method: 'PUT',
    body: JSON.stringify(input),
  });
  return mapLog(row);
}

export async function deleteHealthLog(id: string): Promise<void> {
  await request<{ detail: string }>(`/api/health-logs/${id}`, {
    method: 'DELETE',
  });
}
