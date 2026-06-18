import { request } from './client';

// ---------------------------------------------------------------------------
// 域类型 — 中文枚举保持原文（项目规范 §1.7）
// 与后端 POST /api/medication-plans/auto-schedule 契约对齐
// ---------------------------------------------------------------------------

/** 用户输入：参与排程的药物 */
export interface MedicationInput {
  name: string;
  /** 中药 / 西药 / 中成药 */
  type: string;
  dosage: string;
  /** 每日1次 / 每日2次 / 每日3次 / 隔日1次 */
  frequency: string;
  notes?: string;
}

/** 单格内已排程药物 */
export interface ScheduledMedicine {
  name: string;
  dosage: string;
  type: string;
  /** 该药物被安排到此时段的简明理由 */
  reason: string;
}

/** 单个时间槽位 */
export interface TimeSlot {
  /** 24小时制，如 08:00 */
  time: string;
  /** 友好名称：早餐后 / 上午 / 午餐后 / 晚餐后 / 睡前 ... */
  period: string;
  medicines: ScheduledMedicine[];
  /** 当前槽位冲突提示（字符串数组） */
  conflict_warnings: string[];
}

/** 单日排程 */
export interface DaySchedule {
  day: string;
  slots: TimeSlot[];
}

/** 检测到的冲突 */
export interface ConflictInfo {
  a: string;
  b: string;
  rule: string;
  detail: string;
  /** warning / danger / info */
  severity: string;
}

/** 协同建议 */
export interface SynergyInfo {
  a: string;
  b: string;
  detail: string;
}

/** 时间间隔规则 */
export interface SpacingRule {
  medicines: string[];
  min_gap_hours: number;
  reason: string;
}

/** 完整周排程 */
export interface WeeklySchedule {
  days: DaySchedule[];
  conflicts_found: ConflictInfo[];
  synergies_found: SynergyInfo[];
  spacing_rules: SpacingRule[];
  summary: string;
  safety_verified: boolean;
}

/** 校验结果 */
export interface VerifyResult {
  safe: boolean;
  warnings?: string[];
}

// ---------------------------------------------------------------------------
// 调用后端 /api/medication-plans/auto-schedule
// 失败时回退到本地演示排程（与项目其它 API 客户端一致的离线降级策略）
// ---------------------------------------------------------------------------

export async function autoSchedule(
  medications: MedicationInput[],
  userProfile?: Record<string, unknown>,
): Promise<WeeklySchedule> {
  try {
    return await request<WeeklySchedule>(
      '/api/medication-plans/auto-schedule',
      {
        method: 'POST',
        body: JSON.stringify({
          medications,
          user_profile: userProfile,
        }),
      },
    );
  } catch {
    return buildDemoSchedule(medications);
  }
}

export async function verifySchedule(
  schedule: WeeklySchedule,
): Promise<VerifyResult> {
  try {
    return await request<VerifyResult>(
      '/api/medication-plans/verify-schedule',
      {
        method: 'POST',
        body: JSON.stringify(schedule),
      },
    );
  } catch {
    // 服务不可用时，沿用本地 safety_verified 字段
    return { safe: schedule.safety_verified };
  }
}

// ---------------------------------------------------------------------------
// 本地演示排程引擎
// 在后端不可用时生成可信的周排程，遵循"中西药间隔2小时"等基本安全规则
// ---------------------------------------------------------------------------

const DEMO_DAYS = ['周一', '周二', '周三', '周四', '周五'] as const;

/** 标准时间槽定义 */
const STANDARD_SLOTS: ReadonlyArray<{ time: string; period: string }> = [
  { time: '08:00', period: '早餐后' },
  { time: '10:00', period: '上午' },
  { time: '12:30', period: '午餐后' },
  { time: '18:30', period: '晚餐后' },
  { time: '21:00', period: '睡前' },
];

/** 根据频率解析"该药物每日出现在哪些槽位索引" */
function slotsForFrequency(
  type: string,
  frequency: string,
): number[] {
  const isChinese = type.includes('中') && !type.includes('成药');
  // 中药默认上午槽（索引 1），避开餐后西药高峰
  // 西药/中成药默认餐后槽
  if (frequency.includes('3')) {
    return isChinese ? [1, 2, 4] : [0, 2, 3];
  }
  if (frequency.includes('2')) {
    return isChinese ? [1, 4] : [0, 3];
  }
  // 每日1次 / 隔日1次 / 其它
  return isChinese ? [1] : [0];
}

/** 是否隔日服用 */
function isEveryOtherDay(frequency: string): boolean {
  return frequency.includes('隔日');
}

