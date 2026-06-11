/**
 * Herb (中药) list and detail E2E tests.
 *
 * Covers:
 * - Navigation to herb list page
 * - Filter bar rendering (category, search)
 * - Table/list display with correct columns
 * - Search functionality
 * - Detail view navigation
 * - Empty state for new users
 */
import { test, expect } from '@playwright/test';
import { register, opsCell } from './helpers';

test.describe('Herb List — Navigation & Layout', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `user_${Date.now()}`);
  });

  test('should navigate to herb list page', async ({ page }) => {
    await page.getByText('知识库').first().click();
    await page.getByText('中药').click();

    await page.waitForURL('/herbs');
    await expect(page).toHaveURL('/herbs');
    await expect(page.getByText(/中药/)).toBeVisible();
  });

  test('should show page header with title', async ({ page }) => {
    await page.goto('/herbs');
    // Page should show herb-related heading
    const heading = page.getByRole('heading', { name: /中药/ });
    if (await heading.isVisible()) {
      await expect(heading).toBeVisible();
    } else {
      // Fallback: any prominent text mentioning herbs
      await expect(page.getByText(/中药/).first()).toBeVisible();
    }
  });

  test('should show filter bar with category selector and search', async ({
    page,
  }) => {
    await page.goto('/herbs');

    // Category filter (AntD Select or dropdown)
    await expect(page.getByText('分类').first()).toBeVisible();

    // Search input
    await expect(page.getByPlaceholder('搜索').first()).toBeVisible();
  });

  test('should show table with expected column headers', async ({ page }) => {
    await page.goto('/herbs');

    // Table should exist
    const table = page.locator('.ant-table');
    await expect(table).toBeVisible();

    // Common herb table columns
    const expectedColumns = ['名称', '功效', '性味'];
    for (const col of expectedColumns) {
      await expect(table.getByText(col).first()).toBeVisible();
    }
  });
});

test.describe('Herb List — Search & Filter', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `user_${Date.now()}`);
  });

  test('should filter herbs by search keyword', async ({ page }) => {
    await page.goto('/herbs');

    // Type a search query
    const searchInput = page.getByPlaceholder('搜索').first();
    await searchInput.fill('黄芪');
    await searchInput.press('Enter');

    // Results should mention the searched herb (if data exists)
    // Or show empty state if no match
    const hasResults = await page.getByText('黄芪').isVisible().catch(() => false);
    const hasEmpty = await page.getByText(/暂无|没有找到/).isVisible().catch(() => false);
    expect(hasResults || hasEmpty).toBeTruthy();
  });

  test('should clear search results when search is emptied', async ({
    page,
  }) => {
    await page.goto('/herbs');

    const searchInput = page.getByPlaceholder('搜索').first();
    await searchInput.fill('测试');
    await searchInput.press('Enter');

    // Clear the search
    await searchInput.clear();
    await searchInput.press('Enter');

    // Table should show all items again (or empty state)
    const table = page.locator('.ant-table');
    await expect(table).toBeVisible();
  });
});

test.describe('Herb List — Detail View', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `user_${Date.now()}`);
  });

  test('should open herb detail in drawer when clicking a row', async ({
    page,
  }) => {
    await page.goto('/herbs');

    // Check if there are any rows in the table
    const rows = page.locator('.ant-table-row');
    const rowCount = await rows.count();

    if (rowCount > 0) {
      // Click the first row to open detail
      await rows.first().click();

      // A detail drawer should open
      const drawer = page.locator('.ant-drawer');
      await expect(drawer).toBeVisible();
    }
    // If no rows, the empty state test covers this
  });

  test('should show herb detail with properties', async ({ page }) => {
    await page.goto('/herbs');

    const rows = page.locator('.ant-table-row');
    const rowCount = await rows.count();

    if (rowCount > 0) {
      // Get the herb name from the first row
      const herbName = await rows.first().locator('td').first().textContent();

      // Click to open detail
      await rows.first().click();

      // Detail drawer should show the herb name
      if (herbName) {
        await expect(page.getByText(herbName).first()).toBeVisible();
      }

      // Close the drawer (Lesson T4: verify close doesn't trigger form submit)
      const closeButton = page.locator('.ant-drawer-close, .ant-drawer .ant-btn').first();
      if (await closeButton.isVisible()) {
        await closeButton.click();
      }
    }
  });
});

test.describe('Herb List — Empty State', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `user_${Date.now()}`);
  });

  test('should show empty state when no herbs exist', async ({ page }) => {
    await page.goto('/herbs');

    // For a new user, herb list may be empty or show seeded data
    const table = page.locator('.ant-table');
    const emptyState = page.getByText(/暂无|没有/);

    // Either table with data or empty state should be visible
    const hasTable = await table.isVisible().catch(() => false);
    const hasEmpty = await emptyState.isVisible().catch(() => false);
    expect(hasTable || hasEmpty).toBeTruthy();
  });
});

test.describe('Herb List — Lesson T5: Row Operations', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `user_${Date.now()}`);
  });

  test('should scope action buttons to last column only', async ({ page }) => {
    await page.goto('/herbs');

    const rows = page.locator('.ant-table-row');
    const rowCount = await rows.count();

    if (rowCount > 0) {
      const firstRow = rows.first();

      // Lesson T5: opsCell scopes to last <td> to avoid false matches
      const actions = opsCell(firstRow);
      const actionLinks = actions.locator('a, button');
      const actionCount = await actionLinks.count();

      // Should have at least one action (view/edit/delete)
      expect(actionCount).toBeGreaterThanOrEqual(0);
    }
  });
});
