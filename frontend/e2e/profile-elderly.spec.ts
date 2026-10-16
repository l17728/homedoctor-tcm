/**
 * Profile (健康档案) & Elderly Mode E2E tests.
 *
 * Covers:
 * - Profile page: load, edit, save
 * - Constitution info display in profile
 * - Allergies and health conditions tag input
 * - Elderly mode: toggle in settings, layout switch, 3-tab nav
 * - Auth guard
 */
import { test, expect } from '@playwright/test';
import { register, logout, chineseText } from './helpers';

// ---------------------------------------------------------------------------
// Profile Page Tests
// ---------------------------------------------------------------------------

test.describe('Profile — Navigation & Layout', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `prof_${Date.now()}`);
  });

  test('should navigate to profile page', async ({ page }) => {
    await page.goto('/profile');
    await expect(page.getByRole('heading', { name: '健康档案' })).toBeVisible();
  });

  test('should show basic info card', async ({ page }) => {
    await page.goto('/profile');
    await expect(page.getByText('基本信息')).toBeVisible();
  });

  test('should show health info card', async ({ page }) => {
    await page.goto('/profile');
    await expect(page.getByText('健康信息')).toBeVisible();
  });

  test('should show save button', async ({ page }) => {
    await page.goto('/profile');
    await expect(page.getByRole('button', { name: /保存档案/ })).toBeVisible();
  });
});

test.describe('Profile — Edit & Save', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `prof_${Date.now()}`);
  });

  test('should fill in display name and save', async ({ page }) => {
    await page.goto('/profile');

    await page.getByLabel('昵称').fill('王阿姨');
    await page.getByRole('button', { name: /保存档案/ }).click();

    // Toast success
    await expect(page.locator('.ant-message').first()).toBeVisible();
  });

  test('should select gender', async ({ page }) => {
    await page.goto('/profile');

    // Select female to reveal pregnancy toggle
    await page.getByLabel('女').click();
    await expect(page.getByText('是否孕期')).toBeVisible();
  });

  test('should add allergy tags', async ({ page }) => {
    await page.goto('/profile');

    const allergyInput = page.locator('.ant-form-item').filter({ hasText: '过敏史' }).locator('[role="combobox"]');
    await expect(allergyInput).toBeVisible();
    await allergyInput.click();
    await allergyInput.pressSequentially('海鲜');
    await allergyInput.press('Enter');
    await expect(page.locator('.ant-select-selection-item').filter({ hasText: '海鲜' })).toBeVisible();
  });
});

test.describe('Profile — Constitution Info', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `prof_${Date.now()}`);
  });

  test('should show "go test" link when no constitution', async ({ page }) => {
    await page.goto('/profile');
    await expect(page.getByRole('button', { name: /去测试|重新测试/ })).toBeVisible();
  });

  test('should navigate to constitution page from profile', async ({ page }) => {
    await page.goto('/profile');
    await page.getByRole('button', { name: /去测试|重新测试/ }).click();
    await page.waitForURL('/constitution');
  });
});

test.describe('Profile — Auth Guard', () => {
  test('should redirect to login when not authenticated', async ({ page }) => {
    await page.goto('/profile');
    await page.waitForURL(/\/login/);
  });

  test('should deny access after logout', async ({ page }) => {
    await register(page, `prof_${Date.now()}`);
    await logout(page);
    await page.goto('/profile');
    await page.waitForURL(/\/login/);
  });
});

// ---------------------------------------------------------------------------
// Elderly Mode Tests
// ---------------------------------------------------------------------------

