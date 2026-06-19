import { request, requestUpload } from './client';

/**
 * 知识库 Hub API 客户端
 *
 * 对应后端 /api/knowledge-hub/* 路由：
 *   - GET  /search               搜索（全文 + 类型/分类/标签过滤）
 *   - GET  /entities/{id}        实体详情（含关联摘要）
 *   - GET  /entities/{id}/relationships  关联列表
 *   - GET  /types                各类型计数
 *   - POST /import               文本导入（AI 提取）
 *   - POST /import-file          文件导入（AI 提取）
 *   - GET  /popular              热门（按浏览次数）
 *   - GET  /recent               最近（按创建时间）
 */

/** 实体类型枚举（与后端 node_type 一致） */
export type EntityType =
  | 'herb'
  | 'formula'
  | 'therapy'
  | 'symptom'
  | 'tea_recipe'
  | 'health_method'
  | 'article'
  | string;

/** 实体类型 → 中文标签 */
export const ENTITY_TYPE_LABEL: Record<string, string> = {
  herb: '中药',
  formula: '方剂',
  therapy: '理疗',
  symptom: '症状',
  tea_recipe: '代茶',
  health_method: '养生',
  article: '文章',
};

/** 实体类型 → 卡片边框色（CSS 颜色，与 spec 卡片规范一致） */
export const ENTITY_TYPE_BORDER: Record<string, string> = {
  herb: '#52c41a',
  formula: '#1890ff',
  therapy: '#722ed1',
  symptom: '#faad14',
  tea_recipe: '#13c2c2',
  health_method: '#20c997',
  article: '#8c8c8c',
};

/** 实体类型 → AntD Tag 颜色 */
export const ENTITY_TYPE_TAG_COLOR: Record<string, string> = {
  herb: 'green',
  formula: 'blue',
  therapy: 'purple',
  symptom: 'orange',
  tea_recipe: 'cyan',
  health_method: 'geekblue',
  article: 'default',
};

/** 关联关系类型 → 中文标签（与知识图谱 EDGE_COLORS 对齐） */
export const RELATION_TYPE_LABEL: Record<string, string> = {
  组成: '组成方剂',
  主治: '主治症状',
  配伍禁忌: '配伍禁忌',
  中西药交互: '中西药交互',
  contains: '包含',
  treats: '主治',
  related: '相关',
};

/** 关联关系类型 → 是否警示类（用于卡片前缀 ⚠ 图标） */
export const RELATION_TYPE_WARNING: Record<string, boolean> = {
  配伍禁忌: true,
  中西药交互: true,
};

/** 关联关系类型 → 分组颜色 */
export const RELATION_TYPE_COLOR: Record<string, string> = {
  组成: '#1890ff',
  主治: '#52c41a',
  配伍禁忌: '#ff4d4f',
  中西药交互: '#faad14',
  contains: '#1890ff',
  treats: '#52c41a',
  related: '#8c8c8c',
};

export interface KnowledgeEntity {
  id: string;
  type: EntityType;
  title: string;
  summary: string;
  category: string;
  tags: string[];
  keywords: string[];
  viewCount: number;
  relationshipCount: number;
  source: string;
  createdAt: string;
  updatedAt: string;
}

export interface KnowledgeEntityDetail extends KnowledgeEntity {
  /** 完整描述（详情抽屉展开用） */
  description?: string;
  /** 已按关系类型分组的关联摘要：{ '组成方剂': [{id,label,type}], ... } */
  groupedRelationships?: Record<string, KnowledgeRelationshipItem[]>;
}

export interface KnowledgeRelationshipItem {
  id: string;
  label: string;
  type: EntityType;
}

export interface KnowledgeRelationship {
  source: string;
  target: string;
  type: string;
  /** 冗余字段：关联对端的展示信息（后端可能提供） */
  sourceLabel?: string;
  targetLabel?: string;
  targetType?: EntityType;
}

export interface SearchFacets {
  types?: Record<string, number>;
  categories?: Record<string, number>;
  tags?: Record<string, number>;
}

export interface SearchResult {
  items: KnowledgeEntity[];
  total: number;
  facets?: SearchFacets;
}

export interface TypeCounts {
  [type: string]: number;
}

export interface ImportPreview {
  id?: string;
  type: EntityType;
  category: string;
  title: string;
  summary: string;
  tags: string[];
  keywords: string[];
  relationships: KnowledgeRelationship[];
  wordCount?: number;
}

