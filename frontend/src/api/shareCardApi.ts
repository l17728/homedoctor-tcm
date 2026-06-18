import { request } from './client';

// ---------------------------------------------------------------------------
// 分享卡 API — spec §13.3 V3 P0（家庭健康分享卡）
// 后端 /api/share-cards/* 路由（前端契约先行）
// ---------------------------------------------------------------------------

export type ShareCardType = '健康概览' | '节气养生' | '体质报告';

export interface ShareCard {
  id: string;
  card_type: ShareCardType;
  member_id: string;
  member_name: string;
  date: string;
  constitution: string | null;
  adherence: number | null;
  today_reminders: number | null;
  seasonal_advice: string | null;
  motivational_quote: string | null;
  created_at: string;
}

export interface ShareCardListResponse {
  items: ShareCard[];
  total: number;
}

export interface MonthlyFamilyMetric {
  member_id: string;
  member_name: string;
  constitution: string | null;
  adherence_rate: number | null;
  reminder_count: number;
  medicine_count: number;
  missed_count: number;
}

export interface MonthlyFamilyReport {
  items: MonthlyFamilyMetric[];
  period: string;
  generated_at: string;
}

export interface GenerateCardRequest {
  card_type: ShareCardType;
  member_id: string;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function mapCard(raw: any): ShareCard {
  return {
    id: raw.id ?? '',
    card_type: raw.card_type ?? '健康概览',
    member_id: raw.member_id ?? '',
    member_name: raw.member_name ?? '家人',
    date: raw.date ?? '',
    constitution: raw.constitution ?? null,
    adherence: raw.adherence ?? null,
    today_reminders: raw.today_reminders ?? null,
    seasonal_advice: raw.seasonal_advice ?? null,
    motivational_quote: raw.motivational_quote ?? null,
    created_at: raw.created_at ?? '',
  };
}

export async function generateShareCard(
  req: GenerateCardRequest,
): Promise<ShareCard> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const raw = await request<any>('/api/share-cards/generate', {
    method: 'POST',
    body: JSON.stringify(req),
  });
  return mapCard(raw);
}

export async function listShareCards(): Promise<ShareCard[]> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const data = await request<any>('/api/share-cards/list');
  const items = Array.isArray(data) ? data : data.items ?? [];
  return items.map(mapCard);
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function mapMonthlyMetric(raw: any): MonthlyFamilyMetric {
  return {
    member_id: raw.member_id ?? '',
    member_name: raw.member_name ?? '家人',
    constitution: raw.constitution ?? null,
    adherence_rate: raw.adherence_rate ?? null,
    reminder_count: raw.reminder_count ?? 0,
    medicine_count: raw.medicine_count ?? 0,
    missed_count: raw.missed_count ?? 0,
  };
}

export async function getMonthlyFamilyReport(): Promise<MonthlyFamilyReport> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const raw = await request<any>('/api/share-cards/monthly-report');
  return {
    items: Array.isArray(raw?.items) ? raw.items.map(mapMonthlyMetric) : [],
    period: raw?.period ?? '',
    generated_at: raw?.generated_at ?? '',
  };
}

export async function deleteShareCard(id: string): Promise<void> {
  await request<void>(`/api/share-cards/${id}`, { method: 'DELETE' });
}

// ---------------------------------------------------------------------------
// PDF 下载 — 二进制响应，request 仅处理 JSON，故此处用原生 fetch
// ---------------------------------------------------------------------------

export async function downloadShareCardPdf(cardId: string): Promise<void> {
  const token = localStorage.getItem('token');
  const headers: Record<string, string> = {};
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const response = await fetch(
    `/api/share-cards/${cardId}/pdf`,
    { method: 'GET', headers },
  );

  if (!response.ok) {
    throw new Error(`PDF 下载失败（${response.status}）`);
  }

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `share-card-${cardId}.pdf`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
