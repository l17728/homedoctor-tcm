/**
 * Knowledge Import (知识导入) page E2E tests.
 *
 * Covers:
 * - Page renders with title and upload area (Dragger)
 * - File type badges visible (PDF/Word/TXT/图片)
 * - Recent imports section (table or empty state)
 * - Upload area is interactive (accepts file types)
 */
import { test, expect } from '@playwright/test';
import { registerWithConsent as register } from './test-helpers';

test.describe('Knowledge Import Page — 知识导入', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `user_${Date.now()}`);
  });

  test('should load page with title and upload area', async ({ page }) => {
    await page.goto('/knowledge-import');

    await expect(page).toHaveURL('/knowledge-import');
    // Page title heading "知识导入"
    await expect(page.getByRole('heading', { name: /知识导入/ })).toBeVisible();

    // Upload Dragger area (AntD 5 uses .ant-upload-drag class)
    await expect(page.locator('.ant-upload-drag')).toBeVisible();

    // Upload hint text
    await expect(page.getByText(/点击或拖拽文件到此处/)).toBeVisible();
  });

  test('should show file type badges (PDF/Word/TXT/图片)', async ({ page }) => {
    await page.goto('/knowledge-import');

    // File type support tags
    await expect(page.getByText('PDF').first()).toBeVisible();
    await expect(page.getByText('Word').first()).toBeVisible();
    await expect(page.getByText(/TXT.*Markdown/).first()).toBeVisible();
    await expect(page.getByText(/图片.*OCR/)).toBeVisible();

    // Should mention size limit
    await expect(page.getByText(/20MB|上限/)).toBeVisible();
  });

  test('should show recent imports table or empty state', async ({ page }) => {
    await page.goto('/knowledge-import');
    await page.waitForTimeout(1500);

    const hasTable = await page.locator('.ant-table').first().isVisible().catch(() => false);
    const hasEmpty = await page.getByText(/暂无导入记录/).isVisible().catch(() => false);

    expect(hasTable || hasEmpty).toBeTruthy();

    if (hasTable) {
      const table = page.locator('.ant-table');
      // Expected columns
      for (const col of ['文件名', '类型', '操作']) {
        await expect(table.getByText(col).first()).toBeVisible();
      }
    }
  });

  test('should have upload area that accepts file input', async ({ page }) => {
    await page.goto('/knowledge-import');

    // The Dragger should have a hidden file input (AntD 5 uses .ant-upload-drag)
    const fileInput = page.locator('.ant-upload-drag input[type="file"]');
    await expect(fileInput).toHaveCount(1);

    // Verify accepted file types
    const accept = await fileInput.getAttribute('accept');
    expect(accept).toContain('.pdf');
    expect(accept).toContain('.docx');
    expect(accept).toContain('.txt');
  });
});
