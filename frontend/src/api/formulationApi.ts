import { request } from './client';

/** 王琦九种体质 */
export const CONSTITUTIONS = [
  '平和质',
  '气虚质',
  '阳虚质',
  '阴虚质',
  '痰湿质',
  '湿热质',
  '血瘀质',
  '气郁质',
  '特禀质',
] as const;

/** A scored herb recommendation returned by /recommend. */
export interface HerbRecommendation {
  id: string;
  name: string;
  aliases: string;
  nature: string;
  flavor: string;
  meridians: string;
  efficacy: string;
  indications: string;
  contraindications: string;
  dosageMinG: number | null;
  dosageMaxG: number | null;
  toxicity: string;
  category: string;
  score: number;
  /** Human-readable match reason, e.g. "匹配症状：气虚、乏力". */
  reason: string;
}

export interface SafetyWarning {
  layer: string;
  severity: string;
  title: string;
  detail: string;
  herbs: string[];
  action: string;
  source: string;
}

export interface SafetyCheck {
  safe: boolean;
  warnings: SafetyWarning[];
  checkedHerbs: string[];
  checkedMedicines: string[];
  unknownHerbs: string[];
  unknownMedicines: string[];
}

/** POST /api/formulations/recommend response. */
export interface RecommendResponse {
  recommendations: HerbRecommendation[];
  symptoms: string[];
  constitution: string | null;
  safetyCheck: SafetyCheck;
  disclaimer: string;
}

export interface TeaRecipeHerb {
  name: string;
  doseG: number;
  role: string;
}

/** POST /api/formulations/tea-recipe response. */
export interface TeaRecipeResponse {
  name: string;
  herbs: TeaRecipeHerb[];
  brewing: string;
  efficacy: string;
  symptoms: string[];
  constitution: string | null;
  safetyCheck: SafetyCheck;
  disclaimer: string;
}

/** POST /api/formulations/from-inventory response. */
export interface InventoryRecommendation {
  name: string;
  source: string;
  reason: string;
  inCabinet: boolean;
}

export interface FromInventoryResponse {
  recommendations: InventoryRecommendation[];
  missingSuggestions: HerbRecommendation[];
  symptoms: string[];
  safetyCheck: SafetyCheck;
  disclaimer: string;
}

export interface FormulationRequest {
  symptoms: string[];
  constitution?: string;
  exclude?: string[];
}

// ---------------------------------------------------------------------------
// Raw backend row shapes (snake_case) for mapping.
// ---------------------------------------------------------------------------
interface RawHerbRec {
  id?: string;
  name?: string;
  aliases?: string;
  nature?: string;
  flavor?: string;
  meridians?: string;
  efficacy?: string;
  indications?: string;
  contraindications?: string;
  dosage_min_g?: number | null;
  dosage_max_g?: number | null;
  toxicity?: string;
  category?: string;
  score?: number;
  reason?: string;
}

interface RawSafetyWarning {
  layer?: string;
  severity?: string;
  title?: string;
  detail?: string;
  herbs?: string[];
  action?: string;
  source?: string;
}

interface RawSafetyCheck {
  safe?: boolean;
  warnings?: RawSafetyWarning[];
  checked_herbs?: string[];
  checked_medicines?: string[];
  unknown_herbs?: string[];
  unknown_medicines?: string[];
}

function mapHerbRec(row: RawHerbRec): HerbRecommendation {
  return {
    id: row.id ?? '',
    name: row.name ?? '',
    aliases: row.aliases ?? '',
    nature: row.nature ?? '',
    flavor: row.flavor ?? '',
    meridians: row.meridians ?? '',
    efficacy: row.efficacy ?? '',
    indications: row.indications ?? '',
    contraindications: row.contraindications ?? '',
    dosageMinG: row.dosage_min_g ?? null,
    dosageMaxG: row.dosage_max_g ?? null,
    toxicity: row.toxicity ?? '',
    category: row.category ?? '',
    score: row.score ?? 0,
    reason: row.reason ?? '综合推荐',
  };
}

