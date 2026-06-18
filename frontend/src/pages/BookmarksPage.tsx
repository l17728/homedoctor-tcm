import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Table,
  Button,
  Popconfirm,
  Modal,
  Form,
  Input,
  Select,
  message,
  Empty,
  Skeleton,
  Typography,
  Space,
  Tag,
  Card,
  Tooltip,
} from 'antd';
import {
  StarOutlined,
  StarFilled,
  DeleteOutlined,
  BookOutlined,
  FolderAddOutlined,
  AppstoreOutlined,
} from '@ant-design/icons';
import {
  getBookmarks,
  deleteBookmark,
  updateBookmark,
  getCollections,
  createCollection,
  type Bookmark,
  type BookmarkCollection,
  type BookmarkType,
  BOOKMARK_TYPE_LABEL,
  BOOKMARK_TYPE_COLOR,
} from '../api/bookmarkApi';
import { PAGE_SIZE } from '../constants';

const { Title, Text } = Typography;

const TYPE_OPTIONS = (Object.keys(BOOKMARK_TYPE_LABEL) as BookmarkType[]).map((t) => ({
  label: BOOKMARK_TYPE_LABEL[t],
  value: t,
}));

const SOURCE_LABEL: Record<string, string> = {
  chat: 'AI对话',
  herb_detail: '中药详情',
  formula_detail: '方剂详情',
  therapy_detail: '理疗详情',
  search: '搜索',
  manual: '手动',
  comparison: '对比',
};

