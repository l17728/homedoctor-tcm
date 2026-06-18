import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import {
  Typography,
  Input,
  Button,
  Space,
  Tag,
  Card,
  Row,
  Col,
  Skeleton,
  Empty,
  Drawer,
  Divider,
  Select,
  Modal,
  Upload,
  Spin,
  Tooltip,
  message,
  Alert,
  Input as AntInput,
} from 'antd';
import type { UploadProps } from 'antd';
import {
  SearchOutlined,
  BookOutlined,
  ImportOutlined,
  EyeOutlined,
  LinkOutlined,
  WarningOutlined,
  InboxOutlined,
  FileTextOutlined,
  RobotOutlined,
  CheckCircleOutlined,
  StarOutlined,
  StarFilled,
  ReloadOutlined,
  FireOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons';
import { useIsMobile } from '../hooks/useIsMobile';
import { ApiError } from '../api/client';
import {
  searchKnowledge,
  getEntity,
  getEntityTypes,
  importText,
  importFile,
  getPopular,
  getRecent,
  ENTITY_TYPE_LABEL,
  ENTITY_TYPE_BORDER,
  ENTITY_TYPE_TAG_COLOR,
  RELATION_TYPE_LABEL,
  RELATION_TYPE_WARNING,
  type KnowledgeEntity,
  type KnowledgeEntityDetail,
  type ImportPreview,
  type TypeCounts,
} from '../api/knowledgeHubApi';

const { Title, Text, Paragraph } = Typography;
const { Dragger } = Upload;
const { TextArea } = AntInput;

const PAGE_SIZE = 18;
const DEBOUNCE_MS = 300;
const ACCEPTED_EXT = '.pdf,.docx,.doc,.txt,.md,.jpg,.jpeg,.png,.webp';

/** 侧边栏类型过滤项顺序（与 spec §知识库 一致） */
const FILTER_ORDER: string[] = [
  'all',
  'herb',
  'formula',
  'therapy',
  'symptom',
  'tea_recipe',
  'health_method',
  'article',
];

function filterLabel(type: string, counts: TypeCounts): string {
  if (type === 'all') return '全部';
  const label = ENTITY_TYPE_LABEL[type] ?? type;
  const n = counts[type] ?? 0;
  return n > 0 ? `${label} ${n}` : label;
}

export default function KnowledgeHubPage() {
  const isMobile = useIsMobile();

  const [activeType, setActiveType] = useState<string>('all');
  const [searchInput, setSearchInput] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');

  const [typeCounts, setTypeCounts] = useState<TypeCounts>({});
  const [items, setItems] = useState<KnowledgeEntity[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);

  const [popular, setPopular] = useState<KnowledgeEntity[]>([]);
  const [recent, setRecent] = useState<KnowledgeEntity[]>([]);
  const [discoverLoading, setDiscoverLoading] = useState(true);

  const [detailId, setDetailId] = useState<string | null>(null);
  const [detail, setDetail] = useState<KnowledgeEntityDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [favorites, setFavorites] = useState<Set<string>>(() => {
    try {
      const raw = localStorage.getItem('kh_favorites');
      return raw ? new Set(JSON.parse(raw) as string[]) : new Set();
    } catch {
      return new Set();
    }
  });

  const [importOpen, setImportOpen] = useState(false);
  const [importMode, setImportMode] = useState<'file' | 'text'>('file');
  const [importing, setImporting] = useState(false);
  const [importPreview, setImportPreview] = useState<ImportPreview | null>(null);
  const [importTextValue, setImportTextValue] = useState('');
  const [importTitle, setImportTitle] = useState('');
  const [editSummary, setEditSummary] = useState('');
  const [editTags, setEditTags] = useState<string[]>([]);

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const isSearching = debouncedQuery.trim().length > 0;

  /** 错误统一提示 */
  const notifyError = useCallback((e: unknown, fallback: string) => {
    const msg = e instanceof ApiError ? e.message : fallback;
    void message.error(msg);
  }, []);

  /** 加载类型计数 + 热门 + 最近 */
  const loadDiscovery = useCallback(async () => {
    setDiscoverLoading(true);
    try {
      const [counts, pop, rec] = await Promise.all([
        getEntityTypes().catch(() => ({})),
        getPopular(6).catch(() => []),
        getRecent(6).catch(() => []),
      ]);
      setTypeCounts(counts);
      setPopular(pop);
      setRecent(rec);
    } finally {
      setDiscoverLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadDiscovery();
  }, [loadDiscovery]);

  /** 搜索输入防抖 */
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setDebouncedQuery(searchInput);
    }, DEBOUNCE_MS);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [searchInput]);

  /** 执行搜索（q 或 type 变化时） */
  const runSearch = useCallback(
    async (q: string, type: string, pageNum: number, append: boolean) => {
      if (append) {
        setLoadingMore(true);
      } else {
        setLoading(true);
      }
      try {
        const result = await searchKnowledge({
          q: q.trim() || undefined,
          type,
          page: pageNum,
          pageSize: PAGE_SIZE,
        });
        setItems((prev) =>
          append ? [...prev, ...result.items] : result.items,
        );
        setTotal(result.total);
        setPage(pageNum);
        setHasMore((append ? items.length : 0) + result.items.length < result.total);
      } catch (e) {
        notifyError(e, '搜索失败，请稍后重试');
        if (!append) {
          setItems([]);
          setTotal(0);
        }
      } finally {
        setLoading(false);
        setLoadingMore(false);
      }
    },
    [notifyError, items.length],
  );

  useEffect(() => {
    if (!isSearching) {
      setItems([]);
      setTotal(0);
      return;
    }
    void runSearch(debouncedQuery, activeType, 1, false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedQuery, activeType, isSearching]);

  const handleLoadMore = () => {
    if (!isSearching) return;
    void runSearch(debouncedQuery, activeType, page + 1, true);
  };

  /** 打开实体详情 */
  const openDetail = useCallback(async (id: string) => {
    setDetailId(id);
    setDetail(null);
    setDetailLoading(true);
    try {
      const d = await getEntity(id);
      setDetail(d);
    } catch (e) {
      notifyError(e, '加载详情失败');
      setDetailId(null);
    } finally {
      setDetailLoading(false);
    }
  }, [notifyError]);

  const closeDetail = () => {
    setDetailId(null);
    setDetail(null);
  };

  /** 收藏切换（本地 localStorage） */
  const toggleFavorite = (id: string) => {
    setFavorites((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
        void message.success('已收藏');
      }
      try {
        localStorage.setItem('kh_favorites', JSON.stringify([...next]));
      } catch {
        /* ignore quota */
      }
      return next;
    });
  };

  // ============ 导入逻辑 ============

  const resetImport = () => {
    setImportPreview(null);
    setImportTextValue('');
    setImportTitle('');
    setEditSummary('');
    setEditTags([]);
  };

  const closeImport = () => {
    setImportOpen(false);
    resetImport();
  };

  const handleFileDrop = async (file: File) => {
    setImporting(true);
    setImportPreview(null);
    try {
      const preview = await importFile(file);
      setImportPreview(preview);
      setEditSummary(preview.summary);
      setEditTags(preview.tags.length > 0 ? preview.tags : preview.keywords);
      void message.success('AI 分析完成');
    } catch (e) {
      notifyError(e, '文件导入失败');
    } finally {
      setImporting(false);
    }
  };

  const handleTextImport = async () => {
    if (!importTextValue.trim()) {
      void message.warning('请输入要分析的内容');
      return;
    }
    setImporting(true);
    setImportPreview(null);
    try {
      const preview = await importText({
        title: importTitle.trim(),
        content: importTextValue,
      });
      setImportPreview(preview);
      setEditSummary(preview.summary);
      setEditTags(preview.tags.length > 0 ? preview.tags : preview.keywords);
      void message.success('AI 分析完成');
    } catch (e) {
      notifyError(e, '分析失败');
    } finally {
      setImporting(false);
    }
  };

  const confirmSaveImport = () => {
    if (importPreview) {
      void message.success(`「${importPreview.title || '新条目'}」已保存到知识库`);
    }
    closeImport();
    // 重新加载发现区
    void loadDiscovery();
    // 若当前在搜索态，刷新
    if (isSearching) {
      void runSearch(debouncedQuery, activeType, 1, false);
    }
  };

  const draggerProps: UploadProps = {
    name: 'file',
    multiple: false,
    accept: ACCEPTED_EXT,
    showUploadList: false,
    disabled: importing,
    beforeUpload: (file) => {
      void handleFileDrop(file);
      return false;
    },
  };

  const totalCount = useMemo(
    () => Object.values(typeCounts).reduce((a, b) => a + b, 0),
    [typeCounts],
  );

  // ============ 渲染辅助 ============

  const renderEntityCard = (entity: KnowledgeEntity) => {
    const borderColor = ENTITY_TYPE_BORDER[entity.type] ?? '#d9d9d9';
    const tagColor = ENTITY_TYPE_TAG_COLOR[entity.type] ?? 'default';
    const typeLabel = ENTITY_TYPE_LABEL[entity.type] ?? entity.type;
    const isFav = favorites.has(entity.id);
    return (
      <Card
        key={entity.id}
        hoverable
        onClick={() => openDetail(entity.id)}
        styles={{ body: { padding: 16 } }}
        style={{
          height: '100%',
          borderRadius: 10,
          borderTop: `3px solid ${borderColor}`,
          transition: 'all 0.25s ease',
        }}
      >
        <Space direction="vertical" size={8} style={{ width: '100%' }}>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'flex-start',
              gap: 8,
            }}
          >
            <Text strong style={{ fontSize: 17, lineHeight: 1.3 }}>
              {entity.title}
            </Text>
            <Tag color={tagColor} style={{ margin: 0, flexShrink: 0 }}>
              {typeLabel}
            </Tag>
          </div>

          {entity.category && (
            <Tag style={{ margin: 0, alignSelf: 'flex-start' }}>
              {entity.category}
            </Tag>
          )}

          {entity.tags.length > 0 && (
            <Space size={[4, 4]} wrap>
              {entity.tags.slice(0, 4).map((t, i) => (
                <Text
                  key={`${t}-${i}`}
                  style={{ fontSize: 12, color: '#8c8c8c' }}
                >
                  #{t}
                </Text>
              ))}
              {entity.tags.length > 4 && (
                <Text style={{ fontSize: 12, color: '#bfbfbf' }}>
                  +{entity.tags.length - 4}
                </Text>
              )}
            </Space>
          )}

          <Paragraph
            type="secondary"
            ellipsis={{ rows: 2 }}
            style={{ fontSize: 14, marginBottom: 0, minHeight: 42 }}
          >
            {entity.summary || '暂无摘要'}
          </Paragraph>

          <Divider style={{ margin: '2px 0' }} />

          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              fontSize: 12,
              color: '#8c8c8c',
            }}
          >
            <Space size={12}>
              <span>
                <EyeOutlined style={{ marginRight: 3 }} />
                {entity.viewCount}
              </span>
              <span>
                <LinkOutlined style={{ marginRight: 3 }} />
                {entity.relationshipCount}
              </span>
            </Space>
            {isFav ? (
              <StarFilled style={{ color: '#faad14', fontSize: 14 }} />
            ) : null}
          </div>
        </Space>
      </Card>
    );
  };

  const renderStatsBar = () => (
    <Card
      size="small"
      style={{ marginBottom: 16, borderRadius: 8 }}
      styles={{ body: { padding: '12px 16px' } }}
    >
      <Space wrap size={[16, 4]}>
        <Text strong style={{ fontSize: 15 }}>
          知识库共 {totalCount.toLocaleString()} 条
        </Text>
        <Text type="secondary" style={{ fontSize: 13 }}>
          ·
        </Text>
        {FILTER_ORDER.filter((t) => t !== 'all').map((t) => {
          const n = typeCounts[t] ?? 0;
          if (n === 0 && !ENTITY_TYPE_LABEL[t]) return null;
          return (
            <Text key={t} style={{ fontSize: 13 }}>
              <span
                style={{
                  display: 'inline-block',
                  width: 8,
                  height: 8,
                  borderRadius: '50%',
                  background: ENTITY_TYPE_BORDER[t] ?? '#d9d9d9',
                  marginRight: 5,
                  verticalAlign: 'middle',
                }}
              />
              {ENTITY_TYPE_LABEL[t] ?? t} {n.toLocaleString()}
            </Text>
          );
        })}
      </Space>
    </Card>
  );

  const renderSidebar = () => (
    <div>
      <Card size="small" style={{ borderRadius: 8 }}>
        <Space direction="vertical" size={4} style={{ width: '100%' }}>
          {FILTER_ORDER.map((t) => {
            const active = activeType === t;
            const n = t === 'all' ? totalCount : typeCounts[t] ?? 0;
            return (
              <div
                key={t}
                onClick={() => setActiveType(t)}
                style={{
                  cursor: 'pointer',
                  padding: '8px 12px',
                  borderRadius: 6,
                  background: active ? '#e6f4ff' : 'transparent',
                  color: active ? '#1677ff' : 'inherit',
                  fontWeight: active ? 600 : 400,
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  fontSize: 15,
                  transition: 'background 0.2s',
                }}
              >
                <span>{filterLabel(t, typeCounts)}</span>
                {t !== 'all' && n > 0 && (
                  <Text
                    type="secondary"
                    style={{
                      fontSize: 12,
                      color: active ? '#1677ff' : '#8c8c8c',
                    }}
                  >
                    {n}
                  </Text>
                )}
              </div>
            );
          })}
        </Space>
      </Card>

      <Divider style={{ margin: '12px 0' }} />

      <Button
        block
        type="dashed"
        icon={<ImportOutlined />}
        onClick={() => {
          setImportMode('file');
          setImportOpen(true);
        }}
        style={{ height: 44, fontSize: 15 }}
      >
        导入新知识
      </Button>
    </div>
  );

  const renderDiscoverSection = (
    title: string,
    icon: React.ReactNode,
    list: KnowledgeEntity[],
  ) => {
    if (list.length === 0) return null;
    return (
      <div style={{ marginBottom: 24 }}>
        <Space style={{ marginBottom: 12 }}>
          {icon}
          <Text strong style={{ fontSize: 16 }}>
            {title}
          </Text>
        </Space>
        <Row gutter={[16, 16]}>
          {list.slice(0, 6).map((e) => (
            <Col xs={24} sm={12} lg={8} key={e.id}>
              {renderEntityCard(e)}
            </Col>
          ))}
        </Row>
      </div>
    );
  };

  const renderImportPreview = () => {
    if (!importPreview) return null;
    return (
      <div style={{ marginTop: 16 }}>
        <Alert
          type="success"
          showIcon
          icon={<CheckCircleOutlined />}
          message="AI 分析完成"
          description={`识别类型：${ENTITY_TYPE_LABEL[importPreview.type] ?? importPreview.type}${
            importPreview.category ? ` · ${importPreview.category}` : ''
          }${importPreview.wordCount ? ` · ${importPreview.wordCount} 字` : ''}`}
          style={{ marginBottom: 12 }}
        />

        <div style={{ marginBottom: 12 }}>
          <Text strong style={{ display: 'block', marginBottom: 4 }}>
            标题
          </Text>
          <Text>{importPreview.title || '（未识别标题）'}</Text>
        </div>

        <div style={{ marginBottom: 12 }}>
          <Text strong style={{ display: 'block', marginBottom: 4 }}>
            摘要（可编辑）
          </Text>
          <TextArea
            value={editSummary}
            onChange={(e) => setEditSummary(e.target.value)}
            autoSize={{ minRows: 3, maxRows: 6 }}
            style={{ fontSize: 14 }}
          />
        </div>

        <div style={{ marginBottom: 12 }}>
          <Text strong style={{ display: 'block', marginBottom: 4 }}>
            关键词（可编辑）
          </Text>
          <Select
            mode="tags"
            style={{ width: '100%' }}
            value={editTags}
            onChange={setEditTags}
            placeholder="输入关键词后回车"
            tokenSeparators={[',', '，', ' ']}
          />
        </div>

        {importPreview.relationships.length > 0 && (
          <div style={{ marginBottom: 12 }}>
            <Text strong style={{ display: 'block', marginBottom: 4 }}>
              发现关联（{importPreview.relationships.length}）
            </Text>
            <Space size={[4, 4]} wrap>
              {importPreview.relationships.slice(0, 12).map((r, i) => {
                const label =
                  r.targetLabel ?? r.sourceLabel ?? r.target ?? r.source;
                const rtype = RELATION_TYPE_LABEL[r.type] ?? r.type;
                const warn = RELATION_TYPE_WARNING[r.type];
                return (
                  <Tag
                    key={`${r.source}-${r.target}-${i}`}
                    color={warn ? 'red' : 'blue'}
                    icon={warn ? <WarningOutlined /> : undefined}
                  >
                    {rtype}：{label}
                  </Tag>
                );
              })}
              {importPreview.relationships.length > 12 && (
                <Tag>+{importPreview.relationships.length - 12}</Tag>
              )}
            </Space>
          </div>
        )}

        <Button
          type="primary"
          block
          size="large"
          icon={<CheckCircleOutlined />}
          onClick={confirmSaveImport}
          style={{ marginTop: 4 }}
        >
          保存到知识库
        </Button>
      </div>
    );
  };

  return (
    <div>
      {/* ============ 页头 ============ */}
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
            <BookOutlined style={{ color: '#1677ff' }} />
            知识库
          </Space>
        </Title>
        <Space wrap>
          <Input
            prefix={<SearchOutlined style={{ color: '#999' }} />}
            placeholder="搜索中药、方剂、症状…"
            allowClear
            style={{ width: isMobile ? '100%' : 280, fontSize: 15 }}
            size="large"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
          />
          <Button
            type="primary"
            icon={<ImportOutlined />}
            size="large"
            onClick={() => {
              setImportMode('file');
              setImportOpen(true);
            }}
          >
            导入
          </Button>
          <Tooltip title="刷新">
            <Button
              icon={<ReloadOutlined />}
              size="large"
              onClick={() => {
                void loadDiscovery();
                if (isSearching) {
                  void runSearch(debouncedQuery, activeType, 1, false);
                }
              }}
            />
          </Tooltip>
        </Space>
      </div>

      {/* ============ 主体布局 ============ */}
      <div
        style={{
          display: 'flex',
          gap: 16,
          alignItems: 'flex-start',
        }}
      >
        {/* 左侧栏 — 桌面端 */}
        {!isMobile && (
          <div style={{ width: 200, flexShrink: 0 }}>{renderSidebar()}</div>
        )}

        {/* 右侧内容 */}
        <div style={{ flex: 1, minWidth: 0 }}>
          {renderStatsBar()}

          {/* 移动端类型下拉 */}
          {isMobile && (
            <Select
              value={activeType}
              onChange={setActiveType}
              style={{ width: '100%', marginBottom: 12 }}
              size="large"
              options={FILTER_ORDER.map((t) => ({
                value: t,
                label: filterLabel(t, typeCounts),
              }))}
            />
          )}

          {/* 内容区域 */}
          {isSearching ? (
            // ====== 搜索结果 ======
            loading ? (
              <Skeleton active paragraph={{ rows: 8 }} />
            ) : items.length === 0 ? (
              <Empty
                description={
                  <span>
                    未找到「{debouncedQuery}」相关知识，
                    <a
                      onClick={() => {
                        setImportMode('text');
                        setImportOpen(true);
                      }}
                    >
                      试试导入新内容？
                    </a>
                  </span>
                }
                style={{ marginTop: 60 }}
              />
            ) : (
              <>
                <Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
                  找到 {total.toLocaleString()} 条结果
                </Text>
                <Row gutter={[16, 16]}>
                  {items.map((e) => (
                    <Col xs={24} sm={12} lg={8} key={e.id}>
                      {renderEntityCard(e)}
                    </Col>
                  ))}
                </Row>
                {hasMore && (
                  <div style={{ textAlign: 'center', marginTop: 24 }}>
                    <Button
                      size="large"
                      loading={loadingMore}
                      onClick={handleLoadMore}
                    >
                      加载更多
                    </Button>
                  </div>
                )}
              </>
            )
          ) : // ====== 发现区（无搜索词） ======
          discoverLoading ? (
            <Skeleton active paragraph={{ rows: 10 }} />
          ) : popular.length === 0 && recent.length === 0 ? (
            <Empty
              description={
                <span>
                  知识库为空，
                  <a
                    onClick={() => {
                      setImportMode('file');
                      setImportOpen(true);
                    }}
                  >
                    导入第一批内容
                  </a>
                </span>
              }
              style={{ marginTop: 60 }}
            />
          ) : (
            <>
              {renderDiscoverSection(
                '热门',
                <FireOutlined style={{ color: '#fa541c' }} />,
                popular,
              )}
              {renderDiscoverSection(
                '最近添加',
                <ClockCircleOutlined style={{ color: '#1677ff' }} />,
                recent,
              )}
            </>
          )}
        </div>
      </div>

      {/* ============ 实体详情抽屉 ============ */}
      <Drawer
        title={
          <Space>
            <Text strong style={{ fontSize: 16 }}>
              {detail?.title ?? '加载中…'}
            </Text>
            {detail && (
              <Tag color={ENTITY_TYPE_TAG_COLOR[detail.type] ?? 'default'}>
                {ENTITY_TYPE_LABEL[detail.type] ?? detail.type}
              </Tag>
            )}
          </Space>
        }
        width={isMobile ? '100%' : 560}
        open={!!detailId}
        onClose={closeDetail}
        destroyOnClose
        maskClosable={false}
        extra={
          detailId && (
            <Button
              type="text"
              icon={
                favorites.has(detailId) ? (
                  <StarFilled style={{ color: '#faad14' }} />
                ) : (
                  <StarOutlined />
                )
              }
              onClick={() => toggleFavorite(detailId)}
            />
          )
        }
      >
        {detailLoading ? (
          <Skeleton active paragraph={{ rows: 10 }} />
        ) : detail ? (
          <EntityDetailContent
            detail={detail}
            onNavigate={(id) => openDetail(id)}
          />
        ) : (
          <Empty description="加载失败" />
        )}
      </Drawer>

      {/* ============ 导入弹窗 ============ */}
      <Modal
        title={
          <Space>
            <RobotOutlined />
            AI 知识导入
          </Space>
        }
        open={importOpen}
        onCancel={closeImport}
        footer={
          importPreview ? (
            <Button onClick={closeImport}>关闭</Button>
          ) : (
            <Space>
              <Button
                type={importMode === 'file' ? 'primary' : 'default'}
                icon={<InboxOutlined />}
                onClick={() => setImportMode('file')}
              >
                文件导入
              </Button>
              <Button
                type={importMode === 'text' ? 'primary' : 'default'}
                icon={<FileTextOutlined />}
                onClick={() => setImportMode('text')}
              >
                文本粘贴
              </Button>
            </Space>
          )
        }
        width={isMobile ? '95%' : 600}
        destroyOnClose
        maskClosable={false}
      >
        {importing ? (
          <div style={{ textAlign: 'center', padding: '40px 0' }}>
            <Spin size="large" />
            <Paragraph
              type="secondary"
              style={{ marginTop: 16, fontSize: 15 }}
            >
              <RobotOutlined style={{ marginRight: 6 }} />
              AI 正在分析…
            </Paragraph>
          </div>
        ) : importPreview ? (
          renderImportPreview()
        ) : importMode === 'file' ? (
          <>
            <Dragger {...draggerProps}>
              <p className="ant-upload-drag-icon">
                <InboxOutlined />
              </p>
              <p className="ant-upload-text" style={{ fontSize: 15 }}>
                点击或拖拽文件到此处
              </p>
              <p className="ant-upload-hint">
                支持 PDF / Word / TXT / Markdown / 图片，AI 将自动提取结构化知识
              </p>
            </Dragger>
            <Alert
              type="info"
              showIcon
              message="AI 会自动识别类型、生成摘要、提取关键词、发现关联"
              style={{ marginTop: 12, fontSize: 13 }}
            />
          </>
        ) : (
          <>
            <Input
              placeholder="标题（可选）"
              value={importTitle}
              onChange={(e) => setImportTitle(e.target.value)}
              style={{ marginBottom: 8, fontSize: 15 }}
              size="large"
            />
            <TextArea
              placeholder="粘贴文章、医案、药方说明等内容…"
              value={importTextValue}
              onChange={(e) => setImportTextValue(e.target.value)}
              autoSize={{ minRows: 8, maxRows: 16 }}
              style={{ fontSize: 14 }}
            />
            <Button
              type="primary"
              block
              size="large"
              icon={<RobotOutlined />}
              onClick={handleTextImport}
              disabled={!importTextValue.trim()}
              style={{ marginTop: 12 }}
            >
              AI 分析
            </Button>
          </>
        )}
      </Modal>
    </div>
  );
}

