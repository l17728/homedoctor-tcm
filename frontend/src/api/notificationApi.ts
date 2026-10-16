import { request } from './client';

export interface InAppNotification {
  id: string;
  type?: string;
  title: string;
  target?: string;
  created_at?: string;
  unread: boolean;
}

export async function getNotifications(): Promise<InAppNotification[]> {
  const data = await request<{ items?: InAppNotification[] }>('/api/notifications');
  return data.items ?? [];
}

export async function markNotificationRead(id: string): Promise<void> {
  await request(`/api/notifications/${encodeURIComponent(id)}/read`, { method: 'POST' });
}
