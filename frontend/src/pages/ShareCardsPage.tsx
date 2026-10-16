import { useState, useEffect, useCallback } from 'react';
import {
  Card,
  Row,
  Col,
  Button,
  Tag,
  Typography,
  Skeleton,
  Empty,
  Space,
  Statistic,
  Descriptions,
  Table,
  Segmented,
  Select,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  ShareAltOutlined,
  PictureOutlined,
  HeartOutlined,
  CalendarOutlined,
  BellOutlined,
  FilePdfOutlined,
  ReloadOutlined,
  TeamOutlined,
  BarChartOutlined,
  CloudOutlined,
} from '@ant-design/icons';
import {
  generateShareCard,
  listShareCards,
  getMonthlyFamilyReport,
  downloadShareCardPdf,
  type ShareCard,
  type ShareCardType,
  type MonthlyFamilyMetric,
} from '../api/shareCardApi';
import { getFamilyMembers, type FamilyMember } from '../api/familyMemberApi';

const { Title, Text, Paragraph } = Typography;

const CARD_TYPE_OPTIONS: { label: string; value: ShareCardType; icon: React.ReactNode }[] = [
  { label: '健康概览', value: '健康概览', icon: <HeartOutlined /> },
  { label: '节气养生', value: '节气养生', icon: <CloudOutlined /> },
  { label: '体质报告', value: '体质报告', icon: <BarChartOutlined /> },
];

const CARD_GRADIENT: Record<ShareCardType, string> = {
  健康概览: 'linear-gradient(135deg, #1890ff 0%, #36cfc9 100%)',
  节气养生: 'linear-gradient(135deg, #52c41a 0%, #95de64 100%)',
  体质报告: 'linear-gradient(135deg, #722ed1 0%, #b37feb 100%)',
};

const CARD_EMOJI: Record<ShareCardType, string> = {
  健康概览: '💚',
  节气养生: '🌿',
  体质报告: '📊',
};

const CONSTITUTION_COLOR: Record<string, string> = {
  平和质: 'green',
  气虚质: 'orange',
  阳虚质: 'red',
  阴虚质: 'cyan',
  痰湿质: 'purple',
  湿热质: 'magenta',
  血瘀质: 'volcano',
  气郁质: 'blue',
  特禀质: 'lime',
};

function adherenceColor(rate: number | null): string {
  if (rate === null) return '#666';
  if (rate >= 80) return '#52c41a';
  if (rate >= 60) return '#faad14';
  return '#ff4d4f';
}

// ===========================================================================
// Share Card Visual
// ===========================================================================

