/**
 * Favorites Page (收藏) E2E tests.
 *
 * Covers:
 * - Page loads with table or list
 * - Filter controls visible (type filter, tag filter, search)
 * - Empty state when no favorites
 * - Auth guard
 */
import { test, expect } from '@playwright/test';
import { registerViaApi, setAuthState } from './api-auth';
import { logout } from './helpers';

let token: string;
let user: string;

test.beforeAll(async () => {
  const auth = await registerViaApi('fav');
  token = auth.token;
  user = auth.user;
});

test.describe('Favorites — Layout & Elements', () => {
  test.beforeEach(async ({ page }) => {
    await setAuthState(page, token, user);
  });

  test('should load favorites page with title', async ({ page }) => {
    await page.goto('/favorites');
    await expect(page).toHaveURL('/favorites');
    await expect(page.getByRole('heading', { name: /我的收藏/ })).toBeVisible();
  });

  test('should show filter controls', async ({ page }) => {
    await page.goto('/favorites');
    await expect(page.getByText('筛选类型')).toBeVisible();
    await expect(page.getByText('全部标签')).toBeVisible();
    await expect(page.getByPlaceholder('搜索标题')).toBeVisible();
  });

  test('should show empty state when no favorites', async ({ page }) => {
    await page.goto('/favorites');
    await expect(page.getByText(/暂无收藏/)).toBeVisible();
  });
});

test.describe('Favorites — Auth Guard', () => {
  test('should redirect to login when not authenticated', async ({ page }) => {
    await page.goto('/favorites');
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
    await page.goto('/favorites');
    await page.waitForURL(/\/login/);
  });
});
