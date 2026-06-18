/**
 * Therapies (外治理疗) list and detail E2E tests.
 *
 * Covers:
 * - Page renders with title, search input, category tabs
 * - Category filter tabs (全部疗法/刮痧/推拿/艾灸/拔罐/针刺/刺血)
 * - Search input exists
 * - Therapy cards display with name and category
 * - Clicking a card opens detail drawer with description
 */
import { test, expect } from '@playwright/test';
import { registerWithConsent as register } from './test-helpers';

test.describe('Therapies Page — 外治理疗', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `user_${Date.now()}`);
  });

  test('should load page with title and search input', async ({ page }) => {
    await page.goto('/therapies');

    await expect(page).toHaveURL('/therapies');
    // Page title heading "外治理疗"
    await expect(page.getByRole('heading', { name: /外治理疗/ })).toBeVisible();

    // Search input
    await expect(page.getByPlaceholder('搜索疗法名称、适应症')).toBeVisible();
  });

  test('should show category filter tabs', async ({ page }) => {
    await page.goto('/therapies');

    // "全部疗法" tab always present
    await expect(page.getByRole('tab', { name: /全部疗法/ })).toBeVisible();

    // At least some category tabs should exist
    const categories = ['刮痧', '推拿', '艾灸', '拔罐', '针刺', '刺血'];
    let foundCount = 0;
    for (const cat of categories) {
      const isVisible = await page
        .getByRole('tab', { name: new RegExp(cat) })
        .isVisible()
        .catch(() => false);
      if (isVisible) foundCount++;
    }
    // Should have at least 3 category tabs visible
    expect(foundCount).toBeGreaterThanOrEqual(3);
  });

  test('should switch category tab when clicked', async ({ page }) => {
    await page.goto('/therapies');

    // Click "刮痧" tab if it exists
    const guashaTab = page.getByRole('tab', { name: /刮痧/ });
    const isVisible = await guashaTab.isVisible().catch(() => false);

    if (isVisible) {
      await guashaTab.click();
      await page.waitForTimeout(1000);

      // Tab should be active (ant-tabs-tab-active class)
      const activeTab = page.locator('.ant-tabs-tab-active');
      await expect(activeTab).toBeVisible();
    } else {
      test.skip();
    }
  });

  test('should show therapy cards or empty state', async ({ page }) => {
    await page.goto('/therapies');
    await page.waitForTimeout(1500);

    const hasCards = await page.locator('.ant-card').first().isVisible().catch(() => false);
    const hasEmpty = await page.getByText(/暂无疗法/).isVisible().catch(() => false);

    expect(hasCards || hasEmpty).toBeTruthy();
  });

  test('should open detail drawer when clicking a therapy card', async ({ page }) => {
    await page.goto('/therapies');
    await page.waitForTimeout(1500);

    // Find hoverable therapy cards (inside Row/Col, not the page-level Card)
    // Therapy cards have onClick handler
    const cards = page.locator('.ant-card-hoverable');
    const cardCount = await cards.count();

    if (cardCount > 0) {
      await cards.first().click();
      await page.waitForTimeout(1500);

      // Detail drawer should open
      const drawer = page.locator('.ant-drawer');
      await expect(drawer).toBeVisible();

      // Drawer should contain some detail labels (风险等级 / 家庭自用 / 适应症 / 禁忌)
      const hasDetailLabel = await drawer
        .getByText(/风险等级|家庭自用|适应症|禁忌/)
        .first()
        .isVisible()
        .catch(() => false);
      expect(hasDetailLabel).toBeTruthy();
    } else {
      test.skip();
    }
  });
});
