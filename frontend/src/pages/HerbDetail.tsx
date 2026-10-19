import { useState, useEffect } from 'react';
import { Descriptions, Button, Skeleton, Typography, message, Tag, Space, Card, Empty } from 'antd';
import { ArrowLeftOutlined, StarOutlined, StarFilled, BookOutlined, LinkOutlined } from '@ant-design/icons';
import { useParams, useNavigate } from 'react-router-dom';
import { getHerb, getHerbFormulas, type Herb, type HerbFormulasResponse } from '../api/herbApi';
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
  const [herbFormulas, setHerbFormulas] = useState<HerbFormulasResponse | null>(null);

  useEffect(() => {
    if (!id) return;
    const load = async () => {
      setLoading(true);
      try {
        const [data, formulas] = await Promise.all([
          getHerb(id),
          getHerbFormulas(id).catch(() => null),
        ]);
        setHerb(data);
        if (formulas) setHerbFormulas(formulas);
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

      <Card
        size="small"
        style={{ marginTop: 16 }}
        title={
          <Space>
            <BookOutlined />
            <span style={{ fontSize: 16 }}>代表方剂</span>
          </Space>
        }
      >
        {herbFormulas && herbFormulas.formulas.length > 0 ? (
          <Space direction="vertical" style={{ width: '100%' }} size={8}>
            {herbFormulas.formulas.slice(0, 10).map((f) => (
              <div
                key={f.id}
                onClick={() => navigate(`/formulas/${f.id}`)}
                style={{
                  padding: '10px 12px',
                  borderRadius: 8,
                  border: '1px solid #f0f0f0',
                  cursor: 'pointer',
                  minHeight: 44,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  transition: 'border-color 0.2s, box-shadow 0.2s',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.borderColor = '#91caff';
                  e.currentTarget.style.boxShadow = '0 2px 8px rgba(24,144,255,0.12)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = '#f0f0f0';
                  e.currentTarget.style.boxShadow = 'none';
                }}
              >
                <span style={{ fontSize: 16, fontWeight: 500, flexShrink: 0 }}>{f.name}</span>
                {f.category && <Tag color="blue">{f.category}</Tag>}
                {f.efficacy && (
                  <span
                    style={{
                      fontSize: 14,
                      color: '#666',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {f.efficacy}
                  </span>
                )}
              </div>
            ))}
          </Space>
        ) : (
          <Empty description="暂无相关方剂" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        )}
      </Card>

      {herbFormulas && herbFormulas.common_combinations.length > 0 && (
        <Card
          size="small"
          style={{ marginTop: 16 }}
          title={
            <Space>
              <LinkOutlined />
              <span style={{ fontSize: 16 }}>常用配伍</span>
            </Space>
          }
        >
          <Space size={[8, 12]} wrap>
            {(() => {
              const combos = herbFormulas.common_combinations;
              const maxCount = combos[0]?.count || 1;
              return combos.map((c) => {
                const ratio = c.count / maxCount;
                const color = ratio > 0.66 ? 'red' : ratio > 0.33 ? 'orange' : 'default';
                return (
                  <Tag
                    key={c.name}
                    color={color}
                    style={{ fontSize: 16, padding: '6px 12px', cursor: 'pointer', minHeight: 32 }}
                    onClick={() => navigate(`/herbs?search=${encodeURIComponent(c.name)}`)}
                  >
                    {c.name}（{c.count}首方剂）
                  </Tag>
                );
              });
            })()}
          </Space>
        </Card>
      )}
    </div>
  );
}
