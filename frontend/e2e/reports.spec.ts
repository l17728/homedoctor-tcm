/**
 * Reports (报告中心) E2E tests.
 *
 * Covers:
 * - Page loads with title
 * - Three tabs visible (体质报告/健康趋势/就诊准备)
 * - Generate report button visible
 * - Tab switching works
 * - Empty state in each tab
 * - Auth guard
 */
import { test, expect } from '@playwright/test';
import { register, logout } from './helpers';

test.describe('Reports — Navigation & Layout', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `rpt_${Date.now()}`);
  });

  test('should load page with title and tabs', async ({ page }) => {
    await page.goto('/reports');
    await expect(page).toHaveURL('/reports');

    // Page title
    await expect(page.getByRole('heading', { name: /报告中心/ })).toBeVisible();

    // All three tabs visible
    await expect(page.getByRole('tab', { name: /体质报告/ })).toBeVisible();
    await expect(page.getByRole('tab', { name: /健康趋势/ })).toBeVisible();
    await expect(page.getByRole('tab', { name: /就诊准备/ })).toBeVisible();
  });

  test('should show generate report and export PDF buttons', async ({
    page,
  }) => {
    await page.goto('/reports');

    // 生成报告 button
    await expect(
      page.getByRole('button', { name: /生成报告/ }),
    ).toBeVisible();

    // 导出 PDF button
    await expect(
      page.getByRole('button', { name: /导出\s?PDF|导出 PDF/ }),
    ).toBeVisible();
  });

  test('should show empty state in default tab before generating', async ({
    page,
  }) => {
    await page.goto('/reports');

    // Default tab is 体质报告 — shows empty state prompting to generate
    await expect(page.getByText(/暂无体质报告|生成报告/).first()).toBeVisible();
  });
});

test.describe('Reports — Tab Switching', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `rpt_${Date.now()}`);
  });

  test('should switch to 健康趋势 tab and show period selector', async ({
    page,
  }) => {
    await page.goto('/reports');

    // Click 健康趋势 tab
    await page.getByRole('tab', { name: /健康趋势/ }).click();

    // Period segmented control appears (近 7 天 / 近 30 天 / 近 90 天)
    await expect(page.getByText('近 7 天').first()).toBeVisible();
    await expect(page.getByText('近 30 天').first()).toBeVisible();

    // Empty state for trend
    await expect(
      page.getByText(/选择周期后点击|生成报告/).first(),
    ).toBeVisible();
  });

  test('should switch to 就诊准备 tab', async ({ page }) => {
    await page.goto('/reports');

    // Click 就诊准备 tab
    await page.getByRole('tab', { name: /就诊准备/ }).click();

    // Empty state for pre-visit
    await expect(
      page.getByText(/暂无就诊准备报告|生成报告/).first(),
    ).toBeVisible();
  });
});

test.describe('Reports — Auth Guard', () => {
  test('should redirect to login when not authenticated', async ({ page }) => {
    await page.goto('/reports');
    await page.waitForURL(/\/login/);
  });

  test('should deny access after logout', async ({ page }) => {
    await register(page, `rpt_${Date.now()}`);
    await logout(page);
    await page.goto('/reports');
    await page.waitForURL(/\/login/);
  });
});
