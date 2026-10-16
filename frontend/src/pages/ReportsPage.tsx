import { useState, useCallback, useEffect } from 'react';
import {
  Card,
  Row,
  Col,
  Tabs,
  Button,
  Tag,
  Typography,
  Skeleton,
  Empty,
  Space,
  Statistic,
  Progress,
  List,
  Checkbox,
  Segmented,
  Alert,
  Divider,
  message,
} from 'antd';
import {
  FileTextOutlined,
  LineChartOutlined,
  MedicineBoxOutlined,
  FilePdfOutlined,
  ReloadOutlined,
  HeartOutlined,
  CoffeeOutlined,
  ThunderboltOutlined,
  HomeOutlined,
  WarningOutlined,
  MessageOutlined,
  CheckCircleOutlined,
  SafetyOutlined,
  AppleOutlined,
  CalendarOutlined,
  DotChartOutlined,
} from '@ant-design/icons';
import {
  getConstitutionReport,
  getHealthTrendReport,
  getPreVisitReport,
  generateReportPdf,
  type ConstitutionReport,
  type HealthTrendReport,
  type PreVisitReport,
  type ReportPeriod,
  type ReportType,
} from '../api/reportApi';
import { listHealthLogs, type HealthLog } from '../api/healthLogApi';
import { getReminderHistory, type CheckInHistory } from '../api/reminderApi';

const { Title, Text, Paragraph } = Typography;

const TAB_ITEMS = [
  {
    key: '体质报告',
    label: (
      <span>
        <HeartOutlined /> 体质报告
      </span>
    ),
  },
  {
    key: '健康趋势',
    label: (
      <span>
        <LineChartOutlined /> 健康趋势
      </span>
    ),
  },
  {
    key: '就诊准备',
    label: (
      <span>
        <FileTextOutlined /> 就诊准备
      </span>
    ),
  },
];

const PERIOD_OPTIONS: { label: string; value: ReportPeriod }[] = [
  { label: '近 7 天', value: '7d' },
  { label: '近 30 天', value: '30d' },
  { label: '近 90 天', value: '90d' },
];

const CONSTITUTION_COLOR: Record<string, string> = {
  平和质: '#52c41a',
  气虚质: '#fa8c16',
  阳虚质: '#fa541c',
  阴虚质: '#13c2c2',
  痰湿质: '#722ed1',
  湿热质: '#eb2f96',
  血瘀质: '#f5222d',
  气郁质: '#2f54eb',
  特禀质: '#a0d911',
};

function adherenceColor(rate: number): string {
  if (rate >= 80) return '#52c41a';
  if (rate >= 60) return '#faad14';
  return '#ff4d4f';
}

// ===========================================================================
// Tab 1 — 体质报告
// ===========================================================================

