import { request } from './client';

export interface Herb {
  id: string;
  name: string;
  aliases?: string | string[] | null;
  category: string;
  nature: string;
  flavor: string;
  meridian: string;
  efficacy: string;
  description: string;
  toxicity: string;
  dosage: string;
  contraindications: string;
}

export interface PaginatedHerbs {
  items: Herb[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
}

export interface HerbFormulaItem {
  id: string;
  name: string;
  category: string;
  efficacy: string;
}

export interface HerbCombinationItem {
  name: string;
  count: number;
}

export interface HerbFormulasResponse {
  herb_name: string;
  formulas: HerbFormulaItem[];
  common_combinations: HerbCombinationItem[];
}

const MOCK_HERBS: Herb[] = [
  {
    id: '1',
    name: '黄芪',
    category: '补气药',
    nature: '温',
    flavor: '甘',
    meridian: '脾、肺',
    efficacy: '补气升阳，固表止汗，利水消肿',
    description:
      '黄芪为豆科植物蒙古黄芪或膜荚黄芪的干燥根。味甘，性微温。归脾、肺经。具有补气升阳，固表止汗，利水消肿，生津养血，行滞通痹，托毒排脓，敛疮生肌之功效。',
    toxicity: '无毒',
    dosage: '9-30g',
    contraindications: '表实邪盛、气滞湿阻、食积内停、阴虚阳亢者忌服',
  },
  {
    id: '2',
    name: '当归',
    category: '补血药',
    nature: '温',
    flavor: '甘、辛',
    meridian: '肝、心、脾',
    efficacy: '补血活血，调经止痛，润肠通便',
    description:
      '当归为伞形科植物当归的干燥根。味甘、辛，性温。归肝、心、脾经。具有补血活血，调经止痛，润肠通便之功效。',
    toxicity: '无毒',
    dosage: '6-12g',
    contraindications: '湿盛中满、大便泄泻者忌服',
  },
  {
    id: '3',
    name: '甘草',
    category: '补气药',
    nature: '平',
    flavor: '甘',
    meridian: '心、肺、脾、胃',
    efficacy: '补脾益气，清热解毒，祛痰止咳，缓急止痛',
    description:
      '甘草为豆科植物甘草的干燥根及根茎。味甘，性平。归心、肺、脾、胃经。具有补脾益气，清热解毒，祛痰止咳，缓急止痛，调和诸药之功效。',
    toxicity: '无毒',
    dosage: '2-10g',
    contraindications: '湿盛胀满、浮肿者不宜使用，不宜与京大戟、芫花、甘遂同用',
  },
  {
    id: '4',
    name: '金银花',
    category: '清热药',
    nature: '寒',
    flavor: '甘',
    meridian: '肺、心、胃',
    efficacy: '清热解毒，疏散风热',
    description:
      '金银花为忍冬科植物忍冬的干燥花蕾或带初开的花。味甘，性寒。归肺、心、胃经。具有清热解毒，疏散风热之功效。',
    toxicity: '无毒',
    dosage: '6-15g',
    contraindications: '脾胃虚寒及气虚疮疡脓清者忌服',
  },
];

/** Map backend herb row to frontend Herb interface */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function mapHerb(row: any): Herb {
  const props = row.properties ?? {};
  return {
    id: row.id ?? '',
    name: row.name ?? '',
    category: row.category ?? '',
    nature: row.nature ?? '',
    flavor: row.flavor ?? '',
    meridian: row.meridians ?? row.meridian ?? '',
    efficacy: row.efficacy ?? '',
    description: row.description ?? props['描述'] ?? row.indications ?? '',
    toxicity: row.toxicity ?? '无毒',
    dosage:
      row.dosage ??
      (row.dosage_min_g != null && row.dosage_max_g != null
        ? `${row.dosage_min_g}-${row.dosage_max_g}g`
        : ''),
    contraindications: row.contraindications ?? '',
  };
}

export async function getHerbs(params?: {
  category?: string;
  search?: string;
  page?: number;
  pageSize?: number;
}): Promise<PaginatedHerbs> {
  try {
    const query = new URLSearchParams();
    if (params?.category) query.set('category', params.category);
    if (params?.search) query.set('q', params.search);
    if (params?.page) query.set('page', String(params.page));
    if (params?.pageSize) query.set('pageSize', String(params.pageSize));
    const qs = query.toString();

    // Backend /api/herbs uses search endpoint for text queries
    const url = params?.search
      ? `/api/herbs/search?${qs}`
      : `/api/herbs${qs ? `?${qs}` : ''}`;

    const data = await request<{ items: unknown[]; total?: number; page?: number; pageSize?: number; totalPages?: number }>(url);
    const items = (data.items ?? []).map(mapHerb);
    return {
      items,
      total: data.total ?? items.length,
      page: data.page ?? 1,
      pageSize: data.pageSize ?? 20,
      totalPages: data.totalPages ?? 1,
    };
  } catch {
    // Mock fallback — client-side filtering
    const search = params?.search ?? '';
    const category = params?.category ?? '';
    const page = params?.page ?? 1;
    const pageSize = params?.pageSize ?? 20;
    let result = [...MOCK_HERBS];
    if (search) {
      result = result.filter(
        (h) => h.name.includes(search) || h.efficacy.includes(search),
      );
    }
    if (category) {
      result = result.filter((h) => h.category === category);
    }
    const total = result.length;
    const start = (page - 1) * pageSize;
    const items = result.slice(start, start + pageSize);
    return {
      items,
      total,
      page,
      pageSize,
      totalPages: Math.ceil(total / pageSize) || 1,
    };
  }
}

export async function getHerb(id: string): Promise<Herb> {
  try {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const row = await request<any>(`/api/herbs/${id}`);
    return mapHerb(row);
  } catch {
    const herb = MOCK_HERBS.find((h) => h.id === id);
    if (!herb) throw new Error('药材未找到');
    return herb;
  }
}

export async function getHerbFormulas(herbId: string): Promise<HerbFormulasResponse> {
  const data = await request<HerbFormulasResponse>(`/api/herbs/${herbId}/formulas`);
  return {
    herb_name: data.herb_name ?? '',
    formulas: Array.isArray(data.formulas) ? data.formulas : [],
    common_combinations: Array.isArray(data.common_combinations)
      ? data.common_combinations
      : [],
  };
}
