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
import { register, chineseText } from './helpers';

test.describe('Settings Page — Layout & Display', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `set_${Date.now()}`);
    await page.goto('/settings');
  });

  test('should load settings page with display settings section', async ({
    page,
  }) => {
    await expect(page).toHaveURL('/settings');
    await expect(page.getByRole('heading', { name: '设置' })).toBeVisible();

    // Display settings card
    await expect(page.getByText('显示设置', { exact: true }).first()).toBeVisible();

    // Two switches: dark mode + elderly mode
    const switches = page.locator('.ant-card').first().locator('.ant-switch');
    await expect(switches.first()).toBeVisible();
  });

  test('should show and toggle dark mode switch', async ({ page }) => {
    // Locate dark mode switch — first switch in 显示设置 card
    const displayCard = page.locator('.ant-card').filter({ hasText: '显示设置' });
    const darkSwitch = displayCard.locator('.ant-switch').first();

    await expect(darkSwitch).toBeVisible();

    // Record initial state, then toggle
    const wasChecked = await darkSwitch.evaluate((el) =>
      el.classList.contains('ant-switch-checked'),
    );
    await darkSwitch.click();

    // State should flip
    if (wasChecked) {
      await expect(darkSwitch).not.toHaveClass(/ant-switch-checked/);
    } else {
      await expect(darkSwitch).toHaveClass(/ant-switch-checked/);
    }
  });

  test('should show confirmation modal when toggling elderly mode', async ({
    page,
  }) => {
    const displayCard = page.locator('.ant-card').filter({ hasText: '显示设置' });
    // Elderly mode switch is the second switch in the card
    const elderlySwitch = displayCard.locator('.ant-switch').nth(1);

    await expect(elderlySwitch).toBeVisible();
    await elderlySwitch.click();

    // Confirmation modal should appear
    await expect(page.getByText('切换到长辈模式')).toBeVisible();

    // Cancel to avoid actually switching layout
    await page.getByRole('button', { name: chineseText('取消') }).click();
    await expect(page.getByText('切换到长辈模式')).not.toBeVisible();
  });
});

test.describe('Settings Page — Backup & Export', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `set_${Date.now()}`);
    await page.goto('/settings');
  });

  test('should show backup section with create button', async ({ page }) => {
    await expect(page.getByText('数据备份', { exact: true }).first()).toBeVisible();
    await expect(
      page.getByRole('button', { name: /创建备份/ }),
    ).toBeVisible();
  });

  test('should show export section with export button', async ({ page }) => {
    await expect(page.getByText('数据导出', { exact: true }).first()).toBeVisible();
    await expect(
      page.getByRole('button', { name: /导出数据/ }),
    ).toBeVisible();
  });
});

test.describe('Settings Page — Account & Version', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `set_${Date.now()}`);
    await page.goto('/settings');
  });

  test('should show account management section with action buttons', async ({
    page,
  }) => {
    await expect(
      page.getByText('账户管理', { exact: true }).first(),
    ).toBeVisible();

    // Warning alert about irreversible operations
    await expect(page.getByText(/不可撤销/)).toBeVisible();

    // Account action buttons
    await expect(
      page.getByRole('button', { name: /查看数据概况/ }),
    ).toBeVisible();
    await expect(
      page.getByRole('button', { name: /删除账户/ }),
    ).toBeVisible();
  });

  test('should display version number 0.4.0 in about section', async ({
    page,
  }) => {
    await expect(page.getByText('关于', { exact: true }).first()).toBeVisible();
    await expect(page.getByText(/0\.4\.0/)).toBeVisible();
  });
});
