import { request } from './client';

export interface Favorite {
  id: string;
  entry_type: string;
  title: string;
  content: string | null;
  summary: string | null;
  tags: string[];
  source_type: string | null;
  source_url: string | null;
  is_starred: boolean;
  created_at: string;
}

export interface FavoriteCreate {
  entry_type: string;
  title: string;
  content?: string;
  summary?: string;
  tags?: string[];
  source_type?: string;
  source_url?: string;
}

export async function getFavorites(params?: {
  entry_type?: string;
  is_starred?: boolean;
  page?: number;
  pageSize?: number;
}): Promise<{ items: Favorite[]; total: number }> {
  const query = new URLSearchParams();
  if (params?.entry_type) query.set('entry_type', params.entry_type);
  if (params?.is_starred !== undefined) query.set('is_starred', String(params.is_starred));
  if (params?.page) query.set('page', String(params.page));
  if (params?.pageSize) query.set('pageSize', String(params.pageSize));
  const qs = query.toString();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const data = await request<any>(`/api/favorites${qs ? `?${qs}` : ''}`);
  return { items: data.items ?? [], total: data.total ?? 0 };
}

export async function createFavorite(data: FavoriteCreate): Promise<Favorite> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return request<any>('/api/favorites', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function deleteFavorite(id: string): Promise<void> {
  await request<void>(`/api/favorites/${id}`, { method: 'DELETE' });
}

export async function toggleFavoriteStar(id: string, starred: boolean): Promise<Favorite> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return request<any>(`/api/favorites/${id}`, {
    method: 'PUT',
    body: JSON.stringify({ is_starred: starred }),
  });
}

export async function updateFavoriteTags(id: string, tags: string[]): Promise<Favorite> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return request<any>(`/api/favorites/${id}`, {
    method: 'PUT',
    body: JSON.stringify({ tags }),
  });
}

export async function checkFavorite(
  entry_type: string,
  source_url: string,
): Promise<{ exists: boolean; favorite_id?: string }> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const data = await request<any>('/api/favorites/check', {
    method: 'POST',
    body: JSON.stringify({ entry_type, source_url }),
  });
  return { exists: data.is_favorited ?? data.exists ?? false, favorite_id: data.entry_id ?? data.favorite_id };
}

export async function saveKnowledgeCard(data: {
  title: string;
  content: string;
  tags?: string[];
}): Promise<Favorite> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return request<any>('/api/chat/save-card', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}
