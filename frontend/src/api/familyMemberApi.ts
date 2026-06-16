import { request } from './client';

export interface FamilyMember {
  id: string;
  family_id: string;
  user_id: string;
  name: string | null;
  relation: string | null;
  gender: string | null;
  date_of_birth: string | null;
  created_at: string;
}

export interface FamilyMemberCreate {
  name: string;
  relation: string;
  birth_date?: string | null;
  gender?: string | null;
}

export interface FamilyMemberUpdate {
  name?: string;
  relation?: string;
  birth_date?: string | null;
  gender?: string | null;
}

interface FamilyMemberRow {
  id: string;
  family_id: string;
  user_id: string;
  name: string | null;
  relation: string | null;
  gender: string | null;
  date_of_birth: string | null;
  created_at: string;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function mapMember(row: any): FamilyMember {
  return {
    id: row.id ?? '',
    family_id: row.family_id ?? '',
    user_id: row.user_id ?? '',
    name: row.name ?? null,
    relation: row.relation ?? null,
    gender: row.gender ?? null,
    date_of_birth: row.date_of_birth ?? null,
    created_at: row.created_at ?? '',
  };
}

export async function getFamilyMembers(): Promise<FamilyMember[]> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const data = await request<any>('/api/family-members');
  const items: FamilyMemberRow[] = Array.isArray(data) ? data : data.items ?? [];
  return items.map(mapMember);
}

export async function createFamilyMember(
  data: FamilyMemberCreate,
): Promise<FamilyMember> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const row = await request<any>('/api/family-members', {
    method: 'POST',
    body: JSON.stringify(data),
  });
  return mapMember(row);
}

export async function updateFamilyMember(
  id: string,
  data: FamilyMemberUpdate,
): Promise<FamilyMember> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const row = await request<any>(`/api/family-members/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
  return mapMember(row);
}

export async function deleteFamilyMember(id: string): Promise<void> {
  await request<void>(`/api/family-members/${id}`, { method: 'DELETE' });
}
