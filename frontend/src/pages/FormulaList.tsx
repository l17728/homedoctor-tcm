import { useState, useEffect, useMemo } from 'react';
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
import { getFormulas, type Formula } from '../api/formulaApi';

const { Title } = Typography;

const CATEGORIES = [
  '补益剂',
  '解表剂',
  '泻下剂',
  '和解剂',
  '清热剂',
  '祛暑剂',
  '温里剂',
  '表里双解剂',
  '安神剂',
  '开窍剂',
  '固涩剂',
  '理气剂',
  '理血剂',
  '治风剂',
  '治燥剂',
  '祛湿剂',
  '消食剂',
  '祛痰剂',
];

export default function FormulaList() {
  const [formulas, setFormulas] = useState<Formula[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState<string | undefined>(undefined);
  const [selectedFormula, setSelectedFormula] = useState<Formula | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const data = await getFormulas();
        setFormulas(data);
      } catch {
        // handled
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const filteredFormulas = useMemo(() => {
    let result = formulas;
    if (search) {
      result = result.filter(
        (f) => f.name.includes(search) || f.efficacy.includes(search),
      );
    }
    if (category) {
      result = result.filter((f) => f.category === category);
    }
    return result;
  }, [formulas, search, category]);

  const columns = [
    { title: '名称', dataIndex: 'name', key: 'name' },
    { title: '分类', dataIndex: 'category', key: 'category' },
    {
      title: '功效',
      dataIndex: 'efficacy',
      key: 'efficacy',
      ellipsis: true,
    },
    {
      title: '操作',
      key: 'action',
      fixed: 'right' as const,
      width: 100,
      render: (_val: unknown, record: Formula) => (
        <Button
          type="link"
          icon={<EyeOutlined />}
          onClick={(e) => {
            e.stopPropagation();
            setSelectedFormula(record);
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
      <Title level={3}>方剂知识库</Title>
      <Space style={{ marginBottom: 16 }} size="middle">
        <span>分类</span>
        <Select
          placeholder="全部分类"
          style={{ width: 200 }}
          allowClear
          value={category}
          onChange={setCategory}
          options={CATEGORIES.map((c) => ({ label: c, value: c }))}
        />
        <Input.Search
          placeholder="搜索"
          allowClear
          style={{ width: 300 }}
          onSearch={setSearch}
          onChange={(e) => {
            if (!e.target.value) setSearch('');
          }}
        />
      </Space>
      {loading ? (
        <Skeleton active />
      ) : filteredFormulas.length === 0 ? (
        <Empty description="暂无方剂数据" />
      ) : (
        <Table
          dataSource={filteredFormulas}
          columns={columns}
          rowKey="id"
          size="middle"
          pagination={{ pageSize: 20 }}
          onRow={(record) => ({
            onClick: () => {
              setSelectedFormula(record);
              setDrawerOpen(true);
            },
            style: { cursor: 'pointer' },
          })}
        />
      )}
      <Drawer
        title={selectedFormula?.name}
        width={480}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        destroyOnClose
      >
        {selectedFormula && (
          <Descriptions column={1} bordered>
            <Descriptions.Item label="分类">
              {selectedFormula.category}
            </Descriptions.Item>
            <Descriptions.Item label="组成">
              {selectedFormula.composition}
            </Descriptions.Item>
            <Descriptions.Item label="功效">
              {selectedFormula.efficacy}
            </Descriptions.Item>
            <Descriptions.Item label="主治">
              {selectedFormula.indication}
            </Descriptions.Item>
            <Descriptions.Item label="用法">
              {selectedFormula.usage}
            </Descriptions.Item>
            <Descriptions.Item label="描述">
              {selectedFormula.description}
            </Descriptions.Item>
          </Descriptions>
        )}
      </Drawer>
    </div>
  );
}