/** 后端返回的原始行（snake_case），通过 mapEntity 统一规整 */
interface EntityRow {
  id?: string;
  type?: string;
  node_type?: string;
  title?: string;
  label?: string;
  name?: string;
  summary?: string;
  description?: string;
  category?: string;
  tags?: string[] | string | null;
  keywords?: string[] | string | null;
  view_count?: number;
  viewCount?: number;
  relationship_count?: number;
  relationshipCount?: number;
  source?: string;
  source_name?: string;
  created_at?: string;
  updatedAt?: string;
  updated_at?: string;
  properties?: Record<string, unknown> | string | null;
  search_text?: string;
}

function toStringArray(v: unknown): string[] {
  if (Array.isArray(v)) {
    return v.map((x) => String(x)).filter(Boolean);
  }
  if (typeof v === 'string' && v.trim()) {
    // 兼容 JSON 字符串或逗号/顿号分隔
    const trimmed = v.trim();
    if (trimmed.startsWith('[')) {
      try {
        const parsed = JSON.parse(trimmed) as unknown;
        return toStringArray(parsed);
      } catch {
        /* fallthrough */
      }
    }
    return trimmed
      .split(/[,，、\s]+/)
      .map((s) => s.trim())
      .filter(Boolean);
  }
  return [];
}

function mapEntity(row: EntityRow): KnowledgeEntity {
  const type = row.type ?? row.node_type ?? 'article';
  const tags = toStringArray(row.tags);
  const keywords =
    toStringArray(row.keywords).length > 0
      ? toStringArray(row.keywords)
      : tags.slice(0, 6);
  return {
    id: row.id ?? '',
    type,
    title: row.title ?? row.label ?? row.name ?? '',
    summary: row.summary ?? row.description ?? '',
    category: row.category ?? '',
    tags,
    keywords,
    viewCount: row.viewCount ?? row.view_count ?? 0,
    relationshipCount: row.relationshipCount ?? row.relationship_count ?? 0,
    source: row.source ?? row.source_name ?? '系统知识库',
    createdAt: row.created_at ?? '',
    updatedAt: row.updated_at ?? row.updatedAt ?? '',
  };
}

function mapRelationship(
  row: Record<string, unknown>,
): KnowledgeRelationship {
  return {
    source: String(row.source ?? row.from ?? ''),
    target: String(row.target ?? row.to ?? ''),
    type: String(row.type ?? row.edge_type ?? row.relation ?? 'related'),
    sourceLabel:
      typeof row.source_label === 'string'
        ? row.source_label
        : typeof row.sourceLabel === 'string'
          ? row.sourceLabel
          : undefined,
    targetLabel:
      typeof row.target_label === 'string'
        ? row.target_label
        : typeof row.targetLabel === 'string'
          ? row.targetLabel
          : undefined,
    targetType:
      (typeof row.target_type === 'string'
        ? row.target_type
        : typeof row.targetType === 'string'
          ? row.targetType
          : undefined) ?? undefined,
  };
}

function mapImportPreview(
  row: Record<string, unknown>,
): ImportPreview {
  return {
    id: typeof row.id === 'string' ? row.id : undefined,
    type: String(row.type ?? row.node_type ?? 'article'),
    category: String(row.category ?? ''),
    title: String(row.title ?? row.name ?? ''),
    summary: String(row.summary ?? row.description ?? ''),
    tags: toStringArray(row.tags),
    keywords:
      toStringArray(row.keywords).length > 0
        ? toStringArray(row.keywords)
        : toStringArray(row.tags).slice(0, 6),
    relationships: Array.isArray(row.relationships)
      ? (row.relationships as Record<string, unknown>[]).map(mapRelationship)
      : [],
    wordCount:
      typeof row.word_count === 'number'
        ? row.word_count
        : typeof row.wordCount === 'number'
          ? row.wordCount
          : undefined,
  };
}

/** 将扁平关系列表按 type 分组为 { 组成方剂: [...], 主治症状: [...] } */
export function groupRelationships(
  relationships: KnowledgeRelationship[],
  currentEntityId: string,
): Record<string, KnowledgeRelationshipItem[]> {
  const groups: Record<string, KnowledgeRelationshipItem[]> = {};
  for (const rel of relationships) {
    const isSource = rel.source === currentEntityId;
    const otherId = isSource ? rel.target : rel.source;
    const otherLabel = isSource ? rel.targetLabel : rel.sourceLabel;
    if (!otherId) continue;
    const groupKey = RELATION_TYPE_LABEL[rel.type] ?? rel.type;
    if (!groups[groupKey]) groups[groupKey] = [];
    groups[groupKey].push({
      id: otherId,
      label: otherLabel ?? otherId,
      type: (isSource ? rel.targetType : undefined) ?? 'article',
    });
  }
  return groups;
}

