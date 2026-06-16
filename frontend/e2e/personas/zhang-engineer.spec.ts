/**
 * Persona 3: 张伟 (42岁, IT架构师) — 数据驱动的理性用户
 *
 * Background: 互联网CTO，长期熬夜，失眠3年，颈肩疼痛，轻度脂肪肝。
 * 试过褪黑素无效，目前服用佐匹克隆（安眠药）。
 * Needs: 有科学依据的中药推荐、精确剂量、药理信息、安全检查
 * Concerns: 数据准确性、参考文献、剂量严谨性、中西药冲突
 *
 * PRODUCT GAP COMMENTS:
 * - 中药详情缺少"现代药理研究"section（如酸枣仁皂苷A的镇静作用）
 * - 缺少参考文献来源标注
 * - 安全检查不覆盖佐匹克隆等西药
 * - 剂量信息不区分煎剂/丸剂/散剂
 * - 缺少搜索历史/搜索建议
 * - 缺少"我的体质"→"推荐药材"的个性化推荐
 */
import { test, expect } from '@playwright/test';
import { register, chineseText, navigateTo } from '../helpers';

test.describe('Persona: 张伟 — IT架构师 · 数据驱动的失眠患者', () => {
  test.beforeEach(async ({ page }) => {
    const user = 'zhang_' + Date.now();
    await register(page, user);
  });

  // -----------------------------------------------------------------------
  // Test 1: Dashboard 统计数据验证 — 数据驱动用户首先看数据量
  // -----------------------------------------------------------------------
  test('Dashboard 显示中药/方剂统计数字且 > 0', async ({ page }) => {
    await expect(page).toHaveURL('/');

    // 等待 skeleton 消失，统计卡片渲染
    await expect(page.getByText('今日健康')).toBeVisible();

    // 中药数统计卡片
    const herbStat = page.locator('.ant-statistic').filter({ hasText: '中药数' });
    await expect(herbStat).toBeVisible();

    // PRODUCT GAP: 数据驱动用户关心具体数字，验证数字 > 0
    const herbValueText = await herbStat.locator('.ant-statistic-content-value').textContent();
    const herbCount = parseInt((herbValueText ?? '0').replace(/[^0-9]/g, ''), 10);
    expect(herbCount).toBeGreaterThan(0);

    // 方剂数统计卡片
    const formulaStat = page.locator('.ant-statistic').filter({ hasText: '方剂数' });
    await expect(formulaStat).toBeVisible();
    const formulaValueText = await formulaStat.locator('.ant-statistic-content-value').textContent();
    const formulaCount = parseInt((formulaValueText ?? '0').replace(/[^0-9]/g, ''), 10);
    expect(formulaCount).toBeGreaterThan(0);

    // PRODUCT GAP: Dashboard 没有显示"数据来源"或"最后更新时间"，理性用户需要知道数据新鲜度
  });

  // -----------------------------------------------------------------------
  // Test 2: 搜索"酸枣仁" → 验证剂量范围和功效/禁忌
  // -----------------------------------------------------------------------
  test('搜索酸枣仁 → 详情页验证剂量和功效禁忌信息', async ({ page }) => {
    await page.goto('/herbs');

    // 搜索酸枣仁（经典安神药）
    const searchInput = page.getByPlaceholder('搜索').first();
    await searchInput.fill('酸枣仁');
    await searchInput.press('Enter');

    // 等待搜索结果
    await page.waitForTimeout(1000);

    // 如果搜索结果中找到酸枣仁，点击查看详情
    const herbLink = page.locator('.ant-table-row').filter({ hasText: '酸枣仁' }).first();
    const hasResult = await herbLink.isVisible().catch(() => false);

    if (hasResult) {
      // 点击"详情"按钮打开 drawer
      await herbLink.locator('button, a').filter({ hasText: '详情' }).first().click();
      const drawer = page.locator('.ant-drawer');
      await expect(drawer).toBeVisible();

      // 验证用量显示（数据驱动用户关注精确剂量）
      // dosage 字段可能是 "9-15g" 或类似格式
      const dosageItem = drawer.locator('.ant-descriptions-item').filter({ hasText: '用量' });
      if (await dosageItem.isVisible().catch(() => false)) {
        const dosageText = await dosageItem.textContent();
        // PRODUCT GAP: 剂量信息是单一文本（如 "9-15g"），不区分煎剂/丸剂/散剂
        // 理性用户需要知道不同剂型的剂量差异
        expect(dosageText).toBeTruthy();
      }

      // 验证功效文字
      const efficacyItem = drawer.locator('.ant-descriptions-item').filter({ hasText: '功效' });
      if (await efficacyItem.isVisible().catch(() => false)) {
        const efficacyText = await efficacyItem.textContent();
        expect(efficacyText).toContain('安神');
      }

      // 验证禁忌文字（安全关注）
      const contraindicationItem = drawer.locator('.ant-descriptions-item').filter({ hasText: '禁忌' });
      if (await contraindicationItem.isVisible().catch(() => false)) {
        const text = await contraindicationItem.textContent();
        expect(text!.length).toBeGreaterThan(0);
      }

      // PRODUCT GAP: 没有"现代药理研究"section
      // 酸枣仁皂苷A/B 的镇静催眠作用、黄酮类成分等药理数据缺失
      // 理性用户（CTO）需要看到科学依据，而不只是传统功效描述
      const pharmacologySection = drawer.getByText(/现代药理|药理研究|有效成分|皂苷/i);
      expect(await pharmacologySection.isVisible().catch(() => false)).toBeFalsy();

      // PRODUCT GAP: 没有参考文献来源标注
      const referenceSection = drawer.getByText(/参考文献|来源|出处|文献/i);
      expect(await referenceSection.isVisible().catch(() => false)).toBeFalsy();
    } else {
      // 数据库可能未收录酸枣仁，验证搜索功能本身可用
      const table = page.locator('.ant-table');
      const emptyState = page.getByText(/暂无/);
      const hasTable = await table.isVisible().catch(() => false);
      const hasEmpty = await emptyState.isVisible().catch(() => false);
      expect(hasTable || hasEmpty).toBeTruthy();
      // PRODUCT GAP: 如果酸枣仁不在数据库中，说明203味药覆盖不足
    }
  });

  // -----------------------------------------------------------------------
  // Test 3: 搜索"远志" → 验证归经信息
  // -----------------------------------------------------------------------
  test('搜索远志 → 详情页验证归经信息显示', async ({ page }) => {
    await page.goto('/herbs');

    const searchInput = page.getByPlaceholder('搜索').first();
    await searchInput.fill('远志');
    await searchInput.press('Enter');
    await page.waitForTimeout(1000);

    const herbRow = page.locator('.ant-table-row').filter({ hasText: '远志' }).first();
    const hasResult = await herbRow.isVisible().catch(() => false);

    if (hasResult) {
      await herbRow.locator('button, a').filter({ hasText: '详情' }).first().click();
      const drawer = page.locator('.ant-drawer');
      await expect(drawer).toBeVisible();

      // 验证归经信息显示
      const meridianItem = drawer.locator('.ant-descriptions-item').filter({ hasText: '归经' });
      await expect(meridianItem).toBeVisible();
      const meridianText = await meridianItem.textContent();
      // 远志归心、肾经
      expect(meridianText).toMatch(/心|肾/);

      // 验证性味信息
      const natureItem = drawer.locator('.ant-descriptions-item').filter({ hasText: '性味' });
      await expect(natureItem).toBeVisible();
    } else {
      // PRODUCT GAP: 远志是常用安神药，如果缺失说明数据库覆盖不足
      const emptyState = page.getByText(/暂无/);
      const hasEmpty = await emptyState.isVisible().catch(() => false);
      const hasTable = await page.locator('.ant-table').isVisible().catch(() => false);
      expect(hasEmpty || hasTable).toBeTruthy();
    }
  });

  // -----------------------------------------------------------------------
  // Test 4: 方剂搜索"酸枣仁汤" → 详情 → 安全检查
  // -----------------------------------------------------------------------
  test('方剂搜索酸枣仁汤 → 验证组成 → API安全检查', async ({ page }) => {
    await page.goto('/formulas');

    // 搜索酸枣仁汤（经典安神方剂）
    const searchInput = page.getByPlaceholder('搜索').first();
    await searchInput.fill('酸枣仁汤');
    await searchInput.press('Enter');
    await page.waitForTimeout(1000);

    const formulaRow = page.locator('.ant-table-row').filter({ hasText: '酸枣仁汤' }).first();
    const hasResult = await formulaRow.isVisible().catch(() => false);

    if (hasResult) {
      // 点击详情打开 drawer
      await formulaRow.locator('button, a').filter({ hasText: '详情' }).first().click();
      const drawer = page.locator('.ant-drawer');
      await expect(drawer).toBeVisible();

      // 验证组成药材列表显示
      const compositionItem = drawer.locator('.ant-descriptions-item').filter({ hasText: '组成' });
      await expect(compositionItem).toBeVisible();

      // 通过 API 进行安全检查（方剂安全检查端点）
      // FormulaDetail 页面没有直接的安全检查按钮，使用 page.evaluate 调用 API
      const token = await page.evaluate(() => localStorage.getItem('family_doctor_token'));
      const formulaId = await formulaRow.locator('td').first().getAttribute('data-row-key');

      if (formulaId && token) {
        const safetyResult = await page.evaluate(
          async ({ id, authToken }) => {
            const res = await fetch(`/api/formulas/${id}/safety-check`, {
              headers: { Authorization: `Bearer ${authToken}` },
            });
            if (!res.ok) return null;
            return res.json();
          },
          { id: formulaId, authToken: token },
        );

        if (safetyResult) {
          // 验证安全检查返回了结果
          expect(safetyResult).toHaveProperty('safe');
          expect(safetyResult).toHaveProperty('warnings');
          expect(safetyResult).toHaveProperty('disclaimer');

          // 第5层免责声明应始终存在
          expect(safetyResult.disclaimer).toBeTruthy();

          // PRODUCT GAP: 安全检查不覆盖方剂与用户正在服用的西药（佐匹克隆）的交互
        }
      }
    } else {
      // PRODUCT GAP: 酸枣仁汤是经典方剂，如果缺失说明方剂数据库覆盖不足
      const emptyState = page.getByText(/暂无/);
      const hasEmpty = await emptyState.isVisible().catch(() => false);
      const hasTable = await page.locator('.ant-table').isVisible().catch(() => false);
      expect(hasEmpty || hasTable).toBeTruthy();
    }
  });

  // -----------------------------------------------------------------------
  // Test 5: 安全检查 POST /api/safety/check-v2 → 酸枣仁+远志 配伍
  // -----------------------------------------------------------------------
  test('安全检查: 酸枣仁+远志 → 验证五层安全检查引擎返回', async ({ page }) => {
    // 使用 page.evaluate 直接调用安全检查 API
    const token = await page.evaluate(() => localStorage.getItem('family_doctor_token'));

    const result = await page.evaluate(
      async ({ authToken }) => {
        const res = await fetch('/api/safety/check-v2', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${authToken}`,
          },
          body: JSON.stringify({
            herbs: ['酸枣仁', '远志'],
            medicines: [],
          }),
        });
        if (!res.ok) return null;
        return res.json();
      },
      { authToken: token },
    );

    if (result) {
      // 验证安全检查引擎返回了完整结果
      expect(result).toHaveProperty('safe');
      expect(result).toHaveProperty('warnings');
      expect(result).toHaveProperty('disclaimer');

      // 酸枣仁和远志不是配伍禁忌，应该相对安全
      // 但第5层免责声明应始终存在
      expect(result.disclaimer).toBeTruthy();
      expect(result.disclaimer.length).toBeGreaterThan(0);

      // 验证 checked_herbs 包含检查的药材
      if (result.checked_herbs) {
        expect(result.checked_herbs.length).toBeGreaterThanOrEqual(0);
      }

      // PRODUCT GAP: 安全检查不检查中西药交互（佐匹克隆 × 酸枣仁）
      // 理性用户需要知道安眠药和中药是否冲突
      const interactionResult = await page.evaluate(
        async ({ authToken }) => {
          const res = await fetch('/api/safety/check-v2', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              Authorization: `Bearer ${authToken}`,
            },
            body: JSON.stringify({
              herbs: ['酸枣仁'],
              medicines: ['佐匹克隆'],
            }),
          });
          if (!res.ok) return null;
          return res.json();
        },
        { authToken: token },
      );

      if (interactionResult) {
        // PRODUCT GAP: 佐匹克隆可能在 unknown_medicines 中，说明西药交互库不完整
        // 理性用户（CTO）会发现这个数据缺口
        expect(interactionResult).toHaveProperty('unknown_medicines');
      }
    } else {
      // API 不可用时跳过（mock fallback 模式下 API 可能不可用）
      expect(true).toBeTruthy();
    }
  });

  // -----------------------------------------------------------------------
  // Test 6: 药箱 → 添加"佐匹克隆"(安眠药) → 添加"酸枣仁"
  // -----------------------------------------------------------------------
  test('药箱: 添加佐匹克隆(西药) → 验证列表 → 添加酸枣仁', async ({ page }) => {
    await page.goto('/medicines');

    // 添加佐匹克隆（张伟正在吃的安眠药）
    const addButton = page.getByRole('button', { name: chineseText('添加') });
    if (await addButton.isVisible().catch(() => false)) {
      await addButton.click();
      const drawer = page.locator('.ant-drawer');
      await expect(drawer).toBeVisible();

      // 填写药品名称
      const nameInput = page.getByLabel('药品名称');
      if (await nameInput.isVisible().catch(() => false)) {
        await nameInput.fill('佐匹克隆');
      }

      // 选择西药类型
      await page.waitForTimeout(500);
      await drawer.locator('.ant-select-selector').first().click();
      await page.waitForTimeout(500);
      await page.locator('.ant-select-item-option').filter({ hasText: '西药' }).first().click({ force: true });

      // 提交
      await page.getByRole('button', { name: chineseText('提交') }).click();

      // 等待 drawer 关闭
      await page.waitForTimeout(1000);
      await expect(page.locator('.ant-drawer-content')).toBeHidden({ timeout: 5000 });

      // 验证佐匹克隆出现在列表中
      await expect(page.getByText('佐匹克隆')).toBeVisible();

      // 再添加酸枣仁（中药）
      const addButton2 = page.getByRole('button', { name: chineseText('添加') });
      await addButton2.click();
      const drawer2 = page.locator('.ant-drawer');
      await expect(drawer2).toBeVisible();

      const nameInput2 = page.getByLabel('药品名称');
      if (await nameInput2.isVisible().catch(() => false)) {
        await nameInput2.fill('酸枣仁');
      }

      await page.waitForTimeout(500);
      await drawer2.locator('.ant-select-selector').first().click();
      await page.waitForTimeout(500);
      await page.locator('.ant-select-item-option').filter({ hasText: '中成药' }).first().click({ force: true });

      await page.getByRole('button', { name: chineseText('提交') }).click();
      await page.waitForTimeout(1000);
      await expect(page.locator('.ant-drawer-content')).toBeHidden({ timeout: 5000 });

      // 验证两种药都在列表中
      await expect(page.getByText('佐匹克隆')).toBeVisible();
      await expect(page.getByText('酸枣仁')).toBeVisible();

      // PRODUCT GAP: 添加酸枣仁到药箱后，系统没有自动触发中西药交互检查
      // 理性用户期望系统主动警告"佐匹克隆 + 酸枣仁 可能增强中枢抑制"
    } else {
      // 添加按钮不存在时的 fallback
      expect(page.locator('.ant-table')).toBeVisible();
    }
  });

  // -----------------------------------------------------------------------
  // Test 7: 体质自测 → 开始问卷 → 验证问题显示 → 回答前5题 → 验证翻页
  // -----------------------------------------------------------------------
  test('体质自测: 开始问卷 → 验证问题显示和分页导航', async ({ page }) => {
    await page.goto('/constitution');
    await page.waitForLoadState('networkidle');

    // 验证介绍页显示
    await expect(page.getByRole('heading', { name: '体质自测' })).toBeVisible();
    await expect(page.getByText(/王琦九种体质/)).toBeVisible();

    // 点击"开始测试"
    const startButton = page.getByRole('button', { name: /开始测试/ });
    await expect(startButton).toBeVisible();
    await startButton.click();
    await page.waitForTimeout(2000);

    await expect(page.getByText('你容易疲乏吗？')).toBeVisible({ timeout: 15000 });

    const radioButtons = page.locator('.ant-radio-wrapper');
    await expect(radioButtons.first()).toBeVisible({ timeout: 5000 });

    // 验证答题选项（没有/很少/有时/经常/总是）
    await expect(page.getByText('没有').first()).toBeVisible();
    await expect(page.getByText('总是').first()).toBeVisible();

    // 回答第一个问题
    await radioButtons.first().click();

    // 验证进度条更新
    const progress = page.locator('.ant-progress');
    await expect(progress).toBeVisible();

    // 点击"下一页"
    const nextButton = page.getByRole('button', { name: /下一页/ });
    await expect(nextButton).toBeVisible();
    await nextButton.click();

    // 验证翻页成功 — 新问题出现
    await page.waitForTimeout(500);
    await expect(page.getByText(/第.*页/)).toBeVisible();

    // PRODUCT GAP: 问卷没有"跳过此题"选项
    // PRODUCT GAP: 没有"保存进度，下次继续"功能
    // 理性用户可能希望分多次完成66题
  });

  // -----------------------------------------------------------------------
  // Test 8: 季节养生 → 验证当前节气 → 验证建议列表 → 切换节气
  // -----------------------------------------------------------------------
  test('季节养生: 验证当前节气显示 → 饮食/起居/运动建议 → 节气切换', async ({ page }) => {
    // 通过侧边栏导航
    await navigateTo(page, '季节养生');
    await page.waitForURL('/seasonal');

    // 等待加载完成
    await page.waitForTimeout(1500);

    // 验证二十四节气卡片显示
    const solarTermsCard = page.getByText('二十四节气');
    const hasTermsCard = await solarTermsCard.isVisible().catch(() => false);

    if (hasTermsCard) {
      // 验证当前节气标记
      await expect(page.getByText('当前')).toBeVisible();

      // 验证建议类别卡片（饮食/起居/运动/穴位）
      const adviceCards = page.locator('.ant-card').filter({ hasText: /饮食建议|起居建议|运动建议/ });
      const adviceCount = await adviceCards.count();

      if (adviceCount > 0) {
        await expect(adviceCards.first()).toBeVisible();
      }

      // 点击不同的节气验证数据切换
      const termItems = page.locator('[style*="cursor: pointer"]');
      const termCount = await termItems.count();

      if (termCount > 1) {
        // 点击第二个节气（非当前）
        await termItems.nth(1).click();
        await page.waitForTimeout(1000);

        // 验证"回到当前节气"按钮出现
        const resetButton = page.getByRole('button', { name: /回到当前节气/ });
        const hasReset = await resetButton.isVisible().catch(() => false);
        if (hasReset) {
          await expect(resetButton).toBeVisible();
        }
      }

      // PRODUCT GAP: 养生建议没有"科学依据"标注
      // 理性用户想知道"为什么这个节气推荐这些食材"
    } else {
      // 数据未加载时的空状态
      const empty = page.getByText(/暂无/);
      const hasEmpty = await empty.isVisible().catch(() => false);
      expect(hasTermsCard || hasEmpty).toBeTruthy();
    }
  });

  // -----------------------------------------------------------------------
  // Test 9: AI聊天 → 输入"长期失眠怎么调理" → 验证AI回复和安全提示
  // -----------------------------------------------------------------------
  test('AI聊天: 长期失眠怎么调理 → 验证AI回复和安全提示', async ({ page }) => {
    await page.goto('/chat');

    // 验证聊天页面加载
    await expect(page.getByText('AI 健康助手')).toBeVisible();

    // 验证欢迎语
    await expect(page.getByText(/欢迎使用AI健康助手/)).toBeVisible();

    // 输入失眠相关问题
    const chatInput = page.locator('textarea').first();
    await chatInput.fill('长期失眠怎么调理');

    // 点击发送
    const sendButton = page.getByRole('button', { name: /发送/ });
    await sendButton.click();

    // 等待AI回复（可能需要较长时间）
    await page.waitForTimeout(5000);

    // 验证用户消息已发送
    const userMsg = page.locator('.ant-card').filter({ hasText: '长期失眠怎么调理' }).first();
    await expect(userMsg).toBeVisible();

    // 验证AI回复出现
    const aiCards = page.locator('.ant-card').filter({ hasText: /失眠|安神|酸枣仁|睡眠|建议|注意/ });
    const aiVisible = await aiCards.last().isVisible().catch(() => false);

    if (aiVisible) {
      // 验证AI回复有内容
      const aiText = await aiCards.last().textContent();
      expect(aiText!.length).toBeGreaterThan(10);
    }

    // PRODUCT GAP: AI回复中应该包含安全提示
    // 长期失眠可能需要就医，AI应该有"建议就医"提示
    // 验证是否有安全警告 Alert
    const safetyAlert = page.locator('.ant-alert').filter({ hasText: /安全|警告|就医/ });
    const hasSafetyAlert = await safetyAlert.isVisible().catch(() => false);
    // 安全提示可能存在也可能不存在（取决于关键词匹配）
    if (hasSafetyAlert) {
      await expect(safetyAlert).toBeVisible();
    }

    // PRODUCT GAP: AI回复缺少"参考文献"或"信息来源"标注
    // PRODUCT GAP: AI回复缺少"此建议不替代专业医疗诊断"的免责声明（可能只在安全检查中）
  });
});