function ShareCardVisual({ card }: { card: ShareCard }) {
  const gradient = CARD_GRADIENT[card.card_type] ?? CARD_GRADIENT['健康概览'];
  const emoji = CARD_EMOJI[card.card_type] ?? '💚';
  const adherence = card.adherence;

  return (
    <Card
      bodyStyle={{ padding: 0 }}
      style={{ overflow: 'hidden', border: 'none', maxWidth: 480, margin: '0 auto' }}
    >
      {/* 渐变标题头 */}
      <div style={{ background: gradient, padding: '24px 20px', color: '#fff' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div>
            <div style={{ fontSize: 28, marginBottom: 4 }}>{emoji}</div>
            <div style={{ fontSize: 22, fontWeight: 700 }}>{card.card_type}</div>
            <div style={{ fontSize: 14, opacity: 0.85, marginTop: 4 }}>
              <CalendarOutlined style={{ marginRight: 4 }} />
              {card.date || '—'}
            </div>
          </div>
          <Tag style={{ background: 'rgba(255,255,255,0.25)', border: 'none', color: '#fff', fontSize: 14 }}>
            家庭医生
          </Tag>
        </div>
      </div>

      {/* 内容区 */}
      <div style={{ padding: '20px' }}>
        <Descriptions column={1} size="small" labelStyle={{ width: 90, color: '#666' }}>
          <Descriptions.Item label="家人">
            <Text strong style={{ fontSize: 16 }}>{card.member_name}</Text>
          </Descriptions.Item>
          {card.constitution && (
            <Descriptions.Item label="体质">
              <Tag color={CONSTITUTION_COLOR[card.constitution] ?? 'blue'}>{card.constitution}</Tag>
            </Descriptions.Item>
          )}
        </Descriptions>

        <Row gutter={12} style={{ marginTop: 12 }}>
          {adherence !== null && (
            <Col span={8}>
              <Statistic
                title="依从率"
                value={adherence}
                suffix="%"
                valueStyle={{ color: adherenceColor(adherence), fontSize: 22 }}
              />
            </Col>
          )}
          {card.today_reminders !== null && (
            <Col span={8}>
              <Statistic
                title="今日提醒"
                value={card.today_reminders}
                prefix={<BellOutlined style={{ color: '#1890ff' }} />}
                valueStyle={{ fontSize: 22 }}
              />
            </Col>
          )}
          <Col span={8}>
            <Statistic
              title="状态"
              value={adherence !== null && adherence >= 80 ? '良好' : '关注'}
              valueStyle={{ fontSize: 16, color: adherenceColor(adherence) }}
            />
          </Col>
        </Row>

        {card.seasonal_advice && (
          <div
            style={{
              marginTop: 16,
              padding: 12,
              background: '#f6ffed',
              borderRadius: 8,
              borderLeft: '3px solid #52c41a',
            }}
          >
            <Text strong style={{ color: '#52c41a' }}>
              <CloudOutlined style={{ marginRight: 4 }} />养生建议
            </Text>
            <Paragraph style={{ marginBottom: 0, marginTop: 4, fontSize: 14 }}>
              {card.seasonal_advice}
            </Paragraph>
          </div>
        )}

        {card.motivational_quote && (
          <div style={{ marginTop: 12, textAlign: 'center' }}>
            <Text italic type="secondary" style={{ fontSize: 14 }}>
              「{card.motivational_quote}」
            </Text>
          </div>
        )}
      </div>
    </Card>
  );
}

// ===========================================================================
// Monthly Family Report Table
// ===========================================================================

const MONTHLY_COLUMNS: ColumnsType<MonthlyFamilyMetric> = [
  {
    title: '家人',
    dataIndex: 'member_name',
    key: 'member_name',
    render: (name: string) => <Text strong>{name}</Text>,
  },
  {
    title: '体质',
    dataIndex: 'constitution',
    key: 'constitution',
    render: (v: string | null) =>
      v ? <Tag color={CONSTITUTION_COLOR[v] ?? 'blue'}>{v}</Tag> : <Text type="secondary">—</Text>,
  },
  {
    title: '依从率',
    dataIndex: 'adherence_rate',
    key: 'adherence_rate',
    align: 'center' as const,
    render: (v: number | null) =>
      v !== null ? (
        <span style={{ color: adherenceColor(v), fontWeight: 600 }}>{v}%</span>
      ) : (
        <Text type="secondary">—</Text>
      ),
  },
  {
    title: '提醒数',
    dataIndex: 'reminder_count',
    key: 'reminder_count',
    align: 'center' as const,
  },
  {
    title: '药品数',
    dataIndex: 'medicine_count',
    key: 'medicine_count',
    align: 'center' as const,
  },
  {
    title: '漏服',
    dataIndex: 'missed_count',
    key: 'missed_count',
    align: 'center' as const,
    render: (v: number) => (
      <span style={{ color: v > 0 ? '#ff4d4f' : undefined, fontWeight: v > 0 ? 600 : undefined }}>
        {v}
      </span>
    ),
  },
];

// ===========================================================================
// Main Page
// ===========================================================================

export default function ShareCardsPage() {
  const [cardType, setCardType] = useState<ShareCardType>('健康概览');
  const [members, setMembers] = useState<FamilyMember[]>([]);
  const [selectedMemberId, setSelectedMemberId] = useState<string | undefined>(undefined);
  const [generating, setGenerating] = useState(false);
  const [currentCard, setCurrentCard] = useState<ShareCard | null>(null);
  const [pdfLoading, setPdfLoading] = useState(false);

  const [cardList, setCardList] = useState<ShareCard[]>([]);
  const [loadingList, setLoadingList] = useState(false);
  const [monthlyMetrics, setMonthlyMetrics] = useState<MonthlyFamilyMetric[]>([]);
  const [loadingMonthly, setLoadingMonthly] = useState(false);

  // Load family members for selector
  useEffect(() => {
    let mounted = true;
    getFamilyMembers()
      .then((list) => {
        if (!mounted) return;
        setMembers(list);
        if (list.length > 0 && list[0]) setSelectedMemberId(list[0].id);
      })
      .catch(() => {
        // no members yet
      });
    return () => {
      mounted = false;
    };
  }, []);

  const fetchCardList = useCallback(async () => {
    setLoadingList(true);
    try {
      const items = await listShareCards();
      setCardList(items);
    } catch {
      // backend may not be ready — leave empty
    } finally {
      setLoadingList(false);
    }
  }, []);

  const fetchMonthly = useCallback(async () => {
    setLoadingMonthly(true);
    try {
      const report = await getMonthlyFamilyReport();
      setMonthlyMetrics(report.items);
    } catch {
      // backend may not be ready
    } finally {
      setLoadingMonthly(false);
    }
  }, []);

  useEffect(() => {
    fetchCardList();
    fetchMonthly();
  }, [fetchCardList, fetchMonthly]);

  const handleGenerate = async () => {
    if (!selectedMemberId) {
      message.warning('请先选择家庭成员');
      return;
    }
    setGenerating(true);
    try {
      const card = await generateShareCard({
        card_type: cardType,
        member_id: selectedMemberId,
      });
      setCurrentCard(card);
      message.success('分享卡已生成');
      fetchCardList();
    } catch (err) {
      const msg = err instanceof Error ? err.message : '生成失败';
      message.error(msg);
    } finally {
      setGenerating(false);
    }
  };

  const handleDownloadPdf = async () => {
    if (!currentCard) return;
    setPdfLoading(true);
    try {
      await downloadShareCardPdf(currentCard.id);
      message.success('PDF 已开始下载');
    } catch (err) {
      const msg = err instanceof Error ? err.message : '下载失败';
      message.error(msg);
    } finally {
      setPdfLoading(false);
    }
  };

  const memberOptions = members.map((m) => ({
    label: m.name ? `${m.name}${m.relation ? `（${m.relation}）` : ''}` : '未命名',
    value: m.id,
  }));

  return (
    <div>
      <Row justify="space-between" align="middle" style={{ marginBottom: 16 }} gutter={[16, 16]}>
        <Col>
          <Title level={3} style={{ marginBottom: 0 }}>
            <ShareAltOutlined style={{ marginRight: 8, color: '#1890ff' }} />
            分享卡
          </Title>
        </Col>
        <Col>
          <Space wrap>
            <Segmented
              options={CARD_TYPE_OPTIONS.map((o) => ({ label: o.label, value: o.value }))}
              value={cardType}
              onChange={(v) => setCardType(v as ShareCardType)}
            />
          </Space>
        </Col>
      </Row>

      {/* 生成器区域 */}
      <Card style={{ marginBottom: 16 }}>
        <Row gutter={[16, 16]} align="middle">
          <Col xs={24} sm={10} md={8}>
            <Text strong style={{ display: 'block', marginBottom: 8 }}>
              <TeamOutlined style={{ marginRight: 4 }} />选择家庭成员
            </Text>
            <Select
              value={selectedMemberId}
              onChange={setSelectedMemberId}
              options={memberOptions}
              placeholder="选择家人"
              style={{ width: '100%' }}
              notFoundContent="暂无家庭成员"
            />
          </Col>
          <Col xs={24} sm={14} md={16}>
            <Space wrap>
              <Button
                type="primary"
                size="large"
                icon={<PictureOutlined />}
                loading={generating}
                onClick={handleGenerate}
              >
                生成分享卡
              </Button>
              {currentCard && (
                <Button
                  size="large"
                  icon={<FilePdfOutlined />}
                  loading={pdfLoading}
                  onClick={handleDownloadPdf}
                >
                  下载 PDF
                </Button>
              )}
            </Space>
          </Col>
        </Row>
      </Card>

      {/* 卡片展示 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} md={12}>
          <Card
            title={
              <Space>
                <PictureOutlined style={{ color: '#1890ff' }} />
                <span>分享卡预览</span>
              </Space>
            }
            extra={
              currentCard && (
                <Button
                  type="text"
                  icon={<ReloadOutlined />}
                  onClick={handleGenerate}
                  loading={generating}
                >
                  重新生成
                </Button>
              )
            }
          >
            {currentCard ? (
              <ShareCardVisual card={currentCard} />
            ) : (
              <Empty description="选择家人后点击「生成分享卡」" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Card>
        </Col>

        {/* 历史卡片列表 */}
        <Col xs={24} md={12}>
          <Card
            title={
              <Space>
                <HeartOutlined style={{ color: '#eb2f96' }} />
                <span>历史分享卡</span>
                {cardList.length > 0 && <Tag color="pink">{cardList.length}</Tag>}
              </Space>
            }
            extra={
              <Button type="text" icon={<ReloadOutlined />} onClick={fetchCardList} loading={loadingList}>
                刷新
              </Button>
            }
          >
            {loadingList ? (
              <Skeleton active paragraph={{ rows: 4 }} />
            ) : cardList.length === 0 ? (
              <Empty description="暂无历史卡片" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
              <Space direction="vertical" style={{ width: '100%' }} size="small">
                {cardList.slice(0, 8).map((card) => (
                  <Card
                    key={card.id}
                    size="small"
                    hoverable
                    onClick={() => setCurrentCard(card)}
                    style={{
                      borderLeft: `4px solid ${CARD_GRADIENT[card.card_type].includes('1890ff') ? '#1890ff' : CARD_GRADIENT[card.card_type].includes('52c41a') ? '#52c41a' : '#722ed1'}`,
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Space>
                        <span style={{ fontSize: 20 }}>{CARD_EMOJI[card.card_type]}</span>
                        <div>
                          <Text strong>{card.member_name}</Text>
                          <div style={{ fontSize: 14, color: '#666' }}>
                            {card.card_type} · {card.date || card.created_at.slice(0, 10)}
                          </div>
                        </div>
                      </Space>
                      {card.adherence !== null && (
                        <Tag color={adherenceColor(card.adherence) === '#52c41a' ? 'green' : adherenceColor(card.adherence) === '#faad14' ? 'orange' : 'red'}>
                          {card.adherence}%
                        </Tag>
                      )}
                    </div>
                  </Card>
                ))}
              </Space>
            )}
          </Card>
        </Col>
      </Row>

      {/* 月度家庭报告 */}
      <Card
        title={
          <Space>
            <BarChartOutlined style={{ color: '#722ed1' }} />
            <span>月度家庭报告</span>
          </Space>
        }
        extra={
          <Button type="text" icon={<ReloadOutlined />} onClick={fetchMonthly} loading={loadingMonthly}>
            刷新
          </Button>
        }
      >
        {loadingMonthly ? (
          <Skeleton active paragraph={{ rows: 4 }} />
        ) : monthlyMetrics.length === 0 ? (
          <Empty description="暂无月度数据，请先添加家庭成员并使用一段时间" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <Table<MonthlyFamilyMetric>
            columns={MONTHLY_COLUMNS}
            dataSource={monthlyMetrics}
            rowKey="member_id"
            pagination={false}
            size="middle"
          />
        )}
      </Card>
    </div>
  );
}
