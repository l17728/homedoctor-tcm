import { request } from './client';

export interface SafetyCheckResult {
  safe: boolean;
  warnings: string[];
  interactions: string[];
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
