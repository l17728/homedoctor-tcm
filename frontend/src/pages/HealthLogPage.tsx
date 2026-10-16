import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Card,
  Button,
  Typography,
  Space,
  InputNumber,
  Input,
  DatePicker,
  Row,
  Col,
  Skeleton,
  Empty,
  Alert,
  Tag,
  Tooltip,
  Divider,
  message,
  Popconfirm,
} from 'antd';
import {
  HeartOutlined,
  SaveOutlined,
  ReloadOutlined,
  EditOutlined,
  DeleteOutlined,
  CloseCircleOutlined,
  CheckCircleFilled,
} from '@ant-design/icons';
import dayjs, { type Dayjs } from 'dayjs';
import 'dayjs/locale/zh-cn';
import {
  listHealthLogs,
  createHealthLog,
  updateHealthLog,
  deleteHealthLog,
  MOOD_EMOJI,
  type HealthLog,
  type Mood,
  type HealthLogInput,
  type HealthLogUpdateInput,
} from '../api/healthLogApi';
import { useIsMobile } from '../hooks/useIsMobile';

dayjs.locale('zh-cn');

const { Title, Text } = Typography;
const { TextArea } = Input;

const MOOD_OPTIONS: { value: Mood; label: string; color: string }[] = [
  { value: '好', label: '好', color: '#52c41a' },
  { value: '一般', label: '一般', color: '#faad14' },
  { value: '差', label: '差', color: '#ff4d4f' },
];

interface FormState {
  systolic: number | null;
  diastolic: number | null;
  blood_sugar: number | null;
  weight: number | null;
  sleep_hours: number | null;
  mood: Mood | null;
  notes: string;
}

const EMPTY_FORM: FormState = {
  systolic: null,
  diastolic: null,
  blood_sugar: null,
  weight: null,
  sleep_hours: null,
  mood: null,
  notes: '',
};

const PAGE_CSS = `
.hlog-page { animation: hlog-fade 0.4s ease; }
@keyframes hlog-fade { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }

.hlog-form-section {
  border: 1px solid #f0f0f0;
  border-radius: 12px;
  padding: 4px 16px;
  margin-bottom: 14px;
  background: #fff;
}
.hlog-form-section-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 12px 0 8px;
}
.hlog-form-section-head .hlog-form-section-icon {
  width: 32px; height: 32px;
  border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  font-size: 16px;
}
.hlog-form-section-title { font-size: 16px; font-weight: 600; }

.hlog-mood-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 10px 8px;
  border: 2px solid #f0f0f0;
  border-radius: 12px;
  background: #fff;
  cursor: pointer;
  transition: all 0.18s ease;
  min-height: 72px;
  user-select: none;
}
.hlog-mood-btn:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.06); }
.hlog-mood-btn.selected { border-width: 2px; background: linear-gradient(135deg, #f6ffed 0%, #fff 100%); }
.hlog-mood-emoji { font-size: 26px; line-height: 1; }
.hlog-mood-label { font-size: 14px; color: #595959; font-weight: 500; }

.hlog-history-card {
  border: 1px solid #f0f0f0;
  border-radius: 10px;
  padding: 12px 14px;
  background: #fff;
  transition: all 0.18s ease;
  height: 100%;
}
.hlog-history-card:hover { box-shadow: 0 4px 14px rgba(0,0,0,0.06); transform: translateY(-1px); }
.hlog-history-date { font-size: 14px; color: #666; }
.hlog-history-metric {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 0;
  border-bottom: 1px dashed #f5f5f5;
  font-size: 14px;
}
.hlog-history-metric:last-child { border-bottom: none; }
.hlog-history-metric-label { color: #666; }
.hlog-history-metric-value { font-weight: 600; color: #262626; }

.elderly-mode .hlog-form-section-title { font-size: 19px; }
.elderly-mode .hlog-mood-emoji { font-size: 32px; }
.elderly-mode .hlog-mood-btn { min-height: 88px; }
`;

function bpCategory(s: number, d: number): { label: string; color: string } {
  if (s < 120 && d < 80) return { label: '理想', color: '#52c41a' };
  if (s < 130 && d < 85) return { label: '正常', color: '#73d13d' };
  if (s < 140 && d < 90) return { label: '正常高值', color: '#faad14' };
  if (s < 160 && d < 100) return { label: '1级高血压', color: '#fa8c16' };
  if (s < 180 && d < 110) return { label: '2级高血压', color: '#fa541c' };
  return { label: '3级高血压', color: '#ff4d4f' };
}

