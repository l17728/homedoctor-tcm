import { request } from './client';

/** 疗法分类 — spec §9.6 */
export const THERAPY_CATEGORIES = [
  '刮痧',
  '推拿',
  '艾灸',
  '拔罐',
  '针刺',
  '刺血',
] as const;

export interface Therapy {
  id: string;
  name: string;
  category: string;
  riskLevel: string;
  homeUseSafe: boolean;
  displayOnly: boolean;
  description: string;
  indications: string;
  contraindications: string;
  operationSteps: string;
  duration: string;
  frequency: string;
  precautions: string;
}

export interface TherapyAcupoint {
  acupoint_name: string;
  location: string;
  function: string;
  meridian: string;
  is_primary: boolean;
}

export interface TherapySafetyRule {
  rule_type: string;
  condition_text: string;
  action: string;
  severity: string;
  therapy_category: string;
}

export interface TherapyDetail extends Therapy {
  acupoints: TherapyAcupoint[];
  safetyRules: TherapySafetyRule[];
}

export interface PaginatedTherapies {
  items: Therapy[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
}

/** Raw backend row shape (snake_case, int booleans). */
interface TherapyRow {
  id?: string;
  name?: string;
  category?: string;
  risk_level?: string;
  home_use_safe?: number | boolean;
  display_only?: number | boolean;
  description?: string;
  indications?: string;
  contraindications?: string;
  operation_steps?: string;
  duration?: string;
  frequency?: string;
  precautions?: string;
  properties?: string | Record<string, unknown>;
  acupoints?: Array<Record<string, unknown>>;
  safety_rules?: Array<Record<string, unknown>>;
}

function toBool(v: number | boolean | undefined): boolean {
  if (typeof v === 'boolean') return v;
  if (typeof v === 'number') return v !== 0;
  return false;
}

function mapTherapy(row: TherapyRow): Therapy {
  return {
    id: row.id ?? '',
    name: row.name ?? '',
    category: row.category ?? '',
    riskLevel: row.risk_level ?? 'medium',
    homeUseSafe: toBool(row.home_use_safe),
    displayOnly: toBool(row.display_only),
    description: row.description ?? '',
    indications: row.indications ?? '',
    contraindications: row.contraindications ?? '',
    operationSteps: row.operation_steps ?? '',
    duration: row.duration ?? '',
    frequency: row.frequency ?? '',
    precautions: row.precautions ?? '',
  };
}

function mapTherapyDetail(row: TherapyRow): TherapyDetail {
  const base = mapTherapy(row);
  const rawAcupoints = Array.isArray(row.acupoints) ? row.acupoints : [];
  const acupoints: TherapyAcupoint[] = rawAcupoints.map((ap) => ({
    acupoint_name: (ap['acupoint_name'] as string) ?? '',
    location: (ap['location'] as string) ?? '',
    function: (ap['function'] as string) ?? '',
    meridian: (ap['meridian'] as string) ?? '',
    is_primary: toBool((ap['is_primary'] as number | boolean | undefined)),
  }));
  const rawRules = Array.isArray(row.safety_rules) ? row.safety_rules : [];
  const safetyRules: TherapySafetyRule[] = rawRules.map((r) => ({
    rule_type: (r['rule_type'] as string) ?? '',
    condition_text: (r['condition_text'] as string) ?? '',
    action: (r['action'] as string) ?? '',
    severity: (r['severity'] as string) ?? '',
    therapy_category: (r['therapy_category'] as string) ?? '',
  }));
  return { ...base, acupoints, safetyRules };
}

// ---------------------------------------------------------------------------
// Mock data — meaningful TCM therapy records for offline / demo rendering.
// ---------------------------------------------------------------------------
const MOCK_THERAPIES: Therapy[] = [
  {
    id: 'm-guasha-1',
    name: '背部刮痧',
    category: '刮痧',
    riskLevel: 'low',
    homeUseSafe: true,
    displayOnly: false,
    description:
      '以牛角或玉石刮板，在背部涂介质后沿经络方向刮拭，使局部出现痧痕，达到疏通经络、活血排毒之效。',
    indications: '感冒、颈肩酸痛、暑湿困倦、肌肉僵硬',
    contraindications: '皮肤破损、凝血障碍、孕妇腰骶部、过饥过饱',
    operationSteps:
      '1. 清洁背部并涂抹刮痧油\n2. 自上而下沿膀胱经刮拭\n3. 每部位刮20-30次至出痧\n4. 力度均匀，避免破损皮肤',
    duration: '15-20分钟',
    frequency: '每周1-2次，间隔3-5天',
    precautions: '刮后避风寒、饮温水，4小时内不宜洗澡',
  },
  {
    id: 'm-tuina-1',
    name: '颈肩推拿',
    category: '推拿',
    riskLevel: 'low',
    homeUseSafe: true,
    displayOnly: false,
    description:
      '运用按、揉、拿、滚等手法作用于颈肩部肌肉与穴位，缓解肌肉紧张，改善局部血液循环。',
    indications: '颈椎病、肩周炎、落枕、久坐疲劳',
    contraindications: '颈椎骨折、肿瘤、急性炎症期、皮肤感染',
    operationSteps:
      '1. 患者坐位放松\n2. 拿揉肩颈部5分钟\n3. 点按风池、肩井、天宗穴\n4. 滚法放松斜方肌\n5. 轻柔牵伸颈部',
    duration: '20-30分钟',
    frequency: '每日或隔日1次',
    precautions: '手法宜轻柔，忌暴力扳颈；头晕即止',
  },
  {
    id: 'm-moxa-1',
    name: '足三里保健灸',
    category: '艾灸',
    riskLevel: 'low',
    homeUseSafe: true,
    displayOnly: false,
    description:
      '以艾条悬灸足三里穴，温通经络、补益脾胃，是经典的延年益寿保健灸法。',
    indications: '脾胃虚弱、免疫力低下、疲劳乏力、虚寒体质',
    contraindications: '阴虚火旺、实热证、皮肤过敏、孕妇慎用',
    operationSteps:
      '1. 定位足三里（外膝眼下3寸）\n2. 点燃艾条\n3. 距皮肤2-3cm悬灸\n4. 局部温热为度，左右各10-15分钟',
    duration: '20-30分钟',
    frequency: '每周2-3次，长期坚持',
    precautions: '防止烫伤，灸后避风寒、饮温水',
  },
  {
    id: 'm-cupping-1',
    name: '背俞穴拔罐',
    category: '拔罐',
    riskLevel: 'medium',
    homeUseSafe: true,
    displayOnly: false,
    description:
      '在背部膀胱经穴位留罐或走罐，通过负压吸引改善气血运行，祛湿通络。',
    indications: '腰背酸痛、感冒、湿气重、肌肉劳损',
    contraindications: '皮肤溃疡、水肿、凝血障碍、高热抽搐',
    operationSteps:
      '1. 患者俯卧暴露背部\n2. 选择适当口径火罐\n3. 闪火法吸附于背俞穴\n4. 留罐5-10分钟\n5. 起罐时按压皮肤',
    duration: '10-15分钟',
    frequency: '每周1次，每次不超过8个罐',
    precautions: '留罐时间不宜过长以防起泡；罐印未退不宜重复拔',
  },
  {
    id: 'm-acup-1',
    name: '针刺合谷太冲',
    category: '针刺',
    riskLevel: 'high',
    homeUseSafe: false,
    displayOnly: true,
    description:
      '四关穴针刺法（合谷+太冲），疏通气血、镇静止痛，属专业医师操作项目，仅供了解。',
    indications: '头痛、失眠、郁证、面瘫、痛经',
    contraindications: '孕妇禁用、出血倾向、极度疲劳饥饿',
    operationSteps:
      '【仅供了解，须由执业中医师操作】\n1. 常规消毒穴位\n2. 合谷直刺0.5-1寸\n3. 太冲斜刺0.5-0.8寸\n4. 行针得气后留针20分钟',
    duration: '20-30分钟',
    frequency: '隔日或每周2-3次，10次为一疗程',
    precautions: '仅限医疗机构由执业医师操作，禁止自行施针',
  },
  {
    id: 'm-bloodlet-1',
    name: '耳尖刺血',
    category: '刺血',
    riskLevel: 'high',
    homeUseSafe: false,
    displayOnly: true,
    description:
      '耳尖穴点刺放血数滴，清热泻火、平肝明目，属专业医师操作项目，仅供了解。',
    indications: '高热、急性结膜炎、高血压头痛、麦粒肿',
    contraindications: '凝血障碍、贫血、体质虚弱、孕妇',
    operationSteps:
      '【仅供了解，须由执业中医师操作】\n1. 揉搓耳廓使其充血\n2. 常规消毒耳尖\n3. 三棱针快速点刺\n4. 挤出血液5-10滴\n5. 消毒按压止血',
    duration: '5-10分钟',
    frequency: '隔日1次，3次为一疗程',
    precautions: '严格无菌操作，仅限医疗机构由执业医师操作',
  },
];

export async function getTherapies(params?: {
  page?: number;
  pageSize?: number;
  category?: string;
}): Promise<PaginatedTherapies> {
  try {
    const query = new URLSearchParams();
    if (params?.page) query.set('page', String(params.page));
    if (params?.pageSize) query.set('pageSize', String(params.pageSize));
    if (params?.category) query.set('category', params.category);
    const qs = query.toString();

    const data = await request<{
      items: TherapyRow[];
      total?: number;
      page?: number;
      pageSize?: number;
      totalPages?: number;
    }>(`/api/therapies${qs ? `?${qs}` : ''}`);
    const items = (data.items ?? []).map(mapTherapy);
    return {
      items,
      total: data.total ?? items.length,
      page: data.page ?? 1,
      pageSize: data.pageSize ?? 20,
      totalPages: data.totalPages ?? 1,
    };
  } catch {
    // Mock fallback — client-side category filtering + pagination
    const category = params?.category ?? '';
    const page = params?.page ?? 1;
    const pageSize = params?.pageSize ?? 20;
    let result = [...MOCK_THERAPIES];
    if (category) {
      result = result.filter((t) => t.category === category);
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

export async function searchTherapies(params: {
  q: string;
  category?: string;
}): Promise<Therapy[]> {
  try {
    const query = new URLSearchParams({ q: params.q });
    if (params.category) query.set('category', params.category);
    const data = await request<{ items: TherapyRow[]; total?: number }>(
      `/api/therapies/search?${query.toString()}`,
    );
    return (data.items ?? []).map(mapTherapy);
  } catch {
    // Mock fallback — match name / description / indications / category
    const q = params.q;
    let result = MOCK_THERAPIES.filter(
      (t) =>
        t.name.includes(q) ||
        t.description.includes(q) ||
        t.indications.includes(q) ||
        t.category.includes(q),
    );
    if (params.category) {
      result = result.filter((t) => t.category === params.category);
    }
    return result;
  }
}

export async function getTherapy(id: string): Promise<TherapyDetail> {
  try {
    const row = await request<TherapyRow>(`/api/therapies/${id}`);
    return mapTherapyDetail(row);
  } catch {
    const therapy = MOCK_THERAPIES.find((t) => t.id === id);
    if (!therapy) throw new Error('未找到该疗法');
    return { ...therapy, acupoints: [], safetyRules: [] };
  }
}
