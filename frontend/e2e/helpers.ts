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
import { expect, type Page, type Locator } from '@playwright/test';

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
  // Keep first-login onboarding out of unrelated feature journeys. Onboarding
  // has its own product flow and its modal otherwise blocks sidebar clicks.
  await page.addInitScript(() => localStorage.setItem('onboarding_completed', 'true'));
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
  // PIPL consent checkboxes (required by LoginPage since v0.4.0)
  const consentPrivacy = activePane.getByRole('checkbox', {
    name: /我已阅读并同意/,
  });
  if (await consentPrivacy.isVisible().catch(() => false)) {
    await consentPrivacy.check();
  }
  const consentHealth = activePane.getByRole('checkbox', {
    name: /我同意收集健康数据/,
  });
  if (await consentHealth.isVisible().catch(() => false)) {
    await consentHealth.check();
  }
  await activePane.getByRole('button', { name: chineseText('注册') }).click();
  await page.waitForURL('/');
  // First-run onboarding otherwise intercepts unrelated sidebar interactions.
  await page.evaluate(() => localStorage.setItem('onboarding_completed', 'true'));
  await page.reload();
  await page.waitForURL('/');
}

/**
 * Log out via the user menu dropdown.
 */
export async function logout(page: Page): Promise<void> {
  // Token-injection auth guard tests can land on first-run onboarding. Mark it
  // complete and reload so its modal cannot intercept the account-menu click.
  await page.evaluate(() => localStorage.setItem('onboarding_completed', 'true'));
  await page.reload();
  // Click the user avatar/name to open the dropdown
  await page.getByRole('button', { name: /用户/ }).click();
  await page.getByRole('menuitem', { name: /退出登录/ }).click();
  await page.waitForURL('/login');
}

// ---------------------------------------------------------------------------
// Navigation helpers
// ---------------------------------------------------------------------------

/**
 * Navigate to a sidebar menu item by text label.
 */
export async function navigateTo(page: Page, menuLabel: string): Promise<void> {
  const normalized = menuLabel.replace(/\s/g, '');
  const knowledgeItems = ['知识库', '中药', '方剂', '外治理疗', '经络穴位', '分类浏览', '经典读诵', '知识图谱'];
  const medicineItems = ['药箱', '吃药提醒', '提醒', '用药套餐', '服药计划', '药箱安全检查'];
  const healthItems = ['健康档案', '体质自测', '健康日志', '健康管理', String.fromCharCode(23395,33410,20859,29983), '季节养生'];
  const parent = knowledgeItems.includes(normalized)
    ? '知识探索'
    : medicineItems.includes(normalized)
      ? '用药管理'
      : healthItems.includes(normalized)
        ? '健康管理'
      : null;
  const targetLabel = normalized === '提醒' ? '吃药提醒' : menuLabel.trim();
  if (parent) {
    const parentItem = page.getByRole('menuitem', { name: new RegExp(parent) }).first();
    const targetItem = page.locator('.ant-menu-item').filter({ hasText: new RegExp(`^${targetLabel}$`) }).last();
    if (!(await targetItem.isVisible().catch(() => false))) {
      await parentItem.click();
      await expect(targetItem).toBeVisible();
    }
    await targetItem.dispatchEvent('click');
    return;
  }

  const label = normalized === 'AI助手' ? /AI\s?助手/ : new RegExp(`^${targetLabel}$`);
  await page.locator('.ant-menu-item').filter({ hasText: label }).last().click();
}

/** Answer one option for every visible constitution question. */
export async function answerVisibleConstitutionQuestions(page: Page): Promise<void> {
  const cards = page.locator('.ant-card').filter({ has: page.locator('.ant-radio-group') });
  const count = await cards.count();
  for (let i = 0; i < count; i++) {
    await cards.nth(i).locator('.ant-radio-wrapper').first().click();
  }
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
  await triggerLocator.click();

  // AntD places the active listbox in a portal. Query rendered option elements
  // directly because popup roles can be inconsistently exposed when closed
  // Select portals remain mounted.
  const triggerRole = await triggerLocator.getAttribute('role');
  const combobox = triggerRole === 'combobox'
    ? triggerLocator
    : triggerLocator.locator('[role="combobox"]').first();
  const options = page.locator(
    '.ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item-option',
  );
  await expect.poll(async () => {
    for (let i = 0; i < await options.count(); i++) {
      const candidate = options.nth(i);
      if ((await candidate.textContent())?.trim() === optionText && await candidate.isVisible()) return true;
    }
    return false;
  }).toBe(true);
  let option: Locator | undefined;
  for (let i = 0; i < await options.count(); i++) {
    const candidate = options.nth(i);
    if ((await candidate.textContent())?.trim() === optionText && await candidate.isVisible()) {
      option = candidate;
      break;
    }
  }
  if (!option) throw new Error(`Visible Select option not found: ${optionText}`);
  // AntD renders dropdowns in a portal and Playwright's normal click can fail
  // viewport checks even when the option is present. Dispatch on the scoped option.
  await option.dispatchEvent('click');
  await expect(combobox).toHaveAttribute('aria-expanded', 'false');
}

/**
 * Get the first toast/notification message on the page.
 * Lesson T3: Multiple toasts can cause strict mode violations.
 */
export function firstToast(page: Page): Locator {
  return page.locator('.ant-message-notice, .ant-notification-notice').first();
}

// ---------------------------------------------------------------------------
// AntD TimePicker helper (supports the current multi-time reminder control and
// older RangePicker based forms).
// ---------------------------------------------------------------------------

/**
 * Set a reminder time. The current reminder form uses one TimePicker per slot;
 * older forms used a TimePicker.RangePicker.
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
  const timeStr = `${hour}:${minute}`;

  const rangePicker = drawer.locator('.ant-picker-range').first();
  if (await rangePicker.count()) {
    await rangePicker.locator('input').nth(0).click();
    await page.waitForTimeout(300);
    await page.keyboard.type(timeStr);
    await page.keyboard.press('Tab');
    await page.waitForTimeout(200);
    await page.keyboard.type(timeStr);
    await page.keyboard.press('Tab');
    await page.waitForTimeout(200);
    return;
  }

  const input = drawer.locator('.ant-picker:not(.ant-picker-range) input').first();
  await input.fill(timeStr);
  await input.press('Enter');
  await input.press('Tab');
  await expect(input).toHaveValue(timeStr);
}
