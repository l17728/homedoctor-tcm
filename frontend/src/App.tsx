import React, { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { ConfigProvider } from 'antd';
import { AuthProvider, useAuth } from './hooks/useAuth';
import { ThemeProvider, useTheme } from './hooks/useTheme';
import { ElderlyModeProvider, useElderlyMode } from './contexts/ElderlyModeContext';
import { ErrorBoundary } from './components/ErrorBoundary';
import { lightTheme, darkTheme } from './theme';
import { isSystemPath, ELDERLY_ALLOWED_PATHS } from './system-paths';
import AppLayout from './layouts/AppLayout';
import ElderlyLayout from './layouts/ElderlyLayout';
import LoginPage from './pages/LoginPage';

const Dashboard = lazy(() => import('./pages/Dashboard'));
const HerbList = lazy(() => import('./pages/HerbList'));
const HerbDetail = lazy(() => import('./pages/HerbDetail'));
const FormulaList = lazy(() => import('./pages/FormulaList'));
const FormulaDetail = lazy(() => import('./pages/FormulaDetail'));
const MedicineList = lazy(() => import('./pages/MedicineList'));
const ChatPage = lazy(() => import('./pages/ChatPage'));
const SettingsPage = lazy(() => import('./pages/SettingsPage'));
const RemindersPage = lazy(() => import('./pages/RemindersPage'));
const ConstitutionPage = lazy(() => import('./pages/ConstitutionPage'));
const ProfilePage = lazy(() => import('./pages/ProfilePage'));
const FavoritesPage = lazy(() => import('./pages/FavoritesPage'));
const SeasonalHealthPage = lazy(() => import('./pages/SeasonalHealthPage'));
const SafetyCheckPage = lazy(() => import('./pages/SafetyCheckPage'));
const FamilyMembersPage = lazy(() => import('./pages/FamilyMembersPage'));
const KnowledgeGraphPage = lazy(() => import('./pages/KnowledgeGraphPage'));
const ClassicsBookshelf = lazy(() => import('./pages/ClassicsBookshelf'));
const ClassicReader = lazy(() => import('./pages/ClassicReader'));
const TherapiesPage = lazy(() => import('./pages/TherapiesPage'));
const MeridianAcupointPage = lazy(() => import('./pages/MeridianAcupointPage'));
const KnowledgeBrowsePage = lazy(() => import('./pages/KnowledgeBrowsePage'));
const AdminPage = lazy(() => import('./pages/AdminPage'));
const HealthPracticePage = lazy(() => import('./pages/HealthPracticePage'));
const MedicationPlansPage = lazy(() => import('./pages/MedicationPlansPage'));
const MedicationSchedulePage = lazy(() => import('./pages/MedicationSchedulePage'));
const FormulationPage = lazy(() => import('./pages/FormulationPage'));
const BookmarksPage = lazy(() => import('./pages/BookmarksPage'));
const ComparisonPage = lazy(() => import('./pages/ComparisonPage'));
const KnowledgeImportPage = lazy(() => import('./pages/KnowledgeImportPage'));
const ReportsPage = lazy(() => import('./pages/ReportsPage'));
const HealthLogPage = lazy(() => import('./pages/HealthLogPage'));
const RemoteAssistPage = lazy(() => import('./pages/RemoteAssistPage'));
const ShareCardsPage = lazy(() => import('./pages/ShareCardsPage'));
const TriagePage = lazy(() => import('./pages/TriagePage'));
const KnowledgeHubPage = lazy(() => import('./pages/KnowledgeHubPage'));

const PageFallback = () => (
  <div style={{ padding: 48, textAlign: 'center' }}>
    <span>加载中...</span>
  </div>
);

function AuthGuard({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuth();
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}

/** 路由守卫：管理员专属路径仅 admin 可入；长辈模式下仅允许白名单路径 */
function RouteGuard({ children }: { children: React.ReactNode }) {
  const location = useLocation();
  const { user } = useAuth();
  const { isElderlyMode } = useElderlyMode();
  const role = (user as { role?: string } | null)?.role ?? 'user';

  if (isSystemPath(location.pathname) && role !== 'admin') {
    return <Navigate to="/" replace />;
  }
  if (isElderlyMode && !ELDERLY_ALLOWED_PATHS.includes(location.pathname)) {
    return <Navigate to="/" replace />;
  }
  return <>{children}</>;
}

function LayoutSwitch() {
  const { isElderlyMode } = useElderlyMode();

  if (isElderlyMode) {
    return (
      <AuthGuard>
        <RouteGuard>
          <ElderlyLayout />
        </RouteGuard>
      </AuthGuard>
    );
  }

  return (
    <AuthGuard>
      <RouteGuard>
        <AppLayout />
      </RouteGuard>
    </AuthGuard>
  );
}

function ThemedApp() {
  const { isDark } = useTheme();
  return (
    <ConfigProvider theme={isDark ? darkTheme : lightTheme}>
      <Suspense fallback={<PageFallback />}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={<LayoutSwitch />}>
            <Route index element={<Dashboard />} />
            <Route path="herbs" element={<HerbList />} />
            <Route path="herbs/:id" element={<HerbDetail />} />
            <Route path="formulas" element={<FormulaList />} />
            <Route path="formulas/:id" element={<FormulaDetail />} />
            <Route path="medicines" element={<MedicineList />} />
            <Route path="chat" element={<ChatPage />} />
            <Route path="reminders" element={<RemindersPage />} />
            <Route path="family" element={<FamilyMembersPage />} />
            <Route path="constitution" element={<ConstitutionPage />} />
            <Route path="profile" element={<ProfilePage />} />
            <Route path="favorites" element={<FavoritesPage />} />
            <Route path="classics" element={<ClassicsBookshelf />} />
            <Route path="classics/:id" element={<ClassicReader />} />
            <Route path="knowledge-graph" element={<KnowledgeGraphPage />} />
            <Route path="knowledge-hub" element={<KnowledgeHubPage />} />
            <Route path="therapies" element={<TherapiesPage />} />
            <Route path="acupoints" element={<MeridianAcupointPage />} />
            <Route path="knowledge-browse" element={<KnowledgeBrowsePage />} />
            <Route path="admin" element={<AdminPage />} />
            <Route path="health-practice" element={<HealthPracticePage />} />
            <Route path="medication-plans" element={<MedicationPlansPage />} />
            <Route path="medication-schedule" element={<MedicationSchedulePage />} />
            <Route path="formulation" element={<FormulationPage />} />
            <Route path="bookmarks" element={<BookmarksPage />} />
            <Route path="comparison" element={<ComparisonPage />} />
            <Route path="knowledge-import" element={<KnowledgeImportPage />} />
            <Route path="reports" element={<ReportsPage />} />
            <Route path="health-log" element={<HealthLogPage />} />
            <Route path="remote-assist" element={<RemoteAssistPage />} />
            <Route path="share-cards" element={<ShareCardsPage />} />
            <Route path="seasonal" element={<SeasonalHealthPage />} />
            <Route path="safety" element={<SafetyCheckPage />} />
            <Route path="triage" element={<TriagePage />} />
            <Route path="settings" element={<SettingsPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </ConfigProvider>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <ThemeProvider>
          <ElderlyModeProvider>
            <ErrorBoundary>
              <ThemedApp />
            </ErrorBoundary>
          </ElderlyModeProvider>
        </ThemeProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}
