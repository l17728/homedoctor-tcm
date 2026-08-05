import { useState, useEffect, useCallback } from 'react';
import {
  Typography, Card, Table, Tag, Button, Space, Statistic, Row, Col,
  Tabs, Modal, Input, message, Empty, Spin, Descriptions, Select,
} from 'antd';
import {
  DatabaseOutlined, ReloadOutlined, DeleteOutlined,
  PlusOutlined, ScanOutlined, ThunderboltOutlined,
} from '@ant-design/icons';
import { request } from '../api/client';

const { Title, Text, Paragraph } = Typography;

interface ModelRow {
  id: string; name: string; provider: string; model_id: string;
  api_endpoint: string; api_key: string; enabled: boolean; is_default: boolean;
  capabilities: string[]; max_tokens: number; temperature: number;
}

interface LogRow {
  id: string; action_type: string; source_type: string; entity_id: string;
  details: Record<string, unknown>; decision: string; created_at: string;
  user_reviewed: boolean;
}

interface RecRow {
  chunk_id: string; entity_id: string; entity_title: string;
  text_preview: string; source_url: string; age_days: number;
  hit_count: number; trust_level: string; priority: number; reasons: string[];
}

export default function AdminPage() {
  const [tab, setTab] = useState('overview');
  return (
    <div>
      <Title level={3} style={{ marginBottom: 16 }}>
        <Space><DatabaseOutlined /> 系统管理</Space>
      </Title>
      <Tabs activeKey={tab} onChange={setTab} items={[
        { key: 'overview', label: '概览', children: <OverviewTab /> },
        { key: 'kscan', label: '知识巡检', children: <KnowledgeScanTab /> },
        { key: 'models', label: 'AI模型管理', children: <ModelsTab /> },
        { key: 'indexes', label: '索引管理', children: <IndexTab /> },
        { key: 'logs', label: 'Agent日志', children: <LogsTab /> },
        { key: 'feeder', label: '巡检Agent', children: <FeederTab /> },
        { key: 'memories', label: 'Agent记忆', children: <MemoriesTab /> },
        { key: 'conversations', label: 'Agent对话', children: <ConversationsTab /> },
      ]} />
    </div>
  );
}

function OverviewTab() {
  const [stats, setStats] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await request<Record<string, number>>('/api/admin/index-stats');
      setStats(data);
    } catch { setStats({}); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  if (loading) return <Spin />;
  return (
    <Row gutter={16}>
      <Col span={6}><Card><Statistic title="知识分块" value={stats.total_chunks ?? 0} /></Card></Col>
      <Col span={6}><Card><Statistic title="外部索引" value={stats.external_chunks ?? 0} valueStyle={{ color: '#fa8c16' }} /></Card></Col>
      <Col span={6}><Card><Statistic title="语义向量" value={stats.total_embeddings ?? 0} valueStyle={{ color: '#52c41a' }} /></Card></Col>
      <Col span={6}><Card><Statistic title="零命中" value={stats.zero_hit_external ?? 0} valueStyle={{ color: '#ff4d4f' }} /></Card></Col>
      <Col span={6} style={{ marginTop: 16 }}><Card><Statistic title="失效URL" value={stats.stale_urls ?? 0} /></Card></Col>
      <Col span={6} style={{ marginTop: 16 }}><Card><Statistic title="豁免数" value={stats.exemptions ?? 0} /></Card></Col>
      <Col span={6} style={{ marginTop: 16 }}><Card><Statistic title="平均命中" value={stats.avg_hit_rate ?? 0} precision={2} /></Card></Col>
    </Row>
  );
}

