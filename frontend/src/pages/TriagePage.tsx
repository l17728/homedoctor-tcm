import { useState, useEffect, useCallback } from 'react';
import type { ReactNode } from 'react';
import {
  Card,
  InputNumber,
  Radio,
  Checkbox,
  Button,
  Alert,
  Tag,
  Spin,
  Empty,
  Typography,
  Space,
  Divider,
  message,
} from 'antd';
import {
  AlertOutlined,
  ReloadOutlined,
  WarningOutlined,
  CheckCircleOutlined,
  InfoCircleOutlined,
} from '@ant-design/icons';
import { request, ApiError } from '../api/client';

const { Title, Paragraph, Text } = Typography;

// ---------------------------------------------------------------------------
// Types — mirror backend triage API (routers/triage.py + triage_data.py)
// ---------------------------------------------------------------------------

interface TriageQuestion {
  id: string;
  category: string;
  symptom: string;
  type: 'number' | 'choice';
  unit?: string;
  threshold?: number;
  options?: string[];
}

interface RedFlag {
  id: string;
  symptom: string;
  detail: string;
  action: string;
  max_age_months: number | null;
}

interface AgeGroupInfo {
  description: string;
  key_clinical_note: string;
  min_months?: number;
  max_months?: number;
  min_days?: number;
  max_days?: number;
}

interface QuestionnaireResponse {
  age_group: string;
  age_months: number | null;
  age_group_info: AgeGroupInfo;
  questions: TriageQuestion[];
  question_count: number;
  red_flags: RedFlag[];
  urgent_threshold: Record<string, unknown>;
  triage_levels: Record<string, Record<string, string>>;
  disclaimer: string;
}

interface TriageResult {
  level_key: string;
  level: string;
  color: string;
  action: string;
  time: string;
  age_group: string;
  age_months: number;
  warnings: string[];
  recommendations: string[];
  triggered_red_flags: RedFlag[];
  disclaimer: string;
}

// ---------------------------------------------------------------------------
// Color + icon maps — keyed by backend `color` field
// ---------------------------------------------------------------------------

const LEVEL_COLOR_HEX: Record<string, string> = {
  red: '#ff4d4f',
  orange: '#faad14',
  green: '#52c41a',
  blue: '#1890ff',
};

const LEVEL_ICON: Record<string, ReactNode> = {
  red: <WarningOutlined />,
  orange: <WarningOutlined />,
  green: <CheckCircleOutlined />,
  blue: <InfoCircleOutlined />,
};

const RESULT_DISCLAIMER =
  '本系统提供的分诊建议仅供参考，不能替代专业医疗诊断。如有疑问请立即就医。';

