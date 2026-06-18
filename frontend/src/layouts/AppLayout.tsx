import { useState, useEffect, useCallback } from 'react';
import { Layout, Menu, Button, Dropdown, Tooltip, Drawer, Breadcrumb, theme } from 'antd';
import {
  HomeOutlined,
  BookOutlined,
  MedicineBoxOutlined,
  MessageOutlined,
  SettingOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  MenuOutlined,
  UserOutlined,
  LogoutOutlined,
  BulbOutlined,
  HeartOutlined,
  TeamOutlined,
  RobotOutlined,
  ShareAltOutlined,
  AlertOutlined,
} from '@ant-design/icons';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { useTheme } from '../hooks/useTheme';
import { useIsMobile } from '../hooks/useIsMobile';
import {
  getFamilyMembers,
  switchMember,
  clearMemberSwitch,
  MEMBER_STORAGE_KEY,
  type FamilyMember,
} from '../api/familyMemberApi';

const { Header, Sider, Content } = Layout;

interface BreadcrumbItem {
  title: string;
  path: string;
}

const ROUTE_BREADCRUMBS: { path: string; items: string[] }[] = [
  { path: '/', items: ['首页'] },
  { path: '/chat', items: ['AI助手'] },
  { path: '/triage', items: ['急症分诊'] },
  { path: '/settings', items: ['设置'] },
  { path: '/classics', items: ['经典读诵'] },
  { path: '/herbs', items: ['知识库', '中药'] },
  { path: '/formulas', items: ['知识库', '方剂'] },
  { path: '/therapies', items: ['知识库', '外治理疗'] },
  { path: '/knowledge-graph', items: ['知识库', '知识图谱'] },
  { path: '/bookmarks', items: ['知识库', '书签'] },
  { path: '/comparison', items: ['知识库', '对比分析'] },
  { path: '/knowledge-import', items: ['知识库', '知识导入'] },
  { path: '/formulation', items: ['知识库', '智能配伍'] },
  { path: '/medicines', items: ['用药管理', '药箱'] },
  { path: '/reminders', items: ['用药管理', '吃药提醒'] },
  { path: '/medication-plans', items: ['用药管理', '用药套餐'] },
  { path: '/medication-schedule', items: ['用药管理', '服药计划'] },
  { path: '/safety', items: ['用药管理', '药箱安全检查'] },
  { path: '/constitution', items: ['健康管理', '体质自测'] },
  { path: '/profile', items: ['健康管理', '健康档案'] },
  { path: '/health-log', items: ['健康管理', '每日打卡'] },
  { path: '/reports', items: ['健康管理', '报告中心'] },
  { path: '/seasonal', items: ['健康管理', '季节养生'] },
  { path: '/favorites', items: ['健康管理', '收藏'] },
  { path: '/family', items: ['健康管理', '家庭成员'] },
  { path: '/remote-assist', items: ['家庭共享', '远程协助'] },
  { path: '/share-cards', items: ['家庭共享', '分享卡'] },
];

function getBreadcrumbItems(pathname: string): BreadcrumbItem[] {
  const match = ROUTE_BREADCRUMBS
    .filter((r) => pathname === r.path || (r.path !== '/' && pathname.startsWith(r.path + '/')))
    .sort((a, b) => b.path.length - a.path.length)[0];

  if (!match) return [{ title: '首页', path: '/' }];

  const items: BreadcrumbItem[] = [];
  match.items.forEach((title, idx) => {
    if (match.items.length === 1) {
      items.push({ title, path: match.path });
    } else {
      items.push({
        title,
        path: idx === match.items.length - 1 ? match.path : '/',
      });
    }
  });

  const hasSubPath = pathname !== match.path && pathname.startsWith(match.path + '/');
  if (hasSubPath) {
    items.push({ title: '详情', path: pathname });
  }

  return items;
}