function mapSafety(s: RawSafetyCheck | undefined): SafetyCheck {
  return {
    safe: s?.safe ?? true,
    warnings: (s?.warnings ?? []).map((w) => ({
      layer: w.layer ?? '',
      severity: w.severity ?? '',
      title: w.title ?? '',
      detail: w.detail ?? '',
      herbs: w.herbs ?? [],
      action: w.action ?? '',
      source: w.source ?? '',
    })),
    checkedHerbs: s?.checked_herbs ?? [],
    checkedMedicines: s?.checked_medicines ?? [],
    unknownHerbs: s?.unknown_herbs ?? [],
    unknownMedicines: s?.unknown_medicines ?? [],
  };
}

// ---------------------------------------------------------------------------
// Mock data — for offline / demo rendering.
// ---------------------------------------------------------------------------
const DISCLAIMER =
  '本推荐仅供参考，不能替代执业中医师当面辨证施治。用药前请咨询专业医师。';

function mockRecommend(symptoms: string[], constitution?: string): RecommendResponse {
  const sym = symptoms.join('、');
  const recs: HerbRecommendation[] = [
    {
      id: 'm-huangqi',
      name: '黄芪',
      aliases: '黄耆',
      nature: '微温',
      flavor: '甘',
      meridians: '脾、肺',
      efficacy: '补气升阳，固表止汗，利水消肿',
      indications: '气虚乏力、食少便溏、表虚自汗',
      contraindications: '表实邪盛、阴虚阳亢者忌服',
      dosageMinG: 9,
      dosageMaxG: 30,
      toxicity: '无毒',
      category: '补气药',
      score: 90,
      reason: `匹配症状：${sym}；补气要药，适合${constitution ?? '气虚'}体质`,
    },
    {
      id: 'm-dangshen',
      name: '党参',
      aliases: '',
      nature: '平',
      flavor: '甘',
      meridians: '脾、肺',
      efficacy: '补中益气，生津养血',
      indications: '脾肺气虚、食少倦怠、气血两亏',
      contraindications: '实证、热证者忌服',
      dosageMinG: 9,
      dosageMaxG: 30,
      toxicity: '无毒',
      category: '补气药',
      score: 75,
      reason: `匹配症状：${sym}；健脾益气，性平温和`,
    },
    {
      id: 'm-gouqi',
      name: '枸杞子',
      aliases: '枸杞',
      nature: '平',
      flavor: '甘',
      meridians: '肝、肾',
      efficacy: '滋补肝肾，益精明目',
      indications: '肝肾阴虚、腰膝酸软、头晕目眩',
      contraindications: '脾虚便溏者慎用',
      dosageMinG: 6,
      dosageMaxG: 12,
      toxicity: '无毒',
      category: '补阴药',
      score: 60,
      reason: '平补肝肾，可作茶饮常服',
    },
  ];
  return {
    recommendations: recs,
    symptoms,
    constitution: constitution ?? null,
    safetyCheck: { safe: true, warnings: [], checkedHerbs: ['黄芪', '党参', '枸杞子'], checkedMedicines: [], unknownHerbs: [], unknownMedicines: [] },
    disclaimer: DISCLAIMER,
  };
}

function mockTeaRecipe(symptoms: string[], constitution?: string): TeaRecipeResponse {
  return {
    name: `${symptoms[0] ?? '调理'}养生代茶饮`,
    herbs: [
      { name: '黄芪', doseG: 6, role: '君药' },
      { name: '枸杞子', doseG: 5, role: '臣药' },
      { name: '甘草', doseG: 3, role: '使药' },
    ],
    brewing:
      '1. 取黄芪6g、枸杞子5g、甘草3g，清水快速冲洗\n2. 放入保温杯，注入500ml沸水\n3. 加盖焖泡10-15分钟后温服\n4. 可反复冲泡2-3次至味淡\n5. 每日1剂，饭后温服，连续不超过7天',
    efficacy: '补气养阴，平补肝肾，温和调理',
    symptoms,
    constitution: constitution ?? null,
    safetyCheck: { safe: true, warnings: [], checkedHerbs: ['黄芪', '枸杞子', '甘草'], checkedMedicines: [], unknownHerbs: [], unknownMedicines: [] },
    disclaimer: DISCLAIMER,
  };
}

