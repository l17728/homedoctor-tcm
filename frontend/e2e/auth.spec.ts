/**
 * Auth flow E2E tests — register → login → me → logout lifecycle.
 *
 * Covers:
 * - Login page renders correctly
 * - New user registration and automatic login
 * - Logout and re-login flow
 * - Unauthenticated redirect to /login
 * - Invalid credential error handling
 */
import { test, expect } from '@playwright/test';
import { register, login, logout, chineseText } from './helpers';

test.describe('Auth Flow', () => {
  test('should show login page with form elements', async ({ page }) => {
    await page.goto('/login');

    // Page title / heading
    await expect(page.getByText(chineseText('登录'))).toBeVisible();

    // Form fields
    await expect(page.getByPlaceholder('用户名')).toBeVisible();
    await expect(page.getByPlaceholder('密码')).toBeVisible();

    // Submit button
    await expect(
      page.getByRole('button', { name: chineseText('登录') }),
    ).toBeVisible();

    // Register tab should be accessible
    await expect(page.getByText(chineseText('注册'))).toBeVisible();
  });

  test('should register a new user and redirect to dashboard', async ({
    page,
  }) => {
    const uniqueName = `user_${Date.now()}`;
    await register(page, uniqueName);

    // Should redirect to home/dashboard after successful registration
    await expect(page).toHaveURL('/');
    await expect(page.getByText('今日健康')).toBeVisible();
  });

  test('should login with existing user after registration', async ({
    page,
  }) => {
    // First register a user
    const uniqueName = `user_${Date.now()}`;
    await register(page, uniqueName);

    // Log out
    await page.getByRole('button', { name: /用户/ }).click();
    await page.getByText(chineseText('退出')).click();
    await page.waitForURL('/login');

    // Re-login with same credentials
    await login(page, uniqueName);
    await expect(page).toHaveURL('/');
    await expect(page.getByText('今日健康')).toBeVisible();
  });

  test('should redirect to login when accessing protected route unauthenticated', async ({
    page,
  }) => {
    await page.goto('/herbs');

    // Should be redirected to login page
    await page.waitForURL(/\/login/);
    await expect(page.getByText(chineseText('登录'))).toBeVisible();
  });

  test('should show error on invalid credentials', async ({ page }) => {
    await page.goto('/login');
    await page.getByPlaceholder('用户名').fill('nonexistent_user');
    await page.getByPlaceholder('密码').fill('wrong_password');
    await page.getByRole('button', { name: chineseText('登录') }).click();

    // Should show error message (toast or inline)
    // Accept either "用户名或密码错误" or a generic error toast
    const errorText = page.getByText(/用户名或密码错误|登录失败|错误/);
    await expect(errorText).toBeVisible();
  });

  test('should show validation error when submitting empty form', async ({
    page,
  }) => {
    await page.goto('/login');

    // Click login without filling any fields
    await page.getByRole('button', { name: chineseText('登录') }).click();

    // Ant Design form validation should show required field errors
    await expect(page.getByText(/请输入/)).toBeVisible();
  });

  test('should show validation error for mismatched passwords on register', async ({
    page,
  }) => {
    await page.goto('/login');
    await page.getByText(chineseText('注册')).click();

    await page.getByPlaceholder('用户名').fill('test_mismatch');
    await page.getByPlaceholder('密码').fill('password123');
    await page.getByPlaceholder('确认密码').fill('different456');

    await page.getByRole('button', { name: chineseText('注册') }).click();

    // Should show password mismatch error
    await expect(page.getByText(/密码.*不一致|两次密码/)).toBeVisible();
  });
});

test.describe('Auth — Session Persistence', () => {
  test('should persist session across page reload', async ({ page }) => {
    const uniqueName = `user_${Date.now()}`;
    await register(page, uniqueName);

    // Reload the page
    await page.reload();

    // Should still be on dashboard (not redirected to login)
    await expect(page).toHaveURL('/');
    await expect(page.getByText('今日健康')).toBeVisible();
  });

  test('should require login again after logout', async ({ page }) => {
    const uniqueName = `user_${Date.now()}`;
    await register(page, uniqueName);

    await logout(page);

    // Try accessing a protected page
    await page.goto('/herbs');
    await page.waitForURL(/\/login/);
    await expect(page.getByText(chineseText('登录'))).toBeVisible();
  });
});
