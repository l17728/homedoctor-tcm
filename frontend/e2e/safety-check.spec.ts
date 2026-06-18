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
import { register, logout } from './helpers';

test.describe('Safety Check — Layout & Elements', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `sf_${Date.now()}`);
    await page.goto('/safety');
  });

  test('should load page with title and herb/medicine inputs', async ({
    page,
  }) => {
    await expect(page).toHaveURL('/safety');
    await expect(page.getByRole('heading', { name: '安全检查' })).toBeVisible();

    // Herb input
    await expect(
      page.getByPlaceholder('输入中药名称，如：黄芪、附子、半夏'),
    ).toBeVisible();

    // Medicine input
    await expect(
      page.getByPlaceholder('输入药品名称，如：阿司匹林、布洛芬'),
    ).toBeVisible();
  });

  test('should show check button disabled initially', async ({ page }) => {
    const checkBtn = page.getByRole('button', { name: /开始安全检查/ });
    await expect(checkBtn).toBeVisible();
    await expect(checkBtn).toBeDisabled();
  });

  test('should show empty result state with coverage info', async ({ page }) => {
    await expect(
      page.getByText(/添加药材和药品后.*开始安全检查/),
    ).toBeVisible();

    // Safety coverage tags
    await expect(page.getByText('十八反十九畏')).toBeVisible();
  });
});

test.describe('Safety Check — Interaction', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `sf_${Date.now()}`);
    await page.goto('/safety');
  });

  test('should add herb via input and enable check button', async ({ page }) => {
    // Type herb name and add
    await page
      .getByPlaceholder('输入中药名称，如：黄芪、附子、半夏')
      .fill('黄芪');
    await page.getByPlaceholder('输入中药名称，如：黄芪、附子、半夏').press('Enter');

    // Herb tag should appear
    await expect(
      page.locator('.ant-tag-color-green').filter({ hasText: '黄芪' }),
    ).toBeVisible();

    // Check button should now be enabled
    const checkBtn = page.getByRole('button', { name: /开始安全检查/ });
    await expect(checkBtn).toBeEnabled();
  });

  test('should run check and show result area', async ({ page }) => {
    // Add a herb
    await page
      .getByPlaceholder('输入中药名称，如：黄芪、附子、半夏')
      .fill('甘草');
    await page.getByPlaceholder('输入中药名称，如：黄芪、附子、半夏').press('Enter');

    // Run check
    await page.getByRole('button', { name: /开始安全检查/ }).click();

    // Result area should appear (either safe result or disclaimer)
    // The page shows result card with either "未发现严重安全问题" or warning count
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
    await register(page, `sf_${Date.now()}`);
    await logout(page);
    await page.goto('/safety');
    await page.waitForURL(/\/login/);
  });
});