function ModelsTab() {
  const [models, setModels] = useState<ModelRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [addOpen, setAddOpen] = useState(false);
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await request<{ items: ModelRow[] }>('/api/models');
      setModels(data.items ?? []);
    } catch { setModels([]); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  return (
    <div>
      <Button type="primary" icon={<PlusOutlined />} onClick={() => setAddOpen(true)} style={{ marginBottom: 16 }}>
        添加模型
      </Button>
      <Table
        loading={loading}
        dataSource={models}
        rowKey="id"
        size="small"
        pagination={false}
        columns={[
          { title: '名称', dataIndex: 'name', key: 'name', width: 120 },
          { title: '提供商', dataIndex: 'provider', key: 'provider', width: 100 },
          { title: '模型ID', dataIndex: 'model_id', key: 'model_id', width: 150 },
          { title: '能力', key: 'capabilities', render: (_, r) => (r.capabilities || []).map((c) => <Tag key={c}>{c}</Tag>) },
          { title: '默认', key: 'default', width: 60, render: (_, r) => r.is_default ? <Tag color="green">默认</Tag> : '' },
          { title: '状态', key: 'enabled', width: 60, render: (_, r) => r.enabled ? <Tag color="green">启用</Tag> : <Tag>禁用</Tag> },
          {
            title: '操作', key: 'action', width: 120,
            render: (_, r) => (
              <Space>
                <Button size="small" type="link" onClick={async () => {
                  await request(`/api/models/${r.id}`, { method: 'PUT', body: JSON.stringify({ enabled: !r.enabled }) });
                  void message.success(r.enabled ? '已禁用' : '已启用');
                  void load();
                }}>{r.enabled ? '禁用' : '启用'}</Button>
                <Button size="small" type="link" danger onClick={async () => {
                  await request(`/api/models/${r.id}`, { method: 'DELETE' });
                  void message.success('已删除');
                  void load();
                }}>删除</Button>
              </Space>
            ),
          },
        ]}
      />
      <AddModelModal open={addOpen} onClose={() => { setAddOpen(false); void load(); }} />
    </div>
  );
}

function AddModelModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [form, setForm] = useState({ name: '', provider: '', model_id: '', api_endpoint: '', api_key: '', capabilities: 'text' });
  const [saving, setSaving] = useState(false);
  return (
    <Modal title="添加AI模型" open={open} onCancel={onClose} confirmLoading={saving}
      onOk={async () => {
        if (!form.name || !form.model_id) { void message.error('名称和模型ID必填'); return; }
        setSaving(true);
        try {
          await request('/api/models', { method: 'POST', body: JSON.stringify({
            ...form, capabilities: form.capabilities.split(',').map((s) => s.trim()),
          }) });
          void message.success('添加成功');
          onClose();
        } catch { void message.error('添加失败'); }
        finally { setSaving(false); }
      }}>
      <Space direction="vertical" style={{ width: '100%' }} size={8}>
        <Input placeholder="模型名称 (如 Kimi-K2.6)" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        <Input placeholder="提供商 (如 huawei_cloud)" value={form.provider} onChange={(e) => setForm({ ...form, provider: e.target.value })} />
        <Input placeholder="模型ID (如 Kimi-K2.6)" value={form.model_id} onChange={(e) => setForm({ ...form, model_id: e.target.value })} />
        <Input placeholder="API端点" value={form.api_endpoint} onChange={(e) => setForm({ ...form, api_endpoint: e.target.value })} />
        <Input.Password placeholder="API密钥" value={form.api_key} onChange={(e) => setForm({ ...form, api_key: e.target.value })} />
        <Input placeholder="能力 (逗号分隔: text,vision)" value={form.capabilities} onChange={(e) => setForm({ ...form, capabilities: e.target.value })} />
      </Space>
    </Modal>
  );
}

function IndexTab() {
  const [recs, setRecs] = useState<RecRow[]>([]);
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await request<{ recommendations: RecRow[] }>('/api/admin/deletion-recommendations');
      setRecs(data.recommendations ?? []);
    } catch { setRecs([]); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
        <Text type="secondary">系统只推荐删除，不自动执行。管理员确认后才删除。</Text>
      </Space>
      <Table loading={loading} dataSource={recs} rowKey="chunk_id" size="small"
        pagination={{ pageSize: 10 }}
        columns={[
          { title: '优先级', dataIndex: 'priority', key: 'priority', width: 70, render: (v) => <Tag color={v > 50 ? 'red' : v > 30 ? 'orange' : 'default'}>{v}</Tag> },
          { title: '预览', dataIndex: 'text_preview', key: 'text_preview', ellipsis: true },
          { title: '信任', dataIndex: 'trust_level', key: 'trust_level', width: 60 },
          { title: '命中', dataIndex: 'hit_count', key: 'hit_count', width: 50 },
          { title: '天数', dataIndex: 'age_days', key: 'age_days', width: 60 },
          { title: '原因', key: 'reasons', render: (_, r) => r.reasons?.map((rs, i) => <Tag key={i}>{rs}</Tag>) },
          {
            title: '操作', key: 'action', width: 160,
            render: (_, r) => (
              <Space>
                <Button size="small" danger icon={<DeleteOutlined />} onClick={async () => {
                  await request('/api/admin/deletion-execute', { method: 'POST', body: JSON.stringify({ chunk_ids: [r.chunk_id] }) });
                  void message.success('已删除');
                  void load();
                }}>删除</Button>
                <Button size="small" onClick={async () => {
                  await request('/api/admin/deletion-exempt', { method: 'POST', body: JSON.stringify({ target_type: 'chunk', target_id: r.chunk_id }) });
                  void message.success('已豁免');
                  void load();
                }}>豁免</Button>
              </Space>
            ),
          },
        ]}
      />
      {recs.length === 0 && !loading ? <Empty description="暂无删除推荐" /> : null}
    </div>
  );
}

