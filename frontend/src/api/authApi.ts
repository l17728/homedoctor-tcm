import { request } from './client';

export interface User {
  id: string;
  username: string;
}

export interface AuthResponse {
  token: string;
  user: User;
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
): Promise<AuthResponse> {
  const raw = await request<BackendAuthResponse>('/api/auth/register', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  });
  return mapAuthResponse(raw);
}

export async function getMe(): Promise<User> {
  return request<User>('/api/auth/me');
}
