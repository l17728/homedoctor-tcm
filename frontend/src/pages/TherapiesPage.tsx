import { useState, useEffect, useCallback } from 'react';
import {
  Card,
  Row,
  Col,
  Input,
  Tabs,
  Drawer,
  Tag,
  Typography,
  Skeleton,
  Empty,
  Space,
  Descriptions,
  Alert,
  Divider,
} from 'antd';
import {
  SearchOutlined,
  WarningOutlined,
  SafetyCertificateOutlined,
  ExperimentOutlined,
} from '@ant-design/icons';
import {
  getTherapies,
  searchTherapies,
  getTherapy,
  THERAPY_CATEGORIES,
  type Therapy,
  type TherapyDetail,
} from '../api/therapyApi';

const { Title, Paragraph, Text } = Typography;

/** 疗法分类主题色 — 温润中医色系 */
const CATEGORY_COLOR: Record<string, string> = {
  刮痧: 'volcano',
  推拿: 'blue',
  艾灸: 'orange',
  拔罐: 'purple',
  针刺: 'red',
  刺血: 'magenta',
};

/** 风险等级色 */
const RISK_COLOR: Record<string, string> = {
  low: 'green',
  medium: 'gold',
  high: 'red',
};

const RISK_LABEL: Record<string, string> = {
  low: '低风险',
  medium: '中风险',
  high: '高风险',
};