function LogsTab() {
  const [logs, setLogs] = useState<LogRow[]>([]);
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await request<{ items: LogRow[] }>('/api/agent/logs?page_size=50');
      setLogs(data.items ?? []);
    } catch { setLogs([]); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const decisionColor: Record<string, string> = { created: 'green', merged: 'blue', rejected: 'red', adopted: 'green', 'pending_review': 'orange', indexed: 'cyan' };

  return (
    <div>
      <Button icon={<ReloadOutlined />} onClick={load} style={{ marginBottom: 16 }}>刷新</Button>
      <Table loading={loading} dataSource={logs} rowKey="id" size="small"
        pagination={{ pageSize: 20 }}
        columns={[
          { title: '时间', dataIndex: 'created_at', key: 'created_at', width: 160, render: (v) => v?.substring(0, 19) },
          { title: '操作', dataIndex: 'action_type', key: 'action_type', width: 120 },
          { title: '来源', dataIndex: 'source_type', key: 'source_type', width: 80 },
          { title: '决策', dataIndex: 'decision', key: 'decision', width: 100, render: (v) => v ? <Tag color={decisionColor[v] || 'default'}>{v}</Tag> : '' },
          {
            title: '详情', key: 'details', ellipsis: true,
            render: (_, r) => {
              const d = r.details || {};
              const parts: string[] = [];
              if (d.title) parts.push(String(d.title));
              if (d.score !== undefined) parts.push(`评分:${d.score}`);
              if (d.chunks !== undefined) parts.push(`${d.chunks}块`);
              if (d.hits !== undefined) parts.push(`${d.hits}命中`);
              return parts.join(' | ') || JSON.stringify(d).slice(0, 80);
            },
          },
        ]}
      />
    </div>
  );
}

function FeederTab() {
  const [scanning, setScanning] = useState(false);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  return (
    <div style={{ maxWidth: 600 }}>
      <Card title="巡检Agent — 知识Feeder">
        <Paragraph type="secondary">
          巡检Agent定期扫描知识库缺口，自动搜索中医内容，将URL投喂给自生长管道。
          系统自动处理：提取→评审→入库→索引→关联。仅限中医/中国传统文化内容。
        </Paragraph>
        <Button type="primary" icon={<ScanOutlined />} loading={scanning} onClick={async () => {
          setScanning(true); setResult(null);
          try {
            const data = await request<Record<string, unknown>>('/api/admin/feeder/scan?max_feeds=5');
            setResult(data);
            void message.success(String(data.message ?? '巡检完成'));
          } catch { void message.error('巡检失败'); }
          finally { setScanning(false); }
        }}>立即巡检</Button>
        {result ? (
          <Descriptions column={1} bordered size="small" style={{ marginTop: 16 }}>
            <Descriptions.Item label="发现缺口">{String(result.gaps_found ?? 0)}</Descriptions.Item>
            <Descriptions.Item label="投喂链接">{String(result.feeds_sent ?? 0)}</Descriptions.Item>
            <Descriptions.Item label="采纳数量">{String(result.adopted ?? 0)}</Descriptions.Item>
            <Descriptions.Item label="结果">{String(result.message ?? '')}</Descriptions.Item>
          </Descriptions>
        ) : null}
      </Card>
    </div>
  );
}

