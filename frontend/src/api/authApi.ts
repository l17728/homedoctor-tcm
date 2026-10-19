import { request } from './client';

export interface User {
  id: string;
  username: string;
  role?: 'admin' | 'user';
  display_name?: string;
  family_id?: string;
}

export interface AuthResponse {
  token: string;
  user: User;
}

export interface RegisterConsent {
  consent_privacy: boolean;
  consent_health_data: boolean;
  birth_year?: number;
}

export interface ConsentStatus {
  consent_privacy: boolean;
  consent_health_data: boolean;
  consent_date: string | null;
  birth_year: number | null;
}

interface BackendAuthResponse {
  access_token: string;
  token_type: string;
  user: User;
}

function mapAuthResponse(raw: BackendAuthResponse): AuthResponse {
  return { token: raw.access_token, user: raw.user };
}

export async function loginApi(
  username: string,
  password: string,
): Promise<AuthResponse> {
  const raw = await request<BackendAuthResponse>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  });
  return mapAuthResponse(raw);
}

export async function registerApi(
  username: string,
  password: string,
  consent: RegisterConsent,
): Promise<AuthResponse> {
  const raw = await request<BackendAuthResponse>('/api/auth/register', {
    method: 'POST',
    body: JSON.stringify({ username, password, ...consent }),
  });
  return mapAuthResponse(raw);
}

export async function getMe(): Promise<User> {
  return request<User>('/api/auth/me');
}

/** Best-effort server-side token revocation; intentionally avoids request()'s 401 redirect side effect. */
export async function logoutApi(token: string): Promise<void> {
  const response = await fetch('/api/auth/logout', {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    signal: AbortSignal.timeout(2000),
  });
  if (!response.ok) throw new Error(`Logout revocation failed (${response.status})`);
}

export async function getConsentStatus(): Promise<ConsentStatus> {
  return request<ConsentStatus>('/api/auth/consent-status');
}
