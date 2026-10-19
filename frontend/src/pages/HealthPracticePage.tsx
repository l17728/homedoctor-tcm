import { useState, useEffect, useCallback } from 'react';
import {
  Typography, Input, Card, Row, Col, Tag, Drawer, Skeleton,
  Empty, Space, Radio, Descriptions, Alert,
} from 'antd';
import {
  ThunderboltOutlined, HeartOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import { useIsMobile } from '../hooks/useIsMobile';
import { request } from '../api/client';
import {
  ENTITY_TYPE_TAG_COLOR,
  type KnowledgeEntity,
  type KnowledgeEntityDetail,
} from '../api/knowledgeHubApi';

const { Title, Text, Paragraph } = Typography;

const PRACTICE_TYPE_COLORS: Record<string, string> = {
  动功: '#52c41a',
  静功: '#1890ff',
  动静结合: '#722ed1',
};

export default function HealthPracticePage() {
  const isMobile = useIsMobile();
  const [practices, setPractices] = useState<KnowledgeEntity[]>([]);
  const [schools, setSchools] = useState<KnowledgeEntity[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [viewMode, setViewMode] = useState<'practice' | 'school'>('practice');
  const [filterType, setFilterType] = useState<string>('all');
  const [detail, setDetail] = useState<KnowledgeEntityDetail | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);

  const loadPractices = useCallback(async () => {
    setLoading(true);
    try {
      const data = await request<{ items: KnowledgeEntity[]; total: number }>(
        `/api/knowledge/search?q=${encodeURIComponent(searchQuery)}&type=health_practice`
      );
      let items = data.items || [];
      if (filterType !== 'all') {
        items = items.filter((it) => {
          const pt = (it.properties as Record<string, unknown>)?.practice_type as string;
          return pt === filterType;
        });
      }
      setPractices(items);
    } catch {
      setPractices([]);
    } finally {
      setLoading(false);
    }
  }, [searchQuery, filterType]);

  const loadSchools = useCallback(async () => {
    try {
      const data = await request<{ items: KnowledgeEntity[] }>(
        '/api/knowledge/search?q=&type=practice_school'
      );
      setSchools(data.items || []);
    } catch {
      setSchools([]);
    }
  }, []);

  useEffect(() => {
    void loadPractices();
    void loadSchools();
  }, [loadPractices, loadSchools]);

  const openDetail = async (id: string) => {
    setDetailOpen(true);
    setDetail(null);
    setDetailLoading(true);
    try {
      const d = await request<KnowledgeEntityDetail & { relationships?: Record<string, unknown>[] }>(
        `/api/knowledge/herbs/${encodeURIComponent(id)}`
      );
      setDetail(d);
    } catch {
      try {
        const d2 = await request<KnowledgeEntityDetail>(
          `/api/knowledge-hub/entities/${encodeURIComponent(id)}`
        );
        setDetail(d2);
      } catch {
        setDetail(null);
      }
    } finally {
      setDetailLoading(false);
    }
  };

  const renderPracticeCard = (p: KnowledgeEntity) => {
    const props = (p.properties || {}) as Record<string, unknown>;
    const pType = props.practice_type as string;
    const difficulty = props.difficulty as string;
    const duration = props.duration_minutes as string;
    const color = PRACTICE_TYPE_COLORS[pType] || '#1890ff';
    return (
      <Col xs={24} sm={12} lg={8} xl={6} key={p.id}>
        <Card
          hoverable
          onClick={() => openDetail(p.id)}
          style={{ borderLeft: `4px solid ${color}` }}
        >
          <Space direction="vertical" size={4} style={{ width: '100%' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Text strong style={{ fontSize: 17 }}>{p.title}</Text>
              {difficulty && <Tag color={difficulty === '入门' ? 'green' : difficulty === '进阶' ? 'orange' : 'red'}>{difficulty}</Tag>}
            </div>
            {pType && <Tag color={color === '#52c41a' ? 'green' : color === '#1890ff' ? 'blue' : 'purple'}>{pType}</Tag>}
            <Paragraph type="secondary" style={{ margin: 0, fontSize: 14 }} ellipsis={{ rows: 2 }}>
              {(props.core_essence as string) || p.summary || ''}
            </Paragraph>
            {duration && <Text type="secondary" style={{ fontSize: 14 }}>⏱ {duration}</Text>}
          </Space>
        </Card>
      </Col>
    );
  };

  const renderSchoolCard = (s: KnowledgeEntity) => {
    const props = (s.properties || {}) as Record<string, unknown>;
    return (
      <Col xs={24} sm={12} lg={8} xl={6} key={s.id}>
        <Card hoverable onClick={() => openDetail(s.id)} style={{ borderLeft: '4px solid #fa541c' }}>
          <Space direction="vertical" size={4} style={{ width: '100%' }}>
            <Text strong style={{ fontSize: 17 }}>{s.title}</Text>
            {props.founder ? <Text type="secondary" style={{ fontSize: 14 }}>创始人：{props.founder as string}</Text> : null}
            <Paragraph type="secondary" style={{ margin: 0, fontSize: 14 }} ellipsis={{ rows: 2 }}>
              {(props.characteristics as string) || s.summary || ''}
            </Paragraph>
          </Space>
        </Card>
      </Col>
    );
  };

  const renderDetail = () => {
    if (detailLoading) return <Skeleton active paragraph={{ rows: 10 }} />;
    if (!detail) return <Empty description="未找到功法信息" />;
    const props = (detail.properties || {}) as Record<string, unknown>;
    const steps = (props.steps as Array<Record<string, string>>) || [];
    const keyPoints = (props.key_points as string[]) || [];
    const indications = (props.indications as string[]) || [];
    const groups = detail.groupedRelationships || {};

    return (
      <div>
        <div style={{ marginBottom: 16 }}>
          <Space align="center" wrap>
            <Title level={3} style={{ margin: 0 }}>{detail.title}</Title>
            {props.practice_type ? <Tag color="purple">{props.practice_type as string}</Tag> : null}
            {props.difficulty ? <Tag color="orange">{props.difficulty as string}</Tag> : null}
          </Space>
        </div>

        {props.core_essence ? (
          <Alert
            type="info"
            showIcon
            icon={<ThunderboltOutlined />}
            message="功法精要"
            description={props.core_essence as string}
            style={{ marginBottom: 16 }}
          />
        ) : null}

        <Descriptions column={1} bordered size="small" style={{ marginBottom: 16 }}>
          {props.origin ? (
            <Descriptions.Item label="起源">{props.origin as string}</Descriptions.Item>
          ) : null}
          {props.founder ? (
            <Descriptions.Item label="代表人物">{props.founder as string}</Descriptions.Item>
          ) : null}
          {props.duration_minutes ? (
            <Descriptions.Item label="练习时长">{props.duration_minutes as string}</Descriptions.Item>
          ) : null}
          {props.best_time ? (
            <Descriptions.Item label="最佳时间">{props.best_time as string}</Descriptions.Item>
          ) : null}
        </Descriptions>

        {props.mental_focus ? (
          <div style={{ marginBottom: 16, padding: 12, background: '#f6ffed', borderRadius: 8 }}>
            <Text strong style={{ color: '#52c41a' }}>🧘 心法要诀</Text>
            <Paragraph style={{ marginTop: 8, marginBottom: 0 }}>{props.mental_focus as string}</Paragraph>
          </div>
        ) : null}

        {props.breathing ? (
          <div style={{ marginBottom: 16, padding: 12, background: '#e6f7ff', borderRadius: 8 }}>
            <Text strong style={{ color: '#1890ff' }}>🫁 呼吸要点</Text>
            <Paragraph style={{ marginTop: 8, marginBottom: 0 }}>{props.breathing as string}</Paragraph>
          </div>
        ) : null}

        {keyPoints.length > 0 ? (
          <div style={{ marginBottom: 16 }}>
            <Text strong>关键要点：</Text>
            <Space wrap style={{ marginTop: 8 }}>
              {keyPoints.map((kp, i) => (
                <Tag key={i} color="gold">{kp}</Tag>
              ))}
            </Space>
          </div>
        ) : null}

        {steps.length > 0 ? (
          <div style={{ marginBottom: 16 }}>
            <Text strong>练习步骤：</Text>
            {steps.map((step, i) => (
              <Card key={i} size="small" style={{ marginTop: 8 }}>
                <Text strong>步骤{i + 1}：{step.name || step.step_name || ''}</Text>
                {step.points ? <Paragraph style={{ marginTop: 4, marginBottom: 0 }}>{step.points}</Paragraph> : null}
                {step.detail ? <Paragraph style={{ marginTop: 4, marginBottom: 0 }}>{step.detail}</Paragraph> : null}
              </Card>
            ))}
          </div>
        ) : null}

        {indications.length > 0 ? (
          <div style={{ marginBottom: 16 }}>
            <Text strong>养生功效：</Text>
            <Space wrap style={{ marginTop: 8 }}>
              {indications.map((ind, i) => (
                <Tag key={i} color="green">{ind}</Tag>
              ))}
            </Space>
          </div>
        ) : null}

        {props.cautions ? (
          <Alert
            type="warning"
            message="注意事项"
            description={props.cautions as string}
            style={{ marginBottom: 16 }}
          />
        ) : null}

        {Object.keys(groups).length > 0 && (
          <div>
            <Text strong>关联知识：</Text>
            {Object.entries(groups).map(([type, items]) => (
              items.length > 0 && (
                <div key={type} style={{ marginTop: 8 }}>
                  <Text type="secondary">{type}：</Text>
                  <Space wrap>
                    {items.map((item) => (
                      <Tag key={item.id} color={ENTITY_TYPE_TAG_COLOR[item.type] || 'default'}>
                        {item.label}
                      </Tag>
                    ))}
                  </Space>
                </div>
              )
            ))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16, flexWrap: 'wrap', gap: 12 }}>
        <Title level={3} style={{ margin: 0 }}>
          <Space>
            <HeartOutlined style={{ color: '#52c41a' }} />
            养生功法
          </Space>
        </Title>
        <Space wrap>
          <Input
            prefix={<SearchOutlined style={{ color: '#666' }} />}
            placeholder="搜索功法…"
            allowClear
            style={{ width: isMobile ? '100%' : 220, fontSize: 15 }}
            size="large"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          <Radio.Group
            value={viewMode}
            onChange={(e) => setViewMode(e.target.value)}
            optionType="button"
            buttonStyle="solid"
          >
            <Radio.Button value="practice">功法</Radio.Button>
            <Radio.Button value="school">门派</Radio.Button>
          </Radio.Group>
        </Space>
      </div>

      {viewMode === 'practice' && (
        <div style={{ marginBottom: 16 }}>
          <Radio.Group
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
            size="small"
            optionType="button"
          >
            <Radio.Button value="all">全部</Radio.Button>
            <Radio.Button value="动功">动功</Radio.Button>
            <Radio.Button value="静功">静功</Radio.Button>
            <Radio.Button value="动静结合">动静结合</Radio.Button>
          </Radio.Group>
        </div>
      )}

      {loading ? (
        <Skeleton active paragraph={{ rows: 8 }} />
      ) : viewMode === 'practice' ? (
        practices.length > 0 ? (
          <Row gutter={[16, 16]}>
            {practices.map(renderPracticeCard)}
          </Row>
        ) : (
          <Empty description="未找到功法" />
        )
      ) : (
        <Row gutter={[16, 16]}>
          {schools.map(renderSchoolCard)}
        </Row>
      )}

      <Drawer
        title="功法详情"
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        width={isMobile ? '100%' : 560}
        destroyOnClose
      >
        {renderDetail()}
      </Drawer>
    </div>
  );
}
