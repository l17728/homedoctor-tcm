import { useState, useEffect } from 'react';
import { Card, Row, Col, Statistic, Button, Typography, Skeleton } from 'antd';
import {
  MedicineBoxOutlined,
  BookOutlined,
  BellOutlined,
  PlusOutlined,
  SunOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { getDashboardStats, type DashboardStats } from '../api/dashboardApi';
import { getDailyHealth, type DailyHealth } from '../api/dailyHealthApi';

const { Title, Text, Paragraph } = Typography;

export default function Dashboard() {
  const navigate = useNavigate();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [dailyHealth, setDailyHealth] = useState<DailyHealth | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const [s, dh] = await Promise.all([
          getDashboardStats(),
          getDailyHealth(),
        ]);
        setStats(s);
        setDailyHealth(dh);
      } catch {
        // handled by fallback in API
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  if (loading) {
    return (
      <div>
        <Title level={3}>今日健康</Title>
        <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
          {[1, 2, 3, 4].map((i) => (
            <Col key={i} xs={24} sm={12} md={6}>
              <Skeleton active paragraph={{ rows: 1 }} />
            </Col>
          ))}
        </Row>
        <Skeleton active paragraph={{ rows: 3 }} />
      </div>
    );
  }

  return (
    <div>
      <Title level={3}>今日健康</Title>
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="中药数"
              value={stats?.herb_count ?? 0}
              prefix={<BookOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="方剂数"
              value={stats?.formula_count ?? 0}
              prefix={<BookOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="药箱数"
              value={stats?.medicine_count ?? 0}
              prefix={<MedicineBoxOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="今日提醒"
              value={stats?.reminder_count ?? 0}
              prefix={<BellOutlined />}
            />
          </Card>
        </Col>
      </Row>

      {dailyHealth && (
        <Card
          style={{ marginBottom: 24 }}
          title={
            <span>
              <SunOutlined style={{ marginRight: 8, color: '#faad14' }} />
              {dailyHealth.solar_term} · {dailyHealth.date}
            </span>
          }
        >
          <Paragraph>{dailyHealth.season_advice}</Paragraph>
          {dailyHealth.health_tips.length > 0 && (
            <div>
              <Text strong>健康提示：</Text>
              <ul style={{ marginTop: 8, paddingLeft: 20 }}>
                {dailyHealth.health_tips.map((tip, idx) => (
                  <li key={idx}>
                    <Text>{tip}</Text>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Card>
      )}

      <Row gutter={[16, 16]}>
        <Col>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => navigate('/medicines')}
          >
            添加药品
          </Button>
        </Col>
        <Col>
          <Button
            icon={<BookOutlined />}
            onClick={() => navigate('/herbs')}
          >
            浏览中药
          </Button>
        </Col>
      </Row>
    </div>
  );
}
