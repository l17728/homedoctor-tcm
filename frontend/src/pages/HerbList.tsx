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
  Alert,
  message,
} from 'antd';
import { EyeOutlined, ReloadOutlined } from '@ant-design/icons';
import { getHerbs, type Herb, type PaginatedHerbs } from '../api/herbApi';
import StatusTag from '../components/StatusTag';
import { TOXICITY_COLOR } from '../constants';
import { useIsMobile } from '../hooks/useIsMobile';
import { request } from '../api/client';

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
  const isMobile = useIsMobile();
  const [herbs, setHerbs] = useState<Herb[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState<string | undefined>(undefined);
  const [selectedHerb, setSelectedHerb] = useState<Herb | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20, total: 0 });
  const [aliasDraft, setAliasDraft] = useState('');
  const [aliasSource, setAliasSource] = useState('');
  const [savingAliases, setSavingAliases] = useState(false);
  const isAdmin = (() => {
    try { return JSON.parse(localStorage.getItem('user') || '{}').role === 'admin'; }
    catch { return false; }
  })();

  const loadData = async (params?: { page?: number; pageSize?: number; category?: string; search?: string }) => {
    setLoading(true);
    setLoadError(false);
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
      setLoadError(true);
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
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 16, alignItems: 'center' }}>
        <span>分类</span>
        <Select
          placeholder="全部分类"
          style={{ flex: 1, minWidth: 160 }}
          allowClear
          value={category}
          onChange={handleCategoryChange}
          options={CATEGORIES.map((c) => ({ label: c, value: c }))}
        />
        <Input.Search
          placeholder="搜索"
          allowClear
          style={{ flex: 1, minWidth: 160 }}
          onSearch={handleSearch}
          onChange={(e) => {
            if (!e.target.value) {
              setSearch('');
              loadData({ page: 1, category, search: '' });
            }
          }}
        />
      </div>
      {loading ? (
        <Skeleton active />
      ) : loadError ? (
        <Alert
          type="error"
          showIcon
          message="中药数据加载失败，请检查网络"
          action={
            <Button icon={<ReloadOutlined />} onClick={() => loadData({ page: 1 })}>
              重试
            </Button>
          }
        />
      ) : herbs.length === 0 ? (
        <Empty description="暂无中药数据" />
      ) : (
        <Table
          dataSource={herbs}
          columns={columns}
          rowKey="id"
          size="middle"
          scroll={{ x: 'max-content' }}
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
              setAliasDraft(Array.isArray(record.aliases) ? record.aliases.join('、') : record.aliases || '');
              setAliasSource('');
              setDrawerOpen(true);
            },
            style: { cursor: 'pointer' },
          })}
        />
      )}
      <Drawer
        title={selectedHerb?.name}
        width={isMobile ? '100%' : 480}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        destroyOnClose
      >
        {selectedHerb && (
          <>
          <Descriptions column={1} bordered>
            <Descriptions.Item label="分类">
              {selectedHerb.category}
            </Descriptions.Item>
            <Descriptions.Item label="别名">
              {Array.isArray(selectedHerb.aliases)
                ? selectedHerb.aliases.join('、')
                : selectedHerb.aliases || '建议值：无；来源：没有可核验的别名词典；置信度：无。需人工查证后维护。'}
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
          {isAdmin && (
            <div style={{ marginTop: 16 }}>
              <Alert
                type="info"
                showIcon
                message="别名建议：没有可核验的自动候选"
                description="建议值：无；来源：无已配置的权威别名词典；置信度：无。只保存管理员依据外部权威资料人工核验的别名。"
                style={{ marginBottom: 12 }}
              />
              <Input.TextArea
                aria-label="人工核验的药材别名"
                rows={2}
                value={aliasDraft}
                onChange={(event) => setAliasDraft(event.target.value)}
                placeholder="人工核验后填写，多个别名用顿号或逗号分隔"
              />
              <Input
                aria-label="别名核验来源"
                style={{ marginTop: 8 }}
                value={aliasSource}
                onChange={(event) => setAliasSource(event.target.value)}
                placeholder="来源文献、药典版本或审核记录"
              />
              <Button
                type="primary"
                loading={savingAliases}
                disabled={!aliasSource.trim()}
                style={{ marginTop: 8, minHeight: 44 }}
                onClick={async () => {
                  setSavingAliases(true);
                  try {
                    const aliases = aliasDraft.split(/[、,，]/).map((item) => item.trim()).filter(Boolean);
                    const result = await request<{ aliases: string[] }>(`/api/herbs/${selectedHerb.id}/aliases`, {
                      method: 'PATCH',
                      body: JSON.stringify({ aliases, source: aliasSource, verified: true }),
                    });
                    setSelectedHerb({ ...selectedHerb, aliases: result.aliases });
                    setAliasDraft(result.aliases.join('、'));
                    message.success('已保存人工核验的别名');
                  } catch {
                    message.error('保存失败，请确认管理员权限和来源信息');
                  } finally {
                    setSavingAliases(false);
                  }
                }}
              >
                保存人工核验别名
              </Button>
            </div>
          )}
          </>
        )}
      </Drawer>
    </div>
  );
}
