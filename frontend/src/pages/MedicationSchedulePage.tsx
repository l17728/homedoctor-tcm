import { useState, useEffect, useMemo, useCallback } from 'react';
import {
  Card,
  Button,
  Typography,
  Space,
  Tag,
  Checkbox,
  Select,
  Input,
  Row,
  Col,
  Drawer,
  Form,
  Empty,
  Skeleton,
  Alert,
  Tooltip,
  Popover,
  Divider,
  Steps,
  message,
  theme,
} from 'antd';
import {
  ScheduleOutlined,
  PlusOutlined,
  PrinterOutlined,
  ShareAltOutlined,
  ReloadOutlined,
  SaveOutlined,
  CheckCircleFilled,
  WarningFilled,
  ClockCircleOutlined,
  ExperimentOutlined,
  MedicineBoxOutlined,
  InfoCircleOutlined,
  HistoryOutlined,
  CopyOutlined,
  FileAddOutlined,
  ArrowLeftOutlined,
  ArrowRightOutlined,
} from '@ant-design/icons';
import { getMedicines, type Medicine } from '../api/medicineApi';
import {
  createMedicationPlan,
  getMedicationPlans,
  type MedicationPlan,
} from '../api/medicationPlanApi';
import {
  autoSchedule,
  type MedicationInput,
  type WeeklySchedule,
  type TimeSlot,
  type ScheduledMedicine,
  type ConflictInfo,
  type SynergyInfo,
  type SpacingRule,
} from '../api/scheduleApi';
import { useIsMobile } from '../hooks/useIsMobile';

const { Title, Text } = Typography;

// ---------------------------------------------------------------------------
// 颜色常量（语义色，不随主题变化）
// ---------------------------------------------------------------------------

const COLOR_SAFE = '#52c41a';
const COLOR_SAFE_BG = '#f6ffed';
const COLOR_CAUTION = '#faad14';
const COLOR_CAUTION_BG = '#fffbe6';
const COLOR_CONFLICT = '#ff4d4f';
const COLOR_CONFLICT_BG = '#fff1f0';
const COLOR_INFO = '#1890ff';
const COLOR_INFO_BG = '#e6f7ff';

const MED_TYPE_COLOR: Record<string, string> = {
  中药: 'green',
  西药: 'blue',
  中成药: 'geekblue',
};

const FREQUENCY_OPTIONS = [
  { label: '每日 1 次', value: '每日1次' },
  { label: '每日 2 次', value: '每日2次' },
  { label: '每日 3 次', value: '每日3次' },
  { label: '隔日 1 次', value: '隔日1次' },
];

const NOTES_OPTIONS = [
  '饭后服用',
  '空腹服用',
  '睡前服用',
  '温开水送服',
];

// ---------------------------------------------------------------------------
// 类型
// ---------------------------------------------------------------------------

interface CustomMedication extends MedicationInput {
  /** 本地临时 id */
  localId: string;
}

// ---------------------------------------------------------------------------
// 安全等级判定
// ---------------------------------------------------------------------------

type SafetyLevel = 'empty' | 'safe' | 'caution' | 'conflict';

function getCellSafety(
  slot: TimeSlot | undefined,
  conflicts: ConflictInfo[],
): SafetyLevel {
  if (!slot || slot.medicines.length === 0) return 'empty';
  const names = slot.medicines.map((m) => m.name);

  // 两冲突药物在同一槽位 — 最严重
  const bothInSlot = conflicts.some((c) => {
    const aHere = names.some((n) => n.includes(c.a) || c.a.includes(n));
    const bHere = names.some((n) => n.includes(c.b) || c.b.includes(n));
    return aHere && bHere;
  });
  if (bothInSlot) return 'conflict';

  // 该槽位含交互药物或带提示 — 注意级
  const involvesConflict =
    conflicts.length > 0 &&
    conflicts.some((c) =>
      names.some(
        (n) =>
          n.includes(c.a) ||
          c.a.includes(n) ||
          n.includes(c.b) ||
          c.b.includes(n),
      ),
    );
  if (involvesConflict || slot.conflict_warnings.length > 0) return 'caution';

  return 'safe';
}

const LEVEL_DOT: Record<SafetyLevel, string> = {
  empty: 'transparent',
  safe: COLOR_SAFE,
  caution: COLOR_CAUTION,
  conflict: COLOR_CONFLICT,
};

// ---------------------------------------------------------------------------
// 内联样式表 — 含打印样式与长辈模式适配
// ---------------------------------------------------------------------------

