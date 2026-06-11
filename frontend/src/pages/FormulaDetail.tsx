import { useState, useEffect } from 'react';
import { Descriptions, Button, Skeleton, Typography } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import { useParams, useNavigate } from 'react-router-dom';
import { getFormula, type Formula } from '../api/formulaApi';

const { Title } = Typography;

export default function FormulaDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [formula, setFormula] = useState<Formula | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    const load = async () => {
      setLoading(true);
      try {
        const data = await getFormula(id);
        setFormula(data);
      } catch {
        // handled
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [id]);

  if (loading) return <Skeleton active />;
  if (!formula) return <div>方剂未找到</div>;

  return (
    <div>
      <Button
        icon={<ArrowLeftOutlined />}
        onClick={() => navigate('/formulas')}
        style={{ marginBottom: 16 }}
      >
        返回列表
      </Button>
      <Title level={3}>{formula.name}</Title>
      <Descriptions column={1} bordered>
        <Descriptions.Item label="分类">{formula.category}</Descriptions.Item>
        <Descriptions.Item label="组成">
          {formula.composition}
        </Descriptions.Item>
        <Descriptions.Item label="功效">{formula.efficacy}</Descriptions.Item>
        <Descriptions.Item label="主治">
          {formula.indication}
        </Descriptions.Item>
        <Descriptions.Item label="用法">{formula.usage}</Descriptions.Item>
        <Descriptions.Item label="描述">
          {formula.description}
        </Descriptions.Item>
      </Descriptions>
    </div>
  );
}
