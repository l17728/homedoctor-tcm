import { request } from './client';

export interface Herb {
  id: string;
  name: string;
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

export async function getHerbs(params?: {
  category?: string;
  search?: string;
}): Promise<Herb[]> {
  try {
    const query = new URLSearchParams();
    if (params?.category) query.set('category', params.category);
    if (params?.search) query.set('search', params.search);
    const qs = query.toString();
    return request<Herb[]>(`/api/herbs${qs ? `?${qs}` : ''}`);
  } catch {
    const search = params?.search ?? '';
    const category = params?.category ?? '';
    let result = [...MOCK_HERBS];
    if (search) {
      result = result.filter(
        (h) => h.name.includes(search) || h.efficacy.includes(search),
      );
    }
    if (category) {
      result = result.filter((h) => h.category === category);
    }
    return result;
  }
}

export async function getHerb(id: string): Promise<Herb> {
  try {
    return request<Herb>(`/api/herbs/${id}`);
  } catch {
    const herb = MOCK_HERBS.find((h) => h.id === id);
    if (!herb) throw new Error('药材未找到');
    return herb;
  }
}
