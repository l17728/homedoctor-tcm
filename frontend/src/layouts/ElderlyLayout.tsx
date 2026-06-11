import { Layout } from 'antd';
import { HomeOutlined, MessageOutlined, UserOutlined } from '@ant-design/icons';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import type { ReactNode } from 'react';

const { Content } = Layout;

interface TabItem {
  key: string;
  label: string;
  icon: ReactNode;
}

export default function ElderlyLayout() {
  const navigate = useNavigate();
  const location = useLocation();

  const tabs: TabItem[] = [
    { key: '/', label: '首页', icon: <HomeOutlined /> },
    { key: '/chat', label: 'AI问答', icon: <MessageOutlined /> },
    { key: '/profile', label: '我的', icon: <UserOutlined /> },
  ];

  const activeTab = (() => {
    if (location.pathname === '/' || location.pathname === '/dashboard') return '/';
    if (location.pathname.startsWith('/chat')) return '/chat';
    if (
      location.pathname.startsWith('/profile') ||
      location.pathname.startsWith('/constitution') ||
      location.pathname.startsWith('/reminders')
    )
      return '/profile';
    return '/';
  })();

  return (
    <Layout style={{ minHeight: '100vh', background: '#f5f5f5' }}>
      <Content
        style={{
          padding: 16,
          paddingBottom: 80,
          maxWidth: 600,
          margin: '0 auto',
          width: '100%',
        }}
      >
        <Outlet />
      </Content>
      <div
        style={{
          position: 'fixed',
          bottom: 0,
          left: 0,
          right: 0,
          maxWidth: 600,
          margin: '0 auto',
          background: '#fff',
          borderTop: '1px solid #e8e8e8',
          zIndex: 1000,
          display: 'flex',
          height: 64,
        }}
      >
        {tabs.map((tab) => {
          const isActive = activeTab === tab.key;
          return (
            <div
              key={tab.key}
              onClick={() => navigate(tab.key)}
              style={{
                flex: 1,
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer',
                color: isActive ? '#1890ff' : '#999',
                transition: 'color 0.2s',
              }}
            >
              <span style={{ fontSize: 28 }}>{tab.icon}</span>
              <span style={{ fontSize: 14, marginTop: 2 }}>{tab.label}</span>
            </div>
          );
        })}
      </div>
    </Layout>
  );
}
