/**
 * Medication Plans (用药套餐) E2E tests.
 *
 * Covers:
 * - Page loads with title
 * - "新建套餐" button visible
 * - Empty state shows when no plans
 * - Create modal opens with form fields
 * - Form validation for required fields
 * - Auth guard
 */
import { test, expect } from '@playwright/test';
import { register, logout, chineseText } from './helpers';

test.describe('Medication Plans — Navigation & Layout', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `plan_${Date.now()}`);
  });

  test('should load page with title and create button', async ({ page }) => {
    await page.goto('/medication-plans');
    await expect(page).toHaveURL('/medication-plans');

    // Page title
    await expect(page.getByRole('heading', { name: /用药套餐/ })).toBeVisible();

    // Create plan button
    await expect(
      page.getByRole('button', { name: /新建套餐/ }),
    ).toBeVisible();
  });
});

test.describe('Medication Plans — Empty State', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `plan_${Date.now()}`);
  });

  test('should show empty state when no plans exist', async ({ page }) => {
    await page.goto('/medication-plans');

    // For a new user, no plans exist
    await expect(page.getByText(/暂无用药套餐/)).toBeVisible();
  });
});

test.describe('Medication Plans — Create Modal', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `plan_${Date.now()}`);
  });

  test('should open create modal with form fields', async ({ page }) => {
    await page.goto('/medication-plans');

    await page.getByRole('button', { name: /新建套餐/ }).click();

    // Modal opens
    const modal = page.locator('.ant-modal').last();
    await expect(modal).toBeVisible();

    // Modal title
    await expect(page.getByText('新建用药套餐').first()).toBeVisible();

    // Plan name input
    await expect(page.getByLabel('套餐名称')).toBeVisible();

    // 用药明细 section
    await expect(page.getByText('用药明细')).toBeVisible();

    // 药品名称 input within the form list
    await expect(
      page.locator('.ant-modal').last().getByLabel('药品名称').first(),
    ).toBeVisible();
  });

  test('should show validation error when creating without name', async ({
    page,
  }) => {
    await page.goto('/medication-plans');

    await page.getByRole('button', { name: /新建套餐/ }).click();

    // Click create (创建, 2-char Chinese → may have auto-space) without filling name
    await page.getByRole('button', { name: chineseText('创建') }).click();

    // Validation error for plan name
    await expect(page.getByText(/请输入套餐名称/).first()).toBeVisible();
  });
});

test.describe('Medication Plans — Auth Guard', () => {
  test('should redirect to login when not authenticated', async ({ page }) => {
    await page.goto('/medication-plans');
    await page.waitForURL(/\/login/);
  });

  test('should deny access after logout', async ({ page }) => {
    await register(page, `plan_${Date.now()}`);
    await logout(page);
    await page.goto('/medication-plans');
    await page.waitForURL(/\/login/);
  });
});
