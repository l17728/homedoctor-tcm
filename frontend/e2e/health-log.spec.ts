/**
 * Health Log (每日健康打卡) E2E tests.
 *
 * Covers:
 * - Page loads with title and date picker
 * - Blood pressure section (收缩压/舒张压)
 * - Blood sugar / weight section
 * - Sleep / mood section
 * - Save button visible
 * - Recent 7 days section
 * - Auth guard
 */
import { test, expect } from '@playwright/test';
import { register, logout } from './helpers';

test.describe('Health Log — Navigation & Layout', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `hlog_${Date.now()}`);
  });

  test('should load page with title and date picker', async ({ page }) => {
    await page.goto('/health-log');
    await expect(page).toHaveURL('/health-log');

    // Page title
    await expect(page.getByRole('heading', { name: /每日健康打卡/ })).toBeVisible();

    // Date label
    await expect(page.getByText('打卡日期')).toBeVisible();

    // DatePicker is present
    await expect(page.locator('.ant-picker').first()).toBeVisible();

    // Refresh button
    await expect(page.getByRole('button', { name: /刷新/ })).toBeVisible();
  });

  test('should show blood pressure section with systolic/diastolic inputs', async ({
    page,
  }) => {
    await page.goto('/health-log');

    // BP section title
    await expect(page.getByText(/血压/).first()).toBeVisible();

    // Systolic / Diastolic labels
    await expect(page.getByText('收缩压')).toBeVisible();
    await expect(page.getByText('舒张压')).toBeVisible();

    // InputNumber placeholders
    await expect(page.getByPlaceholder('如 120')).toBeVisible();
    await expect(page.getByPlaceholder('如 80')).toBeVisible();
  });

  test('should show blood sugar / weight and sleep / mood sections', async ({
    page,
  }) => {
    await page.goto('/health-log');

    // Blood sugar / weight section
    await expect(page.getByText(/血糖/).first()).toBeVisible();
    await expect(page.getByText(/体重/).first()).toBeVisible();

    // Sleep / mood section
    await expect(page.getByText(/睡眠/).first()).toBeVisible();

    // Mood options (好 / 一般 / 差)
    await expect(page.getByText('今天的心情')).toBeVisible();
  });
});

test.describe('Health Log — Form Actions', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `hlog_${Date.now()}`);
  });

  test('should have save and clear buttons', async ({ page }) => {
    await page.goto('/health-log');

    // Save button (保存今日打卡 or 更新记录)
    await expect(
      page.getByRole('button', { name: /保存今日打卡|更新记录/ }),
    ).toBeVisible();

    // Clear button (清空)
    await expect(
      page.getByRole('button', { name: /清空/ }),
    ).toBeVisible();
  });

  test('should warn when saving empty form', async ({ page }) => {
    await page.goto('/health-log');

    // Click save without any data
    await page.getByRole('button', { name: /保存今日打卡|更新记录/ }).click();

    // Should show a warning toast about filling at least one metric
    await expect(
      page.locator('.ant-message-notice').first(),
    ).toBeVisible();
  });
});

test.describe('Health Log — Recent Logs', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `hlog_${Date.now()}`);
  });

  test('should show recent 7 days section', async ({ page }) => {
    await page.goto('/health-log');

    // Recent 7 days card title
    await expect(page.getByText(/最近 7 天/)).toBeVisible();
  });
});

test.describe('Health Log — Auth Guard', () => {
  test('should redirect to login when not authenticated', async ({ page }) => {
    await page.goto('/health-log');
    await page.waitForURL(/\/login/);
  });

  test('should deny access after logout', async ({ page }) => {
    await register(page, `hlog_${Date.now()}`);
    await logout(page);
    await page.goto('/health-log');
    await page.waitForURL(/\/login/);
  });
});
