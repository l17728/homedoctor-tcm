import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ConfigProvider } from 'antd';
import { AuthProvider, useAuth } from './hooks/useAuth';
import { ThemeProvider, useTheme } from './hooks/useTheme';
import { ElderlyModeProvider, useElderlyMode } from './contexts/ElderlyModeContext';
import { ErrorBoundary } from './components/ErrorBoundary';
import { lightTheme, darkTheme } from './theme';
import AppLayout from './layouts/AppLayout';
import ElderlyLayout from './layouts/ElderlyLayout';
import LoginPage from './pages/LoginPage';
import Dashboard from './pages/Dashboard';
import HerbList from './pages/HerbList';
import HerbDetail from './pages/HerbDetail';
import FormulaList from './pages/FormulaList';
import FormulaDetail from './pages/FormulaDetail';
import MedicineList from './pages/MedicineList';
import ChatPage from './pages/ChatPage';
import SettingsPage from './pages/SettingsPage';
import RemindersPage from './pages/RemindersPage';
import ConstitutionPage from './pages/ConstitutionPage';
import ProfilePage from './pages/ProfilePage';
import FavoritesPage from './pages/FavoritesPage';
import SeasonalHealthPage from './pages/SeasonalHealthPage';
import SafetyCheckPage from './pages/SafetyCheckPage';
import FamilyMembersPage from './pages/FamilyMembersPage';
import KnowledgeGraphPage from './pages/KnowledgeGraphPage';
import ClassicsBookshelf from './pages/ClassicsBookshelf';
import ClassicReader from './pages/ClassicReader';
import TherapiesPage from './pages/TherapiesPage';
import MeridianAcupointPage from './pages/MeridianAcupointPage';
import KnowledgeBrowsePage from './pages/KnowledgeBrowsePage';
import HealthPracticePage from './pages/HealthPracticePage';
import MedicationPlansPage from './pages/MedicationPlansPage';
import MedicationSchedulePage from './pages/MedicationSchedulePage';
import FormulationPage from './pages/FormulationPage';
import BookmarksPage from './pages/BookmarksPage';
import ComparisonPage from './pages/ComparisonPage';
import KnowledgeImportPage from './pages/KnowledgeImportPage';
import ReportsPage from './pages/ReportsPage';
import HealthLogPage from './pages/HealthLogPage';
import RemoteAssistPage from './pages/RemoteAssistPage';
import ShareCardsPage from './pages/ShareCardsPage';
import TriagePage from './pages/TriagePage';
import KnowledgeHubPage from './pages/KnowledgeHubPage';

function AuthGuard({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuth();
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}

function LayoutSwitch() {
  const { isElderlyMode } = useElderlyMode();

  if (isElderlyMode) {
    return (
      <AuthGuard>
        <ElderlyLayout />
      </AuthGuard>
    );
  }

  return (
    <AuthGuard>
      <AppLayout />
    </AuthGuard>
  );
}

function ThemedApp() {
  const { isDark } = useTheme();
  return (
    <ConfigProvider theme={isDark ? darkTheme : lightTheme}>
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