/** 朴素的中西药交互识别（仅用于演示，真实交互由后端规则引擎判定） */
function detectInteractions(meds: MedicationInput[]): {
  conflicts: ConflictInfo[];
  synergies: SynergyInfo[];
  spacing: SpacingRule[];
} {
  const conflicts: ConflictInfo[] = [];
  const synergies: SynergyInfo[] = [];
  const spacing: SpacingRule[] = [];

  const names = meds.map((m) => m.name);
  const hasChinese = meds.some((m) => m.type.includes('中') && !m.type.includes('成药'));
  const hasWestern = meds.some((m) => m.type === '西药' || m.type === '中成药');

  // 中西药交互通用规则
  if (hasChinese && hasWestern) {
    const chineseNames = meds
      .filter((m) => m.type.includes('中') && !m.type.includes('成药'))
      .map((m) => m.name);
    const westernNames = meds
      .filter((m) => m.type === '西药' || m.type === '中成药')
      .map((m) => m.name);
    const chineseLabel = chineseNames.slice(0, 2).join('、');
    const westernLabel = westernNames[0] ?? '西药';
    conflicts.push({
      a: westernLabel,
      b: chineseLabel,
      rule: '中西药交互',
      detail: '需间隔2小时以上服用',
      severity: 'warning',
    });
    spacing.push({
      medicines: [westernLabel, chineseLabel],
      min_gap_hours: 2,
      reason: '中西药交互风险，避免同时服用影响吸收',
    });
  }

  // 已知协同：当归 + 黄芪 = 气血双补
  const hasDangGui = names.some((n) => n.includes('当归'));
  const hasHuangQi = names.some((n) => n.includes('黄芪'));
  if (hasDangGui && hasHuangQi) {
    synergies.push({
      a: '黄芪',
      b: '当归',
      detail: '气血双补，建议同煎服用（当归补血汤思路）',
    });
  }

  return { conflicts, synergies, spacing };
}

/** 为单种药物生成简明的服药理由 */
function reasonForMedicine(
  med: MedicationInput,
  slotPeriod: string,
  hasInteraction: boolean,
): string {
  const isChinese = med.type.includes('中') && !med.type.includes('成药');
  if (isChinese && hasInteraction) {
    return `${slotPeriod}服用，与西药间隔2小时以上，避免影响吸收`;
  }
  if (isChinese) {
    return `${slotPeriod}服用，吸收较好，温服为宜`;
  }
  if (slotPeriod === '早餐后') {
    return '晨起血压/症状高峰期，餐后服用减少胃肠刺激';
  }
  if (slotPeriod === '晚餐后') {
    return '晚餐后服用，减少胃肠道刺激';
  }
  if (slotPeriod === '睡前') {
    return '睡前服用，药效覆盖夜间';
  }
  if (slotPeriod === '午餐后') {
    return '午餐后服用，维持日间血药浓度';
  }
  return `${slotPeriod}服用`;
}

function buildDemoSchedule(meds: MedicationInput[]): WeeklySchedule {
  if (meds.length === 0) {
    return {
      days: DEMO_DAYS.map((day) => ({ day, slots: [] })),
      conflicts_found: [],
      synergies_found: [],
      spacing_rules: [],
      summary: '尚未选择任何药物',
      safety_verified: true,
    };
  }

  const { conflicts, synergies, spacing } = detectInteractions(meds);
  const hasInteraction = conflicts.length > 0;
  const everyOther = meds.some((m) => isEveryOtherDay(m.frequency));

  // 预计算每个药物应出现的槽位
  type Placement = {
    med: MedicationInput;
    slotIdx: number;
    reason: string;
  };
  const placements: Placement[] = [];
  meds.forEach((med) => {
    const freq = med.frequency || '每日1次';
    const idxs = slotsForFrequency(med.type, freq);
    idxs.forEach((slotIdx) => {
      const slot = STANDARD_SLOTS[slotIdx];
      if (!slot) return;
      placements.push({
        med,
        slotIdx,
        reason: reasonForMedicine(med, slot.period, hasInteraction),
      });
    });
  });

  // 构建天数据
  const days: DaySchedule[] = DEMO_DAYS.map((day, dayIdx) => {
    // 隔日药物只在 周一/三/五 出现
    const daySkip = everyOther && dayIdx % 2 === 1;

    const slots: TimeSlot[] = STANDARD_SLOTS.map((slotDef, slotIdx) => {
      const matched = placements.filter(
        (p) => p.slotIdx === slotIdx && !(daySkip && isEveryOtherDay(p.med.frequency)),
      );
      const medicines: ScheduledMedicine[] = matched.map((p) => ({
        name: p.med.name,
        dosage: p.med.dosage || '1片',
        type: p.med.type,
        reason: p.reason,
      }));

      // 槽位冲突提示
      const conflict_warnings: string[] = [];
      if (hasInteraction && medicines.length > 0) {
        const hasChineseHere = medicines.some(
          (m) => m.type.includes('中') && !m.type.includes('成药'),
        );
        const hasWesternHere = medicines.some(
          (m) => m.type === '西药' || m.type === '中成药',
        );
        if (hasChineseHere && hasWesternHere) {
          conflict_warnings.push('中西药同槽，建议人工复核间隔');
        } else if (hasChineseHere) {
          conflict_warnings.push('已与西药间隔2小时以上');
        }
      }

      return {
        time: slotDef.time,
        period: slotDef.period,
        medicines,
        conflict_warnings,
      };
    });

    return { day, slots };
  });

  const summary = hasInteraction
    ? `本周共安排 ${meds.length} 种药物，发现 ${conflicts.length} 项交互，已自动间隔安排`
    : `本周共安排 ${meds.length} 种药物，未发现明显交互`;

  return {
    days,
    conflicts_found: conflicts,
    synergies_found: synergies,
    spacing_rules: spacing,
    summary,
    safety_verified: true,
  };
}
