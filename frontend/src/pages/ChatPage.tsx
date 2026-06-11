import { useState } from 'react';
import { Input, Button, Card, Typography, Space } from 'antd';
import { SendOutlined, RobotOutlined, UserOutlined } from '@ant-design/icons';

const { Title } = Typography;
const { TextArea } = Input;

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSend = () => {
    if (!input.trim()) return;

    const userMessage: Message = { role: 'user', content: input.trim() };
    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setLoading(true);

    const query = userMessage.content;
    setTimeout(() => {
      const aiMessage: Message = {
        role: 'assistant',
        content: `您好！我是家庭医生AI助手。您询问的是关于"${query}"的问题。这是一个演示回复，实际使用时将连接到真实的AI服务。`,
      };
      setMessages((prev) => [...prev, aiMessage]);
      setLoading(false);
    }, 1000);
  };

  return (
    <div>
      <Title level={3}>AI 健康助手</Title>
      <div
        style={{
          height: 'calc(100vh - 280px)',
          overflowY: 'auto',
          marginBottom: 16,
          padding: 16,
        }}
      >
        {messages.length === 0 ? (
          <div style={{ textAlign: 'center', color: '#999', padding: 40 }}>
            <RobotOutlined style={{ fontSize: 48, marginBottom: 16 }} />
            <p>欢迎使用AI健康助手，请输入您的健康问题</p>
          </div>
        ) : (
          <Space
            direction="vertical"
            style={{ width: '100%' }}
            size="middle"
          >
            {messages.map((msg, idx) => (
              <Card
                key={idx}
                size="small"
                style={{
                  background:
                    msg.role === 'user' ? '#e6f7ff' : '#f6ffed',
                  maxWidth: '80%',
                  marginLeft: msg.role === 'user' ? 'auto' : 0,
                  marginRight: msg.role === 'user' ? 0 : 'auto',
                }}
              >
                <span style={{ marginRight: 8 }}>
                  {msg.role === 'assistant' ? (
                    <RobotOutlined />
                  ) : (
                    <UserOutlined />
                  )}
                </span>
                {msg.content}
              </Card>
            ))}
            {loading && (
              <Card
                size="small"
                style={{ background: '#f6ffed', maxWidth: '80%' }}
              >
                <RobotOutlined /> 正在思考...
              </Card>
            )}
          </Space>
        )}
      </div>
      <div style={{ display: 'flex', gap: 8 }}>
        <TextArea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="请输入您的健康问题..."
          autoSize={{ minRows: 1, maxRows: 4 }}
          onPressEnter={(e) => {
            if (!e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
        />
        <Button
          type="primary"
          icon={<SendOutlined />}
          onClick={handleSend}
          loading={loading}
        >
          发送
        </Button>
      </div>
    </div>
  );
}
