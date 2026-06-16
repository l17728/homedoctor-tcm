import { useState } from 'react';
import { Layout, Menu, Button, Dropdown, theme } from 'antd';
import {
  HomeOutlined,
  BookOutlined,
  MedicineBoxOutlined,
  MessageOutlined,
  SettingOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  UserOutlined,
  LogoutOutlined,
  BulbOutlined,
  ClockCircleOutlined,
  HeartOutlined,
  StarOutlined,
  CalendarOutlined,
  SafetyOutlined,
  TeamOutlined,
} from '@ant-design/icons';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { useTheme } from '../hooks/useTheme';

const { Header, Sider, Content } = Layout;

export default function AppLayout() {
  const [collapsed, setCollapsed] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuth();
  const { toggleTheme, isDark } = useTheme();
  const { token: themeToken } = theme.useToken();

  const menuItems = [
    {
      key: '/',
      icon: <HomeOutlined />,
      label: '首页',
    },
    {
      key: 'knowledge',
      icon: <BookOutlined />,
      label: '知识库',
      children: [
        { key: '/herbs', label: '中药' },
        { key: '/formulas', label: '方剂' },
      ],
    },
    {
      key: '/medicines',
      icon: <MedicineBoxOutlined />,
      label: '药箱',
    },
    {
      key: '/reminders',
      icon: <ClockCircleOutlined />,
      label: '提醒',
    },
    {
      key: '/family',
      icon: <TeamOutlined />,
      label: '家庭成员',
    },
    {
      key: '/favorites',
      icon: <StarOutlined />,
      label: '收藏',
    },
    {
      key: '/seasonal',
      icon: <CalendarOutlined />,
      label: '季节养生',
    },
    {
      key: '/safety',
      icon: <SafetyOutlined />,
      label: '安全检查',
    },
    {
      key: '/chat',
      icon: <MessageOutlined />,
      label: 'AI 助手',
    },
    {
      key: 'health',
      icon: <HeartOutlined />,
      label: '健康',
      children: [
        { key: '/constitution', label: '体质自测' },
        { key: '/profile', label: '健康档案' },
      ],
    },
    {
      key: '/settings',
      icon: <SettingOutlined />,
      label: '设置',
    },
  ];

  const handleMenuClick = ({ key }: { key: string }) => {
    if (key !== 'knowledge' && key !== 'health') {
      navigate(key);
    }
  };

  const userMenuItems = [
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: '退出登录',
      onClick: () => {
        logout();
        navigate('/login');
      },
    },
  ];

  const selectedKey = location.pathname;
  const [openKeys, setOpenKeys] = useState<string[]>(() => {
    if (
      location.pathname.startsWith('/herbs') ||
      location.pathname.startsWith('/formulas')
    ) {
      return ['knowledge'];
    }
    if (
      location.pathname.startsWith('/constitution') ||
      location.pathname.startsWith('/profile')
    ) {
      return ['health'];
    }
    if (location.pathname.startsWith('/favorites')) {
      return [];
    }
    return [];
  });

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        width={200}
        collapsedWidth={64}
        style={{
          overflow: 'auto',
          height: '100vh',
          position: 'fixed',
          left: 0,
          top: 0,
          bottom: 0,
        }}
      >
        <div
          style={{
            height: 32,
            margin: 16,
            textAlign: 'center',
            color: '#fff',
            fontSize: collapsed ? 14 : 18,
            fontWeight: 600,
          }}
        >
          {collapsed ? '医' : '家庭医生'}
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selectedKey]}
          openKeys={openKeys}
          onOpenChange={setOpenKeys}
          items={menuItems}
          onClick={handleMenuClick}
        />
      </Sider>
      <Layout
        style={{
          marginLeft: collapsed ? 64 : 200,
          transition: 'all 0.2s',
        }}
      >
        <Header
          style={{
            padding: '0 24px',
            background: themeToken.colorBgContainer,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            boxShadow: '0 1px 4px rgba(0,0,0,0.08)',
          }}
        >
          <Button
            type="text"
            icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            onClick={() => setCollapsed(!collapsed)}
          />
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <Button
              type="text"
              icon={<BulbOutlined />}
              onClick={toggleTheme}
            >
              {isDark ? '浅色' : '深色'}
            </Button>
            <Dropdown menu={{ items: userMenuItems }} placement="bottomRight">
              <Button type="text" icon={<UserOutlined />}>
                {user?.username ? `用户 ${user.username}` : '用户'}
              </Button>
            </Dropdown>
          </div>
        </Header>
        <Content
          style={{
            margin: '24px',
            padding: 24,
            background: themeToken.colorBgContainer,
            borderRadius: 8,
            minHeight: 280,
          }}
        >
          <div style={{ maxWidth: 1400, margin: '0 auto' }}>
            <Outlet />
          </div>
        </Content>
      </Layout>
    </Layout>
  );
}
