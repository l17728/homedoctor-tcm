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
import { registerViaApi, setAuthState } from './api-auth';
import { logout } from './helpers';

let token: string;
let user: string;

test.beforeAll(async () => {
  const auth = await registerViaApi('fm');
  token = auth.token;
  user = auth.user;
});

test.describe('Formulation — Layout & Elements', () => {
  test.beforeEach(async ({ page }) => {
    await setAuthState(page, token, user);
  });

  test('should load page with symptom input', async ({ page }) => {
    await page.goto('/formulation');
    await expect(page).toHaveURL('/formulation');
    await expect(page.getByRole('heading', { name: /智能配伍/ })).toBeVisible();
    await expect(page.getByPlaceholder('如：气虚乏力、失眠多梦')).toBeVisible();
    await expect(page.getByText('症状描述')).toBeVisible();
  });

  test('should show constitution selector', async ({ page }) => {
    await page.goto('/formulation');
    await expect(page.getByText('体质类型')).toBeVisible();
    await expect(page.getByText('选择体质（可选）')).toBeVisible();
  });

  test('should show recommend and tea recipe buttons', async ({ page }) => {
    await page.goto('/formulation');
    await expect(
      page.getByRole('button', { name: /推荐中药/ }),
    ).toBeVisible();
    await expect(
      page.getByRole('button', { name: /生成代茶饮配方/ }),
    ).toBeVisible();
  });
});

test.describe('Formulation — Interaction', () => {
  test.beforeEach(async ({ page }) => {
    await setAuthState(page, token, user);
  });

  test('should disable action buttons when no symptoms selected', async ({
    page,
  }) => {
    await page.goto('/formulation');
    const recommendBtn = page.getByRole('button', { name: /推荐中药/ });
    await expect(recommendBtn).toBeDisabled();
  });

  test('should enable action buttons after adding a symptom', async ({
    page,
  }) => {
    await page.goto('/formulation');
    await page.getByText('气虚乏力', { exact: true }).click();

    const recommendBtn = page.getByRole('button', { name: /推荐中药/ });
    await expect(recommendBtn).toBeEnabled();
  });
});

test.describe('Formulation — Auth Guard', () => {
  test('should redirect to login when not authenticated', async ({ page }) => {
    await page.goto('/formulation');
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
    await page.goto('/formulation');
    await page.waitForURL(/\/login/);
  });
});
