import { useState } from 'react';
import {
  Modal,
  Steps,
  Form,
  Input,
  InputNumber,
  Select,
  Button,
  TimePicker,
  Typography,
  Space,
  Tag,
  Empty,
  message,
} from 'antd';
import {
  HeartOutlined,
  MedicineBoxOutlined,
  BellOutlined,
  CheckCircleOutlined,
  PlusOutlined,
  CloseOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { updateProfile, type ProfileUpdate } from '../api/profileApi';
import { createMedicine, type Medicine } from '../api/medicineApi';
import { createReminder } from '../api/reminderApi';

const { Title, Text, Paragraph } = Typography;

export const ONBOARDING_KEY = 'onboarding_completed';

const MEDICINE_TYPES = ['西药', '中成药', '中药饮片', '保健品'];

interface MedicineDraft {
  name: string;
  type: string;
}

interface ProfileFormValues {
  birth_year?: number;
  gender?: string;
  height_cm?: number;
  weight_kg?: number;
  conditions?: string;
}

interface Props {
  open: boolean;
  onComplete: () => void;
}

export default function OnboardingWizard({ open, onComplete }: Props) {
  const [current, setCurrent] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [profileForm] = Form.useForm<ProfileFormValues>();

  // Step 2 — medicines draft list
  const [medName, setMedName] = useState('');
  const [medType, setMedType] = useState<string>(MEDICINE_TYPES[0]!);
  const [medicines, setMedicines] = useState<MedicineDraft[]>([]);

  // Step 3 — reminder
  const [reminderMedName, setReminderMedName] = useState('');
  const [reminderTime, setReminderTime] = useState<dayjs.Dayjs | null>(null);

  const addMedicine = () => {
    const name = medName.trim();
    if (!name) {
      message.warning('请输入药品名称');
      return;
    }
    setMedicines((prev) => [...prev, { name, type: medType }]);
    setMedName('');
  };

  const removeMedicine = (index: number) => {
    setMedicines((prev) => prev.filter((_, i) => i !== index));
  };

  const finishProfile = async () => {
    try {
      const values = await profileForm.validateFields();
      const update: ProfileUpdate = {};
      if (values.birth_year != null) update.birth_year = values.birth_year;
      if (values.gender) update.gender = values.gender;
      if (values.height_cm != null) update.height_cm = values.height_cm;
      if (values.weight_kg != null) update.weight_kg = values.weight_kg;
      if (values.conditions?.trim()) {
        update.health_conditions = values.conditions
          .split(/[,，;；\s]+/)
          .map((s) => s.trim())
          .filter(Boolean);
      }
      if (Object.keys(update).length > 0) {
        try {
          await updateProfile(update);
        } catch {
          // 非致命：网络异常也可继续后续步骤
        }
      }
      setCurrent(1);
    } catch {
      // 校验未通过，停留在当前步
    }
  };

  const saveMedicinesAndNext = async () => {
    setSubmitting(true);
    const created: Medicine[] = [];
    try {
      for (const m of medicines) {
        try {
          const med = await createMedicine({ name: m.name, type: m.type });
          created.push(med);
        } catch {
          // 单条失败不阻断流程
        }
      }
      // 预填下一步的药品名（取首个）
      if (created.length > 0 && created[0]?.name) {
        setReminderMedName(created[0].name);
      } else if (medicines.length > 0 && medicines[0]?.name) {
        setReminderMedName(medicines[0].name);
      }
      setCurrent(2);
    } finally {
      setSubmitting(false);
    }
  };

  const saveReminderAndFinish = async () => {
    setSubmitting(true);
    try {
      const name = reminderMedName.trim();
      const time = reminderTime ? reminderTime.format('HH:mm') : '';
      if (name && time) {
        try {
          await createReminder({
            title: `${name} 服药提醒`,
            medicine_name: name,
            frequency: 'daily',
            times: [time],
            start_date: new Date().toISOString().slice(0, 10),
            enabled: true,
          });
        } catch {
          // 非致命
        }
      }
      setCurrent(3);
    } finally {
      setSubmitting(false);
    }
  };

  const handleComplete = () => {
    localStorage.setItem(ONBOARDING_KEY, 'true');
    onComplete();
  };

  const handleSkip = () => {
    // 跳过当前步骤直接进入下一步（不保存数据）
    setCurrent((c) => Math.min(c + 1, 3));
  };

  const isLastFormStep = current === 2;
  const isCompletion = current === 3;

  const footerBtns = (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
      <div>
        {current > 0 && !isCompletion && (
          <Button onClick={() => setCurrent((c) => c - 1)}>上一步</Button>
        )}
      </div>
      <Space>
        {/* 步骤 2、3 允许跳过 */}
        {(current === 1 || current === 2) && (
          <Button onClick={handleSkip}>跳过</Button>
        )}
        {current === 0 && (
          <Button type="primary" onClick={finishProfile} loading={submitting}>
            下一步
          </Button>
        )}
        {current === 1 && (
          <Button type="primary" onClick={saveMedicinesAndNext} loading={submitting}>
            下一步
          </Button>
        )}
        {isLastFormStep && (
          <Button type="primary" onClick={saveReminderAndFinish} loading={submitting}>
            完成
          </Button>
        )}
        {isCompletion && (
          <Button type="primary" onClick={handleComplete}>
            开始使用
          </Button>
        )}
      </Space>
    </div>
  );

  return (
    <Modal
      open={open}
      closable={false}
      maskClosable={false}
      keyboard={false}
      footer={footerBtns}
      width={480}
      centered
      styles={{ body: { padding: '24px 24px 8px' } }}
    >
      <Steps
        current={current}
        size="small"
        style={{ marginBottom: 24 }}
        items={[
          { title: '健康档案', icon: <HeartOutlined /> },
          { title: '常用药品', icon: <MedicineBoxOutlined /> },
          { title: '吃药提醒', icon: <BellOutlined /> },
          { title: '完成', icon: <CheckCircleOutlined /> },
        ]}
      />

      {/* 步骤 1：健康档案 */}
      {current === 0 && (
        <div>
          <Title level={4} style={{ marginBottom: 8 }}>
            完善健康档案
          </Title>
          <Paragraph type="secondary" style={{ fontSize: 16, marginBottom: 16 }}>
            填写基本信息，让我们更好地为您服务。
          </Paragraph>
          <Form
            form={profileForm}
            layout="vertical"
            requiredMark={false}
            style={{ fontSize: 18 }}
          >
            <Form.Item label="出生年份" name="birth_year">
              <InputNumber
                placeholder="如 1955"
                min={1900}
                max={new Date().getFullYear()}
                style={{ width: '100%' }}
              />
            </Form.Item>
            <Form.Item label="性别" name="gender">
              <Select
                placeholder="请选择"
                options={[
                  { label: '男', value: '男' },
                  { label: '女', value: '女' },
                ]}
              />
            </Form.Item>
            <div style={{ display: 'flex', gap: 12 }}>
              <Form.Item label="身高 (cm)" name="height_cm" style={{ flex: 1, marginBottom: 16 }}>
                <InputNumber placeholder="如 165" min={50} max={250} style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item label="体重 (kg)" name="weight_kg" style={{ flex: 1, marginBottom: 16 }}>
                <InputNumber placeholder="如 60" min={10} max={300} style={{ width: '100%' }} />
              </Form.Item>
            </div>
            <Form.Item
              label="现有疾病/健康状况"
              name="conditions"
              extra="多个疾病用逗号或空格分隔，如：高血压、糖尿病"
            >
              <Input.TextArea
                rows={2}
                placeholder="如：高血压、糖尿病"
                style={{ fontSize: 16 }}
              />
            </Form.Item>
          </Form>
        </div>
      )}

      {/* 步骤 2：常用药品 */}
      {current === 1 && (
        <div>
          <Title level={4} style={{ marginBottom: 8 }}>
            添加常用药品
          </Title>
          <Paragraph type="secondary" style={{ fontSize: 16, marginBottom: 16 }}>
            把家里的常用药加入药箱，方便管理与提醒。
          </Paragraph>

          <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
            <Input
              placeholder="药品名称，如 二甲双胍"
              value={medName}
              onChange={(e) => setMedName(e.target.value)}
              onPressEnter={addMedicine}
              style={{ flex: 1, fontSize: 16 }}
            />
            <Select
              value={medType}
              onChange={setMedType}
              style={{ width: 120 }}
              options={MEDICINE_TYPES.map((t) => ({ label: t, value: t }))}
            />
            <Button type="primary" icon={<PlusOutlined />} onClick={addMedicine}>
              添加
            </Button>
          </div>

          {medicines.length === 0 ? (
            <Empty
              description="还没有添加药品，可点击「跳过」稍后再加"
              image={Empty.PRESENTED_IMAGE_SIMPLE}
            />
          ) : (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {medicines.map((m, i) => (
                <Tag
                  key={`${m.name}-${i}`}
                  closable
                  closeIcon={<CloseOutlined />}
                  onClose={() => removeMedicine(i)}
                  style={{ fontSize: 16, padding: '4px 10px' }}
                  icon={<MedicineBoxOutlined />}
                >
                  {m.name} · {m.type}
                </Tag>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 步骤 3：吃药提醒 */}
      {isLastFormStep && (
        <div>
          <Title level={4} style={{ marginBottom: 8 }}>
            设置吃药提醒
          </Title>
          <Paragraph type="secondary" style={{ fontSize: 16, marginBottom: 16 }}>
            设定一个固定的服药时间，再也不怕忘记。
          </Paragraph>
          <Form layout="vertical" requiredMark={false}>
            <Form.Item label="药品名称">
              <Input
                placeholder="如 二甲双胍"
                value={reminderMedName}
                onChange={(e) => setReminderMedName(e.target.value)}
                style={{ fontSize: 16 }}
              />
            </Form.Item>
            <Form.Item label="提醒时间">
              <TimePicker
                value={reminderTime}
                onChange={setReminderTime}
                format="HH:mm"
                minuteStep={5}
                placeholder="选择时间"
                style={{ width: '100%', fontSize: 16 }}
              />
            </Form.Item>
          </Form>
        </div>
      )}

      {/* 完成页 */}
      {isCompletion && (
        <div style={{ textAlign: 'center', padding: '24px 0' }}>
          <CheckCircleOutlined style={{ fontSize: 56, color: '#52c41a', marginBottom: 16 }} />
          <Title level={3} style={{ marginBottom: 8 }}>
            完成！
          </Title>
          <Paragraph style={{ fontSize: 18 }}>
            您已准备好开始健康管理之旅
          </Paragraph>
        </div>
      )}

      <div style={{ textAlign: 'center', marginTop: 8 }}>
        <Text type="secondary" style={{ fontSize: 13 }}>
          第 {Math.min(current + 1, 4)} / 4 步
        </Text>
      </div>
    </Modal>
  );
}
