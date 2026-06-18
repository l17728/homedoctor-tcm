import { useState, useEffect, useCallback } from 'react';
import {
  Card,
  Row,
  Col,
  Button,
  Modal,
  Form,
  Input,
  Select,
  Tag,
  Typography,
  Skeleton,
  Empty,
  Space,
  Table,
  Popconfirm,
  message,
  Tooltip,
} from 'antd';
import {
  PlusOutlined,
  DeleteOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  MedicineBoxOutlined,
  MinusCircleOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons';
import {
  getMedicationPlans,
  createMedicationPlan,
  deleteMedicationPlan,
  pausePlan,
  resumePlan,
  type MedicationPlan,
  type PlanItem,
  type PlanStatus,
} from '../api/medicationPlanApi';

const { Title, Text, Paragraph } = Typography;

/** 套餐状态色与文案 */
const STATUS_COLOR: Record<PlanStatus, string> = {
  active: 'green',
  paused: 'orange',
  completed: 'blue',
};

const STATUS_LABEL: Record<PlanStatus, string> = {
  active: '进行中',
  paused: '已暂停',
  completed: '已完成',
};

const FREQUENCY_OPTIONS = [
  { label: '每日', value: 'daily' },
  { label: '隔日', value: 'every-other-day' },
  { label: '每周', value: 'weekly' },
  { label: '按需', value: 'as-needed' },
];

const FREQUENCY_LABEL: Record<string, string> = {
  daily: '每日',
  'every-other-day': '隔日',
  weekly: '每周',
  'as-needed': '按需',
};

interface ItemFormValues {
  medicineName: string;
  dosage?: string;
  frequency?: string;
  times: string[];
  notes?: string;
}

interface PlanFormValues {
  name: string;
  description?: string;
  items: ItemFormValues[];
}

export default function MedicationPlansPage() {
  const [plans, setPlans] = useState<MedicationPlan[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [detailPlan, setDetailPlan] = useState<MedicationPlan | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [form] = Form.useForm<PlanFormValues>();

  const loadPlans = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getMedicationPlans();
      setPlans(data);
    } catch {
      setPlans([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadPlans();
  }, [loadPlans]);

  const handleOpenCreate = () => {
    form.resetFields();
    form.setFieldsValue({
      name: '',
      description: '',
      items: [
        { medicineName: '', dosage: '', frequency: 'daily', times: [], notes: '' },
      ],
    });
    setModalOpen(true);
  };

  const handleCreate = async () => {
    try {
      const values = await form.validateFields();
      setSubmitting(true);
      await createMedicationPlan({
        name: values.name,
        description: values.description,
        items: values.items.map((it) => ({
          medicineName: it.medicineName,
          dosage: it.dosage,
          frequency: it.frequency ?? 'daily',
          times: it.times,
          notes: it.notes,
        })),
      });
      message.success('用药套餐已创建');
      setModalOpen(false);
      loadPlans();
    } catch (err) {
      if (err instanceof Error && err.message.includes('未授权')) {
        message.error('登录已过期，请重新登录');
      }
      // validation errors are shown inline by Form
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteMedicationPlan(id);
      message.success('已删除用药套餐');
      if (detailPlan?.id === id) {
        setDetailOpen(false);
        setDetailPlan(null);
      }
      loadPlans();
    } catch {
      message.error('删除失败');
    }
  };

  const handlePause = async (id: string) => {
    try {
      const updated = await pausePlan(id);
      message.success('已暂停套餐及相关提醒');
      setDetailPlan(updated);
      loadPlans();
    } catch {
      message.error('操作失败');
    }
  };

  const handleResume = async (id: string) => {
    try {
      const updated = await resumePlan(id);
      message.success('已恢复套餐及相关提醒');
      setDetailPlan(updated);
      loadPlans();
    } catch {
      message.error('操作失败');
    }
  };

  const openDetail = (plan: MedicationPlan) => {
    setDetailPlan(plan);
    setDetailOpen(true);
  };

  const itemColumns = [
    {
      title: '药品名称',
      dataIndex: 'medicineName',
      key: 'medicineName',
      render: (v: string) => <Text strong>{v}</Text>,
    },
    {
      title: '用量',
      dataIndex: 'dosage',
      key: 'dosage',
      render: (v: string) => v || '—',
    },
    {
      title: '频率',
      dataIndex: 'frequency',
      key: 'frequency',
      render: (v: string) => FREQUENCY_LABEL[v] ?? v,
    },
    {
      title: '提醒时间',
      dataIndex: 'times',
      key: 'times',
      render: (times: string[]) => (
        <Space wrap size={[4, 4]}>
          {(times ?? []).map((t, i) => (
            <Tag key={i} icon={<ClockCircleOutlined />} color="blue">
              {t}
            </Tag>
          ))}
        </Space>
      ),
    },
    {
      title: '备注',
      dataIndex: 'notes',
      key: 'notes',
      render: (v: string) => v || '—',
    },
  ];

  return (
    <div>
      {/* 页头 */}
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
            <MedicineBoxOutlined style={{ color: '#08979c' }} />
            用药套餐
          </Space>
        </Title>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={handleOpenCreate}
          size="large"
        >
          新建套餐
        </Button>
      </div>

      {/* 内容区 */}
      {loading ? (
        <Skeleton active paragraph={{ rows: 6 }} />
      ) : plans.length === 0 ? (
        <Empty
          description="暂无用药套餐，点击「新建套餐」开始"
          style={{ marginTop: 60 }}
        />
      ) : (
        <Row gutter={[16, 16]}>
          {plans.map((plan) => (
            <Col xs={24} sm={12} lg={8} key={plan.id}>
              <Card
                hoverable
                onClick={() => openDetail(plan)}
                styles={{ body: { padding: 20 } }}
                style={{
                  borderRadius: 12,
                  border: '1px solid #e8f4f0',
                }}
              >
                <Space direction="vertical" size={10} style={{ width: '100%' }}>
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'flex-start',
                      gap: 8,
                    }}
                  >
                    <Text strong style={{ fontSize: 18, color: '#006d75' }}>
                      {plan.name}
                    </Text>
                    <Tag color={STATUS_COLOR[plan.status]}>
                      {STATUS_LABEL[plan.status]}
                    </Tag>
                  </div>

                  {plan.description && (
                    <Paragraph
                      type="secondary"
                      ellipsis={{ rows: 2 }}
                      style={{ fontSize: 14, marginBottom: 0, minHeight: 42 }}
                    >
                      {plan.description}
                    </Paragraph>
                  )}

                  <div
                    style={{
                      display: 'flex',
                      gap: 16,
                      flexWrap: 'wrap',
                      fontSize: 14,
                    }}
                  >
                    <span>
                      <Text type="secondary">药品数：</Text>
                      <Text strong>{plan.items.length}</Text> 项
                    </span>
                  </div>

                  <div style={{ fontSize: 13, color: '#999' }}>
                    {plan.startDate || plan.endDate ? (
                      <span>
                        {plan.startDate ?? '—'} 至 {plan.endDate ?? '长期'}
                      </span>
                    ) : (
                      <span>创建于 {plan.createdAt.slice(0, 10)}</span>
                    )}
                  </div>
                </Space>
              </Card>
            </Col>
          ))}
        </Row>
      )}

      {/* 新建套餐弹窗 */}
      <Modal
        title="新建用药套餐"
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        width={640}
        destroyOnClose
        okText="创建"
        cancelText="取消"
        confirmLoading={submitting}
        onOk={handleCreate}
      >
        <Form form={form} layout="vertical" preserve={false}>
          <Form.Item
            label="套餐名称"
            name="name"
            rules={[{ required: true, message: '请输入套餐名称' }]}
          >
            <Input placeholder="如：高血压日常管理" />
          </Form.Item>
          <Form.Item label="描述" name="description">
            <Input.TextArea rows={2} placeholder="可选，简要说明套餐目的" />
          </Form.Item>

          <Text strong style={{ display: 'block', marginBottom: 8 }}>
            用药明细
          </Text>
          <Form.List name="items">
            {(fields, { add, remove }) => (
              <>
                {fields.map((field) => (
                  <div
                    key={field.key}
                    style={{
                      border: '1px solid #f0f0f0',
                      borderRadius: 8,
                      padding: 12,
                      marginBottom: 12,
                      background: '#fafcfc',
                    }}
                  >
                    <Row gutter={12}>
                      <Col span={12}>
                        <Form.Item
                          label="药品名称"
                          name={[field.name, 'medicineName']}
                          rules={[{ required: true, message: '请输入药品名称' }]}
                        >
                          <Input placeholder="如：缬沙坦胶囊" />
                        </Form.Item>
                      </Col>
                      <Col span={12}>
                        <Form.Item label="用量" name={[field.name, 'dosage']}>
                          <Input placeholder="如：每次80mg" />
                        </Form.Item>
                      </Col>
                    </Row>
                    <Row gutter={12}>
                      <Col span={8}>
                        <Form.Item
                          label="频率"
                          name={[field.name, 'frequency']}
                          initialValue="daily"
                        >
                          <Select options={FREQUENCY_OPTIONS} />
                        </Form.Item>
                      </Col>
                      <Col span={16}>
                        <Form.Item
                          label="提醒时间（输入后回车添加）"
                          name={[field.name, 'times']}
                          rules={[
                            {
                              required: true,
                              message: '至少添加一个提醒时间',
                            },
                          ]}
                        >
                          <Select
                            mode="tags"
                            placeholder="如：08:00，回车添加"
                            tokenSeparators={[',', ' ']}
                          />
                        </Form.Item>
                      </Col>
                    </Row>
                    <Form.Item label="备注" name={[field.name, 'notes']}>
                      <Input placeholder="如：空腹服用" />
                    </Form.Item>
                    {fields.length > 1 && (
                      <Button
                        type="link"
                        danger
                        icon={<MinusCircleOutlined />}
                        onClick={() => remove(field.name)}
                      >
                        移除该药品
                      </Button>
                    )}
                  </div>
                ))}
                <Button
                  type="dashed"
                  icon={<PlusOutlined />}
                  onClick={() =>
                    add({
                      medicineName: '',
                      dosage: '',
                      frequency: 'daily',
                      times: [],
                      notes: '',
                    })
                  }
                  block
                >
                  添加药品
                </Button>
              </>
            )}
          </Form.List>
        </Form>
      </Modal>

      {/* 套餐详情抽屉 */}
      <Modal
        title={detailPlan?.name}
        open={detailOpen}
        onCancel={() => setDetailOpen(false)}
        footer={null}
        width={760}
        destroyOnClose
      >
        {detailPlan && (
          <div>
            <Space wrap size={[8, 8]} style={{ marginBottom: 16 }}>
              <Tag color={STATUS_COLOR[detailPlan.status]}>
                {STATUS_LABEL[detailPlan.status]}
              </Tag>
              <Tag icon={<MedicineBoxOutlined />}>
                {detailPlan.items.length} 项药品
              </Tag>
              {detailPlan.startDate && (
                <Tag>
                  {detailPlan.startDate}
                  {detailPlan.endDate ? ` 至 ${detailPlan.endDate}` : ' 起'}
                </Tag>
              )}
            </Space>

            {detailPlan.description && (
              <Paragraph type="secondary">{detailPlan.description}</Paragraph>
            )}

            <Table<PlanItem>
              dataSource={detailPlan.items}
              columns={itemColumns}
              rowKey="id"
              size="middle"
              pagination={false}
              style={{ marginBottom: 16 }}
            />

            <Space wrap>
              {detailPlan.status === 'active' && (
                <Button
                  icon={<PauseCircleOutlined />}
                  onClick={() => handlePause(detailPlan.id)}
                >
                  暂停套餐
                </Button>
              )}
              {detailPlan.status === 'paused' && (
                <Button
                  type="primary"
                  icon={<PlayCircleOutlined />}
                  onClick={() => handleResume(detailPlan.id)}
                >
                  恢复套餐
                </Button>
              )}
              <Popconfirm
                title="确定删除该用药套餐？关联的提醒将一并删除。"
                okText="确定删除"
                cancelText="取消"
                onConfirm={() => handleDelete(detailPlan.id)}
              >
                <Button danger icon={<DeleteOutlined />}>
                  删除套餐
                </Button>
              </Popconfirm>
              <Tooltip title="套餐中的每个药品已自动生成吃药提醒，可在「吃药提醒」页面查看">
                <Text type="secondary" style={{ fontSize: 13 }}>
                  提醒已同步至「吃药提醒」
                </Text>
              </Tooltip>
            </Space>
          </div>
        )}
      </Modal>
    </div>
  );
}