const PAGE_CSS = `
.medsched-page { animation: medsched-fade 0.35s ease; }
@keyframes medsched-fade { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: none; } }

.medsched-med-pick {
  border: 2px solid #f0f0f0;
  border-radius: 10px;
  padding: 10px 12px;
  cursor: pointer;
  transition: all 0.18s ease;
  background: #fff;
  user-select: none;
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 56px;
}
.medsched-med-pick:hover { border-color: #2ba471; transform: translateY(-1px); box-shadow: 0 2px 8px rgba(43,164,113,0.12); }
.medsched-med-pick.selected {
  border-color: #2ba471;
  background: linear-gradient(135deg, #f6ffed 0%, #fff 100%);
}
.medsched-med-pick .medsched-med-name { font-size: 16px; font-weight: 600; flex: 1; }
.medsched-med-pick .medsched-med-dosage { font-size: 14px; color: #666; }

/* 周课表网格 */
.medsched-grid {
  display: grid;
  gap: 1px;
  background: #e8e8e8;
  border: 1px solid #e8e8e8;
  border-radius: 10px;
  overflow: hidden;
}
.medsched-grid-head, .medsched-grid-corner, .medsched-grid-day {
  background: #fafafa;
  padding: 10px 8px;
  font-weight: 600;
  text-align: center;
}
.medsched-grid-corner {
  position: sticky;
  left: 0;
  z-index: 3;
  background: #f5f5f5;
  color: #595959;
  font-size: 14px;
}
.medsched-grid-head {
  position: sticky;
  top: 0;
  z-index: 2;
  color: #262626;
}
.medsched-grid-head-period { font-size: 15px; }
.medsched-grid-head-time { font-size: 14px; color: #666; margin-top: 2px; }
.medsched-grid-day {
  position: sticky;
  left: 0;
  z-index: 2;
  font-size: 15px;
  color: #262626;
  min-width: 64px;
}
.medsched-cell {
  background: #fff;
  padding: 6px;
  min-height: 84px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.medsched-cell-empty {
  background: repeating-linear-gradient(45deg, #fafafa, #fafafa 6px, #f5f5f5 6px, #f5f5f5 12px);
  align-items: center;
  justify-content: center;
  color: #d9d9d9;
}
.medsched-pill {
  border-radius: 8px;
  padding: 6px 8px;
  font-size: 14px;
  line-height: 1.4;
  border: 1.5px solid;
  cursor: pointer;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.medsched-pill:hover { transform: translateY(-1px); box-shadow: 0 2px 6px rgba(0,0,0,0.08); }
.medsched-pill-name { font-weight: 600; font-size: 15px; }
.medsched-pill-dose { font-size: 14px; color: #595959; margin-top: 2px; }
.medsched-pill-flag { font-size: 14px; margin-top: 4px; }

.medsched-reason-popover { max-width: 280px; }
.medsched-reason-popover .medsched-reason-text { font-size: 14px; line-height: 1.6; color: #595959; }

/* 安全卡片 */
.medsched-safety-card {
  border-radius: 10px;
  padding: 12px 14px;
  border: 1px solid;
  display: flex;
  align-items: flex-start;
  gap: 10px;
  font-size: 15px;
  line-height: 1.5;
}
.medsched-safety-card .medsched-safety-icon { font-size: 20px; flex-shrink: 0; margin-top: 2px; }
.medsched-safety-card .medsched-safety-body { flex: 1; }
.medsched-safety-card .medsched-safety-title { font-weight: 600; font-size: 15px; }
.medsched-safety-card .medsched-safety-detail { font-size: 14px; color: #595959; margin-top: 2px; }

.medsched-reason-item {
  display: flex;
  gap: 10px;
  padding: 10px 0;
  border-bottom: 1px dashed #f0f0f0;
  font-size: 15px;
  line-height: 1.6;
}
.medsched-reason-item:last-child { border-bottom: none; }
.medsched-reason-bullet {
  width: 24px; height: 24px;
  border-radius: 50%;
  background: #e6f7ff;
  color: #1890ff;
  display: flex; align-items: center; justify-content: center;
  font-size: 14px; font-weight: 600;
  flex-shrink: 0;
}

/* 长辈模式适配 */
.elderly-mode .medsched-med-name { font-size: 20px; }
.elderly-mode .medsched-med-pick { min-height: 64px; }
.elderly-mode .medsched-grid-head-period,
.elderly-mode .medsched-grid-day { font-size: 18px; }
.elderly-mode .medsched-pill { font-size: 17px; padding: 8px 10px; }
.elderly-mode .medsched-pill-name { font-size: 18px; }
.elderly-mode .medsched-cell { min-height: 96px; }
.elderly-mode .medsched-safety-card { font-size: 18px; }

/* 打印样式 */
@media print {
  .no-print, .no-print * { display: none !important; }
  .ant-layout-sider, .ant-layout-header, .ai-fab { display: none !important; }
  .ant-layout-content { margin: 0 !important; padding: 0 !important; }
  .ant-layout { min-height: auto !important; }
  .ant-layout > .ant-layout { margin-left: 0 !important; }
  .medsched-page { padding: 0 !important; }
  .ant-card { box-shadow: none !important; border: 1px solid #d9d9d9 !important; page-break-inside: avoid; }
  .medsched-grid { page-break-inside: avoid; }
  .medsched-cell { min-height: 60px !important; }
  body { background: #fff !important; }
}
`;

// ---------------------------------------------------------------------------
// 主组件
// ---------------------------------------------------------------------------

