import { useState, useEffect, useCallback } from 'react';
import {
  Table,
  Button,
  Popconfirm,
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
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import {
  getFavorites,
  deleteFavorite,
  toggleFavoriteStar,
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

  const filtered = searchTitle
    ? favorites.filter((f) => f.title.includes(searchTitle))
    : favorites;

  const columns = [
    {
      title: '收藏',
      key: 'star',
      width: 50,
      render: (_: unknown, r: Favorite) => (
        <Button
          type="text"
          size="small"
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
              <Tag key={t} color={ROLE_COLOR[t] ?? undefined}>{t}</Tag>
            ))}
          </Space>
        ) : (
          '—'
        ),
    },
    {
      title: '操作',
      key: 'action',
      fixed: 'right' as const,
      width: 80,
      render: (_: unknown, r: Favorite) => (
        <Popconfirm
          title="确定删除该收藏吗？"
          onConfirm={() => handleDelete(r.id)}
          okText="确定"
          cancelText="取消"
        >
          <Button type="link" size="small" danger icon={<DeleteOutlined />}>
            删除
          </Button>
        </Popconfirm>
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

      <Space style={{ marginBottom: 16 }}>
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
          pagination={{ pageSize: PAGE_SIZE, showSizeChanger: false }}
        />
      )}
    </div>
  );
}