/** 实体详情内容（按关系分组渲染可点击的关联芯片） */
function EntityDetailContent({
  detail,
  onNavigate,
}: {
  detail: KnowledgeEntityDetail;
  onNavigate: (id: string) => void;
}) {
  const groups = detail.groupedRelationships ?? {};
  const groupKeys = Object.keys(groups);
  const totalRel = groupKeys.reduce(
    (sum, k) => sum + (groups[k]?.length ?? 0),
    0,
  );

  return (
    <div>
      {/* 标签行 */}
      {(detail.category || detail.tags.length > 0) && (
        <div style={{ marginBottom: 12 }}>
          {detail.category && (
            <Tag style={{ marginBottom: 4 }}>{detail.category}</Tag>
          )}
          {detail.tags.slice(0, 8).map((t, i) => (
            <Text
              key={`tag-${t}-${i}`}
              style={{
                fontSize: 13,
                color: '#1677ff',
                marginRight: 8,
              }}
            >
              #{t}
            </Text>
          ))}
        </div>
      )}

      {/* 摘要 */}
      {detail.description && (
        <Section title="摘要" icon={<FileTextOutlined />}>
          <Paragraph
            style={{
              whiteSpace: 'pre-wrap',
              fontSize: 15,
              lineHeight: 1.7,
              marginBottom: 0,
            }}
          >
            {detail.description}
          </Paragraph>
        </Section>
      )}

      {/* 关键词 */}
      {detail.keywords.length > 0 && (
        <Section title="关键词" icon={<SearchOutlined />}>
          <Space size={[6, 6]} wrap>
            {detail.keywords.map((k, i) => (
              <Tag key={`kw-${k}-${i}`} color="blue">
                {k}
              </Tag>
            ))}
          </Space>
        </Section>
      )}

      {/* 来源 */}
      {detail.source && (
        <Section title="来源" icon={<BookOutlined />}>
          <Text type="secondary">{detail.source}</Text>
        </Section>
      )}

      {/* 关联 */}
      <Divider orientation="left" plain style={{ marginTop: 16 }}>
        <Space>
          <LinkOutlined />
          <Text strong>关联（{totalRel}）</Text>
        </Space>
      </Divider>

      {totalRel === 0 ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="暂无关联"
          style={{ margin: '12px 0' }}
        />
      ) : (
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          {groupKeys.map((gk) => {
            const relItems = groups[gk] ?? [];
            const isWarning = Object.entries(RELATION_TYPE_LABEL).some(
              ([k, label]) =>
                label === gk && RELATION_TYPE_WARNING[k],
            );
            return (
              <Card
                key={gk}
                size="small"
                style={{
                  borderRadius: 8,
                  borderLeft: `3px solid ${
                    isWarning ? '#ff4d4f' : '#d9d9d9'
                  }`,
                }}
                styles={{ body: { padding: 12 } }}
              >
                <Text
                  strong
                  style={{
                    display: 'block',
                    marginBottom: 8,
                    fontSize: 14,
                    color: isWarning ? '#ff4d4f' : undefined,
                  }}
                >
                  {isWarning && <WarningOutlined style={{ marginRight: 4 }} />}
                  {gk}（{relItems.length}）
                </Text>
                <Space size={[6, 6]} wrap>
                  {relItems.map((item) => (
                    <Tag
                      key={item.id}
                      color={ENTITY_TYPE_TAG_COLOR[item.type] ?? 'default'}
                      style={{ cursor: 'pointer', margin: 0 }}
                      onClick={() => onNavigate(item.id)}
                    >
                      {item.label}
                    </Tag>
                  ))}
                </Space>
              </Card>
            );
          })}
        </Space>
      )}

      {/* 页脚元信息 */}
      <Divider style={{ margin: '16px 0 12px' }} />
      <Text type="secondary" style={{ fontSize: 12 }}>
        <EyeOutlined style={{ marginRight: 4 }} />
        浏览 {detail.viewCount} 次
        {detail.updatedAt && (
          <>
            {' '}· 更新 {detail.updatedAt.slice(0, 10)}
          </>
        )}
      </Text>
    </div>
  );
}

/** 详情区段（标题 + 内容） */
function Section({
  title,
  icon,
  children,
}: {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <>
      <Divider orientation="left" plain style={{ marginTop: 16 }}>
        <Space>
          {icon}
          <Text strong>{title}</Text>
        </Space>
      </Divider>
      {children}
    </>
  );
}
