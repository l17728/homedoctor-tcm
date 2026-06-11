import { request } from './client';

export interface UserProfile {
  user_id: string;
  display_name: string | null;
  birth_year: number | null;
  gender: string | null;
  height_cm: number | null;
  weight_kg: number | null;
  constitution_type: string | null;
  constitution_secondary: string[];
  allergies: string[];
  health_conditions: string[];
  is_pregnant: boolean;
  blood_type: string | null;
  notes: string | null;
  updated_at: string;
}

export interface ProfileUpdate {
  display_name?: string | null;
  birth_year?: number | null;
  gender?: string | null;
  height_cm?: number | null;
  weight_kg?: number | null;
  allergies?: string[];
  health_conditions?: string[];
  is_pregnant?: boolean;
  blood_type?: string | null;
  notes?: string | null;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function mapProfile(row: any): UserProfile {
  return {
    user_id: row.user_id ?? '',
    display_name: row.display_name ?? null,
    birth_year: row.birth_year ?? null,
    gender: row.gender ?? null,
    height_cm: row.height_cm ?? null,
    weight_kg: row.weight_kg ?? null,
    constitution_type: row.constitution_type ?? null,
    constitution_secondary: row.constitution_secondary ?? [],
    allergies: row.allergies ?? [],
    health_conditions: row.health_conditions ?? [],
    is_pregnant: row.is_pregnant ?? false,
    blood_type: row.blood_type ?? null,
    notes: row.notes ?? null,
    updated_at: row.updated_at ?? '',
  };
}

export async function getProfile(): Promise<UserProfile> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const data = await request<any>('/api/profile');
  return mapProfile(data);
}

export async function updateProfile(data: ProfileUpdate): Promise<UserProfile> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const row = await request<any>('/api/profile', {
    method: 'PUT',
    body: JSON.stringify(data),
  });
  return mapProfile(row);
}
