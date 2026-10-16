import { request, type FullConfig } from '@playwright/test';

export default async function globalSetup(_config: FullConfig): Promise<void> {
  const webPort = Number(process.env.HOMEDOCTOR_WEB_PORT ?? 3000);
  const api = await request.newContext({ baseURL: `http://127.0.0.1:${webPort}` });
  const credentials = { username: 'testuser', password: 'testpass123' };

  try {
    const registration = await api.post('/api/auth/register', {
      data: {
        ...credentials,
        consent_privacy: true,
        consent_health_data: true,
      },
    });

    if (registration.ok()) return;

    // Reuse the isolated CI test account if a local run kept its temp DB.
    const login = await api.post('/api/auth/login', { data: credentials });
    if (!login.ok()) {
      throw new Error(
        `Could not prepare E2E test account: register=${registration.status()}, login=${login.status()}`,
      );
    }
  } finally {
    await api.dispose();
  }
}
