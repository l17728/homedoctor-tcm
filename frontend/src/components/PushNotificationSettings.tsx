import { useEffect, useState } from 'react';
import { Alert, Button, Space, Typography, message } from 'antd';
import { BellOutlined } from '@ant-design/icons';
import { request } from '../api/client';
import { removeBrowserPushSubscription } from '../api/pushApi';

const { Text } = Typography;
type PushConfig = { enabled: boolean; public_key: string };

function decodeKey(value: string): ArrayBuffer {
  const padded = value + '='.repeat((4 - (value.length % 4)) % 4);
  const raw = atob(padded.replace(/-/g, '+').replace(/_/g, '/'));
  const bytes = new Uint8Array(raw.length);
  for (let index = 0; index < raw.length; index += 1) bytes[index] = raw.charCodeAt(index);
  return bytes.buffer;
}

export default function PushNotificationSettings() {
  const [config, setConfig] = useState<PushConfig | null>(null);
  const [subscribed, setSubscribed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [syncError, setSyncError] = useState(false);

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const result = await request<PushConfig>('/api/push/config');
        if (!active) return;
        setConfig(result);
        if ('serviceWorker' in navigator && 'PushManager' in window) {
          const registration = await navigator.serviceWorker.register('/sw.js');
          const subscription = await registration.pushManager.getSubscription();
          if (!active) return;
          setSubscribed(Boolean(subscription));
          // Re-associate an existing browser subscription with the currently signed-in account.
          if (subscription && result.enabled) {
            try {
              await request('/api/push/subscriptions', {
                method: 'POST',
                body: JSON.stringify(subscription.toJSON()),
              });
            } catch {
              if (active) setSyncError(true);
            }
          }
        }
      } catch {
        if (active) setConfig({ enabled: false, public_key: '' });
      }
    })();
    return () => { active = false; };
  }, []);

  const enable = async () => {
    if (!config?.enabled || !('serviceWorker' in navigator) || !('PushManager' in window)) return;
    setBusy(true);
    try {
      const permission = await Notification.requestPermission();
      if (permission !== 'granted') throw new Error('请允许浏览器发送通知后重试');
      const registration = await navigator.serviceWorker.register('/sw.js');
      const subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: decodeKey(config.public_key),
      });
      await request('/api/push/subscriptions', {
        method: 'POST',
        body: JSON.stringify(subscription.toJSON()),
      });
      setSubscribed(true);
      setSyncError(false);
      message.success('浏览器推送已开启');
    } catch (error) {
      message.error(error instanceof Error ? error.message : '开启推送失败');
    } finally {
      setBusy(false);
    }
  };

  const disable = async () => {
    setBusy(true);
    try {
      const token = localStorage.getItem('token');
      if (!token) throw new Error('登录状态已失效');
      await removeBrowserPushSubscription(token);
      setSubscribed(false);
      message.success('浏览器推送已关闭');
    } catch {
      message.error('关闭推送失败，请检查网络后重试');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Space direction="vertical" size={12} style={{ width: '100%' }}>
      <Text>在浏览器后台接收每周健康摘要。推送仅在已授权的浏览器中生效。</Text>
      {!config?.enabled && <Alert type="info" showIcon message="服务器尚未配置 VAPID 密钥，浏览器推送不可用。" />}
      {config?.enabled && (!('serviceWorker' in navigator) || !('PushManager' in window)) && (
        <Alert type="warning" showIcon message="当前浏览器不支持 Web Push。" />
      )}
      {syncError && <Alert type="warning" showIcon message="当前浏览器订阅尚未同步到此账户，请关闭后重新开启推送。" />}
      {config?.enabled && 'PushManager' in window && (
        <Button
          icon={<BellOutlined />}
          loading={busy}
          disabled={!('serviceWorker' in navigator)}
          onClick={subscribed ? disable : enable}
        >
          {subscribed ? '关闭浏览器推送' : '开启浏览器推送'}
        </Button>
      )}
    </Space>
  );
}
