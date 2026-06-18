/**
 * Settings Page (设置) E2E tests.
 *
 * Covers:
 * - Page loads with display settings section
 * - Dark mode toggle visible and clickable
 * - Elderly mode toggle shows confirmation modal
 * - Backup + Export sections visible
 * - Account management section + version number visible
 */
import { test, expect } from '@playwright/test';
import { registerViaApi, setAuthState } from './api-auth';
import { logout, chineseText } from './helpers';

let token: string;
let user: string;

test.beforeAll(async () => {
  const auth = await registerViaApi('set');
  token = auth.token;
  user = auth.user;
});

test.describe('Settings — Layout & Display', () => {
  test.beforeEach(async ({ page }) => {
    await setAuthState(page, token, user);
  });

  test('should load settings page with display settings section', async ({
    page,
  }) => {
    await page.goto('/settings');
    await expect(page).toHaveURL('/settings');
    await expect(page.getByRole('heading', { name: '设置' })).toBeVisible();
    await expect(
      page.getByText('显示设置', { exact: true }).first(),
    ).toBeVisible();

    const switches = page.locator('.ant-switch');
    await expect(switches.first()).toBeVisible();
  });

  test('should show and toggle dark mode switch', async ({ page }) => {
    await page.goto('/settings');
    const displayCard = page.locator('.ant-card').filter({ hasText: '显示设置' });
    const darkSwitch = displayCard.locator('.ant-switch').first();

    await expect(darkSwitch).toBeVisible();

    const wasChecked = await darkSwitch.evaluate((el) =>
      el.classList.contains('ant-switch-checked'),
    );
    await darkSwitch.click();

    if (wasChecked) {
      await expect(darkSwitch).not.toHaveClass(/ant-switch-checked/);
    } else {
      await expect(darkSwitch).toHaveClass(/ant-switch-checked/);
    }
  });

  test('should show confirmation modal when toggling elderly mode', async ({
    page,
  }) => {
    await page.goto('/settings');
    const displayCard = page.locator('.ant-card').filter({ hasText: '显示设置' });
    const elderlySwitch = displayCard.locator('.ant-switch').nth(1);

    await expect(elderlySwitch).toBeVisible();
    await elderlySwitch.click();

    await expect(page.locator('.ant-modal-confirm')).toBeVisible();
    await page.getByRole('button', { name: chineseText('取消') }).click();
    await expect(page.locator('.ant-modal-confirm')).not.toBeVisible();
  });
});

test.describe('Settings — Backup & Export', () => {
  test.beforeEach(async ({ page }) => {
    await setAuthState(page, token, user);
  });

  test('should show backup and export sections with buttons', async ({
    page,
  }) => {
    await page.goto('/settings');

    await expect(
      page.getByText('数据备份', { exact: true }).first(),
    ).toBeVisible();
    await expect(page.getByRole('button', { name: /创建备份/ })).toBeVisible();

    await expect(
      page.getByText('数据导出', { exact: true }).first(),
    ).toBeVisible();
    await expect(page.getByRole('button', { name: /导出数据/ })).toBeVisible();
  });
});

test.describe('Settings — Account & Version', () => {
  test.beforeEach(async ({ page }) => {
    await setAuthState(page, token, user);
  });

  test('should show account management section and version 0.4.0', async ({
    page,
  }) => {
    await page.goto('/settings');

    await expect(
      page.getByText('账户管理', { exact: true }).first(),
    ).toBeVisible();
    await expect(page.getByText(/不可撤销/)).toBeVisible();
    await expect(
      page.getByRole('button', { name: /查看数据概况/ }),
    ).toBeVisible();
    await expect(
      page.getByRole('button', { name: /删除账户/ }),
    ).toBeVisible();

    await expect(page.getByText('关于', { exact: true }).first()).toBeVisible();
    await expect(page.getByText(/0\.4\.0/)).toBeVisible();
  });
});

test.describe('Settings — Auth Guard', () => {
  test('should redirect to login when not authenticated', async ({ page }) => {
    await page.goto('/settings');
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
    await page.goto('/settings');
    await page.waitForURL(/\/login/);
  });
});
