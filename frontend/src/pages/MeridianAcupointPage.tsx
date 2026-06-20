import { useState, useEffect, useCallback } from 'react';
import {
  Typography, Input, Card, Row, Col, Tag, Drawer, Table, Skeleton,
  Empty, Badge, Space, Descriptions, Button, Radio,
} from 'antd';
import {
  AimOutlined, SearchOutlined, EnvironmentOutlined,
  ThunderboltOutlined, FireOutlined, MedicineBoxOutlined,
} from '@ant-design/icons';
import { useIsMobile } from '../hooks/useIsMobile';
import {
  listMeridians, listAcupoints, getEntity,
  ENTITY_TYPE_TAG_COLOR,
  type KnowledgeEntity, type KnowledgeEntityDetail,
} from '../api/knowledgeHubApi';

const { Title, Text, Paragraph } = Typography;

const MERIDIAN_COLORS: Record<string, string> = {
  正经: '#1890ff',
  奇经: '#fa8c16',
};

export default function MeridianAcupointPage() {
  const isMobile = useIsMobile();
  const [meridians, setMeridians] = useState<KnowledgeEntity[]>([]);
  const [meridianLoading, setMeridianLoading] = useState(true);
  const [viewMode, setViewMode] = useState<'meridian' | 'acupoint'>('meridian');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedMeridian, setSelectedMeridian] = useState<string | undefined>();
  const [acupoints, setAcupoints] = useState<KnowledgeEntity[]>([]);
  const [acupointTotal, setAcupointTotal] = useState(0);
  const [acupointLoading, setAcupointLoading] = useState(false);
  const [detail, setDetail] = useState<KnowledgeEntityDetail | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    listMeridians()
      .then(setMeridians)
      .catch(() => {})
      .finally(() => setMeridianLoading(false));
  }, []);

  const loadAcupoints = useCallback(async (q?: string, meridian?: string) => {
    setAcupointLoading(true);
    try {
      const result = await listAcupoints(q, meridian, 1, 200);
      setAcupoints(result.items);
      setAcupointTotal(result.total);
    } catch {
      setAcupoints([]);
      setAcupointTotal(0);
    } finally {
      setAcupointLoading(false);
    }
  }, []);

  useEffect(() => {
    if (viewMode === 'acupoint' || searchQuery || selectedMeridian) {
      void loadAcupoints(searchQuery, selectedMeridian);
    }
  }, [viewMode, searchQuery, selectedMeridian, loadAcupoints]);

  const openDetail = async (id: string) => {
    setDetailOpen(true);
    setDetail(null);
    setDetailLoading(true);
    try {
      const d = await getEntity(id);
      setDetail(d);
    } catch {
      setDetail(null);
    } finally {
      setDetailLoading(false);
    }
  };

  const renderMeridianCards = () => {
    if (meridianLoading) return <Skeleton active paragraph={{ rows: 6 }} />;
    if (!meridians.length) return <Empty description="暂无经络数据" />;
    return (
      <Row gutter={[16, 16]}>
        {meridians.map((m) => {
          const props = m.properties as Record<string, unknown>;
          const cat = (m.category as string) || '正经';
          const code = (props.code as string) || '';
          const pointCount = (props.point_count as number) || 0;
          const organ = (props.organ as string) || '';
          const indications = (props.common_indications as string) || '';
          return (
            <Col xs={24} sm={12} lg={8} xl={6} key={m.id}>
              <Card
                hoverable
                onClick={() => {
                  setSelectedMeridian(code);
                  setViewMode('acupoint');
                }}
                style={{ borderLeft: `4px solid ${MERIDIAN_COLORS[cat] || '#1890ff'}` }}
              >
                <Space direction="vertical" size={4} style={{ width: '100%' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Text strong style={{ fontSize: 18 }}>{m.title}</Text>
                    <Badge count={code} style={{ backgroundColor: MERIDIAN_COLORS[cat] || '#1890ff' }} />
                  </div>
                  <Space size={8}>
                    <Tag color={cat === '正经' ? 'blue' : 'orange'}>{cat}</Tag>
                    {organ && <Tag>{organ}</Tag>}
                    <Text type="secondary">{pointCount}穴</Text>
                  </Space>
                  {indications && (
                    <Paragraph type="secondary" style={{ margin: 0, fontSize: 13 }} ellipsis={{ rows: 2 }}>
                      {indications}
                    </Paragraph>
                  )}
                </Space>
              </Card>
            </Col>
          );
        })}
      </Row>
    );
  };

  const columns = [
    {
      title: '穴名',
      dataIndex: 'title',
      key: 'title',
      width: 100,
      render: (text: string) => <Text strong style={{ fontSize: 15 }}>{text}</Text>,
    },
    {
      title: '代码',
      key: 'code',
      width: 80,
      render: (_: unknown, record: KnowledgeEntity) => {
        const code = (record.properties as Record<string, unknown>)?.code as string;
        return code ? <Badge count={code} color="#eb2f96" /> : null;
      },
    },
    {
      title: '经络',
      key: 'meridian',
      width: 140,
      render: (_: unknown, record: KnowledgeEntity) => (
        <Tag color="red">{(record.properties as Record<string, unknown>)?.meridian as string || record.category}</Tag>
      ),
    },
    {
      title: '定位',
      key: 'location',
      ellipsis: true,
      render: (_: unknown, record: KnowledgeEntity) => (
        <Text type="secondary" style={{ fontSize: 13 }}>
          {(record.properties as Record<string, unknown>)?.location as string || ''}
        </Text>
      ),
    },
    {
      title: '特定穴',
      key: 'specific',
      width: 120,
      render: (_: unknown, record: KnowledgeEntity) => {
        const sp = (record.properties as Record<string, unknown>)?.specific_point as string;
        if (!sp) return null;
        return sp.split('；').slice(0, 2).map((s, i) => (
          <Tag key={i} color="gold">{s}</Tag>
        ));
      },
    },
    {
      title: '操作',
      key: 'action',
      width: 80,
      fixed: 'right' as const,
      render: (_: unknown, record: KnowledgeEntity) => (
        <Button type="link" size="small" onClick={() => openDetail(record.id)}>
          详情
        </Button>
      ),
    },
  ];

  const renderAcupointTable = () => {
    if (acupointLoading) return <Skeleton active paragraph={{ rows: 8 }} />;
    if (!acupoints.length) return <Empty description="未找到穴位" />;
    return (
      <>
        {selectedMeridian && (
          <div style={{ marginBottom: 12 }}>
            <Space>
              <Text type="secondary">当前经络：</Text>
              <Tag color="red">{selectedMeridian}</Tag>
              <Button type="link" size="small" onClick={() => setSelectedMeridian(undefined)}>
                清除筛选
              </Button>
            </Space>
          </div>
        )}
        <Text type="secondary" style={{ display: 'block', marginBottom: 8 }}>
          共 {acupointTotal} 个穴位
        </Text>
        <Table
          dataSource={acupoints}
          columns={columns}
          rowKey="id"
          size="middle"
          pagination={{ pageSize: 20, showSizeChanger: false }}
          scroll={{ x: 800 }}
          onRow={(record) => ({
            onClick: (e) => {
              const target = e.target as HTMLElement;
              if (target.tagName === 'BUTTON' || target.tagName === 'A') return;
              void openDetail(record.id);
            },
            style: { cursor: 'pointer' },
          })}
        />
      </>
    );
  };

  const renderDetail = () => {
    if (detailLoading) return <Skeleton active paragraph={{ rows: 10 }} />;
    if (!detail) return <Empty description="未找到穴位信息" />;
    const props = detail.properties as Record<string, unknown>;
    const functions = (props.functions as string[]) || [];
    const indications = (props.indications as string[]) || [];
    const groups = detail.groupedRelationships || {};

    return (
      <div>
        <div style={{ marginBottom: 16 }}>
          <Space align="center">
            <Title level={3} style={{ margin: 0 }}>{detail.title}</Title>
            {props.code ? <Badge count={props.code as string} color="#eb2f96" /> : null}
            {props.meridian ? <Tag color="red">{props.meridian as string}</Tag> : null}
          </Space>
        </div>

        {props.specific_point ? (
          <div style={{ marginBottom: 12 }}>
            <Space wrap>
              {(props.specific_point as string).split('；').map((s, i) => (
                <Tag key={i} color="gold">{s}</Tag>
              ))}
            </Space>
          </div>
        ) : null}

        <Descriptions column={1} bordered size="small" style={{ marginBottom: 16 }}>
          <Descriptions.Item label={<span><EnvironmentOutlined /> 定位</span>}>
            {props.location as string}
          </Descriptions.Item>
          <Descriptions.Item label={<span><ThunderboltOutlined /> 刺法</span>}>
            <Text style={{ color: '#fa541c' }}>{props.needling as string}</Text>
          </Descriptions.Item>
          <Descriptions.Item label={<span><FireOutlined /> 灸法</span>}>
            {props.moxibustion as string}
          </Descriptions.Item>
          <Descriptions.Item label={<span><MedicineBoxOutlined /> 配伍</span>}>
            {props.combinations as string}
          </Descriptions.Item>
        </Descriptions>

        {functions.length > 0 && (
          <div style={{ marginBottom: 12 }}>
            <Text strong>功效：</Text>
            <Space wrap style={{ marginTop: 4 }}>
              {functions.map((f, i) => (
                <Tag key={i} color="green">{f}</Tag>
              ))}
            </Space>
          </div>
        )}

        {indications.length > 0 && (
          <div style={{ marginBottom: 12 }}>
            <Text strong>主治：</Text>
            <Space wrap style={{ marginTop: 4 }}>
              {indications.map((ind, i) => (
                <Tag key={i}>{ind}</Tag>
              ))}
            </Space>
          </div>
        )}

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
            <AimOutlined style={{ color: '#eb2f96' }} />
            经络穴位
          </Space>
        </Title>
        <Space wrap>
          <Input
            prefix={<SearchOutlined style={{ color: '#999' }} />}
            placeholder="搜索穴位名或功效…"
            allowClear
            style={{ width: isMobile ? '100%' : 240, fontSize: 15 }}
            size="large"
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              if (e.target.value) setViewMode('acupoint');
            }}
          />
          <Radio.Group
            value={viewMode}
            onChange={(e) => setViewMode(e.target.value)}
            optionType="button"
            buttonStyle="solid"
          >
            <Radio.Button value="meridian">经络</Radio.Button>
            <Radio.Button value="acupoint">穴位</Radio.Button>
          </Radio.Group>
        </Space>
      </div>

      {viewMode === 'meridian' && !searchQuery && !selectedMeridian
        ? renderMeridianCards()
        : renderAcupointTable()}

      <Drawer
        title="穴位详情"
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
