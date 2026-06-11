import { useState, useEffect, useCallback } from 'react';
import {
  Button,
  Card,
  Typography,
  Space,
  Progress,
  Radio,
  Empty,
  Skeleton,
  Tag,
  Collapse,
  message,
} from 'antd';
import {
  CheckCircleOutlined,
  ReloadOutlined,
  HeartOutlined,
} from '@ant-design/icons';
import {
  getQuestionnaire,
  submitAssessment,
  getAssessmentHistory,
  type ConstitutionQuestion,
} from '../api/constitutionApi';
import type { AssessmentResponse } from '../api/constitutionApi';

const { Title, Text, Paragraph } = Typography;

const ANSWER_OPTIONS = [
  { label: '没有', value: 0 },
  { label: '很少', value: 1 },
  { label: '有时', value: 2 },
  { label: '经常', value: 3 },
  { label: '总是', value: 4 },
];

const CONSTITUTION_COLORS: Record<string, string> = {
  平和质: 'green',
  气虚质: 'gold',
  阳虚质: 'orange',
  阴虚质: 'volcano',
  痰湿质: 'cyan',
  湿热质: 'red',
  血瘀质: 'purple',
  气郁质: 'blue',
  特禀质: 'magenta',
};

const PAGE_SIZE = 8;

export default function ConstitutionPage() {
  const [questions, setQuestions] = useState<ConstitutionQuestion[]>([]);
  const [loading, setLoading] = useState(true);
  const [mode, setMode] = useState<'intro' | 'quiz' | 'result'>('intro');
  const [currentPage, setCurrentPage] = useState(0);
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const [result, setResult] = useState<AssessmentResponse | null>(null);
  const [history, setHistory] = useState<{ id: string; assessed_at: string; primary_type: string; secondary_types: string[] }[]>([]);
  const [submitting, setSubmitting] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [qs, hist] = await Promise.all([getQuestionnaire(), getAssessmentHistory()]);
      setQuestions(qs);
      setHistory(hist.map((h) => ({ id: h.id, assessed_at: h.assessed_at, primary_type: h.primary_type, secondary_types: h.secondary_types })));
    } catch {
      // handled
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const startQuiz = () => {
    setAnswers({});
    setCurrentPage(0);
    setMode('quiz');
  };

  const totalPages = Math.ceil(questions.length / PAGE_SIZE);
  const pageQuestions = questions.slice(currentPage * PAGE_SIZE, (currentPage + 1) * PAGE_SIZE);

  const handleAnswer = (qId: string, value: number) => {
    setAnswers((prev) => ({ ...prev, [qId]: value }));
  };

  const handleNext = () => {
    if (currentPage < totalPages - 1) {
      setCurrentPage((prev) => prev + 1);
    } else {
      handleSubmit();
    }
  };

  const handlePrev = () => {
    if (currentPage > 0) {
      setCurrentPage((prev) => prev - 1);
    }
  };

  const handleSubmit = async () => {
    setSubmitting(true);
    try {
      const res = await submitAssessment(answers);
      setResult(res);
      setMode('result');
      loadData();
      message.success('体质评估完成');
    } catch {
      message.error('提交失败，请重试');
    } finally {
      setSubmitting(false);
    }
  };

  const pageAnswered = pageQuestions.filter((q) => answers[q.id] !== undefined).length;
  const progressPercent = questions.length > 0 ? (Object.keys(answers).length / questions.length) * 100 : 0;

  if (loading) {
    return <Skeleton active />;
  }

  if (mode === 'intro') {
    return (
      <div>
        <Title level={3}>体质自测</Title>
        <Card>
          <div style={{ textAlign: 'center', padding: '40px 20px' }}>
            <HeartOutlined style={{ fontSize: 64, color: '#1890ff', marginBottom: 24 }} />
            <Title level={4}>王琦九种体质标准量表</Title>
            <Paragraph type="secondary">
              本测试基于中华中医药学会《中医体质分类与判定》标准，
              共{questions.length}道题，帮助您了解自己的体质类型。
              测试结果将用于个性化养生建议。
            </Paragraph>
            <Space direction="vertical" size="large">
              <div>
                <Tag color="green">平和质</Tag>
                <Tag color="gold">气虚质</Tag>
                <Tag color="orange">阳虚质</Tag>
                <Tag color="volcano">阴虚质</Tag>
                <Tag color="cyan">痰湿质</Tag>
                <Tag color="red">湿热质</Tag>
                <Tag color="purple">血瘀质</Tag>
                <Tag color="blue">气郁质</Tag>
                <Tag color="magenta">特禀质</Tag>
              </div>
              <Button type="primary" size="large" icon={<CheckCircleOutlined />} onClick={startQuiz}>
                开始测试（约5分钟）
              </Button>
            </Space>
          </div>
        </Card>

        {history.length > 0 && (
          <Card title="历史记录" style={{ marginTop: 24 }}>
            <Collapse
              items={history.map((h, i) => ({
                key: i,
                label: (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <Text>{h.assessed_at.slice(0, 10)}</Text>
                    <Tag color={CONSTITUTION_COLORS[h.primary_type] ?? 'default'}>
                      {h.primary_type}
                    </Tag>
                    {h.secondary_types.map((s) => (
                      <Tag key={s} color={CONSTITUTION_COLORS[s] ?? 'default'}>
                        兼：{s}
                      </Tag>
                    ))}
                  </div>
                ),
                children: (
                  <Button type="link" onClick={startQuiz}>
                    重新测试
                  </Button>
                ),
              }))}
            />
          </Card>
        )}
      </div>
    );
  }

  if (mode === 'quiz') {
    return (
      <div>
        <Title level={3}>体质自测</Title>
        <Progress percent={Math.round(progressPercent)} style={{ marginBottom: 24 }} />
        <div style={{ textAlign: 'center', marginBottom: 16 }}>
          <Text type="secondary">
            第 {currentPage + 1} / {totalPages} 页（已答 {pageAnswered}/{pageQuestions.length}）
          </Text>
        </div>
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          {pageQuestions.map((q) => (
            <Card key={q.id} size="small">
              <div style={{ marginBottom: 12 }}>
                <Tag color={CONSTITUTION_COLORS[q.type] ?? 'default'} style={{ marginRight: 8 }}>
                  {q.type}
                </Tag>
                <Text strong style={{ fontSize: 16 }}>{q.text}</Text>
              </div>
              <Radio.Group
                value={answers[q.id]}
                onChange={(e) => handleAnswer(q.id, e.target.value)}
                style={{ width: '100%' }}
              >
                <Space direction="vertical" style={{ width: '100%' }}>
                  {ANSWER_OPTIONS.map((opt) => (
                    <Radio key={opt.value} value={opt.value} style={{ fontSize: 16, padding: '4px 0' }}>
                      {opt.label}
                    </Radio>
                  ))}
                </Space>
              </Radio.Group>
            </Card>
          ))}
        </Space>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 24 }}>
          <Button onClick={handlePrev} disabled={currentPage === 0} size="large">
            上一页
          </Button>
          <Button
            type="primary"
            onClick={handleNext}
            loading={submitting}
            size="large"
          >
            {currentPage < totalPages - 1 ? '下一页' : '提交'}
          </Button>
        </div>
      </div>
    );
  }

  // mode === 'result'
  if (!result) {
    return <Empty description="无结果" />;
  }

  const sortedResults = Object.entries(result.results).sort(([, a], [, b]) => b - a);
  const maxScore = Math.max(...sortedResults.map(([, v]) => v), 1);

  return (
    <div>
      <Title level={3}>体质自测结果</Title>

      <Card style={{ marginBottom: 24 }}>
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <Tag color={CONSTITUTION_COLORS[result.primary_type] ?? 'blue'} style={{ fontSize: 20, padding: '8px 24px' }}>
            主体质：{result.primary_type}
          </Tag>
        </div>
        {result.secondary_types.length > 0 && (
          <div style={{ textAlign: 'center', marginBottom: 16 }}>
            <Text>兼夹体质：</Text>
            {result.secondary_types.map((s) => (
              <Tag key={s} color={CONSTITUTION_COLORS[s] ?? 'default'} style={{ marginLeft: 4 }}>
                {s}
              </Tag>
            ))}
          </div>
        )}
        <Paragraph type="secondary" style={{ textAlign: 'center' }}>
          {result.description}
        </Paragraph>
      </Card>

      <Card title="体质得分" style={{ marginBottom: 24 }}>
        <Space direction="vertical" style={{ width: '100%' }} size="small">
          {sortedResults.map(([type, score]) => (
            <div key={type} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <div style={{ width: 80, textAlign: 'right' }}>
                <Tag color={CONSTITUTION_COLORS[type] ?? 'default'}>{type}</Tag>
              </div>
              <div
                style={{
                  flex: 1,
                  height: 24,
                  background: '#f0f0f0',
                  borderRadius: 4,
                  overflow: 'hidden',
                }}
              >
                <div
                  style={{
                    width: `${(score / maxScore) * 100}%`,
                    height: '100%',
                    background:
                      score >= 60 ? '#ff4d4f' : score >= 40 ? '#faad14' : '#52c41a',
                    transition: 'width 0.5s',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'flex-end',
                    paddingRight: 8,
                    color: '#fff',
                    fontSize: 12,
                    fontWeight: 600,
                  }}
                >
                  {score.toFixed(0)}
                </div>
              </div>
            </div>
          ))}
        </Space>
      </Card>

      <div style={{ textAlign: 'center' }}>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={startQuiz} size="large">
            重新测试
          </Button>
        </Space>
      </div>
    </div>
  );
}
