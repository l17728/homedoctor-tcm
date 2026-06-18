import { request } from './client';

// ---------------------------------------------------------------------------
// 报告中心 API — spec §7 / §13.3 V3 P0
// ---------------------------------------------------------------------------

export type ReportType = 'constitution' | 'health-trend' | 'pre-visit';
export type ReportPeriod = '7d' | '30d' | '90d';

interface ReportEnvelope {
  report_type: string;
  generated_at: string;
  data_period: string;
  disclaimer: string;
}

export interface ConstitutionAssessment {
  has_data: boolean;
  primary_type: string | null;
  secondary_types: string[];
  description: string;
  latest_scores: Record<string, number>;
  assessed_at: string | null;
}

export interface TrendPoint {
  assessed_at: string;
  primary_type: string;
  primary_score: number;
  all_scores: Record<string, number>;
}

export interface ConstitutionReport extends ReportEnvelope {
  assessment: ConstitutionAssessment;
  trend: {
    total_assessments: number;
    points: TrendPoint[];
  };
  recommendations: {
    diet: { 宜食: string[]; 忌食: string[] };
    exercise: string[];
    lifestyle: string[];
    description: string;
  };
  seasonal_advice: {
    current_term: string;
    season: string;
    principle: string;
    diet: string[];
    lifestyle: string[];
    exercise: string[];
    recommended_herbs: string[];
    recommended_formulas: string[];
  };
}

export interface HealthTrendReport extends ReportEnvelope {
  period: ReportPeriod;
  period_days: number;
  medication_adherence: {
    period_days: number;
    total_logs: number;
    taken_count: number;
    skipped_count: number;
    adherence_rate: number;
  };
  reminder_trends: {
    total_reminders: number;
    enabled_reminders: number;
    disabled_reminders: number;
    daily_completion: { date: string; count: number }[];
    active_days: number;
  };
  medicine_cabinet_changes: {
    additions_count: number;
    deletions_count: number;
    expired_count: number;
    expiring_soon_count: number;
    expired: { name: string; expiry_date: string }[];
    expiring_soon: { name: string; expiry_date: string; quantity: number }[];
  };
  chat_interaction: {
    total_conversations: number;
    active_days: number;
    daily_breakdown: { date: string; count: number }[];
  };
  safety_check_history: {
    total_checks: number;
    warning_count: number;
    critical_count: number;
  };
}

export interface PreVisitMedication {
  name: string;
  type: string | null;
  specification: string | null;
  dosage: string | null;
  quantity: number | null;
  expiry_date: string | null;
  brand: string | null;
  drug_class: string | null;
}

