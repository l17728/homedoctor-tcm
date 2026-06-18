import { useState, useEffect, useCallback, useMemo, type ReactNode } from 'react';
import {
  Button,
  Select,
  Radio,
  Table,
  Typography,
  Space,
  Card,
  Alert,
  Empty,
  Spin,
  Tag,
  message,
} from 'antd';
import {
  SwapOutlined,
  SearchOutlined,
  CheckCircleOutlined,
  WarningOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons';
import { getHerbs, type Herb } from '../api/herbApi';
import { getFormulas, type Formula } from '../api/formulaApi';
import {
  compareHerbs,
  compareFormulas,
  type HerbComparisonResult,
  type FormulaComparisonResult,
  type ComparisonPropertyRow,
} from '../api/comparisonApi';

const { Title, Text } = Typography;

type CompareKind = 'herb' | 'formula';

const MIN_ITEMS = 2;
const MAX_ITEMS = 5;

const SAME_BG = '#f6ffed';
const DIFF_BG = '#fffbe6';
const WARNING_BG = '#fff2f0';

export default function ComparisonPage() {
  const [kind, setKind] = useState<CompareKind>('herb');
  const [herbOptions, setHerbOptions] = useState<Herb[]>([]);
  const [formulaOptions, setFormulaOptions] = useState<Formula[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [loadingOptions, setLoadingOptions] = useState(false);
  const [comparing, setComparing] = useState(false);
  const [herbResult, setHerbResult] = useState<HerbComparisonResult | null>(null);
  const [formulaResult, setFormulaResult] = useState<FormulaComparisonResult | null>(null);

  const loadOptions = useCallback(async () => {
    setLoadingOptions(true);
    try {
      if (kind === 'herb') {
        const { items } = await getHerbs({ pageSize: 300 });
        setHerbOptions(items);
      } else {
        const { items } = await getFormulas({ pageSize: 300 });
        setFormulaOptions(items);
      }
    } catch {
      // fallback handled inside API clients (mock data)
    } finally {
      setLoadingOptions(false);
    }
  }, [kind]);

  useEffect(() => {
    loadOptions();
  }, [loadOptions]);

  useEffect(() => {
    setSelectedIds([]);
    setHerbResult(null);
    setFormulaResult(null);
  }, [kind]);

  const options = useMemo(() => {
    const list = kind === 'herb' ? herbOptions : formulaOptions;
    return list.map((item) => ({ label: item.name, value: item.id }));
  }, [kind, herbOptions, formulaOptions]);

  const selectedNames = useMemo(() => {
    const list = kind === 'herb' ? herbOptions : formulaOptions;
    return selectedIds
      .map((id) => list.find((x) => x.id === id)?.name ?? '')
      .filter(Boolean);
  }, [selectedIds, kind, herbOptions, formulaOptions]);

  const canCompare = selectedIds.length >= MIN_ITEMS && selectedIds.length <= MAX_ITEMS;

  const handleCompare = async () => {
    if (!canCompare) {
      message.warning(`请选择 ${MIN_ITEMS}-${MAX_ITEMS} 个项目进行对比`);
      return;
    }
    setComparing(true);
    try {
      if (kind === 'herb') {
        const res = await compareHerbs(selectedIds);
        setHerbResult(res);
        setFormulaResult(null);
        if (res.not_found.length > 0) {
          message.warning(`未找到：${res.not_found.join('、')}`);
        }
      } else {
        const res = await compareFormulas(selectedIds);
        setFormulaResult(res);
        setHerbResult(null);
        if (res.not_found.length > 0) {
          message.warning(`未找到：${res.not_found.join('、')}`);
        }
      }
    } catch {
      message.error('对比失败，请稍后重试');
    } finally {
      setComparing(false);
    }
  };

  const renderPropertyTable = (
    propertyTable: ComparisonPropertyRow[],
    itemNames: string[],
  ) => {
    const columns = [
      {
        title: '属性',
        dataIndex: 'label',
        key: 'label',
        width: 120,
        fixed: 'left' as const,
        render: (label: string) => <Text strong>{label}</Text>,
      },
      ...itemNames.map((name) => ({
        title: name,
        key: name,
        render: (_: unknown, row: ComparisonPropertyRow) => {
          const val = row.values[name];
          const display = val && val !== '' ? val : '—';
          return (
            <span
              style={{
                display: 'inline-block',
                width: '100%',
                padding: '2px 6px',
                borderRadius: 4,
                background: row.same ? SAME_BG : 'transparent',
              }}
            >
              {display}
            </span>
          );
        },
      })),
    ];
    return (
      <Table
        dataSource={propertyTable}
        columns={columns}
        rowKey="field"
        size="middle"
        pagination={false}
        scroll={{ x: 'max-content' }}
      />
    );
  };

  return (
    <div>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 16,
        }}
      >
        <Title level={3} style={{ margin: 0 }}>
          <SwapOutlined style={{ marginRight: 8 }} />
          对比分析
        </Title>
      </div>

      <Card style={{ marginBottom: 16 }}>
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <div>
            <Text strong style={{ marginRight: 12 }}>
              对比类型
            </Text>
            <Radio.Group
              value={kind}
              onChange={(e) => setKind(e.target.value as CompareKind)}
              optionType="button"
              buttonStyle="solid"
            >
              <Radio.Button value="herb">中药对比</Radio.Button>
              <Radio.Button value="formula">方剂对比</Radio.Button>
            </Radio.Group>
          </div>

          <div>
            <Text strong style={{ marginRight: 12 }}>
              选择项目（{MIN_ITEMS}-{MAX_ITEMS} 个）
            </Text>
            {loadingOptions ? (
              <Spin size="small" />
            ) : (
              <Select
                mode="multiple"
                placeholder={
                  kind === 'herb' ? '搜索并选择中药' : '搜索并选择方剂'
                }
                style={{ minWidth: 420, maxWidth: '100%' }}
                value={selectedIds}
                onChange={setSelectedIds}
                options={options}
                showSearch
                filterOption={(input, option) =>
                  (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
                }
                maxTagCount="responsive"
                suffixIcon={<SearchOutlined />}
              />
            )}
          </div>

          <Space>
            <Button
              type="primary"
              icon={<SwapOutlined />}
              loading={comparing}
              disabled={!canCompare}
              onClick={handleCompare}
            >
              开始对比
            </Button>
            <Text type="secondary">
              已选 {selectedIds.length} / {MAX_ITEMS}（至少 {MIN_ITEMS} 个）
            </Text>
          </Space>
        </Space>
      </Card>

      {comparing && (
        <div style={{ textAlign: 'center', padding: 48 }}>
          <Spin tip="正在生成对比分析…" />
        </div>
      )}

      {!comparing && herbResult && (
        <HerbResultView result={herbResult} names={selectedNames} renderTable={renderPropertyTable} />
      )}

      {!comparing && formulaResult && (
        <FormulaResultView result={formulaResult} names={selectedNames} renderTable={renderPropertyTable} />
      )}

      {!comparing && !herbResult && !formulaResult && (
        <Empty
          description="选择项目后点击「开始对比」，查看属性异同与安全提示"
          style={{ marginTop: 48 }}
        />
      )}
    </div>
  );
}

interface ResultViewProps {
  names: string[];
  renderTable: (
    propertyTable: ComparisonPropertyRow[],
    itemNames: string[],
  ) => ReactNode;
}

function HerbResultView({ result, names, renderTable }: ResultViewProps & {
  result: HerbComparisonResult;
}) {
  return (
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      <Card title={<><CheckCircleOutlined style={{ color: '#52c41a' }} /> 相同点</>} size="small">
        {result.similarities.length > 0 ? (
          <Space direction="vertical" size={4}>
            {result.similarities.map((s, i) => (
              <Tag key={i} color="green" style={{ marginRight: 0 }}>
                {s}
              </Tag>
            ))}
          </Space>
        ) : (
          <Text type="secondary">无明显相同属性</Text>
        )}
      </Card>

      <Card title={<><WarningOutlined style={{ color: '#faad14' }} /> 不同点</>} size="small">
        {result.differences.length > 0 ? (
          <Space direction="vertical" size={4}>
            {result.differences.map((d, i) => (
              <Tag key={i} color="gold" style={{ marginRight: 0 }}>
                {d}
              </Tag>
            ))}
          </Space>
        ) : (
          <Text type="secondary">无明显差异</Text>
        )}
      </Card>

      {result.safety_notes.length > 0 && (
        <Card title={<><SafetyCertificateOutlined style={{ color: '#ff4d4f' }} /> 合用安全提示</>} size="small">
          <Space direction="vertical" size={6} style={{ width: '100%' }}>
            {result.safety_notes.map((n, i) => (
              <Alert
                key={i}
                type={n.includes('严重') || n.includes('禁止') || n.includes('致命') ? 'error' : 'warning'}
                message={n}
                showIcon
                style={{ background: WARNING_BG }}
              />
            ))}
          </Space>
        </Card>
      )}

      <Card title="属性对比表（绿色=相同）" size="small">
        {renderTable(result.property_table, names.length > 0 ? names : result.herbs.map((h) => h.name))}
      </Card>
    </Space>
  );
}

function FormulaResultView({ result, names, renderTable }: ResultViewProps & {
  result: FormulaComparisonResult;
}) {
  const itemNames = names.length > 0 ? names : result.formulas.map((f) => f.name);
  return (
    <Space direction="vertical" style={{ width: '100%' }} size="middle">
      <Card title={<><CheckCircleOutlined style={{ color: '#52c41a' }} /> 共同药材（{result.shared_herb_count}）</>} size="small">
        {result.shared_herbs.length > 0 ? (
          <Space size={[4, 4]} wrap>
            {result.shared_herbs.map((h) => (
              <Tag key={h} color="green">
                {h}
              </Tag>
            ))}
          </Space>
        ) : (
          <Text type="secondary">无共同药材</Text>
        )}
      </Card>

      {result.composition_overlap.length > 0 && (
        <Card title="组成重合度" size="small">
          <Space direction="vertical" size={4} style={{ width: '100%' }}>
            {result.composition_overlap.map((o, i) => (
              <div
                key={i}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '6px 10px',
                  background: o.overlap_ratio >= 0.5 ? SAME_BG : DIFF_BG,
                  borderRadius: 6,
                }}
              >
                <Text>
                  {o.formula_a} ↔ {o.formula_b}
                </Text>
                <Space>
                  <Tag color="blue">共同 {o.shared_count} 味</Tag>
                  <Tag color={o.overlap_ratio >= 0.5 ? 'green' : 'gold'}>
                    重合度 {Math.round(o.overlap_ratio * 100)}%
                  </Tag>
                </Space>
              </div>
            ))}
          </Space>
        </Card>
      )}

      {Object.keys(result.herbs_unique_to_each).length > 0 && (
        <Card title="各自独有药材" size="small">
          <Space direction="vertical" size={6} style={{ width: '100%' }}>
            {Object.entries(result.herbs_unique_to_each).map(([fname, herbs]) => (
              <div key={fname}>
                <Text strong style={{ marginRight: 8 }}>
                  {fname}：
                </Text>
                {herbs.length > 0 ? (
                  <Space size={[4, 4]} wrap>
                    {herbs.map((h) => (
                      <Tag key={h} color="orange">
                        {h}
                      </Tag>
                    ))}
                  </Space>
                ) : (
                  <Text type="secondary">无独有药材</Text>
                )}
              </div>
            ))}
          </Space>
        </Card>
      )}

      {result.safety_notes.length > 0 && (
        <Card title={<><SafetyCertificateOutlined style={{ color: '#ff4d4f' }} /> 合用安全提示</>} size="small">
          <Space direction="vertical" size={6} style={{ width: '100%' }}>
            {result.safety_notes.map((n, i) => (
              <Alert
                key={i}
                type={n.includes('严重') || n.includes('禁止') || n.includes('致命') ? 'error' : 'warning'}
                message={n}
                showIcon
                style={{ background: WARNING_BG }}
              />
            ))}
          </Space>
        </Card>
      )}

      <Card title="属性对比表（绿色=相同）" size="small">
        {renderTable(result.property_table, itemNames)}
      </Card>
    </Space>
  );
}
