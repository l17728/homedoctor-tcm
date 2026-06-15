import { request } from './client';

export interface SafetyCheckResult {
  safe: boolean;
  warnings: string[];
  interactions: string[];
  disclaimer?: string;
  layers?: {
    name: string;
    triggered: boolean;
    details: string[];
  }[];
}

export async function checkSafety(
  herbs: string[],
  medicines: string[],
): Promise<SafetyCheckResult> {
  return request<SafetyCheckResult>('/api/safety/check', {
    method: 'POST',
    body: JSON.stringify({ herbs, medicines }),
  });
}

export async function checkSafetyV2(params: {
  herbs: string[];
  medicines?: string[];
  user_profile?: Record<string, unknown>;
}): Promise<SafetyCheckResult> {
  return request<SafetyCheckResult>('/api/safety/check-v2', {
    method: 'POST',
    body: JSON.stringify(params),
  });
}
