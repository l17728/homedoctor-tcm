import { useState, useEffect } from 'react';
import { Card, Row, Col, Statistic, Button, Typography, Skeleton, Alert, Space, Empty, Timeline, InputNumber, Tag, message } from 'antd';
import {
  MedicineBoxOutlined,
  BookOutlined,
  BellOutlined,
  PlusOutlined,
  SunOutlined,
  WarningOutlined,
  ExclamationCircleOutlined,
  SafetyOutlined,
  CalendarOutlined,
  MessageOutlined,
  CheckCircleOutlined,
  HeartOutlined,
  HistoryOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { getDashboardStats, type DashboardStats } from '../api/dashboardApi';
import { getDailyHealth, type DailyHealth } from '../api/dailyHealthApi';
import { getLatestAssessment, type ConstitutionResult } from '../api/constitutionApi';
import { getProfile, type UserProfile } from '../api/profileApi';
import {
  getTodayReminders,
  getReminderHistory,
  checkInReminder,
  type TodayReminderSlot,
  type CheckInHistory,
} from '../api/reminderApi';
import { createHealthLog } from '../api/healthLogApi';
import { request } from '../api/client';
import OnboardingWizard, { ONBOARDING_KEY } from '../components/OnboardingWizard';

const { Title, Text, Paragraph } = Typography;

// 必须与后端 app/constitution_data.py CONSTITUTION_DESCRIPTIONS 保持一致
const CONSTITUTION_DESCRIPTIONS: Record<string, string> = {
  平和质: '体态适中、面色红润、精力充沛，是最健康的体质类型。',
  气虚质: '元气不足，易疲乏、气短、自汗，需要益气健脾。',
  阳虚质: '阳气不足，畏寒怕冷、手足不温，需要温阳补火。',
  阴虚质: '阴液亏少，口燥咽干、手足心热，需要滋阴润燥。',
  痰湿质: '痰湿凝聚，体形肥胖、腹部肥满，需要化痰祛湿。',
  湿热质: '湿热内蕴，面垢油光、口苦，需要清热利湿。',
  血瘀质: '血行不畅，肤色晦黯、易有瘀斑，需要活血化瘀。',
  气郁质: '气机郁滞，情绪低落、敏感多虑，需要疏肝解郁。',
  特禀质: '先天禀赋异常，易过敏，需要益气固表。',
};

function ConstitutionRing({
  score,
  primaryType,
}: {
  score: number;
  primaryType: string;
}) {
  const radius = 60;
  const circumference = 2 * Math.PI * radius;
  const clamped = Math.max(0, Math.min(100, score));
  const offset = circumference - (clamped / 100) * circumference;

  return (
    <div
      style={{
        position: 'relative',
        width: 140,
        height: 140,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        margin: '0 auto',
      }}
    >
      <svg width={140} height={140} viewBox="0 0 140 140" style={{ transform: 'rotate(-90deg)' }}>
        <circle cx={70} cy={70} r={radius} fill="none" stroke="#f0f0f0" strokeWidth={10} />
        <circle
          cx={70}
          cy={70}
          r={radius}
          fill="none"
          stroke="#1890ff"
          strokeWidth={10}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          style={{ transition: 'stroke-dashoffset 0.8s ease-in-out' }}
        />
      </svg>
      <div
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          width: '100%',
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <div style={{ fontSize: 24, fontWeight: 600, color: '#1890ff', lineHeight: 1.2 }}>
          {Math.round(clamped)}
          <span style={{ fontSize: 14, fontWeight: 400 }}>分</span>
        </div>
        <div style={{ fontSize: 16, marginTop: 4, color: 'rgba(0,0,0,0.85)' }}>{primaryType}</div>
      </div>
    </div>
  );
}

interface ActivityItem {
  color: string;
  text: string;
  timestamp: string;
}

function buildActivityItems(
  history: CheckInHistory | null,
  constitution: ConstitutionResult | null,
  todayReminders: TodayReminderSlot[],
): ActivityItem[] {
  const items: ActivityItem[] = [];
  const todayStr = new Date().toISOString().slice(0, 10);

  for (const r of todayReminders) {
    const name = r.medicine_name || r.herb_name || r.formula_name || r.title;
    if (!name) continue;
    const ts = `${todayStr}T${(r.time || '00:00').padStart(5, '0')}:00`;
    if (r.status === '已服') {
      items.push({ color: 'green', text: `按时服药：${name}`, timestamp: ts });
    } else if (r.status === '漏服') {
      items.push({ color: 'red', text: `漏服：${name}`, timestamp: ts });
    }
  }

  if (history) {
    for (const log of history.items) {
      if (log.date === todayStr) continue; // 跳过今日，已在 todayReminders 中处理
      const name =
        log.medicine_name || log.herb_name || log.formula_name || log.title || '药品';
      const ts = log.created_at || `${log.date}T00:00:00`;
      if (log.taken) {
        items.push({ color: 'green', text: `按时服药：${name}`, timestamp: ts });
      } else {
        items.push({ color: 'red', text: `漏服：${name}`, timestamp: ts });
      }
    }
  }

  if (constitution?.assessed_at) {
    items.push({
      color: 'purple',
      text: '完成体质评估',
      timestamp: constitution.assessed_at,
    });
  }

  items.sort((a, b) => b.timestamp.localeCompare(a.timestamp));
  return items.slice(0, 8);
}

function formatRelativeTime(ts: string): string {
  try {
    const date = new Date(ts);
    const now = Date.now();
    const diffMs = now - date.getTime();
    const diffMin = Math.floor(diffMs / 60000);
    const diffHour = Math.floor(diffMs / 3600000);
    const diffDay = Math.floor(diffMs / 86400000);

    if (diffMin < 1) return '刚刚';
    if (diffMin < 60) return `${diffMin}分钟前`;
    if (diffHour < 24) return `${diffHour}小时前`;
    if (diffDay < 30) return `${diffDay}天前`;
    return `${date.getMonth() + 1}月${date.getDate()}日`;
  } catch {
    return '';
  }
}

export default function Dashboard() {
  // 通知轮询已移至 AppLayout/ElderlyLayout 挂载（全局生效，不重复轮询/蜂鸣）
  const navigate = useNavigate();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [dailyHealth, setDailyHealth] = useState<DailyHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [expiryAlerts, setExpiryAlerts] = useState<{
    expired: { id: string; name: string; expiry_date: string }[];
    expiring_soon: { id: string; name: string; expiry_date: string }[];
    low_stock: { id: string; name: string; quantity: number }[];
  }>({ expired: [], expiring_soon: [], low_stock: [] });
  const [constitution, setConstitution] = useState<ConstitutionResult | null>(null);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [todayReminders, setTodayReminders] = useState<TodayReminderSlot[]>([]);
  const [checkInHistory, setCheckInHistory] = useState<CheckInHistory | null>(null);

  // 新手引导
  const [onboardingOpen, setOnboardingOpen] = useState(false);

  // 今日待服药品 — 打卡状态
  const [checkedInKeys, setCheckedInKeys] = useState<Set<string>>(new Set());
  const [checkInBusy, setCheckInBusy] = useState<string | null>(null);

  // 健康打卡 — 快速记录
  const [hpSystolic, setHpSystolic] = useState<number | null>(null);
  const [hpDiastolic, setHpDiastolic] = useState<number | null>(null);
  const [hpSugar, setHpSugar] = useState<number | null>(null);
  const [hpSaving, setHpSaving] = useState(false);
  const [hpRecorded, setHpRecorded] = useState(false);

  useEffect(() => {
    if (!localStorage.getItem(ONBOARDING_KEY)) {
      setOnboardingOpen(true);
    }
  }, []);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const [s, dh] = await Promise.all([
          getDashboardStats(),
          getDailyHealth(),
        ]);
        setStats(s);
        setDailyHealth(dh);
        try {
          const alerts = await request<typeof expiryAlerts>(
            '/api/medicines/alerts/expiring',
          );
          setExpiryAlerts(alerts);
        } catch {
          // non-critical
        }

        // 404 is expected for new users — no constitution assessment yet
        try {
          setConstitution(await getLatestAssessment());
        } catch {
          // silently ignore — new users have no assessment
        }

        const settled = await Promise.allSettled([
          getProfile(),
          getTodayReminders(),
          getReminderHistory(7),
        ]);
        if (settled[0].status === 'fulfilled') setProfile(settled[0].value);
        if (settled[1].status === 'fulfilled') setTodayReminders(settled[1].value);
        if (settled[2].status === 'fulfilled') setCheckInHistory(settled[2].value);
      } catch {
        // handled by fallback in API
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const slotKey = (r: TodayReminderSlot) => `${r.reminder_id}:${r.time}`;

  const handleCheckIn = async (r: TodayReminderSlot) => {
    const key = slotKey(r);
    setCheckInBusy(key);
    try {
      await checkInReminder(r.reminder_id, r.time, true);
      setCheckedInKeys((prev) => new Set(prev).add(key));
      message.success(`已记录：${r.medicine_name || r.herb_name || r.formula_name || r.title}`);
    } catch {
      message.error('打卡失败，请稍后重试');
    } finally {
      setCheckInBusy(null);
    }
  };

  const handleSaveHealthLog = async () => {
    if (hpSystolic == null && hpDiastolic == null && hpSugar == null) {
      message.warning('请至少填写一项健康指标');
      return;
    }
    setHpSaving(true);
    try {
      await createHealthLog({
        log_date: new Date().toISOString().slice(0, 10),
        systolic: hpSystolic,
        diastolic: hpDiastolic,
        blood_sugar: hpSugar,
      });
      setHpRecorded(true);
      message.success('健康指标已记录');
    } catch {
      message.error('记录失败，请稍后重试');
    } finally {
      setHpSaving(false);
    }
  };

  // 待服药品（状态=待服 且 本次会话尚未打卡）
  const pendingReminders = todayReminders.filter(
    (r) => r.status === '待服' && !checkedInKeys.has(slotKey(r)),
  );
  const takenToday = todayReminders.filter(
    (r) => r.status === '已服' || checkedInKeys.has(slotKey(r)),
  );
  const allDone = todayReminders.length > 0 && pendingReminders.length === 0;

  if (loading) {
    return (
      <div>
        <Title level={3}>今日健康</Title>
        <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
          {[1, 2, 3].map((i) => (
            <Col key={i} xs={24} lg={8}>
              <Skeleton active paragraph={{ rows: 2 }} />
            </Col>
          ))}
        </Row>
        <Skeleton active paragraph={{ rows: 3 }} />
      </div>
    );
  }

  return (
    <div>
      <Title level={3}>今日健康任务</Title>
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        {/* Card 1：今日待服药品 */}
        <Col xs={24} lg={8}>
          <Card
            style={{ height: '100%' }}
            title={
              <span>
                <MedicineBoxOutlined style={{ marginRight: 8, color: '#1890ff' }} />
                今日待服药品
              </span>
            }
          >
            {todayReminders.length === 0 ? (
              <Empty
                description="今日暂无提醒"
                image={Empty.PRESENTED_IMAGE_SIMPLE}
              >
                <Button
                  type="primary"
                  icon={<PlusOutlined />}
                  onClick={() => navigate('/reminders')}
                >
                  去设置提醒
                </Button>
              </Empty>
            ) : allDone ? (
              <div style={{ textAlign: 'center', padding: '12px 0' }}>
                <CheckCircleOutlined style={{ fontSize: 40, color: '#52c41a' }} />
                <div style={{ marginTop: 8, fontSize: 16, fontWeight: 600, color: '#52c41a' }}>
                  全部完成🎉
                </div>
                <Text type="secondary" style={{ fontSize: 14 }}>
                  今日已服 {takenToday.length} 次，坚持真好！
                </Text>
              </div>
            ) : (
              <Space direction="vertical" style={{ width: '100%' }} size="small">
                {pendingReminders.map((r) => {
                  const name = r.medicine_name || r.herb_name || r.formula_name || r.title;
                  return (
                    <div
                      key={slotKey(r)}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        gap: 8,
                        padding: '6px 0',
                      }}
                    >
                      <div>
                        <Text style={{ fontSize: 16 }}>{r.time}</Text>
                        <Text style={{ fontSize: 16, marginLeft: 8 }}>{name}</Text>
                        {r.dosage && (
                          <Text type="secondary" style={{ fontSize: 14, marginLeft: 8 }}>
                            {r.dosage}
                          </Text>
                        )}
                      </div>
                      <Button
                        type="primary"
                        style={{ minWidth: 64, minHeight: 44 }}
                        loading={checkInBusy === slotKey(r)}
                        onClick={() => handleCheckIn(r)}
                      >
                        打卡
                      </Button>
                    </div>
                  );
                })}
                {takenToday.length > 0 && (
                  <div style={{ borderTop: '1px solid #f0f0f0', marginTop: 4, paddingTop: 8 }}>
                    <Text type="secondary" style={{ fontSize: 14 }}>
                      已完成 {takenToday.length} 项：
                    </Text>
                    {takenToday.slice(0, 4).map((r) => {
                      const name = r.medicine_name || r.herb_name || r.formula_name || r.title;
                      return (
                        <Tag key={slotKey(r)} style={{ marginLeft: 6 }}>
                          <CheckCircleOutlined style={{ color: '#52c41a', marginRight: 2 }} />
                          {name}
                        </Tag>
                      );
                    })}
                  </div>
                )}
              </Space>
            )}
          </Card>
        </Col>

        {/* Card 2：健康打卡 */}
        <Col xs={24} lg={8}>
          <Card
            style={{ height: '100%' }}
            title={
              <span>
                <HeartOutlined style={{ marginRight: 8, color: '#ff4d4f' }} />
                健康打卡
              </span>
            }
          >
            {hpRecorded ? (
              <div style={{ textAlign: 'center', padding: '12px 0' }}>
                <CheckCircleOutlined style={{ fontSize: 40, color: '#52c41a' }} />
                <div style={{ marginTop: 8, fontSize: 16, fontWeight: 600 }}>已记录✓</div>
                <Button
                  type="link"
                  onClick={() => {
                    setHpRecorded(false);
                    setHpSystolic(null);
                    setHpDiastolic(null);
                    setHpSugar(null);
                  }}
                >
                  再记一条
                </Button>
              </div>
            ) : (
              <Space direction="vertical" style={{ width: '100%' }} size="middle">
                <div>
                  <Text style={{ fontSize: 16, display: 'block', marginBottom: 6 }}>
                    血压 (mmHg)
                  </Text>
                  <Space>
                    <InputNumber
                      placeholder="收缩压"
                      min={60}
                      max={260}
                      value={hpSystolic}
                      onChange={(v) => setHpSystolic(v)}
                      style={{ width: 100 }}
                    />
                    <Text type="secondary">/</Text>
                    <InputNumber
                      placeholder="舒张压"
                      min={40}
                      max={160}
                      value={hpDiastolic}
                      onChange={(v) => setHpDiastolic(v)}
                      style={{ width: 100 }}
                    />
                  </Space>
                </div>
                <div>
                  <Text style={{ fontSize: 16, display: 'block', marginBottom: 6 }}>
                    血糖 (mmol/L)
                  </Text>
                  <InputNumber
                    placeholder="如 5.6"
                    min={1}
                    max={35}
                    step={0.1}
                    value={hpSugar}
                    onChange={(v) => setHpSugar(v)}
                    style={{ width: 120 }}
                  />
                </div>
                <Button
                  type="primary"
                  block
                  loading={hpSaving}
                  onClick={handleSaveHealthLog}
                >
                  记录今日指标
                </Button>
              </Space>
            )}
          </Card>
        </Col>

        {/* Card 3：今日养生 */}
        <Col xs={24} lg={8}>
          <Card
            style={{ height: '100%' }}
            title={
              <span>
                <SunOutlined style={{ marginRight: 8, color: '#faad14' }} />
                今日养生
                {dailyHealth?.solar_term && (
                  <Text type="secondary" style={{ fontSize: 14, marginLeft: 8 }}>
                    {dailyHealth.solar_term} · {dailyHealth.date}
                  </Text>
                )}
              </span>
            }
          >
            {dailyHealth ? (
              <>
                <Paragraph style={{ marginBottom: 8 }}>{dailyHealth.season_advice}</Paragraph>
                {Array.isArray(dailyHealth.health_tips) && dailyHealth.health_tips.length > 0 && (
                  <ul style={{ marginTop: 4, paddingLeft: 20, marginBottom: 0 }}>
                    {dailyHealth.health_tips.slice(0, 3).map((tip, idx) => (
                      <li key={idx}>
                        <Text style={{ fontSize: 14 }}>{tip}</Text>
                      </li>
                    ))}
                  </ul>
                )}
                {dailyHealth.recent_consultations && dailyHealth.recent_consultations.count > 0 && (
                  <Text type="secondary" style={{ display: 'block', marginTop: 8, fontSize: 14 }}>
                    结合近7天 {dailyHealth.recent_consultations.count} 次咨询：
                    {dailyHealth.recent_consultations.topics.slice(0, 2).join('、')}
                  </Text>
                )}
              </>
            ) : (
              <Empty description="暂无养生建议" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Card>
        </Col>
      </Row>

      {/* 知识库统计 — 淡化展示 */}
      <div style={{ marginBottom: 24, textAlign: 'center' }}>
        <Text type="secondary" style={{ fontSize: 14 }}>
          知识库：{stats?.herb_count ?? 0}味中药 · {stats?.formula_count ?? 0}首方剂 ·{' '}
          {stats?.medicine_count ?? 0}项药箱
        </Text>
      </div>

      <Card
        style={{ marginBottom: 24 }}
        title={
          <span>
            <HeartOutlined style={{ marginRight: 8, color: '#1890ff' }} />
            我的体质
          </span>
        }
      >
        {constitution ? (
          <div style={{ textAlign: 'center' }}>
            <ConstitutionRing
              score={
                constitution.primary_type
                  ? constitution.results[constitution.primary_type] ?? 0
                  : 0
              }
              primaryType={constitution.primary_type}
            />
            <Paragraph
              style={{ marginTop: 16, marginBottom: 8, fontSize: 16 }}
              type="secondary"
            >
              {CONSTITUTION_DESCRIPTIONS[constitution.primary_type] ??
                '暂无描述'}
            </Paragraph>
            {constitution.secondary_types.length > 0 && (
              <Space wrap>
                <Text type="secondary">兼夹体质：</Text>
                {constitution.secondary_types.map((t) => (
                  <Text key={t} style={{ fontSize: 16 }}>
                    {t}
                  </Text>
                ))}
              </Space>
            )}
            <div style={{ marginTop: 12 }}>
              <Button
                type="link"
                onClick={() => navigate('/constitution')}
                style={{ fontSize: 16, padding: '4px 0' }}
              >
                重新测评 →
              </Button>
            </div>
          </div>
        ) : (
          <Empty description="您还未进行体质测评" image={Empty.PRESENTED_IMAGE_SIMPLE}>
            <Button
              type="primary"
              icon={<HeartOutlined />}
              size="large"
              onClick={() => navigate('/constitution')}
            >
              去测体质
            </Button>
          </Empty>
        )}
      </Card>

      {!!stats?.adherence_total_7d && stats.adherence_total_7d > 0 && (
        <Card
          style={{ marginBottom: 24 }}
          title={
            <span>
              <CheckCircleOutlined style={{ marginRight: 8, color: '#52c41a' }} />
              用药依从性
            </span>
          }
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 24 }}>
            <Statistic
              title="近7天按时服药率"
              value={stats.adherence_rate ?? 0}
              suffix="%"
              valueStyle={{
                color: (stats.adherence_rate ?? 0) >= 80 ? '#52c41a' : (stats.adherence_rate ?? 0) >= 60 ? '#faad14' : '#ff4d4f',
                fontSize: 36,
              }}
            />
            <div>
              <Text type="secondary" style={{ fontSize: 16 }}>
                {stats.adherence_taken_7d ?? 0} / {stats.adherence_total_7d ?? 0} 次按时服药
              </Text>
              <br />
              <Text type="secondary">
                {(stats.adherence_rate ?? 0) >= 80
                  ? '坚持得很好，继续保持！'
                  : (stats.adherence_rate ?? 0) >= 60
                    ? '还可以，建议设置提醒避免漏服'
                    : '依从性较低，请务必按时服药'}
              </Text>
            </div>
          </div>
        </Card>
      )}

      {(expiryAlerts.expired.length > 0 ||
        expiryAlerts.expiring_soon.length > 0 ||
        expiryAlerts.low_stock.length > 0) && (
        <Card
          style={{ marginBottom: 24 }}
          title={
            <span>
              <WarningOutlined style={{ marginRight: 8, color: '#faad14' }} />
              药箱提醒
            </span>
          }
        >
          <Space direction="vertical" style={{ width: '100%' }} size="small">
            {expiryAlerts.expired.map((m) => (
              <Alert
                key={m.id}
                type="error"
                showIcon
                icon={<ExclamationCircleOutlined />}
                message={`${m.name} 已过期（${m.expiry_date}）`}
              />
            ))}
            {expiryAlerts.expiring_soon.map((m) => (
              <Alert
                key={m.id}
                type="warning"
                showIcon
                message={`${m.name} 即将过期（${m.expiry_date}）`}
              />
            ))}
            {expiryAlerts.low_stock.map((m) => (
              <Alert
                key={m.id}
                type="info"
                showIcon
                message={`${m.name} 库存不足（剩余 ${m.quantity}）`}
              />
            ))}
          </Space>
        </Card>
      )}

      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} lg={12}>
          <Card
            style={{ height: '100%' }}
            title={
              <span>
                <HistoryOutlined style={{ marginRight: 8, color: '#1890ff' }} />
                近期活动
              </span>
            }
          >
            {(() => {
              const activities = buildActivityItems(
                checkInHistory,
                constitution,
                todayReminders,
              );
              if (activities.length === 0) {
                return <Empty description="暂无近期活动" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
              }
              return (
                <Timeline
                  items={activities.map((a) => ({
                    color: a.color,
                    children: (
                      <div>
                        <Text style={{ fontSize: 16 }}>{a.text}</Text>
                        <br />
                        <Text type="secondary" style={{ fontSize: 14 }}>
                          {formatRelativeTime(a.timestamp)}
                        </Text>
                      </div>
                    ),
                  }))}
                />
              );
            })()}
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card
            style={{ height: '100%' }}
            title={
              <span>
                <ThunderboltOutlined style={{ marginRight: 8, color: '#faad14' }} />
                健康速记
              </span>
            }
          >
            {(() => {
              const bmi =
                profile?.height_cm && profile?.weight_kg && profile.height_cm > 0
                  ? Math.round(
                      (profile.weight_kg /
                        Math.pow(profile.height_cm / 100, 2)) *
                        10,
                    ) / 10
                  : null;
              const bmiStatus =
                bmi !== null
                  ? bmi < 18.5
                    ? '偏瘦'
                    : bmi < 24
                      ? '正常'
                      : bmi < 28
                        ? '偏胖'
                        : '肥胖'
                  : null;
              const bmiColor =
                bmi !== null
                  ? bmi < 18.5 || bmi >= 28
                    ? '#ff4d4f'
                    : bmi < 24
                      ? '#52c41a'
                      : '#faad14'
                  : undefined;

              const nextReminder = todayReminders
                .filter((r) => r.status === '待服')
                .sort((a, b) => a.time.localeCompare(b.time))[0];
              const nextName = nextReminder
                ? nextReminder.medicine_name ||
                  nextReminder.herb_name ||
                  nextReminder.formula_name ||
                  nextReminder.title
                : null;

              const daysSince =
                constitution?.assessed_at
                  ? Math.floor(
                      (Date.now() -
                        new Date(constitution.assessed_at).getTime()) /
                        86400000,
                    )
                  : null;

              const hasAny =
                bmi !== null || nextName || daysSince !== null;

              if (!hasAny) {
                return (
                  <Empty
                    description="完善健康档案获取更多健康信息"
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                  >
                    <Button onClick={() => navigate('/profile')}>
                      去完善档案
                    </Button>
                  </Empty>
                );
              }

              return (
                <Space direction="vertical" style={{ width: '100%' }} size="middle">
                  {bmi !== null && bmiStatus && (
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                      }}
                    >
                      <Text style={{ fontSize: 16 }}>体质指数 BMI</Text>
                      <Text style={{ fontSize: 18, fontWeight: 600, color: bmiColor }}>
                        {bmi}（{bmiStatus}）
                      </Text>
                    </div>
                  )}
                  {nextName && (
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                      }}
                    >
                      <Text style={{ fontSize: 16 }}>下一次服药</Text>
                      <Text style={{ fontSize: 16 }}>
                        {nextReminder!.time} {nextName}
                      </Text>
                    </div>
                  )}
                  {daysSince !== null && (
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                      }}
                    >
                      <Text style={{ fontSize: 16 }}>上次体质测评</Text>
                      <Text style={{ fontSize: 16 }}>
                        {daysSince === 0 ? '今天' : `${daysSince} 天前`}
                      </Text>
                    </div>
                  )}
                </Space>
              );
            })()}
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => navigate('/medicines')}
          >
            添加药品
          </Button>
        </Col>
        <Col>
          <Button
            icon={<BellOutlined />}
            onClick={() => navigate('/reminders')}
          >
            吃药提醒
          </Button>
        </Col>
        <Col>
          <Button
            icon={<BookOutlined />}
            onClick={() => navigate('/herbs')}
          >
            浏览中药
          </Button>
        </Col>
        <Col>
          <Button
            icon={<SafetyOutlined />}
            onClick={() => navigate('/safety')}
          >
            安全检查
          </Button>
        </Col>
        <Col>
          <Button
            icon={<CalendarOutlined />}
            onClick={() => navigate('/seasonal')}
          >
            季节养生
          </Button>
        </Col>
        <Col>
          <Button
            icon={<MessageOutlined />}
            onClick={() => navigate('/chat')}
          >
            AI问答
          </Button>
        </Col>
      </Row>

      {stats && stats.medicine_count === 0 && stats.reminder_count === 0 && (
        <Card style={{ marginTop: 24 }}>
          <Empty description="欢迎使用家庭医生！开始您的健康管理之旅">
            <Space direction="vertical" size="small" style={{ alignItems: 'center' }}>
              <Text type="secondary">建议您先完成以下步骤：</Text>
              <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate('/medicines')}>
                1. 添加您的常用药品
              </Button>
              <Button icon={<BellOutlined />} onClick={() => navigate('/reminders')}>
                2. 设置吃药提醒
              </Button>
              <Button icon={<BookOutlined />} onClick={() => navigate('/herbs')}>
                3. 浏览中药知识库
              </Button>
            </Space>
          </Empty>
        </Card>
      )}

      <OnboardingWizard
        open={onboardingOpen}
        onComplete={() => setOnboardingOpen(false)}
      />
    </div>
  );
}
