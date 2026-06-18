import { useState } from 'react';
import {
  Card,
  Row,
  Col,
  Input,
  Select,
  Button,
  Tag,
  Typography,
  Space,
  Empty,
  Alert,
  Divider,
  Spin,
  Tooltip,
} from 'antd';
import {
  PlusOutlined,
  ThunderboltOutlined,
  CoffeeOutlined,
  ExperimentOutlined,
  SafetyCertificateOutlined,
  WarningOutlined,
  CloseOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import {
  recommendHerbs,
  generateTeaRecipe,
  recommendFromInventory,
  CONSTITUTIONS,
  type HerbRecommendation,
  type RecommendResponse,
  type TeaRecipeResponse,
  type FromInventoryResponse,
} from '../api/formulationApi';

const { Title, Text, Paragraph } = Typography;

const COMMON_SYMPTOMS = [
  '气虚乏力',
  '失眠多梦',
  '食欲不振',
  '腰膝酸软',
  '头晕目眩',
  '咳嗽痰多',
  '口干口苦',
  '手脚冰凉',
];

export default function FormulationPage() {
  const navigate = useNavigate();
  const [symptoms, setSymptoms] = useState<string[]>([]);
  const [symptomInput, setSymptomInput] = useState('');
  const [constitution, setConstitution] = useState<string | undefined>(undefined);

  const [recLoading, setRecLoading] = useState(false);
  const [recResult, setRecResult] = useState<RecommendResponse | null>(null);

  const [teaLoading, setTeaLoading] = useState(false);
  const [teaResult, setTeaResult] = useState<TeaRecipeResponse | null>(null);

  const [invLoading, setInvLoading] = useState(false);
  const [invResult, setInvResult] = useState<FromInventoryResponse | null>(null);

  const canSubmit = symptoms.length > 0;

  const addSymptom = (value: string) => {
    const v = value.trim();
    if (v && !symptoms.includes(v)) {
      setSymptoms((prev) => [...prev, v]);
    }
    setSymptomInput('');
  };

  const removeSymptom = (s: string) => {
    setSymptoms((prev) => prev.filter((x) => x !== s));
  };

  const handleRecommend = async () => {
    if (!canSubmit) return;
    setRecLoading(true);
    setRecResult(null);
    try {
      const res = await recommendHerbs({
        symptoms,
        constitution,
      });
      setRecResult(res);
    } finally {
      setRecLoading(false);
    }
  };

  const handleTeaRecipe = async () => {
    if (!canSubmit) return;
    setTeaLoading(true);
    setTeaResult(null);
    try {
      const res = await generateTeaRecipe({ symptoms, constitution });
      setTeaResult(res);
    } finally {
      setTeaLoading(false);
    }
  };

  const handleFromInventory = async () => {
    if (!canSubmit) return;
    setInvLoading(true);
    setInvResult(null);
    try {
      const res = await recommendFromInventory({ symptoms });
      setInvResult(res);
    } finally {
      setInvLoading(false);
    }
  };

  return (
    <div>
      {/* 页头 */}
      <Title level={3} style={{ marginBottom: 16 }}>
        <Space>
          <ExperimentOutlined style={{ color: '#722ed1' }} />
          智能配伍
        </Space>
      </Title>
      <Paragraph type="secondary" style={{ fontSize: 15, marginBottom: 20 }}>
        根据症状与体质智能推荐中药组合，一键生成代茶饮配方，或从家庭药箱中筛选可用药品。
      </Paragraph>

      {/* 输入区 */}
      <Card
        style={{ marginBottom: 20, borderRadius: 12, borderColor: '#d3adf7' }}
        styles={{ body: { padding: 24 } }}
      >
        {/* 症状标签输入 */}
        <div style={{ marginBottom: 8 }}>
          <Text strong style={{ fontSize: 16 }}>
            症状描述
          </Text>
          <Text type="secondary" style={{ marginLeft: 8 }}>
            输入后按回车添加
          </Text>
        </div>
        <Input
          size="large"
          placeholder="如：气虚乏力、失眠多梦"
          value={symptomInput}
          onChange={(e) => setSymptomInput(e.target.value)}
          onPressEnter={(e) => addSymptom(e.currentTarget.value)}
          suffix={
            symptomInput ? (
              <PlusOutlined
                style={{ color: '#722ed1', cursor: 'pointer' }}
                onClick={() => addSymptom(symptomInput)}
              />
            ) : null
          }
        />

        {/* 快捷症状 */}
        <div style={{ marginTop: 10 }}>
          <Space wrap size={[6, 6]}>
            <Text type="secondary" style={{ fontSize: 13 }}>
              常见：
            </Text>
            {COMMON_SYMPTOMS.filter((s) => !symptoms.includes(s)).map((s) => (
              <Tag
                key={s}
                style={{ cursor: 'pointer', fontSize: 14 }}
                onClick={() => addSymptom(s)}
              >
                <PlusOutlined /> {s}
              </Tag>
            ))}
          </Space>
        </div>

        {/* 已选症状 */}
        {symptoms.length > 0 && (
          <div style={{ marginTop: 12 }}>
            <Space wrap size={[6, 6]}>
              {symptoms.map((s) => (
                <Tag
                  key={s}
                  color="purple"
                  closable
                  closeIcon={<CloseOutlined />}
                  onClose={(e) => {
                    e.preventDefault();
                    removeSymptom(s);
                  }}
                  style={{ fontSize: 15, padding: '2px 8px' }}
                >
                  {s}
                </Tag>
              ))}
            </Space>
          </div>
        )}

        {/* 体质选择 */}
        <Divider style={{ margin: '16px 0' }} />
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <Text strong style={{ fontSize: 16 }}>
            体质类型
          </Text>
          <Select
            placeholder="选择体质（可选）"
            allowClear
            style={{ width: 200 }}
            size="large"
            value={constitution}
            onChange={(v) => setConstitution(v)}
            options={CONSTITUTIONS.map((c) => ({ label: c, value: c }))}
          />
        </div>

        {/* 操作按钮 */}
        <Row gutter={[12, 12]} style={{ marginTop: 20 }}>
          <Col xs={24} sm={8}>
            <Button
              type="primary"
              size="large"
              block
              icon={<ThunderboltOutlined />}
              loading={recLoading}
              disabled={!canSubmit}
              onClick={handleRecommend}
            >
              推荐中药
            </Button>
          </Col>
          <Col xs={24} sm={8}>
            <Button
              size="large"
              block
              icon={<CoffeeOutlined />}
              loading={teaLoading}
              disabled={!canSubmit}
              onClick={handleTeaRecipe}
            >
              生成代茶饮配方
            </Button>
          </Col>
          <Col xs={24} sm={8}>
            <Button
              size="large"
              block
              icon={<ExperimentOutlined />}
              loading={invLoading}
              disabled={!canSubmit}
              onClick={handleFromInventory}
            >
              从药箱推荐
            </Button>
          </Col>
        </Row>
      </Card>

      {/* 结果区：推荐中药 */}
      {recLoading && <ResultSectionLoading title="正在为您匹配中药…" />}
      {recResult && (
        <ResultCard
          title="推荐中药"
          icon={<ThunderboltOutlined style={{ color: '#722ed1' }} />}
          extra={
            <SafetyCheckButton
              safe={recResult.safetyCheck.safe}
              warningCount={recResult.safetyCheck.warnings.length}
              onClick={() => navigate('/safety')}
            />
          }
        >
          <SafetyBanner safety={recResult.safetyCheck} style={{ marginBottom: 12 }} />
          {recResult.recommendations.length === 0 ? (
            <Empty description="未找到匹配症状的中药，请调整症状描述" />
          ) : (
            <Row gutter={[12, 12]}>
              {recResult.recommendations.map((h) => (
                <Col xs={24} sm={12} lg={8} key={h.id}>
                  <HerbCard herb={h} />
                </Col>
              ))}
            </Row>
          )}
          <Disclaimer text={recResult.disclaimer} />
        </ResultCard>
      )}

      {/* 结果区：代茶饮配方 */}
      {teaLoading && <ResultSectionLoading title="正在生成代茶饮配方…" />}
      {teaResult && (
        <ResultCard
          title={teaResult.name}
          icon={<CoffeeOutlined style={{ color: '#d48806' }} />}
          extra={
            <SafetyCheckButton
              safe={teaResult.safetyCheck.safe}
              warningCount={teaResult.safetyCheck.warnings.length}
              onClick={() => navigate('/safety')}
            />
          }
        >
          <SafetyBanner safety={teaResult.safetyCheck} style={{ marginBottom: 12 }} />
          <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
            {teaResult.herbs.map((h, i) => (
              <Col xs={12} sm={8} key={`${h.name}-${i}`}>
                <Card
                  size="small"
                  style={{ textAlign: 'center', borderRadius: 10 }}
                  styles={{ body: { padding: 16 } }}
                >
                  <Tag color={h.role === '君药' ? 'gold' : 'default'}>
                    {h.role}
                  </Tag>
                  <div style={{ fontSize: 20, fontWeight: 600, margin: '8px 0 4px' }}>
                    {h.name}
                  </div>
                  <Text type="secondary">{h.doseG}g</Text>
                </Card>
              </Col>
            ))}
          </Row>
          {teaResult.efficacy && (
            <Alert
              type="success"
              message="功效"
              description={teaResult.efficacy}
              style={{ marginBottom: 12 }}
            />
          )}
          <Divider orientation="left" plain>
            <Text strong>冲泡方法</Text>
          </Divider>
          <pre
            style={{
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
              fontSize: 15,
              lineHeight: 1.9,
              background: '#fffbe6',
              padding: 16,
              borderRadius: 8,
              margin: 0,
              fontFamily: 'inherit',
            }}
          >
            {teaResult.brewing}
          </pre>
          <Disclaimer text={teaResult.disclaimer} />
        </ResultCard>
      )}

      {/* 结果区：药箱推荐 */}
      {invLoading && <ResultSectionLoading title="正在扫描您的药箱…" />}
      {invResult && (
        <ResultCard
          title="药箱推荐"
          icon={<ExperimentOutlined style={{ color: '#08979c' }} />}
          extra={
            <SafetyCheckButton
              safe={invResult.safetyCheck.safe}
              warningCount={invResult.safetyCheck.warnings.length}
              onClick={() => navigate('/safety')}
            />
          }
        >
          <SafetyBanner safety={invResult.safetyCheck} style={{ marginBottom: 12 }} />
          {invResult.recommendations.length === 0 ? (
            <Empty description="药箱中暂无匹配症状的药品" />
          ) : (
            <>
              <Text strong style={{ display: 'block', marginBottom: 8 }}>
                药箱中可用药品
              </Text>
              <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
                {invResult.recommendations.map((r, i) => (
                  <Col xs={24} sm={12} key={`${r.name}-${i}`}>
                    <Card size="small" style={{ borderRadius: 10 }}>
                      <Space direction="vertical" size={4} style={{ width: '100%' }}>
                        <div
                          style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                          }}
                        >
                          <Text strong style={{ fontSize: 16 }}>
                            {r.name}
                          </Text>
                          <Tag color="green">{r.source}</Tag>
                        </div>
                        <Text type="secondary" style={{ fontSize: 14 }}>
                          {r.reason}
                        </Text>
                      </Space>
                    </Card>
                  </Col>
                ))}
              </Row>
            </>
          )}
          {invResult.missingSuggestions.length > 0 && (
            <>
              <Divider orientation="left" plain>
                <Text strong>建议补充的中药</Text>
              </Divider>
              <Row gutter={[12, 12]}>
                {invResult.missingSuggestions.map((h) => (
                  <Col xs={24} sm={12} lg={8} key={h.id}>
                    <HerbCard herb={h} />
                  </Col>
                ))}
              </Row>
            </>
          )}
          <Disclaimer text={invResult.disclaimer} />
        </ResultCard>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ResultCard({
  title,
  icon,
  extra,
  children,
}: {
  title: string;
  icon: React.ReactNode;
  extra?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <Card
      style={{ marginBottom: 20, borderRadius: 12 }}
      title={
        <Space>
          {icon}
          <span style={{ fontSize: 18 }}>{title}</span>
        </Space>
      }
      extra={extra}
      styles={{ body: { padding: 20 } }}
    >
      {children}
    </Card>
  );
}

function ResultSectionLoading({ title }: { title: string }) {
  return (
    <Card style={{ marginBottom: 20, borderRadius: 12, textAlign: 'center' }} styles={{ body: { padding: 40 } }}>
      <Spin tip={title} size="large">
        <div style={{ minHeight: 80 }} />
      </Spin>
    </Card>
  );
}

function HerbCard({ herb }: { herb: HerbRecommendation }) {
  const dosage =
    herb.dosageMinG != null && herb.dosageMaxG != null
      ? `${herb.dosageMinG}-${herb.dosageMaxG}g`
      : '—';
  return (
    <Card
      size="small"
      style={{ borderRadius: 10, height: '100%' }}
      styles={{ body: { padding: 14 } }}
    >
      <Space direction="vertical" size={6} style={{ width: '100%' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
          <Text strong style={{ fontSize: 17, color: '#531dab' }}>
            {herb.name}
          </Text>
          {herb.toxicity && herb.toxicity !== '无毒' && (
            <Tag color="orange">{herb.toxicity}</Tag>
          )}
        </div>
        {herb.category && (
          <Tag style={{ alignSelf: 'flex-start' }}>{herb.category}</Tag>
        )}
        <Paragraph
          style={{ fontSize: 14, marginBottom: 0 }}
          ellipsis={{ rows: 2 }}
        >
          {herb.efficacy}
        </Paragraph>
        <div
          style={{
            background: '#f9f0ff',
            borderRadius: 6,
            padding: '6px 10px',
            fontSize: 13,
            color: '#531dab',
          }}
        >
          <Space align="start">
            <Tooltip title="推荐理由">
              <SafetyCertificateOutlined />
            </Tooltip>
            <span>{herb.reason}</span>
          </Space>
        </div>
        <div style={{ display: 'flex', gap: 12, fontSize: 13, flexWrap: 'wrap' }}>
          <span>
            <Text type="secondary">用量：</Text>
            {dosage}
          </span>
          {herb.nature && (
            <span>
              <Text type="secondary">性：</Text>
              {herb.nature}
            </span>
          )}
        </div>
      </Space>
    </Card>
  );
}

function SafetyBanner({
  safety,
  style,
}: {
  safety: RecommendResponse['safetyCheck'];
  style?: React.CSSProperties;
}) {
  if (safety.safe && safety.warnings.length === 0) {
    return (
      <Alert
        type="success"
        showIcon
        icon={<SafetyCertificateOutlined />}
        message="五层安全检查通过：未发现配伍禁忌、剂量超标或特殊人群风险。"
        style={style}
      />
    );
  }
  return (
    <Alert
      type="error"
      showIcon
      icon={<WarningOutlined />}
      message={`检测到 ${safety.warnings.length} 项安全提示，请仔细阅读`}
      description={
        <ul style={{ margin: 0, paddingLeft: 20, fontSize: 14 }}>
          {safety.warnings.slice(0, 3).map((w, i) => (
            <li key={i}>
              <Text strong>[{w.layer}]</Text> {w.title}：{w.detail}
            </li>
          ))}
          {safety.warnings.length > 3 && (
            <li>
              <Text type="secondary">
                …还有 {safety.warnings.length - 3} 项，请前往安全检查查看详情
              </Text>
            </li>
          )}
        </ul>
      }
      style={style}
    />
  );
}

function SafetyCheckButton({
  safe,
  warningCount,
  onClick,
}: {
  safe: boolean;
  warningCount: number;
  onClick: () => void;
}) {
  return (
    <Button
      type={safe ? 'default' : 'primary'}
      danger={!safe}
      icon={<SafetyCertificateOutlined />}
      onClick={onClick}
    >
      安全检查{warningCount > 0 ? `（${warningCount}项提示）` : ''}
    </Button>
  );
}

function Disclaimer({ text }: { text: string }) {
  return (
    <Paragraph
      type="secondary"
      style={{ fontSize: 13, marginTop: 16, marginBottom: 0 }}
    >
      <WarningOutlined style={{ marginRight: 4 }} />
      {text}
    </Paragraph>
  );
}
