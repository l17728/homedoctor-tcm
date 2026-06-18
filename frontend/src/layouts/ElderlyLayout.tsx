import { Layout, Card } from 'antd';
import {
  HomeOutlined,
  MessageOutlined,
  UserOutlined,
  SettingOutlined,
  HeartOutlined,
  SolutionOutlined,
  RightOutlined,
} from '@ant-design/icons';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import type { ReactNode } from 'react';

const { Content } = Layout;

interface TabItem {
  key: string;
  label: string;
  icon: ReactNode;
}

interface MeMenuItem {
  path: string;
  icon: ReactNode;
  label: string;
  desc: string;
}

// 长辈模式 3 Tab（spec §6.6）：首页 / 问答 / 我的
// "吃药"与"药箱"功能保留在首页 Dashboard 卡片中（已存在）。
export default function ElderlyLayout() {
  const navigate = useNavigate();
  const location = useLocation();

  const tabs: TabItem[] = [
    { key: '/', label: '首页', icon: <HomeOutlined /> },
    { key: '/chat', label: '问答', icon: <MessageOutlined /> },
    { key: '/profile', label: '我的', icon: <UserOutlined /> },
  ];

  const isMeSection =
    location.pathname.startsWith('/profile') ||
    location.pathname.startsWith('/settings') ||
    location.pathname.startsWith('/constitution');

  const activeTab = (() => {
    if (location.pathname === '/' || location.pathname === '/dashboard') return '/';
    if (location.pathname.startsWith('/chat')) return '/chat';
    if (isMeSection) return '/profile';
    return '/';
  })();

  const meMenuItems: MeMenuItem[] = [
    { path: '/profile', icon: <SolutionOutlined />, label: '健康档案', desc: '基本信息 · 过敏史' },
    { path: '/constitution', icon: <HeartOutlined />, label: '体质自测', desc: '九种体质测评' },
    { path: '/settings', icon: <SettingOutlined />, label: '设置', desc: '显示 · 长辈模式' },
  ];

  return (
    <Layout style={{ minHeight: '100vh', background: '#f5f5f5' }}>
      <Content
        style={{
          padding: 16,
          paddingBottom: 88,
          maxWidth: 600,
          margin: '0 auto',
          width: '100%',
        }}
      >
        {/* "我的"分区快捷菜单 — 长辈模式下持久可见的导航 */}
        {isMeSection && (
          <Card
            size="small"
            style={{ marginBottom: 16 }}
            styles={{ body: { padding: 0 } }}
          >
            {meMenuItems.map((item, idx) => {
              const active = location.pathname.startsWith(item.path);
              return (
                <div
                  key={item.path}
                  onClick={() => navigate(item.path)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    padding: '14px 16px',
                    cursor: 'pointer',
                    borderTop: idx === 0 ? 'none' : '1px solid #f0f0f0',
                    background: active ? '#e6f7ff' : 'transparent',
                  }}
                >
                  <span style={{ fontSize: 24, marginRight: 14, color: '#1890ff' }}>
                    {item.icon}
                  </span>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 18, fontWeight: active ? 600 : 500 }}>
                      {item.label}
                    </div>
                    <div style={{ fontSize: 14, color: '#999' }}>{item.desc}</div>
                  </div>
                  <RightOutlined style={{ color: '#ccc' }} />
                </div>
              );
            })}
          </Card>
        )}
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
              <span style={{ fontSize: 32 }}>{tab.icon}</span>
              <span style={{ fontSize: 18, marginTop: 2 }}>{tab.label}</span>
            </div>
          );
        })}
      </div>
    </Layout>
  );
}
