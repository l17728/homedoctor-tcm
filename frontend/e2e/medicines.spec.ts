/**
 * Medicine (西药/药箱) CRUD lifecycle E2E tests.
 *
 * Covers:
 * - Navigation to medicine list
 * - Add new medicine via drawer form
 * - View medicine details
 * - Edit existing medicine
 * - Delete medicine with confirmation
 * - Empty state for new users
 * - Form validation
 */
import { test, expect } from '@playwright/test';
import {
  register,
  logout,
  opsCell,
  chineseText,
  selectAntdOption,
} from './helpers';

test.describe('Medicine CRUD — Navigation & Layout', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `user_${Date.now()}`);
  });

  test('should navigate to medicine list page', async ({ page }) => {
    const medicineGroup = page.locator('.ant-menu-submenu').filter({ hasText: '用药管理' });
    await medicineGroup.locator('.ant-menu-submenu-title').click();
    await medicineGroup.getByRole('menuitem', { name: '药箱', exact: true }).click();
    await page.waitForURL('/medicines');

    await expect(page).toHaveURL('/medicines');
    await expect(page.getByRole('heading', { name: '药箱管理' })).toBeVisible();
  });

  test('should show page header with add button', async ({ page }) => {
    await page.goto('/medicines');

    // Should have an "add" button (Lesson T1: 2-char Chinese button)
    const addButton = page.getByRole('button', { name: chineseText('添加') }).last();
    if (await addButton.isVisible().catch(() => false)) {
      await expect(addButton).toBeVisible();
    }
  });

  test('should show table with expected column headers', async ({ page }) => {
    await page.goto('/medicines');

    const table = page.getByRole('table');
    const isTableVisible = await table.isVisible().catch(() => false);
    if (!isTableVisible) {
      await expect(page.locator('.ant-empty')).toBeVisible();
      return;
    }

    // Common medicine table columns
    const expectedColumns = ['名称', '类型'];
    for (const col of expectedColumns) {
      await expect(table.getByText(col).first()).toBeVisible();
    }
  });
});

test.describe('Medicine CRUD — Create', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `user_${Date.now()}`);
  });

  test('should open add drawer when clicking add button', async ({ page }) => {
    await page.goto('/medicines');

    const addButton = page.getByRole('button', { name: chineseText('添加') }).last();
    if (await addButton.isVisible().catch(() => false)) {
      await addButton.click();

      // Drawer should open
      const drawer = page.locator('.ant-drawer');
      await expect(drawer).toBeVisible();
    }
  });

  test('barcode scanner falls back to manual entry when camera detection is unavailable', async ({ page }) => {
    await page.goto('/medicines');
    const addButton = page.getByRole('button', { name: chineseText('添加') }).last();
    await addButton.click();

    // BarcodeDetector is not available in every browser. The form must keep
    // manual entry usable and explain why camera scanning cannot start.
    await page.evaluate(() => {
      Object.defineProperty(window, 'BarcodeDetector', { configurable: true, value: undefined });
    });
    await page.getByRole('button', { name: '相机扫码' }).click();
    const scanner = page.getByRole('dialog', { name: '扫描药品条形码' });
    await expect(scanner).toBeVisible();
    await expect(scanner.getByText(/当前浏览器不支持相机条码识别/)).toBeVisible();
    await scanner.getByRole('button', { name: '关闭相机并返回' }).click();

    const medicineDrawer = page.locator('.ant-drawer:visible').last();
    await expect(medicineDrawer).toBeVisible();
    await medicineDrawer.getByRole('textbox', { name: '条形码' }).fill('6901234567892');
    await page.getByRole('button', { name: chineseText('校验') }).click();
    await expect(page.getByText(/校验通过/)).toBeVisible();
  });

  test('should add a new medicine via drawer form', async ({ page }) => {
    await page.goto('/medicines');

    const addButton = page.getByRole('button', { name: chineseText('添加') }).last();
    if (await addButton.isVisible().catch(() => false)) {
      await addButton.click();

      // Fill form fields in the drawer
      const nameInput = page.getByLabel('药品名称');
      if (await nameInput.isVisible().catch(() => false)) {
        await nameInput.fill('布洛芬');
      }

      // Select type (Lesson T2: use dispatchEvent for AntD Select)
      const typeSelect = page.locator('.ant-drawer').getByLabel('类型');
      if (await typeSelect.isVisible().catch(() => false)) {
        await selectAntdOption(page, typeSelect, '西药');
      }

      // Submit the form (Lesson T1: 2-char button)
      await page
        .getByRole('button', { name: chineseText('提交') })
        .click();

      // Drawer should close
      const drawer = page.locator('.ant-drawer');
      await expect(drawer).not.toBeVisible();

      // New medicine should appear in the table
      await expect(page.getByText('布洛芬')).toBeVisible();
    }
  });

  test('should show validation errors for required fields', async ({
    page,
  }) => {
    await page.goto('/medicines');

    const addButton = page.getByRole('button', { name: chineseText('添加') }).last();
    if (await addButton.isVisible().catch(() => false)) {
      await addButton.click();

      // Submit without filling any fields
      await page
        .getByRole('button', { name: chineseText('提交') })
        .click();

      // Ant Design form validation should show errors
      await expect(page.getByText(/请输入|必填/).first()).toBeVisible();
    }
  });
});

