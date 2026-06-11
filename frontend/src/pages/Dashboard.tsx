import { Card, Row, Col, Statistic, Button, Typography } from 'antd';
import {
  MedicineBoxOutlined,
  BookOutlined,
  BellOutlined,
  PlusOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';

const { Title } = Typography;

export default function Dashboard() {
  const navigate = useNavigate();

  return (
    <div>
      <Title level={3}>今日健康</Title>
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="中药数"
              value={200}
              prefix={<BookOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="方剂数"
              value={80}
              prefix={<BookOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="药箱数"
              value={0}
              prefix={<MedicineBoxOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="今日提醒"
              value={0}
              prefix={<BellOutlined />}
            />
          </Card>
        </Col>
      </Row>
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