export default function MedicationSchedulePage() {
  const isMobile = useIsMobile();
  const { token } = theme.useToken();

  // 药箱与选择状态
  const [cabinetMeds, setCabinetMeds] = useState<Medicine[]>([]);
  const [cabinetLoading, setCabinetLoading] = useState(true);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [customMeds, setCustomMeds] = useState<CustomMedication[]>([]);
  const [frequency, setFrequency] = useState<string>('每日1次');
  const [notes, setNotes] = useState<string>('饭后服用');

  // 排程状态
  const [schedule, setSchedule] = useState<WeeklySchedule | null>(null);
  const [generating, setGenerating] = useState(false);
  const [savingPlan, setSavingPlan] = useState(false);

  // 模板与上次计划
  const [templates, setTemplates] = useState<MedicationPlan[]>([]);
  const [templatesLoading, setTemplatesLoading] = useState(false);
  const [loadingLast, setLoadingLast] = useState(false);
  const [savingTemplate, setSavingTemplate] = useState(false);

  // 自定义药物抽屉
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [submittingCustom, setSubmittingCustom] = useState(false);
  const [customForm] = Form.useForm<CustomMedication>();

  // 步骤导航（选择药物 → 设置频率 → 生成计划）
  const [currentStep, setCurrentStep] = useState(0);

  // 加载药箱
  const loadCabinet = useCallback(async () => {
    setCabinetLoading(true);
    try {
      const data = await getMedicines({ page: 1, pageSize: 100 });
      setCabinetMeds(data.items);
    } catch {
      setCabinetMeds([]);
    } finally {
      setCabinetLoading(false);
    }
  }, []);

  const loadTemplates = useCallback(async () => {
    setTemplatesLoading(true);
    try {
      const plans = await getMedicationPlans();
      setTemplates(plans);
    } catch {
      setTemplates([]);
    } finally {
      setTemplatesLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadCabinet();
    void loadTemplates();
  }, [loadCabinet, loadTemplates]);

  // 统一选择的药物清单（药箱选中 + 自定义）
  const selectedMeds: MedicationInput[] = useMemo(() => {
    const fromCabinet: MedicationInput[] = cabinetMeds
      .filter((m) => selectedIds.has(m.id))
      .map((m) => ({
        name: m.name,
        type: m.type || '西药',
        dosage: m.dosage || '1片',
        frequency,
        notes: notes || m.notes || undefined,
      }));
    const fromCustom: MedicationInput[] = customMeds.map((c) => ({
      name: c.name,
      type: c.type,
      dosage: c.dosage,
      frequency: c.frequency || frequency,
      notes: c.notes || notes || undefined,
    }));
    return [...fromCabinet, ...fromCustom];
  }, [cabinetMeds, selectedIds, customMeds, frequency, notes]);

  // 时间槽位（取并集，按时间排序）
  const slotColumns = useMemo(() => {
    if (!schedule) return [] as { time: string; period: string }[];
    const map = new Map<string, { time: string; period: string }>();
    schedule.days.forEach((d) => {
      d.slots.forEach((s) => {
        const key = `${s.time}|${s.period}`;
        if (!map.has(key)) map.set(key, { time: s.time, period: s.period });
      });
    });
    return Array.from(map.values()).sort((a, b) =>
      a.time.localeCompare(b.time),
    );
  }, [schedule]);

  // 单元格查找表 day|time -> slot
  const cellLookup = useMemo(() => {
    const m = new Map<string, TimeSlot>();
    if (!schedule) return m;
    schedule.days.forEach((d) => {
      d.slots.forEach((s) => {
        m.set(`${d.day}|${s.time}`, s);
      });
    });
    return m;
  }, [schedule]);

  // 收集所有排程理由（按槽位汇总）
  const allReasons = useMemo(() => {
    if (!schedule) return [] as { med: string; reason: string }[];
    const seen = new Set<string>();
    const out: { med: string; reason: string }[] = [];
    schedule.days.forEach((d) => {
      d.slots.forEach((s) => {
        s.medicines.forEach((med) => {
          const key = `${med.name}|${med.reason}`;
          if (med.reason && !seen.has(key)) {
            seen.add(key);
            out.push({ med: med.name, reason: med.reason });
          }
        });
      });
    });
    return out;
  }, [schedule]);

  // ----- 操作 -----

  const toggleMed = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const removeMed = useCallback(
    (identifier: { id?: string; localId?: string }) => {
      if (identifier.id) {
        setSelectedIds((prev) => {
          const next = new Set(prev);
          next.delete(identifier.id!);
          return next;
        });
      }
      if (identifier.localId) {
        setCustomMeds((prev) =>
          prev.filter((c) => c.localId !== identifier.localId),
        );
      }
    },
    [],
  );

  const handleGenerate = useCallback(async () => {
    if (selectedMeds.length === 0) {
      message.warning('请先选择至少一种药物');
      return;
    }
    setGenerating(true);
    try {
      const result = await autoSchedule(selectedMeds);
      setSchedule(result);
      message.success('已生成本周服药计划');
    } catch {
      message.error('生成失败，请稍后重试');
    } finally {
      setGenerating(false);
    }
  }, [selectedMeds]);

  const handleAddCustom = async () => {
    try {
      const values = await customForm.validateFields();
      setSubmittingCustom(true);
      const newCustom: CustomMedication = {
        localId: `custom-${Date.now()}`,
        name: values.name,
        type: values.type ?? '西药',
        dosage: values.dosage ?? '1片',
        frequency: values.frequency ?? frequency,
        notes: values.notes,
      };
      setCustomMeds((prev) => [...prev, newCustom]);
      message.success(`已添加自定义药物：${newCustom.name}`);
      customForm.resetFields();
      setDrawerOpen(false);
    } catch {
      // 校验错误内联展示
    } finally {
      setSubmittingCustom(false);
    }
  };

  const handleSaveAsPlan = useCallback(async () => {
    if (!schedule) return;
    setSavingPlan(true);
    try {
      // 把周排程打包成用药套餐
      const items = selectedMeds.map((m, idx) => {
        // 找该药物出现的所有时间
        const times = new Set<string>();
        schedule.days.forEach((d) => {
          d.slots.forEach((s) => {
            if (s.medicines.some((sm) => sm.name === m.name)) {
              times.add(s.time);
            }
          });
        });
        return {
          medicineName: m.name,
          dosage: m.dosage,
          frequency: m.frequency,
          times: Array.from(times).sort(),
          notes: m.notes,
          sortOrder: idx,
        };
      });
      await createMedicationPlan({
        name: `本周服药计划 ${new Date().toLocaleDateString('zh-CN')}`,
        description: schedule.summary,
        items,
      });
      message.success('已保存为用药套餐，可在「用药套餐」页面查看');
    } catch {
      message.error('保存失败，请稍后重试');
    } finally {
      setSavingPlan(false);
    }
  }, [schedule, selectedMeds]);

  const handlePrint = () => {
    window.print();
  };

  const handleShare = useCallback(async () => {
    if (!schedule) return;
    const text = `【我的服药计划】\n${schedule.summary}\n\n${schedule.days
      .map((d) => `${d.day}：${d.slots
        .filter((s) => s.medicines.length > 0)
        .map((s) => `${s.period}(${s.time}) ${s.medicines.map((m) => m.name).join('、')}`)
        .join('； ')}`)
      .join('\n')}`;
    try {
      if (navigator.share) {
        await navigator.share({ title: '我的服药计划', text });
      } else {
        await navigator.clipboard.writeText(text);
        message.success('计划已复制到剪贴板');
      }
    } catch {
      // 用户取消分享 — 静默
    }
  }, [schedule]);

  // 加载上次/某个模板的药物列表到当前选择
  const applyPlanToSelection = useCallback(
    (plan: MedicationPlan) => {
      const cabinetByName = new Map(
        cabinetMeds.map((m) => [m.name, m.id]),
      );
      const nextSelected = new Set<string>();
      const newCustoms: CustomMedication[] = [];
      const usedLocalIds = new Set<string>();
      plan.items.forEach((item, idx) => {
        const cabinetId = cabinetByName.get(item.medicineName);
        if (cabinetId && !usedLocalIds.has(`cab-${cabinetId}`)) {
          nextSelected.add(cabinetId);
          usedLocalIds.add(`cab-${cabinetId}`);
        } else {
          newCustoms.push({
            localId: `tpl-${plan.id}-${idx}-${Date.now()}`,
            name: item.medicineName,
            type: '西药',
            dosage: item.dosage || '1片',
            frequency: item.frequency || frequency,
            notes: item.notes || undefined,
          });
        }
      });
      setSelectedIds(nextSelected);
      setCustomMeds((prev) => {
        const kept = prev.filter((c) => !c.localId.startsWith('tpl-'));
        return [...kept, ...newCustoms];
      });
      message.success(
        `已加载「${plan.name}」共 ${plan.items.length} 种药物`,
      );
    },
    [cabinetMeds, frequency],
  );

  const handleLoadLast = useCallback(async () => {
    setLoadingLast(true);
    try {
      const plans = await getMedicationPlans();
      if (plans.length === 0) {
        message.info('暂无历史计划，请先生成并保存一份');
        return;
      }
      const lastPlan = plans[0];
      if (lastPlan) {
        applyPlanToSelection(lastPlan);
      }
    } catch {
      message.error('加载上次计划失败，请稍后重试');
    } finally {
      setLoadingLast(false);
    }
  }, [applyPlanToSelection]);

  const handleLoadTemplate = useCallback(
    (planId: string) => {
      const plan = templates.find((p) => p.id === planId);
      if (!plan) return;
      applyPlanToSelection(plan);
    },
    [templates, applyPlanToSelection],
  );

  const handleSaveAsTemplate = useCallback(async () => {
    if (selectedMeds.length === 0) {
      message.warning('请先选择药物');
      return;
    }
    setSavingTemplate(true);
    try {
      const dateStr = new Date().toLocaleDateString('zh-CN');
      const timesSet = new Set<string>(['08:00']);
      schedule?.days.forEach((d) => {
        d.slots.forEach((s) => {
          if (s.medicines.length > 0) timesSet.add(s.time);
        });
      });
      const items = selectedMeds.map((m, idx) => ({
        medicineName: m.name,
        dosage: m.dosage,
        frequency: m.frequency,
        times: Array.from(timesSet).sort(),
        notes: m.notes,
        sortOrder: idx,
      }));
      await createMedicationPlan({
        name: `${dateStr} 模板`,
        description: `由 ${selectedMeds.length} 种药物组成的常用模板`,
        items,
      });
      message.success(`已保存为模板「${dateStr} 模板」`);
      await loadTemplates();
    } catch {
      message.error('保存模板失败，请稍后重试');
    } finally {
      setSavingTemplate(false);
    }
  }, [selectedMeds, schedule, loadTemplates]);

  // ----- 渲染 -----

  return (
    <div className="medsched-page">
      <style>{PAGE_CSS}</style>

      {/* 页头 */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 16,
          flexWrap: 'wrap',
          gap: 12,
        }}
      >
        <Title level={3} style={{ margin: 0 }}>
          <Space>
            <ScheduleOutlined style={{ color: token.colorPrimary }} />
            我的服药计划
          </Space>
        </Title>
        <Space className="no-print" wrap>
          <Select<string>
            placeholder="选择常用模板"
            style={{ minWidth: 200 }}
            size="large"
            loading={templatesLoading}
            value={undefined}
            onChange={(v) => {
              if (v) handleLoadTemplate(v);
            }}
            options={templates.map((p) => ({
              label: `${p.name}（${p.items.length} 种药）`,
              value: p.id,
            }))}
            notFoundContent={
              templatesLoading ? '加载中...' : '暂无保存的模板'
            }
            allowClear
          />
          <Button
            size="large"
            icon={<HistoryOutlined />}
            onClick={handleLoadLast}
            loading={loadingLast}
          >
            加载上次计划
          </Button>
        </Space>
      </div>

      {/* 步骤式选择流程：选择药物 → 设置频率 → 生成计划 */}
      <Card
        className="no-print"
        style={{ marginBottom: 16, borderRadius: 12 }}
        styles={{ body: { padding: isMobile ? 16 : 24 } }}
      >
        <Steps
          current={currentStep}
          size="small"
          style={{ marginBottom: 24 }}
          items={[
            { title: '选择药物' },
            { title: '设置频率' },
            { title: '生成计划' },
          ]}
        />

        {/* ===== Step 0: 选择药物 ===== */}
        {currentStep === 0 && (
          <>
            <div style={{ marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
              <MedicineBoxOutlined style={{ color: token.colorPrimary, fontSize: 18 }} />
              <Text strong style={{ fontSize: 17 }}>从药箱选择药物</Text>
              <Text type="secondary" style={{ fontSize: 14 }}>
                （点击卡片选择/取消，已选 {selectedMeds.length} 种）
              </Text>
            </div>

            {cabinetLoading ? (
              <Skeleton active paragraph={{ rows: 3 }} />
            ) : cabinetMeds.length === 0 && customMeds.length === 0 ? (
              <Empty
                description="药箱为空，请先添加药物到药箱，或使用下方「添加自定义药物」"
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                style={{ margin: '16px 0' }}
              />
            ) : (
              <Row gutter={[8, 8]}>
                {cabinetMeds.map((m) => {
                  const checked = selectedIds.has(m.id);
                  return (
                    <Col xs={24} sm={12} lg={8} xl={6} key={m.id}>
                      <div
                        className={`medsched-med-pick ${checked ? 'selected' : ''}`}
                        onClick={() => toggleMed(m.id)}
                        role="checkbox"
                        aria-checked={checked}
                        tabIndex={0}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            toggleMed(m.id);
                          }
                        }}
                      >
                        <Checkbox checked={checked} tabIndex={-1} />
                        <span className="medsched-med-name">{m.name}</span>
                        {m.type && (
                          <Tag color={MED_TYPE_COLOR[m.type] ?? 'default'} style={{ margin: 0 }}>
                            {m.type}
                          </Tag>
                        )}
                        {m.dosage && (
                          <span className="medsched-med-dosage">{m.dosage}</span>
                        )}
                      </div>
                    </Col>
                  );
                })}
                {customMeds.map((c) => (
                  <Col xs={24} sm={12} lg={8} xl={6} key={c.localId}>
                    <div
                      className="medsched-med-pick selected"
                      style={{ borderColor: token.colorPrimary, background: COLOR_INFO_BG }}
                    >
                      <ExperimentOutlined style={{ color: COLOR_INFO }} />
                      <span className="medsched-med-name">{c.name}</span>
                      <Tag color={MED_TYPE_COLOR[c.type] ?? 'default'} style={{ margin: 0 }}>
                        {c.type}
                      </Tag>
                      <span className="medsched-med-dosage">{c.dosage}</span>
                      <Button
                        type="text"
                        danger
                        onClick={(e) => {
                          e.stopPropagation();
                          removeMed({ localId: c.localId });
                        }}
                        style={{ padding: '0 4px', height: 'auto' }}
                      >
                        ×
                      </Button>
                    </div>
                  </Col>
                ))}
              </Row>
            )}

            <Divider style={{ margin: '16px 0' }} />

            <Button
              block
              size="large"
              icon={<PlusOutlined />}
              onClick={() => {
                customForm.resetFields();
                setDrawerOpen(true);
              }}
              style={{ height: 48 }}
            >
              添加自定义药物
            </Button>

            <div style={{ marginTop: 16, display: 'flex', justifyContent: 'flex-end' }}>
              <Button
                type="primary"
                size="large"
                icon={<ArrowRightOutlined />}
                disabled={selectedMeds.length === 0}
                onClick={() => setCurrentStep(1)}
              >
                下一步：设置频率
              </Button>
            </div>
          </>
        )}

        {/* ===== Step 1: 设置频率 ===== */}
        {currentStep === 1 && (
          <>
            <div style={{ marginBottom: 16 }}>
              <Text strong style={{ fontSize: 17 }}>设置服用频率与说明</Text>
            </div>

            <Row gutter={[12, 12]} align="middle">
              <Col xs={24} sm={12}>
                <Text strong style={{ fontSize: 15, display: 'block', marginBottom: 6 }}>
                  服用频率
                </Text>
                <Select
                  value={frequency}
                  onChange={setFrequency}
                  options={FREQUENCY_OPTIONS}
                  style={{ width: '100%' }}
                  size="large"
                />
              </Col>
              <Col xs={24} sm={12}>
                <Text strong style={{ fontSize: 15, display: 'block', marginBottom: 6 }}>
                  服用说明
                </Text>
                <Select
                  mode="tags"
                  value={notes ? [notes] : []}
                  onChange={(vals) => setNotes(vals[0] ?? '')}
                  options={NOTES_OPTIONS.map((n) => ({ label: n, value: n }))}
                  placeholder="选择或输入说明"
                  style={{ width: '100%' }}
                  size="large"
                  maxCount={1}
                />
              </Col>
            </Row>

            {/* 已选药物标签 */}
            {selectedMeds.length > 0 && (
              <div style={{ marginTop: 20 }}>
                <Text type="secondary" style={{ fontSize: 14 }}>本次参与排程：</Text>
                <Space wrap size={[6, 6]} style={{ marginTop: 6 }}>
                  {selectedMeds.map((m, i) => {
                    const id = cabinetMeds.find((c) => c.name === m.name)?.id;
                    const custom = customMeds.find((c) => c.name === m.name);
                    return (
                      <Tag
                        key={`${m.name}-${i}`}
                        color={MED_TYPE_COLOR[m.type] ?? 'blue'}
                        closable
                        onClose={() => removeMed({ id, localId: custom?.localId })}
                        style={{ fontSize: 14, padding: '2px 8px' }}
                      >
                        {m.name} · {m.dosage}
                      </Tag>
                    );
                  })}
                </Space>
              </div>
            )}

            <div style={{ marginTop: 24, display: 'flex', justifyContent: 'space-between' }}>
              <Button
                size="large"
                icon={<ArrowLeftOutlined />}
                onClick={() => setCurrentStep(0)}
              >
                上一步
              </Button>
              <Button
                type="primary"
                size="large"
                icon={<ArrowRightOutlined />}
                onClick={() => setCurrentStep(2)}
              >
                下一步：生成计划
              </Button>
            </div>
          </>
        )}

        {/* ===== Step 2: 生成计划 ===== */}
        {currentStep === 2 && (
          <>
            <div style={{ marginBottom: 16 }}>
              <Text strong style={{ fontSize: 17 }}>确认并生成计划</Text>
            </div>

            <Alert
              type="info"
              showIcon
              message={`将生成包含 ${selectedMeds.length} 种药物的本周服药计划`}
              description={
                <Space direction="vertical" size={4} style={{ marginTop: 4 }}>
                  <Text style={{ fontSize: 14 }}>
                    频率：{FREQUENCY_OPTIONS.find((f) => f.value === frequency)?.label ?? frequency}
                  </Text>
                  {notes && <Text style={{ fontSize: 14 }}>说明：{notes}</Text>}
                  <Text type="secondary" style={{ fontSize: 14 }}>
                    {selectedMeds.map((m) => m.name).join('、')}
                  </Text>
                </Space>
              }
              style={{ marginBottom: 24, borderRadius: 10 }}
            />

            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <Button
                size="large"
                icon={<ArrowLeftOutlined />}
                onClick={() => setCurrentStep(1)}
              >
                上一步
              </Button>
              <Button
                type="primary"
                size="large"
                icon={<ScheduleOutlined />}
                onClick={handleGenerate}
                loading={generating}
                disabled={selectedMeds.length === 0}
                style={{ minWidth: 200, height: 48 }}
              >
                {schedule ? '重新生成' : '生成计划'}
              </Button>
            </div>
          </>
        )}
      </Card>

      {/* 第二步：生成中 */}
      {generating && (
        <Card style={{ marginBottom: 16, borderRadius: 12 }}>
          <Skeleton active paragraph={{ rows: 8 }} />
        </Card>
      )}

      {/* 第三步：周课表 + 安全提示 + 安排说明 */}
      {!generating && schedule && (
        <>
          {/* 顶部摘要 */}
          <Alert
            type={schedule.safety_verified ? 'success' : 'warning'}
            showIcon
            icon={schedule.safety_verified ? <CheckCircleFilled /> : <WarningFilled />}
            message={schedule.summary}
            style={{ marginBottom: 16, borderRadius: 10, fontSize: 16, padding: '12px 16px' }}
          />

          {/* 周课表卡片 */}
          <Card
            style={{ marginBottom: 16, borderRadius: 12 }}
            styles={{ body: { padding: isMobile ? 12 : 20 } }}
            title={
              <Space>
                <ScheduleOutlined style={{ color: token.colorPrimary }} />
                <span style={{ fontSize: 18 }}>本周服药时刻表</span>
              </Space>
            }
            extra={
              <Space className="no-print" wrap>
                <Tooltip title="打印本周计划">
                  <Button icon={<PrinterOutlined />} onClick={handlePrint}>打印</Button>
                </Tooltip>
                <Tooltip title="分享给家人">
                  <Button icon={<ShareAltOutlined />} onClick={handleShare}>分享</Button>
                </Tooltip>
                <Button icon={<ReloadOutlined />} onClick={handleGenerate}>重新生成</Button>
              </Space>
            }
          >
            <WeeklyGrid
              schedule={schedule}
              slotColumns={slotColumns}
              cellLookup={cellLookup}
              isMobile={isMobile}
              token={token}
            />

            {/* 图例 */}
            <div
              style={{
                marginTop: 16,
                display: 'flex',
                gap: 16,
                flexWrap: 'wrap',
                fontSize: 14,
                color: token.colorTextSecondary,
              }}
            >
              <Space size={6}>
                <span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: '50%', background: COLOR_SAFE }} />
                安全无冲突
              </Space>
              <Space size={6}>
                <span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: '50%', background: COLOR_CAUTION }} />
                含时间提醒（如需间隔）
              </Space>
              <Space size={6}>
                <span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: '50%', background: COLOR_CONFLICT }} />
                同槽冲突（需复核）
              </Space>
            </div>
          </Card>

          {/* 安全提示 */}
          <Card
            style={{ marginBottom: 16, borderRadius: 12 }}
            styles={{ body: { padding: isMobile ? 12 : 20 } }}
            title={
              <Space>
                <SafetyIconWrap />
                <span style={{ fontSize: 18 }}>安全提示</span>
              </Space>
            }
          >
            <SafetyPanel
              conflicts={schedule.conflicts_found}
              synergies={schedule.synergies_found}
              spacing={schedule.spacing_rules}
              isMobile={isMobile}
            />
            {schedule.conflicts_found.length === 0 &&
              schedule.synergies_found.length === 0 &&
              schedule.spacing_rules.length === 0 && (
                <Empty
                  description="未发现冲突或协同，可放心服用"
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  style={{ marginTop: 16 }}
                />
              )}
          </Card>

          {/* 安排说明 */}
          <Card
            style={{ marginBottom: 16, borderRadius: 12 }}
            styles={{ body: { padding: isMobile ? 12 : 20 } }}
            title={
              <Space>
                <InfoCircleOutlined style={{ color: COLOR_INFO, fontSize: 18 }} />
                <span style={{ fontSize: 18 }}>安排说明</span>
              </Space>
            }
          >
            {allReasons.length === 0 ? (
              <Empty description="暂无安排说明" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
              <div>
                {allReasons.map((r, i) => (
                  <div className="medsched-reason-item" key={`${r.med}-${i}`}>
                    <div className="medsched-reason-bullet">{i + 1}</div>
                    <div>
                      <Text strong style={{ fontSize: 16 }}>{r.med}：</Text>
                      <Text style={{ fontSize: 15 }}>{r.reason}</Text>
                    </div>
                  </div>
                ))}
              </div>
            )}
            <Alert
              type="info"
              showIcon
              message="本计划由智能排程引擎生成，仅供日常用药参考。如出现不适或症状变化，请及时咨询医师。"
              style={{ marginTop: 16, borderRadius: 8 }}
            />
          </Card>

          {/* 保存为套餐 / 模板 */}
          <div className="no-print" style={{ textAlign: 'center', paddingBottom: 24 }}>
            <Space wrap size="middle">
              <Button
                size="large"
                icon={<FileAddOutlined />}
                onClick={handleSaveAsTemplate}
                loading={savingTemplate}
                style={{ minWidth: 180, height: 48 }}
              >
                保存为模板
              </Button>
              <Button
                type="primary"
                size="large"
                icon={<SaveOutlined />}
                onClick={handleSaveAsPlan}
                loading={savingPlan}
                style={{ minWidth: 200, height: 48 }}
              >
                保存为用药套餐
              </Button>
            </Space>
            <div style={{ marginTop: 8 }}>
              <Text type="secondary" style={{ fontSize: 14 }}>
                <CopyOutlined style={{ marginRight: 4 }} />
                模板可在下次快速加载；套餐会自动生成提醒
              </Text>
            </div>
          </div>
        </>
      )}

      {/* 空状态 */}
      {!schedule && !generating && (
        <Card style={{ borderRadius: 12 }}>
          <Empty
            description={
              <span style={{ fontSize: 16 }}>
                请在上方选择药物后，点击「生成计划」查看本周服药时刻表
              </span>
            }
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            style={{ marginTop: 40, marginBottom: 40 }}
          />
          <div style={{ textAlign: 'center', marginTop: 16 }}>
            <Space direction="vertical" size="small">
              <Text type="secondary">智能排程提供：</Text>
              <Space wrap>
                <Tag color="green" icon={<CheckCircleFilled />}>自动避开冲突</Tag>
                <Tag color="blue" icon={<ClockCircleOutlined />}>最佳服用时段</Tag>
                <Tag color="orange" icon={<WarningFilled />}>中西药间隔</Tag>
              </Space>
            </Space>
          </div>
        </Card>
      )}

      {/* 自定义药物抽屉 */}
      <Drawer
        title="添加自定义药物"
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        width={isMobile ? '100%' : 420}
        destroyOnClose
        maskClosable={false}
        extra={
          <Space>
            <Button onClick={() => setDrawerOpen(false)}>取消</Button>
            <Button type="primary" loading={submittingCustom} onClick={handleAddCustom}>
              添加
            </Button>
          </Space>
        }
      >
        <Form form={customForm} layout="vertical" preserve={false}>
          <Form.Item
            label="药物名称"
            name="name"
            rules={[{ required: true, message: '请输入药物名称' }]}
          >
            <Input placeholder="如：银杏叶片" size="large" />
          </Form.Item>
          <Form.Item label="类型" name="type" initialValue="西药">
            <Select
              size="large"
              options={[
                { label: '西药', value: '西药' },
                { label: '中药', value: '中药' },
                { label: '中成药', value: '中成药' },
              ]}
            />
          </Form.Item>
          <Form.Item label="用量" name="dosage" initialValue="1片">
            <Input placeholder="如：1片 / 煎服" size="large" />
          </Form.Item>
          <Form.Item label="服用频率" name="frequency" initialValue={frequency}>
            <Select size="large" options={FREQUENCY_OPTIONS} />
          </Form.Item>
          <Form.Item label="服用说明" name="notes">
            <Input placeholder="如：饭后服用" size="large" />
          </Form.Item>
        </Form>
      </Drawer>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 周课表网格（桌面）/ 纵向卡片（移动端）