export default function TherapiesPage() {
  const [therapies, setTherapies] = useState<Therapy[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeCategory, setActiveCategory] = useState<string>('all');
  const [searchValue, setSearchValue] = useState('');
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [selected, setSelected] = useState<TherapyDetail | null>(null);

  const loadData = useCallback(
    async (category: string, search: string) => {
      setLoading(true);
      try {
        if (search.trim()) {
          const result = await searchTherapies({
            q: search.trim(),
            category: category !== 'all' ? category : undefined,
          });
          setTherapies(result);
        } else {
          const data = await getTherapies({
            page: 1,
            pageSize: 100,
            category: category !== 'all' ? category : undefined,
          });
          setTherapies(data.items);
        }
      } catch {
        setTherapies([]);
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  useEffect(() => {
    loadData('all', '');
  }, [loadData]);

  const handleTabChange = (key: string) => {
    setActiveCategory(key);
    loadData(key, searchValue);
  };

  const handleSearch = (value: string) => {
    setSearchValue(value);
    loadData(activeCategory, value);
  };

  const openDetail = async (therapy: Therapy) => {
    setDrawerOpen(true);
    setDetailLoading(true);
    setSelected(null);
    try {
      const detail = await getTherapy(therapy.id);
      setSelected(detail);
    } catch {
      // fallback — show the list-level data we already have
      setSelected({ ...therapy, acupoints: [], safetyRules: [] });
    } finally {
      setDetailLoading(false);
    }
  };

  const tabItems = [
    { key: 'all', label: '全部疗法' },
    ...THERAPY_CATEGORIES.map((c) => ({ key: c, label: c })),
  ];

  return (
    <div>
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
            <ExperimentOutlined style={{ color: '#8B5A2B' }} />
            外治理疗
          </Space>
        </Title>
        <Input
          prefix={<SearchOutlined style={{ color: '#666' }} />}
          placeholder="搜索疗法名称、适应症"
          allowClear
          style={{ width: 300, fontSize: 16 }}
          size="large"
          value={searchValue}
          onChange={(e) => {
            setSearchValue(e.target.value);
            if (!e.target.value) loadData(activeCategory, '');
          }}
          onPressEnter={(e) => handleSearch(e.currentTarget.value)}
        />
      </div>

      {/* 分类筛选 Tabs */}
      <Tabs
        activeKey={activeCategory}
        onChange={handleTabChange}
        items={tabItems}
        style={{ marginBottom: 8 }}
        size="large"
      />

      {/* 内容区 */}
      {loading ? (
        <Skeleton active paragraph={{ rows: 6 }} />
      ) : therapies.length === 0 ? (
        <Empty description="暂无疗法数据" style={{ marginTop: 60 }} />
      ) : (
        <Row gutter={[16, 16]}>
          {therapies.map((t) => {
            const riskColor = RISK_COLOR[t.riskLevel] ?? 'default';
            const catColor = CATEGORY_COLOR[t.category] ?? 'default';
            return (
              <Col xs={24} sm={12} lg={8} xl={6} key={t.id}>
                <Card
                  hoverable
                  onClick={() => openDetail(t)}
                  styles={{
                    body: { padding: 20, minHeight: 200 },
                  }}
                  style={{
                    borderRadius: 12,
                    border: `1px solid ${
                      t.displayOnly ? '#ffd591' : '#f0e6d9'
                    }`,
                    transition: 'all 0.25s ease',
                  }}
                >
                  <Space
                    direction="vertical"
                    size={12}
                    style={{ width: '100%' }}
                  >
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'flex-start',
                        gap: 8,
                      }}
                    >
                      <Text
                        strong
                        style={{ fontSize: 18, color: '#5b3a1a' }}
                      >
                        {t.name}
                      </Text>
                      <Tag color={catColor} style={{ margin: 0 }}>
                        {t.category}
                      </Tag>
                    </div>

                    <Paragraph
                      type="secondary"
                      ellipsis={{ rows: 2 }}
                      style={{ fontSize: 15, marginBottom: 0, minHeight: 44 }}
                    >
                      {t.description || '暂无描述'}
                    </Paragraph>

                    <div>
                      <Text
                        type="secondary"
                        style={{ fontSize: 14 }}
                      >
                        适应症
                      </Text>
                      <div style={{ marginTop: 4 }}>
                        <Text style={{ fontSize: 14 }}>
                          {t.indications || '—'}
                        </Text>
                      </div>
                    </div>

                    <Divider style={{ margin: '4px 0' }} />
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                      }}
                    >
                      <Tag
                        color={riskColor}
                        icon={
                          t.riskLevel === 'high' ? (
                            <WarningOutlined />
                          ) : (
                            <SafetyCertificateOutlined />
                          )
                        }
                      >
                        {RISK_LABEL[t.riskLevel] ?? t.riskLevel}
                      </Tag>
                      {t.displayOnly && (
                        <Text type="warning" style={{ fontSize: 14 }}>
                          仅供了解
                        </Text>
                      )}
                    </div>
                  </Space>
                </Card>
              </Col>
            );
          })}
        </Row>
      )}

      {/* 详情抽屉 */}
      <Drawer
        title={
          selected ? (
            <Space>
              <span>{selected.name}</span>
              <Tag color={CATEGORY_COLOR[selected.category] ?? 'default'}>
                {selected.category}
              </Tag>
            </Space>
          ) : (
            '疗法详情'
          )
        }
        width={560}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        destroyOnClose
      >
        {detailLoading ? (
          <Skeleton active paragraph={{ rows: 10 }} />
        ) : selected ? (
          <div>
            {selected.displayOnly && (
              <Alert
                type="warning"
                showIcon
                icon={<WarningOutlined />}
                message="本疗法仅供了解，须由执业中医师操作，禁止自行施治。"
                style={{ marginBottom: 16 }}
              />
            )}

            <Descriptions column={1} bordered size="small">
              <Descriptions.Item label="风险等级">
                <Tag color={RISK_COLOR[selected.riskLevel] ?? 'default'}>
                  {RISK_LABEL[selected.riskLevel] ?? selected.riskLevel}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="家庭自用">
                {selected.homeUseSafe ? (
                  <Tag color="green">适合</Tag>
                ) : (
                  <Tag color="red">不适合</Tag>
                )}
              </Descriptions.Item>
              <Descriptions.Item label="适应症">
                {selected.indications || '—'}
              </Descriptions.Item>
              <Descriptions.Item label="禁忌">
                <Text type="danger">
                  {selected.contraindications || '—'}
                </Text>
              </Descriptions.Item>
            </Descriptions>

            <Divider orientation="left" plain>
              <Text strong>操作步骤</Text>
            </Divider>
            <pre
              style={{
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                fontSize: 15,
                lineHeight: 1.8,
                background: '#faf6f0',
                padding: 16,
                borderRadius: 8,
                margin: 0,
                fontFamily: 'inherit',
              }}
            >
              {selected.operationSteps || '暂无操作步骤说明'}
            </pre>

            <Row gutter={16} style={{ marginTop: 16 }}>
              <Col span={12}>
                <Card size="small" title="单次时长" styles={{ body: { padding: 12 } }}>
                  <Text style={{ fontSize: 16 }}>
                    {selected.duration || '—'}
                  </Text>
                </Card>
              </Col>
              <Col span={12}>
                <Card size="small" title="建议频率" styles={{ body: { padding: 12 } }}>
                  <Text style={{ fontSize: 16 }}>
                    {selected.frequency || '—'}
                  </Text>
                </Card>
              </Col>
            </Row>

            {selected.precautions && (
              <>
                <Divider orientation="left" plain>
                  <Text strong>注意事项</Text>
                </Divider>
                <Alert
                  type="info"
                  showIcon
                  message={selected.precautions}
                  style={{ fontSize: 15 }}
                />
              </>
            )}

            {selected.acupoints.length > 0 && (
              <>
                <Divider orientation="left" plain>
                  <Text strong>相关穴位</Text>
                </Divider>
                <Space wrap>
                  {selected.acupoints.map((ap, i) => (
                    <Tag
                      key={`${ap.acupoint_name}-${i}`}
                      color={ap.is_primary ? 'gold' : 'default'}
                    >
                      {ap.acupoint_name}
                      {ap.meridian ? `（${ap.meridian}）` : ''}
                    </Tag>
                  ))}
                </Space>
              </>
            )}

            {selected.safetyRules.length > 0 && (
              <>
                <Divider orientation="left" plain>
                  <Text strong>安全规则</Text>
                </Divider>
                {selected.safetyRules.map((rule, i) => (
                  <Alert
                    key={i}
                    type={
                      rule.severity === 'critical' || rule.severity === 'high'
                        ? 'error'
                        : 'warning'
                    }
                    showIcon
                    message={rule.condition_text}
                    description={rule.action}
                    style={{ marginBottom: 8, fontSize: 14 }}
                  />
                ))}
              </>
            )}

            <Divider />
            <Paragraph type="secondary" style={{ fontSize: 14 }}>
              以上信息仅供参考，具体操作请咨询执业中医师。
            </Paragraph>
          </div>
        ) : (
          <Empty description="加载失败" />
        )}
      </Drawer>
    </div>
  );
}
