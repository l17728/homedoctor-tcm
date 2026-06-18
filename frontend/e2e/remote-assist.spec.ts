/**
 * Remote Assist Page (远程协助) E2E tests.
 *
 * Covers:
 * - Page loads
 * - Invite button visible
 * - Shared users section exists
 * - Alert settings section exists (via invite modal)
 * - Empty state when no shared users
 * - Auth guard
 */
import { test, expect } from '@playwright/test';
import { register, logout, chineseText } from './helpers';

test.describe('Remote Assist — Layout & Elements', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `ra_${Date.now()}`);
    await page.goto('/remote-assist');
  });

  test('should load remote assist page', async ({ page }) => {
    await expect(page).toHaveURL('/remote-assist');
    await expect(page.getByRole('heading', { name: /远程协助/ })).toBeVisible();
  });

  test('should show invite button in header', async ({ page }) => {
    await expect(
      page.getByRole('button', { name: /邀请家属/ }),
    ).toBeVisible();
  });

  test('should show shared users section with empty state', async ({ page }) => {
    await expect(page.getByText('我的家人')).toBeVisible();
    // Empty state for new user with no shared members
    await expect(
      page.getByText(/暂无共享家人/),
    ).toBeVisible();

    // Detail area prompt
    await expect(
      page.getByText(/从左侧选择家人查看健康摘要/),
    ).toBeVisible();
  });
});

test.describe('Remote Assist — Invite Modal', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `ra_${Date.now()}`);
    await page.goto('/remote-assist');
  });

  test('should open invite modal on button click', async ({ page }) => {
    await page.getByRole('button', { name: /邀请家属/ }).click();

    const modal = page.locator('.ant-modal').last();
    await expect(modal).toBeVisible();
    await expect(page.getByText('邀请家属').last()).toBeVisible();

    // Username input with placeholder
    await expect(page.getByPlaceholder('请输入对方用户名')).toBeVisible();

    // Submit button
    await expect(
      page.getByRole('button', { name: /发送邀请/ }),
    ).toBeVisible();

    // Cancel to close
    await page.getByRole('button', { name: chineseText('取消') }).click();
    await expect(modal).not.toBeVisible();
  });

  test('should show validation error when inviting without username', async ({
    page,
  }) => {
    await page.getByRole('button', { name: /邀请家属/ }).click();

    // Click submit without filling username
    await page.getByRole('button', { name: /发送邀请/ }).click();

    // AntD form validation error
    await expect(page.getByText(/请输入用户名/)).toBeVisible();
  });
});

test.describe('Remote Assist — Auth Guard', () => {
  test('should redirect to login when not authenticated', async ({ page }) => {
    await page.goto('/remote-assist');
    await page.waitForURL(/\/login/);
  });

  test('should deny access after logout', async ({ page }) => {
    await register(page, `ra_${Date.now()}`);
    await logout(page);
    await page.goto('/remote-assist');
    await page.waitForURL(/\/login/);
  });
});
