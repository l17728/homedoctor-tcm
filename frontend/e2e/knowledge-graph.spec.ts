/**
 * Knowledge Graph (知识图谱) page E2E tests.
 *
 * Covers:
 * - Page renders with title and graph container
 * - Filter controls visible (type selector, search input)
 * - Action buttons visible (定位/刷新/重建图谱)
 * - "重建图谱" button triggers Popconfirm
 * - Graph stats text visible
 */
import { test, expect } from '@playwright/test';
import { registerWithConsent as register } from './test-helpers';

test.describe('Knowledge Graph Page — 知识图谱', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `user_${Date.now()}`);
  });

  test('should load page with title and subtitle', async ({ page }) => {
    await page.goto('/knowledge-graph');

    await expect(page).toHaveURL('/knowledge-graph');
    // Title "知识图谱"
    await expect(page.getByText('知识图谱').first()).toBeVisible();
    // Subtitle
    await expect(page.getByText(/中药.*方剂.*症状.*疗法/)).toBeVisible();
  });

  test('should show filter controls (type selector and search input)', async ({
    page,
  }) => {
    await page.goto('/knowledge-graph');

    // Type filter Select with placeholder
    await expect(
      page.locator('.ant-select').filter({ hasText: /按类型筛选/ }).first(),
    ).toBeVisible();

    // Search input
    await expect(page.getByPlaceholder('搜索关键词')).toBeVisible();
  });

  test('should show action buttons (定位/刷新/重建图谱)', async ({ page }) => {
    await page.goto('/knowledge-graph');

    // 定位 button
    await expect(page.getByRole('button', { name: /定位/ })).toBeVisible();

    // 刷新 button
    await expect(page.getByRole('button', { name: /刷新/ })).toBeVisible();

    // 重建图谱 button
    await expect(page.getByRole('button', { name: /重建图谱/ })).toBeVisible();
  });

  test('should show graph container and stats text', async ({ page }) => {
    await page.goto('/knowledge-graph');
    await page.waitForTimeout(2000);

    // The graph canvas container should exist (div with the G6 canvas inside)
    const graphContainer = page.locator('canvas').first();
    const hasCanvas = await graphContainer.isVisible().catch(() => false);

    // Stats text: "单击查看详情 · 双击展开/折叠关联 · 当前 X 节点 / X 关系"
    await expect(page.getByText(/单击查看详情.*双击展开/)).toBeVisible();

    // Should mention node/edge counts
    await expect(page.getByText(/节点/)).toBeVisible();

    // If no canvas, there should be empty state
    if (!hasCanvas) {
      await expect(page.getByText(/暂无图谱数据/)).toBeVisible();
    }
  });

  test('should show Popconfirm when clicking 重建图谱', async ({ page }) => {
    await page.goto('/knowledge-graph');

    // Click rebuild button
    await page.getByRole('button', { name: /重建图谱/ }).click();
    await page.waitForTimeout(500);

    // Popconfirm should appear with confirm/cancel buttons
    await expect(page.getByText('确认重建')).toBeVisible();
    await expect(page.getByRole('button', { name: /取消/ })).toBeVisible();

    // Cancel the confirmation
    await page.getByRole('button', { name: /取消/ }).click();
  });
});
