import { useState, useEffect, useRef } from 'react';
import {
  Input,
  Button,
  Card,
  Typography,
  Space,
  Alert,
  Spin,
  Switch,
  Tooltip,
  Collapse,
  Skeleton,
  message,
} from 'antd';
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
import {
  sendMessage,
  sendMessageStream,
  sendMessageWithImage,
  getChatHistory,
  type ChatMessage,
  type ReasoningStep,
} from '../api/chatApi';
import { saveKnowledgeCard } from '../api/favoriteApi';
import { useSpeechRecognition } from '../hooks/useSpeechRecognition';
import { useSpeechSynthesis } from '../hooks/useSpeechSynthesis';

const { Title, Text } = Typography;
const { TextArea } = Input;

const MAX_IMAGE_SIZE = 10 * 1024 * 1024;

const TREATMENT_ADVICE_KEYWORDS = [
  '建议服用',
  '推荐用药',
  '可以尝试',
  '建议使用',
  '方剂推荐',
];

const containsTreatmentAdvice = (content: string): boolean =>
  TREATMENT_ADVICE_KEYWORDS.some((kw) => content.includes(kw));

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  /** True only while SSE chunks are actively being appended (typing dots). */
  const [streaming, setStreaming] = useState(false);
  /** True while the conversation history is being fetched on mount. */
  const [historyLoading, setHistoryLoading] = useState(true);
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

  // ---------------------------------------------------------------------------
  // Enhancement 1 — restore the latest conversation on mount so messages are
  // not lost on refresh. Fails silently to the welcome state.
  // ---------------------------------------------------------------------------
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const history = await getChatHistory();
        if (cancelled) return;
        if (history.length > 0) {
          setMessages(history);
        }
      } catch {
        // silent fallback — show welcome message instead
      } finally {
        if (!cancelled) setHistoryLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

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
          next[assistantIdx] = {
            role: 'assistant',
            content: resp.reply,
            warnings,
            ...(resp.reasoning_trace?.length
              ? { reasoning_trace: resp.reasoning_trace }
              : {}),
          };
          return next;
        });
        if (ttsEnabled) speak(resp.reply);
      } else {
        let fullContent = '';
        let reasoningTrace: ReasoningStep[] | undefined;
        setStreaming(true);
        try {
          for await (const chunk of sendMessageStream(text, messages)) {
            if (chunk.content !== undefined) {
              fullContent += chunk.content;
              setMessages((prev) => {
                const next = [...prev];
                next[assistantIdx] = { role: 'assistant', content: fullContent };
                return next;
              });
            }
            // Backend may attach reasoning_trace to the terminating event.
            if (chunk.reasoning_trace) {
              reasoningTrace = chunk.reasoning_trace;
            }
          }
        } finally {
          setStreaming(false);
        }

        // Enhancement 3 — graceful fallback to non-streaming when nothing
        // arrived, and surface an error if even the fallback is empty.
        if (!fullContent) {
          const resp = await sendMessage(text, messages);
          const warnings = resp.safety_warning ? [resp.safety_warning] : undefined;
          if (resp.reasoning_trace?.length) {
            reasoningTrace = resp.reasoning_trace;
          }
          fullContent = resp.reply;
          setMessages((prev) => {
            const next = [...prev];
            next[assistantIdx] = {
              role: 'assistant',
              content: fullContent,
              warnings,
              ...(reasoningTrace ? { reasoning_trace: reasoningTrace } : {}),
            };
            return next;
          });
        } else if (reasoningTrace) {
          // Attach reasoning trace captured during streaming.
          setMessages((prev) => {
            const next = [...prev];
            if (next[assistantIdx]) {
              next[assistantIdx] = {
                ...next[assistantIdx],
                reasoning_trace: reasoningTrace,
              };
            }
            return next;
          });
        }

        if (!fullContent) {
          setMessages((prev) => {
            const next = [...prev];
            if (next[assistantIdx]) {
              next[assistantIdx] = {
                role: 'assistant',
                content: '抱歉，未能获取回复内容，请稍后重试。',
              };
            }
            return next;
          });
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
            next[assistantIdx] = {
              role: 'assistant',
              content: resp.reply,
              warnings,
              ...(resp.reasoning_trace?.length
                ? { reasoning_trace: resp.reasoning_trace }
                : {}),
            };
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
      setStreaming(false);
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
        {historyLoading && messages.length === 0 ? (
          <div style={{ padding: 16 }}>
            <Skeleton active paragraph={{ rows: 3 }} />
          </div>
        ) : messages.length === 0 ? (
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
                    {/* Enhancement 3 — typing indicator while streaming this turn */}
                    {streaming &&
                      msg.role === 'assistant' &&
                      idx === messages.length - 1 && (
                        <span className="typing-dots" aria-hidden>
                          <span className="typing-dot" />
                          <span className="typing-dot" style={{ animationDelay: '0.15s' }} />
                          <span className="typing-dot" style={{ animationDelay: '0.3s' }} />
                        </span>
                      )}
                  </div>
                  {/* Enhancement 2 — expandable reasoning trace */}
                  {msg.role === 'assistant' &&
                    msg.reasoning_trace &&
                    msg.reasoning_trace.length > 0 && (
                      <Collapse
                        ghost
                        size="small"
                        style={{ marginTop: 8 }}
                        items={[
                          {
                            key: 'reasoning',
                            label: (
                              <Text type="secondary" style={{ fontSize: 13 }}>
                                🧠 AI 推理过程
                              </Text>
                            ),
                            children: (
                              <Space direction="vertical" size={6} style={{ width: '100%' }}>
                                {msg.reasoning_trace.map((t, ti) => (
                                  <div key={ti}>
                                    <Text type="secondary" style={{ fontSize: 12 }}>
                                      步骤 {ti + 1}：{t.step}
                                    </Text>
                                    <div
                                      style={{
                                        background: '#f5f5f5',
                                        borderRadius: 4,
                                        padding: '4px 8px',
                                        fontSize: 12,
                                        color: '#666',
                                        marginTop: 2,
                                        lineHeight: 1.6,
                                        wordBreak: 'break-word',
                                      }}
                                    >
                                      {t.result}
                                    </div>
                                  </div>
                                ))}
                              </Space>
                            ),
                          },
                        ]}
                      />
                    )}
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
                  {msg.role === 'assistant' &&
                    msg.content &&
                    containsTreatmentAdvice(msg.content) && (
                      <Alert
                        type="warning"
                        showIcon
                        message="⚠️ 以上建议涉及用药，请务必咨询专业医师后使用。"
                        style={{ marginTop: 6, padding: '4px 12px', fontSize: 13 }}
                      />
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
            {loading && !streaming && (
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
        .typing-dots {
          display: inline-flex;
          align-items: center;
          gap: 3px;
          margin-left: 4px;
          vertical-align: middle;
        }
        .typing-dot {
          width: 6px;
          height: 6px;
          border-radius: 50%;
          background: #1890ff;
          display: inline-block;
          animation: typing-bounce 1s infinite ease-in-out;
        }
        @keyframes typing-bounce {
          0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
          30% { transform: translateY(-4px); opacity: 1; }
        }
      `}</style>
    </div>
  );
}