export default function AppLayout() {
  const [collapsed, setCollapsed] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuth();
  const { toggleTheme, isDark } = useTheme();
  const { token: themeToken } = theme.useToken();
  const isMobile = useIsMobile();

  const [members, setMembers] = useState<FamilyMember[]>([]);
  const [currentMemberId, setCurrentMemberId] = useState<string | null>(
    () => localStorage.getItem(MEMBER_STORAGE_KEY),
  );

  const loadMembers = useCallback(async () => {
    try {
      const list = await getFamilyMembers();
      setMembers(list);
      if (list.length === 0 && currentMemberId) {
        localStorage.removeItem(MEMBER_STORAGE_KEY);
        setCurrentMemberId(null);
      }
    } catch {
      // Not logged in or network error — silently ignore
    }
  }, [currentMemberId]);

  useEffect(() => {
    if (user) {
      void loadMembers();
    }
  }, [user, loadMembers]);

  const handleSelectMember = useCallback(
    async (memberId: string | null) => {
      if (memberId) {
        const member = await switchMember(memberId);
        if (member) {
          localStorage.setItem(MEMBER_STORAGE_KEY, memberId);
          setCurrentMemberId(memberId);
          navigate(0);
        }
      } else {
        await clearMemberSwitch();
        localStorage.removeItem(MEMBER_STORAGE_KEY);
        setCurrentMemberId(null);
        navigate(0);
      }
    },
    [navigate],
  );

  // 4 个可折叠分组键（不导航，仅展开/收起）
  const GROUP_KEYS = ['group-medicine', 'group-knowledge', 'group-health', 'group-sharing'] as const;

  // 路由 → 所属分组映射（用于默认展开当前路由所在分组）
  const ROUTE_TO_GROUP: Record<string, string> = {
    // 💊 用药管理
    '/medicines': 'group-medicine',
    '/reminders': 'group-medicine',
    '/medication-plans': 'group-medicine',
    '/medication-schedule': 'group-medicine',
    '/safety': 'group-medicine',
    // 📚 知识探索
    '/herbs': 'group-knowledge',
    '/formulas': 'group-knowledge',
    '/therapies': 'group-knowledge',
    '/classics': 'group-knowledge',
    '/knowledge-graph': 'group-knowledge',
    '/bookmarks': 'group-knowledge',
    '/comparison': 'group-knowledge',
    '/knowledge-import': 'group-knowledge',
    '/formulation': 'group-knowledge',
    // 🌿 健康管理
    '/constitution': 'group-health',
    '/profile': 'group-health',
    '/health-log': 'group-health',
    '/reports': 'group-health',
    '/seasonal': 'group-health',
    '/favorites': 'group-health',
    '/family': 'group-health',
    // 👨‍👩‍👧 家庭共享
    '/remote-assist': 'group-sharing',
    '/share-cards': 'group-sharing',
  };

  const isGroupKey = (key: string) => (GROUP_KEYS as readonly string[]).includes(key);

  const menuItems = [
    {
      key: '/',
      icon: <HomeOutlined />,
      label: '首页',
    },
    {
      key: '/chat',
      icon: <MessageOutlined />,
      label: 'AI助手',
    },
    {
      key: '/triage',
      icon: <AlertOutlined />,
      label: '急症分诊',
      danger: true,
    },
    {
      key: 'group-medicine',
      icon: <MedicineBoxOutlined />,
      label: '用药管理',
      children: [
        { key: '/medicines', label: '药箱' },
        { key: '/reminders', label: '吃药提醒' },
        { key: '/medication-plans', label: '用药套餐' },
        { key: '/medication-schedule', label: '服药计划' },
        { key: '/safety', label: '药箱安全检查' },
      ],
    },
    {
      key: 'group-knowledge',
      icon: <BookOutlined />,
      label: '知识探索',
      children: [
        { key: '/knowledge-hub', label: '知识库' },
        { key: '/herbs', label: '中药' },
        { key: '/formulas', label: '方剂' },
        { key: '/therapies', label: '外治理疗' },
        { key: '/classics', label: '经典读诵' },
        { key: '/knowledge-graph', label: '知识图谱' },
        { key: '/bookmarks', label: '书签' },
        { key: '/comparison', label: '对比分析' },
        { key: '/knowledge-import', label: '知识导入' },
        { key: '/formulation', label: '智能配伍' },
      ],
    },
    {
      key: 'group-health',
      icon: <HeartOutlined />,
      label: '健康管理',
      children: [
        { key: '/constitution', label: '体质自测' },
        { key: '/profile', label: '健康档案' },
        { key: '/health-log', label: '每日打卡' },
        { key: '/reports', label: '报告中心' },
        { key: '/seasonal', label: '季节养生' },
        { key: '/favorites', label: '收藏' },
        { key: '/family', label: '家庭成员' },
      ],
    },
    {
      key: 'group-sharing',
      icon: <ShareAltOutlined />,
      label: '家庭共享',
      children: [
        { key: '/remote-assist', label: '远程协助' },
        { key: '/share-cards', label: '分享卡' },
      ],
    },
    {
      key: '/settings',
      icon: <SettingOutlined />,
      label: '设置',
    },
  ];

  const handleMenuClick = ({ key }: { key: string }) => {
    if (!isGroupKey(key)) {
      navigate(key);
      if (isMobile) setDrawerOpen(false);
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

  // Prefix-match: detail pages (e.g. /herbs/123) keep their parent menu item
  // (e.g. /herbs) highlighted. Parent-only keys (knowledge/health/sharing) are
  // ignored — only leaf keys with a leading "/" participate in prefix matching.
  const allKeys: string[] = menuItems.flatMap((m) => {
    const children = 'children' in m ? (m as { children?: { key: string }[] }).children : undefined;
    return children ? [m.key, ...children.map((c) => c.key)] : [m.key];
  });
  const matchedKey = (() => {
    const exact = allKeys.find((k) => k === location.pathname);
    if (exact) return exact;
    // Longest segment-aware prefix wins (e.g. /herbs/123 → /herbs)
    const prefix = allKeys
      .filter((k) => k !== '/' && location.pathname.startsWith(k + '/'))
      .sort((a, b) => b.length - a.length)[0];
    return prefix ?? location.pathname;
  })();
  const [openKeys, setOpenKeys] = useState<string[]>(() => {
    // 默认展开当前路由所属的分组
    const group = ROUTE_TO_GROUP[location.pathname];
    return group ? [group] : [];
  });

  // 手风琴行为：展开新分组时自动收起其他分组
  const handleOpenChange = (keys: string[]) => {
    const latest = keys.find((k) => !openKeys.includes(k));
    if (latest && isGroupKey(latest)) {
      setOpenKeys([latest]);
    } else {
      setOpenKeys(keys);
    }
  };

  return (
    <Layout style={{ minHeight: '100vh' }}>
      {/* Desktop fixed sidebar */}
      {!isMobile && (
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
            selectedKeys={[matchedKey]}
            openKeys={openKeys}
            onOpenChange={handleOpenChange}
            items={menuItems}
            onClick={handleMenuClick}
          />
        </Sider>
      )}

      {/* Mobile drawer menu */}
      <Drawer
        placement="left"
        width={250}
        open={isMobile && drawerOpen}
        onClose={() => setDrawerOpen(false)}
        styles={{ body: { padding: 0, background: '#001529' } }}
        closable={false}
      >
        <div
          style={{
            height: 32,
            margin: 16,
            textAlign: 'center',
            color: '#fff',
            fontSize: 18,
            fontWeight: 600,
          }}
        >
          家庭医生
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[matchedKey]}
          openKeys={openKeys}
          onOpenChange={handleOpenChange}
          items={menuItems}
          onClick={handleMenuClick}
        />
      </Drawer>

      <Layout
        style={{
          marginLeft: isMobile ? 0 : collapsed ? 64 : 200,
          transition: 'all 0.2s',
        }}
      >
        <Header
          style={{
            padding: isMobile ? '0 12px' : '0 24px',
            background: themeToken.colorBgContainer,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            boxShadow: '0 1px 4px rgba(0,0,0,0.08)',
          }}
        >
          {isMobile ? (
            <Button
              type="text"
              icon={<MenuOutlined />}
              onClick={() => setDrawerOpen(true)}
              style={{ fontSize: 18 }}
            />
          ) : (
            <Button
              type="text"
              icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
              onClick={() => setCollapsed(!collapsed)}
            />
          )}
          <div style={{ display: 'flex', alignItems: 'center', gap: isMobile ? 4 : 12 }}>
            {members.length > 0 && (
              <Dropdown
                placement="bottomRight"
                menu={{
                  items: [
                    {
                      key: 'all',
                      label: '全部成员',
                      onClick: () => void handleSelectMember(null),
                    },
                    { type: 'divider' as const },
                    ...members.map((m) => ({
                      key: m.id,
                      label: m.name ?? '未命名',
                      onClick: () => void handleSelectMember(m.id),
                    })),
                  ],
                  selectedKeys: currentMemberId ? [currentMemberId] : ['all'],
                }}
              >
                <Button
                  type="text"
                  icon={<TeamOutlined />}
                  style={{ minHeight: 40, minWidth: 44, justifyContent: 'center' }}
                >
                  {isMobile
                    ? null
                    : currentMemberId
                      ? members.find((m) => m.id === currentMemberId)?.name ?? '成员'
                      : '全部成员'}
                </Button>
              </Dropdown>
            )}
            <Button
              type="text"
              icon={<BulbOutlined />}
              onClick={toggleTheme}
            >
              {isMobile ? null : isDark ? '浅色' : '深色'}
            </Button>
            <Dropdown menu={{ items: userMenuItems }} placement="bottomRight">
              <Button type="text" icon={<UserOutlined />}>
                {isMobile ? null : user?.username ? `用户 ${user.username}` : '用户'}
              </Button>
            </Dropdown>
          </div>
        </Header>
        <Content
          style={{
            margin: isMobile ? 12 : 24,
            padding: isMobile ? 12 : 24,
            background: themeToken.colorBgContainer,
            borderRadius: 8,
            minHeight: 280,
          }}
        >
          <Breadcrumb
            style={{ marginBottom: 16 }}
            items={getBreadcrumbItems(location.pathname).map((item, idx, arr) => ({
              title:
                idx === arr.length - 1 ? (
                  item.title
                ) : (
                  <a onClick={() => navigate(item.path)}>{item.title}</a>
                ),
            }))}
          />
          <div style={{ maxWidth: 1400, margin: '0 auto' }}>
            <Outlet />
          </div>
        </Content>
      </Layout>

      {/* AI 健康助手 — 悬浮按钮 */}
      {!['/chat', '/login'].includes(location.pathname) &&
        !location.pathname.startsWith('/classics') && (
        <>
          <style>{`
            .ai-fab {
              transition: transform 0.2s ease, box-shadow 0.2s ease;
            }
            .ai-fab:hover {
              transform: scale(1.05);
              box-shadow: 0 6px 16px rgba(24, 144, 255, 0.55);
            }
          `}</style>
          <Tooltip title="AI健康助手" placement="left">
            <Button
              className="ai-fab"
              shape="circle"
              size="large"
              icon={<RobotOutlined />}
              onClick={() => navigate('/chat')}
              style={{
                position: 'fixed',
                bottom: isMobile ? 16 : 32,
                right: isMobile ? 16 : 32,
                width: 56,
                height: 56,
                zIndex: 1000,
                fontSize: 24,
                backgroundColor: '#1890ff',
                borderColor: '#1890ff',
                color: '#fff',
                boxShadow: '0 4px 12px rgba(24, 144, 255, 0.45)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            />
          </Tooltip>
        </>
      )}
    </Layout>
  );
}
