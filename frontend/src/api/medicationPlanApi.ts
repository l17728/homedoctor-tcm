import { request } from './client';

/** 用药套餐状态 — active / paused / completed */
export type PlanStatus = 'active' | 'paused' | 'completed';

export interface PlanItem {
  id: string;
  planId: string;
  medicineName: string;
  dosage: string;
  frequency: string;
  times: string[];
  notes: string;
  sortOrder: number;
  reminderId?: string;
}

export interface MedicationPlan {
  id: string;
  userId: string;
  familyMemberId?: string;
  name: string;
  description: string;
  status: PlanStatus;
  startDate?: string;
  endDate?: string;
  createdAt: string;
  updatedAt: string;
  items: PlanItem[];
}

export interface CreatePlanItemInput {
  medicineName: string;
  dosage?: string;
  frequency?: string;
  times: string[];
  notes?: string;
  sortOrder?: number;
}

export interface CreateMedicationPlanInput {
  name: string;
  description?: string;
  familyMemberId?: string;
  status?: PlanStatus;
  startDate?: string;
  endDate?: string;
  items: CreatePlanItemInput[];
}

export interface UpdateMedicationPlanInput {
  name?: string;
  description?: string;
  status?: PlanStatus;
  startDate?: string;
  endDate?: string;
}

/** Raw backend plan row (snake_case; times is JSON string). */
interface PlanRow {
  id?: string;
  user_id?: string;
  family_member_id?: string | null;
  name?: string;
  description?: string | null;
  status?: string;
  start_date?: string | null;
  end_date?: string | null;
  created_at?: string;
  updated_at?: string;
  items?: PlanItemRow[];
}

interface PlanItemRow {
  id?: string;
  plan_id?: string;
  medicine_name?: string;
  dosage?: string | null;
  frequency?: string | null;
  times?: string | string[];
  notes?: string | null;
  sort_order?: number;
  reminder_id?: string | null;
}

function parseTimes(v: string | string[] | undefined): string[] {
  if (Array.isArray(v)) return v;
  if (typeof v === 'string' && v) {
    try {
      const parsed = JSON.parse(v);
      return Array.isArray(parsed) ? parsed.map(String) : [];
    } catch {
      return [];
    }
  }
  return [];
}

function mapPlanItem(row: PlanItemRow): PlanItem {
  return {
    id: row.id ?? '',
    planId: row.plan_id ?? '',
    medicineName: row.medicine_name ?? '',
    dosage: row.dosage ?? '',
    frequency: row.frequency ?? 'daily',
    times: parseTimes(row.times),
    notes: row.notes ?? '',
    sortOrder: row.sort_order ?? 0,
    reminderId: row.reminder_id ?? undefined,
  };
}

function mapPlan(row: PlanRow): MedicationPlan {
  const rawItems = Array.isArray(row.items) ? row.items : [];
  return {
    id: row.id ?? '',
    userId: row.user_id ?? '',
    familyMemberId: row.family_member_id ?? undefined,
    name: row.name ?? '',
    description: row.description ?? '',
    status: (row.status as PlanStatus) ?? 'active',
    startDate: row.start_date ?? undefined,
    endDate: row.end_date ?? undefined,
    createdAt: row.created_at ?? '',
    updatedAt: row.updated_at ?? '',
    items: rawItems.map(mapPlanItem),
  };
}

// ---------------------------------------------------------------------------
// Mock data — localStorage-backed for offline / demo rendering.
// ---------------------------------------------------------------------------
const STORAGE_KEY = 'family_doctor_medication_plans';

function getStored(): MedicationPlan[] {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return [];
  try {
    return JSON.parse(raw) as MedicationPlan[];
  } catch {
    return [];
  }
}

function saveStored(plans: MedicationPlan[]): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(plans));
}

function seedIfEmpty(): MedicationPlan[] {
  const existing = getStored();
  if (existing.length > 0) return existing;
  const now = new Date().toISOString().slice(0, 19).replace('T', ' ');
  const seeded: MedicationPlan[] = [
    {
      id: 'demo-plan-1',
      userId: 'demo',
      name: '高血压日常管理',
      description: '晨起服用降压药，监测血压',
      status: 'active',
      startDate: '2026-06-01',
      createdAt: now,
      updatedAt: now,
      items: [
        {
          id: 'demo-item-1',
          planId: 'demo-plan-1',
          medicineName: '缬沙坦胶囊',
          dosage: '每次80mg',
          frequency: 'daily',
          times: ['07:00'],
          notes: '空腹服用',
          sortOrder: 0,
        },
      ],
    },
    {
      id: 'demo-plan-2',
      userId: 'demo',
      name: '感冒调理（已停）',
      description: '中药+西药联合用药',
      status: 'paused',
      startDate: '2026-05-20',
      endDate: '2026-05-27',
      createdAt: now,
      updatedAt: now,
      items: [
        {
          id: 'demo-item-2',
          planId: 'demo-plan-2',
          medicineName: '感冒清热颗粒',
          dosage: '每次1袋',
          frequency: 'daily',
          times: ['08:00', '20:00'],
          notes: '温水冲服',
          sortOrder: 0,
        },
      ],
    },
  ];
  saveStored(seeded);
  return seeded;
}