// ---------------------------------------------------------------------------

interface WeeklyGridProps {
  schedule: WeeklySchedule;
  slotColumns: { time: string; period: string }[];
  cellLookup: Map<string, TimeSlot>;
  isMobile: boolean;
  token: ReturnType<typeof theme.useToken>['token'];
}

function WeeklyGrid({
  schedule,
  slotColumns,
  cellLookup,
  isMobile,
  token,
}: WeeklyGridProps) {
  if (isMobile) {
    return <MobileSchedule schedule={schedule} token={token} />;
  }
  return (
    <DesktopSchedule
      schedule={schedule}
      slotColumns={slotColumns}
      cellLookup={cellLookup}
      token={token}
    />
  );
}

function DesktopSchedule({
  schedule,
  slotColumns,
  cellLookup,
}: Omit<WeeklyGridProps, 'isMobile'>) {
  return (
    <div
      className="medsched-grid"
      style={{
        gridTemplateColumns: `72px repeat(${slotColumns.length}, minmax(120px, 1fr))`,
      }}
    >
      {/* 表头 */}
      <div className="medsched-grid-corner">时间</div>
      {slotColumns.map((col) => (
        <div className="medsched-grid-head" key={`${col.time}|${col.period}`}>
          <div className="medsched-grid-head-period">{col.period}</div>
          <div className="medsched-grid-head-time">{col.time}</div>
        </div>
      ))}

      {/* 每日 */}
      {schedule.days.map((day) => (
        <DayRowFragment
          key={day.day}
          day={day.day}
          slotColumns={slotColumns}
          cellLookup={cellLookup}
          conflicts={schedule.conflicts_found}
        />
      ))}
    </div>
  );
}

