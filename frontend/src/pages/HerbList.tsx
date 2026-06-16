import { useState, useEffect } from 'react';
import {
  Table,
  Input,
  Select,
  Button,
  Drawer,
  Descriptions,
  Empty,
  Skeleton,
  Typography,
  Space,
} from 'antd';
import { EyeOutlined } from '@ant-design/icons';
import { getHerbs, type Herb, type PaginatedHerbs } from '../api/herbApi';
import StatusTag from '../components/StatusTag';
import { TOXICITY_COLOR } from '../constants';

const { Title } = Typography;

const CATEGORIES = [
  '补虚药',
  '解表药',
  '清热药',
  '泻下药',
  '祛风湿药',
  '化湿药',
  '利水渗湿药',
  '温里药',
  '理气药',
  '消食药',
  '止血药',
  '活血化瘀药',
  '化痰止咳平喘药',
  '安神药',
  '平肝熄风药',
  '开窍药',
  '收涩药',
  '攻毒杀虫止痒药',
  '拔毒化腐生肌药',
  '涌吐药',
];

export default function HerbList() {
  const [herbs, setHerbs] = useState<Herb[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState<string | undefined>(undefined);
  const [selectedHerb, setSelectedHerb] = useState<Herb | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20, total: 0 });

  const loadData = async (params?: { page?: number; pageSize?: number; category?: string; search?: string }) => {
    setLoading(true);
    try {
      const data: PaginatedHerbs = await getHerbs({
        page: params?.page ?? pagination.current,
        pageSize: params?.pageSize ?? pagination.pageSize,
        category: params?.category ?? category,
        search: params?.search ?? search,
      });
      setHerbs(data.items);
      setPagination({
        current: data.page,
        pageSize: data.pageSize,
        total: data.total,
      });
    } catch {
      // error handled by api client
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData({ page: 1 });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleCategoryChange = (value: string | undefined) => {
    setCategory(value);
    loadData({ page: 1, category: value, search });
  };

  const handleSearch = (value: string) => {
    setSearch(value);
    loadData({ page: 1, category, search: value });
  };

  const handleTableChange = (pag: { current?: number; pageSize?: number }) => {
    loadData({
      page: pag.current ?? 1,
      pageSize: pag.pageSize ?? 20,
      category,
      search,
    });
  };

  const columns = [
    { title: '名称', dataIndex: 'name', key: 'name' },
    { title: '分类', dataIndex: 'category', key: 'category' },
    {
      title: '性味',
      key: 'nature',
      render: (_val: unknown, record: Herb) =>
        `${record.nature}，${record.flavor}`,
    },
    { title: '功效', dataIndex: 'efficacy', key: 'efficacy', ellipsis: true },
    {
      title: '操作',
      key: 'action',
      fixed: 'right' as const,
      width: 100,
      render: (_val: unknown, record: Herb) => (
        <Button
          type="link"
          icon={<EyeOutlined />}
          onClick={(e) => {
            e.stopPropagation();
            setSelectedHerb(record);
            setDrawerOpen(true);
          }}
        >
          详情
        </Button>
      ),
    },
  ];

  return (
    <div>
      <Title level={3}>中药知识库</Title>
      <Space style={{ marginBottom: 16 }} size="middle">
        <span>分类</span>
        <Select
          placeholder="全部分类"
          style={{ width: 200 }}
          allowClear
          value={category}
          onChange={handleCategoryChange}
          options={CATEGORIES.map((c) => ({ label: c, value: c }))}
        />
        <Input.Search
          placeholder="搜索"
          allowClear
          style={{ width: 300 }}
          onSearch={handleSearch}
          onChange={(e) => {
            if (!e.target.value) {
              setSearch('');
              loadData({ page: 1, category, search: '' });
            }
          }}
        />
      </Space>
      {loading ? (
        <Skeleton active />
      ) : herbs.length === 0 ? (
        <Empty description="暂无中药数据" />
      ) : (
        <Table
          dataSource={herbs}
          columns={columns}
          rowKey="id"
          size="middle"
          pagination={{
            current: pagination.current,
            pageSize: pagination.pageSize,
            total: pagination.total,
            showSizeChanger: false,
          }}
          onChange={(pag) =>
            handleTableChange({ current: pag.current, pageSize: pag.pageSize })
          }
          onRow={(record) => ({
            onClick: () => {
              setSelectedHerb(record);
              setDrawerOpen(true);
            },
            style: { cursor: 'pointer' },
          })}
        />
      )}
      <Drawer
        title={selectedHerb?.name}
        width={480}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        destroyOnClose
      >
        {selectedHerb && (
          <Descriptions column={1} bordered>
            <Descriptions.Item label="分类">
              {selectedHerb.category}
            </Descriptions.Item>
            <Descriptions.Item label="性味">
              {selectedHerb.nature}，{selectedHerb.flavor}
            </Descriptions.Item>
            <Descriptions.Item label="归经">
              {selectedHerb.meridian}
            </Descriptions.Item>
            <Descriptions.Item label="功效">
              {selectedHerb.efficacy}
            </Descriptions.Item>
            <Descriptions.Item label="毒性">
              <StatusTag
                status={selectedHerb.toxicity}
                colorMap={TOXICITY_COLOR}
              />
            </Descriptions.Item>
            <Descriptions.Item label="用量">
              {selectedHerb.dosage}
            </Descriptions.Item>
            <Descriptions.Item label="禁忌">
              {selectedHerb.contraindications}
            </Descriptions.Item>
            <Descriptions.Item label="描述">
              {selectedHerb.description}
            </Descriptions.Item>
          </Descriptions>
        )}
      </Drawer>
    </div>
  );
}
