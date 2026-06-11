import { useState, useEffect, useRef } from 'react';
import { Input, Button, Card, Typography, Space, Alert, Spin, Switch, Tooltip } from 'antd';
import {
  SendOutlined,
  RobotOutlined,
  UserOutlined,
  AudioOutlined,
  AudioMutedOutlined,
  SoundOutlined,
} from '@ant-design/icons';
import { sendMessage, type ChatMessage } from '../api/chatApi';
import { useSpeechRecognition } from '../hooks/useSpeechRecognition';
import { useSpeechSynthesis } from '../hooks/useSpeechSynthesis';

const { Title, Text } = Typography;
const { TextArea } = Input;

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [ttsEnabled, setTtsEnabled] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const { isListening, transcript, startListening, stopListening, isSupported: micSupported, error: micError } =
    useSpeechRecognition();
  const { speak, cancel, isSpeaking, isSupported: ttsSupported } = useSpeechSynthesis();

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Update input from speech recognition transcript
  useEffect(() => {
    if (transcript) {
      setInput(transcript);
    }
  }, [transcript]);

  // Auto-stop listening → auto-send after a brief pause
  const wasListeningRef = useRef(false);
  useEffect(() => {
    if (isListening) {
      wasListeningRef.current = true;
    }
    if (!isListening && wasListeningRef.current && transcript) {
      wasListeningRef.current = false;
      // transcript already set in input, user can review and send
    }
  }, [isListening, transcript]);

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
      if (ttsEnabled) {
        speak(response.reply);
      }
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

  const toggleMic = () => {
    if (isListening) {
      stopListening();
    } else {
      setInput('');
      startListening();
    }
  };

  const toggleTts = (checked: boolean) => {
    setTtsEnabled(checked);
    if (!checked && isSpeaking) {
      cancel();
    }
  };

  return (
    <div>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 16,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <RobotOutlined style={{ fontSize: 24, marginRight: 8, color: '#1890ff' }} />
          <Title level={3} style={{ margin: 0 }}>
            AI 健康助手
          </Title>
        </div>
        {ttsSupported && (
          <Space>
            <SoundOutlined />
            <Tooltip title="开启后AI回复将语音播报">
              <Switch checked={ttsEnabled} onChange={toggleTts} checkedChildren="播报" unCheckedChildren="关闭" />
            </Tooltip>
          </Space>
        )}
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
            <p>欢迎使用AI健康助手，请输入或语音说出您的健康问题</p>
          </div>
        ) : (
          <Space direction="vertical" style={{ width: '100%' }} size="middle">
            {messages.map((msg, idx) => (
              <div key={idx}>
                <Card
                  size="small"
                  style={{
                    background: msg.role === 'user' ? '#e6f7ff' : '#f6ffed',
                    maxWidth: '80%',
                    marginLeft: msg.role === 'user' ? 'auto' : 0,
                    marginRight: msg.role === 'user' ? 0 : 'auto',
                  }}
                >
                  <div style={{ marginBottom: msg.warnings && msg.warnings.length > 0 ? 8 : 0 }}>
                    <span style={{ marginRight: 8 }}>
                      {msg.role === 'assistant' ? <RobotOutlined /> : <UserOutlined />}
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
              <Card size="small" style={{ background: '#f6ffed', maxWidth: '80%' }}>
                <Spin size="small" /> <RobotOutlined /> 正在思考...
              </Card>
            )}
            <div ref={messagesEndRef} />
          </Space>
        )}
      </div>

      {micError && (
        <Alert
          type="warning"
          message={micError}
          closable
          style={{ marginBottom: 8 }}
        />
      )}

      <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
        <TextArea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={isListening ? '正在聆听...' : '请输入您的健康问题...'}
          autoSize={{ minRows: 1, maxRows: 4 }}
          onPressEnter={(e) => {
            if (!e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
          style={isListening ? { borderColor: '#ff4d4f' } : undefined}
        />
        {micSupported && (
          <Tooltip title={isListening ? '点击停止' : '语音输入'}>
            <Button
              type={isListening ? 'primary' : 'default'}
              danger={isListening}
              shape="circle"
              size="large"
              icon={isListening ? <AudioMutedOutlined /> : <AudioOutlined />}
              onClick={toggleMic}
              style={{
                width: 48,
                height: 48,
                flexShrink: 0,
                animation: isListening ? 'pulse 1.5s infinite' : undefined,
              }}
            />
          </Tooltip>
        )}
        <Button
          type="primary"
          icon={<SendOutlined />}
          onClick={handleSend}
          loading={loading}
          style={{ height: 48 }}
        >
          发送
        </Button>
      </div>

      <style>{`
        @keyframes pulse {
          0% { box-shadow: 0 0 0 0 rgba(255, 77, 79, 0.4); }
          70% { box-shadow: 0 0 0 10px rgba(255, 77, 79, 0); }
          100% { box-shadow: 0 0 0 0 rgba(255, 77, 79, 0); }
        }
      `}</style>
    </div>
  );
}
