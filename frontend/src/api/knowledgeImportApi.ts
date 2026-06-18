import { request, requestUpload } from './client';

export type ImportFileType = 'pdf' | 'word' | 'txt' | 'image' | 'markdown' | 'unknown';

export interface KnowledgeImportEntry {
  id: string;
  user_id: string;
  entry_type: string;
  title: string;
  content: string | null;
  summary: string | null;
  tags: string[];
  source_type: string | null;
  source_url: string | null;
  is_starred: boolean;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeImportSummary {
  sections: unknown;
  metadata: {
    sections?: number;
    words?: number;
    type?: string;
    empty?: boolean;
  };
  type: ImportFileType;
}

export interface UploadResponse {
  entry_id: string;
  title: string;
  entry_type: string;
  source_url: string | null;
  tags: string[];
  sections_parsed: number;
  word_count: number;
  created_at: string;
  entry: KnowledgeImportEntry;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function mapEntry(row: any): KnowledgeImportEntry {
  return {
    id: row.id ?? '',
    user_id: row.user_id ?? '',
    entry_type: row.entry_type ?? 'document',
    title: row.title ?? '',
    content: row.content ?? null,
    summary: row.summary ?? null,
    tags: Array.isArray(row.tags) ? row.tags : [],
    source_type: row.source_type ?? null,
    source_url: row.source_url ?? null,
    is_starred: !!row.is_starred,
    created_at: row.created_at ?? '',
    updated_at: row.updated_at ?? '',
  };
}

export function detectFileType(filename: string): ImportFileType {
  const lower = (filename ?? '').toLowerCase();
  if (lower.endsWith('.pdf')) return 'pdf';
  if (lower.endsWith('.docx') || lower.endsWith('.doc')) return 'word';
  if (lower.endsWith('.txt') || lower.endsWith('.md')) return 'txt';
  if (lower.match(/\.(jpg|jpeg|png|webp)$/)) return 'image';
  return 'unknown';
}

export const FILE_TYPE_LABEL: Record<ImportFileType, string> = {
  pdf: 'PDF',
  word: 'Word',
  txt: '文本',
  image: '图片',
  markdown: '文本',
  unknown: '未知',
};

export const FILE_TYPE_COLOR: Record<ImportFileType, string> = {
  pdf: 'red',
  word: 'blue',
  txt: 'default',
  image: 'purple',
  markdown: 'default',
  unknown: 'default',
};

export function parseSummary(raw: string | null): KnowledgeImportSummary | null {
  if (!raw) return null;
  try {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const obj = JSON.parse(raw) as any;
    return {
      sections: obj.sections,
      metadata: {
        sections: obj.metadata?.sections ?? 0,
        words: obj.metadata?.words ?? 0,
        type: obj.metadata?.type ?? obj.type ?? '',
        empty: obj.metadata?.empty ?? false,
      },
      type: (obj.type ?? 'unknown') as ImportFileType,
    };
  } catch {
    return null;
  }
}

export function getWordCount(entry: KnowledgeImportEntry): number {
  const summary = parseSummary(entry.summary);
  return summary?.metadata.words ?? 0;
}

export async function uploadKnowledgeFile(file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append('file', file);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const data = await requestUpload<any>('/api/knowledge-import/upload', form);
  return {
    entry_id: data.entry_id ?? '',
    title: data.title ?? '',
    entry_type: data.entry_type ?? 'document',
    source_url: data.source_url ?? null,
    tags: Array.isArray(data.tags) ? data.tags : [],
    sections_parsed: data.sections_parsed ?? 0,
    word_count: data.word_count ?? 0,
    created_at: data.created_at ?? '',
    entry: mapEntry(data.entry ?? {}),
  };
}

export async function getRecentImports(limit = 20): Promise<{ items: KnowledgeImportEntry[]; total: number }> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const data = await request<any>(`/api/knowledge-import/recent?limit=${limit}`);
  const items = Array.isArray(data.items) ? data.items : [];
  return { items: items.map(mapEntry), total: data.total ?? items.length };
}

export async function deleteImport(id: string): Promise<void> {
  await request<void>(`/api/knowledge-import/${id}`, { method: 'DELETE' });
}
