import React, {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
} from 'react';
import {
  loginApi,
  registerApi,
  getMe,
  logoutApi,
  type User,
  type AuthResponse,
  type RegisterConsent,
} from '../api/authApi';

interface AuthContextType {
  user: User | null;
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<void>;
  register: (username: string, password: string, consent: RegisterConsent) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(() => {
    const stored = localStorage.getItem('user');
    if (stored) {
      try {
        return JSON.parse(stored) as User;
      } catch {
        return null;
      }
    }
    return null;
  });

  const isAuthenticated = !!user && !!localStorage.getItem('token');

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (token && (!user || !user.role)) {
      getMe()
        .then((currentUser) => {
          localStorage.setItem('user', JSON.stringify(currentUser));
          setUser(currentUser);
        })
        .catch(() => {
          // A temporary network failure must not log out a valid cached session.
          // The API client already clears the session for an expired/invalid token.
          if (!localStorage.getItem('token')) setUser(null);
        });
    }
    // Only run on mount — intentionally empty deps
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleAuthResponse = useCallback((response: AuthResponse) => {
    localStorage.setItem('token', response.token);
    localStorage.setItem('user', JSON.stringify(response.user));
    setUser(response.user);
  }, []);

  const login = useCallback(
    async (username: string, password: string) => {
      const response = await loginApi(username, password);
      handleAuthResponse(response);
    },
    [handleAuthResponse],
  );

  const register = useCallback(
    async (username: string, password: string, consent: RegisterConsent) => {
      const response = await registerApi(username, password, consent);
      handleAuthResponse(response);
    },
    [handleAuthResponse],
  );

  const logout = useCallback(async () => {
    const token = localStorage.getItem('token');
    try {
      if (token) {
        try {
          const { removeBrowserPushSubscription } = await import('../api/pushApi');
          await removeBrowserPushSubscription(token);
        } catch (error) {
          console.warn('Could not remove browser push subscription during logout', error);
        }
        try {
          await logoutApi(token);
        } catch (error) {
          console.warn('Could not revoke server token during logout', error);
        }
      }
    } finally {
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      localStorage.removeItem('current_member_id');
      setUser(null);
    }
  }, []);

  return (
    <AuthContext.Provider
      value={{ user, isAuthenticated, login, register, logout }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
}
