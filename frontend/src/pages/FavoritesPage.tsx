import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Table,
  Button,
  Popconfirm,
  Popover,
  message,
  Empty,
  Skeleton,
  Typography,
  Space,
  Tag,
  Select,
  Input,
} from 'antd';
import {
  StarOutlined,
  StarFilled,
  DeleteOutlined,
  BookOutlined,
  TagOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import {
  getFavorites,
  deleteFavorite,
  toggleFavoriteStar,
  updateFavoriteTags,
  type Favorite,
} from '../api/favoriteApi';
import { PAGE_SIZE } from '../constants';

const { Title } = Typography;

const ENTRY_TYPE_LABEL: Record<string, string> = {
  herb: '中药',
  formula: '方剂',
  knowledge_card: '知识卡片',
  medicine: '药品',
};

const ROLE_COLOR: Record<string, string> = {
  君药: 'red',
  臣药: 'orange',
  佐药: 'blue',
  使药: 'green',
};

export default function FavoritesPage() {
  const navigate = useNavigate();
  const [favorites, setFavorites] = useState<Favorite[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterType, setFilterType] = useState<string | undefined>(undefined);
  const [searchTitle, setSearchTitle] = useState('');
  const [filterTag, setFilterTag] = useState<string | undefined>(undefined);

  // --- tag editor state per-row ---
  const [tagDraft, setTagDraft] = useState<Record<string, string>>({});
  const [tagSavingId, setTagSavingId] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const { items } = await getFavorites({
        entry_type: filterType,
        page: 1,
        pageSize: 100,
      });
      setFavorites(items);
    } catch {
      // handled
    } finally {
      setLoading(false);
    }
  }, [filterType]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleDelete = async (id: string) => {
    try {
      await deleteFavorite(id);
      message.success('已删除');
      loadData();
    } catch {
      message.error('删除失败');
    }
  };

  const handleToggleStar = async (id: string, current: boolean) => {
    try {
      await toggleFavoriteStar(id, !current);
      loadData();
    } catch {
      message.error('操作失败');
    }
  };

  // --- tag management ---
  const allTags = useMemo(() => {
    const set = new Set<string>();
    favorites.forEach((f) => f.tags?.forEach((t) => set.add(t)));
    return Array.from(set).sort();
  }, [favorites]);

  const handleAddTag = async (fav: Favorite) => {
    const newTag = (tagDraft[fav.id] ?? '').trim();
    if (!newTag) return;
    if (fav.tags.includes(newTag)) {
      message.warning('该标签已存在');
      return;
    }
    const updated = [...fav.tags, newTag];
    setTagSavingId(fav.id);
    try {
      await updateFavoriteTags(fav.id, updated);
      setFavorites((prev) =>
        prev.map((f) =>
          f.id === fav.id ? { ...f, tags: updated } : f,
        ),
      );
      setTagDraft((prev) => ({ ...prev, [fav.id]: '' }));
    } catch {
      message.error('添加标签失败');
    } finally {
      setTagSavingId(null);
    }
  };

  const handleRemoveTag = async (fav: Favorite, tag: string) => {
    const updated = fav.tags.filter((t) => t !== tag);
    setTagSavingId(fav.id);
    try {
      await updateFavoriteTags(fav.id, updated);
      setFavorites((prev) =>
        prev.map((f) =>
          f.id === fav.id ? { ...f, tags: updated } : f,
        ),
      );
    } catch {
      message.error('删除标签失败');
    } finally {
      setTagSavingId(null);
    }
  };

  const renderTagEditor = (fav: Favorite) => (
    <div style={{ width: 260 }}>
      <div style={{ marginBottom: 8 }}>
        {fav.tags.length > 0 ? (
          <Space size={[4, 4]} wrap>
            {fav.tags.map((t) => (
              <Tag
                key={t}
                color={ROLE_COLOR[t] ?? 'blue'}
                closable
                onClose={(e) => {
                  e.preventDefault();
                  handleRemoveTag(fav, t);
                }}
              >
                {t}
              </Tag>
            ))}
          </Space>
        ) : (
          <span style={{ color: '#666', fontSize: 14 }}>暂无标签</span>
        )}
      </div>
      <Input.Search
        placeholder="输入标签后回车添加"
        size="small"
        enterButton="添加"
        value={tagDraft[fav.id] ?? ''}
        loading={tagSavingId === fav.id}
        onChange={(e) =>
          setTagDraft((prev) => ({ ...prev, [fav.id]: e.target.value }))
        }
        onSearch={() => handleAddTag(fav)}
      />
    </div>
  );

  // --- filtering ---
  const filtered = useMemo(() => {
    let result = favorites;
    if (searchTitle) {
      result = result.filter((f) => f.title.includes(searchTitle));
    }
    if (filterTag) {
      result = result.filter((f) => f.tags?.includes(filterTag));
    }
    return result;
  }, [favorites, searchTitle, filterTag]);

  const columns = [
    {
      title: '收藏',
      key: 'star',
      width: 50,
      render: (_: unknown, r: Favorite) => (
        <Button
          type="text"
          icon={r.is_starred ? <StarFilled style={{ color: '#faad14' }} /> : <StarOutlined />}
          onClick={() => handleToggleStar(r.id, r.is_starred)}
        />
      ),
    },
    {
      title: '类型',
      dataIndex: 'entry_type',
      key: 'entry_type',
      width: 100,
      render: (t: string) => (
        <Tag>{ENTRY_TYPE_LABEL[t] ?? t}</Tag>
      ),
    },
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      render: (title: string, r: Favorite) => {
        if (r.source_type === 'herb' && r.source_url) {
          return (
            <Button type="link" onClick={() => navigate(`/herbs/${r.source_url}`)}>
              {title}
            </Button>
          );
        }
        if (r.source_type === 'formula' && r.source_url) {
          return (
            <Button type="link" onClick={() => navigate(`/formulas/${r.source_url}`)}>
              {title}
            </Button>
          );
        }
        return <span>{title}</span>;
      },
    },
    {
      title: '摘要',
      dataIndex: 'summary',
      key: 'summary',
      ellipsis: true,
      render: (s: string | null) => s ?? '—',
    },
    {
      title: '标签',
      dataIndex: 'tags',
      key: 'tags',
      render: (tags: string[]) =>
        tags.length > 0 ? (
          <Space size={4} wrap>
            {tags.map((t) => (
              <Tag
                key={t}
                color={ROLE_COLOR[t] ?? undefined}
                style={{ cursor: 'pointer' }}
                onClick={() => setFilterTag(t)}
              >
                {t}
              </Tag>
            ))}
          </Space>
        ) : (
          <span style={{ color: '#666' }}>—</span>
        ),
    },
    {
      title: '操作',
      key: 'action',
      fixed: 'right' as const,
      width: 160,
      render: (_: unknown, r: Favorite) => (
        <Space size={0}>
          <Popover
            title="编辑标签"
            trigger="click"
            placement="left"
            content={renderTagEditor(r)}
          >
            <Button type="link" icon={<TagOutlined />}>
              标签
            </Button>
          </Popover>
          <Popconfirm
            title="确定删除该收藏吗？"
            onConfirm={() => handleDelete(r.id)}
            okText="确定"
            cancelText="取消"
          >
            <Button type="link" danger icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 16,
        }}
      >
        <Title level={3} style={{ margin: 0 }}>
          <BookOutlined style={{ marginRight: 8 }} />
          我的收藏
        </Title>
      </div>

      <Space style={{ marginBottom: 16 }} wrap>
        <Select
          allowClear
          placeholder="筛选类型"
          style={{ width: 150 }}
          value={filterType}
          onChange={(v) => setFilterType(v)}
          options={[
            { label: '中药', value: 'herb' },
            { label: '方剂', value: 'formula' },
            { label: '知识卡片', value: 'knowledge_card' },
          ]}
        />
        <Select
          allowClear
          placeholder="全部标签"
          style={{ width: 150 }}
          value={filterTag}
          onChange={(v) => setFilterTag(v)}
          options={allTags.map((t) => ({ label: t, value: t }))}
          tagRender={(props) => (
            <Tag color={ROLE_COLOR[props.value] ?? 'blue'} style={{ margin: 0 }}>
              {props.label}
            </Tag>
          )}
        />
        <Input.Search
          placeholder="搜索标题"
          allowClear
          style={{ width: 200 }}
          onSearch={setSearchTitle}
        />
      </Space>

      {loading ? (
        <Skeleton active />
      ) : filtered.length === 0 ? (
        <Empty description="暂无收藏，去浏览中药和方剂吧" />
      ) : (
        <Table
          dataSource={filtered}
          columns={columns}
          rowKey="id"
          size="middle"
          scroll={{ x: 'max-content' }}
          pagination={{ pageSize: PAGE_SIZE, showSizeChanger: false }}
        />
      )}
    </div>
  );
}