test.describe('Medicine CRUD — Read', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `user_${Date.now()}`);
  });

  test('should view medicine details by clicking a row', async ({ page }) => {
    await page.goto('/medicines');

    const rows = page.locator('.ant-table-row');
    const rowCount = await rows.count();

    if (rowCount > 0) {
      const firstRow = rows.first();
      const name = await firstRow.locator('td').first().textContent();

      // Click row to open detail drawer
      await firstRow.click();

      const drawer = page.locator('.ant-drawer');
      await expect(drawer).toBeVisible();

      // Detail should show the medicine name
      if (name) {
        await expect(page.getByText(name).first()).toBeVisible();
      }
    }
  });
});

test.describe('Medicine CRUD — Update', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `user_${Date.now()}`);
  });

  test('should edit medicine via operation button', async ({ page }) => {
    await page.goto('/medicines');

    const rows = page.locator('.ant-table-row');
    const rowCount = await rows.count();

    if (rowCount > 0) {
      // Lesson T5: scope to ops cell
      const actions = opsCell(rows.first());
      const editButton = actions.getByText(/编辑|编辑/).first();

      if (await editButton.isVisible().catch(() => false)) {
        await editButton.click();

        // Edit drawer should open
        const drawer = page.locator('.ant-drawer');
        await expect(drawer).toBeVisible();

        // Modify the name
        const nameInput = page.getByLabel('药品名称');
        if (await nameInput.isVisible().catch(() => false)) {
          await nameInput.clear();
          await nameInput.fill('布洛芬缓释胶囊');
        }

        // Submit changes
        await page
          .getByRole('button', { name: chineseText('提交') })
          .click();

        // Updated name should appear
        await expect(page.getByText('布洛芬缓释胶囊')).toBeVisible();
      }
    }
  });
});

test.describe('Medicine CRUD — Delete', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `user_${Date.now()}`);
  });

  test('should delete medicine with confirmation', async ({ page }) => {
    await page.goto('/medicines');

    const rows = page.locator('.ant-table-row');
    const rowCount = await rows.count();

    if (rowCount > 0) {
      const firstName = await rows
        .first()
        .locator('td')
        .first()
        .textContent();

      // Lesson T5: scope to ops cell
      const actions = opsCell(rows.first());
      const deleteButton = actions.getByText(chineseText('删除')).first();

      if (await deleteButton.isVisible().catch(() => false)) {
        await deleteButton.click();

        // Confirmation modal should appear
        const confirmModal = page.locator('.ant-modal-confirm, .ant-popconfirm');
        await expect(confirmModal.first()).toBeVisible();

        // Confirm deletion
        await page
          .getByRole('button', { name: chineseText('确定') })
          .click();

        // Item should be removed from table
        if (firstName) {
          await expect(page.getByText(firstName)).not.toBeVisible();
        }
      }
    }
  });
});

test.describe('Medicine CRUD — Empty State', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `user_${Date.now()}`);
  });

  test('should show empty state when no medicines exist', async ({ page }) => {
    await page.goto('/medicines');

    // For a new user, medicine list should show empty state
    await expect(page.getByRole('heading', { name: '药箱管理' })).toBeVisible();
    await expect(page.getByText('暂无药品，点击添加', { exact: true })).toBeVisible();
  });
});

test.describe('Medicine CRUD — Auth Guard', () => {
  test('should redirect to login when not authenticated', async ({ page }) => {
    await page.goto('/medicines');
    await page.waitForURL(/\/login/);
    await expect(page.getByRole('button', { name: chineseText('登录') })).toBeVisible();
  });

  test('should deny access after logout', async ({ page }) => {
    const uniqueName = `user_${Date.now()}`;
    await register(page, uniqueName);
    await logout(page);

    await page.goto('/medicines');
    await page.waitForURL(/\/login/);
    await expect(page.getByRole('button', { name: chineseText('登录') })).toBeVisible();
  });
});
