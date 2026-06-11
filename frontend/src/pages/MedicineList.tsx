import { useState, useEffect } from 'react';
import {
  Table,
  Button,
  Drawer,
  Form,
  Input,
  Select,
  Popconfirm,
  message,
  Empty,
  Skeleton,
  Typography,
  Space,
} from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import {
  getMedicines,
  createMedicine,
  updateMedicine,
  deleteMedicine,
  type Medicine,
} from '../api/medicineApi';
import { PAGE_SIZE, DRUG_STATUS_COLOR } from '../constants';
import StatusTag from '../components/StatusTag';

const { Title } = Typography;

const MEDICINE_TYPES = ['西药', '中成药', '中药饮片', '保健品'];
const MEDICINE_STATUS = ['充足', '低库存', '已过期'];

interface FormValues {
  name: string;
  type: string;
  status?: string;
  dosage?: string;
  notes?: string;
}

export default function MedicineList() {
  const [medicines, setMedicines] = useState<Medicine[]>([]);
  const [loading, setLoading] = useState(true);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editingMedicine, setEditingMedicine] = useState<Medicine | null>(
    null,
  );
  const [form] = Form.useForm<FormValues>();

  useEffect(() => {
    loadMedicines();
  }, []);

  const loadMedicines = async () => {
    setLoading(true);
    try {
      const data = await getMedicines();
      setMedicines(data);
    } catch {
      // handled
    } finally {
      setLoading(false);
    }
  };

  const handleAdd = () => {
    setEditingMedicine(null);
    form.resetFields();
    setDrawerOpen(true);
  };

  const handleEdit = (record: Medicine) => {
    setEditingMedicine(record);
    form.setFieldsValue({
      name: record.name,
      type: record.type,
      status: record.status,
      dosage: record.dosage,
      notes: record.notes,
    });
    setDrawerOpen(true);
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      if (editingMedicine) {
        await updateMedicine(editingMedicine.id, values);
        message.success('更新成功');
      } else {
        await createMedicine(values);
        message.success('添加成功');
      }
      setDrawerOpen(false);
      loadMedicines();
    } catch {
      // validation error or API error
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteMedicine(id);
      message.success('删除成功');
      loadMedicines();
    } catch {
      message.error('删除失败');
    }
  };

  const columns = [
    { title: '名称', dataIndex: 'name', key: 'name' },
    { title: '类型', dataIndex: 'type', key: 'type' },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => (
        <StatusTag status={status} colorMap={DRUG_STATUS_COLOR} />
      ),
    },
    {
      title: '操作',
      key: 'action',
      fixed: 'right' as const,
      width: 160,
      render: (_val: unknown, record: Medicine) => (
        <Space>
          <Button
            type="link"
            size="small"
            icon={<EditOutlined />}
            onClick={() => handleEdit(record)}
          >
            编辑
          </Button>
          <Popconfirm
            title="确定删除该药品吗？"
            onConfirm={() => handleDelete(record.id)}
            okText="确定"
            cancelText="取消"
          >
            <Button type="link" size="small" danger icon={<DeleteOutlined />}>
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
          药箱管理
        </Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
          添加
        </Button>
      </div>
      {loading ? (
        <Skeleton active />
      ) : medicines.length === 0 ? (
        <Empty description="暂无药品，点击添加" />
      ) : (
        <Table
          dataSource={medicines}
          columns={columns}
          rowKey="id"
          size="middle"
          pagination={{ pageSize: PAGE_SIZE }}
        />
      )}
      <Drawer
        title={editingMedicine ? '编辑药品' : '添加药品'}
        width={480}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        destroyOnClose
        extra={
          <Button type="primary" onClick={handleSubmit}>
            提交
          </Button>
        }
      >
        <Form form={form} layout="vertical">
          <Form.Item
            label="药品名称"
            name="name"
            rules={[{ required: true, message: '请输入药品名称' }]}
          >
            <Input />
          </Form.Item>
          <Form.Item
            label="类型"
            name="type"
            rules={[{ required: true, message: '请选择类型' }]}
          >
            <Select
              options={MEDICINE_TYPES.map((t) => ({ label: t, value: t }))}
              placeholder="请选择类型"
            />
          </Form.Item>
          <Form.Item label="状态" name="status">
            <Select
              allowClear
              options={MEDICINE_STATUS.map((s) => ({ label: s, value: s }))}
              placeholder="请选择状态"
            />
          </Form.Item>
          <Form.Item label="用量" name="dosage">
            <Input placeholder="如：每次1片，每日3次" />
          </Form.Item>
          <Form.Item label="备注" name="notes">
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Drawer>
    </div>
  );
}
