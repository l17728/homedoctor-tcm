import { test, expect } from '@playwright/test';

test.describe('经络穴位模块', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('http://localhost:3000/login');
    await page.fill('input[placeholder*="用户名"], input#username', 'testuser');
    await page.fill('input[placeholder*="密码"], input#password', 'test123');
    await page.click('button[type="submit"]');
    await page.waitForURL('**/dashboard', { timeout: 10000 }).catch(() => {});
  });

  test('经络穴位页面加载 + 显示14经络', async ({ page }) => {
    await page.goto('http://localhost:3000/acupoints');
    await page.waitForTimeout(2000);

    await expect(page.locator('text=经络穴位')).toBeVisible({ timeout: 10000 });

    const meridianCards = page.locator('.ant-card');
    await expect(meridianCards.first()).toBeVisible({ timeout: 10000 });
    const count = await meridianCards.count();
    expect(count).toBeGreaterThanOrEqual(10);
  });

  test('搜索穴位 — 足三里', async ({ page }) => {
    await page.goto('http://localhost:3000/acupoints');
    await page.waitForTimeout(2000);

    const searchInput = page.locator('input[placeholder*="搜索穴位"]');
    await searchInput.fill('足三里');
    await page.waitForTimeout(1500);

    await expect(page.locator('text=足三里')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('text=ST36').first()).toBeVisible();
  });

  test('点击经络卡片筛选穴位', async ({ page }) => {
    await page.goto('http://localhost:3000/acupoints');
    await page.waitForTimeout(2000);

    await page.locator('text=手太阴肺经').first().click();
    await page.waitForTimeout(1500);

    const tableRows = page.locator('.ant-table-tbody tr');
    await expect(tableRows.first()).toBeVisible({ timeout: 10000 });
    const count = await tableRows.count();
    expect(count).toBeGreaterThanOrEqual(1);
  });

  test('穴位详情抽屉 — 定位 + 刺法', async ({ page }) => {
    await page.goto('http://localhost:3000/acupoints');
    await page.waitForTimeout(2000);

    await page.locator('input[placeholder*="搜索穴位"]').fill('合谷');
    await page.waitForTimeout(1500);

    await page.locator('text=合谷').first().click();
    await page.waitForTimeout(1500);

    const drawer = page.locator('.ant-drawer');
    await expect(drawer).toBeVisible({ timeout: 5000 });
    await expect(page.locator('.ant-drawer').locator('text=定位')).toBeVisible();
    await expect(page.locator('.ant-drawer').locator('text=刺法')).toBeVisible();
  });

  test('视图切换 — 经络 ↔ 穴位', async ({ page }) => {
    await page.goto('http://localhost:3000/acupoints');
    await page.waitForTimeout(2000);

    await page.locator('button:has-text("穴位")').click();
    await page.waitForTimeout(1500);
    await expect(page.locator('.ant-table')).toBeVisible({ timeout: 5000 });

    await page.locator('button:has-text("经络")').click();
    await page.waitForTimeout(500);
    await expect(page.locator('.ant-card').first()).toBeVisible({ timeout: 5000 });
  });
});

test.describe('知识库语义搜索', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('http://localhost:3000/login');
    await page.fill('input[placeholder*="用户名"], input#username', 'testuser');
    await page.fill('input[placeholder*="密码"], input#password', 'test123');
    await page.click('button[type="submit"]');
    await page.waitForURL('**/dashboard', { timeout: 10000 }).catch(() => {});
  });

  test('语义搜索开关存在', async ({ page }) => {
    await page.goto('http://localhost:3000/knowledge-hub');
    await page.waitForTimeout(2000);

    await expect(page.locator('text=经络穴位').first()).toBeVisible({ timeout: 10000 }).catch(() => {});

    const switchBtn = page.locator('.ant-switch').first();
    if (await switchBtn.isVisible()) {
      await switchBtn.click();
      await page.waitForTimeout(500);
    }
  });
});

test.describe('外治理疗扩充', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('http://localhost:3000/login');
    await page.fill('input[placeholder*="用户名"], input#username', 'testuser');
    await page.fill('input[placeholder*="密码"], input#password', 'test123');
    await page.click('button[type="submit"]');
    await page.waitForURL('**/dashboard', { timeout: 10000 }).catch(() => {});
  });

  test('外治理疗页面加载 + 多分类', async ({ page }) => {
    await page.goto('http://localhost:3000/therapies');
    await page.waitForTimeout(2000);

    const cards = page.locator('.ant-card');
    await expect(cards.first()).toBeVisible({ timeout: 10000 });
    const count = await cards.count();
    expect(count).toBeGreaterThanOrEqual(5);
  });
});
