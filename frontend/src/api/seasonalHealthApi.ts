import { request } from './client';

export interface Acupoint {
  name: string;
  location: string;
  effect: string;
}

export interface SeasonalHerb {
  name: string;
  reason: string;
}

export interface SolarTermInfo {
  name: string;
  season: string;
  month: number;
  is_current: boolean;
}

export interface SeasonalHealth {
  current_term: string;
  season: string;
  next_term: string;
  days_to_next_term: number;
  principle: string;
  diet: string[];
  lifestyle: string[];
  exercise: string[];
  acupoints: Acupoint[];
  herbs: SeasonalHerb[];
  formulas: string[];
  all_terms: SolarTermInfo[];
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function mapSeasonalHealth(raw: any): SeasonalHealth {
  return {
    current_term: raw.current_term ?? '',
    season: raw.season ?? '',
    next_term: raw.next_term ?? '',
    days_to_next_term: raw.days_to_next_term ?? 0,
    principle: raw.principle ?? '',
    diet: Array.isArray(raw.diet) ? raw.diet : [],
    lifestyle: Array.isArray(raw.lifestyle) ? raw.lifestyle : [],
    exercise: Array.isArray(raw.exercise) ? raw.exercise : [],
    acupoints: Array.isArray(raw.acupoints) ? raw.acupoints : [],
    herbs: Array.isArray(raw.herbs) ? raw.herbs : [],
    formulas: Array.isArray(raw.formulas) ? raw.formulas : [],
    all_terms: Array.isArray(raw.all_terms) ? raw.all_terms : [],
  };
}

export async function getSeasonalHealth(term?: string): Promise<SeasonalHealth> {
  const url = term
    ? `/api/seasonal-health?term=${encodeURIComponent(term)}`
    : '/api/seasonal-health';
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const raw = await request<any>(url);
  return mapSeasonalHealth(raw);
}
