import { useState, useEffect, useRef } from 'react';
import { Input, Button, Card, Typography, Space, Alert, Spin } from 'antd';
import { SendOutlined, RobotOutlined, UserOutlined } from '@ant-design/icons';
import { sendMessage, type ChatMessage } from '../api/chatApi';

const { Title, Text } = Typography;
const { TextArea } = Input;

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || loading) return;

    const userMessage: ChatMessage = { role: 'user', content: input.trim() };
    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setLoading(true);

    try {
      const response = await sendMessage(userMessage.content, messages);
      const aiMessage: ChatMessage = {
        role: 'assistant',
        content: response.reply,
        warnings: response.warnings,
      };
      setMessages((prev) => [...prev, aiMessage]);
    } catch {
      const aiMessage: ChatMessage = {
        role: 'assistant',
        content: '抱歉，服务暂时不可用，请稍后再试。',
      };
      setMessages((prev) => [...prev, aiMessage]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 16 }}>
        <RobotOutlined style={{ fontSize: 24, marginRight: 8, color: '#1890ff' }} />
        <Title level={3} style={{ margin: 0 }}>AI 健康助手</Title>
      </div>

      <div
        style={{
          height: 'calc(100vh - 300px)',
          overflowY: 'auto',
          marginBottom: 16,
          padding: 16,
          background: '#fafafa',
          borderRadius: 8,
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
              <div key={idx}>
                <Card
                  size="small"
                  style={{
                    background:
                      msg.role === 'user' ? '#e6f7ff' : '#f6ffed',
                    maxWidth: '80%',
                    marginLeft: msg.role === 'user' ? 'auto' : 0,
                    marginRight: msg.role === 'user' ? 0 : 'auto',
                  }}
                >
                  <div style={{ marginBottom: msg.warnings && msg.warnings.length > 0 ? 8 : 0 }}>
                    <span style={{ marginRight: 8 }}>
                      {msg.role === 'assistant' ? (
                        <RobotOutlined />
                      ) : (
                        <UserOutlined />
                      )}
                    </span>
                    <Text>{msg.content}</Text>
                  </div>
                  {msg.warnings && msg.warnings.length > 0 && (
                    <Alert
                      type="error"
                      showIcon
                      message="安全警告"
                      description={
                        <ul style={{ margin: 0, paddingLeft: 20 }}>
                          {msg.warnings.map((w, wi) => (
                            <li key={wi}>{w}</li>
                          ))}
                        </ul>
                      }
                      style={{ marginTop: 8 }}
                    />
                  )}
                </Card>
              </div>
            ))}
            {loading && (
              <Card
                size="small"
                style={{ background: '#f6ffed', maxWidth: '80%' }}
              >
                <Spin size="small" /> <RobotOutlined /> 正在思考...
              </Card>
            )}
            <div ref={messagesEndRef} />
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
