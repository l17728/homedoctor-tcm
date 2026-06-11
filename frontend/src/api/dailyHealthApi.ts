import { request } from './client';

export interface DailyHealth {
  date: string;
  solar_term: string;
  season_advice: string;
  health_tips: string[];
}

const MOCK_DAILY_HEALTH: DailyHealth = {
  date: new Date().toISOString().slice(0, 10),
  solar_term: '夏至',
  season_advice: '夏季气候炎热，应注意防暑降温，多饮水，适当食用清热解暑的食物如绿豆、西瓜等。',
  health_tips: [
    '保持充足睡眠，适当午休',
    '饮食清淡，少食辛辣油腻',
    '适度运动，避免在烈日下长时间活动',
  ],
};

/** Get solar term / season info based on current date */
function computeSolarTerm(date: Date): string {
  const month = date.getMonth() + 1;
  const day = date.getDate();
  const terms: Array<[number, number, string]> = [
    [2, 4, '立春'], [2, 19, '雨水'], [3, 6, '惊蛰'], [3, 21, '春分'],
    [4, 5, '清明'], [4, 20, '谷雨'], [5, 6, '立夏'], [5, 21, '小满'],
    [6, 6, '芒种'], [6, 21, '夏至'], [7, 7, '小暑'], [7, 23, '大暑'],
    [8, 7, '立秋'], [8, 23, '处暑'], [9, 8, '白露'], [9, 23, '秋分'],
    [10, 8, '寒露'], [10, 23, '霜降'], [11, 7, '立冬'], [11, 22, '小雪'],
    [12, 7, '大雪'], [12, 22, '冬至'], [1, 6, '小寒'], [1, 20, '大寒'],
  ];
  let current = '小寒';
  for (const [m, d, name] of terms) {
    if (month > m || (month === m && day >= d)) {
      current = name;
    }
  }
  return current;
}

function getSeasonAdvice(solarTerm: string): string {
  const advices: Record<string, string> = {
    '立春': '春季阳气初生，宜早睡早起，舒缓运动，助阳气升发。',
    '雨水': '雨水时节湿气渐重，宜健脾祛湿，适当食用薏仁、山药等。',
    '惊蛰': '万物复苏，宜养肝护肝，保持心情舒畅，适当户外运动。',
    '春分': '阴阳平衡之时，饮食宜清淡均衡，忌偏热偏寒。',
    '清明': '气候温和，宜踏青郊游，疏肝理气，保持心情愉悦。',
    '谷雨': '春季最后一个节气，湿气渐重，宜祛湿健脾。',
    '立夏': '夏季开始，宜养心安神，饮食清淡，避免贪凉。',
    '小满': '天气渐热，宜清热利湿，多食蔬果，少吃油腻。',
    '芒种': '暑湿渐重，宜清热解暑，保证充足睡眠。',
    '夏至': '阳气最旺，宜晚睡早起，适当午休，避免烈日下久留。',
    '小暑': '天气炎热，宜防暑降温，多饮水，食用绿豆、西瓜等解暑食物。',
    '大暑': '一年中最热时节，宜静养，避免剧烈运动，注意防暑。',
    '立秋': '秋季开始，宜养肺润燥，多食梨、百合等润肺食物。',
    '处暑': '暑气渐消，宜早睡早起，适当增加运动量。',
    '白露': '天气转凉，注意保暖，预防秋燥，多饮温水。',
    '秋分': '阴阳平衡，宜调和阴阳，饮食温润。',
    '寒露': '寒气渐重，宜保暖润燥，少食辛辣。',
    '霜降': '深秋时节，宜进补养阴，为入冬做准备。',
    '立冬': '冬季开始，宜温补养藏，多食温热食物。',
    '小雪': '天气渐寒，宜温补，适当食用羊肉、栗子等温补食物。',
    '大雪': '寒冷加剧，注意保暖，宜温补，适当进补。',
    '冬至': '阴极阳生，宜温补，食用饺子、汤圆等传统食物。',
    '小寒': '寒冷时节，宜温补御寒，注意防寒保暖。',
    '大寒': '一年中最冷时节，宜大补，适当食用温热滋补食物。',
  };
  return advices[solarTerm] ?? '注意饮食均衡，适当运动，保持心情舒畅。';
}

export async function getDailyHealth(): Promise<DailyHealth> {
  try {
    return await request<DailyHealth>('/api/daily-health');
  } catch {
    const solarTerm = computeSolarTerm(new Date());
    return {
      ...MOCK_DAILY_HEALTH,
      date: new Date().toISOString().slice(0, 10),
      solar_term: solarTerm,
      season_advice: getSeasonAdvice(solarTerm),
    };
  }
}
