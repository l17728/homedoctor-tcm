import { useState, useEffect } from 'react';
import {
  Card,
  Form,
  Input,
  InputNumber,
  Radio,
  Select,
  Switch,
  Button,
  Tag,
  Typography,
  Space,
  Skeleton,
  message,
} from 'antd';
import { SaveOutlined, HeartOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import {
  getProfile,
  updateProfile,
  type UserProfile,
} from '../api/profileApi';

const { Title, Text } = Typography;

const BLOOD_TYPES = ['A', 'B', 'AB', 'O'];
const COMMON_CONDITIONS = ['高血压', '糖尿病', '冠心病', '高血脂', '脂肪肝', '痛风', '甲状腺结节', '胃炎'];
const COMMON_ALLERGIES = ['青霉素', '海鲜', '花粉', '尘螨', '芒果', '酒精'];

interface FormValues {
  display_name: string;
  gender: string;
  birth_year: number;
  height_cm: number;
  weight_kg: number;
  blood_type: string;
  allergies: string[];
  health_conditions: string[];
  is_pregnant: boolean;
  notes: string;
}

export default function ProfilePage() {
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm<FormValues>();
  const navigate = useNavigate();

  useEffect(() => {
    getProfile()
      .then((data) => {
        setProfile(data);
        form.setFieldsValue({
          display_name: data.display_name ?? '',
          gender: data.gender ?? undefined,
          birth_year: data.birth_year ?? undefined,
          height_cm: data.height_cm ?? undefined,
          weight_kg: data.weight_kg ?? undefined,
          blood_type: data.blood_type ?? undefined,
          allergies: data.allergies ?? [],
          health_conditions: data.health_conditions ?? [],
          is_pregnant: data.is_pregnant ?? false,
          notes: data.notes ?? '',
        });
      })
      .catch(() => {
        // new user, no profile yet
      })
      .finally(() => setLoading(false));
  }, [form]);

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      setSaving(true);
      const updated = await updateProfile({
        display_name: values.display_name || null,
        gender: values.gender ?? null,
        birth_year: values.birth_year ?? null,
        height_cm: values.height_cm ?? null,
        weight_kg: values.weight_kg ?? null,
        blood_type: values.blood_type ?? null,
        allergies: values.allergies ?? [],
        health_conditions: values.health_conditions ?? [],
        is_pregnant: values.is_pregnant ?? false,
        notes: values.notes || null,
      });
      setProfile(updated);
      message.success('保存成功');
    } catch (err) {
      // antd 表单校验错误为普通对象（含 errorFields），不弹提示；API 失败（Error）才提示
      if (err instanceof Error) {
        message.error('保存失败，请检查网络后重试');
      }
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <Skeleton active />;
  }

  const constitutionType = profile?.constitution_type;

  return (
    <div>
      <Title level={3}>健康档案</Title>

      <Card title="基本信息" style={{ marginBottom: 24 }}>
        <Form form={form} layout="vertical">
          <Form.Item label="昵称" name="display_name">
            <Input placeholder="请输入昵称" />
          </Form.Item>
          <Space style={{ width: '100%' }} size="large">
            <Form.Item label="性别" name="gender">
              <Radio.Group>
                <Radio value="男">男</Radio>
                <Radio value="女">女</Radio>
              </Radio.Group>
            </Form.Item>
            <Form.Item label="出生年份" name="birth_year">
              <InputNumber min={1920} max={2025} placeholder="如：1960" />
            </Form.Item>
          </Space>
          <Space style={{ width: '100%' }} size="large">
            <Form.Item label="身高(cm)" name="height_cm">
              <InputNumber min={80} max={250} placeholder="如：165" />
            </Form.Item>
            <Form.Item label="体重(kg)" name="weight_kg">
              <InputNumber min={20} max={200} placeholder="如：60" />
            </Form.Item>
            <Form.Item label="血型" name="blood_type">
              <Select
                style={{ width: 120 }}
                allowClear
                options={BLOOD_TYPES.map((t) => ({ label: `${t}型`, value: t }))}
                placeholder="选择"
              />
            </Form.Item>
          </Space>
        </Form>
      </Card>

      <Card
        title="体质信息"
        style={{ marginBottom: 24 }}
        extra={
          <Button
            type="link"
            icon={<HeartOutlined />}
            onClick={() => navigate('/constitution')}
          >
            {constitutionType ? '重新测试' : '去测试'}
          </Button>
        }
      >
        {constitutionType ? (
          <Space>
            <Text>主体质：</Text>
            <Tag color="blue" style={{ fontSize: 16, padding: '4px 12px' }}>
              {constitutionType}
            </Tag>
            {profile?.constitution_secondary?.map((s) => (
              <Tag key={s} color="default">
                兼：{s}
              </Tag>
            ))}
          </Space>
        ) : (
          <Text type="secondary">尚未进行体质测试，点击"去测试"开始评估</Text>
        )}
      </Card>

      <Card title="健康信息" style={{ marginBottom: 24 }}>
        <Form form={form} layout="vertical">
          <Form.Item label="过敏史" name="allergies">
            <Select
              mode="tags"
              placeholder="输入或选择过敏源"
              tokenSeparators={[',']}
              options={COMMON_ALLERGIES.map((a) => ({ label: a, value: a }))}
            />
          </Form.Item>
          <Form.Item label="健康问题" name="health_conditions">
            <Select
              mode="tags"
              placeholder="选择或输入健康问题"
              tokenSeparators={[',']}
              options={COMMON_CONDITIONS.map((c) => ({ label: c, value: c }))}
            />
          </Form.Item>
          <Form.Item noStyle shouldUpdate={(prev, cur) => prev.gender !== cur.gender}>
            {({ getFieldValue }) =>
              getFieldValue('gender') === '女' ? (
                <Form.Item label="是否孕期" name="is_pregnant" valuePropName="checked">
                  <Switch />
                </Form.Item>
              ) : null
            }
          </Form.Item>
          <Form.Item label="备注" name="notes">
            <Input.TextArea rows={3} placeholder="其他需要记录的健康信息" />
          </Form.Item>
        </Form>
      </Card>

      <div style={{ textAlign: 'center', paddingBottom: 24 }}>
        <Button
          type="primary"
          size="large"
          icon={<SaveOutlined />}
          onClick={handleSave}
          loading={saving}
        >
          保存档案
        </Button>
      </div>
    </div>
  );
}
