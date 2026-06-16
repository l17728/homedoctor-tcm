import { useState, useEffect, useCallback } from 'react';
import {
  Table,
  Button,
  Drawer,
  Form,
  Input,
  Select,
  TimePicker,
  DatePicker,
  Switch,
  Popconfirm,
  message,
  Empty,
  Skeleton,
  Typography,
  Space,
  Card,
  Tag,
  Radio,
} from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  ClockCircleOutlined,
  CheckCircleOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import {
  getReminders,
  getTodayReminders,
  getReminderHistory,
  createReminder,
  updateReminder,
  deleteReminder,
  toggleReminder,
  checkInReminder,
  type Reminder,
  type TodayReminderSlot,
  type ReminderCreate,
  type CheckInLog,
} from '../api/reminderApi';
import { REMINDER_STATUS_COLOR } from '../constants';
import StatusTag from '../components/StatusTag';

const { Title } = Typography;

interface FormValues {
  title: string;
  linkType: 'none' | 'herb' | 'formula' | 'medicine';
  linkName?: string;
  dosage?: string;
  frequency: string;
  times: dayjs.Dayjs[];
  startDate: dayjs.Dayjs;
  endDate?: dayjs.Dayjs;
  notes?: string;
  enabled: boolean;
}

const FREQUENCY_OPTIONS = [
  { label: '每天', value: 'daily' },
  { label: '每周', value: 'weekly' },
  { label: '自定义', value: 'custom' },
];