test.describe('Elderly Mode — Toggle', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `eld_${Date.now()}`);
  });

  test('should show elderly mode switch in settings', async ({ page }) => {
    await page.goto('/settings');
    await expect(page.getByText('长辈模式')).toBeVisible();
  });

  test('should show confirmation modal when enabling', async ({ page }) => {
    await page.goto('/settings');

    // Find and toggle the elderly mode switch
    const elderlySwitch = page.locator('.ant-form-item').filter({ hasText: '长辈模式' }).locator('.ant-switch');
    await elderlySwitch.click();

    // Confirmation modal should appear
    await expect(page.locator('.ant-modal-confirm, .ant-modal')).toBeVisible();
    await expect(page.locator('.ant-modal-confirm .ant-btn-primary').last()).toBeVisible();
  });

  test('should cancel elderly mode toggle', async ({ page }) => {
    await page.goto('/settings');

    const elderlySwitch = page.locator('.ant-form-item').filter({ hasText: '长辈模式' }).locator('.ant-switch');
    await elderlySwitch.click();

    // Cancel the confirmation
    await page.getByRole('button', { name: chineseText('取消') }).click();

    // Switch should remain off
    await expect(elderlySwitch).not.toHaveClass(/ant-switch-checked/);
  });

  test('should switch to elderly layout when confirmed', async ({ page }) => {
    await page.goto('/settings');

    const elderlySwitch = page.locator('.ant-form-item').filter({ hasText: '长辈模式' }).locator('.ant-switch');
    await elderlySwitch.click();

    // Confirm
    await page.getByRole('button', { name: /确定切换/ }).click();

    // Sidebar should disappear, bottom nav should appear
    await expect(page.locator('.ant-layout-sider')).not.toBeVisible();
    // Bottom nav has 3 tabs
    await expect(page.getByText('首页').last()).toBeVisible();
    await expect(page.getByText('问答').last()).toBeVisible();
    await expect(page.getByText('我的').last()).toBeVisible();
  });

  test('should add elderly-mode class to body when enabled', async ({ page }) => {
    await page.goto('/settings');

    const elderlySwitch = page.locator('.ant-form-item').filter({ hasText: '长辈模式' }).locator('.ant-switch');
    await elderlySwitch.click();
    await page.getByRole('button', { name: /确定切换/ }).click();

    await expect(page.locator('body')).toHaveClass(/elderly-mode/);
  });
});

test.describe('Elderly Mode — Navigation', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `eld_${Date.now()}`);
    // Enable elderly mode first
    await page.goto('/settings');
    const elderlySwitch = page.locator('.ant-form-item').filter({ hasText: '长辈模式' }).locator('.ant-switch');
    await elderlySwitch.click();
    await page.getByRole('button', { name: /确定切换/ }).click();
  });

  test('should navigate via bottom tabs', async ({ page }) => {
    // Click AI问答 tab
    await page.getByText('问答').last().click();
    await page.waitForURL('/chat');
    await expect(page).toHaveURL('/chat');
  });

  test('should navigate to profile via 我的 tab', async ({ page }) => {
    await page.getByText('我的').last().click();
    await page.waitForURL('/profile');
    await expect(page).toHaveURL('/profile');
  });

  test('should navigate to dashboard via 首页 tab', async ({ page }) => {
    // Go to chat first
    await page.goto('/chat');
    // Click 首页
    await page.getByText('首页').last().click();
    await page.waitForURL('/');
  });
});

test.describe('Elderly Mode — Disable', () => {
  test('should revert to normal layout when disabled', async ({ page }) => {
    await register(page, `eld_${Date.now()}`);

    // Enable elderly mode
    await page.goto('/settings');
    let elderlySwitch = page.locator('.ant-form-item').filter({ hasText: '长辈模式' }).locator('.ant-switch');
    await elderlySwitch.click();
    await page.getByRole('button', { name: /确定切换/ }).click();

    // Verify elderly mode is active
    await expect(page.locator('body')).toHaveClass(/elderly-mode/);

    // Now disable it
    await page.goto('/settings');
    elderlySwitch = page.locator('.ant-form-item').filter({ hasText: '长辈模式' }).locator('.ant-switch');
    await elderlySwitch.click();

    // Should revert
    await expect(page.locator('body')).not.toHaveClass(/elderly-mode/);
    await expect(page.locator('.ant-layout-sider')).toBeVisible();
  });
});