function ConstitutionReportView({
  report,
}: {
  report: ConstitutionReport | null;
}) {
  if (!report) {
    return (
      <Empty description="暂无体质报告，点击「生成报告」获取" image={Empty.PRESENTED_IMAGE_SIMPLE} />
    );
  }
  const { assessment, recommendations, seasonal_advice, trend } = report;
  const primary = assessment.primary_type;
  const score = primary ? assessment.latest_scores[primary] ?? 0 : 0;
  const primaryColor = primary ? CONSTITUTION_COLOR[primary] ?? '#1890ff' : '#1890ff';

  return (
    <div>
      {/* Header — constitution ring + type */}
      <Card
        bodyStyle={{ padding: 0 }}
        style={{ marginBottom: 16, overflow: 'hidden', border: 'none' }}
      >
        <div
          style={{
            background: `linear-gradient(135deg, ${primaryColor} 0%, ${primaryColor}cc 100%)`,
            padding: '28px 24px',
            color: '#fff',
          }}
        >
          <Row align="middle" gutter={[24, 16]}>
            <Col xs={24} sm={10} style={{ textAlign: 'center' }}>
              <Progress
                type="circle"
                percent={Math.round(score)}
                strokeColor="#fff"
                trailColor="rgba(255,255,255,0.25)"
                format={() => (
                  <span style={{ color: '#fff', fontSize: 22, fontWeight: 600 }}>
                    {Math.round(score)}
                    <span style={{ fontSize: 14 }}>分</span>
                  </span>
                )}
                width={120}
              />
            </Col>
            <Col xs={24} sm={14}>
              <Space direction="vertical" size="small">
                <Text style={{ color: 'rgba(255,255,255,0.85)', fontSize: 14 }}>
                  您的中医体质
                </Text>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                  <span style={{ fontSize: 32, fontWeight: 700 }}>{primary ?? '未测评'}</span>
                  {assessment.secondary_types.length > 0 && (
                    assessment.secondary_types.map((t) => (
                      <Tag
                        key={t}
                        style={{
                          background: 'rgba(255,255,255,0.2)',
                          border: 'none',
                          color: '#fff',
                          fontSize: 14,
                        }}
                      >
                        兼：{t}
                      </Tag>
                    ))
                  )}
                </div>
                <Paragraph style={{ color: 'rgba(255,255,255,0.9)', marginBottom: 0, fontSize: 15 }}>
                  {assessment.description || '完成体质测评获取个性化建议'}
                </Paragraph>
              </Space>
            </Col>
          </Row>
        </div>
      </Card>

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} lg={12}>
          <Card
            size="small"
            title={
              <Space>
                <AppleOutlined style={{ color: '#fa8c16' }} />
                <span>饮食建议</span>
              </Space>
            }
            style={{ height: '100%' }}
          >
            <Row gutter={16}>
              <Col span={12}>
                <Text strong style={{ color: '#52c41a' }}>宜食</Text>
                {recommendations.diet.宜食.length > 0 ? (
                  <ul style={{ paddingLeft: 18, marginTop: 8 }}>
                    {recommendations.diet.宜食.map((item, idx) => (
                      <li key={idx} style={{ marginBottom: 4, fontSize: 14, lineHeight: 1.6 }}>
                        {item}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <Text type="secondary" style={{ display: 'block', marginTop: 8 }}>暂无</Text>
                )}
              </Col>
              <Col span={12}>
                <Text strong style={{ color: '#ff4d4f' }}>忌食</Text>
                {recommendations.diet.忌食.length > 0 ? (
                  <ul style={{ paddingLeft: 18, marginTop: 8 }}>
                    {recommendations.diet.忌食.map((item, idx) => (
                      <li key={idx} style={{ marginBottom: 4, fontSize: 14, lineHeight: 1.6 }}>
                        {item}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <Text type="secondary" style={{ display: 'block', marginTop: 8 }}>暂无</Text>
                )}
              </Col>
            </Row>
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card
            size="small"
            title={
              <Space>
                <ThunderboltOutlined style={{ color: '#52c41a' }} />
                <span>运动建议</span>
              </Space>
            }
            style={{ height: '100%' }}
          >
            {recommendations.exercise.length > 0 ? (
              <ul style={{ paddingLeft: 20, marginBottom: 0 }}>
                {recommendations.exercise.map((item, idx) => (
                  <li key={idx} style={{ marginBottom: 6, fontSize: 14, lineHeight: 1.6 }}>
                    {item}
                  </li>
                ))}
              </ul>
            ) : (
              <Text type="secondary">暂无建议</Text>
            )}
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Card
            size="small"
            title={
              <Space>
                <HomeOutlined style={{ color: '#1890ff' }} />
                <span>起居建议</span>
              </Space>
            }
          >
            {recommendations.lifestyle.length > 0 ? (
              <ul style={{ paddingLeft: 20, marginBottom: 0 }}>
                {recommendations.lifestyle.map((item, idx) => (
                  <li key={idx} style={{ marginBottom: 6, fontSize: 14, lineHeight: 1.6 }}>
                    {item}
                  </li>
                ))}
              </ul>
            ) : (
              <Text type="secondary">暂无建议</Text>
            )}
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card
            size="small"
            title={
              <Space>
                <CalendarOutlined style={{ color: '#722ed1' }} />
                <span>节气养生 · {seasonal_advice.current_term}</span>
              </Space>
            }
          >
            {seasonal_advice.principle ? (
              <Paragraph style={{ marginBottom: 8 }}>{seasonal_advice.principle}</Paragraph>
            ) : (
              <Text type="secondary">暂无节气建议</Text>
            )}
            {seasonal_advice.diet.length > 0 && (
              <div style={{ marginTop: 8 }}>
                <Tag color="purple">当季饮食</Tag>
                <Space wrap size={[4, 4]} style={{ marginTop: 4 }}>
                  {seasonal_advice.diet.slice(0, 3).map((d, idx) => (
                    <Tag key={idx}>{d}</Tag>
                  ))}
                </Space>
              </div>
            )}
          </Card>
        </Col>
      </Row>

      {trend.total_assessments > 1 && (
        <Card size="small" style={{ marginTop: 16 }} title={<Space><LineChartOutlined />测评趋势</Space>}>
          <Text type="secondary">已完成 {trend.total_assessments} 次体质测评</Text>
          <div style={{ marginTop: 12, display: 'flex', gap: 8, overflowX: 'auto', paddingBottom: 4 }}>
            {trend.points.map((p, idx) => (
              <div
                key={idx}
                style={{
                  minWidth: 100,
                  padding: '8px 12px',
                  borderRadius: 8,
                  background: '#fafafa',
                  border: '1px solid #f0f0f0',
                  flexShrink: 0,
                }}
              >
                <div style={{ fontSize: 14, color: '#666' }}>{p.assessed_at.slice(0, 10)}</div>
                <div style={{ fontWeight: 600, fontSize: 15 }}>{p.primary_type}</div>
                <Text style={{ color: CONSTITUTION_COLOR[p.primary_type] ?? '#1890ff', fontWeight: 600 }}>
                  {Math.round(p.primary_score)} 分
                </Text>
              </div>
            ))}
          </div>
        </Card>
      )}

      {report.disclaimer && (
        <Alert
          type="warning"
          showIcon
          icon={<SafetyOutlined />}
          message={report.disclaimer}
          style={{ marginTop: 16 }}
        />
      )}
    </div>
  );
}

// ===========================================================================
// Tab 2 — 健康趋势
// ===========================================================================

function HealthTrendView({ report }: { report: HealthTrendReport | null }) {
  if (!report) {
    return (
      <Empty description="选择周期后点击「生成报告」获取趋势" image={Empty.PRESENTED_IMAGE_SIMPLE} />
    );
  }
  const { medication_adherence, reminder_trends, medicine_cabinet_changes, chat_interaction, safety_check_history } = report;
  const rate = medication_adherence.adherence_rate;

  return (
    <div>
      <HealthMetricCharts />

      <Row gutter={[16, 16]} style={{ marginBottom: 16, marginTop: 16 }}>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <div style={{ textAlign: 'center' }}>
              <Progress
                type="circle"
                percent={Math.round(rate)}
                strokeColor={adherenceColor(rate)}
                width={100}
                format={(p) => `${p}%`}
              />
              <div style={{ marginTop: 8, fontSize: 14, color: '#666' }}>用药依从率</div>
              <Text type="secondary" style={{ fontSize: 14 }}>
                {medication_adherence.taken_count}/{medication_adherence.total_logs} 次按时
              </Text>
            </div>
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="提醒总数"
              value={reminder_trends.total_reminders}
              prefix={<CheckCircleOutlined style={{ color: '#1890ff' }} />}
            />
            <div style={{ marginTop: 8 }}>
              <Tag color="green">启用 {reminder_trends.enabled_reminders}</Tag>
              <Tag>暂停 {reminder_trends.disabled_reminders}</Tag>
            </div>
            <Text type="secondary" style={{ fontSize: 14 }}>
              活跃天数 {reminder_trends.active_days} 天
            </Text>
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="AI 对话次数"
              value={chat_interaction.total_conversations}
              prefix={<MessageOutlined style={{ color: '#722ed1' }} />}
              suffix={` / ${report.period_days}天`}
            />
            <Text type="secondary" style={{ fontSize: 14 }}>
              活跃 {chat_interaction.active_days} 天
            </Text>
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="安全检查"
              value={safety_check_history.total_checks}
              prefix={<SafetyOutlined style={{ color: '#52c41a' }} />}
            />
            <div style={{ marginTop: 8 }}>
              {safety_check_history.warning_count > 0 && (
                <Tag color="orange">⚠ {safety_check_history.warning_count}</Tag>
              )}
              {safety_check_history.critical_count > 0 && (
                <Tag color="red">⛔ {safety_check_history.critical_count}</Tag>
              )}
              {safety_check_history.warning_count === 0 && safety_check_history.critical_count === 0 && (
                <Tag color="green">无风险</Tag>
              )}
            </div>
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} md={12}>
          <Card
            size="small"
            title={<Space><MedicineBoxOutlined style={{ color: '#fa541c' }} />药箱变化</Space>}
          >
            <Row gutter={8}>
              <Col span={6}>
                <Statistic title="新增" value={medicine_cabinet_changes.additions_count} valueStyle={{ fontSize: 20 }} />
              </Col>
              <Col span={6}>
                <Statistic title="删除" value={medicine_cabinet_changes.deletions_count} valueStyle={{ fontSize: 20 }} />
              </Col>
              <Col span={6}>
                <Statistic title="已过期" value={medicine_cabinet_changes.expired_count} valueStyle={{ color: '#ff4d4f', fontSize: 20 }} />
              </Col>
              <Col span={6}>
                <Statistic title="将过期" value={medicine_cabinet_changes.expiring_soon_count} valueStyle={{ color: '#faad14', fontSize: 20 }} />
              </Col>
            </Row>
            {medicine_cabinet_changes.expiring_soon.length > 0 && (
              <div style={{ marginTop: 12 }}>
                <Text type="secondary" strong>即将过期：</Text>
                <div style={{ marginTop: 4 }}>
                  {medicine_cabinet_changes.expiring_soon.slice(0, 5).map((m, idx) => (
                    <Tag key={idx} color="orange" style={{ marginBottom: 4 }}>
                      {m.name}（{m.expiry_date}）
                    </Tag>
                  ))}
                </div>
              </div>
            )}
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card
            size="small"
            title={<Space><LineChartOutlined style={{ color: '#1890ff' }} />每日服药打卡</Space>}
          >
            {reminder_trends.daily_completion.length > 0 ? (
              <DailyCompletionBars data={reminder_trends.daily_completion} />
            ) : (
              <Empty description="暂无打卡记录" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Card>
        </Col>
      </Row>

      {report.disclaimer && (
        <Alert
          type="warning"
          showIcon
          icon={<SafetyOutlined />}
          message={report.disclaimer}
          style={{ marginTop: 16 }}
        />
      )}
    </div>
  );
}

function DailyCompletionBars({ data }: { data: { date: string; count: number }[] }): React.ReactNode {
  const max = Math.max(1, ...data.map((d) => d.count));
  return (
    <div style={{ display: 'flex', alignItems: 'flex-end', gap: 3, height: 80, overflowX: 'auto', paddingBottom: 4 }}>
      {data.map((d, idx) => (
        <div
          key={idx}
          style={{ flexShrink: 0, textAlign: 'center', minWidth: 24 }}
          title={`${d.date}：${d.count} 次`}
        >
          <div
            style={{
              width: '100%',
              height: `${(d.count / max) * 56}px`,
              minHeight: 4,
              background: 'linear-gradient(180deg, #1890ff 0%, #69b1ff 100%)',
              borderRadius: '3px 3px 0 0',
            }}
          />
          <div style={{ fontSize: 14, color: '#666', marginTop: 2 }}>
            {d.date.slice(5)}
          </div>
        </div>
      ))}
    </div>
  );
}

// ===========================================================================
// 健康指标趋势图（来自每日打卡 /api/health-logs）
// ===========================================================================

function HealthMetricCharts() {
  const [logs, setLogs] = useState<HealthLog[]>([]);
  const [adherence, setAdherence] = useState<CheckInHistory | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const [healthLogs, history] = await Promise.all([
          listHealthLogs(30),
          getReminderHistory(7).catch(() => null),
        ]);
        if (cancelled) return;
        setLogs(healthLogs);
        if (history) setAdherence(history);
      } catch {
        if (!cancelled) setLogs([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) {
    return (
      <Card style={{ marginBottom: 16, borderRadius: 12 }}>
        <Skeleton active paragraph={{ rows: 6 }} />
      </Card>
    );
  }

  if (logs.length === 0) {
    return (
      <Card
        style={{ marginBottom: 16, borderRadius: 12 }}
        title={
          <Space>
            <DotChartOutlined style={{ color: '#722ed1' }} />
            <span style={{ fontSize: 18 }}>健康指标趋势</span>
          </Space>
        }
      >
        <Empty
          description={
            <span style={{ fontSize: 15 }}>
              暂无打卡数据，前往「每日打卡」记录血压、血糖等指标查看趋势
            </span>
          }
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          style={{ margin: '24px 0' }}
        />
      </Card>
    );
  }

  const sortedAsc = [...logs].sort((a, b) => a.log_date.localeCompare(b.log_date));
  const last14 = sortedAsc.slice(-14);
  const last14WithBp = last14.filter((l) => l.systolic !== null && l.diastolic !== null);
  const last14Weight = last14.filter((l) => l.weight !== null);
  const last14Sugar = last14.filter((l) => l.blood_sugar !== null);

  return (
    <Card
      style={{ marginBottom: 16, borderRadius: 12 }}
      title={
        <Space>
          <DotChartOutlined style={{ color: '#722ed1' }} />
          <span style={{ fontSize: 18 }}>健康指标趋势</span>
          <Tag color="purple">最近 14 天</Tag>
        </Space>
      }
      extra={
        <Text type="secondary" style={{ fontSize: 14 }}>
          数据来自每日打卡
        </Text>
      }
    >
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <BloodPressureChart logs={last14WithBp} />
        </Col>
        <Col xs={24} lg={12}>
          <WeightLineChart logs={last14Weight} />
        </Col>
        <Col xs={24} lg={12}>
          <BloodSugarDots logs={last14Sugar} />
        </Col>
        <Col xs={24} lg={12}>
          <MedicationAdherenceBars history={adherence} />
        </Col>
      </Row>
    </Card>
  );
}

interface ChartProps {
  logs: HealthLog[];
}

function ChartFrame({
  title,
  subtitle,
  yLabels,
  children,
}: {
  title: string;
  subtitle?: string;
  yLabels: string[];
  children: React.ReactNode;
}) {
  return (
    <div style={{ padding: 8 }}>
      <div style={{ marginBottom: 8 }}>
        <Text strong style={{ fontSize: 15 }}>{title}</Text>
        {subtitle && (
          <Text type="secondary" style={{ fontSize: 14, marginLeft: 6 }}>
            {subtitle}
          </Text>
        )}
      </div>
      <div style={{ display: 'flex', gap: 8, alignItems: 'stretch', minHeight: 180 }}>
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'space-between',
            alignItems: 'flex-end',
            padding: '4px 0',
            minWidth: 42,
            fontSize: 14,
            color: '#666',
            textAlign: 'right',
          }}
        >
          {yLabels.map((l) => (
            <span key={l}>{l}</span>
          ))}
        </div>
        <div style={{ flex: 1, position: 'relative', minWidth: 0 }}>{children}</div>
      </div>
    </div>
  );
}

const BP_COLOR_SYS = '#ff4d4f';
const BP_COLOR_DIA = '#1890ff';

function BloodPressureChart({ logs }: ChartProps) {
  if (logs.length === 0) {
    return (
      <ChartFrame title="血压趋势" yLabels={['180', '120', '60']}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            height: '100%',
            color: '#666',
            fontSize: 14,
          }}
        >
          近 14 天无血压数据
        </div>
      </ChartFrame>
    );
  }
  const max = 180;
  const min = 60;
  const range = max - min;
  return (
    <ChartFrame
      title="血压趋势"
      subtitle="收缩压/舒张压 (mmHg)"
      yLabels={['180', '150', '120', '90', '60']}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-end',
          gap: 4,
          height: '100%',
          paddingBottom: 24,
          overflowX: 'auto',
        }}
      >
        {logs.map((log, idx) => {
          const sysH = ((log.systolic! - min) / range) * 100;
          const diaH = ((log.diastolic! - min) / range) * 100;
          return (
            <div
              key={`${log.id}-${idx}`}
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                flex: '1 0 28px',
                minWidth: 28,
                height: '100%',
                justifyContent: 'flex-end',
              }}
              title={`${log.log_date} 收缩压 ${log.systolic} / 舒张压 ${log.diastolic}`}
            >
              <div
                style={{
                  display: 'flex',
                  gap: 2,
                  alignItems: 'flex-end',
                  height: '100%',
                  width: '100%',
                  justifyContent: 'center',
                }}
              >
                <div
                  style={{
                    width: 8,
                    height: `${Math.max(2, sysH)}%`,
                    background: BP_COLOR_SYS,
                    borderRadius: '2px 2px 0 0',
                  }}
                />
                <div
                  style={{
                    width: 8,
                    height: `${Math.max(2, diaH)}%`,
                    background: BP_COLOR_DIA,
                    borderRadius: '2px 2px 0 0',
                  }}
                />
              </div>
              <div style={{ fontSize: 14, color: '#666', marginTop: 2, whiteSpace: 'nowrap' }}>
                {log.log_date.slice(5)}
              </div>
            </div>
          );
        })}
      </div>
      <div style={{ marginTop: 4, fontSize: 14, color: '#666' }}>
        <span
          style={{
            display: 'inline-block',
            width: 10,
            height: 10,
            background: BP_COLOR_SYS,
            marginRight: 4,
            verticalAlign: 'middle',
          }}
        />
        收缩压
        <span
          style={{
            display: 'inline-block',
            width: 10,
            height: 10,
            background: BP_COLOR_DIA,
            margin: '0 4px 0 10px',
            verticalAlign: 'middle',
          }}
        />
        舒张压
      </div>
    </ChartFrame>
  );
}