function MemoriesTab() {
  const [items, setItems] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(true);
  const [agentFilter, setAgentFilter] = useState<string | undefined>(undefined);
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (agentFilter) params.set('agent_name', agentFilter);
      params.set('limit', '30');
      const data = await request<{ items: Record<string, unknown>[] }>(`/api/admin/agent/memories?${params}`);
      setItems(data.items ?? []);
    } catch { setItems([]); }
    finally { setLoading(false); }
  }, [agentFilter]);
  useEffect(() => { void load(); }, [load]);

  const typeColors: Record<string, string> = { experience: 'green', lesson: 'red', strategy: 'blue', pattern: 'purple', rule: 'orange' };
  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
        <Select
          value={agentFilter ?? '__all__'}
          onChange={(v) => setAgentFilter(v === '__all__' ? undefined : v)}
          style={{ width: 180 }}
          size="small"
          options={[
            { value: '__all__', label: '全部Agent' },
            { value: 'knowledge_agent', label: '知识Agent' },
            { value: 'patrol_agent', label: '巡检Agent' },
            { value: 'shared', label: '共享记忆' },
          ]}
        />
      </Space>
      <Table loading={loading} dataSource={items} rowKey="id" size="small" pagination={{ pageSize: 15 }}
        columns={[
          { title: 'Agent', dataIndex: 'agent_name', key: 'agent_name', width: 120,
            render: (v: string) => <Tag color={v === 'shared' ? 'gold' : v === 'knowledge_agent' ? 'blue' : 'green'}>{v}</Tag> },
          { title: '类型', dataIndex: 'memory_type', key: 'memory_type', width: 90,
            render: (v: string) => <Tag color={typeColors[v] || 'default'}>{v}</Tag> },
          { title: '内容', dataIndex: 'content', key: 'content', ellipsis: true },
          { title: '置信度', dataIndex: 'confidence', key: 'confidence', width: 70,
            render: (v: number) => <Text style={{ color: v > 0.7 ? '#52c41a' : v > 0.4 ? '#faad14' : '#ff4d4f' }}>{(v ?? 0).toFixed(2)}</Text> },
          { title: '使用', key: 'usage', width: 70,
            render: (_: unknown, r: Record<string, unknown>) => <Text type="secondary">{String(r.times_used ?? 0)}次</Text> },
          { title: '时间', dataIndex: 'created_at', key: 'created_at', width: 140,
            render: (v: string) => v?.substring(0, 16) },
        ]}
      />
      {items.length === 0 && !loading ? <Empty description="暂无记忆" /> : null}
    </div>
  );
}

function ConversationsTab() {
  const [items, setItems] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await request<{ items: Record<string, unknown>[] }>('/api/admin/agent/conversations?limit=50');
      setItems(data.items ?? []);
    } catch { setItems([]); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const msgColors: Record<string, string> = { message: 'blue', ask: 'orange', reply: 'green', propose: 'purple', debate: 'magenta' };
  const agentColors: Record<string, string> = { knowledge_agent: '#1890ff', patrol_agent: '#52c41a' };
  return (
    <div>
      <Button icon={<ReloadOutlined />} onClick={load} style={{ marginBottom: 16 }}>刷新</Button>
      <div style={{ maxWidth: 700 }}>
        {loading ? <Spin /> : items.length === 0 ? <Empty description="暂无对话" /> :
          items.map((msg) => (
            <div key={msg.id as string} style={{
              marginBottom: 12, padding: 12, borderRadius: 8,
              background: msg.from_agent === 'patrol_agent' ? '#f6ffed' : '#e6f4ff',
              borderLeft: `3px solid ${agentColors[msg.from_agent as string] || '#d9d9d9'}`,
            }}>
              <Space style={{ marginBottom: 4 }}>
                <Tag color={agentColors[msg.from_agent as string] === '#52c41a' ? 'green' : 'blue'}>
                  {msg.from_agent as string}
                </Tag>
                <Text type="secondary">→</Text>
                <Tag>{msg.to_agent as string}</Tag>
                <Tag color={msgColors[msg.message_type as string] || 'default'}>{msg.message_type as string}</Tag>
                <Text type="secondary" style={{ fontSize: 11 }}>
                  {(msg.created_at as string)?.substring(0, 16)}
                </Text>
              </Space>
              <Paragraph style={{ margin: 0, fontSize: 14 }}>
                {msg.content as string}
              </Paragraph>
            </div>
          ))
        }
      </div>
    </div>
  );
}