interface DayRowFragmentProps {
  day: string;
  slotColumns: { time: string; period: string }[];
  cellLookup: Map<string, TimeSlot>;
  conflicts: ConflictInfo[];
}

function DayRowFragment({
  day,
  slotColumns,
  cellLookup,
  conflicts,
}: DayRowFragmentProps) {
  return (
    <>
      <div className="medsched-grid-day">{day}</div>
      {slotColumns.map((col) => {
        const slot = cellLookup.get(`${day}|${col.time}`);
        return (
          <ScheduleCell
            key={`${day}|${col.time}`}
            slot={slot}
            conflicts={conflicts}
          />
        );
      })}
    </>
  );
}

// ---------------------------------------------------------------------------
// 单元格
// ---------------------------------------------------------------------------

interface ScheduleCellProps {
  slot: TimeSlot | undefined;
  conflicts: ConflictInfo[];
}

function ScheduleCell({ slot, conflicts }: ScheduleCellProps) {
  const level = getCellSafety(slot, conflicts);

  if (level === 'empty') {
    return (
      <div className="medsched-cell medsched-cell-empty">
        <span style={{ fontSize: 18 }}>—</span>
      </div>
    );
  }

  return (
    <div className="medsched-cell">
      {slot!.medicines.map((med, i) => (
        <MedPill
          key={`${med.name}-${i}`}
          med={med}
          warning={slot!.conflict_warnings}
          conflicts={conflicts}
        />
      ))}
    </div>
  );
}

