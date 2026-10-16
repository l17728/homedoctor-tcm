/**
 * Medication Schedule (服药计划) E2E tests.
 *
 * Covers:
 * - Page loads with title and control buttons
 * - "生成计划" button visible (disabled when no meds selected)
 * - Empty state message when no medicines in cabinet
 * - Add custom medicine drawer opens
 * - Template select placeholder visible
 * - Auth guard
 */
import { test, expect } from '@playwright/test';
import { register, logout } from './helpers';

test.describe('Medication Schedule — Navigation & Layout', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `sched_${Date.now()}`);
  });

  test('should load page with title and action buttons', async ({ page }) => {
    await page.goto('/medication-schedule');
    await expect(page).toHaveURL('/medication-schedule');

    // Page title
    await expect(page.getByRole('heading', { name: /我的服药计划/ })).toBeVisible();

    // With no selected medicine, only the step button is available; the
    // final generation action appears after medication selection.
    await expect(
      page.getByRole('button', { name: /下一步.*设置频率/ }),
    ).toBeVisible();

    // Load last plan button
    await expect(
      page.getByRole('button', { name: /加载上次计划/ }),
    ).toBeVisible();
  });

  test('should show template select placeholder', async ({ page }) => {
    await page.goto('/medication-schedule');

    // AntD Select renders placeholder as text, not as a native placeholder attribute
    await expect(page.getByText('选择常用模板')).toBeVisible();
  });

  test('should show medicine selection section', async ({ page }) => {
    await page.goto('/medication-schedule');

    // Section label
    await expect(page.getByText('从药箱选择药物')).toBeVisible();

    // Add custom medicine button
    await expect(
      page.getByRole('button', { name: /添加自定义药物/ }),
    ).toBeVisible();
  });
});

test.describe('Medication Schedule — Empty State', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `sched_${Date.now()}`);
  });

  test('should show empty state message when no medicines selected', async ({
    page,
  }) => {
    await page.goto('/medication-schedule');

    // Either cabinet empty message or schedule empty hint
    const emptyMsg = page.getByText(/药箱为空|请在上方选择药物后|生成计划/);
    await expect(emptyMsg.first()).toBeVisible();
  });

  test('should disable generate button when no medicines selected', async ({
    page,
  }) => {
    await page.goto('/medication-schedule');

    const nextStepBtn = page.getByRole('button', { name: /下一步.*设置频率/ });
    await expect(nextStepBtn).toBeDisabled();
  });
});

test.describe('Medication Schedule — Custom Medicine Drawer', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `sched_${Date.now()}`);
  });

  test('should open drawer for adding custom medicine', async ({ page }) => {
    await page.goto('/medication-schedule');

    await page.getByRole('button', { name: /添加自定义药物/ }).click();

    // Drawer appears
    const drawer = page.locator('.ant-drawer');
    await expect(drawer).toBeVisible();

    // Drawer title
    await expect(page.getByText('添加自定义药物').first()).toBeVisible();

    // Drug name input field
    await expect(page.getByLabel('药物名称')).toBeVisible();
  });
});

test.describe('Medication Schedule — Auth Guard', () => {
  test('should redirect to login when not authenticated', async ({ page }) => {
    await page.goto('/medication-schedule');
    await page.waitForURL(/\/login/);
  });

  test('should deny access after logout', async ({ page }) => {
    await register(page, `sched_${Date.now()}`);
    await logout(page);
    await page.goto('/medication-schedule');
    await page.waitForURL(/\/login/);
  });
});
