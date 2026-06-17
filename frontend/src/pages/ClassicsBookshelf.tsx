import { useState, useEffect, useMemo } from 'react';
import { Skeleton, Empty, Typography, Tag, theme } from 'antd';
import { BookOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { getClassics, type Classic } from '../api/classicApi';

const { Title, Text, Paragraph } = Typography;

const CATEGORIES = ['全部', '医经', '方书', '伤寒', '温病'] as const;
type CategoryFilter = (typeof CATEGORIES)[number];

/** 朝代文字色——古典感 */
function dynastyTone(dynasty: string): string {
  if (dynasty.includes('秦') || dynasty.includes('汉')) return '#8a6d3b';
  if (dynasty.includes('唐') || dynasty.includes('宋')) return '#5b6e8a';
  if (dynasty.includes('明')) return '#6e4a6e';
  return '#5a6a4e';
}

export default function ClassicsBookshelf() {
  const navigate = useNavigate();
  const { token } = theme.useToken();
  const [classics, setClassics] = useState<Classic[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<CategoryFilter>('全部');

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const { items } = await getClassics();
        if (!cancelled) setClassics(items);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const filtered = useMemo(
    () => (filter === '全部' ? classics : classics.filter((c) => c.category === filter)),
    [classics, filter],
  );

  return (
    <div>
      <style>{`
        .cls-shelf-title {
          font-family: 'KaiTi', 'STKaiti', '楷体', 'Songti SC', serif;
          letter-spacing: 0.12em;
        }
        .cls-book {
          position: relative;
          border-radius: 10px;
          overflow: hidden;
          cursor: pointer;
          background: ${token.colorBgContainer};
          box-shadow: 0 2px 8px rgba(40, 30, 20, 0.10);
          transition: transform .25s cubic-bezier(.2,.7,.3,1), box-shadow .25s;
          border: 1px solid ${token.colorBorderSecondary};
          min-height: 252px;
          display: flex;
          flex-direction: column;
        }
        .cls-book:hover {
          transform: translateY(-6px);
          box-shadow: 0 14px 30px rgba(40, 30, 20, 0.22);
        }
        .cls-book-spine {
          height: 86px;
          position: relative;
          display: flex;
          align-items: flex-end;
          padding: 14px 16px;
          color: #fff;
          overflow: hidden;
        }
        .cls-book-spine::after {
          content: '';
          position: absolute;
          inset: 0;
          background: linear-gradient(180deg, rgba(255,255,255,0.14), rgba(0,0,0,0.32));
          pointer-events: none;
        }
        .cls-book-spine::before {
          content: '';
          position: absolute;
          left: 9px; top: 0; bottom: 0;
          width: 3px;
          background: rgba(255,255,255,0.30);
          border-radius: 2px;
        }
        .cls-book-title {
          font-family: 'KaiTi', 'STKaiti', '楷体', serif;
          font-size: 22px;
          font-weight: 700;
          line-height: 1.25;
          position: relative;
          z-index: 1;
          text-shadow: 0 1px 4px rgba(0,0,0,0.35);
        }
        .cls-cat-pill {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          padding: 7px 18px;
          border-radius: 999px;
          font-size: 15px;
          cursor: pointer;
          user-select: none;
          border: 1px solid ${token.colorBorderSecondary};
          background: ${token.colorBgContainer};
          color: ${token.colorTextSecondary};
          transition: all .2s;
          white-space: nowrap;
        }
        .cls-cat-pill:hover {
          border-color: #b08d57;
          color: #8a6d3b;
        }
        .cls-cat-pill.is-active {
          background: linear-gradient(135deg, #2d5a44, #3a6b52);
          border-color: transparent;
          color: #fff;
          box-shadow: 0 4px 12px rgba(45,90,68,0.30);
        }
        .cls-seal {
          display: inline-block;
          width: 26px; height: 26px;
          border-radius: 5px;
          background: #b94a3d;
          color: #fff;
          font-family: 'KaiTi', '楷体', serif;
          font-size: 14px;
          font-weight: 700;
          line-height: 26px;
          text-align: center;
          box-shadow: 0 1px 2px rgba(0,0,0,0.2);
        }
      `}</style>

      {/* 页头 */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 8,
        }}
      >
        <Title level={3} className="cls-shelf-title" style={{ margin: 0 }}>
          <BookOutlined style={{ marginRight: 10, color: '#b08d57' }} />
          经典读诵
        </Title>
        <span className="cls-seal" title="经典">典</span>
      </div>
      <Paragraph
        type="secondary"
        style={{ marginBottom: 20, fontSize: 15 }}
      >
        千年医典，圣贤智慧。择卷而读，温故知新。
      </Paragraph>

      {/* 分类筛选 */}
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 22 }}>
        {CATEGORIES.map((c) => (
          <span
            key={c}
            className={`cls-cat-pill${filter === c ? ' is-active' : ''}`}
            onClick={() => setFilter(c)}
          >
            {c}
          </span>
        ))}
      </div>

      {loading ? (
        <Skeleton active paragraph={{ rows: 6 }} />
      ) : filtered.length === 0 ? (
        <Empty description="该分类暂无典籍" style={{ marginTop: 60 }} />
      ) : (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
            gap: 20,
          }}
        >
          {filtered.map((c) => (
            <div
              key={c.id}
              className="cls-book"
              onClick={() => navigate(`/classics/${c.id}`)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === 'Enter') navigate(`/classics/${c.id}`);
              }}
            >
              {/* 书脊色块 */}
              <div className="cls-book-spine" style={{ background: c.cover_color }}>
                <div className="cls-book-title">{c.title}</div>
              </div>
              {/* 内容 */}
              <div style={{ padding: '14px 16px 16px', flex: 1, display: 'flex', flexDirection: 'column' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8, flexWrap: 'wrap' }}>
                  <Tag color="gold" style={{ margin: 0 }}>{c.category}</Tag>
                  <Text style={{ fontSize: 14, color: dynastyTone(c.dynasty) }}>
                    {c.dynasty}
                  </Text>
                </div>
                <Text style={{ fontSize: 14, color: token.colorTextSecondary, marginBottom: 8 }}>
                  {c.author}
                </Text>
                <Paragraph
                  ellipsis={{ rows: 3 }}
                  style={{ fontSize: 14, color: token.colorTextTertiary, marginBottom: 12, flex: 1 }}
                >
                  {c.description}
                </Paragraph>
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    paddingTop: 10,
                    borderTop: `1px dashed ${token.colorBorderSecondary}`,
                  }}
                >
                  <Text style={{ fontSize: 13, color: token.colorTextTertiary }}>
                    共 {c.total_chapters} 篇
                  </Text>
                  <Text style={{ fontSize: 14, color: '#2ba471', fontWeight: 500 }}>
                    开卷阅读 →
                  </Text>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
