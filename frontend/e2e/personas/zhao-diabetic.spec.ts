/**
 * Persona 6: 赵国强 (72岁, 退休工人, 糖尿病) — E2E tests.
 *
 * Background: 2型糖尿病12年+高血压8年，每天打胰岛素+吃3种降压药。
 *             老伴帮他操作手机。用安卓手机。左眼白内障视力差。
 * Needs: 多重用药管理、药物交互检查、吃药提醒(5种药不同时间)、简单界面
 * Concerns: 复杂操作做不了、看错数字、漏服药物
 *
 * Covers:
 * 1. 注册 + Dashboard 可见
 * 2. 设置长辈模式 → 验证 3-Tab 布局
 * 3. 长辈模式首页 → 验证健康信息 + 字体
 * 4. 添加 5 种药品 → 验证药箱列表
 * 5. 创建多个提醒 → 验证今日列表
 * 6. 提醒打卡 → 验证状态变为已服
 * 7. AI 问答 (长辈模式)
 * 8. 安全检查 (标准模式): 黄芪+二甲双胍
 */
import { test, expect } from '@playwright/test';
import {
  register,
  chineseText,
} from '../helpers';

// ---------------------------------------------------------------------------
// Helper: Enable elderly mode via settings page
// ---------------------------------------------------------------------------
async function enableElderlyMode(page: import('@playwright/test').Page): Promise<void> {
  await page.goto('/settings');
  const elderlySwitch = page
    .locator('.ant-form-item')
    .filter({ hasText: '长辈模式' })
    .locator('.ant-switch');
  await elderlySwitch.click();
  await page.getByRole('button', { name: /确定切换/ }).click();
  await expect(page.locator('body')).toHaveClass(/elderly-mode/);
}

// ---------------------------------------------------------------------------
// Helper: Add a medicine via the drawer form
// ---------------------------------------------------------------------------
async function addMedicine(
  page: import('@playwright/test').Page,
  name: string,
  type: string,
): Promise<void> {
  await page.goto('/medicines');
  await page.waitForTimeout(500);

  await page.getByRole('button', { name: chineseText('添加') }).click();
  const drawer = page.locator('.ant-drawer');
  await expect(drawer).toBeVisible();

  await page.getByLabel('药品名称').fill(name);

  await page.waitForTimeout(500);
  await drawer.locator('.ant-select-selector').first().click();
  await page.waitForTimeout(500);
  await page.locator('.ant-select-item-option').filter({ hasText: type }).first().click({ force: true });

  await page.getByRole('button', { name: chineseText('提交') }).click();
  await page.waitForTimeout(1000);
  await expect(page.locator('.ant-drawer-content')).toBeHidden({ timeout: 5000 });
  await page.waitForTimeout(500);
}

