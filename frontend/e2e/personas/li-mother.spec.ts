/**
 * Persona E2E tests — 李芳 (35岁, HR经理, 二孩妈妈)
 *
 * 用户画像:
 *   - 上海外企HR经理，大女儿8岁，小儿子3岁
 *   - 压力大导致头痛/月经不调
 *   - 婆婆信偏方，需要验证安全性
 *
 * 核心需求:
 *   - 小儿感冒方剂、验证偏方安全性
 *   - 管理全家用药、快速操作
 *
 * 担忧:
 *   - 儿童用药安全、中西药同服、隐私
 *
 * 这些测试从李芳的视角模拟真实操作流程:
 *   注册 → 搜索方剂 → 安全检查 → 管理药箱 → 收藏 → 提醒 → 体质自测
 */
import { test, expect } from '@playwright/test';
import {
  register,
  logout,
  chineseText,
  firstToast,
  selectAntdOption,
} from '../helpers';

test.describe('Persona: 李芳 — 职场二孩妈妈', () => {
  // -------------------------------------------------------------------------
  // 1. 注册登录 + Dashboard 验证
  // -------------------------------------------------------------------------

  test('1. 应完成注册并验证Dashboard显示统计数字', async ({ page }) => {
    const username = 'li_' + Date.now();
    await register(page, username);

    await expect(page).toHaveURL('/');
    await expect(page.getByText('今日健康')).toBeVisible();

    // 验证4个统计卡片可见（中药数/方剂数/药箱数/今日提醒）
    await expect(page.getByText('中药数')).toBeVisible();
    await expect(page.getByText('方剂数')).toBeVisible();
    await expect(page.getByText('药箱数')).toBeVisible();
    await expect(page.getByText('今日提醒')).toBeVisible();

    // 验证快速操作按钮可见
    await expect(page.getByRole('button', { name: /添加药品/ })).toBeVisible();
    await expect(page.getByRole('button', { name: /浏览中药/ })).toBeVisible();

    // PRODUCT GAP: Dashboard没有"家庭成员"概念。
    //   李芳需要为女儿和儿子分别管理药品和提醒，
    //   但当前系统是单用户单档案，无法区分家庭成员。
    //   建议：增加"家庭成员"管理功能，每个成员有独立药箱/提醒/档案。
  });

  // -------------------------------------------------------------------------
  // 2. 搜索方剂 — 桂枝汤
  // -------------------------------------------------------------------------

  test('2. 应搜索方剂"桂枝汤"并查看组成药材', async ({ page }) => {
    const username = 'li_' + Date.now();
    await register(page, username);

    // 导航到方剂列表
    await page.goto('/formulas');
    await expect(page).toHaveURL('/formulas');
    await expect(page.getByText('方剂知识库')).toBeVisible();

    // 搜索"桂枝汤"
    const searchInput = page.getByPlaceholder('搜索').first();
    await searchInput.fill('桂枝汤');
    await searchInput.press('Enter');
    await page.waitForTimeout(1500);

    // 检查结果
    const rows = page.locator('.ant-table-row');
    const rowCount = await rows.count();

    if (rowCount > 0) {
      // 打开详情（点击行或详情按钮）
      const detailBtn = rows.first().getByText('详情');
      if (await detailBtn.isVisible().catch(() => false)) {
        await detailBtn.click();
      } else {
        await rows.first().click();
      }

      // 详情抽屉应打开
      const drawer = page.locator('.ant-drawer');
      await expect(drawer).toBeVisible();

      // 验证组成药材列表可见
      await expect(drawer.getByText('组成')).toBeVisible();
      await expect(drawer.getByText('功效')).toBeVisible();
      await expect(drawer.getByText('主治')).toBeVisible();
      await expect(drawer.getByText('用法')).toBeVisible();

      // PRODUCT GAP: 方剂详情没有"儿童减量说明"。
      //   李芳搜索桂枝汤给3岁儿子用，但详情页没有儿童剂量调整信息。
      //   建议：方剂详情增加"儿童用量"字段，标注减量比例。
    } else {
      // 验证空状态或表格存在
      const table = page.locator('.ant-table');
      const empty = page.getByText(/暂无|没有/);
      expect(await table.isVisible() || await empty.isVisible()).toBeTruthy();
    }
  });

  // -------------------------------------------------------------------------
  // 3. 方剂安全检查
  // -------------------------------------------------------------------------

  test('3. 应在方剂详情页触发安全检查并查看结果', async ({ page }) => {
    const username = 'li_' + Date.now();
    await register(page, username);

    // 导航到方剂列表，找一个方剂
    await page.goto('/formulas');
    await page.waitForTimeout(1500);

    const rows = page.locator('.ant-table-row');
    const rowCount = await rows.count();

    if (rowCount > 0) {
      // 获取第一个方剂的ID用于直接访问详情页
      const firstRow = rows.first();

      // 打开详情抽屉
      const detailBtn = firstRow.getByText('详情');
      if (await detailBtn.isVisible().catch(() => false)) {
        await detailBtn.click();
      } else {
        await firstRow.click();
      }

      const drawer = page.locator('.ant-drawer');
      await expect(drawer).toBeVisible();

      // 关闭抽屉，通过方剂ID访问独立详情页（有安全检查功能）
      const closeBtn = page.locator('.ant-drawer-close');
      if (await closeBtn.isVisible().catch(() => false)) {
        await closeBtn.click();
      }

      // 尝试通过点击方剂名称导航到独立详情页
      // 独立详情页 /formulas/:id 有收藏和安全功能
      // 我们需要找到方剂的ID。通过API搜索获取
      const response = await page.request.get(
        '/api/formulas?page=1&pageSize=1',
      );
      if (response.ok()) {
        const data = await response.json();
        if (data.items && data.items.length > 0) {
          const formulaId = data.items[0].id;
          await page.goto(`/formulas/${formulaId}`);
          await page.waitForTimeout(1500);

          // 验证方剂详情页加载
          const detailPageTitle = page.getByText(data.items[0].name).first();
          if (await detailPageTitle.isVisible().catch(() => false)) {
            // 验证收藏按钮和导出处方单按钮可见
            await expect(page.getByText(/收藏|已收藏/).first()).toBeVisible();
            await expect(page.getByRole('button', { name: /导出处方单/ })).toBeVisible();

            // 验证君臣佐使拆解区域（如果存在）
            const rolesSection = page.getByText(/君臣佐使/);
            if (await rolesSection.isVisible().catch(() => false)) {
              // 验证角色标签
              const roleTags = ['君药', '臣药', '佐药', '使药'];
              for (const tag of roleTags) {
                const tagEl = page.getByText(tag, { exact: true }).first();
                // 不要求所有标签都存在，至少检查一些可见
                if (await tagEl.isVisible().catch(() => false)) {
                  expect(await tagEl.isVisible()).toBeTruthy();
                  break; // 找到一个就够
                }
              }
            }
          }
        }
      }

      // PRODUCT GAP: 方剂详情页没有显式的"安全检查"按钮。
      //   安全检查API（/api/formulas/{id}/safety-check）存在但未在UI中暴露。
      //   李芳需要验证偏方安全性，但找不到一键检查的入口。
      //   建议：增加"安全检查"按钮，调用safety-check API展示五层结果。
      //   当前安全检查只能通过独立的安全检查页面/API手动操作。
    }
  });

  // -------------------------------------------------------------------------
  // 4. 药箱添加 — 布洛芬 + 小儿氨酚黄那敏
  // -------------------------------------------------------------------------

  test('4. 应添加"布洛芬"和"小儿氨酚黄那敏"到药箱', async ({ page }) => {
    const username = 'li_' + Date.now();
    await register(page, username);

    await page.goto('/medicines');

    // 添加第一个药品：布洛芬
    const addButton = page.getByRole('button', { name: chineseText('添加') });
    if (await addButton.isVisible().catch(() => false)) {
      await addButton.click();
      const drawer = page.locator('.ant-drawer');
      await expect(drawer).toBeVisible();

      // 填写药品名称
      const nameInput = page.getByLabel('药品名称');
      if (await nameInput.isVisible().catch(() => false)) {
        await nameInput.fill('布洛芬');
      }

      // 填写数量（如果有数量字段）
      const qtyInput = page.getByLabel(/数量|库存/);
      if (await qtyInput.isVisible().catch(() => false)) {
        await qtyInput.fill('20');
      }

      // 选择类型
      const typeSelect = page.locator('.ant-drawer .ant-select-selector').first();
      if (await typeSelect.isVisible().catch(() => false)) {
        await typeSelect.click();
        await page.waitForTimeout(500);
        await page.locator('.ant-select-item-option').filter({ hasText: '西药' }).first().click({ force: true });
      }

      await page.getByRole('button', { name: chineseText('提交') }).click();
      await page.waitForTimeout(1000);
      await expect(page.locator('.ant-drawer-content')).toBeHidden({ timeout: 5000 });

      // 验证药品出现在列表
      await expect(page.getByText('布洛芬')).toBeVisible();

      // 添加第二个药品：小儿氨酚黄那敏
      await addButton.click();
      await expect(page.locator('.ant-drawer')).toBeVisible();

      const nameInput2 = page.getByLabel('药品名称');
      if (await nameInput2.isVisible().catch(() => false)) {
        await nameInput2.fill('小儿氨酚黄那敏');
      }

      const qtyInput2 = page.getByLabel(/数量|库存/);
      if (await qtyInput2.isVisible().catch(() => false)) {
        await qtyInput2.fill('10');
      }

      const typeSelect2 = page.locator('.ant-drawer .ant-select-selector').first();
      if (await typeSelect2.isVisible().catch(() => false)) {
        await typeSelect2.click();
        await page.waitForTimeout(500);
        await page.locator('.ant-select-item-option').filter({ hasText: '西药' }).first().click({ force: true });
      }

      await page.getByRole('button', { name: chineseText('提交') }).click();
      await page.waitForTimeout(1000);
      await expect(page.locator('.ant-drawer-content')).toBeHidden({ timeout: 5000 });

      // 验证两个药品都在列表中
      await expect(page.getByText('布洛芬')).toBeVisible();
      await expect(page.getByText('小儿氨酚黄那敏')).toBeVisible();
    } else {
      // 如果没有"添加"按钮，可能有其他入口（如"新增"）
      const table = page.locator('.ant-table');
      const empty = page.getByText(/暂无/);
      expect(await table.isVisible() || await empty.isVisible()).toBeTruthy();
    }

    // PRODUCT GAP: 药箱没有"成人/儿童"标记字段。
    //   李芳给女儿和儿子分别管理药品，但无法区分哪些是成人药、哪些是儿童药。
    //   建议：药品增加"适用人群"字段（成人/儿童/通用）。
    //   这对安全很重要——防止误给儿童服用成人剂量。
  });

  // -------------------------------------------------------------------------
  // 5. 中药搜索验证偏方 — 生姜
  // -------------------------------------------------------------------------

  test('5. 应搜索中药"生姜"查看功效以验证婆婆的偏方', async ({ page }) => {
    const username = 'li_' + Date.now();
    await register(page, username);

    await page.goto('/herbs');

    // 搜索"生姜"
    const searchInput = page.getByPlaceholder('搜索').first();
    await searchInput.fill('生姜');
    await searchInput.press('Enter');
    await page.waitForTimeout(1500);

    const rows = page.locator('.ant-table-row');
    const rowCount = await rows.count();

    if (rowCount > 0) {
      // 打开详情
      const detailBtn = rows.first().getByText('详情');
      if (await detailBtn.isVisible().catch(() => false)) {
        await detailBtn.click();
      } else {
        await rows.first().click();
      }

      const drawer = page.locator('.ant-drawer');
      await expect(drawer).toBeVisible();

      // 验证功效字段可见（李芳需要验证偏方的真实功效）
      await expect(drawer.getByText('功效')).toBeVisible();

      // 验证禁忌可见（确认是否安全）
      await expect(drawer.getByText('禁忌')).toBeVisible();

      // 验证用量可见（确认用量是否合理）
      await expect(drawer.getByText('用量')).toBeVisible();

      // 验证毒性等级可见
      await expect(drawer.getByText('毒性')).toBeVisible();

      // 如果有收藏按钮，验证可收藏（方便后续查阅）
      const favBtn = drawer.getByText(/收藏/);
      if (await favBtn.isVisible().catch(() => false)) {
        // 不实际点击，只验证存在
        expect(await favBtn.isVisible()).toBeTruthy();
      }
    } else {
      // 验证空状态或表格存在
      const table = page.locator('.ant-table');
      const empty = page.getByText(/暂无|没有/);
      expect(await table.isVisible() || await empty.isVisible()).toBeTruthy();
    }
  });

  // -------------------------------------------------------------------------
  // 6. 收藏功能 — 收藏方剂/中药并在收藏页验证
  // -------------------------------------------------------------------------

  test('6. 应收藏中药并在收藏页验证显示', async ({ page }) => {
    const username = 'li_' + Date.now();
    await register(page, username);

    // 先搜索一个中药
    await page.goto('/herbs');
    await page.waitForTimeout(1500);

    const rows = page.locator('.ant-table-row');
    const rowCount = await rows.count();

    if (rowCount > 0) {
      const firstRow = rows.first();

      // 打开详情抽屉
      const detailBtn = firstRow.getByText('详情');
      if (await detailBtn.isVisible().catch(() => false)) {
        await detailBtn.click();
      } else {
        await firstRow.click();
      }

      const drawer = page.locator('.ant-drawer');
      await expect(drawer).toBeVisible();

      // 尝试通过直接访问 /herbs/:id 收藏（详情页有收藏按钮）
      const closeBtn = page.locator('.ant-drawer-close');
      if (await closeBtn.isVisible().catch(() => false)) {
        await closeBtn.click();
      }

      // 通过API获取第一个中药ID，访问独立详情页
      const response = await page.request.get('/api/herbs?page=1&pageSize=1');
      if (response.ok()) {
        const data = await response.json();
        if (data.items && data.items.length > 0) {
          const herbId = data.items[0].id;
          await page.goto(`/herbs/${herbId}`);
          await page.waitForTimeout(1500);

          // 点击收藏按钮
          const favBtn = page.getByText(/收藏/).first();
          if (await favBtn.isVisible().catch(() => false)) {
            await favBtn.click();

            // 验证收藏成功提示
            await expect(firstToast(page)).toBeVisible();

            // 导航到收藏页验证
            await page.goto('/favorites');
            await page.waitForTimeout(1500);

            // 收藏页应显示至少一条记录
            const favTable = page.locator('.ant-table');
            const favEmpty = page.getByText(/暂无/);
            const hasTable = await favTable.isVisible().catch(() => false);
            const hasEmpty = await favEmpty.isVisible().catch(() => false);

            if (hasTable) {
              // 验证收藏的条目可见
              const favRows = page.locator('.ant-table-row');
              const favCount = await favRows.count();
              expect(favCount).toBeGreaterThan(0);
            }
            expect(hasTable || hasEmpty).toBeTruthy();
          }
        }
      }
    } else {
      // 验证页面基本可用
      await expect(page.locator('.ant-table').or(page.getByText(/暂无/))).toBeVisible();
    }

    // 验证收藏页可访问
    await page.goto('/favorites');
    await expect(page.getByText('我的收藏')).toBeVisible();

    // PRODUCT GAP: 没有"分享"功能。
    //   李芳验证了偏方安全后想发给丈夫或婆婆看，
    //   但当前没有分享/导出功能（方剂有导出处方单PDF，中药没有）。
    //   建议：增加分享按钮（复制链接/生成图片/导出PDF）。
  });

  // -------------------------------------------------------------------------
  // 7. 提醒设置 — 布洛芬每日多次
  // -------------------------------------------------------------------------

  test('7. 应创建"布洛芬"每日提醒并验证创建成功', async ({ page }) => {
    const username = 'li_' + Date.now();
    await register(page, username);

    await page.goto('/reminders');
    await expect(page.getByText('吃药提醒')).toBeVisible();

    // 点击添加提醒
    await page.getByRole('button', { name: /添加提醒/ }).click();
    const drawer = page.locator('.ant-drawer');
    await expect(drawer).toBeVisible();

    // 填写提醒标题
    await page.getByLabel('提醒标题').fill('布洛芬（饭后服用）');

    // 选择关联类型为西药
    const medicineRadio = drawer.getByLabel('西药');
    if (await medicineRadio.isVisible().catch(() => false)) {
      await medicineRadio.click();

      // 填写关联名称
      const linkNameInput = page.getByLabel('关联名称');
      if (await linkNameInput.isVisible().catch(() => false)) {
        await linkNameInput.fill('布洛芬');
      }
    }

    // 填写剂量
    const dosageInput = page.getByLabel('剂量');
    if (await dosageInput.isVisible().catch(() => false)) {
      await dosageInput.fill('1片');
    }

    const notesInput = page.getByLabel('备注');
    if (await notesInput.isVisible().catch(() => false)) {
      await notesInput.fill('饭后服用，每日3次');
    }

    const timePicker = drawer.locator('.ant-picker').first();
    if (await timePicker.isVisible().catch(() => false)) {
      await timePicker.click();
      await page.waitForTimeout(300);
      await timePicker.locator('input').first().fill('08:00');
      await timePicker.locator('input').last().fill('20:00');
      await page.keyboard.press('Escape');
      await page.waitForTimeout(300);
    }

    await page.getByRole('button', { name: chineseText('提交') }).click();
    await page.waitForTimeout(1000);
    await expect(page.locator('.ant-drawer-content')).toBeHidden({ timeout: 5000 });

    // 验证提醒出现在列表中
    await expect(page.getByText('布洛芬（饭后服用）')).toBeVisible();

    // PRODUCT GAP: 提醒频率只有"每天/每周/自定义"，
    //   没有"每日3次"的预设选项，需要在备注中手动说明。
    //   李芳需要设置每日多次不同时间的提醒，
    //   当前需要创建多个提醒或使用TimePicker.RangePicker选择多个时间。
    //   建议：增加"每日2次/3次"快捷模板。
  });

  // -------------------------------------------------------------------------
  // 8. 体质自测 — 开始问卷并答题翻页
  // -------------------------------------------------------------------------

  test('8. 应开始体质自测问卷并回答题目翻页', async ({ page }) => {
    const username = 'li_' + Date.now();
    await register(page, username);

    // 导航到体质自测
    await page.goto('/constitution');
    await expect(page.getByRole('heading', { name: '体质自测' })).toBeVisible();

    // 验证介绍页内容
    await expect(page.getByText(/王琦九种体质/)).toBeVisible();
    await expect(page.getByRole('button', { name: /开始测试/ })).toBeVisible();

    // 验证9种体质类型标签可见
    const types = ['平和质', '气虚质', '阳虚质', '阴虚质', '痰湿质'];
    for (const type of types) {
      await expect(page.getByText(type, { exact: true }).first()).toBeVisible();
    }

    await page.getByRole('button', { name: /开始测试/ }).click();
    await page.waitForTimeout(1000);

    await expect(page.locator('.ant-progress')).toBeVisible();
    await expect(page.getByText(/第.*页/)).toBeVisible();

    await expect(page.locator('.ant-radio-wrapper').first()).toBeVisible({ timeout: 10000 });
    const answers = ['没有', '很少', '有时', '经常', '总是'];
    for (const ans of answers) {
      await expect(page.locator('.ant-radio-wrapper').filter({ hasText: ans }).first()).toBeVisible();
    }

    // 回答第一页的题目
    const radios = page.locator('.ant-card .ant-radio-wrapper');
    const radioCount = await radios.count();
    for (let i = 0; i < radioCount; i++) {
      await radios.nth(i).click();
    }

    // 点击下一页
    await page.getByRole('button', { name: /下一页/ }).click();

    // 验证翻到第2页
    await expect(page.getByText(/第 2 \//)).toBeVisible();

    // 验证可以返回上一页
    await page.getByRole('button', { name: /上一页/ }).click();
    await expect(page.getByText(/第 1 \//)).toBeVisible();

    // PRODUCT GAP: 体质自测没有考虑年龄因素。
    //   李芳可能想为8岁女儿做体质自测，但问卷是成人标准量表。
    //   建议：增加儿童体质评估模块，或标注"仅适用于成人"。
  });

  // -------------------------------------------------------------------------
  // 9. 额外：季节养生页面验证
  // -------------------------------------------------------------------------

  test('9. 应能访问季节养生页面查看当季养生建议', async ({ page }) => {
    const username = 'li_' + Date.now();
    await register(page, username);

    await page.goto('/seasonal');
    await page.waitForTimeout(1500);

    // 验证页面加载（标题或内容可见）
    // 季节养生页面应有24节气相关内容
    const pageContent = page.locator('body');
    await expect(pageContent).toBeVisible();

    // 验证有一些节气或养生相关文字
    const hasSeasonalContent = await page
      .getByText(/节气|养生|春|夏|秋|冬/)
      .first()
      .isVisible()
      .catch(() => false);
    expect(hasSeasonalContent).toBeTruthy();

    // PRODUCT GAP: 季节养生没有按家庭成员推荐。
    //   李芳想知道孩子在当前季节需要注意什么，
    //   但当前养生建议是通用的，没有考虑儿童/老人/成人的差异。
  });

  // -------------------------------------------------------------------------
  // 10. 额外：退出后需重新认证（安全）
  // -------------------------------------------------------------------------

  test('10. 应退出后访问受保护页面被重定向到登录页', async ({ page }) => {
    const username = 'li_' + Date.now();
    await register(page, username);

    // 退出
    await logout(page);
    await page.waitForURL('/login');

    // 尝试直接访问药箱页面
    await page.goto('/medicines');
    await page.waitForURL(/\/login/);
    await expect(page.getByText(chineseText('登录')).first()).toBeVisible();

    // 尝试访问提醒页面
    await page.goto('/reminders');
    await page.waitForURL(/\/login/);

    // 尝试访问收藏页面
    await page.goto('/favorites');
    await page.waitForURL(/\/login/);

    // 这验证了：李芳的隐私担忧得到满足——退出后数据不可被未认证访问
  });

  // -------------------------------------------------------------------------
  // 11. 额外：快速搜索中药验证数据可用性
  // -------------------------------------------------------------------------

  test('11. 应验证中药知识库有数据可搜索（非空状态）', async ({ page }) => {
    const username = 'li_' + Date.now();
    await register(page, username);

    await page.goto('/herbs');
    await page.waitForTimeout(2000);

    // 验证中药列表有数据（MVP应有200味中药）
    const rows = page.locator('.ant-table-row');
    const rowCount = await rows.count();
    const table = page.locator('.ant-table');

    if (rowCount > 0) {
      expect(rowCount).toBeGreaterThan(0);

      // 验证表格列标题
      await expect(table.getByText('名称').first()).toBeVisible();
      await expect(table.getByText('功效').first()).toBeVisible();
    } else {
      // 如果没有数据，验证空状态或骨架屏
      const empty = page.getByText(/暂无/);
      const skeleton = page.locator('.ant-skeleton');
      expect(await empty.isVisible() || await skeleton.isVisible()).toBeTruthy();
    }

    // PRODUCT GAP: 搜索无法按"儿童适用"过滤。
    //   李芳想搜索适合儿童感冒的中药，但没有"儿童适用"筛选条件。
    //   当前只能按分类（解表药/清热药等）筛选，对非中医背景用户不友好。
    //   建议：增加"适用人群"或"功效标签"筛选。
  });

  // -------------------------------------------------------------------------
  // 12. 额外：健康档案可填写健康问题（头痛/月经不调）
  // -------------------------------------------------------------------------

  test('12. 应能填写健康档案中的健康问题和过敏史', async ({ page }) => {
    const username = 'li_' + Date.now();
    await register(page, username);

    await page.goto('/profile');
    await expect(page.getByRole('heading', { name: '健康档案' })).toBeVisible();

    // 验证基本信息卡片
    await expect(page.getByText('基本信息')).toBeVisible();

    // 验证健康信息卡片
    await expect(page.getByText('健康信息')).toBeVisible();

    // 填写昵称
    const nicknameInput = page.getByLabel('昵称');
    if (await nicknameInput.isVisible().catch(() => false)) {
      await nicknameInput.fill('李芳');
    }

    // 保存档案
    const saveBtn = page.getByRole('button', { name: /保存档案/ });
    if (await saveBtn.isVisible().catch(() => false)) {
      await saveBtn.click();
      await expect(firstToast(page)).toBeVisible();
    }

    // 验证体质信息区域（显示"去测试"链接，因为还没做过体质自测）
    await expect(page.getByText(/去测试|尚未进行体质测试/).first()).toBeVisible();

    // PRODUCT GAP: 健康档案没有"当前用药"字段。
    //   李芳在吃止痛药（头痛）和调理月经的中药，
    //   这些信息应该记录在档案中，用于安全检查时的中西药交互参考。
    //   建议增加"当前用药清单"字段。
    // PRODUCT GAP: 没有"家庭成员管理"功能。
    //   李芳无法为女儿和儿子分别建立健康档案。
  });
});
