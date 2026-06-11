import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ConfigProvider } from 'antd';
import { AuthProvider, useAuth } from './hooks/useAuth';
import { ThemeProvider, useTheme } from './hooks/useTheme';
import { lightTheme, darkTheme } from './theme';
import AppLayout from './layouts/AppLayout';
import LoginPage from './pages/LoginPage';
import Dashboard from './pages/Dashboard';
import HerbList from './pages/HerbList';
import HerbDetail from './pages/HerbDetail';
import FormulaList from './pages/FormulaList';
import FormulaDetail from './pages/FormulaDetail';
import MedicineList from './pages/MedicineList';
import ChatPage from './pages/ChatPage';
import SettingsPage from './pages/SettingsPage';

function AuthGuard({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuth();
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}

function ThemedApp() {
  const { isDark } = useTheme();
  return (
    <ConfigProvider theme={isDark ? darkTheme : lightTheme}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/"
          element={
            <AuthGuard>
              <AppLayout />
            </AuthGuard>
          }
        >
          <Route index element={<Dashboard />} />
          <Route path="herbs" element={<HerbList />} />
          <Route path="herbs/:id" element={<HerbDetail />} />
          <Route path="formulas" element={<FormulaList />} />
          <Route path="formulas/:id" element={<FormulaDetail />} />
          <Route path="medicines" element={<MedicineList />} />
          <Route path="chat" element={<ChatPage />} />
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
          <ThemedApp />
        </ThemeProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}
