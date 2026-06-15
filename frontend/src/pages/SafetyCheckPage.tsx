import { useState } from 'react';
import {
  Card,
  Button,
  Input,
  Tag,
  Alert,
  Space,
  Typography,
  Empty,
  Spin,
  Divider,
  List,
  Select,
} from 'antd';
import {
  SafetyOutlined,
  PlusOutlined,
  CheckCircleOutlined,
  WarningOutlined,
  ExperimentOutlined,
} from '@ant-design/icons';
import { checkSafetyV2, type SafetyCheckResult } from '../api/safetyApi';

const { Title, Text, Paragraph } = Typography;

interface SelectedItem {
  type: 'herb' | 'medicine';
  name: string;
}

void (0 as unknown as SelectedItem);

export default function SafetyCheckPage() {
  const [herbInput, setHerbInput] = useState('');
  const [medicineInput, setMedicineInput] = useState('');
  const [selectedHerbs, setSelectedHerbs] = useState<string[]>([]);
  const [selectedMedicines, setSelectedMedicines] = useState<string[]>([]);
  const [profile, setProfile] = useState<string>('default');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<SafetyCheckResult | null>(null);

  const addHerb = () => {
    const name = herbInput.trim();
    if (name && !selectedHerbs.includes(name)) {
      setSelectedHerbs([...selectedHerbs, name]);
      setHerbInput('');
    }
  };

  const addMedicine = () => {
    const name = medicineInput.trim();
    if (name && !selectedMedicines.includes(name)) {
      setSelectedMedicines([...selectedMedicines, name]);
      setMedicineInput('');
    }
  };

  const removeHerb = (name: string) => {
    setSelectedHerbs(selectedHerbs.filter((h) => h !== name));
  };

  const removeMedicine = (name: string) => {
    setSelectedMedicines(selectedMedicines.filter((m) => m !== name));
  };

  const runCheck = async () => {
    if (selectedHerbs.length === 0 && selectedMedicines.length === 0) return;
    setLoading(true);
    setResult(null);
    try {
      const userProfile: Record<string, unknown> = {};
      if (profile === 'pregnant') {
        userProfile.is_pregnant = true;
      } else if (profile === 'child') {
        userProfile.age = 5;
      } else if (profile === 'elderly') {
        userProfile.age = 70;
      }

      const res = await checkSafetyV2({
        herbs: selectedHerbs,
        medicines: selectedMedicines,
        user_profile: userProfile,
      });
      setResult(res);
    } catch {
      setResult({
        safe: true,
        warnings: ['安全检查服务暂时不可用，请稍后再试。'],
        interactions: [],
        disclaimer: '⚠ 本工具仅供参考，不能替代专业医疗建议。',
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <Card style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
          <SafetyOutlined style={{ fontSize: 32, color: '#1890ff' }} />
          <div>
            <Title level={3} style={{ margin: 0 }}>安全检查</Title>
            <Text type="secondary">五层安全引擎：中药配伍禁忌 → 中西药交互 → 剂量 → 特殊人群 → 免责声明</Text>
          </div>
        </div>

        <Divider style={{ margin: '12px 0' }} />

        <div style={{ marginBottom: 16 }}>
          <Text strong style={{ fontSize: 16 }}>选择中药材</Text>
          <Space.Compact style={{ width: '100%', marginTop: 8 }}>
            <Input
              placeholder="输入中药名称，如：黄芪、附子、半夏"
              value={herbInput}
              onChange={(e) => setHerbInput(e.target.value)}
              onPressEnter={addHerb}
              size="large"
            />
            <Button type="primary" icon={<PlusOutlined />} onClick={addHerb} size="large">
              添加
            </Button>
          </Space.Compact>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 8 }}>
            {selectedHerbs.map((herb) => (
              <Tag
                key={herb}
                closable
                onClose={() => removeHerb(herb)}
                color="green"
                style={{ fontSize: 14, padding: '4px 8px' }}
              >
                <ExperimentOutlined /> {herb}
              </Tag>
            ))}
          </div>
        </div>

        <div style={{ marginBottom: 16 }}>
          <Text strong style={{ fontSize: 16 }}>选择西药/中成药</Text>
          <Space.Compact style={{ width: '100%', marginTop: 8 }}>
            <Input
              placeholder="输入药品名称，如：阿司匹林、布洛芬"
              value={medicineInput}
              onChange={(e) => setMedicineInput(e.target.value)}
              onPressEnter={addMedicine}
              size="large"
            />
            <Button icon={<PlusOutlined />} onClick={addMedicine} size="large">
              添加
            </Button>
          </Space.Compact>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 8 }}>
            {selectedMedicines.map((med) => (
              <Tag
                key={med}
                closable
                onClose={() => removeMedicine(med)}
                color="blue"
                style={{ fontSize: 14, padding: '4px 8px' }}
              >
                {med}
              </Tag>
            ))}
          </div>
        </div>

        <div style={{ marginBottom: 16 }}>
          <Text strong style={{ fontSize: 16 }}>特殊人群</Text>
          <Select
            value={profile}
            onChange={setProfile}
            style={{ width: '100%', marginTop: 8 }}
            size="large"
            options={[
              { label: '普通成人', value: 'default' },
              { label: '孕妇（特殊安全检查）', value: 'pregnant' },
              { label: '儿童（3岁以下）', value: 'child' },
              { label: '老年人（65岁以上）', value: 'elderly' },
            ]}
          />
        </div>

        <Button
          type="primary"
          size="large"
          block
          icon={<SafetyOutlined />}
          onClick={runCheck}
          loading={loading}
          disabled={selectedHerbs.length === 0 && selectedMedicines.length === 0}
        >
          开始安全检查
        </Button>
      </Card>

      {loading && (
        <Card style={{ textAlign: 'center', padding: 48 }}>
          <Spin size="large" />
          <Paragraph style={{ marginTop: 16, color: '#888' }}>正在进行五层安全检查...</Paragraph>
        </Card>
      )}

      {result && !loading && (
        <Card>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
            {result.safe ? (
              <>
                <CheckCircleOutlined style={{ fontSize: 32, color: '#52c41a' }} />
                <Title level={4} style={{ margin: 0, color: '#52c41a' }}>
                  未发现严重安全问题
                </Title>
              </>
            ) : (
              <>
                <WarningOutlined style={{ fontSize: 32, color: '#ff4d4f' }} />
                <Title level={4} style={{ margin: 0, color: '#ff4d4f' }}>
                  发现 {result.warnings.length} 条安全警告
                </Title>
              </>
            )}
          </div>

          {result.warnings.length > 0 && (
            <>
              <Divider orientation="left">安全警告</Divider>
              <List
                dataSource={result.warnings}
                renderItem={(warning) => (
                  <List.Item>
                    <Alert
                      message={warning}
                      type={warning.includes('禁止') || warning.includes('禁忌') ? 'error' : 'warning'}
                      showIcon
                      style={{ width: '100%' }}
                    />
                  </List.Item>
                )}
              />
            </>
          )}

          {result.interactions.length > 0 && (
            <>
              <Divider orientation="left">交互详情</Divider>
              <List
                dataSource={result.interactions}
                renderItem={(interaction) => (
                  <List.Item>
                    <Tag color="orange">{interaction}</Tag>
                  </List.Item>
                )}
              />
            </>
          )}

          {result.disclaimer && (
            <>
              <Divider />
              <Alert message={result.disclaimer} type="info" showIcon />
            </>
          )}

          {result.safe && result.warnings.length === 0 && (
            <Empty
              description="所有检查项均通过"
              image={Empty.PRESENTED_IMAGE_SIMPLE}
            />
          )}
        </Card>
      )}

      {!result && !loading && (
        <Card>
          <Empty
            description="添加药材和药品后，点击「开始安全检查」"
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          />
          <div style={{ marginTop: 16, textAlign: 'center' }}>
            <Space direction="vertical" size="small">
              <Text type="secondary">安全检查覆盖：</Text>
              <Tag icon={<ExperimentOutlined />} color="red">十八反十九畏</Tag>
              <Tag color="orange">中西药交互</Tag>
              <Tag color="gold">剂量范围</Tag>
              <Tag color="purple">特殊人群</Tag>
              <Tag color="blue">免责声明</Tag>
            </Space>
          </div>
        </Card>
      )}
    </div>
  );
}
