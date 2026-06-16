import { useState, useEffect, useRef } from 'react';
import { Input, Button, Card, Typography, Space, Alert, Spin, Switch, Tooltip, message } from 'antd';
import {
  SendOutlined,
  RobotOutlined,
  UserOutlined,
  AudioOutlined,
  AudioMutedOutlined,
  SoundOutlined,
  SaveOutlined,
  PictureOutlined,
  CloseOutlined,
} from '@ant-design/icons';
import { sendMessage, sendMessageStream, sendMessageWithImage, type ChatMessage } from '../api/chatApi';
import { saveKnowledgeCard } from '../api/favoriteApi';
import { useSpeechRecognition } from '../hooks/useSpeechRecognition';
import { useSpeechSynthesis } from '../hooks/useSpeechSynthesis';

const { Title, Text } = Typography;
const { TextArea } = Input;

const MAX_IMAGE_SIZE = 10 * 1024 * 1024;

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [ttsEnabled, setTtsEnabled] = useState(false);
  const [savedCards, setSavedCards] = useState<Set<number>>(new Set());
  const [pendingImage, setPendingImage] = useState<File | null>(null);
  const [imagePreview, setImagePreview] = useState<string>('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { isListening, transcript, startListening, stopListening, isSupported: micSupported, error: micError } =
    useSpeechRecognition();
  const { speak, cancel, isSpeaking, isSupported: ttsSupported } = useSpeechSynthesis();

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    if (transcript) {
      setInput(transcript);
    }
  }, [transcript]);

  const wasListeningRef = useRef(false);
  useEffect(() => {
    if (isListening) {
      wasListeningRef.current = true;
    }
    if (!isListening && wasListeningRef.current && transcript) {
      wasListeningRef.current = false;
    }
  }, [isListening, transcript]);

  useEffect(() => {
    return () => {
      if (imagePreview) URL.revokeObjectURL(imagePreview);
    };
  }, [imagePreview]);

  const handleSelectImage = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!file.type.startsWith('image/')) {
      message.error('请选择图片文件');
      return;
    }
    if (file.size > MAX_IMAGE_SIZE) {
      message.error('图片大小不能超过 10MB');
      return;
    }
    if (imagePreview) URL.revokeObjectURL(imagePreview);
    setPendingImage(file);
    setImagePreview(URL.createObjectURL(file));
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleRemoveImage = () => {
    if (imagePreview) URL.revokeObjectURL(imagePreview);
    setPendingImage(null);
    setImagePreview('');
  };

  const handleSend = async () => {
    if ((!input.trim() && !pendingImage) || loading) return;

    const text = input.trim() || '请帮我看看这张图片';
    const userMessage: ChatMessage = {
      role: 'user',
      content: text,
      ...(imagePreview ? { image: imagePreview } : {}),
    };
    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    const sentImage = pendingImage;
    const sentPreview = imagePreview;
    setPendingImage(null);
    setImagePreview('');
    setLoading(true);

    const assistantIdx = messages.length + 1;
    setMessages((prev) => [...prev, { role: 'assistant', content: '' }]);

    try {
      if (sentImage) {
        const resp = await sendMessageWithImage(text, sentImage);
        const warnings = resp.safety_warning ? [resp.safety_warning] : undefined;
        setMessages((prev) => {
          const next = [...prev];
          next[assistantIdx] = { role: 'assistant', content: resp.reply, warnings };
          return next;
        });
        if (ttsEnabled) speak(resp.reply);
      } else {
        let fullContent = '';
        for await (const chunk of sendMessageStream(text, messages)) {
          fullContent += chunk;
          setMessages((prev) => {
            const next = [...prev];
            next[assistantIdx] = { role: 'assistant', content: fullContent };
            return next;
          });
        }
        if (!fullContent) {
          const resp = await sendMessage(text, messages);
          const warnings = resp.safety_warning ? [resp.safety_warning] : undefined;
          setMessages((prev) => {
            const next = [...prev];
            next[assistantIdx] = { role: 'assistant', content: resp.reply, warnings };
            return next;
          });
          fullContent = resp.reply;
        }
        if (ttsEnabled && fullContent) speak(fullContent);
      }
    } catch {
      try {
        if (sentImage && sentPreview) {
          const resp = await sendMessageWithImage(text, sentImage);
          const warnings = resp.safety_warning ? [resp.safety_warning] : undefined;
          setMessages((prev) => {
            const next = [...prev];
            next[assistantIdx] = { role: 'assistant', content: resp.reply, warnings };
            return next;
          });
          if (ttsEnabled) speak(resp.reply);
        } else {
          throw new Error('fallback exhausted');
        }
      } catch {
        setMessages((prev) => {
          const next = [...prev];
          if (next[assistantIdx]) {
            next[assistantIdx] = { role: 'assistant', content: '抱歉，服务暂时不可用，请稍后再试。' };
          }
          return next;
        });
      }
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

  const handleSaveCard = async (idx: number, content: string) => {
    const title = content.slice(0, 20) + (content.length > 20 ? '...' : '');
    try {
      await saveKnowledgeCard({ title, content });
      setSavedCards((prev) => new Set(prev).add(idx));
      message.success('已保存为知识卡片');
    } catch {
      message.error('保存失败');
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
          height: 'calc(100vh - 320px)',
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
            <p>欢迎使用AI健康助手，请输入、语音或拍照提问</p>
            <p style={{ fontSize: 12, color: '#bbb' }}>
              支持文字、语音、图片提问（如药品说明书、化验单）
            </p>
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
                  {msg.image && (
                    <div style={{ marginBottom: 8 }}>
                      <img
                        src={msg.image}
                        alt="用户上传"
                        style={{ maxWidth: '100%', borderRadius: 4, maxHeight: 200 }}
                      />
                    </div>
                  )}
                  <div style={{ marginBottom: msg.warnings && msg.warnings.length > 0 ? 8 : 0 }}>
                    <span style={{ marginRight: 8 }}>
                      {msg.role === 'assistant' ? <RobotOutlined /> : <UserOutlined />}
                    </span>
                    <Text style={{ whiteSpace: 'pre-wrap' }}>{msg.content}</Text>
                  </div>
                  {msg.role === 'assistant' && idx > 0 && msg.content && (
                    <div style={{ marginTop: 4, textAlign: 'right' }}>
                      <Button
                        type="text"
                        size="small"
                        icon={<SaveOutlined />}
                        disabled={savedCards.has(idx)}
                        onClick={() => handleSaveCard(idx, msg.content)}
                      >
                        {savedCards.has(idx) ? '已保存' : '存为卡片'}
                      </Button>
                    </div>
                  )}
                  {msg.role === 'assistant' && msg.content && (
                    <div style={{ marginTop: 4 }}>
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        ⚠ 以上建议仅供参考，不能替代专业医疗诊断。用药请遵医嘱。
                      </Text>
                    </div>
                  )}
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

      {imagePreview && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            marginBottom: 8,
            padding: '4px 8px',
            background: '#f5f5f5',
            borderRadius: 4,
          }}
        >
          <img
            src={imagePreview}
            alt="待发送"
            style={{ width: 48, height: 48, objectFit: 'cover', borderRadius: 4 }}
          />
          <Text style={{ flex: 1, color: '#999' }}>
            {pendingImage?.name ?? '图片'} （{(pendingImage ? pendingImage.size / 1024 : 0).toFixed(0)}KB）
          </Text>
          <Button
            type="text"
            size="small"
            icon={<CloseOutlined />}
            onClick={handleRemoveImage}
          />
        </div>
      )}

      <input
        ref={fileInputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp,image/gif"
        onChange={handleSelectImage}
        style={{ display: 'none' }}
      />

      <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
        <Tooltip title="拍照提问">
          <Button
            shape="circle"
            size="large"
            icon={<PictureOutlined />}
            onClick={() => fileInputRef.current?.click()}
            style={{ width: 48, height: 48, flexShrink: 0 }}
          />
        </Tooltip>
        <TextArea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={
            pendingImage
              ? '描述您想了解的内容（可选）...'
              : isListening
                ? '正在聆听...'
                : '请输入您的健康问题...'
          }
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