export interface PreVisitReport extends ReportEnvelope {
  patient_info: {
    display_name: string | null;
    gender: string | null;
    birth_year: number | null;
    height_cm: number | null;
    weight_kg: number | null;
    blood_type: string | null;
    is_pregnant: boolean;
  };
  medications: PreVisitMedication[];
  medication_count: number;
  allergies: string[];
  health_conditions: string[];
  constitution: {
    primary_type: string | null;
    secondary_types: string[];
    description: string;
    assessed_at: string | null;
  };
  recent_chat_topics: string[];
  safety_check_results: {
    created_at: string;
    safe: boolean;
    warning_count: number;
    warnings: unknown[];
  }[];
  questions_for_doctor: string[];
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function mapConstitutionReport(raw: any): ConstitutionReport {
  return {
    report_type: raw.report_type ?? '体质报告',
    generated_at: raw.generated_at ?? '',
    data_period: raw.data_period ?? '',
    disclaimer: raw.disclaimer ?? '',
    assessment: {
      has_data: raw.assessment?.has_data ?? false,
      primary_type: raw.assessment?.primary_type ?? null,
      secondary_types: raw.assessment?.secondary_types ?? [],
      description: raw.assessment?.description ?? '',
      latest_scores: raw.assessment?.latest_scores ?? {},
      assessed_at: raw.assessment?.assessed_at ?? null,
    },
    trend: {
      total_assessments: raw.trend?.total_assessments ?? 0,
      points: raw.trend?.points ?? [],
    },
    recommendations: {
      diet: raw.recommendations?.diet ?? { 宜食: [], 忌食: [] },
      exercise: raw.recommendations?.exercise ?? [],
      lifestyle: raw.recommendations?.lifestyle ?? [],
      description: raw.recommendations?.description ?? '',
    },
    seasonal_advice: {
      current_term: raw.seasonal_advice?.current_term ?? '',
      season: raw.seasonal_advice?.season ?? '',
      principle: raw.seasonal_advice?.principle ?? '',
      diet: raw.seasonal_advice?.diet ?? [],
      lifestyle: raw.seasonal_advice?.lifestyle ?? [],
      exercise: raw.seasonal_advice?.exercise ?? [],
      recommended_herbs: raw.seasonal_advice?.recommended_herbs ?? [],
      recommended_formulas: raw.seasonal_advice?.recommended_formulas ?? [],
    },
  };
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function mapHealthTrendReport(raw: any): HealthTrendReport {
  return {
    report_type: raw.report_type ?? '健康趋势报告',
    generated_at: raw.generated_at ?? '',
    data_period: raw.data_period ?? '',
    disclaimer: raw.disclaimer ?? '',
    period: raw.period ?? '30d',
    period_days: raw.period_days ?? 30,
    medication_adherence: {
      period_days: raw.medication_adherence?.period_days ?? 30,
      total_logs: raw.medication_adherence?.total_logs ?? 0,
      taken_count: raw.medication_adherence?.taken_count ?? 0,
      skipped_count: raw.medication_adherence?.skipped_count ?? 0,
      adherence_rate: raw.medication_adherence?.adherence_rate ?? 0,
    },
    reminder_trends: {
      total_reminders: raw.reminder_trends?.total_reminders ?? 0,
      enabled_reminders: raw.reminder_trends?.enabled_reminders ?? 0,
      disabled_reminders: raw.reminder_trends?.disabled_reminders ?? 0,
      daily_completion: raw.reminder_trends?.daily_completion ?? [],
      active_days: raw.reminder_trends?.active_days ?? 0,
    },
    medicine_cabinet_changes: {
      additions_count: raw.medicine_cabinet_changes?.additions_count ?? 0,
      deletions_count: raw.medicine_cabinet_changes?.deletions_count ?? 0,
      expired_count: raw.medicine_cabinet_changes?.expired_count ?? 0,
      expiring_soon_count: raw.medicine_cabinet_changes?.expiring_soon_count ?? 0,
      expired: raw.medicine_cabinet_changes?.expired ?? [],
      expiring_soon: raw.medicine_cabinet_changes?.expiring_soon ?? [],
    },
    chat_interaction: {
      total_conversations: raw.chat_interaction?.total_conversations ?? 0,
      active_days: raw.chat_interaction?.active_days ?? 0,
      daily_breakdown: raw.chat_interaction?.daily_breakdown ?? [],
    },
    safety_check_history: {
      total_checks: raw.safety_check_history?.total_checks ?? 0,
      warning_count: raw.safety_check_history?.warning_count ?? 0,
      critical_count: raw.safety_check_history?.critical_count ?? 0,
    },
  };
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function mapPreVisitReport(raw: any): PreVisitReport {
  return {
    report_type: raw.report_type ?? '就诊准备报告',
    generated_at: raw.generated_at ?? '',
    data_period: raw.data_period ?? '',
    disclaimer: raw.disclaimer ?? '',
    patient_info: {
      display_name: raw.patient_info?.display_name ?? null,
      gender: raw.patient_info?.gender ?? null,
      birth_year: raw.patient_info?.birth_year ?? null,
      height_cm: raw.patient_info?.height_cm ?? null,
      weight_kg: raw.patient_info?.weight_kg ?? null,
      blood_type: raw.patient_info?.blood_type ?? null,
      is_pregnant: raw.patient_info?.is_pregnant ?? false,
    },
    medications: raw.medications ?? [],
    medication_count: raw.medication_count ?? 0,
    allergies: raw.allergies ?? [],
    health_conditions: raw.health_conditions ?? [],
    constitution: {
      primary_type: raw.constitution?.primary_type ?? null,
      secondary_types: raw.constitution?.secondary_types ?? [],
      description: raw.constitution?.description ?? '',
      assessed_at: raw.constitution?.assessed_at ?? null,
    },
    recent_chat_topics: raw.recent_chat_topics ?? [],
    safety_check_results: raw.safety_check_results ?? [],
    questions_for_doctor: raw.questions_for_doctor ?? [],
  };
}

export async function getConstitutionReport(): Promise<ConstitutionReport> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const raw = await request<any>('/api/reports/constitution');
  return mapConstitutionReport(raw);
}

export async function getHealthTrendReport(
  period: ReportPeriod = '30d',
): Promise<HealthTrendReport> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const raw = await request<any>(
    `/api/reports/health-trend?period=${encodeURIComponent(period)}`,
  );
  return mapHealthTrendReport(raw);
}

export async function getPreVisitReport(): Promise<PreVisitReport> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const raw = await request<any>('/api/reports/pre-visit');
  return mapPreVisitReport(raw);
}

// ---------------------------------------------------------------------------
// PDF 下载 — 二进制响应，request 仅处理 JSON，故此处用原生 fetch
// ---------------------------------------------------------------------------

export async function generateReportPdf(
  reportType: ReportType,
  period: ReportPeriod = '30d',
): Promise<void> {
  const token = localStorage.getItem('token');
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const response = await fetch('/api/reports/generate-pdf', {
    method: 'POST',
    headers,
    body: JSON.stringify({ report_type: reportType, period }),
  });

  if (!response.ok) {
    throw new Error(`PDF 生成失败（${response.status}）`);
  }

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${reportType}-report.pdf`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
