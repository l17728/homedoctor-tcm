import { useState, useEffect } from 'react';
import { Card, Row, Col, Statistic, Button, Typography, Skeleton, Alert, Space, Empty } from 'antd';
import {
  MedicineBoxOutlined,
  BookOutlined,
  BellOutlined,
  PlusOutlined,
  SunOutlined,
  WarningOutlined,
  ExclamationCircleOutlined,
  SafetyOutlined,
  CalendarOutlined,
  MessageOutlined,
  CheckCircleOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { getDashboardStats, type DashboardStats } from '../api/dashboardApi';
import { getDailyHealth, type DailyHealth } from '../api/dailyHealthApi';
import { request } from '../api/client';

const { Title, Text, Paragraph } = Typography;

export default function Dashboard() {
  const navigate = useNavigate();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [dailyHealth, setDailyHealth] = useState<DailyHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [expiryAlerts, setExpiryAlerts] = useState<{
    expired: { id: string; name: string; expiry_date: string }[];
    expiring_soon: { id: string; name: string; expiry_date: string }[];
    low_stock: { id: string; name: string; quantity: number }[];
  }>({ expired: [], expiring_soon: [], low_stock: [] });

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
        try {
          const alerts = await request<typeof expiryAlerts>(
            '/api/medicines/alerts/expiring',
          );
          setExpiryAlerts(alerts);
        } catch {
          // non-critical
        }
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

      {!!stats?.adherence_total_7d && stats.adherence_total_7d > 0 && (
        <Card
          style={{ marginBottom: 24 }}
          title={
            <span>
              <CheckCircleOutlined style={{ marginRight: 8, color: '#52c41a' }} />
              用药依从性
            </span>
          }
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 24 }}>
            <Statistic
              title="近7天按时服药率"
              value={stats.adherence_rate ?? 0}
              suffix="%"
              valueStyle={{
                color: (stats.adherence_rate ?? 0) >= 80 ? '#52c41a' : (stats.adherence_rate ?? 0) >= 60 ? '#faad14' : '#ff4d4f',
                fontSize: 36,
              }}
            />
            <div>
              <Text type="secondary" style={{ fontSize: 16 }}>
                {stats.adherence_taken_7d ?? 0} / {stats.adherence_total_7d ?? 0} 次按时服药
              </Text>
              <br />
              <Text type="secondary">
                {(stats.adherence_rate ?? 0) >= 80
                  ? '坚持得很好，继续保持！'
                  : (stats.adherence_rate ?? 0) >= 60
                    ? '还可以，建议设置提醒避免漏服'
                    : '依从性较低，请务必按时服药'}
              </Text>
            </div>
          </div>
        </Card>
      )}

      {(expiryAlerts.expired.length > 0 ||
        expiryAlerts.expiring_soon.length > 0 ||
        expiryAlerts.low_stock.length > 0) && (
        <Card
          style={{ marginBottom: 24 }}
          title={
            <span>
              <WarningOutlined style={{ marginRight: 8, color: '#faad14' }} />
              药箱提醒
            </span>
          }
        >
          <Space direction="vertical" style={{ width: '100%' }} size="small">
            {expiryAlerts.expired.map((m) => (
              <Alert
                key={m.id}
                type="error"
                showIcon
                icon={<ExclamationCircleOutlined />}
                message={`${m.name} 已过期（${m.expiry_date}）`}
              />
            ))}
            {expiryAlerts.expiring_soon.map((m) => (
              <Alert
                key={m.id}
                type="warning"
                showIcon
                message={`${m.name} 即将过期（${m.expiry_date}）`}
              />
            ))}
            {expiryAlerts.low_stock.map((m) => (
              <Alert
                key={m.id}
                type="info"
                showIcon
                message={`${m.name} 库存不足（剩余 ${m.quantity}）`}
              />
            ))}
          </Space>
        </Card>
      )}

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
          {Array.isArray(dailyHealth.health_tips) && dailyHealth.health_tips.length > 0 && (
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
        <Col>
          <Button
            icon={<SafetyOutlined />}
            onClick={() => navigate('/safety')}
          >
            安全检查
          </Button>
        </Col>
        <Col>
          <Button
            icon={<CalendarOutlined />}
            onClick={() => navigate('/seasonal')}
          >
            季节养生
          </Button>
        </Col>
        <Col>
          <Button
            icon={<MessageOutlined />}
            onClick={() => navigate('/chat')}
          >
            AI问答
          </Button>
        </Col>
      </Row>

      {stats && stats.medicine_count === 0 && stats.reminder_count === 0 && (
        <Card style={{ marginTop: 24 }}>
          <Empty description="欢迎使用家庭医生！开始您的健康管理之旅">
            <Space direction="vertical" size="small" style={{ alignItems: 'center' }}>
              <Text type="secondary">建议您先完成以下步骤：</Text>
              <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate('/medicines')}>
                1. 添加您的常用药品
              </Button>
              <Button icon={<BellOutlined />} onClick={() => navigate('/reminders')}>
                2. 设置吃药提醒
              </Button>
              <Button icon={<BookOutlined />} onClick={() => navigate('/herbs')}>
                3. 浏览中药知识库
              </Button>
            </Space>
          </Empty>
        </Card>
      )}
    </div>
  );
}
