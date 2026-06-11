import { Card, Form, Switch, Typography, Divider, Modal, Space } from 'antd';
import { ExclamationCircleOutlined } from '@ant-design/icons';
import { useTheme } from '../hooks/useTheme';
import { useElderlyMode } from '../contexts/ElderlyModeContext';

const { Title, Text } = Typography;

export default function SettingsPage() {
  const { isDark, toggleTheme } = useTheme();
  const { isElderlyMode, setElderly } = useElderlyMode();

  const handleElderlyToggle = (checked: boolean) => {
    if (checked) {
      Modal.confirm({
        title: '切换到长辈模式',
        icon: <ExclamationCircleOutlined />,
        content: '将切换到简化界面（3个功能标签、大字体），适合长辈使用。确定要切换吗？',
        okText: '确定切换',
        cancelText: '取消',
        onOk: () => setElderly(true),
      });
    } else {
      setElderly(false);
    }
  };

  return (
    <div>
      <Title level={3}>设置</Title>
      <Card title="显示设置">
        <Form layout="vertical">
          <Form.Item label="深色模式">
            <Switch checked={isDark} onChange={toggleTheme} />
          </Form.Item>
          <Divider />
          <Form.Item
            label={
              <Space>
                <Text strong>长辈模式</Text>
                <Text type="secondary">简化界面 · 大字体 · 3个功能</Text>
              </Space>
            }
          >
            <Switch checked={isElderlyMode} onChange={handleElderlyToggle} />
          </Form.Item>
        </Form>
      </Card>
      <Divider />
      <Card title="关于">
        <p>家庭医生 · 您的养生助手</p>
        <p>版本：0.2.0</p>
      </Card>
    </div>
  );
}
