import { useCallback, useEffect, useState } from 'react';
import { Alert, Badge, Button, Dropdown, Empty, List, Typography, message } from 'antd';
import { BellOutlined } from '@ant-design/icons';
import { getNotifications, markNotificationRead, type InAppNotification } from '../api/notificationApi';
import {
  getReminderNotificationPermission,
  requestReminderNotificationPermission,
  type PermissionState,
} from '../hooks/useNotifications';

interface Props {
  onOpen: (path: string) => void;
}

export default function NotificationBell({ onOpen }: Props) {
  const [items, setItems] = useState<InAppNotification[]>([]);
  const [permission, setPermission] = useState<PermissionState>(getReminderNotificationPermission);
  const refresh = useCallback(async () => {
    try { setItems(await getNotifications()); } catch { /* notification polling is best effort */ }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 60_000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const open = async (item: InAppNotification) => {
    if (item.unread) {
      try {
        await markNotificationRead(item.id);
        setItems((current) => current.map((entry) => entry.id === item.id ? { ...entry, unread: false } : entry));
      } catch { /* still allow opening the destination */ }
    }
    onOpen(item.target || '/remote-assist');
  };

  const enableReminderNotifications = async () => {
    const next = await requestReminderNotificationPermission();
    setPermission(next);
    if (next === 'granted') message.success('服药提醒通知已开启');
    else if (next === 'denied') message.warning('请在浏览器设置中允许本网站发送通知');
    else if (next === 'unsupported') message.info('当前浏览器不支持系统通知');
  };

  return (
    <Dropdown trigger={['click']} placement="bottomRight" dropdownRender={() => (
      <div style={{ width: 320, maxHeight: 400, overflowY: 'auto', background: '#fff', padding: 12, borderRadius: 8, boxShadow: '0 4px 16px #0002' }}>
        <Typography.Title level={5} style={{ margin: '4px 8px 12px' }}>通知</Typography.Title>
        {permission === 'default' && (
          <Button block style={{ minHeight: 44, marginBottom: 8 }} onClick={() => void enableReminderNotifications()}>
            开启服药提醒通知
          </Button>
        )}
        {permission === 'denied' && (
          <Alert type="info" showIcon message="浏览器已关闭通知权限，请在浏览器设置中允许后重试。" style={{ marginBottom: 8 }} />
        )}
        {items.length === 0 ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无通知" /> : (
          <List dataSource={items} renderItem={(item) => (
            <List.Item style={{ background: item.unread ? '#f0f7ff' : undefined, padding: '4px 0' }}>
              <Button
                type="text"
                block
                aria-label={`打开通知：${item.title}`}
                style={{ minHeight: 56, height: 'auto', padding: '8px', textAlign: 'left', whiteSpace: 'normal' }}
                onClick={() => void open(item)}
              >
                <span style={{ display: 'block', width: '100%' }}>
                  <span style={{ display: 'block', fontWeight: item.unread ? 600 : 400 }}>
                    {item.unread ? '• ' : ''}{item.title}
                  </span>
                  {item.created_at && (
                    <span style={{ display: 'block', fontSize: 14, color: '#666' }}>
                      {new Date(item.created_at).toLocaleString()}
                    </span>
                  )}
                </span>
              </Button>
            </List.Item>
          )} />
        )}
      </div>
    )}>
      <Badge count={items.filter((item) => item.unread).length} overflowCount={99}>
        <Button aria-label="通知" icon={<BellOutlined />} style={{ minHeight: 44 }}>通知</Button>
      </Badge>
    </Dropdown>
  );
}
