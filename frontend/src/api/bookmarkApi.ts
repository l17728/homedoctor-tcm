import { request } from './client';

export type BookmarkType = 'herb' | 'formula' | 'therapy' | 'knowledge' | 'external';

export const BOOKMARK_TYPE_LABEL: Record<BookmarkType, string> = {
  herb: '中药',
  formula: '方剂',
  therapy: '外治理疗',
  knowledge: '知识',
  external: '外部链接',
};

export const BOOKMARK_TYPE_COLOR: Record<BookmarkType, string> = {
  herb: 'green',
  formula: 'geekblue',
  therapy: 'purple',
  knowledge: 'blue',
  external: 'default',
};

export interface Bookmark {
  id: string;
  user_id: string;
  entry_type: BookmarkType;
  entry_id: string | null;
  title: string;
  content: string | null;
  tags: string[];
  source_type: string | null;
  source_url: string | null;
  is_starred: boolean;
  created_at: string;
  updated_at: string;
}

export interface BookmarkCollection {
  id: string;
  user_id: string;
  entry_type: string;
  title: string;
  content: string[];
  tags: string[];
  source_type: string | null;
  is_starred: boolean;
  member_count: number;
  created_at: string;
  updated_at: string;
}

export interface BookmarkCreate {
  entry_type: BookmarkType;
  title: string;
  entry_id?: string | null;
  content?: string | null;
  tags?: string[];
  source_type?: string;
  is_starred?: boolean;
}

export interface BookmarkUpdate {
  title?: string;
  content?: string | null;
  tags?: string[];
  is_starred?: boolean;
  source_type?: string;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function mapBookmark(row: any): Bookmark {
  return {
    id: row.id ?? '',
    user_id: row.user_id ?? '',
    entry_type: (row.entry_type ?? 'external') as BookmarkType,
    entry_id: row.entry_id ?? null,
    title: row.title ?? '',
    content: row.content ?? null,
    tags: Array.isArray(row.tags) ? row.tags : [],
    source_type: row.source_type ?? null,
    source_url: row.source_url ?? null,
    is_starred: !!row.is_starred,
    created_at: row.created_at ?? '',
    updated_at: row.updated_at ?? '',
  };
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function mapCollection(row: any): BookmarkCollection {
  return {
    id: row.id ?? '',
    user_id: row.user_id ?? '',
    entry_type: row.entry_type ?? 'collection',
    title: row.title ?? '',
    content: Array.isArray(row.content) ? row.content : [],
    tags: Array.isArray(row.tags) ? row.tags : [],
    source_type: row.source_type ?? null,
    is_starred: !!row.is_starred,
    member_count: row.member_count ?? 0,
    created_at: row.created_at ?? '',
    updated_at: row.updated_at ?? '',
  };
}

export async function getBookmarks(params?: {
  entry_type?: BookmarkType;
  is_starred?: boolean;
  tags?: string[];
  tag_logic?: 'AND' | 'OR';
}): Promise<{ items: Bookmark[]; total: number }> {
  const query = new URLSearchParams();
  if (params?.entry_type) query.set('entry_type', params.entry_type);
  if (params?.is_starred !== undefined) query.set('is_starred', String(params.is_starred));
  if (params?.tags && params.tags.length > 0) {
    query.set('tags', params.tags.join(','));
    query.set('tag_logic', params.tag_logic ?? 'OR');
  }
  const qs = query.toString();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const data = await request<any>(`/api/bookmarks${qs ? `?${qs}` : ''}`);
  const items = Array.isArray(data.items) ? data.items : [];
  return { items: items.map(mapBookmark), total: data.total ?? items.length };
}

export async function createBookmark(data: BookmarkCreate): Promise<Bookmark> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const row = await request<any>('/api/bookmarks', {
    method: 'POST',
    body: JSON.stringify(data),
  });
  return mapBookmark(row);
}

export async function updateBookmark(id: string, data: BookmarkUpdate): Promise<Bookmark> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const row = await request<any>(`/api/bookmarks/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
  return mapBookmark(row);
}

export async function deleteBookmark(id: string): Promise<void> {
  await request<void>(`/api/bookmarks/${id}`, { method: 'DELETE' });
}

export async function getCollections(): Promise<{ items: BookmarkCollection[]; total: number }> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const data = await request<any>('/api/bookmarks/collections');
  const items = Array.isArray(data.items) ? data.items : [];
  return { items: items.map(mapCollection), total: data.total ?? items.length };
}

export async function createCollection(data: {
  title: string;
  bookmark_ids?: string[];
  tags?: string[];
  is_starred?: boolean;
}): Promise<BookmarkCollection> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const row = await request<any>('/api/bookmarks/collections', {
    method: 'POST',
    body: JSON.stringify(data),
  });
  return mapCollection(row);
}
