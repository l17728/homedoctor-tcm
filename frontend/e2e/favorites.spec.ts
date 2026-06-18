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
import { register, logout } from './helpers';

test.describe('Favorites — Layout & Elements', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `fav_${Date.now()}`);
    await page.goto('/favorites');
  });

  test('should load favorites page with title', async ({ page }) => {
    await expect(page).toHaveURL('/favorites');
    await expect(page.getByRole('heading', { name: /我的收藏/ })).toBeVisible();
  });

  test('should show filter controls', async ({ page }) => {
    // Type filter Select
    await expect(page.getByText('筛选类型')).toBeVisible();

    // Tag filter Select
    await expect(page.getByText('全部标签')).toBeVisible();

    // Search input
    await expect(page.getByPlaceholder('搜索标题')).toBeVisible();
  });

  test('should show empty state when no favorites', async ({ page }) => {
    await expect(
      page.getByText(/暂无收藏/),
    ).toBeVisible();
  });
});

test.describe('Favorites — Auth Guard', () => {
  test('should redirect to login when not authenticated', async ({ page }) => {
    await page.goto('/favorites');
    await page.waitForURL(/\/login/);
  });

  test('should deny access after logout', async ({ page }) => {
    await register(page, `fav_${Date.now()}`);
    await logout(page);
    await page.goto('/favorites');
    await page.waitForURL(/\/login/);
  });
});