export default function TriagePage() {
  const [ageValue, setAgeValue] = useState<number | null>(null);
  const [ageUnit, setAgeUnit] = useState<'月龄' | '岁'>('月龄');
  const [questionnaire, setQuestionnaire] = useState<QuestionnaireResponse | null>(null);
  const [loadingQ, setLoadingQ] = useState(false);
  const [answers, setAnswers] = useState<Record<string, string | number>>({});
  const [checkedRedFlags, setCheckedRedFlags] = useState<string[]>([]);
  const [result, setResult] = useState<TriageResult | null>(null);
  const [assessing, setAssessing] = useState(false);

  const ageMonths: number | null = (() => {
    if (ageValue == null) return null;
    return ageUnit === '岁' ? ageValue * 12 : ageValue;
  })();

  const fetchQuestionnaire = useCallback(async (months: number) => {
    setLoadingQ(true);
    setResult(null);
    setAnswers({});
    try {
      const data = await request<QuestionnaireResponse>(
        `/api/triage/questionnaire?age_months=${months}`,
      );
      setQuestionnaire(data);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : '获取问卷失败';
      message.error(msg);
      setQuestionnaire(null);
    } finally {
      setLoadingQ(false);
    }
  }, []);

  useEffect(() => {
    if (ageMonths != null && ageMonths >= 0) {
      void fetchQuestionnaire(ageMonths);
    } else {
      setQuestionnaire(null);
    }
  }, [ageMonths, fetchQuestionnaire]);

  const handleAnswer = (qid: string, value: string | number) => {
    setAnswers((prev) => ({ ...prev, [qid]: value }));
  };

  const handleRedFlagToggle = (rfId: string) => {
    setCheckedRedFlags((prev) =>
      prev.includes(rfId) ? prev.filter((x) => x !== rfId) : [...prev, rfId],
    );
  };

  const handleAssess = async () => {
    if (ageMonths == null) {
      message.warning('请先输入年龄');
      return;
    }
    setAssessing(true);
    try {
      const answerList = questionnaire
        ? questionnaire.questions.map((q) => ({
            id: q.id,
            value: answers[q.id] ?? '',
          }))
        : [];
      const payload = {
        age_months: ageMonths,
        answers: answerList,
        red_flags: checkedRedFlags,
      };
      const res = await request<TriageResult>('/api/triage/assess', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      setResult(res);
      setTimeout(() => {
        document
          .getElementById('triage-result')
          ?.scrollIntoView({ behavior: 'smooth' });
      }, 50);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : '评估失败，请重试';
      message.error(msg);
    } finally {
      setAssessing(false);
    }
  };

  const handleReset = () => {
    setAgeValue(null);
    setAnswers({});
    setCheckedRedFlags([]);
    setResult(null);
    setQuestionnaire(null);
  };

  const redFlags = questionnaire?.red_flags ?? [];
  const hasAge = ageMonths != null && ageMonths >= 0;

  return (
    <div>
      <Title level={3}>
        <AlertOutlined style={{ marginRight: 8, color: '#ff4d4f' }} />
        急症分诊
      </Title>
      <Alert
        type="warning"
        showIcon
        message="本工具用于儿童急症初步判断，不能替代专业医疗诊断。如有危及生命的紧急情况，请立即拨打120。"
        style={{ marginBottom: 16 }}
      />

      {/* 第1步：年龄输入 */}
      <Card title="第1步：输入孩子年龄" style={{ marginBottom: 16 }}>
        <Space wrap>
          <InputNumber
            min={0}
            max={ageUnit === '岁' ? 14 : 168}
            value={ageValue ?? undefined}
            onChange={(v) => setAgeValue(v == null ? null : v)}
            placeholder="请输入"
            style={{ width: 140 }}
            size="large"
          />
          <Radio.Group
            value={ageUnit}
            onChange={(e) => setAgeUnit(e.target.value as '月龄' | '岁')}
            buttonStyle="solid"
            size="large"
          >
            <Radio.Button value="月龄">月龄</Radio.Button>
            <Radio.Button value="岁">岁</Radio.Button>
          </Radio.Group>
        </Space>
        {hasAge && questionnaire && (
          <div style={{ marginTop: 12 }}>
            <Tag color="blue">
              年龄组：{questionnaire.age_group}（{questionnaire.age_group_info.description}）
            </Tag>
          </div>
        )}
      </Card>

      {/* 第2步：红旗症状自查（年龄确定后始终可见） */}
      {hasAge && !loadingQ && (
        <Card
          title={
            <span>
              <WarningOutlined style={{ marginRight: 8, color: '#ff4d4f' }} />
              红旗症状自查（任一命中请立即就医）
            </span>
          }
          style={{ marginBottom: 16 }}
          styles={{ header: { background: '#fff1f0' } }}
        >
          {redFlags.length === 0 ? (
            <Empty description="暂无红旗症状数据" />
          ) : (
            <Space direction="vertical" style={{ width: '100%' }} size="small">
              {redFlags.map((rf) => (
                <Checkbox
                  key={rf.id}
                  checked={checkedRedFlags.includes(rf.id)}
                  onChange={() => handleRedFlagToggle(rf.id)}
                >
                  <Text strong style={{ fontSize: 16 }}>
                    {rf.symptom}
                  </Text>
                  <br />
                  <Text type="secondary">{rf.detail}</Text>
                  <br />
                  <Text type="danger" style={{ fontSize: 16, color: '#cf1322' }}>
                    建议：{rf.action}
                  </Text>
                </Checkbox>
              ))}
            </Space>
          )}
        </Card>
      )}

      {/* 第3步：症状问卷 */}
      {loadingQ && (
        <div style={{ textAlign: 'center', padding: 24 }}>
          <Spin tip="加载问卷中..." />
        </div>
      )}
      {!loadingQ && questionnaire && questionnaire.questions.length > 0 && (
        <Card
          title={`第3步：症状问卷（${questionnaire.question_count}题）`}
          style={{ marginBottom: 16 }}
        >
          <Paragraph type="secondary" style={{ fontSize: 14 }}>
            {questionnaire.age_group_info.key_clinical_note}
          </Paragraph>
          <Divider style={{ margin: '12px 0' }} />
          {questionnaire.questions.map((q) => (
            <div key={q.id} style={{ marginBottom: 16 }}>
              <Text strong style={{ fontSize: 16 }}>
                {q.symptom}
                {q.type === 'number' && q.unit ? `（${q.unit}）` : ''}
              </Text>
              <div style={{ marginTop: 8 }}>
                {q.type === 'number' ? (
                  <InputNumber
                    style={{ width: 160 }}
                    placeholder={`请输入${q.symptom}`}
                    value={
                      typeof answers[q.id] === 'number'
                        ? (answers[q.id] as number)
                        : undefined
                    }
                    onChange={(v) => handleAnswer(q.id, v == null ? '' : v)}
                  />
                ) : (
                  <Radio.Group
                    value={answers[q.id] ?? ''}
                    onChange={(e) => handleAnswer(q.id, e.target.value)}
                  >
                    {q.options?.map((opt) => (
                      <Radio key={opt} value={opt}>
                        {opt}
                      </Radio>
                    ))}
                  </Radio.Group>
                )}
              </div>
            </div>
          ))}
        </Card>
      )}

      {/* 评估按钮 */}
      {hasAge && (
        <Space style={{ marginBottom: 16 }}>
          <Button
            type="primary"
            size="large"
            icon={<AlertOutlined />}
            loading={assessing}
            onClick={handleAssess}
          >
            开始评估
          </Button>
          <Button size="large" icon={<ReloadOutlined />} onClick={handleReset}>
            重置
          </Button>
        </Space>
      )}

      {/* 分诊结果 */}
      {result && (
        <Card
          id="triage-result"
          style={{
            marginBottom: 16,
            borderColor: LEVEL_COLOR_HEX[result.color] ?? '#d9d9d9',
            borderWidth: 2,
          }}
          title={
            <span style={{ color: LEVEL_COLOR_HEX[result.color] ?? '#000' }}>
              {LEVEL_ICON[result.color] ?? <InfoCircleOutlined />}
              <span style={{ marginLeft: 8, fontSize: 20, fontWeight: 600 }}>
                分诊结果：{result.level}
              </span>
            </span>
          }
        >
          <div
            style={{
              background: `${LEVEL_COLOR_HEX[result.color] ?? '#1890ff'}15`,
              padding: 16,
              borderRadius: 8,
              marginBottom: 16,
            }}
          >
            <Paragraph style={{ fontSize: 18, marginBottom: 8 }}>
              <Text strong>建议行动：</Text>
              {result.action}
            </Paragraph>
            <Paragraph style={{ marginBottom: 0 }}>
              <Text strong>时间要求：</Text>
              {result.time}
            </Paragraph>
          </div>

          {result.warnings.length > 0 && (
            <>
              <Text strong>⚠️ 警示信息：</Text>
              <ul style={{ marginTop: 8, marginBottom: 16, paddingLeft: 20 }}>
                {result.warnings.map((w, i) => (
                  <li key={i}>
                    <Text>{w}</Text>
                  </li>
                ))}
              </ul>
            </>
          )}

          {result.recommendations.length > 0 && (
            <>
              <Text strong>✅ 建议：</Text>
              <ul style={{ marginTop: 8, marginBottom: 16, paddingLeft: 20 }}>
                {result.recommendations.map((r, i) => (
                  <li key={i}>
                    <Text>{r}</Text>
                  </li>
                ))}
              </ul>
            </>
          )}

          {result.triggered_red_flags.length > 0 && (
            <Alert
              type="error"
              showIcon
              style={{ marginBottom: 16 }}
              message="已触发红旗症状"
              description={
                <ul style={{ paddingLeft: 20, marginBottom: 0 }}>
                  {result.triggered_red_flags.map((rf) => (
                    <li key={rf.id}>
                      <Text strong>{rf.symptom}</Text>：{rf.detail} — {rf.action}
                    </li>
                  ))}
                </ul>
              }
            />
          )}

          <Alert type="warning" showIcon message={result.disclaimer ?? RESULT_DISCLAIMER} />
        </Card>
      )}
    </div>
  );
}
