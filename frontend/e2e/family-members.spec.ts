/**
 * Family Members Page (家庭成员) E2E tests.
 *
 * Covers:
 * - Page loads with member list
 * - "添加成员" button visible
 * - Empty state when no members
 * - Add member drawer with form + validation
 * - Create member flow + header member switcher appears
 * - Auth guard
 */
import { test, expect } from '@playwright/test';
import {
  register,
  logout,
  chineseText,
  selectAntdOption,
} from './helpers';

test.describe('Family Members — Layout & Elements', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `fam_${Date.now()}`);
    await page.goto('/family');
  });

  test('should load family members page with title', async ({ page }) => {
    await expect(page).toHaveURL('/family');
    await expect(
      page.getByRole('heading', { name: '家庭成员' }),
    ).toBeVisible();
  });

  test('should show add member button', async ({ page }) => {
    await expect(
      page.getByRole('button', { name: /添加成员/ }),
    ).toBeVisible();
  });

  test('should show empty state when no members', async ({ page }) => {
    await expect(page.getByText(/暂无成员.*点击添加/)).toBeVisible();
  });
});

test.describe('Family Members — Create Flow', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `fam_${Date.now()}`);
    await page.goto('/family');
  });

  test('should open drawer on add click', async ({ page }) => {
    await page.getByRole('button', { name: /添加成员/ }).click();

    const drawer = page.locator('.ant-drawer');
    await expect(drawer).toBeVisible();
    await expect(page.getByText('添加成员').first()).toBeVisible();

    // Form fields
    await expect(page.getByPlaceholder('请输入姓名')).toBeVisible();
    await expect(page.getByText('关系')).toBeVisible();
  });

  test('should show validation error for empty name', async ({ page }) => {
    await page.getByRole('button', { name: /添加成员/ }).click();

    // Submit without filling required fields
    const drawer = page.locator('.ant-drawer');
    await drawer.getByRole('button', { name: chineseText('提交') }).click();

    await expect(page.getByText(/请输入姓名/).first()).toBeVisible();
  });

  test('should create a member and show in table + header switcher', async ({
    page,
  }) => {
    await page.getByRole('button', { name: /添加成员/ }).click();

    const drawer = page.locator('.ant-drawer');

    // Fill name
    await drawer.getByPlaceholder('请输入姓名').fill('王大爷');

    // Select relation via AntD Select
    const relationSelect = drawer.locator('.ant-select').first();
    await selectAntdOption(page, relationSelect, '父亲');

    // Submit
    await drawer.getByRole('button', { name: chineseText('提交') }).click();

    // Drawer closes
    await expect(drawer).not.toBeVisible();

    // Member appears in table
    await expect(page.getByText('王大爷')).toBeVisible();

    // Header member switcher should now be visible (members.length > 0)
    await expect(page.locator('header').getByText(/全部成员|王大爷/)).toBeVisible();
  });
});

test.describe('Family Members — Auth Guard', () => {
  test('should redirect to login when not authenticated', async ({ page }) => {
    await page.goto('/family');
    await page.waitForURL(/\/login/);
  });

  test('should deny access after logout', async ({ page }) => {
    await register(page, `fam_${Date.now()}`);
    await logout(page);
    await page.goto('/family');
    await page.waitForURL(/\/login/);
  });
});
