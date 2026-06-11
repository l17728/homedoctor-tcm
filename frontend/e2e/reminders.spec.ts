/**
 * Reminders (吃药提醒) E2E tests.
 *
 * Covers:
 * - Navigation to reminders page
 * - Create reminder via drawer form
 * - Today's reminders card display
 * - Enable/disable toggle
 * - Delete reminder
 * - Empty state
 * - Auth guard
 */
import { test, expect } from '@playwright/test';
import { register, logout, chineseText, opsCell } from './helpers';

test.describe('Reminders — Navigation & Layout', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `rem_${Date.now()}`);
  });

  test('should navigate to reminders page', async ({ page }) => {
    await page.getByText('提醒').first().click();
    await page.waitForURL('/reminders');
    await expect(page).toHaveURL('/reminders');
    await expect(page.getByText('吃药提醒')).toBeVisible();
  });

  test('should show add button', async ({ page }) => {
    await page.goto('/reminders');
    const addBtn = page.getByRole('button', { name: /添加提醒/ });
    await expect(addBtn).toBeVisible();
  });
});

test.describe('Reminders — Create', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `rem_${Date.now()}`);
  });

  test('should open drawer on add click', async ({ page }) => {
    await page.goto('/reminders');
    await page.getByRole('button', { name: /添加提醒/ }).click();
    const drawer = page.locator('.ant-drawer');
    await expect(drawer).toBeVisible();
    await expect(page.getByText(/添加提醒/)).toBeVisible();
  });

  test('should show validation error for empty title', async ({ page }) => {
    await page.goto('/reminders');
    await page.getByRole('button', { name: /添加提醒/ }).click();
    await page.getByRole('button', { name: chineseText('提交') }).click();
    await expect(page.getByText(/请输入提醒标题/).first()).toBeVisible();
  });

  test('should create a daily reminder', async ({ page }) => {
    await page.goto('/reminders');
    await page.getByRole('button', { name: /添加提醒/ }).click();

    // Fill title
    await page.getByLabel('提醒标题').fill('服用维生素C');

    // Submit
    await page.getByRole('button', { name: chineseText('提交') }).click();

    // Drawer closes
    await expect(page.locator('.ant-drawer')).not.toBeVisible();

    // Reminder appears in table
    await expect(page.getByText('服用维生素C')).toBeVisible();
  });
});

test.describe('Reminders — Today View', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `rem_${Date.now()}`);
  });

  test('should show today card when reminders exist', async ({ page }) => {
    // Create a reminder first
    await page.goto('/reminders');
    await page.getByRole('button', { name: /添加提醒/ }).click();
    await page.getByLabel('提醒标题').fill('服用钙片');
    await page.getByRole('button', { name: chineseText('提交') }).click();

    // Today section should appear
    await expect(page.getByText('今日提醒')).toBeVisible();
  });

  test('should show empty state when no reminders', async ({ page }) => {
    await page.goto('/reminders');
    await expect(page.getByText(/暂无提醒/)).toBeVisible();
  });
});

test.describe('Reminders — Toggle & Delete', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `rem_${Date.now()}`);
  });

  test('should toggle reminder enabled state', async ({ page }) => {
    await page.goto('/reminders');
    await page.getByRole('button', { name: /添加提醒/ }).click();
    await page.getByLabel('提醒标题').fill('测试toggle');
    await page.getByRole('button', { name: chineseText('提交') }).click();

    // Find the switch in the table
    const toggle = page.locator('.ant-table-tbody .ant-switch').first();
    await expect(toggle).toBeVisible();
    await toggle.click();
    // Switch state changes
    await expect(toggle).not.toHaveClass(/ant-switch-checked/);
  });

  test('should delete reminder with confirmation', async ({ page }) => {
    await page.goto('/reminders');
    await page.getByRole('button', { name: /添加提醒/ }).click();
    await page.getByLabel('提醒标题').fill('待删除提醒');
    await page.getByRole('button', { name: chineseText('提交') }).click();

    const rows = page.locator('.ant-table-row');
    const rowCount = await rows.count();
    expect(rowCount).toBeGreaterThan(0);

    const actions = opsCell(rows.first());
    await actions.getByText(chineseText('删除')).click();

    // Confirm
    await page.getByRole('button', { name: chineseText('确定') }).click();

    // Reminder removed
    await expect(page.getByText('待删除提醒')).not.toBeVisible();
  });
});

test.describe('Reminders — Auth Guard', () => {
  test('should redirect to login when not authenticated', async ({ page }) => {
    await page.goto('/reminders');
    await page.waitForURL(/\/login/);
  });

  test('should deny access after logout', async ({ page }) => {
    await register(page, `rem_${Date.now()}`);
    await logout(page);
    await page.goto('/reminders');
    await page.waitForURL(/\/login/);
  });
});