interface MedPillProps {
  med: ScheduledMedicine;
  warning: string[];
  conflicts: ConflictInfo[];
}

function MedPill({ med, warning, conflicts }: MedPillProps) {
  // 判定该药丸的边框色
  const involvesConflict = conflicts.some(
    (c) =>
      med.name.includes(c.a) ||
      c.a.includes(med.name) ||
      med.name.includes(c.b) ||
      c.b.includes(med.name),
  );
  const hasSlotWarning = warning.length > 0;
  const color = involvesConflict || hasSlotWarning ? COLOR_CAUTION : COLOR_SAFE;
  const bg = involvesConflict || hasSlotWarning ? COLOR_CAUTION_BG : COLOR_SAFE_BG;

  const content = (
    <div
      className="medsched-pill"
      style={{
        borderColor: color,
        background: bg,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
        <span
          style={{
            display: 'inline-block',
            width: 8,
            height: 8,
            borderRadius: '50%',
            background: LEVEL_DOT[involvesConflict || hasSlotWarning ? 'caution' : 'safe'],
            flexShrink: 0,
          }}
        />
        <span className="medsched-pill-name">{med.name}</span>
      </div>
      <div className="medsched-pill-dose">
        {med.dosage}
        {med.type && med.type !== '西药' ? ` · ${med.type}` : ''}
      </div>
      {hasSlotWarning && (
        <div className="medsched-pill-flag" style={{ color: COLOR_CAUTION }}>
          ⏱ {warning[0]}
        </div>
      )}
    </div>
  );

  if (!med.reason) return content;

  return (
    <Popover
      trigger="click"
      placement="rightTop"
      content={
        <div className="medsched-reason-popover">
          <Text strong style={{ fontSize: 15 }}>{med.name}</Text>
          <div className="medsched-reason-text" style={{ marginTop: 4 }}>
            {med.reason}
          </div>
        </div>
      }
      title="服药理由"
    >
      {content}
    </Popover>
  );
}

// ---------------------------------------------------------------------------
// 移动端纵向卡片
// ---------------------------------------------------------------------------

function MobileSchedule({
  schedule,
  token,
}: {
  schedule: WeeklySchedule;
  token: WeeklyGridProps['token'];
}) {
  return (
    <Space direction="vertical" size={12} style={{ width: '100%' }}>
      {schedule.days.map((day) => {
        const filledSlots = day.slots.filter((s) => s.medicines.length > 0);
        return (
          <Card
            key={day.day}
            size="small"
            style={{ borderRadius: 10, borderColor: token.colorBorder }}
            title={
              <span style={{ fontSize: 17, fontWeight: 600 }}>{day.day}</span>
            }
          >
            {filledSlots.length === 0 ? (
              <Text type="secondary" style={{ fontSize: 14 }}>
                本日无服药安排
              </Text>
            ) : (
              filledSlots.map((slot) => {
                const level = getCellSafety(slot, schedule.conflicts_found);
                return (
                  <div
                    key={`${day.day}-${slot.time}`}
                    style={{
                      marginBottom: 10,
                      paddingBottom: 10,
                      borderBottom: '1px dashed #f0f0f0',
                    }}
                  >
                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 6,
                        marginBottom: 6,
                      }}
                    >
                      <ClockCircleOutlined style={{ color: token.colorPrimary }} />
                      <Text strong style={{ fontSize: 16 }}>
                        {slot.period}
                      </Text>
                      <Text type="secondary" style={{ fontSize: 14 }}>
                        {slot.time}
                      </Text>
                      {level !== 'safe' && level !== 'empty' && (
                        <Tag
                          color={level === 'conflict' ? 'red' : 'orange'}
                          style={{ marginLeft: 'auto', fontSize: 14 }}
                        >
                          {level === 'conflict' ? '需复核' : '注意间隔'}
                        </Tag>
                      )}
                    </div>
                    {slot.medicines.map((med, i) => (
                      <MedPill
                        key={`${med.name}-${i}`}
                        med={med}
                        warning={slot.conflict_warnings}
                        conflicts={schedule.conflicts_found}
                      />
                    ))}
                  </div>
                );
              })
            )}
          </Card>
        );
      })}
    </Space>
  );
}