function KnowledgeScanTab() {
  const [loading, setLoading] = useState(false);
  const [maxFills, setMaxFills] = useState(20);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);

  const handleScan = async (fill: boolean) => {
    setLoading(true);
    setResult(null);
    try {
      const data = await request<Record<string, unknown>>('/api/admin/knowledge/scan-all', {
        method: 'POST',
        body: JSON.stringify({ max_fills: maxFills, scan_only: !fill }),
      });
      setResult(data);
      const filled = (data.filled_count as number) || 0;
      const gaps = (data.total_gaps_found as number) || 0;
      message.success(fill
        ? `巡检完成：填补 ${filled} 条，发现 ${gaps} 个缺口`
        : `扫描完成：发现 ${gaps} 个知识缺口`);
    } catch {
      message.error('巡检失败，请检查AI模型配置');
    } finally {
      setLoading(false);
    }
  };

  const typeSummary = (result?.type_summary ?? {}) as Record<string, { total: number; gaps: number; avg_completeness: number }>;
  const filled = (result?.filled ?? []) as Array<{ title: string; type: string; filled_fields: string[] }>;
  const skippedCount = (result?.skipped_count as number) || 0;
  const errorCount = (result?.error_count as number) || 0;

  return (
    <div>
      <Card style={{ marginBottom: 16 }}>
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <div>
            <Title level={5} style={{ marginBottom: 4 }}>
              <ThunderboltOutlined /> 一键知识巡检
            </Title>
            <Text type="secondary">
              扫描所有栏目（中药/穴位/经络/方剂/理疗/功法），自动发现并填补缺失内容
            </Text>
          </div>

          <Space wrap>
            <Button
              type="primary"
              size="large"
              icon={<ThunderboltOutlined />}
              loading={loading}
              onClick={() => handleScan(true)}
            >
              一键巡检并填补
            </Button>
            <Button
              size="large"
              icon={<ScanOutlined />}
              loading={loading}
              onClick={() => handleScan(false)}
            >
              仅扫描（不填补）
            </Button>
            <Text>填补上限：</Text>
            <Select
              value={maxFills}
              onChange={setMaxFills}
              options={[
                { value: 10, label: '10条' },
                { value: 20, label: '20条' },
                { value: 50, label: '50条' },
                { value: 100, label: '100条' },
              ]}
              style={{ width: 80 }}
            />
          </Space>

          {loading && (
            <div style={{ textAlign: 'center', padding: 20 }}>
              <Spin tip="正在巡检知识库，请耐心等待..." />
            </div>
          )}
        </Space>
      </Card>

      {result && !loading && (
        <>
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={6}>
              <Card><Statistic title="发现缺口" value={Number(result.total_gaps_found || 0)} /></Card>
            </Col>
            <Col span={6}>
              <Card><Statistic title="已填补" value={Number(result.filled_count || 0)} valueStyle={{ color: '#52c41a' }} /></Card>
            </Col>
            <Col span={6}>
              <Card><Statistic title="跳过" value={skippedCount} valueStyle={{ color: '#faad14' }} /></Card>
            </Col>
            <Col span={6}>
              <Card><Statistic title="失败" value={errorCount} valueStyle={{ color: '#ff4d4f' }} /></Card>
            </Col>
          </Row>

          {Object.keys(typeSummary).length > 0 && (
            <Card title="各栏目完整度" size="small" style={{ marginBottom: 16 }}>
              <Table
                dataSource={Object.entries(typeSummary).map(([type, s]) => ({ key: type, type, ...s }))}
                columns={[
                  { title: '栏目', dataIndex: 'type', key: 'type', render: (t: string) => <Tag>{t}</Tag> },
                  { title: '总数', dataIndex: 'total', key: 'total' },
                  { title: '缺口数', dataIndex: 'gaps', key: 'gaps', render: (v: number) => v > 0 ? <Text type="danger">{v}</Text> : v },
                  { title: '平均完整度', dataIndex: 'avg_completeness', key: 'avg',
                    render: (v: number) => <Text style={{ color: v >= 80 ? '#52c41a' : v >= 50 ? '#faad14' : '#ff4d4f' }}>{v}%</Text> },
                ]}
                pagination={false}
                size="small"
              />
            </Card>
          )}

          {filled.length > 0 && (
            <Card title={`已填补详情（${filled.length}条）`} size="small">
              <Table
                dataSource={filled.map((f, i) => ({ key: i, ...f }))}
                columns={[
                  { title: '标题', dataIndex: 'title', key: 'title', render: (t: string) => <Text strong>{t}</Text> },
                  { title: '类型', dataIndex: 'type', key: 'type', render: (t: string) => <Tag>{t}</Tag> },
                  { title: '填补字段', dataIndex: 'filled_fields', key: 'fields',
                    render: (fields: string[]) => <Space wrap>{fields.map((f) => <Tag key={f} color="green">{f}</Tag>)}</Space> },
                ]}
                pagination={{ pageSize: 10 }}
                size="small"
              />
            </Card>
          )}
        </>
      )}
    </div>
  );
}
