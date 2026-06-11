import { useState, useEffect } from 'react';
import { Descriptions, Button, Skeleton, Typography } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import { useParams, useNavigate } from 'react-router-dom';
import { getHerb, type Herb } from '../api/herbApi';
import StatusTag from '../components/StatusTag';
import { TOXICITY_COLOR } from '../constants';

const { Title } = Typography;

export default function HerbDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [herb, setHerb] = useState<Herb | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    const load = async () => {
      setLoading(true);
      try {
        const data = await getHerb(id);
        setHerb(data);
      } catch {
        // handled
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [id]);

  if (loading) return <Skeleton active />;
  if (!herb) return <div>药材未找到</div>;

  return (
    <div>
      <Button
        icon={<ArrowLeftOutlined />}
        onClick={() => navigate('/herbs')}
        style={{ marginBottom: 16 }}
      >
        返回列表
      </Button>
      <Title level={3}>{herb.name}</Title>
      <Descriptions column={1} bordered>
        <Descriptions.Item label="分类">{herb.category}</Descriptions.Item>
        <Descriptions.Item label="性味">
          {herb.nature}，{herb.flavor}
        </Descriptions.Item>
        <Descriptions.Item label="归经">{herb.meridian}</Descriptions.Item>
        <Descriptions.Item label="功效">{herb.efficacy}</Descriptions.Item>
        <Descriptions.Item label="毒性">
          <StatusTag status={herb.toxicity} colorMap={TOXICITY_COLOR} />
        </Descriptions.Item>
        <Descriptions.Item label="用量">{herb.dosage}</Descriptions.Item>
        <Descriptions.Item label="禁忌">
          {herb.contraindications}
        </Descriptions.Item>
        <Descriptions.Item label="描述">{herb.description}</Descriptions.Item>
      </Descriptions>
    </div>
  );
}
