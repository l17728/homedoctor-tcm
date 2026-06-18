/**
 * Safety Check Page (安全检查) E2E tests.
 *
 * Covers:
 * - Page loads with herb/medicine input
 * - "检查" button visible (disabled initially)
 * - Result area empty state
 * - Add herb interaction enables check button
 * - Auth guard
 */
import { test, expect } from '@playwright/test';
import { registerViaApi, setAuthState } from './api-auth';
import { logout } from './helpers';

let token: string;
let user: string;

test.beforeAll(async () => {
  const auth = await registerViaApi('sf');
  token = auth.token;
  user = auth.user;
});

test.describe('Safety Check — Layout & Elements', () => {
  test.beforeEach(async ({ page }) => {
    await setAuthState(page, token, user);
  });

  test('should load page with title and herb/medicine inputs', async ({
    page,
  }) => {
    await page.goto('/safety');
    await expect(page).toHaveURL('/safety');
    await expect(page.getByRole('heading', { name: '安全检查' })).toBeVisible();
    await expect(
      page.getByPlaceholder('输入中药名称，如：黄芪、附子、半夏'),
    ).toBeVisible();
    await expect(
      page.getByPlaceholder('输入药品名称，如：阿司匹林、布洛芬'),
    ).toBeVisible();
  });

  test('should show check button disabled initially', async ({ page }) => {
    await page.goto('/safety');
    const checkBtn = page.getByRole('button', { name: /开始安全检查/ });
    await expect(checkBtn).toBeVisible();
    await expect(checkBtn).toBeDisabled();
  });

  test('should show empty result state with coverage info', async ({
    page,
  }) => {
    await page.goto('/safety');
    await expect(
      page.getByText(/添加药材和药品后.*开始安全检查/),
    ).toBeVisible();
    await expect(page.getByText('十八反十九畏')).toBeVisible();
  });
});

test.describe('Safety Check — Interaction', () => {
  test.beforeEach(async ({ page }) => {
    await setAuthState(page, token, user);
  });

  test('should add herb via input and enable check button', async ({
    page,
  }) => {
    await page.goto('/safety');
    await page
      .getByPlaceholder('输入中药名称，如：黄芪、附子、半夏')
      .fill('黄芪');
    await page
      .getByPlaceholder('输入中药名称，如：黄芪、附子、半夏')
      .press('Enter');

    const checkBtn = page.getByRole('button', { name: /开始安全检查/ });
    await expect(checkBtn).toBeEnabled();
  });

  test('should run check and show result area', async ({ page }) => {
    await page.goto('/safety');
    await page
      .getByPlaceholder('输入中药名称，如：黄芪、附子、半夏')
      .fill('甘草');
    await page
      .getByPlaceholder('输入中药名称，如：黄芪、附子、半夏')
      .press('Enter');

    await page.getByRole('button', { name: /开始安全检查/ }).click();

    await expect(
      page.getByText(/未发现严重安全问题|发现.*条安全警告/),
    ).toBeVisible({ timeout: 15000 });
  });
});

test.describe('Safety Check — Auth Guard', () => {
  test('should redirect to login when not authenticated', async ({ page }) => {
    await page.goto('/safety');
    await page.waitForURL(/\/login/);
  });

  test('should deny access after logout', async ({ page }) => {
    await page.goto('/login');
    await page.evaluate(
      ([t, u]) => {
        localStorage.setItem('token', t);
        localStorage.setItem('user', u);
      },
      [token, user],
    );
    await page.goto('/');
    await logout(page);
    await page.goto('/safety');
    await page.waitForURL(/\/login/);
  });
});
