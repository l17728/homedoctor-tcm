import { useState, useEffect, useCallback } from 'react';
import { Typography, Input, Tag, Skeleton, Empty, Space, Select, Button, message, Divider, Input as AntInput } from 'antd';
import {
  SearchOutlined, PlusOutlined, AppstoreOutlined,
  EditOutlined, SaveOutlined,
} from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import { useIsMobile } from '../hooks/useIsMobile';
import {
  getCategories, browseKnowledge, getEntity, appendKnowledge, 
  getNote, saveNote,
  ENTITY_TYPE_LABEL, ENTITY_TYPE_TAG_COLOR,
  type KnowledgeEntity, type KnowledgeEntityDetail,
} from '../api/knowledgeHubApi';

const { Title, Text, Paragraph } = Typography;

const TRUST_COLORS: Record<string, string> = {
  S: '#52c41a', A: '#1890ff', B: '#faad14', C: '#fa8c16',
};

export default function KnowledgeBrowsePage() {
  const isMobile = useIsMobile();
  const [types, setTypes] = useState<Array<{ type: string; label: string; count: number }>>([]);
  const [categories, setCategories] = useState<Record<string, Array<{ category: string; count: number }>>>({});
  const [activeType, setActiveType] = useState('herb');
  const [activeCategory, setActiveCategory] = useState<string | undefined>();
  const [searchQuery, setSearchQuery] = useState('');
  const [items, setItems] = useState<Array<KnowledgeEntity & { trustLevel?: string; trustScore?: number }>>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<KnowledgeEntityDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [appendOpen, setAppendOpen] = useState(false);
  const [appendInstruction, setAppendInstruction] = useState('');
  const [appendLoading, setAppendLoading] = useState(false);
  const [appendResult, setAppendResult] = useState<Record<string, unknown> | null>(null);
  const [noteContent, setNoteContent] = useState('');
  const [noteEditing, setNoteEditing] = useState(false);
  const [noteSaving, setNoteSaving] = useState(false);

  useEffect(() => {
    getCategories().then((data) => {
      setTypes(data.types ?? []);
      setCategories(data.categories ?? {});
      if (data.types?.length > 0 && !data.types.find((t) => t.type === activeType)) {
        setActiveType(data.types?.[0]?.type ?? "herb");
      }
    }).catch(() => {});
  }, []);

  const loadItems = useCallback(async () => {
    setLoading(true);
    try {
      const result = await browseKnowledge(activeType, activeCategory, searchQuery || undefined, 1, 100);
      setItems(result.items as Array<KnowledgeEntity & { trustLevel?: string; trustScore?: number }>);
      setTotal(result.total);
      if (result.items.length > 0 && !selectedId) {
        setSelectedId(result.items?.[0]?.id ?? null);
      }
    } catch {
      setItems([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [activeType, activeCategory, searchQuery]);

  useEffect(() => { void loadItems(); }, [loadItems]);

  useEffect(() => {
    if (!selectedId) { setDetail(null); return; }
    setDetailLoading(true);
    setDetail(null);
    getEntity(selectedId).then((d) => {
      setDetail(d);
      getNote(selectedId).then((n) => setNoteContent(n.content || '')).catch(() => setNoteContent(''));
    }).catch(() => setDetail(null)).finally(() => setDetailLoading(false));
  }, [selectedId]);

  const handleAppend = async () => {
    if (!detail || !appendInstruction.trim()) return;
    setAppendLoading(true);
    setAppendResult(null);
    try {
      const result = await appendKnowledge(detail.id, appendInstruction.trim());
      setAppendResult(result);
    } catch { message.error('追加失败'); }
    finally { setAppendLoading(false); }
  };

  const handleSaveNote = async () => {
    if (!selectedId) return;
    setNoteSaving(true);
    try {
      await saveNote(selectedId, noteContent);
      setNoteEditing(false);
      message.success('笔记已保存');
    } catch { message.error('保存失败'); }
    finally { setNoteSaving(false); }
  };

  const renderLeftList = () => {
    if (loading) return <Skeleton active paragraph={{ rows: 8 }} />;
    if (!items.length) return <Empty description="暂无知识" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
    return (
      <div style={{ overflow: 'auto', flex: 1 }}>
        {items.map((e) => {
          const trustLevel = e.trustLevel ?? 'S';
          const isActive = selectedId === e.id;
          return (
            <div
              key={e.id}
              onClick={() => setSelectedId(e.id)}
              style={{
                cursor: 'pointer',
                padding: '10px 12px',
                borderRadius: 6,
                background: isActive ? '#e6f4ff' : 'transparent',
                borderLeft: isActive ? '3px solid #1677ff' : '3px solid transparent',
                marginBottom: 2,
                transition: 'background 0.2s',
              }}
              onMouseEnter={(ev) => { if (!isActive) (ev.currentTarget as HTMLDivElement).style.background = '#f5f5f5'; }}
              onMouseLeave={(ev) => { if (!isActive) (ev.currentTarget as HTMLDivElement).style.background = 'transparent'; }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <div style={{
                  width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
                  background: TRUST_COLORS[trustLevel] ?? '#1890ff',
                }} />
                <Text ellipsis style={{ fontSize: 14, fontWeight: isActive ? 600 : 400, flex: 1 }}>
                  {e.title}
                </Text>
              </div>
              {e.category ? (
                <Text type="secondary" style={{ fontSize: 11, marginLeft: 14 }}>
                  {e.category}
                </Text>
              ) : null}
            </div>
          );
        })}
      </div>
    );
  };

  const renderRightContent = () => {
    if (detailLoading) return <Skeleton active paragraph={{ rows: 12 }} />;
    if (!detail) return <Empty description="选择左侧条目查看详情" />;
    const props = (detail.properties ?? {}) as Record<string, unknown>;
    const groups = detail.groupedRelationships ?? {};
    const markdownContent = buildMarkdown(detail, props, groups);

    return (
      <div style={{ overflow: 'auto', padding: '16px 24px' }}>
        <div style={{ marginBottom: 16 }}>
          <Space align="center" wrap>
            <Title level={3} style={{ margin: 0 }}>{detail.title}</Title>
            <Tag color={ENTITY_TYPE_TAG_COLOR[detail.type] ?? 'default'}>
              {ENTITY_TYPE_LABEL[detail.type] ?? detail.type}
            </Tag>
            {detail.category ? <Tag>{detail.category}</Tag> : null}
          </Space>
        </div>

        <div className="markdown-body" style={{ marginBottom: 24 }}>
          <ReactMarkdown>{markdownContent}</ReactMarkdown>
        </div>

        <Divider />

        <div style={{ marginBottom: 16 }}>
          <Space style={{ marginBottom: 8 }}>
            <EditOutlined />
            <Text strong>我的笔记</Text>
            {!noteEditing && noteContent ? (
              <Button type="link" size="small" icon={<EditOutlined />} onClick={() => setNoteEditing(true)}>
                编辑
              </Button>
            ) : null}
          </Space>
          {!noteEditing ? (
            noteContent ? (
              <div className="markdown-body" style={{
                padding: 12, background: '#fafafa', borderRadius: 8, border: '1px solid #f0f0f0',
              }}>
                <ReactMarkdown>{noteContent}</ReactMarkdown>
              </div>
            ) : (
              <AntInput.TextArea
                value={noteContent}
                onChange={(e) => setNoteContent(e.target.value)}
                onFocus={() => setNoteEditing(true)}
                placeholder="点击此处添加笔记（支持Markdown格式）..."
                autoSize={{ minRows: 2 }}
                style={{ fontSize: 14 }}
              />
            )
          ) : (
            <div>
              <AntInput.TextArea
                value={noteContent}
                onChange={(e) => setNoteContent(e.target.value)}
                placeholder="记录你的理解、心得、疑问..."
                autoSize={{ minRows: 4 }}
                style={{ fontSize: 14, marginBottom: 8 }}
              />
              <Space>
                <Button type="primary" size="small" icon={<SaveOutlined />} loading={noteSaving} onClick={handleSaveNote}>
                  保存
                </Button>
                <Button size="small" onClick={() => setNoteEditing(false)}>
                  取消
                </Button>
              </Space>
            </div>
          )}
        </div>

        <Divider />

        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => { setAppendOpen(true); setAppendResult(null); setAppendInstruction(''); }}
          size="large"
        >
          追加内容
        </Button>

        {appendOpen ? (
          <div style={{ marginTop: 16, padding: 16, background: '#f6f8fa', borderRadius: 8 }}>
            <Text type="secondary" style={{ display: 'block', marginBottom: 8 }}>
              Agent将自动从知识库、外部索引和互联网收集信息，合成补充内容，经专家评审后入库。支持多次追加。
            </Text>
            {!appendResult ? (
              <>
                <AntInput.TextArea
                  value={appendInstruction}
                  onChange={(e) => setAppendInstruction(e.target.value)}
                  placeholder={'描述你想追加的内容，例如：\n• 添加具体练习步骤\n• 补充适应人群和禁忌\n• 增加药理研究数据'}
                  rows={3}
                  style={{ fontSize: 14, marginBottom: 8 }}
                />
                <Space>
                  <Button type="primary" loading={appendLoading} onClick={handleAppend} disabled={!appendInstruction.trim()}>
                    提交追加请求
                  </Button>
                  <Button onClick={() => setAppendOpen(false)}>取消</Button>
                </Space>
              </>
            ) : (
              <div>
                <Tag color={(appendResult as Record<string, string>).decision === 'adopted' ? 'green' : 'orange'}>
                  {(appendResult as Record<string, string>).decision ?? '完成'}
                </Tag>
                <Text style={{ marginLeft: 8 }}>{(appendResult as Record<string, string>).message ?? ''}</Text>
                {(appendResult as Record<string, unknown>).synthesized_preview ? (
                  <Paragraph style={{ marginTop: 8, fontSize: 13, color: '#666' }}>
                    {(appendResult as Record<string, string>).synthesized_preview as string}
                  </Paragraph>
                ) : null}
                <Button size="small" type="link" onClick={() => { setAppendResult(null); setAppendInstruction(''); }}>
                  再次追加
                </Button>
              </div>
            )}
          </div>
        ) : null}
      </div>
    );
  };

  return (
    <div style={{ height: 'calc(100vh - 120px)', display: 'flex', flexDirection: 'column' }}>
      <div style={{ marginBottom: 12, display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        <Space>
          <AppstoreOutlined style={{ color: '#1677ff' }} />
          <Text strong>知识库</Text>
        </Space>
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
          {types.map((t) => (
            <Button
              key={t.type}
              type={activeType === t.type ? 'primary' : 'default'}
              size="small"
              onClick={() => { setActiveType(t.type); setActiveCategory(undefined); setSelectedId(null); }}
            >
              {t.label}({t.count})
            </Button>
          ))}
        </div>
        <Select
          value={activeCategory ?? '__all__'}
          onChange={(v) => { setActiveCategory(v === '__all__' ? undefined : v); setSelectedId(null); }}
          size="small"
          style={{ width: 160 }}
          options={[
            { value: '__all__', label: '全部分类' },
            ...((categories[activeType] ?? []).map((c) => ({ value: c.category, label: `${c.category} (${c.count})` }))),
          ]}
        />
        <Input
          prefix={<SearchOutlined style={{ color: '#999' }} />}
          placeholder="搜索..."
          allowClear
          size="small"
          style={{ width: 160 }}
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
        />
      </div>

      <div style={{ flex: 1, display: 'flex', gap: 0, border: '1px solid #f0f0f0', borderRadius: 8, overflow: 'hidden' }}>
        <div style={{
          width: isMobile ? '40%' : 280,
          flexShrink: 0,
          borderRight: '1px solid #f0f0f0',
          display: 'flex',
          flexDirection: 'column',
        }}>
          <Text type="secondary" style={{ padding: '8px 12px', fontSize: 12, borderBottom: '1px solid #f0f0f0' }}>
            {total} 条结果
          </Text>
          {renderLeftList()}
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          {renderRightContent()}
        </div>
      </div>
    </div>
  );
}

function buildMarkdown(
  detail: KnowledgeEntityDetail,
  props: Record<string, unknown>,
  groups: Record<string, Array<{ id: string; label: string; type: string }>>,
): string {
  const lines: string[] = [];
  if (detail.summary) {
    lines.push(`> ${detail.summary}`, '');
  }
  const skipKeys = new Set(['source_type', 'content_length', 'source_url', 'ai_keywords', 'related_entities', 'category']);
  const entries = Object.entries(props).filter(([k]) => !skipKeys.has(k));
  if (entries.length > 0) {
    lines.push('### 属性详情', '');
    for (const [k, v] of entries.slice(0, 20)) {
      const val = Array.isArray(v) ? v.join('、') : typeof v === 'object' ? JSON.stringify(v).slice(0, 100) : String(v);
      if (val && val.trim()) {
        lines.push(`- **${k}**: ${val}`);
      }
    }
    lines.push('');
  }
  if (Object.keys(groups).length > 0) {
    lines.push('### 关联知识', '');
    for (const [type, items] of Object.entries(groups)) {
      if (items.length > 0) {
        lines.push(`**${type}**: ${items.map((i) => i.label).join('、')}`);
      }
    }
    lines.push('');
  }
  return lines.join('\n');
}
