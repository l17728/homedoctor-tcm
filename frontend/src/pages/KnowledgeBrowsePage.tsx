import { useState, useEffect, useCallback } from 'react';
import {
  Typography, Input, Card, Row, Col, Tag, Drawer, Skeleton, Empty,
  Space, Select, Button, Modal, message, Tooltip, Spin, Alert,
} from 'antd';
import {
  SearchOutlined, PlusOutlined, AppstoreOutlined,
  CheckCircleOutlined, ClockCircleOutlined,
} from '@ant-design/icons';
import { useIsMobile } from '../hooks/useIsMobile';
import {
  getCategories, browseKnowledge, getEntity, appendKnowledge, getAppendHistory,
  ENTITY_TYPE_LABEL, ENTITY_TYPE_TAG_COLOR,
  type KnowledgeEntity, type KnowledgeEntityDetail,
} from '../api/knowledgeHubApi';

const { Title, Text, Paragraph } = Typography;

const TRUST_COLORS: Record<string, string> = {
  S: '#52c41a', A: '#1890ff', B: '#faad14', C: '#fa8c16',
};

const TRUST_LABELS: Record<string, string> = {
  S: '系统权威', A: '权威来源', B: '用户导入', C: '网络搜索',
};

export default function KnowledgeBrowsePage() {
  const isMobile = useIsMobile();
  const [types, setTypes] = useState<Array<{ type: string; label: string; count: number }>>([]);
  const [categories, setCategories] = useState<Record<string, Array<{ category: string; count: number }>>>({});
  const [activeType, setActiveType] = useState('herb');
  const [activeCategory, setActiveCategory] = useState<string | undefined>();
  const [searchQuery, setSearchQuery] = useState('');
  const [items, setItems] = useState<KnowledgeEntity[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);

  const [detail, setDetail] = useState<KnowledgeEntityDetail | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);

  const [appendOpen, setAppendOpen] = useState(false);
  const [appendInstruction, setAppendInstruction] = useState('');
  const [appendLoading, setAppendLoading] = useState(false);
  const [appendResult, setAppendResult] = useState<Record<string, unknown> | null>(null);
  const [appendHistory, setAppendHistory] = useState<Array<Record<string, unknown>>>([]);

  useEffect(() => {
    getCategories().then((data) => {
      setTypes(data.types ?? []);
      setCategories(data.categories ?? {});
    }).catch(() => {});
  }, []);

  const loadItems = useCallback(async () => {
    setLoading(true);
    try {
      const result = await browseKnowledge(activeType, activeCategory, searchQuery || undefined, page, 20);
      setItems(result.items);
      setTotal(result.total);
    } catch {
      setItems([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [activeType, activeCategory, searchQuery, page]);

  useEffect(() => { void loadItems(); }, [loadItems]);

  const openDetail = async (id: string) => {
    setDetailOpen(true);
    setDetail(null);
    setDetailLoading(true);
    try {
      const d = await getEntity(id);
      setDetail(d);
      try {
        const hist = await getAppendHistory(id);
        setAppendHistory(hist.items ?? []);
      } catch { setAppendHistory([]); }
    } catch { setDetail(null); }
    finally { setDetailLoading(false); }
  };

  const handleAppend = async () => {
    if (!detail || !appendInstruction.trim()) return;
    setAppendLoading(true);
    setAppendResult(null);
    try {
      const result = await appendKnowledge(detail.id, appendInstruction.trim());
      setAppendResult(result);
      message.success((result as Record<string, string>).message ?? '追加请求已处理');
    } catch (e) {
      message.error('追加失败，请稍后重试');
    } finally {
      setAppendLoading(false);
    }
  };

  const renderTypeTabs = () => (
    <div style={{ marginBottom: 16, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
      {types.map((t) => (
        <Button
          key={t.type}
          type={activeType === t.type ? 'primary' : 'default'}
          onClick={() => { setActiveType(t.type); setActiveCategory(undefined); setPage(1); }}
          size="middle"
        >
          {t.label} ({t.count})
        </Button>
      ))}
    </div>
  );

  const renderCategoryFilter = () => {
    const cats = categories[activeType] ?? [];
    if (cats.length === 0) return null;
    return (
      <div style={{ marginBottom: 16 }}>
        <Select
          value={activeCategory ?? '__all__'}
          onChange={(v) => { setActiveCategory(v === '__all__' ? undefined : v); setPage(1); }}
          style={{ width: 200 }}
          size="middle"
          options={[
            { value: '__all__', label: '全部分类' },
            ...cats.map((c) => ({ value: c.category, label: `${c.category} (${c.count})` })),
          ]}
        />
      </div>
    );
  };

  const renderEntityCard = (e: KnowledgeEntity & { trustLevel?: string; trustScore?: number }) => {
    const trustLevel = e.trustLevel ?? 'S';
    const trustScore = e.trustScore ?? 0;
    return (
      <Col xs={24} sm={12} lg={8} xl={6} key={e.id}>
        <Card hoverable onClick={() => openDetail(e.id)} style={{ borderLeft: `3px solid ${TRUST_COLORS[trustLevel] ?? '#1890ff'}` }}>
          <Space direction="vertical" size={4} style={{ width: '100%' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Text strong style={{ fontSize: 16 }}>{e.title}</Text>
              <Tooltip title={`${TRUST_LABELS[trustLevel] ?? trustLevel} · 评分${trustScore}`}>
                <Tag color={TRUST_COLORS[trustLevel]?.replace('#', '') as string} style={{ margin: 0 }}>
                  {trustLevel}
                </Tag>
              </Tooltip>
            </div>
            {e.category && <Tag>{e.category}</Tag>}
            <Paragraph type="secondary" style={{ margin: 0, fontSize: 13 }} ellipsis={{ rows: 2 }}>
              {e.summary || '暂无摘要'}
            </Paragraph>
          </Space>
        </Card>
      </Col>
    );
  };

  const renderDetail = () => {
    if (detailLoading) return <Skeleton active paragraph={{ rows: 10 }} />;
    if (!detail) return <Empty description="未找到" />;
    const props = (detail.properties ?? {}) as Record<string, unknown>;
    const groups = detail.groupedRelationships ?? {};

    return (
      <div>
        <div style={{ marginBottom: 16 }}>
          <Space align="center" wrap>
            <Title level={3} style={{ margin: 0 }}>{detail.title}</Title>
            <Tag color={ENTITY_TYPE_TAG_COLOR[detail.type] ?? 'default'}>
              {ENTITY_TYPE_LABEL[detail.type] ?? detail.type}
            </Tag>
            {detail.category && <Tag>{detail.category}</Tag>}
          </Space>
        </div>

        {detail.summary && (
          <Paragraph style={{ marginBottom: 16 }}>{detail.summary}</Paragraph>
        )}

        {Object.keys(props).length > 0 && (
          <div style={{ marginBottom: 16 }}>
            <Text strong>属性详情：</Text>
            <div style={{ marginTop: 8 }}>
              {Object.entries(props).slice(0, 15).map(([k, v]) => (
                <div key={k} style={{ marginBottom: 4 }}>
                  <Text type="secondary" style={{ fontSize: 13 }}>{k}：</Text>
                  <Text style={{ fontSize: 13 }}>
                    {Array.isArray(v) ? v.join('、') : typeof v === 'object' ? JSON.stringify(v).slice(0, 100) : String(v).slice(0, 200)}
                  </Text>
                </div>
              ))}
            </div>
          </div>
        )}

        {Object.keys(groups).length > 0 && (
          <div style={{ marginBottom: 16 }}>
            <Text strong>关联知识：</Text>
            {Object.entries(groups).map(([type, items]) => items.length > 0 && (
              <div key={type} style={{ marginTop: 8 }}>
                <Text type="secondary">{type}：</Text>
                <Space wrap>
                  {items.map((item) => (
                    <Tag key={item.id} color={ENTITY_TYPE_TAG_COLOR[item.type] ?? 'default'}>{item.label}</Tag>
                  ))}
                </Space>
              </div>
            ))}
          </div>
        )}

        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => { setAppendOpen(true); setAppendResult(null); setAppendInstruction(''); }}
          size="large"
          style={{ marginTop: 8 }}
        >
          追加内容
        </Button>

        {appendHistory.length > 0 && (
          <div style={{ marginTop: 16 }}>
            <Text strong>追加历史（{appendHistory.length}次）：</Text>
            {appendHistory.slice(0, 5).map((h, i) => {
              const details = h.details as Record<string, unknown> ?? {};
              const decision = h.decision as string ?? '';
              return (
                <div key={i} style={{ marginTop: 4, padding: 8, background: '#fafafa', borderRadius: 4 }}>
                  <Space>
                    {decision === 'adopted' ? <CheckCircleOutlined style={{ color: '#52c41a' }} /> : <ClockCircleOutlined style={{ color: '#faad14' }} />}
                    <Text style={{ fontSize: 13 }}>{(details.instruction as string) ?? (details.request_id as string) ?? '追加请求'}</Text>
                    <Tag>{decision}</Tag>
                  </Space>
                </div>
              );
            })}
          </div>
        )}
      </div>
    );
  };

  const renderAppendModal = () => (
    <Modal
      title={`追加内容 — ${detail?.title ?? ''}`}
      open={appendOpen}
      onCancel={() => setAppendOpen(false)}
      footer={appendResult ? [
        <Button key="close" onClick={() => setAppendOpen(false)}>关闭</Button>,
        <Button key="again" type="primary" onClick={() => { setAppendResult(null); setAppendInstruction(''); }}>
          再次追加
        </Button>,
      ] : [
        <Button key="cancel" onClick={() => setAppendOpen(false)}>取消</Button>,
        <Button key="submit" type="primary" loading={appendLoading} onClick={handleAppend} disabled={!appendInstruction.trim()}>
          提交追加请求
        </Button>,
      ]}
      width={600}
    >
      {!appendResult ? (
        <Space direction="vertical" style={{ width: '100%' }} size={12}>
          <Text type="secondary">
            Agent将自动从内部知识库、外部索引和互联网搜索相关信息，合成补充内容，并经过多AI专家团评审后入库。
          </Text>
          <Input.TextArea
            value={appendInstruction}
            onChange={(e) => setAppendInstruction(e.target.value)}
            placeholder="描述你想追加的内容，例如：&#10;• 添加真气运行法的具体练习步骤&#10;• 补充该功法的适应人群和禁忌&#10;• 增加呼吸方法的详细说明"
            rows={4}
            style={{ fontSize: 14 }}
          />
          <Alert type="info" message="支持多次提交：你可以反复追加不同方面的内容，每次都经过专家评审。" banner />
        </Space>
      ) : (
        <Space direction="vertical" style={{ width: '100%' }} size={12}>
          <Alert
            type={(appendResult as Record<string, string>).decision === 'adopted' ? 'success' : 'warning'}
            message={(appendResult as Record<string, string>).message ?? '处理完成'}
            showIcon
          />
          {appendLoading && <Spin tip="Agent正在收集信息并合成内容..." />}
          {(appendResult as Record<string, unknown>).synthesized_preview ? (
            <div>
              <Text strong>合成内容预览：</Text>
              <Paragraph style={{ marginTop: 8, fontSize: 13, background: '#f6f8fa', padding: 12, borderRadius: 8 }}>
                {(appendResult as Record<string, string>).synthesized_preview as string}
              </Paragraph>
            </div>
          ) : null}
          {(appendResult as Record<string, unknown>).sources_gathered ? (
            <div>
              <Text type="secondary" style={{ fontSize: 13 }}>
                信息来源：内部{(appendResult as Record<string, Record<string, number>>).sources_gathered?.internal ?? 0}条 ·
                外部{(appendResult as Record<string, Record<string, number>>).sources_gathered?.external ?? 0}条 ·
                网络{(appendResult as Record<string, Record<string, number>>).sources_gathered?.web ?? 0}条
              </Text>
            </div>
          ) : null}
          {(appendResult as Record<string, unknown>).new_fields ? (
            <div>
              <Text type="secondary" style={{ fontSize: 13 }}>
                新增字段：{((appendResult as Record<string, string[]>).new_fields ?? []).join('、')}
              </Text>
            </div>
          ) : null}
        </Space>
      )}
    </Modal>
  );

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16, flexWrap: 'wrap', gap: 12 }}>
        <Title level={3} style={{ margin: 0 }}>
          <Space>
            <AppstoreOutlined style={{ color: '#1677ff' }} />
            知识库浏览
          </Space>
        </Title>
        <Input
          prefix={<SearchOutlined style={{ color: '#999' }} />}
          placeholder="搜索知识..."
          allowClear
          style={{ width: isMobile ? '100%' : 240 }}
          size="large"
          value={searchQuery}
          onChange={(e) => { setSearchQuery(e.target.value); setPage(1); }}
        />
      </div>

      {renderTypeTabs()}
      {renderCategoryFilter()}

      <Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
        共 {total} 条 · {ENTITY_TYPE_LABEL[activeType] ?? activeType}
        {activeCategory ? ` · ${activeCategory}` : ''}
      </Text>

      {loading ? (
        <Skeleton active paragraph={{ rows: 8 }} />
      ) : items.length > 0 ? (
        <Row gutter={[16, 16]}>
          {items.map(renderEntityCard)}
        </Row>
      ) : (
        <Empty description="未找到知识" />
      )}

      {total > 20 && (
        <div style={{ textAlign: 'center', marginTop: 24 }}>
          <Button size="large" disabled={page * 20 >= total} onClick={() => setPage(page + 1)}>
            加载更多
          </Button>
        </div>
      )}

      <Drawer
        title="知识详情"
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        width={isMobile ? '100%' : 560}
        destroyOnClose
      >
        {renderDetail()}
      </Drawer>

      {renderAppendModal()}
    </div>
  );
}
