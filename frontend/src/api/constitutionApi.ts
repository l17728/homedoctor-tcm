import { request } from './client';

export interface ConstitutionQuestion {
  id: string;
  type: string;
  text: string;
}

export interface ConstitutionResult {
  id: string;
  assessed_at: string;
  results: Record<string, number>;
  primary_type: string;
  secondary_types: string[];
  raw_answers: Record<string, number>;
}

export interface AssessmentResponse {
  id: string;
  assessed_at: string;
  results: Record<string, number>;
  primary_type: string;
  secondary_types: string[];
  description: string;
}

export async function getQuestionnaire(): Promise<ConstitutionQuestion[]> {
  const data = await request<{ questions: ConstitutionQuestion[] }>(
    '/api/constitution/questionnaire',
  );
  return data.questions ?? [];
}

export async function submitAssessment(
  answers: Record<string, number>,
): Promise<AssessmentResponse> {
  const data = await request<{
    id: string;
    assessed_at: string;
    results: Record<string, number>;
    primary_type: string;
    secondary_types: string[];
    description?: string;
  }>('/api/constitution/assess', {
    method: 'POST',
    body: JSON.stringify({ answers }),
  });
  return {
    id: data.id,
    assessed_at: data.assessed_at,
    results: data.results ?? {},
    primary_type: data.primary_type ?? '平和质',
    secondary_types: data.secondary_types ?? [],
    description: data.description ?? '',
  };
}

export async function getAssessmentHistory(): Promise<ConstitutionResult[]> {
  const data = await request<unknown[]>('/api/constitution/history');
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return data.map((row: any) => ({
    id: row.id ?? '',
    assessed_at: row.assessed_at ?? '',
    results: row.results ?? {},
    primary_type: row.primary_type ?? '',
    secondary_types: row.secondary_types ?? [],
    raw_answers: row.raw_answers ?? {},
  }));
}

export async function getLatestAssessment(): Promise<ConstitutionResult | null> {
  try {
    const data = await request<ConstitutionResult>('/api/constitution/latest');
    return data;
  } catch {
    return null;
  }
}
