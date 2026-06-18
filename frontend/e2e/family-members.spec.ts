/**
 * Family Members Page (家庭成员) E2E tests.
 *
 * Covers:
 * - Page loads with member list
 * - "添加成员" button visible
 * - Empty state when no members
 * - Add member drawer with form + validation
 * - Auth guard
 */
import { test, expect } from '@playwright/test';
import { registerViaApi, setAuthState } from './api-auth';
import { logout, chineseText } from './helpers';

let token: string;
let user: string;

test.beforeAll(async () => {
  const auth = await registerViaApi('fam');
  token = auth.token;
  user = auth.user;
});

test.describe('Family Members — Layout & Elements', () => {
  test.beforeEach(async ({ page }) => {
    await setAuthState(page, token, user);
  });

  test('should load family members page with title', async ({ page }) => {
    await page.goto('/family');
    await expect(page).toHaveURL('/family');
    await expect(page.getByRole('heading', { name: '家庭成员' })).toBeVisible();
  });

  test('should show add member button', async ({ page }) => {
    await page.goto('/family');
    await expect(
      page.getByRole('button', { name: /添加成员/ }),
    ).toBeVisible();
  });

  test('should show empty state when no members', async ({ page }) => {
    await page.goto('/family');
    await expect(page.getByText(/暂无成员.*点击添加/)).toBeVisible();
  });
});

test.describe('Family Members — Create Flow', () => {
  test.beforeEach(async ({ page }) => {
    await setAuthState(page, token, user);
  });

  test('should open drawer on add click', async ({ page }) => {
    await page.goto('/family');
    await page.getByRole('button', { name: /添加成员/ }).click();

    const drawer = page.locator('.ant-drawer');
    await expect(drawer).toBeVisible();
    await expect(page.getByPlaceholder('请输入姓名')).toBeVisible();
  });

  test('should show validation error for empty name', async ({ page }) => {
    await page.goto('/family');
    await page.getByRole('button', { name: /添加成员/ }).click();

    const drawer = page.locator('.ant-drawer');
    await drawer.getByRole('button', { name: chineseText('提交') }).click();

    await expect(page.getByText(/请输入姓名/).first()).toBeVisible();
  });
});

test.describe('Family Members — Auth Guard', () => {
  test('should redirect to login when not authenticated', async ({ page }) => {
    await page.goto('/family');
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
    await page.goto('/family');
    await page.waitForURL(/\/login/);
  });
});
