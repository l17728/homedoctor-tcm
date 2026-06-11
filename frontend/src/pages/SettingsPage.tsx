import { Card, Form, Switch, Typography, Divider } from 'antd';
import { useTheme } from '../hooks/useTheme';

const { Title } = Typography;

export default function SettingsPage() {
  const { isDark, toggleTheme } = useTheme();

  return (
    <div>
      <Title level={3}>设置</Title>
      <Card>
        <Form layout="vertical">
          <Form.Item label="深色模式">
            <Switch checked={isDark} onChange={toggleTheme} />
          </Form.Item>
        </Form>
      </Card>
      <Divider />
      <Card title="关于">
        <p>家庭医生 · 您的养生助手</p>
        <p>版本：0.1.0</p>
      </Card>
    </div>
  );
}
