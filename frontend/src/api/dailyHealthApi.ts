import { request } from './client';

export interface DailyHealth {
  date: string;
  solar_term: string;
  season: string;
  season_advice: string;
  health_tips: string[];
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function mapDailyHealth(raw: any): DailyHealth {
  const seasonAdvice = Array.isArray(raw.season_advice)
    ? raw.season_advice.join('；')
    : raw.season_advice ?? '';

  const tips: string[] = [
    ...(Array.isArray(raw.constitution_tips) ? raw.constitution_tips : []),
    ...(Array.isArray(raw.season_advice) ? raw.season_advice : []),
  ];

  return {
    date: raw.date ?? '',
    solar_term: raw.solar_term ?? '',
    season: raw.season ?? '',
    season_advice: seasonAdvice,
    health_tips: tips,
  };
}

const FALLBACK_SOLAR_TERMS: Array<[number, number, string]> = [
  [2, 4, '立春'], [2, 19, '雨水'], [3, 6, '惊蛰'], [3, 21, '春分'],
  [4, 5, '清明'], [4, 20, '谷雨'], [5, 6, '立夏'], [5, 21, '小满'],
  [6, 6, '芒种'], [6, 21, '夏至'], [7, 7, '小暑'], [7, 23, '大暑'],
  [8, 7, '立秋'], [8, 23, '处暑'], [9, 8, '白露'], [9, 23, '秋分'],
  [10, 8, '寒露'], [10, 23, '霜降'], [11, 7, '立冬'], [11, 22, '小雪'],
  [12, 7, '大雪'], [12, 22, '冬至'], [1, 6, '小寒'], [1, 20, '大寒'],
];

function computeSolarTerm(date: Date): string {
  const month = date.getMonth() + 1;
  const day = date.getDate();
  let current = '小寒';
  for (const [m, d, name] of FALLBACK_SOLAR_TERMS) {
    if (month > m || (month === m && day >= d)) {
      current = name;
    }
  }
  return current;
}

export async function getDailyHealth(): Promise<DailyHealth> {
  try {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const raw = await request<any>('/api/daily-health');
    return mapDailyHealth(raw);
  } catch {
    const solarTerm = computeSolarTerm(new Date());
    return {
      date: new Date().toISOString().slice(0, 10),
      solar_term: solarTerm,
      season: '',
      season_advice: '注意饮食均衡，适当运动，保持心情舒畅。',
      health_tips: [],
    };
  }
}
