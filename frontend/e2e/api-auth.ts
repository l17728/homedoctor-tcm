/**
 * API-based auth helper for E2E tests.
 *
 * Registers a user via direct HTTP call (no UI navigation), which is ~10x
 * faster than the UI-based register() helper and avoids rate-limit issues
 * when many tests need authentication.
 *
 * Usage in test files:
 *
 *   import { createAuthFixture } from './api-auth';
 *
 *   const { authToken, authUser, setAuth } = createAuthFixture('fam');
 *
 *   test.beforeAll(async () => { await authToken; });
 *   test.beforeEach(async ({ page }) => { await setAuth(page); });
 */
import { test, type Page } from '@playwright/test';

const API_BASE = `http://127.0.0.1:${Number(process.env.HOMEDOCTOR_WEB_PORT ?? 3000)}`;

interface BackendAuthResponse {
  access_token: string;
  token_type: string;
  user: { id: string; username: string };
}

export async function registerViaApi(
  prefix: string,
): Promise<{ token: string; user: string }> {
  const username = `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;

  for (let attempt = 0; ; attempt++) {
    const ctx = await test.request.newContext({ baseURL: API_BASE });

    const res = await ctx.post('/api/auth/register', {
      data: {
        username,
        password: 'testpass123',
        consent_privacy: true,
        consent_health_data: true,
      },
    });

    if (res.ok()) {
      const data: BackendAuthResponse = await res.json();
      await ctx.dispose();
      return {
        token: data.access_token,
        user: JSON.stringify(data.user),
      };
    }

    await ctx.dispose();

    if (res.status() === 429 && attempt < 6) {
      await new Promise((r) => setTimeout(r, 3000 * (attempt + 1)));
      continue;
    }

    const body = await res.text().catch(() => '');
    throw new Error(`Register failed (${res.status()}): ${body}`);
  }
}

/** Inject auth token into localStorage before page loads. */
export async function setAuthState(
  page: Page,
  token: string,
  user: string,
): Promise<void> {
  await page.addInitScript(([t, u]) => {
    localStorage.setItem('token', t);
    localStorage.setItem('user', u);
  }, [token, user]);
}
