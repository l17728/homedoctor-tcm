import { useState, useEffect, useCallback } from 'react';
import { Card, Row, Col, Tag, Skeleton, Empty, Typography, Button, Tooltip } from 'antd';
import {
  FireOutlined,
  CoffeeOutlined,
  ThunderboltOutlined,
  AimOutlined,
  ExperimentOutlined,
  RightOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import {
  getSeasonalHealth,
  type SeasonalHealth,
} from '../api/seasonalHealthApi';

const { Text, Paragraph } = Typography;

const SEASON_GRADIENT: Record<string, string> = {
  春: 'linear-gradient(135deg, #52c41a 0%, #95de64 100%)',
  夏: 'linear-gradient(135deg, #fa541c 0%, #ffc069 100%)',
  秋: 'linear-gradient(135deg, #fa8c16 0%, #ffd591 100%)',
  冬: 'linear-gradient(135deg, #1890ff 0%, #91d5ff 100%)',
};

const SEASON_ICON: Record<string, string> = {
  春: '🌱',
  夏: '☀️',
  秋: '🍂',
  冬: '❄️',
};

const SEASON_COLOR: Record<string, string> = {
  春: 'green',
  夏: 'volcano',
  秋: 'orange',
  冬: 'blue',
};

const TAB_ICONS: Record<string, React.ReactNode> = {
  饮食建议: <CoffeeOutlined style={{ fontSize: 20 }} />,
  起居建议: <FireOutlined style={{ fontSize: 20 }} />,
  运动建议: <ThunderboltOutlined style={{ fontSize: 20 }} />,
  穴位按摩: <AimOutlined style={{ fontSize: 20 }} />,
};

export default function SeasonalHealthPage() {
  const navigate = useNavigate();
  const [data, setData] = useState<SeasonalHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedTerm, setSelectedTerm] = useState<string | null>(null);

  const fetchData = useCallback(async (term?: string) => {
    setLoading(true);
    try {
      const result = await getSeasonalHealth(term);
      setData(result);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleTermClick = (termName: string) => {
    setSelectedTerm(termName);
    fetchData(termName);
  };

  const handleResetToCurrent = () => {
    setSelectedTerm(null);
    fetchData();
  };

  if (loading) {
    return (
      <div>
        <Skeleton active paragraph={{ rows: 3 }} />
        <div style={{ height: 24 }} />
        <Row gutter={[16, 16]}>
          {[1, 2, 3, 4].map((i) => (
            <Col xs={24} sm={12} md={6} key={i}>
              <Card>
                <Skeleton active paragraph={{ rows: 4 }} />
              </Card>
            </Col>
          ))}
        </Row>
      </div>
    );
  }

  if (!data) {
    return (
      <Empty description="暂无季节养生数据">
        <Button icon={<ReloadOutlined />} onClick={() => fetchData()}>
          重新加载
        </Button>
      </Empty>
    );
  }

  const gradient = SEASON_GRADIENT[data.season] || 'linear-gradient(135deg, #1890ff 0%, #69b1ff 100%)';
  const seasonIcon = SEASON_ICON[data.season] || '🌿';

  const adviceCards = [
    { key: '饮食建议', icon: <CoffeeOutlined />, items: data.diet, color: '#fa8c16' },
    { key: '起居建议', icon: <FireOutlined />, items: data.lifestyle, color: '#1890ff' },
    { key: '运动建议', icon: <ThunderboltOutlined />, items: data.exercise, color: '#52c41a' },
    { key: '穴位按摩', icon: <AimOutlined />, items: data.acupoints, color: '#eb2f96' },
  ];

  return (
    <div>
      {/* Hero Card — Current Solar Term */}
      <Card
        bodyStyle={{ padding: 0 }}
        style={{
          marginBottom: 24,
          overflow: 'hidden',
          border: 'none',
        }}
      >
        <div
          style={{
            background: gradient,
            padding: '32px 28px',
            color: '#fff',
          }}
        >
          <Row align="middle" justify="space-between" gutter={[16, 16]}>
            <Col xs={24} sm={16}>
              <div style={{ fontSize: 48, marginBottom: 8 }}>
                {seasonIcon}
              </div>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
                <span style={{ fontSize: 36, fontWeight: 700 }}>
                  {data.current_term}
                </span>
                <Tag
                  color={SEASON_COLOR[data.season]}
                  style={{ fontSize: 16, padding: '2px 12px', border: 'none', color: '#fff', background: 'rgba(255,255,255,0.25)' }}
                >
                  {data.season}季
                </Tag>
              </div>
              {data.principle && (
                <Paragraph
                  style={{
                    color: 'rgba(255,255,255,0.9)',
                    fontSize: 16,
                    marginTop: 12,
                    marginBottom: 0,
                  }}
                >
                  {data.principle}
                </Paragraph>
              )}
              {data.next_term && (
                <div style={{ marginTop: 12, fontSize: 14, color: 'rgba(255,255,255,0.8)' }}>
                  距{data.next_term}还有 <Text strong style={{ color: '#fff', fontSize: 18 }}>{data.days_to_next_term}</Text> 天
                </div>
              )}
            </Col>
            <Col xs={24} sm={8} style={{ textAlign: 'center' }}>
              {selectedTerm && (
                <Button
                  ghost
                  icon={<ReloadOutlined />}
                  onClick={handleResetToCurrent}
                  style={{ borderColor: 'rgba(255,255,255,0.5)' }}
                >
                  回到当前节气
                </Button>
              )}
            </Col>
          </Row>
        </div>
      </Card>

      {/* 24 Solar Terms Timeline */}
      <Card title="二十四节气" style={{ marginBottom: 24 }}>
        <div
          style={{
            display: 'flex',
            gap: 8,
            overflowX: 'auto',
            paddingBottom: 8,
          }}
        >
          {data.all_terms.map((term) => {
            const isCurrent = term.name === data.current_term;
            const isSelected = term.name === selectedTerm;
            return (
              <Tooltip key={term.name} title={`${term.month}月`}>
                <div
                  onClick={() => handleTermClick(term.name)}
                  style={{
                    minWidth: 72,
                    textAlign: 'center',
                    padding: '12px 8px',
                    borderRadius: 8,
                    cursor: 'pointer',
                    border: `2px solid ${
                      isCurrent
                        ? '#1890ff'
                        : isSelected
                        ? '#52c41a'
                        : '#f0f0f0'
                    }`,
                    background: isCurrent
                      ? '#e6f7ff'
                      : isSelected
                      ? '#f6ffed'
                      : '#fafafa',
                    transition: 'all 0.2s',
                    flexShrink: 0,
                  }}
                >
                  <div style={{ fontSize: 16, fontWeight: 600, color: isCurrent ? '#1890ff' : '#333' }}>
                    {term.name}
                  </div>
                  <Tag
                    color={SEASON_COLOR[term.season]}
                    style={{ marginTop: 4, fontSize: 14, border: 'none' }}
                  >
                    {term.season}
                  </Tag>
                  {isCurrent && (
                    <div style={{ fontSize: 14, color: '#1890ff', marginTop: 2 }}>当前</div>
                  )}
                </div>
              </Tooltip>
            );
          })}
        </div>
      </Card>

      {/* Four Advice Categories */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        {adviceCards.map((card) => {
          const isEmpty =
            !card.items ||
            card.items.length === 0 ||
            (card.items.length === 1 && !card.items[0]);

          return (
            <Col xs={24} sm={12} md={6} key={card.key}>
              <Card
                size="small"
                title={
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ color: card.color }}>{TAB_ICONS[card.key]}</span>
                    <span>{card.key}</span>
                  </div>
                }
                style={{ height: '100%' }}
              >
                {isEmpty ? (
                  <Text type="secondary">暂无建议</Text>
                ) : card.key === '穴位按摩' ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                    {(card.items as any[]).map((pt, idx) => (
                      <div key={idx}>
                        <div style={{ fontWeight: 600, fontSize: 15 }}>
                          <Tag color="magenta" style={{ marginRight: 4 }}>{pt.name}</Tag>
                        </div>
                        <div style={{ fontSize: 14, color: '#666', marginTop: 2 }}>
                          📍 {pt.location}
                        </div>
                        <div style={{ fontSize: 14, color: '#666', marginTop: 2 }}>
                          功效：{pt.effect}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <ul style={{ paddingLeft: 20, marginBottom: 0 }}>
                    {(card.items as string[]).map((item, idx) => (
                      <li key={idx} style={{ marginBottom: 6, fontSize: 14, lineHeight: 1.6 }}>
                        {item}
                      </li>
                    ))}
                  </ul>
                )}
              </Card>
            </Col>
          );
        })}
      </Row>

      {/* Seasonal Herbs + Recommended Formulas */}
      <Row gutter={[16, 16]}>
        <Col xs={24} md={14}>
          <Card
            title={
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <ExperimentOutlined style={{ color: '#52c41a' }} />
                <span>当季推荐药材</span>
              </div>
            }
          >
            {data.herbs.length === 0 ? (
              <Empty description="暂无推荐" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
              <Row gutter={[12, 12]}>
                {data.herbs.map((herb, idx) => (
                  <Col xs={24} sm={12} key={idx}>
                    <Card
                      size="small"
                      hoverable
                      onClick={() => navigate(`/herbs?search=${encodeURIComponent(herb.name)}`)}
                      style={{ borderLeft: `3px solid ${SEASON_COLOR[data.season] || '#1890ff'}` }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div>
                          <Text strong style={{ fontSize: 16 }}>{herb.name}</Text>
                          <div style={{ fontSize: 14, color: '#666', marginTop: 4 }}>
                            {herb.reason}
                          </div>
                        </div>
                        <RightOutlined style={{ color: '#666' }} />
                      </div>
                    </Card>
                  </Col>
                ))}
              </Row>
            )}
          </Card>
        </Col>

        <Col xs={24} md={10}>
          <Card
            title={
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <CoffeeOutlined style={{ color: '#fa8c16' }} />
                <span>推荐方剂</span>
              </div>
            }
          >
            {data.formulas.length === 0 ? (
              <Empty description="暂无推荐" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {data.formulas.map((formulaName, idx) => (
                  <Button
                    key={idx}
                    block
                    type="text"
                    style={{
                      textAlign: 'left',
                      height: 'auto',
                      padding: '8px 12px',
                      borderRadius: 8,
                      background: '#fafafa',
                    }}
                    onClick={() => navigate(`/formulas?search=${encodeURIComponent(formulaName)}`)}
                  >
                    <span style={{ fontSize: 15 }}>{formulaName}</span>
                    <RightOutlined style={{ float: 'right', marginTop: 4, color: '#666' }} />
                  </Button>
                ))}
              </div>
            )}
          </Card>
        </Col>
      </Row>
    </div>
  );
}