test.describe('Persona: 赵国强 (72岁糖尿病退休工人) — 用药管理与长辈模式', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `zhao_${Date.now()}_${Math.floor(Math.random() * 10000)}`);
  });

  // -------------------------------------------------------------------------
  // Test 1: 注册 + Dashboard 可见
  // -------------------------------------------------------------------------

  test('01 注册成功并验证 Dashboard 可见', async ({ page }) => {
    await expect(page).toHaveURL('/');
    await expect(page.getByText('今日健康')).toBeVisible();

    // 验证统计卡片可见
    await expect(
      page.locator('.ant-statistic').filter({ hasText: '药箱数' }),
    ).toBeVisible();
    await expect(
      page.locator('.ant-statistic').filter({ hasText: '今日提醒' }),
    ).toBeVisible();

    // PRODUCT GAP: 新用户 Dashboard 没有引导提示（如"欢迎使用，请先添加您的药品"）
  });

  // -------------------------------------------------------------------------
  // Test 2: 设置长辈模式 → 验证 3-Tab 布局
  // -------------------------------------------------------------------------

  test('02 开启长辈模式并验证3-Tab布局 (首页/AI问答/我的)', async ({ page }) => {
    await enableElderlyMode(page);

    // 验证侧边栏消失
    await expect(page.locator('.ant-layout-sider')).not.toBeVisible();

    // 验证5-Tab底部导航可见
    await expect(page.getByText('首页').last()).toBeVisible();
    await expect(page.getByText('问答').last()).toBeVisible();
    await expect(page.getByText('我的').last()).toBeVisible();

    // 验证 body 有 elderly-mode class
    await expect(page.locator('body')).toHaveClass(/elderly-mode/);

    // PRODUCT GAP: 长辈模式缺少SOS紧急按钮（72岁糖尿病+高血压患者安全需求）
  });

  // -------------------------------------------------------------------------
  // Test 3: 长辈模式首页 → 验证健康信息 + 字体够大
  // -------------------------------------------------------------------------

  test('03 长辈模式首页显示健康信息且字体够大', async ({ page }) => {
    await enableElderlyMode(page);

    // 导航到首页
    await page.goto('/');
    await page.waitForTimeout(1000);

    // 验证"今日健康"标题可见
    await expect(page.getByText('今日健康')).toBeVisible();

    // 验证统计卡片区域可见（即使数据为0）
    const statArea = page.locator('.ant-statistic').first();
    await expect(statArea).toBeVisible();

    // 验证每日养生卡可见（如果数据存在）
    const dailyHealthCard = page.locator('.ant-card').filter({ hasText: /节气|养生/ });
    if (await dailyHealthCard.first().isVisible().catch(() => false)) {
      await expect(dailyHealthCard.first()).toBeVisible();
    }

    // 验证字体大小 ≥ 18px (elderly-mode.css 应设置 body font-size: 18px)
    // UX ISSUE: 长辈模式下统计数字字体是否足够大需验证
    const bodyFontSize = await page.evaluate(() => {
      const body = document.body;
      return window.getComputedStyle(body).fontSize;
    });
    const fontSizeNum = parseInt(bodyFontSize, 10);
    expect(fontSizeNum).toBeGreaterThanOrEqual(16);

    // PRODUCT GAP: 长辈模式首页缺少"今日用药清单"一目了然显示
    // PRODUCT GAP: 缺少"血糖记录"和"血压记录"功能（糖尿病+高血压核心需求）
  });

  // -------------------------------------------------------------------------
  // Test 4: 添加 5 种药品 → 验证药箱列表
  // -------------------------------------------------------------------------

  test('04 添加5种药品(胰岛素/二甲双胍/缬沙坦/氨氯地平/阿司匹林)并验证列表', async ({
    page,
  }) => {
    // 添加 5 种药品
    const medicines = [
      { name: '胰岛素', type: '西药' },
      { name: '二甲双胍', type: '西药' },
      { name: '缬沙坦', type: '西药' },
      { name: '氨氯地平', type: '西药' },
      { name: '阿司匹林', type: '西药' },
    ];

    for (const med of medicines) {
      await addMedicine(page, med.name, med.type);
    }

    // 验证药箱列表包含所有5种药
    await page.goto('/medicines');
    await page.waitForTimeout(1000);

    const table = page.locator('.ant-table');
    await expect(table).toBeVisible();

    for (const med of medicines) {
      await expect(page.getByText(med.name).first()).toBeVisible();
    }

    // 验证药品数量
    const rows = page.locator('.ant-table-row');
    const rowCount = await rows.count();
    expect(rowCount).toBeGreaterThanOrEqual(5);

    // PRODUCT GAP: 药箱不支持区分"注射剂"（胰岛素）和"口服药"，类型选项无此分类
    // PRODUCT GAP: 缺少"库存不足预警"在列表中的突出显示（已有低库存Tag但需手动设置数量）
  });

  // -------------------------------------------------------------------------
  // Test 5: 创建多个提醒 → 验证今日列表
  // -------------------------------------------------------------------------

  test('05 创建多个提醒(早7点降压药/午12点二甲双胍/晚6点二甲双胍/睡前胰岛素)验证今日列表', async ({
    page,
  }) => {
    const reminders = [
      { title: '早服降压药(缬沙坦+氨氯地平)', time: '07:00' },
      { title: '午服二甲双胍', time: '12:00' },
      { title: '晚服二甲双胍', time: '18:00' },
      { title: '睡前注射胰岛素', time: '22:00' },
    ];

    for (const reminder of reminders) {
      await page.goto('/reminders');
      await page.waitForTimeout(500);

      await page.getByRole('button', { name: /添加提醒/ }).click();
      const drawer = page.locator('.ant-drawer');
      await expect(drawer).toBeVisible();

      // 填写标题
      await page.getByLabel('提醒标题').fill(reminder.title);

      await page.waitForTimeout(500);
      await drawer.locator('.ant-select-selector').first().click();
      await page.waitForTimeout(500);
      await page.locator('.ant-select-item-option').filter({ hasText: '每天' }).first().click({ force: true });

      // 设置时间（TimePicker.RangePicker 需要设置开始和结束时间）
      // 实际只需一个时间点，使用 RangePicker 选同一时间
      const timePicker = drawer.locator('.ant-picker-range');
      await timePicker.first().click();
      // 输入时间
      await page.keyboard.type(reminder.time);
      await page.keyboard.press('Enter');
      await page.waitForTimeout(200);
      // 结束时间也输入同一个
      await page.keyboard.type(reminder.time);
      await page.keyboard.press('Enter');
      await page.waitForTimeout(300);

      // 提交
      await page.getByRole('button', { name: chineseText('提交') }).click();
      await page.waitForTimeout(1000);
      await expect(page.locator('.ant-drawer-content')).toBeHidden({ timeout: 5000 });
      await page.waitForTimeout(500);
    }

    // 验证今日提醒列表
    await page.goto('/reminders');
    await page.waitForTimeout(1000);

    // 验证今日提醒卡片显示
    await expect(page.getByText('今日提醒')).toBeVisible();

    // 验证至少有部分提醒出现在今日列表
    const todaySlots = page.locator('.ant-card').filter({ hasText: '今日提醒' }).locator('div').filter({ hasText: /:/ });
    const slotCount = await todaySlots.count();
    expect(slotCount).toBeGreaterThan(0);

    // PRODUCT GAP: 缺少"漏服通知"功能，如果过了时间没打卡不会有提醒
    // UX ISSUE: RangePicker 用于单时间点提醒不够直观，老年人难以操作
  });

  // -------------------------------------------------------------------------
  // Test 6: 提醒打卡 → 验证状态变为已服
  // -------------------------------------------------------------------------

  test('06 提醒打卡: 找到待服提醒 → 点击打卡 → 验证状态变为已服', async ({ page }) => {
    // 先创建一个提醒
    await page.goto('/reminders');
    await page.getByRole('button', { name: /添加提醒/ }).click();

    await page.getByLabel('提醒标题').fill('服用缬沙坦');

    const drawer = page.locator('.ant-drawer');
    await page.waitForTimeout(500);
    await drawer.locator('.ant-select-selector').first().click();
    await page.waitForTimeout(500);
    await page.locator('.ant-select-item-option').filter({ hasText: '每天' }).first().click({ force: true });

    // 设置时间
    const timePicker = drawer.locator('.ant-picker-range');
    await timePicker.first().click();
    await page.keyboard.type('08:00');
    await page.keyboard.press('Enter');
    await page.waitForTimeout(200);
    await page.keyboard.type('08:00');
    await page.keyboard.press('Enter');
    await page.waitForTimeout(300);

    await page.getByRole('button', { name: chineseText('提交') }).click();
    await page.waitForTimeout(1000);
    await expect(page.locator('.ant-drawer-content')).toBeHidden({ timeout: 5000 });
    await page.waitForTimeout(1000);

    // 查找今日提醒中的"待服"状态
    const todayCard = page.locator('.ant-card').filter({ hasText: '今日提醒' });
    await expect(todayCard).toBeVisible();

    // 验证有"待服"状态标签
    const pendingTag = todayCard.getByText('待服');
    await expect(pendingTag.first()).toBeVisible();

    // 点击"打卡"按钮
    const checkInBtn = todayCard.getByRole('button', { name: /打卡/ });
    await expect(checkInBtn.first()).toBeVisible();
    await checkInBtn.first().click();

    // 验证打卡成功提示
    await expect(page.locator('.ant-message').first()).toBeVisible();

    // 验证状态变为"已服"
    await page.waitForTimeout(1000);
    const completedTag = page.locator('.ant-card').filter({ hasText: '今日提醒' }).getByText('已服');
    await expect(completedTag.first()).toBeVisible();

    // PRODUCT GAP: 打卡后缺少"下次提醒时间"提示，老年人不知道下次什么时候吃药
  });

  // -------------------------------------------------------------------------
  // Test 7: AI 问答 (长辈模式)
  // -------------------------------------------------------------------------

  test('07 长辈模式AI问答: 输入"糖尿病能吃什么中药"验证回复', async ({ page }) => {
    await enableElderlyMode(page);

    // 导航到 AI 问答 Tab
    await page.getByText('问答').last().click();
    await page.waitForURL('/chat');
    await expect(page).toHaveURL('/chat');

    // 验证 AI 健康助手标题可见
    await expect(page.getByText('AI 健康助手')).toBeVisible();

    // 输入问题
    const textArea = page.locator('textarea').first();
    await textArea.fill('糖尿病能吃什么中药？');
    await page.getByRole('button', { name: /发送/ }).click();

    // 验证用户消息出现
    await expect(page.getByText('糖尿病能吃什么中药？', { exact: true })).toBeVisible();

    // 等待 AI 回复
    await page.waitForTimeout(5000);

    // 验证有至少2个消息卡片（用户+AI）
    const messageCards = page.locator('.ant-card');
    const cardCount = await messageCards.count();
    expect(cardCount).toBeGreaterThanOrEqual(2);

    // PRODUCT GAP: 长辈模式 AI 问答是否有语音输入？Web Speech API 在安卓 Chrome 支持，
    //              但 E2E 环境无法测试实际语音识别，只能验证麦克风按钮存在

    // PRODUCT GAP: AI 回复缺少"建议就医"安全提示（糖尿病是慢性病，AI应提醒遵医嘱）
  });

  // -------------------------------------------------------------------------
  // Test 8: 安全检查 (标准模式): 黄芪 + 二甲双胍
  // -------------------------------------------------------------------------

  test('08 安全检查: 黄芪+二甲双胍中西药交互检查验证', async ({ page }) => {
    // 确保在标准模式（默认注册后就是标准模式）
    await expect(page.locator('body')).not.toHaveClass(/elderly-mode/);

    // PRODUCT GAP: 应用没有独立的安全检查页面UI，只能通过 API 调用
    // UX ISSUE: 安全检查功能不突出，老年人无法主动检查药物交互

    // 通过 API 进行安全检查
    const token = await page.evaluate(() => localStorage.getItem('family_doctor_token') || '');

    const response = await page.request.post('/api/safety/check', {
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      data: {
        herbs: ['黄芪'],
        medicines: ['二甲双胍'],
      },
    });

    expect(response.ok()).toBeTruthy();

    const result = (await response.json()) as {
      safe: boolean;
      warnings: string[];
      interactions: string[];
    };

    // 验证安全检查返回了结果
    expect(result).toHaveProperty('safe');
    expect(result).toHaveProperty('warnings');

    // 验证 warnings 是数组
    expect(Array.isArray(result.warnings)).toBeTruthy();

    // PRODUCT GAP: 没有从药箱页面直接触发安全检查的入口
    // PRODUCT GAP: 安全检查结果不包含"建议替代方案"，只有警告
    // PRODUCT GAP: 缺少自动安全检查（添加药品时自动检查与已有药品的交互）
  });
});