function mockFromInventory(symptoms: string[]): FromInventoryResponse {
  return {
    recommendations: [
      {
        name: '感冒清热颗粒',
        source: '药箱',
        reason: `匹配症状：${symptoms.join('、')}；疏风散寒，解表清热`,
        inCabinet: true,
      },
      {
        name: '板蓝根颗粒',
        source: '药箱',
        reason: '清热解毒，可辅助缓解症状',
        inCabinet: true,
      },
    ],
    missingSuggestions: [mockRecommend(symptoms).recommendations[0]!],
    symptoms,
    safetyCheck: { safe: true, warnings: [], checkedHerbs: [], checkedMedicines: ['感冒清热颗粒', '板蓝根颗粒'], unknownHerbs: [], unknownMedicines: [] },
    disclaimer: DISCLAIMER,
  };
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------
export async function recommendHerbs(
  req: FormulationRequest,
): Promise<RecommendResponse> {
  try {
    const data = await request<Record<string, unknown>>(
      '/api/formulations/recommend',
      {
        method: 'POST',
        body: JSON.stringify({
          symptoms: req.symptoms,
          constitution: req.constitution,
          exclude: req.exclude,
        }),
      },
    );
    return {
      recommendations: ((data['recommendations'] as RawHerbRec[]) ?? []).map(
        mapHerbRec,
      ),
      symptoms: (data['symptoms'] as string[]) ?? req.symptoms,
      constitution: (data['constitution'] as string | null) ?? null,
      safetyCheck: mapSafety(data['safety_check'] as RawSafetyCheck | undefined),
      disclaimer: (data['disclaimer'] as string) ?? '',
    };
  } catch {
    return mockRecommend(req.symptoms, req.constitution);
  }
}

export async function generateTeaRecipe(
  req: FormulationRequest,
): Promise<TeaRecipeResponse> {
  try {
    const data = await request<Record<string, unknown>>(
      '/api/formulations/tea-recipe',
      {
        method: 'POST',
        body: JSON.stringify({
          symptoms: req.symptoms,
          constitution: req.constitution,
          exclude: req.exclude,
        }),
      },
    );
    return {
      name: (data['name'] as string) ?? '代茶饮配方',
      herbs: ((data['herbs'] as Array<Record<string, unknown>>) ?? []).map(
        (h) => ({
          name: (h['name'] as string) ?? '',
          doseG: (h['dose_g'] as number) ?? 0,
          role: (h['role'] as string) ?? '',
        }),
      ),
      brewing: (data['brewing'] as string) ?? '',
      efficacy: (data['efficacy'] as string) ?? '',
      symptoms: (data['symptoms'] as string[]) ?? req.symptoms,
      constitution: (data['constitution'] as string | null) ?? null,
      safetyCheck: mapSafety(data['safety_check'] as RawSafetyCheck | undefined),
      disclaimer: (data['disclaimer'] as string) ?? '',
    };
  } catch {
    return mockTeaRecipe(req.symptoms, req.constitution);
  }
}

export async function recommendFromInventory(
  req: FormulationRequest,
): Promise<FromInventoryResponse> {
  try {
    const data = await request<Record<string, unknown>>(
      '/api/formulations/from-inventory',
      {
        method: 'POST',
        body: JSON.stringify({ symptoms: req.symptoms }),
      },
    );
    return {
      recommendations: ((data['recommendations'] as Array<Record<string, unknown>>) ?? []).map(
        (r) => ({
          name: (r['name'] as string) ?? '',
          source: (r['source'] as string) ?? '',
          reason: (r['reason'] as string) ?? '',
          inCabinet: (r['in_cabinet'] as boolean) ?? true,
        }),
      ),
      missingSuggestions: ((data['missing_suggestions'] as RawHerbRec[]) ?? []).map(
        mapHerbRec,
      ),
      symptoms: (data['symptoms'] as string[]) ?? req.symptoms,
      safetyCheck: mapSafety(data['safety_check'] as RawSafetyCheck | undefined),
      disclaimer: (data['disclaimer'] as string) ?? '',
    };
  } catch {
    return mockFromInventory(req.symptoms);
  }
}
