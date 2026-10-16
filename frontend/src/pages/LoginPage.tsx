import { useState } from 'react';
import {
  Card,
  Form,
  Input,
  Button,
  Tabs,
  message,
  Typography,
  Checkbox,
  Modal,
  Alert,
  InputNumber,
} from 'antd';
import { UserOutlined, LockOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import type { RegisterConsent } from '../api/authApi';

const { Title, Paragraph, Text } = Typography;

interface LoginForm {
  username: string;
  password: string;
}

interface RegisterForm {
  username: string;
  password: string;
  confirmPassword: string;
  consentPrivacy: boolean;
  consentHealthData: boolean;
  birthYear?: number;
}

const PRIVACY_NOTICE_TEXT =
  '本应用收集您的健康信息（体质类型、用药记录、过敏史等）用于：' +
  '1. 个性化健康建议 2. 用药安全检查 3. 养生推荐。' +
  '数据存储在本地设备，不会上传至云端（AI对话除外）。' +
  '您随时可以通过设置→账户管理→删除账户来清除所有数据。';

export default function LoginPage() {
  const [loading, setLoading] = useState(false);
  const [privacyModalOpen, setPrivacyModalOpen] = useState(false);
  const [registerForm] = Form.useForm<RegisterForm>();
  const { login, register } = useAuth();
  const navigate = useNavigate();

  const handleLogin = async (values: LoginForm) => {
    setLoading(true);
    try {
      await login(values.username, values.password);
      message.success('登录成功');
      navigate('/');
    } catch (err) {
      // fetch 网络失败抛 TypeError；服务端业务错误（ApiError）为凭据问题
      if (err instanceof TypeError) {
        message.error('无法连接服务器，请检查网络或联系管理员');
      } else {
        message.error('用户名或密码错误');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleRegister = async (values: RegisterForm) => {
    if (values.password !== values.confirmPassword) {
      message.error('两次输入的密码不一致');
      return;
    }

    const consent: RegisterConsent = {
      consent_privacy: values.consentPrivacy,
      consent_health_data: values.consentHealthData,
      birth_year: values.birthYear,
    };

    setLoading(true);
    try {
      await register(values.username, values.password, consent);
      message.success('注册成功');
      navigate('/');
    } catch {
      message.error('注册失败，请重试');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        minHeight: '100vh',
        background: '#f0f2f5',
      }}
    >
      <Card style={{ width: '90%', maxWidth: 400 }}>
        <Title level={3} style={{ textAlign: 'center', marginBottom: 24 }}>
          家庭医生
        </Title>
        <Tabs
          items={[
            {
              key: 'login',
              label: '登录',
              children: (
                <Form onFinish={handleLogin} size="large">
                  <Form.Item
                    name="username"
                    rules={[{ required: true, message: '请输入用户名' }]}
                  >
                    <Input
                      prefix={<UserOutlined />}
                      placeholder="用户名"
                    />
                  </Form.Item>
                  <Form.Item
                    name="password"
                    rules={[{ required: true, message: '请输入密码' }]}
                  >
                    <Input.Password
                      prefix={<LockOutlined />}
                      placeholder="密码"
                    />
                  </Form.Item>
                  <Form.Item>
                    <Button
                      type="primary"
                      htmlType="submit"
                      loading={loading}
                      block
                    >
                      登录
                    </Button>
                  </Form.Item>
                </Form>
              ),
            },
            {
              key: 'register',
              label: '注册',
              children: (
                <Form
                  form={registerForm}
                  onFinish={handleRegister}
                  size="large"
                  layout="vertical"
                >
                  <Form.Item
                    name="username"
                    rules={[{ required: true, message: '请输入用户名' }]}
                  >
                    <Input
                      prefix={<UserOutlined />}
                      placeholder="用户名"
                    />
                  </Form.Item>
                  <Form.Item
                    name="password"
                    rules={[{ required: true, message: '请输入密码' }]}
                  >
                    <Input.Password
                      prefix={<LockOutlined />}
                      placeholder="密码"
                    />
                  </Form.Item>
                  <Form.Item
                    name="confirmPassword"
                    rules={[{ required: true, message: '请确认密码' }]}
                  >
                    <Input.Password
                      prefix={<LockOutlined />}
                      placeholder="确认密码"
                    />
                  </Form.Item>

                  <Form.Item
                    name="consentPrivacy"
                    valuePropName="checked"
                    rules={[
                      {
                        validator: (_, value: boolean) =>
                          value
                            ? Promise.resolve()
                            : Promise.reject(new Error('请同意隐私政策')),
                      },
                    ]}
                  >
                    <Checkbox style={{ fontSize: 16 }}>
                      我已阅读并同意
                      <Text
                        strong
                        style={{ color: '#1677ff', cursor: 'pointer' }}
                        onClick={(e) => {
                          e.stopPropagation();
                          setPrivacyModalOpen(true);
                        }}
                      >
                        《隐私政策》
                      </Text>
                      和
                      <Text
                        strong
                        style={{ color: '#1677ff', cursor: 'pointer' }}
                        onClick={(e) => {
                          e.stopPropagation();
                          setPrivacyModalOpen(true);
                        }}
                      >
                        《用户协议》
                      </Text>
                    </Checkbox>
                  </Form.Item>

                  <Form.Item
                    name="consentHealthData"
                    valuePropName="checked"
                  >
                    <Checkbox style={{ fontSize: 16 }}>
                      我同意收集健康数据（体质、用药、过敏等信息）用于健康管理
                    </Checkbox>
                  </Form.Item>

                  <Form.Item name="birthYear">
                    <InputNumber
                      style={{ width: '100%' }}
                      placeholder="出生年份（用于未成年人保护）"
                      min={1900}
                      max={new Date().getFullYear()}
                    />
                  </Form.Item>

                  <Form.Item
                    noStyle
                    shouldUpdate={(prev, curr) =>
                      prev.birthYear !== curr.birthYear
                    }
                  >
                    {({ getFieldValue }) => {
                      const year = getFieldValue('birthYear') as
                        | number
                        | undefined;
                      if (
                        year &&
                        new Date().getFullYear() - year < 14
                      ) {
                        return (
                          <Alert
                            message="未成年人使用需监护人确认"
                            type="warning"
                            showIcon
                            style={{ marginBottom: 16 }}
                          />
                        );
                      }
                      return null;
                    }}
                  </Form.Item>

                  <Form.Item>
                    <Button
                      type="primary"
                      htmlType="submit"
                      loading={loading}
                      block
                    >
                      注册
                    </Button>
                  </Form.Item>
                </Form>
              ),
            },
          ]}
        />
      </Card>

      <Modal
        title="隐私政策与用户协议"
        open={privacyModalOpen}
        onCancel={() => setPrivacyModalOpen(false)}
        footer={[
          <Button key="close" onClick={() => setPrivacyModalOpen(false)}>
            关闭
          </Button>,
        ]}
        width={520}
      >
        <Paragraph style={{ fontSize: 15, lineHeight: 1.8 }}>
          {PRIVACY_NOTICE_TEXT}
        </Paragraph>
      </Modal>
    </div>
  );
}
