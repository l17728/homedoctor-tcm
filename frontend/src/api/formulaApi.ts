import { request } from './client';

export interface ModificationItem {
  symptom?: string;      // 症状/场景 (e.g., "兼有食积者")
  action?: string;       // 加减 (e.g., "加山楂、神曲")
  add?: string[];        // 加 (herbs to add)
  remove?: string[];     // 减 (herbs to remove)
  note?: string;         // 备注
}

export interface Formula {
  id: string;
  name: string;
  category: string;
  composition: string;
  efficacy: string;
  indication: string;
  usage: string;
  description: string;
  modifications?: string[] | ModificationItem[] | string;
  modifications_structured?: ModificationItem[];
  derived_from_id?: string | null;
}

export interface PaginatedFormulas {
  items: Formula[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
}

const MOCK_FORMULAS: Formula[] = [
  {
    id: '1',
    name: '四君子汤',
    category: '补益剂',
    composition: '人参、白术、茯苓、甘草',
    efficacy: '益气健脾',
    indication: '脾胃气虚证，症见面色萎白、语声低微、气短乏力、食少便溏',
    usage: '水煎服',
    description:
      '四君子汤出自《太平惠民和剂局方》，为补气的基础方。后世诸多健脾益气的方剂均从此方衍化而来，故有"天下补气第一方"之称。',
  },
  {
    id: '2',
    name: '六味地黄丸',
    category: '补益剂',
    composition: '熟地黄、山茱萸、山药、泽泻、茯苓、牡丹皮',
    efficacy: '滋阴补肾',
    indication: '肾阴虚证，症见头晕耳鸣、腰膝酸软、骨蒸潮热、盗汗遗精',
    usage: '口服，一次8丸，一日3次',
    description:
      '六味地黄丸出自宋代钱乙《小儿药证直诀》，由张仲景《金匮要略》中的肾气丸减去桂枝、附子而成。为滋阴补肾的代表方剂。',
  },
];

/** Map backend formula row to frontend Formula interface */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function mapFormula(row: any): Formula {
  const props = row.properties ?? {};
  // Backend composition is array of objects; stringify for display
  let compositionStr = '';
  if (Array.isArray(row.composition)) {
    compositionStr = row.composition
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      .map((c: any) => (typeof c === 'string' ? c : c.name ?? c.herb ?? JSON.stringify(c)))
      .join('、');
  } else if (typeof row.composition === 'string') {
    compositionStr = row.composition;
  }

  return {
    id: row.id ?? '',
    name: row.name ?? '',
    category: row.category ?? '',
    composition: compositionStr,
    efficacy: row.efficacy ?? '',
    indication: row.indications ?? row.indication ?? '',
    usage: row.usage ?? props['用法'] ?? '',
    description: row.description ?? row.source ?? '',
    modifications: row.modifications ?? undefined,
    modifications_structured: row.modifications_structured ?? undefined,
    derived_from_id: row.derived_from_id ?? null,
  };
}

export async function getFormulas(params?: {
  category?: string;
  search?: string;
  page?: number;
  pageSize?: number;
}): Promise<PaginatedFormulas> {
  try {
    const query = new URLSearchParams();
    if (params?.category) query.set('category', params.category);
    if (params?.page) query.set('page', String(params.page));
    if (params?.pageSize) query.set('pageSize', String(params.pageSize));
    const qs = query.toString();

    const data = await request<{ items: unknown[]; total?: number; page?: number; pageSize?: number; totalPages?: number }>(
      `/api/formulas${qs ? `?${qs}` : ''}`,
    );
    let items = (data.items ?? []).map(mapFormula);

    // Client-side search filter (backend doesn't have search param for formulas)
    if (params?.search) {
      const s = params.search;
      items = items.filter(
        (f) => f.name.includes(s) || f.efficacy.includes(s) || f.composition.includes(s),
      );
    }

    return {
      items,
      total: data.total ?? items.length,
      page: data.page ?? 1,
      pageSize: data.pageSize ?? 20,
      totalPages: data.totalPages ?? 1,
    };
  } catch {
    const search = params?.search ?? '';
    const category = params?.category ?? '';
    const page = params?.page ?? 1;
    const pageSize = params?.pageSize ?? 20;
    let result = [...MOCK_FORMULAS];
    if (search) {
      result = result.filter(
        (f) => f.name.includes(search) || f.efficacy.includes(search),
      );
    }
    if (category) {
      result = result.filter((f) => f.category === category);
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

export async function getFormula(id: string): Promise<Formula> {
  try {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const row = await request<any>(`/api/formulas/${id}`);
    return mapFormula(row);
  } catch {
    const formula = MOCK_FORMULAS.find((f) => f.id === id);
    if (!formula) throw new Error('方剂未找到');
    return formula;
  }
}