// ---------------------------------------------------------------------------
// 安全提示面板
// ---------------------------------------------------------------------------

interface SafetyPanelProps {
  conflicts: ConflictInfo[];
  synergies: SynergyInfo[];
  spacing: SpacingRule[];
  isMobile: boolean;
}

function SafetyPanel({
  conflicts,
  synergies,
  spacing,
  isMobile,
}: SafetyPanelProps) {
  const gutter: [number, number] = isMobile ? [12, 12] : [16, 16];
  return (
    <Row gutter={gutter}>
      {/* 冲突已处理 */}
      <Col xs={24} lg={8}>
        <Text strong style={{ fontSize: 15, display: 'block', marginBottom: 8, color: COLOR_CONFLICT }}>
          <WarningFilled style={{ marginRight: 6 }} />
          冲突已处理（{conflicts.length}）
        </Text>
        <Space direction="vertical" size={8} style={{ width: '100%' }}>
          {conflicts.length === 0 ? (
            <Text type="secondary" style={{ fontSize: 14 }}>无冲突</Text>
          ) : (
            conflicts.map((c, i) => (
              <div
                key={`conflict-${i}`}
                className="medsched-safety-card"
                style={{
                  borderColor: c.severity === 'danger' ? COLOR_CONFLICT : COLOR_CAUTION,
                  background: c.severity === 'danger' ? COLOR_CONFLICT_BG : COLOR_CAUTION_BG,
                }}
              >
                <WarningFilled
                  className="medsched-safety-icon"
                  style={{ color: c.severity === 'danger' ? COLOR_CONFLICT : COLOR_CAUTION }}
                />
                <div className="medsched-safety-body">
                  <div className="medsched-safety-title">
                    {c.a} × {c.b}
                  </div>
                  <div className="medsched-safety-detail">
                    <Tag style={{ marginRight: 4 }}>{c.rule}</Tag>
                    {c.detail} · 已自动隔开
                  </div>
                </div>
              </div>
            ))
          )}
        </Space>
      </Col>

      {/* 协同建议 */}
      <Col xs={24} lg={8}>
        <Text strong style={{ fontSize: 15, display: 'block', marginBottom: 8, color: COLOR_SAFE }}>
          <CheckCircleFilled style={{ marginRight: 6 }} />
          协同建议（{synergies.length}）
        </Text>
        <Space direction="vertical" size={8} style={{ width: '100%' }}>
          {synergies.length === 0 ? (
            <Text type="secondary" style={{ fontSize: 14 }}>无协同组合</Text>
          ) : (
            synergies.map((s, i) => (
              <div
                key={`syn-${i}`}
                className="medsched-safety-card"
                style={{ borderColor: COLOR_SAFE, background: COLOR_SAFE_BG }}
              >
                <CheckCircleFilled
                  className="medsched-safety-icon"
                  style={{ color: COLOR_SAFE }}
                />
                <div className="medsched-safety-body">
                  <div className="medsched-safety-title">
                    {s.a} + {s.b}
                  </div>
                  <div className="medsched-safety-detail">{s.detail}</div>
                </div>
              </div>
            ))
          )}
        </Space>
      </Col>

      {/* 时间间隔规则 */}
      <Col xs={24} lg={8}>
        <Text strong style={{ fontSize: 15, display: 'block', marginBottom: 8, color: COLOR_INFO }}>
          <ClockCircleOutlined style={{ marginRight: 6 }} />
          时间间隔规则（{spacing.length}）
        </Text>
        <Space direction="vertical" size={8} style={{ width: '100%' }}>
          {spacing.length === 0 ? (
            <Text type="secondary" style={{ fontSize: 14 }}>无间隔要求</Text>
          ) : (
            spacing.map((sp, i) => (
              <div
                key={`spacing-${i}`}
                className="medsched-safety-card"
                style={{ borderColor: COLOR_INFO, background: COLOR_INFO_BG }}
              >
                <ClockCircleOutlined
                  className="medsched-safety-icon"
                  style={{ color: COLOR_INFO }}
                />
                <div className="medsched-safety-body">
                  <div className="medsched-safety-title">
                    {sp.medicines.join(' 与 ')}
                  </div>
                  <div className="medsched-safety-detail">
                    至少间隔 <Text strong>{sp.min_gap_hours}</Text> 小时 · {sp.reason}
                  </div>
                </div>
              </div>
            ))
          )}
        </Space>
      </Col>
    </Row>
  );
}

// ---------------------------------------------------------------------------
// 小图标包装（避免重复样式）
// ---------------------------------------------------------------------------

function SafetyIconWrap() {
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: 24,
        height: 24,
        borderRadius: '50%',
        background: COLOR_INFO_BG,
      }}
    >
      <ExperimentOutlined style={{ color: COLOR_INFO, fontSize: 16 }} />
    </span>
  );
}

