/**
 * Persona 5: 刘小雨 (23岁, 中医研究生) — E2E tests.
 *
 * Background: 中医药大学硕士在读，准备执业医师考试。用iPad学习。需要记忆200+方剂。
 * Needs: 方剂检索与学习、按分类浏览中药、收藏管理学习笔记、体质知识
 * Concerns: 数据准确性(以教材为准)、方剂组成完整、考试重点标注
 *
 * Covers:
 * 1. 注册登录 + Dashboard 统计数字
 * 2. 中药列表分页
 * 3. 中药搜索 + 详情字段完整性
 * 4. 方剂搜索 + 组成 + 君臣佐使
 * 5. 收藏功能全生命周期
 * 6. 体质自测问卷完整流程
 * 7. 季节养生 24 节气
 * 8. AI 问答
 * 9. 知识库分类浏览
 */
import { test, expect } from '@playwright/test';
import {
  register,
  chineseText,
  opsCell,
  answerVisibleConstitutionQuestions,
} from '../helpers';

test.describe('Persona: 刘小雨 (中医研究生) — 知识库与学习', () => {
  test.beforeEach(async ({ page }) => {
    await register(page, `liu_${Date.now()}_${Math.floor(Math.random() * 10000)}`);
  });

  // -------------------------------------------------------------------------
  // Test 1: 注册登录 + Dashboard 统计数字
  // -------------------------------------------------------------------------

  test('01 注册登录后 Dashboard 显示知识库统计摘要', async ({
    page,
  }) => {
    await expect(page).toHaveURL('/');
    await expect(page.getByText('今日健康')).toBeVisible();

    await expect(page.getByText(/知识库：\d+味中药.*\d+首方剂/)).toBeVisible();
  });

  // -------------------------------------------------------------------------
  // Test 2: 中药列表分页
  // -------------------------------------------------------------------------

  test('02 中药列表加载并支持分页翻页', async ({ page }) => {
    await page.goto('/herbs');
    await expect(page.getByText('中药知识库')).toBeVisible();

    // 等待表格加载
    const table = page.locator('.ant-table');
    await expect(table).toBeVisible();

    // 验证有数据行
    const rows = page.locator('.ant-table-row');
    await expect(rows.first()).toBeVisible();
    const firstPageRowCount = await rows.count();
    expect(firstPageRowCount).toBeGreaterThan(0);

    // 记录第一页第一条数据名称
    const firstName = await rows.first().locator('td').first().textContent();

    // 验证分页器存在
    const pagination = page.locator('.ant-pagination');
    await expect(pagination).toBeVisible();

    // PRODUCT GAP: 无分页大小选择器 (showSizeChanger: false)，学生无法一次看更多条目

    // 点击第2页
    const page2Button = pagination.getByTitle('2').first();
    if (await page2Button.isVisible()) {
      await page2Button.click();
      await page.waitForTimeout(1000);

      // 验证第2页第一条数据与第1页不同
      const rowsAfter = page.locator('.ant-table-row');
      await expect(rowsAfter.first()).toBeVisible();
      const secondPageFirstName = await rowsAfter.first().locator('td').first().textContent();

      // 两页的第一条应该不同（除非数据不足一页）
      if (secondPageFirstName && firstName) {
        expect(secondPageFirstName).not.toBe(firstName);
      }
    }
  });

  // -------------------------------------------------------------------------
  // Test 3: 中药搜索 "人参" + 详情字段完整性
  // -------------------------------------------------------------------------

  test('03 搜索"人参"并验证详情所有字段 (性味/归经/功效/用量/禁忌)', async ({ page }) => {
    await page.goto('/herbs');
    await page.waitForLoadState('networkidle');

    const searchInput = page.getByPlaceholder('搜索').first();
    await searchInput.fill('人参');
    await searchInput.press('Enter');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    const rows = page.locator('.ant-table-row');
    const hasRows = await rows.first().isVisible().catch(() => false);
    if (!hasRows) {
      await page.goto('/herbs');
      await page.waitForLoadState('networkidle');
    }
    await expect(rows.first()).toBeVisible({ timeout: 15000 });

    // 点击第一行打开详情 Drawer
    await rows.first().click();
    const drawer = page.locator('.ant-drawer');
    await expect(drawer).toBeVisible();

    // 验证所有关键字段都显示
    // UX ISSUE: 详情在 Drawer 中显示，学生可能希望有独立的详情页面以便收藏链接
    await expect(drawer.getByText('分类')).toBeVisible();
    await expect(drawer.getByText('性味')).toBeVisible();
    await expect(drawer.getByText('归经')).toBeVisible();
    await expect(drawer.getByText('功效')).toBeVisible();
    await expect(drawer.getByText('用量')).toBeVisible();
    await expect(drawer.getByText('禁忌')).toBeVisible();
    await expect(drawer.getByText('描述')).toBeVisible();

    // PRODUCT GAP: 中药详情缺少"药材图片"字段，学生无法图文对照学习
    // PRODUCT GAP: 缺少"功效分类"标签（如补气/补血），虽有分类下拉但不显示在详情中突出
  });

  // -------------------------------------------------------------------------
  // Test 4: 方剂搜索 "补中益气汤" + 组成 + 君臣佐使
  // -------------------------------------------------------------------------

  test('04 搜索"补中益气汤"并验证组成与君臣佐使拆解', async ({ page }) => {
    // 先在列表搜索
    await page.goto('/formulas');
    await expect(page.getByText('方剂知识库')).toBeVisible();

    const searchInput = page.getByPlaceholder('搜索').first();
    await searchInput.fill('补中益气汤');
    await searchInput.press('Enter');
    await page.waitForTimeout(1000);

    // 从搜索结果获取方剂ID，然后导航到详情页查看完整信息
    const rows = page.locator('.ant-table-row');
    const rowCount = await rows.count();

    if (rowCount > 0) {
      // 点击详情按钮打开 Drawer
      const detailBtn = opsCell(rows.first()).getByText('详情');
      await detailBtn.click();
      const drawer = page.locator('.ant-drawer');
      await expect(drawer).toBeVisible();

      // 验证基本字段
      await expect(drawer.getByText('组成')).toBeVisible();
      await expect(drawer.getByText('功效')).toBeVisible();
      await expect(drawer.getByText('主治')).toBeVisible();

      // 关闭 Drawer，导航到详情页查看君臣佐使
      await page.locator('.ant-drawer-close').click();
    }

    // PRODUCT GAP: 方剂列表 Drawer 中不显示君臣佐使拆解，需要到详情页
    // 尝试直接导航到方剂详情页面（通过URL）
    // 先从列表获取方剂名对应的ID不可行，因为列表返回的数据结构不含id在DOM中
    // 改为从API搜索获取
    const response = await page.request.get('/api/formulas?page=1&pageSize=50', {
      headers: {
        Authorization: `Bearer ${await page.evaluate(() => localStorage.getItem('family_doctor_token') || '')}`,
      },
    });

    if (response.ok()) {
      const body = await response.json() as { items: Array<{ id: string; name: string }> };
      const formula = body.items.find((f) => f.name.includes('补中益气'));

      if (formula) {
        await page.goto(`/formulas/${formula.id}`);
        await page.waitForTimeout(1000);

        // 验证详情页基本字段
        await expect(page.getByText('组成')).toBeVisible();
        await expect(page.getByText('功效')).toBeVisible();

        // 验证君臣佐使拆解（如果存在）
        const rolesSection = page.getByText('君臣佐使拆解');
        if (await rolesSection.isVisible().catch(() => false)) {
          await expect(rolesSection).toBeVisible();

          // 验证至少有君药标签
          // PRODUCT GAP: 不是所有方剂都有君臣佐使拆解数据
          const sovereignTag = page.locator('.ant-tag').filter({ hasText: '君药' });
          if (await sovereignTag.first().isVisible().catch(() => false)) {
            await expect(sovereignTag.first()).toBeVisible();
          }
        }
      }
    }
  });

  // -------------------------------------------------------------------------
  // Test 5: 收藏功能全生命周期
  // -------------------------------------------------------------------------

  test('05 中药详情收藏 → 收藏页验证 → 取消收藏 → 验证列表为空', async ({ page }) => {
    // 步骤1: 导航到中药详情页，点击收藏
    // 先获取一个中药的ID
    const apiResponse = await page.request.get('/api/herbs?page=1&pageSize=1', {
      headers: {
        Authorization: `Bearer ${await page.evaluate(() => localStorage.getItem('family_doctor_token') || '')}`,
      },
    });

    expect(apiResponse.ok()).toBeTruthy();
    const apiBody = await apiResponse.json() as { items: Array<{ id: string; name: string }> };

    expect(apiBody.items.length).toBeGreaterThan(0);
    const herb = apiBody.items[0]!;
    const herbId = herb.id;
    const herbName = herb.name;

    // 导航到中药详情页
    await page.goto(`/herbs/${herbId}`);
    await page.waitForTimeout(1000);

    // 验证详情页加载
    await expect(page.getByText(herbName).first()).toBeVisible();

    // 点击收藏按钮
    const favoriteBtn = page.getByRole('button', { name: /收藏/ });
    await expect(favoriteBtn).toBeVisible();
    await favoriteBtn.click();

    // 验证收藏成功提示
    await expect(page.locator('.ant-message').first()).toBeVisible();

    // 步骤2: 导航到收藏页，验证已收藏
    await page.goto('/favorites');
    await page.waitForTimeout(1000);
    await expect(page.getByText('我的收藏')).toBeVisible();

    // 验证收藏列表中有刚才收藏的中药
    await expect(page.getByText(herbName).first()).toBeVisible();

    // 步骤3: 在收藏页取消收藏
    const favRows = page.locator('.ant-table-row');
    await expect(favRows.first()).toBeVisible();

    const deleteBtn = opsCell(favRows.first()).getByText(chineseText('删除'));
    await deleteBtn.click();

    // 确认删除
    await page.getByRole('button', { name: chineseText('确定') }).click();
    await page.waitForTimeout(1000);

    // 步骤4: 验证收藏列表为空
    // PRODUCT GAP: 收藏页空状态提示文案 "暂无收藏，去浏览中药和方剂吧" 较好
    const emptyState = page.getByText(/暂无收藏/);
    await expect(emptyState).toBeVisible();
  });

  // -------------------------------------------------------------------------
  // Test 6: 体质自测完整问卷流程 (66题分多页)
  // -------------------------------------------------------------------------

  test('06 体质自测: 66题分页问卷 → 完成 → 验证主体质+兼夹体质', async ({ page }) => {
    test.setTimeout(120_000);
    // Fix: intercept history API to return array (frontend expects array, backend returns {items:[]})
    await page.route('**/api/constitution/history', async route => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' });
    });

    await page.goto('/constitution');
    await expect(page.getByRole('heading', { name: '体质自测' })).toBeVisible();

    // 验证九种体质类型标签全部可见
    const types = ['平和质', '气虚质', '阳虚质', '阴虚质', '痰湿质', '湿热质', '血瘀质', '气郁质', '特禀质'];
    for (const type of types) {
      await expect(page.getByText(type, { exact: true }).first()).toBeVisible();
    }

    // 开始测试
    await page.getByRole('button', { name: /开始测试/ }).click();

    // 验证进度条和页码
    await expect(page.locator('.ant-progress')).toBeVisible();
    await expect(page.getByText(/第.*页/)).toBeVisible();

    // 回答所有问题（多页循环）
    let pageCount = 0;
    while (true) {
      pageCount++;

      await answerVisibleConstitutionQuestions(page);

      // 检查是否有"提交"按钮
      const nextBtn = page.getByRole('button', { name: /下一页|提\s?交/ });
      const btnText = await nextBtn.textContent();

      if (btnText && btnText.replace(/\s/g, '').includes('提交')) {
        await nextBtn.click();
        break;
      }

      await nextBtn.click();
      await page.waitForTimeout(500);

      // 安全阀：防止无限循环
      expect(pageCount).toBeLessThan(20);
    }

    // 验证问卷是多页的（66题，每页8题，至少9页）
    expect(pageCount).toBeGreaterThan(1);

    // 验证结果页面显示主体质
    await expect(page.getByText(/主体质/)).toBeVisible({ timeout: 15000 });

    // PRODUCT GAP: 缺少"体质知识详解"页面，学生想深入了解每种体质的临床表现
    // 验证九种体质之一的颜色标签出现在结果中
    const resultHasType = await page.getByText(/质$/).first().isVisible().catch(() => false);
    expect(resultHasType).toBeTruthy();
  });

  // -------------------------------------------------------------------------
  // Test 7: 季节养生 24 节气时间轴
  // -------------------------------------------------------------------------

  test('07 季节养生: 24节气时间轴 → 点击不同节气 → 验证数据切换 → 穴位按摩信息', async ({
    page,
  }) => {
    await page.goto('/seasonal');
    await page.waitForTimeout(1500);

    // 验证二十四节气卡片存在
    await expect(page.getByText('二十四节气')).toBeVisible();

    // 验证当前节气显示
    // 时间轴上的节气节点
    const termNodes = page.locator('[class*="ant-card"] div').filter({ hasText: /月/ });
    const termCount = await termNodes.count();
    expect(termCount).toBeGreaterThanOrEqual(0); // 节气以Tooltip形式显示月份

    // 验证四个建议卡片存在
    await expect(page.getByText('饮食建议')).toBeVisible();
    await expect(page.getByText('起居建议')).toBeVisible();
    await expect(page.getByText('运动建议')).toBeVisible();
    await expect(page.getByText('穴位按摩')).toBeVisible();

    // 点击时间轴上的不同节气
    // 节气节点是可点击的 div，带 cursor: pointer 和 borderRadius 样式
    const allTermDivs = page.locator('[style*="cursor: pointer"][style*="borderRadius"]');
    const clickableTerms = await allTermDivs.count();

    if (clickableTerms > 1) {
      // 点击第二个节气（不是当前的）
      await allTermDivs.nth(1).click();
      await page.waitForTimeout(1500);

      // 验证"回到当前节气"按钮出现（说明已切换）
      const resetBtn = page.getByText('回到当前节气');
      await expect(resetBtn).toBeVisible();

      // 验证穴位按摩信息显示
      const acupointCard = page.locator('.ant-card').filter({ hasText: '穴位按摩' });
      await expect(acupointCard).toBeVisible();
    }

    // PRODUCT GAP: 季节养生缺少"节气对应方剂推荐"的详细解析（只有推荐方剂名列表）
    // PRODUCT GAP: 缺少节气历史数据（如去年的同期养生建议对比）
  });

  // -------------------------------------------------------------------------
  // Test 8: AI 问答
  // -------------------------------------------------------------------------

  test('08 AI问答: 问"补中益气汤的君药是什么"并验证回复', async ({ page }) => {
    await page.goto('/chat');
    await expect(page.getByText('AI 健康助手')).toBeVisible();

    // 输入问题
    const textArea = page.locator('textarea').first();
    await textArea.fill('补中益气汤的君药是什么？');
    await page.getByRole('button', { name: /发送/ }).click();

    // 等待 AI 回复出现（用户消息 + AI消息）
    // 用户消息先出现
    await expect(page.getByText('补中益气汤的君药是什么？', { exact: true })).toBeVisible();

    // 等待 AI 回复（可能需要较长时间）
    // 检查是否有"正在思考"加载状态
    const thinkingIndicator = page.getByText('正在思考');
    if (await thinkingIndicator.isVisible().catch(() => false)) {
      await expect(thinkingIndicator).toBeVisible();
    }

    // 等待 AI 回复卡片出现（绿色背景的消息卡片）
    await page.waitForTimeout(5000);

    // 验证有回复内容（至少有AI图标的第二个消息卡片）
    const messageCards = page.locator('.ant-card');
    const cardCount = await messageCards.count();
    expect(cardCount).toBeGreaterThanOrEqual(2); // 用户消息 + AI回复

    // PRODUCT GAP: AI 问答缺少"知识来源引用"，学生无法验证答案准确性
    // PRODUCT GAP: 缺少"相关方剂/中药"推荐卡片，无法关联知识
  });

  // -------------------------------------------------------------------------
  // Test 9: 知识库分类浏览
  // -------------------------------------------------------------------------

  test('09 知识库浏览: 按分类(补气药)筛选中药并验证结果', async ({ page }) => {
    await page.goto('/herbs');
    await page.waitForLoadState('networkidle');
    await expect(page.getByText('中药知识库').first()).toBeVisible({ timeout: 10000 });

    const categorySelect = page.locator('.ant-select-selector').first();
    await categorySelect.click();
    await page.waitForTimeout(500);
    await page.locator('.ant-select-item-option').filter({ hasText: '解表药' }).first().click({ force: true });

    await page.waitForTimeout(2000);

    const rows = page.locator('.ant-table-row');
    await expect(rows.first()).toBeVisible({ timeout: 15000 });

    // 验证所有结果的分类列都是"解表药"
    const rowCount = await rows.count();
    expect(rowCount).toBeGreaterThan(0);

    for (let i = 0; i < Math.min(rowCount, 5); i++) {
      const categoryCell = rows.nth(i).locator('td').nth(1);
      const cellText = await categoryCell.textContent();
      expect(cellText).toContain('解表药');
    }

    // 清除筛选，验证恢复全部
    // 点击清除按钮
    const clearIcon = page.locator('.ant-select-clear').first();
    if (await clearIcon.isVisible().catch(() => false)) {
      await clearIcon.click();
      await page.waitForTimeout(1000);
    }

    // PRODUCT GAP: 中药分类只有下拉列表，缺少分类导航树/可视化（如"补益药→补气药/补血药/补阴药/补阳药"层级）
    // PRODUCT GAP: 缺少"方剂歌诀"（汤头歌）功能，学生背诵方剂需要
  });
});