export default function BookmarksPage() {
  const [bookmarks, setBookmarks] = useState<Bookmark[]>([]);
  const [collections, setCollections] = useState<BookmarkCollection[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterType, setFilterType] = useState<BookmarkType | undefined>(undefined);
  const [filterStarred, setFilterStarred] = useState<boolean | undefined>(undefined);
  const [filterTags, setFilterTags] = useState<string[]>([]);
  const [collectionModalOpen, setCollectionModalOpen] = useState(false);
  const [creatingCollection, setCreatingCollection] = useState(false);
  const [collectionForm] = Form.useForm<{ title: string; tags?: string[] }>();

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [bm, cols] = await Promise.all([
        getBookmarks({
          entry_type: filterType,
          is_starred: filterStarred,
          tags: filterTags.length > 0 ? filterTags : undefined,
          tag_logic: 'OR',
        }),
        getCollections(),
      ]);
      setBookmarks(bm.items);
      setCollections(cols.items);
    } catch {
      // handled by 401 redirect in client
    } finally {
      setLoading(false);
    }
  }, [filterType, filterStarred, filterTags]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleDelete = async (id: string) => {
    try {
      await deleteBookmark(id);
      message.success('已删除');
      loadData();
    } catch {
      message.error('删除失败');
    }
  };

  const handleToggleStar = async (id: string, current: boolean) => {
    try {
      await updateBookmark(id, { is_starred: !current });
      setBookmarks((prev) =>
        prev.map((b) => (b.id === id ? { ...b, is_starred: !current } : b)),
      );
    } catch {
      message.error('操作失败');
    }
  };

  const handleCreateCollection = async () => {
    try {
      const values = await collectionForm.validateFields();
      setCreatingCollection(true);
      await createCollection({ title: values.title, tags: values.tags });
      message.success('合集已创建');
      setCollectionModalOpen(false);
      collectionForm.resetFields();
      loadData();
    } catch {
      // validation or network error
    } finally {
      setCreatingCollection(false);
    }
  };

  const allTags = useMemo(() => {
    const set = new Set<string>();
    bookmarks.forEach((b) => b.tags.forEach((t) => set.add(t)));
    return Array.from(set).sort();
  }, [bookmarks]);

  const columns = [
    {
      title: '类型',
      dataIndex: 'entry_type',
      key: 'entry_type',
      width: 110,
      render: (t: BookmarkType) => (
        <Tag color={BOOKMARK_TYPE_COLOR[t] ?? 'default'}>
          {BOOKMARK_TYPE_LABEL[t] ?? t}
        </Tag>
      ),
    },
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      ellipsis: true,
      render: (title: string, r: Bookmark) =>
        r.source_url && r.entry_type === 'external' ? (
          <a href={r.source_url} target="_blank" rel="noopener noreferrer">
            {title}
          </a>
        ) : (
          <span>{title}</span>
        ),
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
                style={{ cursor: 'pointer' }}
                onClick={() => {
                  if (!filterTags.includes(t)) setFilterTags((prev) => [...prev, t]);
                }}
              >
                {t}
              </Tag>
            ))}
          </Space>
        ) : (
          <Text type="secondary">—</Text>
        ),
    },
    {
      title: '来源',
      dataIndex: 'source_type',
      key: 'source_type',
      width: 110,
      render: (s: string | null) =>
        s ? <Tag>{SOURCE_LABEL[s] ?? s}</Tag> : <Text type="secondary">—</Text>,
    },
    {
      title: '星标',
      dataIndex: 'is_starred',
      key: 'is_starred',
      width: 60,
      render: (starred: boolean, r: Bookmark) => (
        <Tooltip title={starred ? '取消星标' : '加星标'}>
          <Button
            type="text"
            size="small"
            icon={
              starred ? <StarFilled style={{ color: '#faad14' }} /> : <StarOutlined />
            }
            onClick={() => handleToggleStar(r.id, starred)}
          />
        </Tooltip>
      ),
    },
    {
      title: '收藏时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 170,
      render: (t: string) => t || '—',
    },
    {
      title: '操作',
      key: 'action',
      fixed: 'right' as const,
      width: 90,
      render: (_: unknown, r: Bookmark) => (
        <Popconfirm
          title="确定删除该书签吗？"
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
          我的书签
        </Title>
        <Button
          type="primary"
          icon={<FolderAddOutlined />}
          onClick={() => setCollectionModalOpen(true)}
        >
          新建合集
        </Button>
      </div>

      {collections.length > 0 && (
        <Card size="small" style={{ marginBottom: 16 }} bodyStyle={{ padding: 12 }}>
          <Text type="secondary" style={{ marginRight: 8 }}>
            <AppstoreOutlined /> 合集
          </Text>
          <Space size={[8, 8]} wrap>
            {collections.map((c) => (
              <Tag key={c.id} color="geekblue" style={{ padding: '2px 8px' }}>
                {c.title}（{c.member_count}）
              </Tag>
            ))}
          </Space>
        </Card>
      )}

      <Space style={{ marginBottom: 16 }} wrap>
        <Select
          allowClear
          placeholder="筛选类型"
          style={{ width: 150 }}
          value={filterType}
          onChange={(v) => setFilterType(v)}
          options={TYPE_OPTIONS}
        />
        <Select
          allowClear
          placeholder="星标"
          style={{ width: 120 }}
          value={filterStarred}
          onChange={(v) => setFilterStarred(v)}
          options={[
            { label: '仅星标', value: true },
            { label: '非星标', value: false },
          ]}
        />
        <Select
          mode="multiple"
          allowClear
          placeholder="筛选标签（任一匹配）"
          style={{ minWidth: 220 }}
          value={filterTags}
          onChange={(v) => setFilterTags(v)}
          options={allTags.map((t) => ({ label: t, value: t }))}
          maxTagCount="responsive"
        />
      </Space>

      {loading ? (
        <Skeleton active />
      ) : bookmarks.length === 0 ? (
        <Empty description="暂无书签，去浏览中药、方剂和知识吧" />
      ) : (
        <Table
          dataSource={bookmarks}
          columns={columns}
          rowKey="id"
          size="middle"
          pagination={{ pageSize: PAGE_SIZE, showSizeChanger: false }}
        />
      )}

      <Modal
        title="新建合集"
        open={collectionModalOpen}
        onCancel={() => setCollectionModalOpen(false)}
        onOk={handleCreateCollection}
        confirmLoading={creatingCollection}
        okText="创建"
        cancelText="取消"
        destroyOnClose
        maskClosable={false}
      >
        <Form form={collectionForm} layout="vertical">
          <Form.Item
            label="合集名称"
            name="title"
            rules={[{ required: true, message: '请输入合集名称' }]}
          >
            <Input placeholder="如：补气类中药、常用方剂" />
          </Form.Item>
          <Form.Item label="标签" name="tags">
            <Select mode="tags" placeholder="输入标签后回车" tokenSeparators={[',']} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
