/** Remove this browser's push endpoint from the signed-in account, then unsubscribe locally. */
export async function removeBrowserPushSubscription(token: string): Promise<void> {
  if (!('serviceWorker' in navigator) || !('PushManager' in window)) return;

  const registration = await navigator.serviceWorker.getRegistration('/');
  const subscription = await registration?.pushManager.getSubscription();
  if (!subscription) return;

  try {
    const response = await fetch('/api/push/subscriptions', {
      method: 'DELETE',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ endpoint: subscription.endpoint }),
      signal: AbortSignal.timeout(2000),
    });
    if (!response.ok) throw new Error(`Push subscription removal failed (${response.status})`);
  } finally {
    // Stop this device from receiving notifications even if the server is unavailable.
    await subscription.unsubscribe();
  }
}
