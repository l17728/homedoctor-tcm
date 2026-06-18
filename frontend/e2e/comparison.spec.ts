/**
 * Comparison (对比分析) page E2E tests.
 *
 * Covers:
 * - Page renders with title
 * - Type selector (中药对比/方剂对比) visible
 * - Selection input (Select) visible
 * - "开始对比" button exists and is initially disabled
 * - Switching type resets selection
 * - Empty state prompt visible before comparison
 */
import { test, expect } from '@playwright/test';
import { chineseText } from './helpers';
import { registerWithConsent as register } from './test-helpers';

test.describe('Comparison Page — 对比分析', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `user_${Date.now()}`);
  });

  test('should load page with title and type selector', async ({ page }) => {
    await page.goto('/comparison');

    await expect(page).toHaveURL('/comparison');
    // Page title heading "对比分析"
    await expect(page.getByRole('heading', { name: /对比分析/ })).toBeVisible();

    // Type label "对比类型"
    await expect(page.getByText('对比类型')).toBeVisible();

    // Radio buttons rendered as Radio.Button — label text is clickable
    await expect(page.getByText('中药对比', { exact: true })).toBeVisible();
    await expect(page.getByText('方剂对比', { exact: true })).toBeVisible();
  });

  test('should show selection input and compare button', async ({ page }) => {
    await page.goto('/comparison');
    await page.waitForTimeout(1000);

    // Selection label text
    await expect(page.getByText(/选择项目/).first()).toBeVisible();

    // Wait for options to load (Select is hidden while Spin shows)
    await page.waitForTimeout(2000);

    // AntD 5 multi-mode Select renders placeholder in a div, not input attribute
    await expect(page.locator('.ant-select-selection-placeholder').filter({ hasText: '搜索并选择' })).toBeVisible();

    // "开始对比" button
    await expect(
      page.getByRole('button', { name: chineseText('开始对比') }),
    ).toBeVisible();
  });

  test('should have 开始对比 button disabled when fewer than 2 items selected', async ({
    page,
  }) => {
    await page.goto('/comparison');
    await page.waitForTimeout(1000);

    // The compare button should be disabled initially
    const compareBtn = page.getByRole('button', { name: chineseText('开始对比') });
    await expect(compareBtn).toBeDisabled();

    // Should show "已选 0 / 5（至少 2 个）"
    await expect(page.getByText(/已选.*0.*至少.*2/)).toBeVisible();
  });

  test('should show empty state prompt before comparison', async ({ page }) => {
    await page.goto('/comparison');
    await page.waitForTimeout(1000);

    // Empty state with instruction text
    await expect(
      page.getByText(/选择项目后点击.*开始对比/),
    ).toBeVisible();
  });

  test('should switch between herb and formula comparison types', async ({ page }) => {
    await page.goto('/comparison');
    await page.waitForTimeout(1000);

    // Default is herb
    await expect(page.getByText('中药对比', { exact: true })).toBeVisible();

    // Switch to formula — click the label text (Radio.Button renders label as clickable span)
    await page.getByText('方剂对比', { exact: true }).click();
    await page.waitForTimeout(2000);

    // AntD 5 multi-mode Select renders placeholder in a div
    await expect(page.locator('.ant-select-selection-placeholder').filter({ hasText: '方剂' })).toBeVisible();

    // Switch back to herb
    await page.getByText('中药对比', { exact: true }).click();
    await page.waitForTimeout(2000);
    await expect(page.locator('.ant-select-selection-placeholder').filter({ hasText: '中药' })).toBeVisible();
  });
});
