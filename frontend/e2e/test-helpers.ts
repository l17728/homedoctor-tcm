/**
 * Extended E2E test helpers for 家庭医生 (Family Doctor) project.
 *
 * This file supplements helpers.ts with a registration flow that handles
 * the PIPL consent checkboxes and birth year field required by the
 * current login page (added after the original helpers.ts was written).
 *
 * Usage: import { registerWithConsent } from './test-helpers';
 */
import { type Page } from '@playwright/test';
import { chineseText, DEFAULT_PASSWORD } from './helpers';

/**
 * Register a new user via the UI, handling PIPL consent checkboxes.
 *
 * The login page registration form requires:
 * 1. Username + password + confirm password
 * 2. Privacy policy checkbox (mandatory — shows "请同意隐私政策" error if unchecked)
 * 3. Health data consent checkbox (optional)
 * 4. Birth year spinbutton (optional, for minor protection)
 *
 * Waits for redirect to the home page.
 */
export async function registerWithConsent(
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

  // Check the mandatory privacy policy consent checkbox
  const privacyCheckbox = activePane.getByRole('checkbox', {
    name: /隐私政策.*用户协议/,
  });
  await privacyCheckbox.check();

  // Optionally check health data consent checkbox
  const healthCheckbox = activePane.getByRole('checkbox', {
    name: /健康数据/,
  });
  const healthVisible = await healthCheckbox.isVisible().catch(() => false);
  if (healthVisible) {
    await healthCheckbox.check();
  }

  // Click register button
  await activePane.getByRole('button', { name: chineseText('注册') }).click();
  await page.waitForURL('/', { timeout: 15000 });
}