export default function RemindersPage() {
  const [reminders, setReminders] = useState<Reminder[]>([]);
  const [todaySlots, setTodaySlots] = useState<TodayReminderSlot[]>([]);
  const [history, setHistory] = useState<CheckInLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editing, setEditing] = useState<Reminder | null>(null);
  const [form] = Form.useForm<FormValues>();

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [list, today, hist] = await Promise.all([
        getReminders(),
        getTodayReminders(),
        getReminderHistory(7).catch(() => null),
      ]);
      setReminders(list);
      setTodaySlots(today);
      setHistory(hist?.items ?? []);
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
    form.setFieldsValue({
      linkType: 'none',
      frequency: 'daily',
      enabled: true,
      startDate: dayjs(),
    });
    setDrawerOpen(true);
  };

  const handleEdit = (record: Reminder) => {
    setEditing(record);
    const linkType = record.herb_name
      ? 'herb'
      : record.formula_name
        ? 'formula'
        : record.medicine_name
          ? 'medicine'
          : 'none';
    const linkName =
      record.herb_name ?? record.formula_name ?? record.medicine_name ?? '';
    form.setFieldsValue({
      title: record.title,
      linkType,
      linkName,
      dosage: record.dosage ?? undefined,
      frequency: record.frequency,
      times: record.times.map((t) => dayjs(t, 'HH:mm')),
      startDate: dayjs(record.start_date),
      endDate: record.end_date ? dayjs(record.end_date) : undefined,
      notes: record.notes ?? undefined,
      enabled: record.enabled,
    });
    setDrawerOpen(true);
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      const payload: ReminderCreate = {
        title: values.title,
        dosage: values.dosage ?? null,
        frequency: values.frequency,
        times: values.times.map((t) => t.format('HH:mm')),
        start_date: values.startDate.format('YYYY-MM-DD'),
        end_date: values.endDate ? values.endDate.format('YYYY-MM-DD') : null,
        notes: values.notes ?? null,
        enabled: values.enabled,
      };
      if (values.linkType === 'herb') payload.herb_name = values.linkName ?? null;
      else if (values.linkType === 'formula') payload.formula_name = values.linkName ?? null;
      else if (values.linkType === 'medicine') payload.medicine_name = values.linkName ?? null;

      if (editing) {
        await updateReminder(editing.id, payload);
        message.success('更新成功');
      } else {
        await createReminder(payload);
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
      await deleteReminder(id);
      message.success('删除成功');
      loadData();
    } catch {
      message.error('删除失败');
    }
  };

  const handleToggle = async (id: string) => {
    try {
      await toggleReminder(id);
      loadData();
    } catch {
      message.error('操作失败');
    }
  };

  const handleCheckIn = async (reminderId: string, time: string) => {
    try {
      await checkInReminder(reminderId, time, true);
      const remaining = todaySlots.filter(
        (s) => s.status === '待服' && s.time !== time
      );
      if (remaining.length > 0) {
        const next = remaining[0]!;
        message.success(`已打卡 ✓ 下次：${next.time} ${next.title}`);
      } else {
        message.success('已打卡 ✓ 今日药品已全部服用完');
      }
      loadData();
    } catch {
      message.error('打卡失败');
    }
  };

  const columns = [
    { title: '标题', dataIndex: 'title', key: 'title', ellipsis: true },
    {
      title: '关联',
      key: 'link',
      render: (_: unknown, r: Reminder) =>
        r.herb_name ? `中药·${r.herb_name}` : r.formula_name ? `方剂·${r.formula_name}` : r.medicine_name ? `西药·${r.medicine_name}` : '—',
    },
    {
      title: '时间',
      key: 'times',
      render: (_: unknown, r: Reminder) => r.times.join('、'),
    },
    {
      title: '频率',
      dataIndex: 'frequency',
      key: 'frequency',
      render: (f: string) => f === 'daily' ? '每天' : f === 'weekly' ? '每周' : '自定义',
    },
    {
      title: '状态',
      key: 'enabled',
      render: (_: unknown, r: Reminder) => (
        <Switch checked={r.enabled} size="small" onChange={() => handleToggle(r.id)} />
      ),
    },
    {
      title: '操作',
      key: 'action',
      fixed: 'right' as const,
      width: 160,
      render: (_: unknown, r: Reminder) => (
        <Space>
          <Button type="link" size="small" icon={<EditOutlined />} onClick={() => handleEdit(r)}>
            编辑
          </Button>
          <Popconfirm title="确定删除该提醒吗？" onConfirm={() => handleDelete(r.id)} okText="确定" cancelText="取消">
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
        <Title level={3} style={{ margin: 0 }}>吃药提醒</Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
          添加提醒
        </Button>
      </div>

      {loading ? (
        <Skeleton active />
      ) : (
        <>
          {todaySlots.length > 0 && (
            <Card title={<><ClockCircleOutlined /> 今日提醒</>} style={{ marginBottom: 24 }}>
              <Space direction="vertical" style={{ width: '100%' }} size="small">
                {todaySlots.map((slot, i) => (
                  <div
                    key={i}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '8px 12px',
                      background: '#fafafa',
                      borderRadius: 6,
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                       <Tag color="blue" style={{ fontSize: 14, padding: '2px 8px' }}>
                         {slot.time}
                       </Tag>
                       <span style={{ fontSize: 16 }}>{slot.title}</span>
                       {slot.dosage && <span style={{ color: '#888' }}>{slot.dosage}</span>}
                     </div>
                     <Space>
                       {slot.status === '待服' && (
                         <Button
                           type="primary"
                           size="small"
                           icon={<CheckCircleOutlined />}
                           onClick={() => handleCheckIn(slot.reminder_id, slot.time)}
                         >
                           打卡
                         </Button>
                       )}
                       <StatusTag status={slot.status} colorMap={REMINDER_STATUS_COLOR} />
                     </Space>
                  </div>
                ))}
              </Space>
            </Card>
          )}

          {history.length > 0 && (
            <Card title={<><CheckCircleOutlined /> 打卡历史（近7天）</>} style={{ marginBottom: 24 }}>
              <Space direction="vertical" style={{ width: '100%' }} size="small">
                {history.slice(0, 10).map((log) => (
                  <div
                    key={log.id}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '6px 12px',
                      background: log.taken ? '#f6ffed' : '#fff2f0',
                      borderRadius: 6,
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                      <Tag color={log.taken ? 'green' : 'red'} style={{ fontSize: 13 }}>
                        {log.date}
                      </Tag>
                      <span style={{ fontSize: 15 }}>
                        {log.title ?? '已删除的提醒'}
                      </span>
                    </div>
                    <Tag color={log.taken ? 'success' : 'error'}>
                      {log.taken ? '已服' : '漏服'}
                    </Tag>
                  </div>
                ))}
              </Space>
            </Card>
          )}

          {reminders.length === 0 ? (
            <Empty description="暂无提醒，点击添加" />
          ) : (
            <Table
              dataSource={reminders}
              columns={columns}
              rowKey="id"
              size="middle"
              pagination={false}
            />
          )}
        </>
      )}

      <Drawer
        title={editing ? '编辑提醒' : '添加提醒'}
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
          <Form.Item label="提醒标题" name="title" rules={[{ required: true, message: '请输入提醒标题' }]}>
            <Input placeholder="如：服用降压药" />
          </Form.Item>
          <Form.Item label="关联类型" name="linkType">
            <Radio.Group>
              <Radio value="none">无</Radio>
              <Radio value="herb">中药</Radio>
              <Radio value="formula">方剂</Radio>
              <Radio value="medicine">西药</Radio>
            </Radio.Group>
          </Form.Item>
          <Form.Item noStyle shouldUpdate={(prev, cur) => prev.linkType !== cur.linkType}>
            {({ getFieldValue }) =>
              getFieldValue('linkType') !== 'none' ? (
                <Form.Item label="关联名称" name="linkName">
                  <Input placeholder="请输入名称" />
                </Form.Item>
              ) : null
            }
          </Form.Item>
          <Form.Item label="剂量" name="dosage">
            <Input placeholder="如：2片 或 10g煎服" />
          </Form.Item>
          <Form.Item label="频率" name="frequency" rules={[{ required: true }]}>
            <Select options={FREQUENCY_OPTIONS} />
          </Form.Item>
          <Form.Item label="提醒时间" name="times" rules={[{ required: true, message: '请至少选择一个时间' }]}>
            <TimePicker.RangePicker format="HH:mm" style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item label="开始日期" name="startDate" rules={[{ required: true, message: '请选择开始日期' }]}>
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item label="结束日期" name="endDate">
            <DatePicker style={{ width: '100%' }} placeholder="留空=无限期" />
          </Form.Item>
          <Form.Item label="备注" name="notes">
            <Input.TextArea rows={2} placeholder="如：饭后服用" />
          </Form.Item>
          <Form.Item label="启用" name="enabled" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Drawer>
    </div>
  );
}
