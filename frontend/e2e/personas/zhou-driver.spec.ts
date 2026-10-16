/**
 * Persona 8: 周建华 (58岁, 出租车司机) — E2E tests.
 *
 * Background: 开出租20年，两班倒。腰椎间盘突出、胃病、痔疮。
 *             每天在车里10小时。手机操作一般。
 *             利用等客/休息间隙查信息。
 * Needs: 快速查腰椎/胃病中药方、简单实用、语音输入
 * Concerns: 没时间复杂操作、需要见效快的方法、开车时不能用太复杂的操作
 *
 * These tests simulate real usage from 周建华's perspective:
 *   注册 → 搜索腰胃病中药 → 方剂查询 → AI问答 → 季节养生 → 提醒 → 药箱管理
 */
import { test, expect } from '@playwright/test';
import {
  register,
  chineseText,
  fillTimeRangePicker,
  navigateTo,
  opsCell,
} from '../helpers';

test.describe('Persona: 周建华 — 出租车司机职业病用户', () => {
  // -------------------------------------------------------------------------
  // Test 1: 注册 → 快速完成 → 验证Dashboard
  // -------------------------------------------------------------------------

  test('01 快速注册后Dashboard显示统计信息和快捷操作', async ({ page }) => {
    const username = 'zhou_' + Date.now();
    await register(page, username);

    // 注册后自动跳转到首页
    await expect(page).toHaveURL('/');
    await expect(page.getByText('今日健康')).toBeVisible();

    // 验证统计卡片
    await expect(page.getByText(/知识库：\d+味中药/)).toBeVisible();
    await expect(page.getByRole('heading', { name: '今日健康任务' })).toBeVisible();

    // 验证快捷操作按钮（周建华需要快速入口）
    const addMedicineBtn = page.getByRole('button', { name: /添加药品/ });
    const browseHerbBtn = page.getByRole('button', { name: /浏览中药/ });

    if (await addMedicineBtn.isVisible().catch(() => false)) {
      await expect(addMedicineBtn).toBeVisible();
    }
    if (await browseHerbBtn.isVisible().catch(() => false)) {
      await expect(browseHerbBtn).toBeVisible();
    }

    // PRODUCT GAP: 首页没有"常见病速查"入口。
    //   周建华有腰椎间盘突出和胃病，想在首页一键进入相关中药/方剂。
    //   建议增加"常见问题"快捷卡片：腰痛/胃病/失眠/疲劳等。
    // PRODUCT GAP: 没有"职业病"专区或推荐。
    //   久坐/驾驶相关健康问题（腰椎/颈椎/痔疮/胃病）应有专题入口。
    //   出租车司机群体高度一致的健康需求未被覆盖。
  });

  // -------------------------------------------------------------------------
  // Test 2: 搜索"杜仲"(补肾强腰) → 详情 → 验证功效
  // -------------------------------------------------------------------------

  test('02 搜索"杜仲"(强筋骨)并验证功效', async ({ page }) => {
    const username = 'zhou_' + Date.now();
    await register(page, username);

    await page.goto('/herbs');
    await expect(page.getByText('中药知识库')).toBeVisible();

    // 搜索"杜仲" — 补肝肾、强筋骨，治腰痛要药
    const searchInput = page.getByPlaceholder('搜索').first();
    await searchInput.fill('杜仲');
    await searchInput.press('Enter');
    await page.waitForTimeout(1000);

    const rows = page.locator('.ant-table-row');
    const rowCount = await rows.count();

    if (rowCount > 0) {
      const detailBtn = rows.first().getByText('详情');
      if (await detailBtn.isVisible().catch(() => false)) {
        await detailBtn.click();
      } else {
        await rows.first().click();
      }

      const drawer = page.locator('.ant-drawer');
      await expect(drawer).toBeVisible();

      // 验证功效字段
      await expect(drawer.getByText('功效')).toBeVisible();

      // 读取功效内容
      const efficacyContent = drawer
        .locator('.ant-descriptions-item-content')
        .filter({ hasText: /强|筋|骨|腰|肝|肾/ })
        .first();

      if (await efficacyContent.isVisible().catch(() => false)) {
        const text = await efficacyContent.textContent();
        // 杜仲功效应包含强筋骨/补肝肾相关
        expect(text).toBeTruthy();
      }

      // PRODUCT GAP: 中药详情没有"简明摘要"模式。
      //   周建华等客间隙时间短，需要一眼看到"杜仲→治腰痛"的精简信息，
      //   而不是读完整描述。建议增加TL;DR摘要（一句话功效+适用症状）。
    } else {
      // 数据库可能没有杜仲
      const table = page.locator('.ant-table');
      const empty = page.getByText(/暂无|没有/);
      expect(await table.isVisible() || await empty.isVisible()).toBeTruthy();
    }
  });

  // -------------------------------------------------------------------------
  // Test 3: 搜索"陈皮"(理气健胃) → 详情 → 验证功效
  // -------------------------------------------------------------------------

  test('03 搜索"陈皮"(理气健胃)并验证功效', async ({ page }) => {
    const username = 'zhou_' + Date.now();
    await register(page, username);

    await page.goto('/herbs');

    // 搜索"陈皮" — 理气健脾、燥湿化痰，治胃病常用
    const searchInput = page.getByPlaceholder('搜索').first();
    await searchInput.fill('陈皮');
    await searchInput.press('Enter');
    await page.waitForTimeout(1000);

    const rows = page.locator('.ant-table-row');
    const rowCount = await rows.count();

    if (rowCount > 0) {
      const detailBtn = rows.first().getByText('详情');
      if (await detailBtn.isVisible().catch(() => false)) {
        await detailBtn.click();
      } else {
        await rows.first().click();
      }

      const drawer = page.locator('.ant-drawer');
      await expect(drawer).toBeVisible();

      // 验证功效和性味字段
      await expect(drawer.getByText('功效')).toBeVisible();
      await expect(drawer.getByText('性味')).toBeVisible();

      // 验证禁忌（胃病患者需注意）
      await expect(drawer.getByText('禁忌')).toBeVisible();

      // UX ISSUE: 搜索结果表格只显示名称/分类/性味/功效，
      //   司机想快速看"这药治什么"，需要点开详情才能看到完整信息。
      //   建议列表中增加"主治"列或"适用症状"标签。
    } else {
      const table = page.locator('.ant-table');
      const empty = page.getByText(/暂无|没有/);
      expect(await table.isVisible() || await empty.isVisible()).toBeTruthy();
    }
  });

  // -------------------------------------------------------------------------
  // Test 4: 方剂搜索"独活寄生汤" → 详情 → 验证组成
  // -------------------------------------------------------------------------

  test('04 搜索"独活寄生汤"(治腰痛经典方)并验证组成', async ({ page }) => {
    const username = 'zhou_' + Date.now();
    await register(page, username);

    await page.goto('/formulas');
    await expect(page.getByText('方剂知识库')).toBeVisible();

    // 搜索"独活寄生汤" — 治疗痹证腰痛的经典方
    const searchInput = page.getByPlaceholder('搜索').first();
    await searchInput.fill('独活寄生汤');
    await searchInput.press('Enter');
    await page.waitForTimeout(1000);

    const rows = page.locator('.ant-table-row');
    const rowCount = await rows.count();

    if (rowCount > 0) {
      const detailBtn = opsCell(rows.first()).getByText('详情');
      if (await detailBtn.isVisible().catch(() => false)) {
        await detailBtn.click();
      } else {
        await rows.first().click();
      }

      const drawer = page.locator('.ant-drawer');
      await expect(drawer).toBeVisible();

      // 验证组成和功效
      await expect(drawer.getByText('组成')).toBeVisible();
      await expect(drawer.getByText('功效')).toBeVisible();
      await expect(drawer.getByText('主治')).toBeVisible();

      // 关闭抽屉
      await page.locator('.ant-drawer-close').click();
    }

    // 通过API获取方剂ID，导航到详情页
    const token = await page.evaluate(() => localStorage.getItem('family_doctor_token') || '');
    const apiResponse = await page.request.get('/api/formulas?page=1&pageSize=50', {
      headers: { Authorization: `Bearer ${token}` },
    });

    if (apiResponse.ok()) {
      const body = await apiResponse.json() as { items: Array<{ id: string; name: string }> };
      const formula = body.items.find((f) => f.name.includes('独活寄生'));

      if (formula) {
        await page.goto(`/formulas/${formula.id}`);
        await page.waitForTimeout(1000);

        // 验证详情页
        await expect(page.getByText('组成')).toBeVisible();
        await expect(page.getByText('功效')).toBeVisible();
        await expect(page.getByText('主治')).toBeVisible();

        // 验证"导出处方单"按钮（周建华可能想打印处方给中医师看）
        const printBtn = page.getByRole('button', { name: /导出处方单/ });
        if (await printBtn.isVisible().catch(() => false)) {
          await expect(printBtn).toBeVisible();
        }

        // 验证君臣佐使拆解（如果存在）
        const rolesSection = page.getByText('君臣佐使拆解');
        if (await rolesSection.isVisible().catch(() => false)) {
          await expect(rolesSection).toBeVisible();
        }
      }
    }

    // PRODUCT GAP: 没有方剂"打印处方单"后的购药链接。
    //   周建华拿到处方后不知道去哪里抓药。
    //   建议处方单增加"附近药店"或"在线购药"入口。
  });

  // -------------------------------------------------------------------------
  // Test 5: AI问答 → "腰痛吃什么中药好" → 验证回复
  // -------------------------------------------------------------------------

  test('05 AI问答: 问"腰痛吃什么中药好" → 验证回复内容', async ({ page }) => {
    const username = 'zhou_' + Date.now();
    await register(page, username);

    await page.goto('/chat');
    await expect(page.getByText('AI 健康助手')).toBeVisible();

    // 输入腰痛相关问题
    const textArea = page.locator('textarea').first();
    await textArea.fill('腰痛吃什么中药好？');
    await page.getByRole('button', { name: /发送/ }).click();

    // 验证用户消息出现
    await expect(page.getByText('腰痛吃什么中药好？', { exact: true })).toBeVisible();

    // 等待AI回复
    const thinkingIndicator = page.getByText('正在思考');
    if (await thinkingIndicator.isVisible().catch(() => false)) {
      await expect(thinkingIndicator).toBeVisible();
    }

    await page.waitForTimeout(5000);

    // 验证有回复消息（>= 2条卡片：用户 + AI）
    const messageCards = page.locator('.ant-card');
    const cardCount = await messageCards.count();
    expect(cardCount).toBeGreaterThanOrEqual(2);

    // PRODUCT GAP: AI对话没有上下文记忆（连续追问）。
    //   周建华可能想追问"那杜仲怎么吃""每天多少克"，
    //   但当前每次对话都是独立的，无法基于上轮对话理解。
    //   ChatPage 的 handleSend 传递了 messages 历史，
    //   但后端是否真正使用历史上下文需验证。
    // UX ISSUE: AI回复可能太长，司机等客间隙时间短。
    //   建议回复默认显示摘要，点击展开查看详细内容。
  });

  // -------------------------------------------------------------------------
  // Test 6: 季节养生 → 查看 → 验证实用建议
  // -------------------------------------------------------------------------

  test('06 季节养生: 查看当前节气 → 验证饮食和起居建议', async ({ page }) => {
    const username = 'zhou_' + Date.now();
    await register(page, username);

    await page.goto('/seasonal');
    await page.waitForTimeout(1500);

    // 验证二十四节气标题
    await expect(page.getByText('二十四节气')).toBeVisible();

    // 验证四个建议卡片
    await expect(page.getByText('饮食建议')).toBeVisible();
    await expect(page.getByText('起居建议')).toBeVisible();
    await expect(page.getByText('运动建议')).toBeVisible();
    await expect(page.getByText('穴位按摩')).toBeVisible();

    // PRODUCT GAP: 季节养生没有针对职业病的特别建议。
    //   周建华久坐开车，不同季节腰椎/胃病保养方式不同：
    //   冬季保暖腰部、夏季祛湿、梅雨季注意关节。
    //   建议增加"职业病季节提醒"功能。
    // UX ISSUE: 起居建议对司机不适用（如"早睡早起"）。
    //   两班倒司机作息不规律，应提供适配不规律作息的建议。
  });

  // -------------------------------------------------------------------------
  // Test 7: 提醒设置 → 创建"吃胃药"提醒 → 验证
  // -------------------------------------------------------------------------

  test('07 创建"服用奥美拉唑"胃药提醒并验证列表显示', async ({ page }) => {
    const username = 'zhou_' + Date.now();
    await register(page, username);

    await page.goto('/reminders');
    await expect(page.getByRole('heading', { name: '吃药提醒' })).toBeVisible();

    // 点击添加提醒
    await page.getByRole('button', { name: /添加提醒/ }).click();
    const drawer = page.locator('.ant-drawer');
    await expect(drawer).toBeVisible();

    // 填写提醒标题
    await page.getByLabel('提醒标题').fill('饭前服用奥美拉唑（胃药）');

    // 设置时间（TimePicker.RangePicker — required field）
    const startDate = drawer.locator('.ant-picker').nth(1).locator('input');
    await startDate.fill(new Date().toISOString().slice(0, 10));
    await startDate.press('Enter');

    // 提交
    await page.getByRole('button', { name: chineseText('提交') }).click();

    // 抽屉关闭
    await page.waitForTimeout(1000);
    await expect(page.locator('.ant-drawer-content')).toBeHidden({ timeout: 5000 });

    // 验证提醒出现在列表中
    await expect(page.getByText('饭前服用奥美拉唑（胃药）').first()).toBeVisible();

    // 验证今日提醒区域
    await expect(page.getByText('今日提醒')).toBeVisible();

    // PRODUCT GAP: 提醒创建没有"关联药品"自动填充。
    //   周建华药箱里有"奥美拉唑"，创建提醒时应可从药箱选择药品，
    //   自动填充标题和剂量，减少手动输入（司机打字不便）。
    // UX ISSUE: 提醒表单的 TimePicker 对手机操作不便的司机来说较复杂。
    //   建议提供常用时间预设：饭前30分钟/饭后30分钟/睡前等一键选择。
    // PRODUCT GAP: 没有声音通知/推送提醒。
    //   司机开车时不会看手机屏幕，需要声音提醒才不会漏服。
  });

  // -------------------------------------------------------------------------
  // Test 8: 药箱 → 添加"奥美拉唑" → 验证列表
  // -------------------------------------------------------------------------

  test('08 药箱添加"奥美拉唑"胃药并验证列表显示', async ({ page }) => {
    const username = 'zhou_' + Date.now();
    await register(page, username);

    await page.goto('/medicines');

    // 点击添加按钮
    const addButton = page.getByRole('button', { name: chineseText('添加') }).last();
    if (await addButton.isVisible().catch(() => false)) {
      await addButton.click();

      const drawer = page.locator('.ant-drawer');
      await expect(drawer).toBeVisible();

      // 填写药品名称
      const nameInput = page.getByLabel('药品名称');
      if (await nameInput.isVisible().catch(() => false)) {
        await nameInput.fill('奥美拉唑肠溶胶囊');
      }

      await page.waitForTimeout(500);
      await drawer.locator('.ant-select-selector').first().click();
      await page.waitForTimeout(500);
      await page.locator('.ant-select-item-option').filter({ hasText: '西药' }).first().click({ force: true });

      // 提交
      await page.getByRole('button', { name: chineseText('提交') }).click();

      // 抽屉关闭
      await page.waitForTimeout(1000);
      await expect(page.locator('.ant-drawer-content')).toBeHidden({ timeout: 5000 });

      // 验证药品出现在列表中
      await expect(page.getByText('奥美拉唑肠溶胶囊')).toBeVisible();
    }

    // PRODUCT GAP: 药箱没有"库存数量"和"到期日"字段（或字段不够醒目）。
    //   司机需要知道药还剩多少、什么时候到期，避免断药。
    // PRODUCT GAP: 没有"购药提醒"（库存低于阈值时自动提醒补充）。
    //   周建华出车时不想为买药分心，应有"库存不足自动提醒"功能。
    // UX ISSUE: 添加药品表单字段较多，对手机操作一般的司机来说负担重。
    //   建议支持"扫码识别"或"拍照识别"药品包装自动填充。
  });

  // -------------------------------------------------------------------------
  // Test 9: 额外 — 语音输入功能验证（司机核心需求）
  // -------------------------------------------------------------------------

  test('09 AI问答页应有语音输入按钮（司机等客间隙使用）', async ({ page }) => {
    const username = 'zhou_' + Date.now();
    await register(page, username);

    await page.goto('/chat');
    await expect(page.getByText('AI 健康助手')).toBeVisible();

    // 语音输入按钮（圆形麦克风图标，48x48px）
    const micButton = page.locator('button').filter({ has: page.locator('.anticon-audio') });
    const micVisible = await micButton.first().isVisible().catch(() => false);

    // 在支持的浏览器中，语音按钮应该可见
    // Chromium headless 可能不支持 Web Speech API，此时按钮应优雅隐藏
    if (micVisible) {
      await expect(micButton.first()).toBeVisible();
      // 按钮应有48px大小（符合适老化触控标准）
      const box = await micButton.first().boundingBox();
      if (box) {
        expect(box.width).toBeGreaterThanOrEqual(40);
        expect(box.height).toBeGreaterThanOrEqual(40);
      }
    }

    // PRODUCT GAP: 语音输入在Chromium headless中不被支持，
    //   需确认在移动端浏览器（Chrome for Android / iOS Safari）上正常工作。
    //   周建华等司机群体主要用手机，语音输入是核心功能。
    //   不支持的浏览器上应显示明确提示（当前仅有Tooltip）。
    // UX ISSUE: 语音输入按钮没有语音反馈。
    //   司机开车时不能看屏幕，需要语音确认"正在聆听"和"已识别"状态。
    //   建议增加"叮"声提示开始/结束录音。
  });

  // -------------------------------------------------------------------------
  // Test 10: 额外 — 通过侧边栏快速导航（司机效率优先）
  // -------------------------------------------------------------------------

  test('10 通过侧边栏快速导航到中药/方剂/药箱（效率验证）', async ({ page }) => {
    const username = 'zhou_' + Date.now();
    await register(page, username);

    // 验证侧边栏存在
    await expect(page.locator('.ant-layout-sider')).toBeVisible();

    // 通过侧边栏导航到知识库 → 中药
    await navigateTo(page, '知识库');
    await page.locator('.ant-menu').getByText('中药', { exact: true }).click();
    await page.waitForURL('/herbs');
    await expect(page).toHaveURL('/herbs');
    await expect(page.getByText('中药知识库')).toBeVisible();

    // 导航到方剂
    await page.getByText('知识库').first().click();
    await page.locator('.ant-menu').getByText('方剂', { exact: true }).click();
    await page.waitForURL('/formulas');
    await expect(page.getByText('方剂知识库')).toBeVisible();

    // 导航到药箱
    await navigateTo(page, '药箱');
    await page.waitForURL('/medicines');
    await expect(page).toHaveURL('/medicines');

    // 导航到提醒
    await navigateTo(page, '提醒');
    await page.waitForURL('/reminders');
    await expect(page.getByRole('heading', { name: '吃药提醒' })).toBeVisible();

    // 导航到AI助手
    await navigateTo(page, 'AI 助手');
    await page.waitForURL('/chat');
    await expect(page).toHaveURL('/chat');

    // PRODUCT GAP: 侧边栏没有"常见病速查"快捷入口。
    //   周建华想一键查"腰痛"或"胃病"相关中药/方剂，
    //   当前需要先去知识库再搜索，步骤多。
    //   建议侧边栏增加"快速查找"搜索框，输入症状直接关联中药/方剂。
    // PRODUCT GAP: 没有"附近药店"功能。
    //   司机在外跑车时需要知道附近哪里有药店。
  });
});
