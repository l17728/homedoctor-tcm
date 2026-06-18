/**
 * Bookmarks (书签) page E2E tests.
 *
 * Covers:
 * - Page renders with title and "新建合集" button
 * - Filter controls visible (类型/星标/标签)
 * - Empty state when no bookmarks for new user
 * - "新建合集" button opens modal with form
 * - Table columns visible when data exists
 */
import { test, expect } from '@playwright/test';
import { chineseText } from './helpers';
import { registerWithConsent as register } from './test-helpers';

test.describe('Bookmarks Page — 我的书签', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `user_${Date.now()}`);
  });

  test('should load page with title and new collection button', async ({ page }) => {
    await page.goto('/bookmarks');

    await expect(page).toHaveURL('/bookmarks');
    // Page title "我的书签"
    await expect(page.getByText('我的书签').first()).toBeVisible();

    // "新建合集" button
    await expect(
      page.getByRole('button', { name: chineseText('新建合集') }),
    ).toBeVisible();
  });

  test('should show filter controls (类型/星标/标签)', async ({ page }) => {
    await page.goto('/bookmarks');

    // Type filter Select
    await expect(
      page.locator('.ant-select').filter({ hasText: /筛选类型/ }).first(),
    ).toBeVisible();

    // Starred filter Select
    await expect(
      page.locator('.ant-select').filter({ hasText: /星标/ }).first(),
    ).toBeVisible();

    // Tag filter Select
    await expect(
      page.locator('.ant-select').filter({ hasText: /筛选标签/ }).first(),
    ).toBeVisible();
  });

  test('should show table with correct columns or empty state', async ({ page }) => {
    await page.goto('/bookmarks');
    await page.waitForTimeout(1500);

    const hasTable = await page.locator('.ant-table').first().isVisible().catch(() => false);
    const hasEmpty = await page.getByText(/暂无书签/).isVisible().catch(() => false);

    expect(hasTable || hasEmpty).toBeTruthy();

    if (hasTable) {
      const table = page.locator('.ant-table');
      // Expected columns
      for (const col of ['类型', '标题', '操作']) {
        await expect(table.getByText(col).first()).toBeVisible();
      }
    }
  });

  test('should open collection modal when clicking 新建合集', async ({ page }) => {
    await page.goto('/bookmarks');

    await page.getByRole('button', { name: chineseText('新建合集') }).click();
    await page.waitForTimeout(500);

    // Modal should appear
    const modal = page.locator('.ant-modal').last();
    await expect(modal).toBeVisible();

    // Should have title "新建合集"
    await expect(modal.getByText('新建合集')).toBeVisible();

    // Form field "合集名称" label
    await expect(modal.getByText('合集名称')).toBeVisible();

    // Input with placeholder
    await expect(modal.getByPlaceholder(/补气类中药/)).toBeVisible();

    // Cancel button to close
    await modal.getByRole('button', { name: /取消/ }).click();
  });

  test('should show validation error when creating empty collection', async ({
    page,
  }) => {
    await page.goto('/bookmarks');

    await page.getByRole('button', { name: chineseText('新建合集') }).click();
    await page.waitForTimeout(500);

    const modal = page.locator('.ant-modal').last();

    // Click "创建" (OK) without filling title
    await modal.getByRole('button', { name: /创建/ }).click();
    await page.waitForTimeout(500);

    // Should show validation error "请输入合集名称"
    await expect(page.getByText(/请输入合集名称/)).toBeVisible();
  });
});