function sugarCategory(v: number): { label: string; color: string } {
  if (v < 3.9) return { label: '偏低', color: '#faad14' };
  if (v <= 6.1) return { label: '正常(空腹)', color: '#52c41a' };
  if (v <= 7.8) return { label: '正常(餐后)', color: '#73d13d' };
  if (v <= 11.1) return { label: '糖耐量受损', color: '#fa8c16' };
  return { label: '糖尿病范围', color: '#ff4d4f' };
}

export default function HealthLogPage() {
  const isMobile = useIsMobile();

  const [selectedDate, setSelectedDate] = useState<Dayjs>(dayjs());
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [recentLogs, setRecentLogs] = useState<HealthLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const loadRecent = useCallback(async () => {
    setLoading(true);
    try {
      const logs = await listHealthLogs(30);
      setRecentLogs(logs);
    } catch {
      setRecentLogs([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const tryLoadForDate = useCallback(
    async (date: Dayjs) => {
      const dateStr = date.format('YYYY-MM-DD');
      try {
        const logs = await listHealthLogs(30);
        setRecentLogs(logs);
        const match = logs.find((l) => l.log_date === dateStr);
        if (match) {
          setForm({
            systolic: match.systolic,
            diastolic: match.diastolic,
            blood_sugar: match.blood_sugar,
            weight: match.weight,
            sleep_hours: match.sleep_hours,
            mood: match.mood,
            notes: match.notes ?? '',
          });
          setEditingId(match.id);
        } else {
          setForm(EMPTY_FORM);
          setEditingId(null);
        }
      } catch {
        setForm(EMPTY_FORM);
        setEditingId(null);
      }
    },
    [],
  );

  useEffect(() => {
    void tryLoadForDate(dayjs());
  }, [tryLoadForDate]);

  const handleDateChange = (date: Dayjs | null) => {
    if (!date) return;
    setSelectedDate(date);
    void tryLoadForDate(date);
  };

  const handleMoodSelect = (mood: Mood) => {
    setForm((prev) => ({ ...prev, mood: prev.mood === mood ? null : mood }));
  };

  const handleClear = () => {
    setForm(EMPTY_FORM);
    setEditingId(null);
  };

  const handleSave = async () => {
    const dateStr = selectedDate.format('YYYY-MM-DD');
    if (form.systolic !== null && form.diastolic === null) {
      message.warning('请同时填写舒张压');
      return;
    }
    if (form.diastolic !== null && form.systolic === null) {
      message.warning('请同时填写收缩压');
      return;
    }
    if (
      form.systolic !== null &&
      form.diastolic !== null &&
      form.systolic <= form.diastolic
    ) {
      message.warning('收缩压必须大于舒张压');
      return;
    }
    const allEmpty =
      form.systolic === null &&
      form.diastolic === null &&
      form.blood_sugar === null &&
      form.weight === null &&
      form.sleep_hours === null &&
      form.mood === null &&
      !form.notes.trim();
    if (allEmpty) {
      message.warning('请至少填写一项健康指标或备注');
      return;
    }

    setSaving(true);
    try {
      const payload: HealthLogInput = {
        log_date: dateStr,
        systolic: form.systolic,
        diastolic: form.diastolic,
        blood_sugar: form.blood_sugar,
        weight: form.weight,
        sleep_hours: form.sleep_hours,
        mood: form.mood,
        notes: form.notes.trim() || null,
      };
      if (editingId) {
        const update: HealthLogUpdateInput = { ...payload };
        delete (update as { log_date?: string }).log_date;
        const updated = await updateHealthLog(editingId, update);
        message.success(`${updated.log_date} 健康记录已更新`);
      } else {
        const created = await createHealthLog(payload);
        setEditingId(created.id);
        message.success(`${created.log_date} 健康记录已保存`);
      }
      await loadRecent();
    } catch (err) {
      const msg = err instanceof Error ? err.message : '保存失败，请稍后重试';
      message.error(msg);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteHealthLog(id);
      message.success('已删除');
      if (editingId === id) {
        setForm(EMPTY_FORM);
        setEditingId(null);
        setSelectedDate(dayjs());
      }
      await loadRecent();
    } catch (err) {
      const msg = err instanceof Error ? err.message : '删除失败';
      message.error(msg);
    }
  };

  const handleEditFromHistory = (log: HealthLog) => {
    setEditingId(log.id);
    setSelectedDate(dayjs(log.log_date));
    setForm({
      systolic: log.systolic,
      diastolic: log.diastolic,
      blood_sugar: log.blood_sugar,
      weight: log.weight,
      sleep_hours: log.sleep_hours,
      mood: log.mood,
      notes: log.notes ?? '',
    });
    if (isMobile) {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }
  };

  const last7Days = useMemo(() => {
    const map = new Map<string, HealthLog>();
    recentLogs.forEach((l) => map.set(l.log_date, l));
    const days: { date: Dayjs; log: HealthLog | null }[] = [];
    for (let i = 0; i < 7; i++) {
      const d = dayjs().subtract(i, 'day');
      days.push({ date: d, log: map.get(d.format('YYYY-MM-DD')) ?? null });
    }
    return days;
  }, [recentLogs]);

  return (
    <div className="hlog-page">
      <style>{PAGE_CSS}</style>

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
            <HeartOutlined style={{ color: '#ff4d4f' }} />
            每日健康打卡
          </Space>
        </Title>
        <Space wrap>
          <Button icon={<ReloadOutlined />} onClick={() => tryLoadForDate(selectedDate)}>
            刷新
          </Button>
        </Space>
      </div>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={14}>
          <Card
            style={{ borderRadius: 12 }}
            styles={{ body: { padding: isMobile ? 16 : 24 } }}
          >
            <div style={{ marginBottom: 16, display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
              <Text strong style={{ fontSize: 16 }}>打卡日期</Text>
              <DatePicker
                value={selectedDate}
                onChange={handleDateChange}
                allowClear={false}
                disabledDate={(d: Dayjs) => d.isAfter(dayjs(), 'day')}
                size="large"
                style={{ minWidth: 180 }}
              />
              {editingId && (
                <Tag color="blue" icon={<EditOutlined />}>
                  编辑模式
                </Tag>
              )}
            </div>

            {/* 血压 */}
            <div className="hlog-form-section">
              <div className="hlog-form-section-head">
                <div
                  className="hlog-form-section-icon"
                  style={{ background: '#fff1f0', color: '#ff4d4f' }}
                >
                  <HeartOutlined />
                </div>
                <span className="hlog-form-section-title">血压 (mmHg)</span>
              </div>
              <Row gutter={12}>
                <Col xs={12} sm={6}>
                  <Text type="secondary" style={{ fontSize: 14 }}>收缩压</Text>
                  <InputNumber
                    value={form.systolic ?? undefined}
                    onChange={(v) => setForm((p) => ({ ...p, systolic: v ?? null }))}
                    min={40}
                    max={300}
                    size="large"
                    placeholder="如 120"
                    style={{ width: '100%', marginTop: 4 }}
                  />
                </Col>
                <Col xs={12} sm={6}>
                  <Text type="secondary" style={{ fontSize: 14 }}>舒张压</Text>
                  <InputNumber
                    value={form.diastolic ?? undefined}
                    onChange={(v) => setForm((p) => ({ ...p, diastolic: v ?? null }))}
                    min={20}
                    max={200}
                    size="large"
                    placeholder="如 80"
                    style={{ width: '100%', marginTop: 4 }}
                  />
                </Col>
                <Col xs={24} sm={12} style={{ display: 'flex', alignItems: 'flex-end' }}>
                  {form.systolic !== null && form.diastolic !== null && (
                    (() => {
                      const cat = bpCategory(form.systolic, form.diastolic);
                      return (
                        <Tag color="default" style={{ marginTop: 8, fontSize: 14, padding: '4px 10px', color: cat.color, borderColor: cat.color }}>
                          {cat.label}
                        </Tag>
                      );
                    })()
                  )}
                </Col>
              </Row>
            </div>

            {/* 血糖 + 体重 */}
            <div className="hlog-form-section">
              <div className="hlog-form-section-head">
                <div
                  className="hlog-form-section-icon"
                  style={{ background: '#e6fffb', color: '#13c2c2' }}
                >
                  💧
                </div>
                <span className="hlog-form-section-title">血糖 / 体重</span>
              </div>
              <Row gutter={12}>
                <Col xs={12}>
                  <Text type="secondary" style={{ fontSize: 14 }}>血糖 (mmol/L)</Text>
                  <InputNumber
                    value={form.blood_sugar ?? undefined}
                    onChange={(v) => setForm((p) => ({ ...p, blood_sugar: v ?? null }))}
                    min={1}
                    max={40}
                    step={0.1}
                    size="large"
                    placeholder="如 5.6"
                    style={{ width: '100%', marginTop: 4 }}
                  />
                  {form.blood_sugar !== null && (
                    (() => {
                      const cat = sugarCategory(form.blood_sugar);
                      return (
                        <Tag color="default" style={{ marginTop: 6, fontSize: 14, color: cat.color, borderColor: cat.color }}>
                          {cat.label}
                        </Tag>
                      );
                    })()
                  )}
                </Col>
                <Col xs={12}>
                  <Text type="secondary" style={{ fontSize: 14 }}>体重 (kg)</Text>
                  <InputNumber
                    value={form.weight ?? undefined}
                    onChange={(v) => setForm((p) => ({ ...p, weight: v ?? null }))}
                    min={10}
                    max={500}
                    step={0.1}
                    size="large"
                    placeholder="如 65.5"
                    style={{ width: '100%', marginTop: 4 }}
                  />
                </Col>
              </Row>
            </div>

            {/* 睡眠 + 心情 */}
            <div className="hlog-form-section">
              <div className="hlog-form-section-head">
                <div
                  className="hlog-form-section-icon"
                  style={{ background: '#f9f0ff', color: '#722ed1' }}
                >
                  🌙
                </div>
                <span className="hlog-form-section-title">睡眠 / 心情</span>
              </div>
              <Row gutter={12} style={{ marginBottom: 12 }}>
                <Col xs={24} sm={10}>
                  <Text type="secondary" style={{ fontSize: 14 }}>睡眠时长 (小时)</Text>
                  <InputNumber
                    value={form.sleep_hours ?? undefined}
                    onChange={(v) => setForm((p) => ({ ...p, sleep_hours: v ?? null }))}
                    min={0}
                    max={24}
                    step={0.5}
                    size="large"
                    placeholder="如 7.5"
                    style={{ width: '100%', marginTop: 4 }}
                  />
                </Col>
              </Row>
              <Text type="secondary" style={{ fontSize: 14 }}>今天的心情</Text>
              <Row gutter={8} style={{ marginTop: 8 }}>
                {MOOD_OPTIONS.map((opt) => {
                  const selected = form.mood === opt.value;
                  return (
                    <Col xs={8} key={opt.value}>
                      <div
                        className={`hlog-mood-btn ${selected ? 'selected' : ''}`}
                        style={selected ? { borderColor: opt.color } : undefined}
                        onClick={() => handleMoodSelect(opt.value)}
                        role="button"
                        tabIndex={0}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            handleMoodSelect(opt.value);
                          }
                        }}
                      >
                        <span className="hlog-mood-emoji">{MOOD_EMOJI[opt.value]}</span>
                        <span className="hlog-mood-label">{opt.label}</span>
                      </div>
                    </Col>
                  );
                })}
              </Row>
            </div>

            {/* 备注 */}
            <div style={{ marginBottom: 16 }}>
              <Text strong style={{ fontSize: 15, display: 'block', marginBottom: 6 }}>
                今日备注
              </Text>
              <TextArea
                value={form.notes}
                onChange={(e) => setForm((p) => ({ ...p, notes: e.target.value }))}
                rows={3}
                placeholder="记录今天身体感受、症状、特殊情况……"
                maxLength={2000}
                showCount
                size="large"
              />
            </div>

            <Divider style={{ margin: '12px 0' }} />

            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', flexWrap: 'wrap' }}>
              <Button
                icon={<CloseCircleOutlined />}
                onClick={handleClear}
                size="large"
                disabled={saving}
              >
                清空
              </Button>
              <Tooltip title={editingId ? '更新今日记录' : '保存今日记录'}>
                <Button
                  type="primary"
                  icon={<SaveOutlined />}
                  onClick={handleSave}
                  loading={saving}
                  size="large"
                  style={{ minWidth: 140 }}
                >
                  {editingId ? '更新记录' : '保存今日打卡'}
                </Button>
              </Tooltip>
            </div>

            <Alert
              type="info"
              showIcon
              icon={<CheckCircleFilled />}
              message="每日记录健康指标，便于发现长期趋势。所有数据仅本家庭可见。"
              style={{ marginTop: 16, borderRadius: 8 }}
            />
          </Card>
        </Col>

        <Col xs={24} lg={10}>
          <Card
            title={
              <Space>
                <span style={{ fontSize: 18 }}>📅</span>
                <span>最近 7 天</span>
              </Space>
            }
            style={{ borderRadius: 12 }}
            styles={{ body: { padding: isMobile ? 12 : 16 } }}
          >
            {loading ? (
              <Skeleton active paragraph={{ rows: 6 }} />
            ) : last7Days.every((d) => d.log === null) ? (
              <Empty
                description="暂无打卡记录，先填写左侧表单保存第一条吧"
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                style={{ margin: '24px 0' }}
              />
            ) : (
              <Row gutter={[8, 8]}>
                {last7Days.map(({ date, log }) => (
                  <Col xs={24} sm={12} key={date.format('YYYY-MM-DD')}>
                    <HistoryCard
                      date={date}
                      log={log}
                      onEdit={() => log && handleEditFromHistory(log)}
                      onDelete={() => log && handleDelete(log.id)}
                      isToday={date.isSame(dayjs(), 'day')}
                    />
                  </Col>
                ))}
              </Row>
            )}
          </Card>

          {!loading && recentLogs.length > 0 && (
            <div style={{ marginTop: 12, textAlign: 'center' }}>
              <Text type="secondary" style={{ fontSize: 14 }}>
                共 {recentLogs.length} 条记录（最近 30 天）
              </Text>
            </div>
          )}
        </Col>
      </Row>
    </div>
  );
}

interface HistoryCardProps {
  date: Dayjs;
  log: HealthLog | null;
  onEdit: () => void;
  onDelete: () => void;
  isToday: boolean;
}

function HistoryCard({ date, log, onEdit, onDelete, isToday }: HistoryCardProps) {
  const weekday = ['日', '一', '二', '三', '四', '五', '六'][date.day()];
  return (
    <div
      className="hlog-history-card"
      style={isToday ? { borderColor: '#1890ff', background: '#e6f7ff' } : undefined}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
        <span className="hlog-history-date">
          {date.format('MM-DD')} · 周{weekday}
          {isToday && <Tag color="blue" style={{ marginLeft: 6 }}>今日</Tag>}
        </span>
        {log && (
          <Space size={2}>
            <Button
              type="text"
              icon={<EditOutlined />}
              onClick={onEdit}
              aria-label="编辑健康记录"
            />
            <Popconfirm
              title="删除这条健康记录？"
              description="删除后无法恢复，确定删除吗？"
              okText="删除"
              okButtonProps={{ danger: true }}
              cancelText="取消"
              onConfirm={onDelete}
            >
              <Button
                type="text"
                danger
                icon={<DeleteOutlined />}
                aria-label="删除健康记录"
              />
            </Popconfirm>
          </Space>
        )}
      </div>
      {!log ? (
        <Text type="secondary" style={{ fontSize: 14 }}>
          未打卡
        </Text>
      ) : (
        <div>
          {log.systolic !== null && log.diastolic !== null && (
            <div className="hlog-history-metric">
              <span className="hlog-history-metric-label">血压</span>
              <span className="hlog-history-metric-value">
                {log.systolic}/{log.diastolic}
              </span>
            </div>
          )}
          {log.blood_sugar !== null && (
            <div className="hlog-history-metric">
              <span className="hlog-history-metric-label">血糖</span>
              <span className="hlog-history-metric-value">{log.blood_sugar} mmol/L</span>
            </div>
          )}
          {log.weight !== null && (
            <div className="hlog-history-metric">
              <span className="hlog-history-metric-label">体重</span>
              <span className="hlog-history-metric-value">{log.weight} kg</span>
            </div>
          )}
          {log.sleep_hours !== null && (
            <div className="hlog-history-metric">
              <span className="hlog-history-metric-label">睡眠</span>
              <span className="hlog-history-metric-value">{log.sleep_hours} 小时</span>
            </div>
          )}
          {log.mood !== null && (
            <div className="hlog-history-metric">
              <span className="hlog-history-metric-label">心情</span>
              <span className="hlog-history-metric-value">
                {MOOD_EMOJI[log.mood]} {log.mood}
              </span>
            </div>
          )}
          {log.notes && (
            <div style={{ marginTop: 4, fontSize: 14, color: '#595959', lineHeight: 1.5 }}>
              {log.notes.length > 50 ? `${log.notes.slice(0, 50)}…` : log.notes}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