export interface SearchParams {
  q?: string;
  type?: string;
  category?: string;
  tag?: string;
  page?: number;
  pageSize?: number;
}

export async function searchKnowledge(
  params: SearchParams,
): Promise<SearchResult> {
  const query = new URLSearchParams();
  if (params.q) query.set('q', params.q);
  if (params.type && params.type !== 'all') query.set('type', params.type);
  if (params.category) query.set('category', params.category);
  if (params.tag) query.set('tag', params.tag);
  if (params.page) query.set('page', String(params.page));
  if (params.pageSize) query.set('pageSize', String(params.pageSize));
  const qs = query.toString();
  const data = await request<{
    items?: EntityRow[];
    total?: number;
    facets?: SearchFacets;
  }>(`/api/knowledge-hub/search${qs ? `?${qs}` : ''}`);
  const items = (data.items ?? []).map(mapEntity);
  return {
    items,
    total: data.total ?? items.length,
    facets: data.facets,
  };
}

export async function getEntity(id: string): Promise<KnowledgeEntityDetail> {
  const data = await request<EntityRow & { relationships?: Record<string, unknown>[]; grouped_relationships?: Record<string, unknown> }>(
    `/api/knowledge-hub/entities/${encodeURIComponent(id)}`,
  );
  const base = mapEntity(data);
  const relationships = Array.isArray(data.relationships)
    ? data.relationships.map(mapRelationship)
    : [];
  return {
    ...base,
    description: data.description ?? data.summary ?? '',
    groupedRelationships: groupRelationships(relationships, id),
  };
}

export async function getEntityRelationships(
  id: string,
): Promise<KnowledgeRelationship[]> {
  const data = await request<unknown[]>(
    `/api/knowledge-hub/entities/${encodeURIComponent(id)}/relationships`,
  );
  if (!Array.isArray(data)) return [];
  return data.map((r) =>
    mapRelationship(r as Record<string, unknown>),
  );
}

export async function getEntityTypes(): Promise<TypeCounts> {
  const data = await request<{ facets: TypeCounts; total: number } | TypeCounts>('/api/knowledge-hub/types');
  if (data && typeof data === 'object' && 'facets' in data) {
    return (data as { facets: TypeCounts }).facets;
  }
  return (data as TypeCounts) ?? {};
}

export interface ImportTextParams {
  title?: string;
  content: string;
}

export async function importText(
  params: ImportTextParams,
): Promise<ImportPreview> {
  const data = await request<Record<string, unknown>>(
    '/api/knowledge-hub/import',
    {
      method: 'POST',
      body: JSON.stringify({
        title: params.title ?? '',
        content: params.content,
      }),
    },
  );
  return mapImportPreview(data);
}

export async function importFile(file: File): Promise<ImportPreview> {
  const form = new FormData();
  form.append('file', file);
  const data = await requestUpload<Record<string, unknown>>(
    '/api/knowledge-hub/import-file',
    form,
  );
  return mapImportPreview(data);
}

/** 通过 URL 导入文章（网页正文提取 + AI 结构化） */
export async function importUrl(url: string): Promise<ImportPreview> {
  const data = await request<Record<string, unknown>>(
    '/api/knowledge-hub/import-url',
    {
      method: 'POST',
      body: JSON.stringify({ url }),
    },
  );
  return mapImportPreview(data);
}

/** 通过视频 URL 导入（YouTube/B站字幕提取 + AI 结构化） */
export async function importVideoUrl(url: string): Promise<ImportPreview> {
  const data = await request<Record<string, unknown>>(
    '/api/knowledge-hub/import-video-url',
    {
      method: 'POST',
      body: JSON.stringify({ url }),
    },
  );
  return mapImportPreview(data);
}

export async function getPopular(limit = 12): Promise<KnowledgeEntity[]> {
  const data = await request<EntityRow[] | { items?: EntityRow[] }>(
    `/api/knowledge-hub/popular?limit=${limit}`,
  );
  const items = Array.isArray(data) ? data : data?.items ?? [];
  return items.map(mapEntity);
}

export async function getRecent(limit = 12): Promise<KnowledgeEntity[]> {
  const data = await request<EntityRow[] | { items?: EntityRow[] }>(
    `/api/knowledge-hub/recent?limit=${limit}`,
  );
  const items = Array.isArray(data) ? data : data?.items ?? [];
  return items.map(mapEntity);
}
