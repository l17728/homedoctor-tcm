import { useState, useEffect, useCallback } from 'react';
import type { ColumnsType } from 'antd/es/table';
import {
  Table,
  Button,
  Drawer,
  Form,
  Input,
  Select,
  DatePicker,
  Popconfirm,
  message,
  Empty,
  Skeleton,
  Typography,
  Space,
} from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import {
  getFamilyMembers,
  createFamilyMember,
  updateFamilyMember,
  deleteFamilyMember,
  type FamilyMember,
  type FamilyMemberCreate,
} from '../api/familyMemberApi';

const { Title } = Typography;

const RELATION_OPTIONS = [
  { label: '父亲', value: '父亲' },
  { label: '母亲', value: '母亲' },
  { label: '配偶', value: '配偶' },
  { label: '儿子', value: '儿子' },
  { label: '女儿', value: '女儿' },
  { label: '自己', value: '自己' },
  { label: '其他', value: '其他' },
];

const GENDER_OPTIONS = [
  { label: '男', value: '男' },
  { label: '女', value: '女' },
];

interface FormValues {
  name: string;
  relation: string;
  gender?: string;
  birthDate?: dayjs.Dayjs;
}

export default function FamilyMembersPage() {
  const [members, setMembers] = useState<FamilyMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editing, setEditing] = useState<FamilyMember | null>(null);
  const [form] = Form.useForm<FormValues>();

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const list = await getFamilyMembers();
      setMembers(list);
    } catch {
      // handled
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleAdd = () => {
    setEditing(null);
    form.resetFields();
    setDrawerOpen(true);
  };

  const handleEdit = (record: FamilyMember) => {
    setEditing(record);
    form.setFieldsValue({
      name: record.name ?? '',
      relation: record.relation ?? undefined,
      gender: record.gender ?? undefined,
      birthDate: record.date_of_birth ? dayjs(record.date_of_birth) : undefined,
    });
    setDrawerOpen(true);
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      const payload: FamilyMemberCreate = {
        name: values.name,
        relation: values.relation,
        birth_date: values.birthDate ? values.birthDate.format('YYYY-MM-DD') : null,
        gender: values.gender ?? null,
      };

      if (editing) {
        await updateFamilyMember(editing.id, payload);
        message.success('更新成功');
      } else {
        await createFamilyMember(payload);
        message.success('添加成功');
      }
      setDrawerOpen(false);
      loadData();
    } catch {
      // validation error
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteFamilyMember(id);
      message.success('删除成功');
      loadData();
    } catch {
      message.error('删除失败');
    }
  };

  const columns: ColumnsType<FamilyMember> = [
    { title: '姓名', dataIndex: 'name', key: 'name', ellipsis: true },
    { title: '关系', dataIndex: 'relation', key: 'relation' },
    { title: '性别', dataIndex: 'gender', key: 'gender' },
    { title: '出生日期', dataIndex: 'date_of_birth', key: 'date_of_birth' },
    {
      title: '操作',
      key: 'action',
      fixed: 'right',
      width: 160,
      render: (_: unknown, r: FamilyMember) => (
        <Space>
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => handleEdit(r)}>
            编辑
          </Button>
          <Popconfirm title="确定删除该成员吗？" onConfirm={() => handleDelete(r.id)} okText="确定" cancelText="取消">
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
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0 }}>家庭成员</Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
          添加成员
        </Button>
      </div>

      {loading ? (
        <Skeleton active />
      ) : members.length === 0 ? (
        <Empty description="暂无成员，点击添加" />
      ) : (
        <Table
          dataSource={members}
          columns={columns}
          rowKey="id"
          size="middle"
          pagination={{ pageSize: 20 }}
        />
      )}

      <Drawer
        title={editing ? '编辑成员' : '添加成员'}
        width={480}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        destroyOnClose
        maskClosable={false}
        extra={
          <Button type="primary" onClick={handleSubmit}>
            提交
          </Button>
        }
      >
        <Form form={form} layout="vertical">
          <Form.Item label="姓名" name="name" rules={[{ required: true, message: '请输入姓名' }]}>
            <Input placeholder="请输入姓名" />
          </Form.Item>
          <Form.Item label="关系" name="relation" rules={[{ required: true, message: '请选择关系' }]}>
            <Select options={RELATION_OPTIONS} placeholder="请选择关系" />
          </Form.Item>
          <Form.Item label="性别" name="gender">
            <Select options={GENDER_OPTIONS} placeholder="请选择性别" allowClear />
          </Form.Item>
          <Form.Item label="出生日期" name="birthDate">
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Drawer>
    </div>
  );
}
