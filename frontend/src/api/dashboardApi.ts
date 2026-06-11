import { request } from './client';

export interface DashboardStats {
  herb_count: number;
  formula_count: number;
  medicine_count: number;
  reminder_count: number;
}

const MOCK_STATS: DashboardStats = {
  herb_count: 200,
  formula_count: 80,
  medicine_count: 0,
  reminder_count: 0,
};

export async function getDashboardStats(): Promise<DashboardStats> {
  try {
    return await request<DashboardStats>('/api/dashboard/stats');
  } catch {
    // Backend doesn't have this endpoint yet — aggregate from available APIs
    try {
      const [herbs, formulas, medicines] = await Promise.all([
        request<{ total: number }>('/api/herbs'),
        request<{ total: number }>('/api/formulas'),
        request<{ total: number }>('/api/medicines'),
      ]);
      return {
        herb_count: herbs.total ?? 0,
        formula_count: formulas.total ?? 0,
        medicine_count: medicines.total ?? 0,
        reminder_count: 0,
      };
    } catch {
      return MOCK_STATS;
    }
  }
}
