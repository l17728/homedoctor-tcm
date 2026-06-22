import { useState, useEffect, useCallback } from 'react';
import {
  Typography, Card, Table, Tag, Button, Space, Statistic, Row, Col,
  Tabs, Modal, Input, message, Empty, Spin, Descriptions,
} from 'antd';
import {
  DatabaseOutlined, ReloadOutlined, DeleteOutlined,
  PlusOutlined, ScanOutlined,
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
        { key: 'models', label: 'AI模型管理', children: <ModelsTab /> },
        { key: 'indexes', label: '索引管理', children: <IndexTab /> },
        { key: 'logs', label: 'Agent日志', children: <LogsTab /> },
        { key: 'feeder', label: '巡检Agent', children: <FeederTab /> },
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