export async function getMedicationPlans(): Promise<MedicationPlan[]> {
  try {
    const data = await request<{ items: PlanRow[]; total?: number }>(
      '/api/medication-plans',
    );
    return (data.items ?? []).map(mapPlan);
  } catch {
    return seedIfEmpty();
  }
}

export async function getMedicationPlan(id: string): Promise<MedicationPlan> {
  try {
    const row = await request<PlanRow>(`/api/medication-plans/${id}`);
    return mapPlan(row);
  } catch {
    const plan = seedIfEmpty().find((p) => p.id === id);
    if (!plan) throw new Error('未找到该用药套餐');
    return plan;
  }
}

export async function createMedicationPlan(
  input: CreateMedicationPlanInput,
): Promise<MedicationPlan> {
  try {
    const body = {
      name: input.name,
      description: input.description,
      family_member_id: input.familyMemberId,
      status: input.status ?? 'active',
      start_date: input.startDate,
      end_date: input.endDate,
      items: input.items.map((it) => ({
        medicine_name: it.medicineName,
        dosage: it.dosage,
        frequency: it.frequency ?? 'daily',
        times: it.times,
        notes: it.notes,
        sort_order: it.sortOrder ?? 0,
      })),
    };
    const row = await request<PlanRow>('/api/medication-plans', {
      method: 'POST',
      body: JSON.stringify(body),
    });
    return mapPlan(row);
  } catch {
    // Mock fallback — persist locally
    const plans = seedIfEmpty();
    const now = new Date().toISOString().slice(0, 19).replace('T', ' ');
    const planId = `local-${Date.now()}`;
    const newPlan: MedicationPlan = {
      id: planId,
      userId: 'local',
      familyMemberId: input.familyMemberId,
      name: input.name,
      description: input.description ?? '',
      status: input.status ?? 'active',
      startDate: input.startDate,
      endDate: input.endDate,
      createdAt: now,
      updatedAt: now,
      items: input.items.map((it, idx) => ({
        id: `local-item-${Date.now()}-${idx}`,
        planId,
        medicineName: it.medicineName,
        dosage: it.dosage ?? '',
        frequency: it.frequency ?? 'daily',
        times: it.times,
        notes: it.notes ?? '',
        sortOrder: it.sortOrder ?? idx,
      })),
    };
    plans.unshift(newPlan);
    saveStored(plans);
    return newPlan;
  }
}

export async function updateMedicationPlan(
  id: string,
  input: UpdateMedicationPlanInput,
): Promise<MedicationPlan> {
  try {
    const body: Record<string, unknown> = {};
    if (input.name !== undefined) body['name'] = input.name;
    if (input.description !== undefined) body['description'] = input.description;
    if (input.status !== undefined) body['status'] = input.status;
    if (input.startDate !== undefined) body['start_date'] = input.startDate;
    if (input.endDate !== undefined) body['end_date'] = input.endDate;
    const row = await request<PlanRow>(`/api/medication-plans/${id}`, {
      method: 'PUT',
      body: JSON.stringify(body),
    });
    return mapPlan(row);
  } catch {
    const plans = seedIfEmpty();
    const idx = plans.findIndex((p) => p.id === id);
    if (idx < 0) throw new Error('未找到该用药套餐');
    const existing = plans[idx];
    if (!existing) throw new Error('未找到该用药套餐');
    const updated: MedicationPlan = {
      ...existing,
      name: input.name ?? existing.name,
      description: input.description ?? existing.description,
      status: input.status ?? existing.status,
      startDate: input.startDate ?? existing.startDate,
      endDate: input.endDate ?? existing.endDate,
      updatedAt: new Date().toISOString().slice(0, 19).replace('T', ' '),
    };
    plans[idx] = updated;
    saveStored(plans);
    return updated;
  }
}

export async function deleteMedicationPlan(id: string): Promise<void> {
  try {
    await request<{ detail: string }>(`/api/medication-plans/${id}`, {
      method: 'DELETE',
    });
  } catch {
    const plans = seedIfEmpty().filter((p) => p.id !== id);
    saveStored(plans);
  }
}

export async function pausePlan(id: string): Promise<MedicationPlan> {
  try {
    const row = await request<PlanRow>(`/api/medication-plans/${id}/pause`, {
      method: 'POST',
    });
    return mapPlan(row);
  } catch {
    return updateMedicationPlan(id, { status: 'paused' });
  }
}

export async function resumePlan(id: string): Promise<MedicationPlan> {
  try {
    const row = await request<PlanRow>(`/api/medication-plans/${id}/resume`, {
      method: 'POST',
    });
    return mapPlan(row);
  } catch {
    return updateMedicationPlan(id, { status: 'active' });
  }
}
