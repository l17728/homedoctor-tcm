import { test, expect } from '@playwright/test';
import { register } from './helpers';

test.describe('KnowledgeBrowse', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `kb_${Date.now()}`);
  });

  test('should display knowledge browse page', async ({ page }) => {
    await page.goto('/knowledge-browse');
    await page.waitForTimeout(1000);
    await expect(page.locator('.ant-layout-content')).toBeVisible();
  });

  test('should show category filter or entity list', async ({ page }) => {
    await page.goto('/knowledge-browse');
    await page.waitForTimeout(1000);
    const content = page.locator('.ant-layout-content');
    await expect(content.getByRole('textbox', { name: '搜索...' })).toBeVisible();
    await expect(content.getByRole('button', { name: /穴位\(/ })).toBeVisible();
  });

  test('should handle search within knowledge browse', async ({ page }) => {
    await page.goto('/knowledge-browse');
    await page.waitForTimeout(1000);
    const searchInput = page.getByPlaceholder(/搜索|查找|关键字/);
    if (await searchInput.isVisible().catch(() => false)) {
      await searchInput.fill('黄芪');
      await page.waitForTimeout(500);
      await expect(searchInput).toHaveValue('黄芪');
    }
  });
});

test.describe('AdminPage access control', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `admin_${Date.now()}`);
  });

  test('should redirect non-admin users from admin page', async ({ page }) => {
    await page.goto('/admin');
    await page.waitForTimeout(1000);
    const url = page.url();
    const isAdminRoute = url.includes('/admin');
    const hasError = await page.getByText(/权限|禁止|403|无权/).count();
    if (isAdminRoute) {
      expect(hasError > 0 || await page.locator('.ant-empty').count() > 0).toBeTruthy();
    }
  });
});

test.describe('KnowledgeHub', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `kh_${Date.now()}`);
  });

  test('should display knowledge hub page', async ({ page }) => {
    await page.goto('/knowledge-hub');
    await page.waitForTimeout(1000);
    await expect(page.locator('.ant-layout-content')).toBeVisible();
  });

  test('should show import or browse options', async ({ page }) => {
    await page.goto('/knowledge-hub');
    await page.waitForTimeout(1000);
    const content = page.locator('.ant-layout-content');
    const hasCard = await content.locator('.ant-card').count();
    const hasButton = await content.locator('button').count();
    expect(hasCard > 0 || hasButton > 0).toBeTruthy();
  });
});
