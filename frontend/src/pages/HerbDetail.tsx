import { useState, useEffect } from 'react';
import { Descriptions, Button, Skeleton, Typography, message, Tag, Space } from 'antd';
import { ArrowLeftOutlined, StarOutlined, StarFilled } from '@ant-design/icons';
import { useParams, useNavigate } from 'react-router-dom';
import { getHerb, type Herb } from '../api/herbApi';
import { createFavorite, deleteFavorite, checkFavorite } from '../api/favoriteApi';
import StatusTag from '../components/StatusTag';
import { TOXICITY_COLOR } from '../constants';

const { Title } = Typography;

const PREGNANCY_KEYWORDS: Record<string, string> = {
  孕妇禁用: '禁用',
  孕妇忌用: '忌用',
  孕妇慎用: '慎用',
  孕妇不宜: '慎用',
  孕妇服: '禁用',
  孕妇不可: '禁用',
  孕期禁用: '禁用',
  妊娠禁用: '禁用',
};

function detectPregnancyWarning(contraindications: string): string | null {
  if (!contraindications) return null;
  for (const keyword of Object.keys(PREGNANCY_KEYWORDS)) {
    if (contraindications.includes(keyword)) {
      return PREGNANCY_KEYWORDS[keyword] ?? '慎用';
    }
  }
  if (contraindications.includes('孕妇') || contraindications.includes('妊娠') || contraindications.includes('怀孕')) {
    return '慎用';
  }
  return null;
}

const PREGNANCY_TAG_COLOR: Record<string, string> = {
  禁用: 'red',
  忌用: 'volcano',
  慎用: 'orange',
};

export default function HerbDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [herb, setHerb] = useState<Herb | null>(null);
  const [loading, setLoading] = useState(true);
  const [isFavorite, setIsFavorite] = useState(false);
  const [favoriteId, setFavoriteId] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    const load = async () => {
      setLoading(true);
      try {
        const data = await getHerb(id);
        setHerb(data);
        const check = await checkFavorite('herb', id);
        setIsFavorite(check.exists);
        setFavoriteId(check.favorite_id ?? null);
      } catch {
        // handled
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [id]);

  const handleToggleFavorite = async () => {
    if (!herb || !id) return;
    try {
      if (isFavorite && favoriteId) {
        await deleteFavorite(favoriteId);
        setIsFavorite(false);
        setFavoriteId(null);
        message.success('已取消收藏');
      } else {
        const fav = await createFavorite({
          entry_type: 'herb',
          title: herb.name,
          content: `${herb.nature}，${herb.flavor}。归${herb.meridian}。功效：${herb.efficacy}`,
          summary: herb.efficacy,
          source_type: 'herb',
          source_url: id,
        });
        setIsFavorite(true);
        setFavoriteId(fav.id);
        message.success('已收藏');
      }
    } catch {
      message.error('操作失败');
    }
  };

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
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <Space align="center">
          <Title level={3} style={{ margin: 0 }}>{herb.name}</Title>
          {(() => {
            const pw = detectPregnancyWarning(herb.contraindications);
            if (pw) {
              return (
                <Tag color={PREGNANCY_TAG_COLOR[pw]} style={{ fontSize: 14 }}>
                  孕妇{pw}
                </Tag>
              );
            }
            return null;
          })()}
        </Space>
        <Button
          type="text"
          icon={isFavorite ? <StarFilled style={{ color: '#faad14', fontSize: 20 }} /> : <StarOutlined style={{ fontSize: 20 }} />}
          onClick={handleToggleFavorite}
        >
          {isFavorite ? '已收藏' : '收藏'}
        </Button>
      </div>
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
