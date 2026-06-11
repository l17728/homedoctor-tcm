import { request } from './client';

export interface Formula {
  id: string;
  name: string;
  category: string;
  composition: string;
  efficacy: string;
  indication: string;
  usage: string;
  description: string;
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

export async function getFormulas(params?: {
  category?: string;
  search?: string;
}): Promise<Formula[]> {
  try {
    const query = new URLSearchParams();
    if (params?.category) query.set('category', params.category);
    if (params?.search) query.set('search', params.search);
    const qs = query.toString();
    return request<Formula[]>(`/api/formulas${qs ? `?${qs}` : ''}`);
  } catch {
    const search = params?.search ?? '';
    const category = params?.category ?? '';
    let result = [...MOCK_FORMULAS];
    if (search) {
      result = result.filter(
        (f) => f.name.includes(search) || f.efficacy.includes(search),
      );
    }
    if (category) {
      result = result.filter((f) => f.category === category);
    }
    return result;
  }
}

export async function getFormula(id: string): Promise<Formula> {
  try {
    return request<Formula>(`/api/formulas/${id}`);
  } catch {
    const formula = MOCK_FORMULAS.find((f) => f.id === id);
    if (!formula) throw new Error('方剂未找到');
    return formula;
  }
}