const WEIGHT_COLOR = '#722ed1';

function WeightLineChart({ logs }: ChartProps) {
  if (logs.length < 2) {
    return (
      <ChartFrame title="体重趋势" yLabels={['80', '60', '40']}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            height: '100%',
            color: '#666',
            fontSize: 14,
          }}
        >
          近 14 天体重数据不足
        </div>
      </ChartFrame>
    );
  }
  const firstLog = logs[0]!;
  const lastLog = logs[logs.length - 1]!;
  const values = logs.map((l) => l.weight!);
  const max = Math.max(...values);
  const min = Math.min(...values);
  const padding = Math.max(0.5, (max - min) * 0.2);
  const yMax = max + padding;
  const yMin = Math.max(0, min - padding);
  const yRange = yMax - yMin || 1;
  const yLabels = [
    yMax.toFixed(1),
    ((yMax + yMin) / 2).toFixed(1),
    yMin.toFixed(1),
  ];

  const W = 100;
  const H = 100;
  const points = logs.map((l, i) => {
    const x = (i / (logs.length - 1)) * W;
    const y = H - ((l.weight! - yMin) / yRange) * H;
    return [x, y] as const;
  });
  const pathD = points
    .map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(2)},${y.toFixed(2)}`)
    .join(' ');

  return (
    <ChartFrame title="体重趋势" subtitle="kg" yLabels={yLabels}>
      <div style={{ position: 'relative', height: '100%', paddingBottom: 24 }}>
        <svg
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
          style={{ width: '100%', height: '100%', display: 'block' }}
        >
          <line
            x1="0"
            y1="50"
            x2="100"
            y2="50"
            stroke="#f0f0f0"
            strokeWidth="0.4"
          />
          <path
            d={pathD}
            fill="none"
            stroke={WEIGHT_COLOR}
            strokeWidth="1.5"
            strokeLinejoin="round"
            strokeLinecap="round"
            vectorEffect="non-scaling-stroke"
          />
          {points.map(([x, y], i) => (
            <circle
              key={i}
              cx={x}
              cy={y}
              r="1.2"
              fill={WEIGHT_COLOR}
              vectorEffect="non-scaling-stroke"
            />
          ))}
        </svg>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            position: 'absolute',
            bottom: 0,
            left: 0,
            right: 0,
            fontSize: 14,
            color: '#666',
          }}
        >
          <span>{firstLog.log_date.slice(5)}</span>
          <span>{lastLog.log_date.slice(5)}</span>
        </div>
      </div>
      <div style={{ marginTop: 4, fontSize: 14, color: '#666' }}>
        <Text strong style={{ color: WEIGHT_COLOR }}>
          {lastLog.weight} kg
        </Text>
        <Text type="secondary" style={{ marginLeft: 8 }}>
          {(() => {
            const diff = lastLog.weight! - firstLog.weight!;
            const sign = diff > 0 ? '+' : '';
            const color = diff > 0 ? '#fa8c16' : diff < 0 ? '#52c41a' : '#666';
            return (
              <span style={{ color }}>
                {sign}
                {diff.toFixed(1)} kg
              </span>
            );
          })()}
        </Text>
      </div>
    </ChartFrame>
  );
}

const SUGAR_COLOR_NORMAL = '#52c41a';
const SUGAR_COLOR_WARN = '#fa8c16';
const SUGAR_COLOR_HIGH = '#ff4d4f';

function BloodSugarDots({ logs }: ChartProps) {
  if (logs.length === 0) {
    return (
      <ChartFrame title="血糖趋势" yLabels={['12', '7', '3']}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            height: '100%',
            color: '#666',
            fontSize: 14,
          }}
        >
          近 14 天无血糖数据
        </div>
      </ChartFrame>
    );
  }
  const max = 12;
  const min = 3;
  const range = max - min;
  const sugarColor = (v: number) => {
    if (v <= 6.1) return SUGAR_COLOR_NORMAL;
    if (v <= 7.8) return SUGAR_COLOR_WARN;
    return SUGAR_COLOR_HIGH;
  };
  return (
    <ChartFrame
      title="血糖趋势"
      subtitle="mmol/L"
      yLabels={['12', '9', '6', '3']}
    >
      <div style={{ position: 'relative', height: '100%', paddingBottom: 24 }}>
        {[6.1, 7.8].map((threshold) => {
          const pct = ((threshold - min) / range) * 100;
          const bottom = 100 - pct;
          return (
            <div
              key={threshold}
              style={{
                position: 'absolute',
                left: 0,
                right: 0,
                bottom: `${bottom}%`,
                borderTop: `1px dashed ${
                  threshold <= 6.1 ? SUGAR_COLOR_NORMAL : SUGAR_COLOR_WARN
                }`,
                opacity: 0.5,
                fontSize: 14,
                color: '#666',
                paddingLeft: 4,
              }}
            >
              <span style={{ background: '#fff', padding: '0 2px' }}>
                {threshold}
              </span>
            </div>
          );
        })}
        <div
          style={{
            display: 'flex',
            alignItems: 'flex-end',
            gap: 4,
            height: '100%',
            justifyContent: 'space-around',
          }}
        >
          {logs.map((log, idx) => {
            const v = log.blood_sugar!;
            const pct = Math.min(100, Math.max(0, ((v - min) / range) * 100));
            return (
              <div
                key={`${log.id}-${idx}`}
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  flex: '1 0 24px',
                  minWidth: 24,
                  height: '100%',
                  justifyContent: 'flex-end',
                  position: 'relative',
                }}
                title={`${log.log_date} 血糖 ${v} mmol/L`}
              >
                <div
                  style={{
                    width: 14,
                    height: 14,
                    borderRadius: '50%',
                    background: sugarColor(v),
                    marginBottom: `${100 - pct}%`,
                    boxShadow: `0 0 0 2px rgba(255,255,255,0.8)`,
                  }}
                />
                <div style={{ fontSize: 14, color: '#666', marginTop: 2 }}>
                  {log.log_date.slice(5)}
                </div>
              </div>
            );
          })}
        </div>
      </div>
      <div style={{ marginTop: 4, fontSize: 14, color: '#666' }}>
        <span style={{ color: SUGAR_COLOR_NORMAL }}>●</span> 正常 ≤6.1　
        <span style={{ color: SUGAR_COLOR_WARN }}>●</span> 偏高 6.1-7.8　
        <span style={{ color: SUGAR_COLOR_HIGH }}>●</span> 高 &gt;7.8
      </div>
    </ChartFrame>
  );
}

function MedicationAdherenceBars({ history }: { history: CheckInHistory | null }) {
  if (!history || history.items.length === 0) {
    return (
      <ChartFrame title="用药依从" subtitle="近 7 天" yLabels={['100%', '50%', '0%']}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            height: '100%',
            color: '#666',
            fontSize: 14,
          }}
        >
          近 7 天无打卡记录
        </div>
      </ChartFrame>
    );
  }
  const byDate = new Map<string, { total: number; taken: number }>();
  history.items.forEach((item) => {
    const day = item.date;
    const cur = byDate.get(day) ?? { total: 0, taken: 0 };
    cur.total += 1;
    if (item.taken) cur.taken += 1;
    byDate.set(day, cur);
  });
  const days = Array.from(byDate.entries()).sort((a, b) => a[0].localeCompare(b[0]));
  const color = (rate: number) => {
    if (rate >= 80) return '#52c41a';
    if (rate >= 60) return '#faad14';
    return '#ff4d4f';
  };
  return (
    <ChartFrame
      title="用药依从"
      subtitle="近 7 天打卡率"
      yLabels={['100%', '75%', '50%', '25%', '0%']}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-end',
          gap: 8,
          height: '100%',
          paddingBottom: 24,
        }}
      >
        {days.map(([day, stat]) => {
          const rate = stat.total > 0 ? Math.round((stat.taken / stat.total) * 100) : 0;
          return (
            <div
              key={day}
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                flex: 1,
                height: '100%',
                justifyContent: 'flex-end',
              }}
              title={`${day} 服药 ${stat.taken}/${stat.total}（${rate}%）`}
            >
              <Text style={{ fontSize: 14, color: color(rate), fontWeight: 600 }}>{rate}%</Text>
              <div
                style={{
                  width: '100%',
                  maxWidth: 36,
                  height: `${Math.max(2, rate)}%`,
                  background: `linear-gradient(180deg, ${color(rate)} 0%, ${color(rate)}aa 100%)`,
                  borderRadius: '4px 4px 0 0',
                  marginTop: 2,
                }}
              />
              <div style={{ fontSize: 14, color: '#666', marginTop: 2 }}>
                {day.slice(5)}
              </div>
            </div>
          );
        })}
      </div>
      <div style={{ marginTop: 4, fontSize: 14, color: '#666' }}>
        <Text strong>{history.taken_count}</Text> / {history.total} 次按时（
        <Text strong style={{ color: color(history.adherence_rate) }}>
          {history.adherence_rate.toFixed(0)}%
        </Text>
        ）
      </div>
    </ChartFrame>
  );
}

// ===========================================================================
// Tab 3 — 就诊准备
// ===========================================================================

function PreVisitView({ report }: { report: PreVisitReport | null }) {
  const [checkedQuestions, setCheckedQuestions] = useState<number[]>([]);

  if (!report) {
    return (
      <Empty description="暂无就诊准备报告，点击「生成报告」获取" image={Empty.PRESENTED_IMAGE_SIMPLE} />
    );
  }
  const { patient_info, medications, allergies, health_conditions, constitution, questions_for_doctor } = report;
  const age = patient_info.birth_year ? new Date().getFullYear() - patient_info.birth_year : null;

  return (
    <div>
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} md={8}>
          <Card size="small" title={<Space><FileTextOutlined style={{ color: '#1890ff' }} />患者信息</Space>}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <div><Text type="secondary">姓名：</Text><Text strong>{patient_info.display_name ?? '未填写'}</Text></div>
              <div>
                <Text type="secondary">性别：</Text><Text>{patient_info.gender ?? '未填写'}</Text>
                {age && <Text type="secondary"> · {age} 岁</Text>}
              </div>
              {patient_info.blood_type && (
                <div><Text type="secondary">血型：</Text><Tag color="red">{patient_info.blood_type} 型</Tag></div>
              )}
              {patient_info.height_cm && patient_info.weight_kg && (
                <div><Text type="secondary">身高/体重：</Text><Text>{patient_info.height_cm}cm / {patient_info.weight_kg}kg</Text></div>
              )}
              {patient_info.is_pregnant && <Tag color="magenta">孕期</Tag>}
            </div>
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card size="small" title={<Space><WarningOutlined style={{ color: '#fa541c' }} />过敏与病史</Space>}>
            <Text type="secondary">过敏史：</Text>
            <div style={{ marginBottom: 8 }}>
              {allergies.length > 0 ? (
                <Space wrap>{allergies.map((a) => <Tag key={a} color="red">{a}</Tag>)}</Space>
              ) : (
                <Text type="secondary">无</Text>
              )}
            </div>
            <Text type="secondary">健康问题：</Text>
            <div>
              {health_conditions.length > 0 ? (
                <Space wrap>{health_conditions.map((c) => <Tag key={c} color="orange">{c}</Tag>)}</Space>
              ) : (
                <Text type="secondary">无</Text>
              )}
            </div>
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card size="small" title={<Space><HeartOutlined style={{ color: '#722ed1' }} />体质摘要</Space>}>
            {constitution.primary_type ? (
              <Space direction="vertical" size="small">
                <Tag color="purple" style={{ fontSize: 16, padding: '4px 12px' }}>{constitution.primary_type}</Tag>
                {constitution.secondary_types.length > 0 && (
                  <Space wrap size={[4, 4]}>
                    {constitution.secondary_types.map((s) => <Tag key={s}>兼：{s}</Tag>)}
                  </Space>
                )}
                <Paragraph style={{ fontSize: 14, marginBottom: 0, marginTop: 4 }}>
                  {constitution.description}
                </Paragraph>
              </Space>
            ) : (
              <Text type="secondary">尚未测评</Text>
            )}
          </Card>
        </Col>
      </Row>

      <Card
        size="small"
        style={{ marginBottom: 16 }}
        title={
          <Space>
            <MedicineBoxOutlined style={{ color: '#1890ff' }} />
            <span>当前用药</span>
            <Tag color="blue">{medications.length} 种</Tag>
          </Space>
        }
      >
        {medications.length > 0 ? (
          <List
            size="small"
            dataSource={medications}
            renderItem={(m) => (
              <List.Item>
                <Space style={{ width: '100%', justifyContent: 'space-between' }} wrap>
                  <Space wrap>
                    <Text strong>{m.name}</Text>
                    {m.specification && <Text type="secondary">{m.specification}</Text>}
                    {m.drug_class && <Tag>{m.drug_class}</Tag>}
                  </Space>
                  <Space size="small">
                    {m.dosage && <Text type="secondary">{m.dosage}</Text>}
                    {m.quantity !== null && m.quantity <= 7 && (
                      <Tag color="orange">库存 {m.quantity}</Tag>
                    )}
                    {m.expiry_date && (
                      <Tag color="default">效期 {m.expiry_date}</Tag>
                    )}
                  </Space>
                </Space>
              </List.Item>
            )}
          />
        ) : (
          <Empty description="药箱暂无药品" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        )}
      </Card>

      <Card
        title={
          <Space>
            <CoffeeOutlined style={{ color: '#52c41a' }} />
            <span>就诊待问清单</span>
          </Space>
        }
      >
        {questions_for_doctor.length > 0 ? (
          <Checkbox.Group
            value={checkedQuestions}
            onChange={(values) => setCheckedQuestions(values as number[])}
            style={{ width: '100%' }}
          >
            <Space direction="vertical" style={{ width: '100%' }}>
              {questions_for_doctor.map((q, idx) => (
                <Checkbox key={idx} value={idx} style={{ alignItems: 'flex-start' }}>
                  <Text>{q}</Text>
                </Checkbox>
              ))}
            </Space>
          </Checkbox.Group>
        ) : (
          <Empty description="暂无待问问题" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        )}
        <Divider style={{ margin: '12px 0' }} />
        <Space>
          <Tag color={checkedQuestions.length === questions_for_doctor.length && questions_for_doctor.length > 0 ? 'green' : 'default'}>
            已准备 {checkedQuestions.length}/{questions_for_doctor.length}
          </Tag>
        </Space>
      </Card>

      {report.disclaimer && (
        <Alert
          type="warning"
          showIcon
          icon={<SafetyOutlined />}
          message={report.disclaimer}
          style={{ marginTop: 16 }}
        />
      )}
    </div>
  );
}

// ===========================================================================
// Main Page
// ===========================================================================

export default function ReportsPage() {
  const [activeTab, setActiveTab] = useState<string>('体质报告');
  const [period, setPeriod] = useState<ReportPeriod>('30d');
  const [loading, setLoading] = useState(false);
  const [pdfLoading, setPdfLoading] = useState(false);

  const [constitutionReport, setConstitutionReport] = useState<ConstitutionReport | null>(null);
  const [trendReport, setTrendReport] = useState<HealthTrendReport | null>(null);
  const [preVisitReport, setPreVisitReport] = useState<PreVisitReport | null>(null);

  const handleGenerate = useCallback(async () => {
    setLoading(true);
    try {
      if (activeTab === '体质报告') {
        const r = await getConstitutionReport();
        setConstitutionReport(r);
        message.success('体质报告已生成');
      } else if (activeTab === '健康趋势') {
        const r = await getHealthTrendReport(period);
        setTrendReport(r);
        message.success('健康趋势报告已生成');
      } else {
        const r = await getPreVisitReport();
        setPreVisitReport(r);
        message.success('就诊准备报告已生成');
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : '报告生成失败';
      message.error(msg);
    } finally {
      setLoading(false);
    }
  }, [activeTab, period]);

  const handleExportPdf = async () => {
    setPdfLoading(true);
    try {
      let reportType: ReportType;
      if (activeTab === '体质报告') reportType = 'constitution';
      else if (activeTab === '健康趋势') reportType = 'health-trend';
      else reportType = 'pre-visit';
      await generateReportPdf(reportType, period);
      message.success('PDF 已开始下载');
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'PDF 导出失败';
      message.error(msg);
    } finally {
      setPdfLoading(false);
    }
  };

  const handleRefresh = () => {
    if (activeTab === '体质报告') setConstitutionReport(null);
    else if (activeTab === '健康趋势') setTrendReport(null);
    else setPreVisitReport(null);
  };

  const hasReport =
    (activeTab === '体质报告' && constitutionReport) ||
    (activeTab === '健康趋势' && trendReport) ||
    (activeTab === '就诊准备' && preVisitReport);

  return (
    <div>
      <Row justify="space-between" align="middle" style={{ marginBottom: 16 }} gutter={[16, 16]}>
        <Col>
          <Title level={3} style={{ marginBottom: 0 }}>
            <FileTextOutlined style={{ marginRight: 8, color: '#1890ff' }} />
            报告中心
          </Title>
        </Col>
        <Col>
          <Space wrap>
            {activeTab === '健康趋势' && (
              <Segmented
                options={PERIOD_OPTIONS}
                value={period}
                onChange={(v) => setPeriod(v as ReportPeriod)}
              />
            )}
            {hasReport && (
              <Button icon={<ReloadOutlined />} onClick={handleRefresh}>
                重置
              </Button>
            )}
            <Button
              type="primary"
              icon={<FileTextOutlined />}
              loading={loading}
              onClick={handleGenerate}
            >
              生成报告
            </Button>
            <Button
              icon={<FilePdfOutlined />}
              loading={pdfLoading}
              onClick={handleExportPdf}
              disabled={!hasReport}
            >
              导出 PDF
            </Button>
          </Space>
        </Col>
      </Row>

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={TAB_ITEMS}
        style={{ marginBottom: 16 }}
      />

      {loading ? (
        <Skeleton active paragraph={{ rows: 8 }} />
      ) : activeTab === '体质报告' ? (
        <ConstitutionReportView report={constitutionReport} />
      ) : activeTab === '健康趋势' ? (
        <HealthTrendView report={trendReport} />
      ) : (
        <PreVisitView report={preVisitReport} />
      )}
    </div>
  );
}
