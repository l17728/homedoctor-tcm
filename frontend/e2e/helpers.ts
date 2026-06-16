/**
 * Shared E2E test utilities for 家庭医生 (Family Doctor) project.
 *
 * Lessons from /fighting (documented in AGENTS.md §5):
 * - T1: Ant Design 5 auto-inserts spaces in 2-char Chinese button labels
 * - T2: Select dropdowns may be "outside viewport" → dispatchEvent('click')
 * - T3: Multiple Toast messages cause strict mode violations → use .first()
 * - T4: Drawer close does not trigger form submit → regression coverage
 * - T5: Row action selectors match multiple columns → scope to last td
 */
import { type Page, type Locator } from '@playwright/test';

// ---------------------------------------------------------------------------
// Lesson T5: Always scope row actions to last <td>
// ---------------------------------------------------------------------------

/**
 * Get the operations cell (last column) of a table row.
 * Prevents false matches on earlier columns that might contain link text.
 */
export function opsCell(row: Locator): Locator {
  return row.locator('td').last();
}

// ---------------------------------------------------------------------------
// Lesson T1: AntD 5 auto-inserts spaces in 2-char Chinese buttons
// ---------------------------------------------------------------------------

const CJK_PATTERN = /[\u4e00-\u9fff]/;

/**
 * Build a locator for a button or text element, accounting for Ant Design 5's
 * automatic space insertion between the two characters of 2-char Chinese labels.
 *
 * Examples:
 *   buttonByText(page, '登录') → matches "登 录" or "登录"
 *   buttonByText(page, '添加') → matches "添 加" or "添加"
 *   buttonByText(page, 'Submit') → matches "Submit" exactly
 */
export function buttonByText(page: Page, text: string): Locator {
  if (text.length === 2 && CJK_PATTERN.test(text)) {
    const regex = new RegExp(text.split('').join('\\s?'));
    return page.getByText(regex);
  }
  return page.getByText(text);
}

/**
 * Build a regex-compatible string for 2-char Chinese text that may have
 * an auto-inserted space. Useful for getByRole('button', { name: ... }).
 */
export function chineseText(text: string): RegExp {
  if (text.length === 2 && CJK_PATTERN.test(text)) {
    return new RegExp(text.split('').join('\\s?'));
  }
  return new RegExp(text);
}

// ---------------------------------------------------------------------------
// Auth helpers
// ---------------------------------------------------------------------------

/** Default test credentials */
export const DEFAULT_PASSWORD = 'testpass123';

/**
 * Log in via the UI. Waits for redirect to the home page.
 */
export async function login(
  page: Page,
  username: string = 'testuser',
  password: string = DEFAULT_PASSWORD,
): Promise<void> {
  await page.goto('/login');
  // Scope to active tab pane — AntD keeps both login/register forms in DOM
  const activePane = page.locator('.ant-tabs-tabpane-active');
  await activePane.getByPlaceholder('用户名').fill(username);
  await activePane.getByPlaceholder('密码').fill(password);
  await activePane.getByRole('button', { name: chineseText('登录') }).click();
  await page.waitForURL('/');
}

/**
 * Register a new user via the UI. Assumes the login page has a register tab.
 * Waits for redirect to the home page.
 */
export async function register(
  page: Page,
  username: string,
  password: string = DEFAULT_PASSWORD,
): Promise<void> {
  await page.goto('/login');
  // Switch to register tab (AntD Tabs component)
  await page.getByRole('tab', { name: chineseText('注册') }).click();
  await page.waitForTimeout(300);
  // Scope to active tab pane — AntD keeps both login/register forms in DOM
  const activePane = page.locator('.ant-tabs-tabpane-active');
  await activePane.getByPlaceholder('用户名').fill(username);
  await activePane.getByPlaceholder('密码', { exact: true }).fill(password);
  await activePane.getByPlaceholder('确认密码').fill(password);
  await activePane.getByRole('button', { name: chineseText('注册') }).click();
  await page.waitForURL('/');
}

/**
 * Log out via the user menu dropdown.
 */
export async function logout(page: Page): Promise<void> {
  // Click the user avatar/name to open the dropdown
  await page.getByRole('button', { name: /用户/ }).click();
  await page.getByText(chineseText('退出')).click();
  await page.waitForURL('/login');
}

// ---------------------------------------------------------------------------
// Navigation helpers
// ---------------------------------------------------------------------------

/**
 * Navigate to a sidebar menu item by text label.
 */
export async function navigateTo(page: Page, menuLabel: string): Promise<void> {
  await page.getByText(menuLabel).click();
}

// ---------------------------------------------------------------------------
// AntD-specific helpers
// ---------------------------------------------------------------------------

/**
 * Select an option from an Ant Design Select dropdown.
 * Lesson T2: Use dispatchEvent('click') to avoid "outside viewport" issues.
 * Robust approach: click trigger → wait for dropdown → scroll option into view → click.
 */
export async function selectAntdOption(
  page: Page,
  triggerLocator: Locator,
  optionText: string,
): Promise<void> {
  await triggerLocator.dispatchEvent('click');
  await page.waitForTimeout(300); // Give AntD time to render the dropdown portal

  // Try role-based option first
  const option = page.getByRole('option', { name: optionText }).first();
  const isVisible = await option.isVisible().catch(() => false);

  if (isVisible) {
    await option.scrollIntoViewIfNeeded();
    await option.click();
  } else {
    // Fallback: click by text inside the dropdown container
    const dropdown = page.locator('.ant-select-dropdown').last();
    const textOption = dropdown.getByText(optionText, { exact: true }).first();
    await textOption.waitFor({ state: 'visible', timeout: 5000 });
    await textOption.scrollIntoViewIfNeeded();
    await textOption.click();
  }
}

/**
 * Get the first toast/notification message on the page.
 * Lesson T3: Multiple toasts can cause strict mode violations.
 */
export function firstToast(page: Page): Locator {
  return page.locator('.ant-message-notice, .ant-notification-notice').first();
}

// ---------------------------------------------------------------------------
// AntD TimePicker.RangePicker helper
// ---------------------------------------------------------------------------

/**
 * Fill an AntD TimePicker.RangePicker by selecting cells from the dropdown panel.
 *
 * AntD's fill() on the input does NOT set the form value — the picker requires
 * actual panel interaction. This helper opens the panel and clicks the hour/minute
 * cells for both start and end times.
 *
 * @param page Playwright Page
 * @param drawer The drawer locator containing the form
 * @param hour   Hour string (e.g. '08')
 * @param minute Minute string (e.g. '00')
 */
export async function fillTimeRangePicker(
  page: Page,
  drawer: Locator,
  hour: string = '08',
  minute: string = '00',
): Promise<void> {
  const picker = drawer.locator('.ant-picker-range').first();
  const timeStr = `${hour}:${minute}`;

  await picker.locator('input').nth(0).click();
  await page.waitForTimeout(300);
  await page.keyboard.type(timeStr);
  await page.waitForTimeout(200);
  await page.keyboard.press('Tab');
  await page.waitForTimeout(300);

  await page.keyboard.type(timeStr);
  await page.waitForTimeout(200);
  await page.keyboard.press('Tab');
  await page.waitForTimeout(300);
}
