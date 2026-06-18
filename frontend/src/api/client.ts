export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = 'ApiError';
  }
}

interface RequestOptions extends Omit<RequestInit, 'headers'> {
  headers?: Record<string, string>;
}

export async function request<T>(
  url: string,
  options?: RequestOptions,
): Promise<T> {
  const token = localStorage.getItem('token');
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options?.headers ?? {}),
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  const memberId = localStorage.getItem('current_member_id');
  if (memberId) {
    headers['X-Member-Id'] = memberId;
  }

  const response = await fetch(url, { ...options, headers });

  if (response.status === 401) {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    window.location.href = '/login';
    throw new ApiError(401, '未授权，请重新登录');
  }

  if (!response.ok) {
    let message = '请求失败';
    try {
      const data = (await response.json()) as { message?: string; detail?: string };
      message = data.message ?? data.detail ?? message;
    } catch {
      // use default message
    }
    throw new ApiError(response.status, message);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export async function requestUpload<T>(
  url: string,
  body: FormData,
): Promise<T> {
  const headers: Record<string, string> = {};
  const token = localStorage.getItem('token');
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  const memberId = localStorage.getItem('current_member_id');
  if (memberId) {
    headers['X-Member-Id'] = memberId;
  }

  const response = await fetch(url, { method: 'POST', headers, body });

  if (response.status === 401) {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    window.location.href = '/login';
    throw new ApiError(401, '未授权，请重新登录');
  }

  if (!response.ok) {
    let msg = '上传失败';
    try {
      const data = (await response.json()) as { message?: string; detail?: string };
      msg = data.message ?? data.detail ?? msg;
    } catch {
    }
    throw new ApiError(response.status, msg);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}
