/**
 * Share Cards Page (分享卡) E2E tests.
 *
 * Covers:
 * - Page loads with card type selector
 * - "生成分享卡" button visible
 * - Member selector exists
 * - Empty preview + history states
 * - Auth guard
 */
import { test, expect } from '@playwright/test';
import { registerViaApi, setAuthState } from './api-auth';
import { logout } from './helpers';

let token: string;
let user: string;

test.beforeAll(async () => {
  const auth = await registerViaApi('sc');
  token = auth.token;
  user = auth.user;
});

test.describe('Share Cards — Layout & Elements', () => {
  test.beforeEach(async ({ page }) => {
    await setAuthState(page, token, user);
  });

  test('should load page with card type selector', async ({ page }) => {
    await page.goto('/share-cards');
    await expect(page).toHaveURL('/share-cards');
    await expect(page.getByRole('heading', { name: /分享卡/ })).toBeVisible();
    await expect(page.getByText('健康概览')).toBeVisible();
  });

  test('should show generate button and member selector', async ({ page }) => {
    await page.goto('/share-cards');
    await expect(page.getByText('选择家庭成员')).toBeVisible();
    await expect(
      page.getByRole('button', { name: /生成分享卡/ }),
    ).toBeVisible();
  });

  test('should show empty preview and history states', async ({ page }) => {
    await page.goto('/share-cards');

    await expect(page.getByText('分享卡预览')).toBeVisible();
    await expect(page.getByText(/选择家人后点击.*生成分享卡/)).toBeVisible();

    await expect(page.getByText('历史分享卡')).toBeVisible();
    await expect(page.getByText('暂无历史卡片')).toBeVisible();

    await expect(page.getByText('月度家庭报告')).toBeVisible();
    await expect(page.getByText(/暂无月度数据/)).toBeVisible();
  });
});

test.describe('Share Cards — Auth Guard', () => {
  test('should redirect to login when not authenticated', async ({ page }) => {
    await page.goto('/share-cards');
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
    await page.goto('/share-cards');
    await page.waitForURL(/\/login/);
  });
});
