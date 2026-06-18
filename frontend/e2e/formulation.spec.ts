/**
 * Formulation Page (智能配伍) E2E tests.
 *
 * Covers:
 * - Page loads with symptom input
 * - Constitution selector exists
 * - "推荐中药" button visible (disabled without symptoms)
 * - "代茶饮" button visible
 * - Adding a symptom enables action buttons
 * - Auth guard
 */
import { test, expect } from '@playwright/test';
import { register, logout } from './helpers';

test.describe('Formulation — Layout & Elements', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `fm_${Date.now()}`);
    await page.goto('/formulation');
  });

  test('should load page with symptom input', async ({ page }) => {
    await expect(page).toHaveURL('/formulation');
    await expect(page.getByRole('heading', { name: /智能配伍/ })).toBeVisible();

    // Symptom input
    await expect(page.getByPlaceholder('如：气虚乏力、失眠多梦')).toBeVisible();
    await expect(page.getByText('症状描述')).toBeVisible();
  });

  test('should show constitution selector', async ({ page }) => {
    await expect(page.getByText('体质类型')).toBeVisible();
    await expect(page.getByText('选择体质（可选）')).toBeVisible();
  });

  test('should show recommend and tea recipe buttons', async ({ page }) => {
    await expect(
      page.getByRole('button', { name: /推荐中药/ }),
    ).toBeVisible();
    await expect(
      page.getByRole('button', { name: /生成代茶饮配方/ }),
    ).toBeVisible();
    await expect(
      page.getByRole('button', { name: /从药箱推荐/ }),
    ).toBeVisible();
  });
});

test.describe('Formulation — Interaction', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `fm_${Date.now()}`);
    await page.goto('/formulation');
  });

  test('should disable action buttons when no symptoms selected', async ({
    page,
  }) => {
    const recommendBtn = page.getByRole('button', { name: /推荐中药/ });
    await expect(recommendBtn).toBeDisabled();
  });

  test('should enable action buttons after adding a symptom', async ({
    page,
  }) => {
    // Click a common symptom quick tag
    await page.getByText('气虚乏力', { exact: true }).click();

    // Buttons should now be enabled
    const recommendBtn = page.getByRole('button', { name: /推荐中药/ });
    await expect(recommendBtn).toBeEnabled();

    // Verify the symptom tag appears in selected area
    await expect(
      page.locator('.ant-tag-color-purple').filter({ hasText: '气虚乏力' }),
    ).toBeVisible();
  });
});

test.describe('Formulation — Auth Guard', () => {
  test('should redirect to login when not authenticated', async ({ page }) => {
    await page.goto('/formulation');
    await page.waitForURL(/\/login/);
  });

  test('should deny access after logout', async ({ page }) => {
    await register(page, `fm_${Date.now()}`);
    await logout(page);
    await page.goto('/formulation');
    await page.waitForURL(/\/login/);
  });
});
