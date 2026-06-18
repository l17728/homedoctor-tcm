/**
 * Triage (急症分诊) E2E tests.
 *
 * Covers:
 * - Page loads with title and warning alert
 * - Age input card with InputNumber and unit radio
 * - Questionnaire + red flags appear after entering age
 * - Assess / reset buttons become visible
 * - Basic interaction: enter age then assess
 * - Auth guard
 */
import { test, expect } from '@playwright/test';
import { register, logout, chineseText } from './helpers';

test.describe('Triage — Navigation & Layout', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `triage_${Date.now()}`);
  });

  test('should load triage page with title and warning alert', async ({
    page,
  }) => {
    await page.goto('/triage');
    await expect(page).toHaveURL('/triage');

    // Page title
    await expect(page.getByRole('heading', { name: /急症分诊/ })).toBeVisible();

    // Warning alert about not replacing professional diagnosis
    await expect(page.getByText(/不能替代专业医疗诊断/)).toBeVisible();
  });

  test('should show age input card with number input and unit radio', async ({
    page,
  }) => {
    await page.goto('/triage');

    // Step 1 card title
    await expect(page.getByText('第1步：输入孩子年龄')).toBeVisible();

    // InputNumber with placeholder
    await expect(page.getByPlaceholder('请输入')).toBeVisible();

    // Unit radio buttons (月龄 / 岁) — AntD Radio.Button input is visually hidden,
    // so we match the visible label text instead
    await expect(page.getByText('月龄', { exact: true })).toBeVisible();
    await expect(page.getByText('岁', { exact: true })).toBeVisible();
  });
});

test.describe('Triage — Questionnaire Flow', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `triage_${Date.now()}`);
  });

  test('should show red flag checklist and assess button after entering age', async ({
    page,
  }) => {
    await page.goto('/triage');

    // Enter age (12 months = 1 year old, valid age group)
    await page.getByPlaceholder('请输入').fill('12');
    // Wait for questionnaire fetch to complete
    await page.waitForTimeout(1000);

    // Red flag checklist card should appear
    const redFlagCard = page.getByText('红旗症状自查');
    await expect(redFlagCard.first()).toBeVisible();

    // Assess button becomes visible (开始评估)
    await expect(
      page.getByRole('button', { name: /开始评估/ }),
    ).toBeVisible();

    // Reset button also visible (重置, 2-char Chinese)
    await expect(
      page.getByRole('button', { name: chineseText('重置') }),
    ).toBeVisible();
  });

  test('should run assessment and show result card', async ({ page }) => {
    await page.goto('/triage');

    await page.getByPlaceholder('请输入').fill('24');
    await page.waitForTimeout(1000);

    // Click assess
    await page.getByRole('button', { name: /开始评估/ }).click();

    // Result card appears (id=triage-result) — it shows 分诊结果
    const resultCard = page.locator('#triage-result');
    await expect(resultCard).toBeVisible({ timeout: 15000 });

    // Result should contain a level label and disclaimer
    await expect(page.getByText(/分诊结果/).first()).toBeVisible();
  });
});

test.describe('Triage — Reset', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `triage_${Date.now()}`);
  });

  test('should reset the form when clicking reset button', async ({ page }) => {
    await page.goto('/triage');

    await page.getByPlaceholder('请输入').fill('36');
    await page.waitForTimeout(1000);

    // Confirm assess button is visible before reset
    await expect(
      page.getByRole('button', { name: /开始评估/ }),
    ).toBeVisible();

    // Click reset
    await page.getByRole('button', { name: chineseText('重置') }).click();

    // After reset, assess button should no longer be visible (no age)
    await expect(
      page.getByRole('button', { name: /开始评估/ }),
    ).not.toBeVisible();
  });
});

test.describe('Triage — Auth Guard', () => {
  test('should redirect to login when not authenticated', async ({ page }) => {
    await page.goto('/triage');
    await page.waitForURL(/\/login/);
    await expect(page.getByText(chineseText('登录')).first()).toBeVisible();
  });

  test('should deny access after logout', async ({ page }) => {
    await register(page, `triage_${Date.now()}`);
    await logout(page);
    await page.goto('/triage');
    await page.waitForURL(/\/login/);
  });
});
