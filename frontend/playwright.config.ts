import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright E2E test configuration for 家庭医生 (Family Doctor) project.
 *
 * Lessons from /fighting (documented in AGENTS.md §5):
 * - T1: AntD 5 auto-inserts spaces in 2-char Chinese buttons → use regex patterns
 * - T2: Select dropdowns may be "outside viewport" → use dispatchEvent('click')
 * - T3: Multiple toasts can cause strict mode violations → use .first() or precise selectors
 * - T5: Row action selectors must scope to last td → use opsCell() helper
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI
    ? [['html', { open: 'never' }], ['list']]
    : [['html', { open: 'never' }], ['list']],
  timeout: 30000,
  expect: {
    timeout: 10000,
  },
  use: {
    baseURL: 'http://localhost:3000',
    locale: 'zh-CN',
    viewport: { width: 1280, height: 720 },
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command: 'npm run dev',
    port: 3000,
    reuseExistingServer: true,
    timeout: 30000,
  },
});
