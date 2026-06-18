import { useState, useCallback } from 'react';
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
                <div style={{ fontSize: 13, color: '#888' }}>{p.assessed_at.slice(0, 10)}</div>
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
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
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
              <Text type="secondary" style={{ fontSize: 12 }}>
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
            <Text type="secondary" style={{ fontSize: 12 }}>
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
            <Text type="secondary" style={{ fontSize: 12 }}>
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
          <div style={{ fontSize: 9, color: '#999', marginTop: 2 }}>
            {d.date.slice(5)}
          </div>
        </div>
      ))}
    </div>
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
                <Paragraph style={{ fontSize: 13, marginBottom: 0, marginTop: 4 }}>
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
