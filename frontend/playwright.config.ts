import { defineConfig, devices } from '@playwright/test';

const apiPort = Number(process.env.HOMEDOCTOR_API_PORT ?? 7459);
if (!Number.isInteger(apiPort) || apiPort < 1 || apiPort > 65535) {
  throw new Error('HOMEDOCTOR_API_PORT must be a valid TCP port');
}
const webPort = Number(process.env.HOMEDOCTOR_WEB_PORT ?? 3000);
if (!Number.isInteger(webPort) || webPort < 1 || webPort > 65535) {
  throw new Error('HOMEDOCTOR_WEB_PORT must be a valid TCP port');
}

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
  globalSetup: './e2e/global-setup.ts',
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
    baseURL: `http://127.0.0.1:${webPort}`,
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
  webServer: process.env.CI
    ? [
        {
          command: `python scripts/seed_e2e_database.py && python -m uvicorn app.main:app --host 127.0.0.1 --port ${apiPort}`,
          cwd: '../backend',
          url: `http://127.0.0.1:${apiPort}/api/health`,
          reuseExistingServer: false,
          timeout: 300000,
        },
        {
          command: `npm run preview -- --host 127.0.0.1 --port ${webPort} --strictPort`,
          url: `http://127.0.0.1:${webPort}`,
          reuseExistingServer: false,
          timeout: 30000,
        },
      ]
    : {
        command: `npm run dev -- --host 127.0.0.1 --port ${webPort} --strictPort`,
        port: webPort,
        reuseExistingServer: true,
        timeout: 30000,
      },
});
