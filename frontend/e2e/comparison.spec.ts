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
    // Page title "对比分析"
    await expect(page.getByText('对比分析').first()).toBeVisible();

    // Type label "对比类型"
    await expect(page.getByText('对比类型')).toBeVisible();

    // Radio buttons: 中药对比 / 方剂对比
    await expect(page.getByRole('radio', { name: /中药对比/ })).toBeVisible();
    await expect(page.getByRole('radio', { name: /方剂对比/ })).toBeVisible();
  });

  test('should show selection input and compare button', async ({ page }) => {
    await page.goto('/comparison');
    await page.waitForTimeout(1000);

    // Selection label text
    await expect(page.getByText(/选择项目/)).toBeVisible();

    // Multi-select input for choosing herbs/formulas
    await expect(page.getByPlaceholder(/搜索并选择/)).toBeVisible();

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

    // Default is herb — radio should be checked
    const herbRadio = page.getByRole('radio', { name: /中药对比/ });
    await expect(herbRadio).toBeChecked();

    // Switch to formula
    await page.getByRole('radio', { name: /方剂对比/ }).click();
    await expect(page.getByRole('radio', { name: /方剂对比/ })).toBeChecked();

    // Placeholder should change to formula search
    await expect(page.getByPlaceholder(/搜索并选择方剂/)).toBeVisible();

    // Switch back to herb
    await page.getByRole('radio', { name: /中药对比/ }).click();
    await expect(page.getByPlaceholder(/搜索并选择中药/)).toBeVisible();
  });
});
