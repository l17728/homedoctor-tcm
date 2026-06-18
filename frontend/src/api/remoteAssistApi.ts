import { request } from './client';

// ---------------------------------------------------------------------------
// 远程协助 API — spec §22（子女远程查看父母健康数据）
// ---------------------------------------------------------------------------

export interface SharedUser {
  share_id: string;
  sharer_id: string;
  sharer_name: string;
  role: string;
  alert_config: Record<string, unknown>;
  created_at: string | null;
}

export interface SharedListResponse {
  items: SharedUser[];
  total: number;
}

export interface MedicationAdherenceSummary {
  rate: number;
  taken_7d: number;
  missed_7d: number;
  total_7d: number;
}

export interface StockAlert {
  type: string;
  name: string;
  severity: string;
  detail: string;
}

export interface ConstitutionSummary {
  primary_type: string;
  secondary_types: string[];
  assessed_at: string | null;
}

export interface HealthSummary {
  user_id: string;
  medication_adherence: MedicationAdherenceSummary;
  recent_alerts: StockAlert[];
  constitution_summary: ConstitutionSummary | null;
  missed_reminders: number;
  generated_at: string;
}

export interface WeeklyMedication {
  taken: number;
  missed: number;
  adherence_rate: number;
}

export interface NewSymptom {
  content: string;
  date: string | null;
}

export interface UpcomingRefill {
  name: string;
  quantity?: number;
  expiry_date?: string;
  reason: string;
}

export interface WeeklyReport {
  user_id: string;
  period: { from: string; to: string };
  medication: WeeklyMedication;
  new_symptoms_discussed: NewSymptom[];
  safety_alerts: { detail: unknown; created_at: string | null }[];
  upcoming_refills: UpcomingRefill[];
  generated_at: string;
}

export interface AlertConfig {
  missed_reminder_threshold?: number;
  expired_medicine_alert?: boolean;
  low_stock_threshold?: number;
}

export interface ConsentStatus {
  share_consent: boolean;
  role: string;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function mapSharedUser(row: any): SharedUser {
  return {
    share_id: row.share_id ?? row.id ?? '',
    sharer_id: row.sharer_id ?? '',
    sharer_name: row.sharer_name ?? row.display_name ?? row.username ?? '未知',
    role: row.role ?? '家属查看',
    alert_config: row.alert_config ?? {},
    created_at: row.created_at ?? null,
  };
}

export async function getSharedWithMe(): Promise<SharedUser[]> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const data = await request<any>('/api/remote-assist/shared-with-me');
  const items = Array.isArray(data) ? data : data.items ?? [];
  return items.map(mapSharedUser);
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function mapHealthSummary(raw: any): HealthSummary {
  return {
    user_id: raw.user_id ?? '',
    medication_adherence: {
      rate: raw.medication_adherence?.rate ?? 0,
      taken_7d: raw.medication_adherence?.taken_7d ?? 0,
      missed_7d: raw.medication_adherence?.missed_7d ?? 0,
      total_7d: raw.medication_adherence?.total_7d ?? 0,
    },
    recent_alerts: raw.recent_alerts ?? [],
    constitution_summary: raw.constitution_summary ?? null,
    missed_reminders: raw.missed_reminders ?? 0,
    generated_at: raw.generated_at ?? '',
  };
}

export async function getHealthSummary(userId: string): Promise<HealthSummary> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const raw = await request<any>(`/api/remote-assist/${userId}/summary`);
  return mapHealthSummary(raw);
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function mapWeeklyReport(raw: any): WeeklyReport {
  return {
    user_id: raw.user_id ?? '',
    period: {
      from: raw.period?.from ?? '',
      to: raw.period?.to ?? '',
    },
    medication: {
      taken: raw.medication?.taken ?? 0,
      missed: raw.medication?.missed ?? 0,
      adherence_rate: raw.medication?.adherence_rate ?? 0,
    },
    new_symptoms_discussed: raw.new_symptoms_discussed ?? [],
    safety_alerts: raw.safety_alerts ?? [],
    upcoming_refills: raw.upcoming_refills ?? [],
    generated_at: raw.generated_at ?? '',
  };
}

export async function getWeeklyReport(userId: string): Promise<WeeklyReport> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const raw = await request<any>(`/api/remote-assist/${userId}/weekly-report`);
  return mapWeeklyReport(raw);
}

export async function setAlertConfig(
  userId: string,
  config: AlertConfig,
): Promise<{ alert_config: AlertConfig }> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const raw = await request<any>(`/api/remote-assist/${userId}/alert`, {
    method: 'POST',
    body: JSON.stringify(config),
  });
  return { alert_config: raw.alert_config ?? config };
}

export interface InviteResult {
  id: string;
  sharer_id: string;
  viewer_id: string;
  role: string;
  status: string;
}

export async function inviteFamilyMember(
  inviteeUsername: string,
  role: string = '家属查看',
): Promise<InviteResult> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return await request<any>('/api/remote-assist/invite', {
    method: 'POST',
    body: JSON.stringify({ invitee_username: inviteeUsername, role }),
  });
}

export async function revokeShare(shareId: string): Promise<void> {
  await request<void>(`/api/remote-assist/invite/${shareId}`, {
    method: 'DELETE',
  });
}

export async function setShareConsent(
  shareConsent: boolean,
): Promise<{ share_consent: boolean }> {
  return await request<{ share_consent: boolean }>(
    '/api/remote-assist/consent',
    {
      method: 'PUT',
      body: JSON.stringify({ share_consent: shareConsent }),
    },
  );
}

export async function getShareConsent(): Promise<ConsentStatus> {
  return await request<ConsentStatus>('/api/remote-assist/consent');
}
