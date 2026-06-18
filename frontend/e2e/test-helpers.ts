/**
 * Extended E2E test helpers for 家庭医生 (Family Doctor) project.
 *
 * Registers via backend API + caches token at module level so each Playwright
 * worker makes at most ONE registration call. Subsequent tests in the same
 * worker reuse the cached token via localStorage.
 *
 * Usage: import { registerWithConsent as register } from './test-helpers';
 */
import { type Page } from '@playwright/test';
import { DEFAULT_PASSWORD } from './helpers';

interface BackendAuthResponse {
  access_token: string;
  token_type: string;
  user: { id: string; username: string };
}

// Module-level cache: shared across all tests in the same Playwright worker.
// Each worker process imports this module once, so only ONE API registration
// happens per worker regardless of how many tests/files it runs.
let cachedToken: string | null = null;
let cachedUser: { id: string; username: string } | null = null;

async function setAuthAndNavigate(page: Page): Promise<void> {
  await page.goto('/login');
  await page.evaluate(
    ({ token, user }) => {
      localStorage.setItem('token', token);
      localStorage.setItem('user', JSON.stringify(user));
    },
    { token: cachedToken!, user: cachedUser! },
  );
  await page.goto('/');
  await page.waitForLoadState('networkidle');
}

export async function registerWithConsent(
  page: Page,
  username: string,
  password: string = DEFAULT_PASSWORD,
): Promise<void> {
  if (cachedToken && cachedUser) {
    await setAuthAndNavigate(page);
    return;
  }

  const response = await page.request.post('/api/auth/register', {
    data: {
      username,
      password,
      consent_privacy: true,
      consent_health_data: true,
    },
  });

  let authData: BackendAuthResponse;

  if (response.ok()) {
    authData = (await response.json()) as BackendAuthResponse;
  } else {
    const loginResponse = await page.request.post('/api/auth/login', {
      data: { username, password },
    });
    if (!loginResponse.ok()) {
      throw new Error(`Auth failed for ${username}`);
    }
    authData = (await loginResponse.json()) as BackendAuthResponse;
  }

  cachedToken = authData.access_token;
  cachedUser = authData.user;
  await setAuthAndNavigate(page);
}
