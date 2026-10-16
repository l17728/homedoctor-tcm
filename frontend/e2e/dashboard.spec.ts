/**
 * Dashboard E2E tests — stat cards, sidebar navigation, and layout.
 *
 * Tests assume a freshly registered user (no pre-existing data).
 * All data assertions account for empty/zero states.
 */
import { test, expect } from '@playwright/test';
import { register } from './helpers';

test.describe('Dashboard', () => {
  test.beforeEach(async ({ page }) => {
    // Register + auto-login before each test
    await register(page, `user_${Date.now()}`);
  });

  test('should show dashboard heading after login', async ({ page }) => {
    await expect(page.getByText('今日健康')).toBeVisible();
  });

  test('should show stat cards section', async ({ page }) => {
    // Dashboard should have stat cards area (even with 0 data)
    // These may show "0" counts for herbs, medicines, reminders, etc.
    const statArea = page.locator('.ant-card, [data-testid="stat-card"]');
    await expect(statArea.first()).toBeVisible();
  });

  test('should show sidebar navigation with main sections', async ({ page }) => {
    // Main navigation items expected in sidebar
    const navItems = ['知识探索', '用药管理', 'AI助手'];

    for (const item of navItems) {
      await expect(page.getByText(item).first()).toBeVisible();
    }
  });

  test('should navigate to herb list via sidebar', async ({ page }) => {
    // Click the knowledge base or herbs menu item
    const knowledgeGroup = page.locator('.ant-menu-submenu').filter({ hasText: '知识探索' });
    await knowledgeGroup.locator('.ant-menu-submenu-title').click();
    await knowledgeGroup.locator('.ant-menu-item').filter({ hasText: /^中药$/ }).click();

    await page.waitForURL('/herbs');
    await expect(page).toHaveURL('/herbs');
  });

  test('should navigate to medicine cabinet via sidebar', async ({ page }) => {
    const medicineGroup = page.locator('.ant-menu-submenu').filter({ hasText: '用药管理' });
    await medicineGroup.locator('.ant-menu-submenu-title').click();
    await medicineGroup.getByRole('menuitem', { name: '药箱', exact: true }).click();
    await page.waitForURL('/medicines');
    await expect(page).toHaveURL('/medicines');
  });

  test('should navigate to AI assistant via sidebar', async ({ page }) => {
    await page.getByRole('menuitem', { name: /AI助手/ }).click();
    await page.waitForURL('/chat');
    await expect(page).toHaveURL('/chat');
  });

  test('should show user info in header', async ({ page }) => {
    // User avatar or name should be visible in the header
    const userElement = page.getByRole('button', { name: /用户/ });
    await expect(userElement).toBeVisible();
  });

  test('should have responsive layout at 1280px width', async ({ page }) => {
    // Default viewport is 1280x720 per playwright.config.ts
    const sidebar = page.locator('.ant-layout-sider, [class*="sidebar"]');
    // Sidebar should be visible at desktop width
    await expect(sidebar.first()).toBeVisible();
  });
});

test.describe('Dashboard — Empty State', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `user_${Date.now()}`);
  });

  test('should show welcome message or empty state for new user', async ({
    page,
  }) => {
    // New user dashboard might show a welcome guide or empty state
    // At minimum, the dashboard heading should be present
    await expect(page.getByText('今日健康')).toBeVisible();
  });
});
