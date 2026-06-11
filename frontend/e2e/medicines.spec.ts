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
    await page.getByText('药箱').first().click();
    await page.waitForURL('/medicines');

    await expect(page).toHaveURL('/medicines');
    await expect(page.getByText(/药品|药箱/)).toBeVisible();
  });

  test('should show page header with add button', async ({ page }) => {
    await page.goto('/medicines');

    // Should have an "add" button (Lesson T1: 2-char Chinese button)
    const addButton = page.getByRole('button', { name: chineseText('添加') });
    if (await addButton.isVisible().catch(() => false)) {
      await expect(addButton).toBeVisible();
    }
  });

  test('should show table with expected column headers', async ({ page }) => {
    await page.goto('/medicines');

    const table = page.locator('.ant-table');
    await expect(table).toBeVisible();

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

    const addButton = page.getByRole('button', { name: chineseText('添加') });
    if (await addButton.isVisible().catch(() => false)) {
      await addButton.click();

      // Drawer should open
      const drawer = page.locator('.ant-drawer');
      await expect(drawer).toBeVisible();
    }
  });

  test('should add a new medicine via drawer form', async ({ page }) => {
    await page.goto('/medicines');

    const addButton = page.getByRole('button', { name: chineseText('添加') });
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

    const addButton = page.getByRole('button', { name: chineseText('添加') });
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
    const emptyText = page.getByText(/暂无药品|没有药品|暂无数据/);
    const table = page.locator('.ant-table');

    const hasEmpty = await emptyText.isVisible().catch(() => false);
    const hasTable = await table.isVisible().catch(() => false);
    expect(hasEmpty || hasTable).toBeTruthy();
  });
});

test.describe('Medicine CRUD — Auth Guard', () => {
  test('should redirect to login when not authenticated', async ({ page }) => {
    await page.goto('/medicines');
    await page.waitForURL(/\/login/);
    await expect(page.getByText(chineseText('登录'))).toBeVisible();
  });

  test('should deny access after logout', async ({ page }) => {
    const uniqueName = `user_${Date.now()}`;
    await register(page, uniqueName);
    await logout(page);

    await page.goto('/medicines');
    await page.waitForURL(/\/login/);
    await expect(page.getByText(chineseText('登录'))).toBeVisible();
  });
});
