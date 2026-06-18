import { useState, useEffect, useRef } from 'react';
import {
  Table,
  Button,
  Drawer,
  Form,
  Input,
  Select,
  InputNumber,
  DatePicker,
  Popconfirm,
  message,
  Empty,
  Skeleton,
  Typography,
  Space,
  Tag,
  Alert,
  Spin,
} from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  CameraOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import {
  getMedicines,
  createMedicine,
  updateMedicine,
  deleteMedicine,
  recognizeMedicineImage,
  type Medicine,
  type PaginatedMedicines,
  type OcrRecognitionResult,
} from '../api/medicineApi';
import { PAGE_SIZE, DRUG_STATUS_COLOR } from '../constants';
import StatusTag from '../components/StatusTag';
import { useIsMobile } from '../hooks/useIsMobile';

const { Title } = Typography;

const MEDICINE_TYPES = ['西药', '中成药', '中药饮片', '保健品'];
const MEDICINE_STATUS = ['充足', '低库存', '已过期'];

interface FormValues {
  name: string;
  type: string;
  status?: string;
  dosage?: string;
  notes?: string;
  quantity?: number;
  expiry_date?: dayjs.Dayjs;
}

export default function MedicineList() {
  const isMobile = useIsMobile();
  const [medicines, setMedicines] = useState<Medicine[]>([]);
  const [loading, setLoading] = useState(true);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editingMedicine, setEditingMedicine] = useState<Medicine | null>(
    null,
  );
  const [form] = Form.useForm<FormValues>();
  const [pagination, setPagination] = useState({ current: 1, pageSize: PAGE_SIZE, total: 0 });
  const [ocrLoading, setOcrLoading] = useState(false);
  const [lowConfidenceFields, setLowConfidenceFields] = useState<Set<string>>(new Set());
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadMedicines = async (page?: number) => {
    setLoading(true);
    try {
      const data: PaginatedMedicines = await getMedicines({
        page: page ?? pagination.current,
        pageSize: pagination.pageSize,
      });
      setMedicines(data.items);
      setPagination({
        current: data.page,
        pageSize: data.pageSize,
        total: data.total,
      });
    } catch {
      // handled
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadMedicines(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleAdd = () => {
    setEditingMedicine(null);
    setLowConfidenceFields(new Set());
    form.resetFields();
    setDrawerOpen(true);
  };

  const handlePhotoAdd = () => {
    fileInputRef.current?.click();
  };

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = '';

    setOcrLoading(true);
    try {
      const result: OcrRecognitionResult = await recognizeMedicineImage(file);

      setEditingMedicine(null);
      setLowConfidenceFields(new Set());
      form.resetFields();

      const lowFields = new Set<string>();

      if (result.name) {
        form.setFieldValue('name', result.name);
        if (result.confidence === 'low') lowFields.add('name');
      }
      if (result.dosage_instructions) {
        form.setFieldValue('dosage', result.dosage_instructions);
        if (result.confidence === 'low') lowFields.add('dosage');
      }
      if (result.specification || result.raw_text) {
        const noteParts: string[] = [];
        if (result.specification) noteParts.push(`规格：${result.specification}`);
        if (result.raw_text) noteParts.push(`OCR识别原文：\n${result.raw_text.substring(0, 200)}`);
        form.setFieldValue('notes', noteParts.join('\n'));
      }

      setLowConfidenceFields(lowFields);
      setDrawerOpen(true);

      if (result.confidence === 'high') {
        message.success('识别成功，请确认信息后保存');
      } else if (result.confidence === 'medium') {
        message.warning('部分识别，请核实标黄字段');
      } else {
        message.warning('识别置信度较低，请仔细核实');
      }
    } catch {
      message.error('识别失败，请重试或手动添加');
    } finally {
      setOcrLoading(false);
    }
  };

  const handleEdit = (record: Medicine) => {
    setEditingMedicine(record);
    setLowConfidenceFields(new Set());
    form.setFieldsValue({
      name: record.name,
      type: record.type,
      status: record.status,
      dosage: record.dosage,
      notes: record.notes,
      quantity: record.quantity,
      expiry_date: record.expiry_date ? dayjs(record.expiry_date) : undefined,
    });
    setDrawerOpen(true);
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      if (editingMedicine) {
        await updateMedicine(editingMedicine.id, {
          ...values,
          expiry_date: values.expiry_date?.format('YYYY-MM-DD'),
        });
        message.success('更新成功');
      } else {
        await createMedicine({
          ...values,
          expiry_date: values.expiry_date?.format('YYYY-MM-DD'),
        });
        message.success('添加成功');
      }
      setDrawerOpen(false);
      loadMedicines(pagination.current);
    } catch (err) {
      // validation error or API error
      if (err instanceof Error && err.message.includes('未授权')) {
        message.error('登录已过期，请重新登录');
      }
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteMedicine(id);
      message.success('删除成功');
      loadMedicines(pagination.current);
    } catch (err) {
      if (err instanceof Error && err.message.includes('未授权')) {
        message.error('登录已过期，请重新登录');
      } else {
        message.error('删除失败');
      }
    }
  };

  const columns = [
    { title: '名称', dataIndex: 'name', key: 'name' },
    { title: '类型', dataIndex: 'type', key: 'type' },
    {
      title: '数量',
      dataIndex: 'quantity',
      key: 'quantity',
      width: 80,
      render: (qty: number | undefined) => {
        if (qty == null) return '—';
        return (
          <Tag color={qty <= 5 ? 'orange' : 'green'}>
            {qty <= 5 ? `低库存 ${qty}` : qty}
          </Tag>
        );
      },
    },
    {
      title: '过期日期',
      dataIndex: 'expiry_date',
      key: 'expiry_date',
      width: 130,
      render: (date: string | undefined) => {
        if (!date) return '—';
        const daysLeft = dayjs(date).diff(dayjs(), 'day');
        if (daysLeft < 0) return <Tag color="red">已过期</Tag>;
        if (daysLeft <= 30) return <Tag color="orange">{daysLeft}天后过期</Tag>;
        return <span>{date}</span>;
      },
    },
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
        <Space>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/jpeg,image/png,image/webp,image/bmp"
            style={{ display: 'none' }}
            onChange={handleFileSelect}
          />
          <Button
            icon={<CameraOutlined />}
            onClick={handlePhotoAdd}
            loading={ocrLoading}
          >
            拍照添加
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
            添加
          </Button>
        </Space>
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
          scroll={{ x: 'max-content' }}
          pagination={{
            current: pagination.current,
            pageSize: pagination.pageSize,
            total: pagination.total,
            showSizeChanger: false,
          }}
          onChange={(pag) => loadMedicines(pag.current)}
        />
      )}
      <Drawer
        title={editingMedicine ? '编辑药品' : '添加药品'}
        width={isMobile ? '100%' : 480}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        destroyOnClose
        extra={
          <Button type="primary" onClick={handleSubmit}>
            提交
          </Button>
        }
      >
        {ocrLoading && (
          <div style={{ textAlign: 'center', padding: '40px 0' }}>
            <Spin tip="正在识别药品信息..." />
          </div>
        )}
        {!ocrLoading && lowConfidenceFields.size > 0 && (
          <Alert
            type="warning"
            message="以下字段识别置信度较低，请核实标黄字段"
            showIcon
            style={{ marginBottom: 16 }}
          />
        )}
        <Form form={form} layout="vertical">
          <Form.Item
            label="药品名称"
            name="name"
            rules={[{ required: true, message: '请输入药品名称' }]}
          >
            <Input
              style={
                lowConfidenceFields.has('name')
                  ? { backgroundColor: '#fffbe6', borderColor: '#ffe58f' }
                  : undefined
              }
            />
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
            <Input
              placeholder="如：每次1片，每日3次"
              style={
                lowConfidenceFields.has('dosage')
                  ? { backgroundColor: '#fffbe6', borderColor: '#ffe58f' }
                  : undefined
              }
            />
          </Form.Item>
          <Form.Item label="库存数量" name="quantity">
            <InputNumber min={0} placeholder="如：30" style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item label="过期日期" name="expiry_date">
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item label="备注" name="notes">
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Drawer>
    </div>
  );
}
