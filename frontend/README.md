# Frontend — 家庭医生 SPA

React 18 + TypeScript + Ant Design 5 + Vite。

## 快速开始

```bash
npm install
npm run dev        # 开发服务器 http://localhost:3000
npm run build      # 生产构建 → dist/
npm run preview    # 预览构建结果
```

## 页面清单（35 页）

| 路由 | 页面 | 说明 |
|------|------|------|
| `/login` | LoginPage | 登录/注册 |
| `/` | Dashboard | 首页统计 + 每日养生卡 |
| `/herbs` | HerbList | 中药列表 + FTS5 搜索 |
| `/herbs/:id` | HerbDetail | 中药详情（性味归经/功效/禁忌） |
| `/formulas` | FormulaList | 方剂列表 + 搜索 |
| `/formulas/:id` | FormulaDetail | 方剂详情（组成/用法/安全检查） |
| `/medicines` | MedicineList | 药箱 CRUD |
| `/chat` | ChatPage | AI 问答（语音输入 + TTS 播报 + 图谱上下文注入） |
| `/reminders` | RemindersPage | 吃药提醒 CRUD + 今日时间轴 |
| `/constitution` | ConstitutionPage | 体质自测（66 题问卷 + 评分） |
| `/profile` | ProfilePage | 健康档案 |
| `/settings` | SettingsPage | 设置（深色模式 + 长辈模式） |
| `/safety-check` | SafetyCheckPage | 五层安全检查 |
| `/formulation` | FormulationPage | 智能配伍引擎 |
| `/knowledge-hub` | KnowledgeHubPage | 知识中枢 |
| `/knowledge-browse` | KnowledgeBrowsePage | 知识浏览（wiki式 + 笔记 + 追加） |
| `/admin` | AdminPage | 管理面板（7Tab: 概览/模型/索引/日志/巡检/记忆/对话） |
| `/knowledge-graph` | KnowledgeGraphPage | 知识图谱可视化（AntV G6） |
| `/classics` | ClassicsBookshelf | 经典书柜 |
| `/classics/:id` | ClassicReader | 经典阅读器（批注 + AI问答） |
| `/therapies` | TherapiesPage | 外治理疗（7类105条） |
| `/meridians` | MeridianAcupointPage | 经络穴位浏览器 |
| `/health-practice` | HealthPracticePage | 养生功法 |
| `/medication-plans` | MedicationPlansPage | 用药套餐 |
| `/medication-schedule` | MedicationSchedulePage | 智能服药排程 |
| `/bookmarks` | BookmarksPage | 书签管理 |
| `/comparison` | ComparisonPage | 中药对比 |
| `/knowledge-import` | KnowledgeImportPage | 知识导入（PDF/Word/URL/OCR） |
| `/reports` | ReportsPage | 报告体系（体质/趋势/就诊准备） |
| `/health-log` | HealthLogPage | 每日健康打卡 |
| `/remote-assist` | RemoteAssistPage | 子女远程协助 |
| `/share-cards` | ShareCardsPage | 家庭分享卡 |
| `/triage` | TriagePage | 儿童急症分诊 |
| `/family-members` | FamilyMembersPage | 家庭成员管理 |
| `/favorites` | FavoritesPage | 收藏夹 |

## 组件架构

```
App.tsx
  ├── AuthProvider          ← 认证状态
  ├── ThemeProvider          ← 亮/暗主题
  ├── ElderlyModeProvider    ← 长辈模式
  └── LayoutSwitch
       ├── AppLayout         ← 标准侧边栏布局
       │    └── <Outlet />   ← 当前页面
       └── ElderlyLayout     ← 长辈 3-Tab 底部导航
            └── <Outlet />
```

### API 客户端（12 个）

```
api/
  client.ts              ← fetch 封装（Bearer token + 401 重定向）
  authApi.ts             ← 登录/注册
  herbApi.ts             ← 中药列表/搜索/详情
  formulaApi.ts          ← 方剂列表/详情
  medicineApi.ts         ← 药箱 CRUD（localStorage fallback）
  chatApi.ts             ← AI 对话
  safetyApi.ts           ← 安全检查
  reminderApi.ts         ← 提醒 CRUD + 今日
  constitutionApi.ts     ← 问卷/评估/历史
  profileApi.ts          ← 健康档案
  dashboardApi.ts        ← 首页统计
  dailyHealthApi.ts      ← 每日养生卡
```

每个 API 客户端遵循统一模式：
- `import { request } from './client'`
- 失败时部分客户端 fallback 到 localStorage（medicineApi）
- 401 自动清除 token 并重定向 `/login`

### Hooks

| Hook | 说明 |
|------|------|
| `useAuth` | 登录状态、user、login/register/logout |
| `useTheme` | 亮/暗切换，localStorage 持久化 |
| `useSpeechRecognition` | Web Speech API 语音输入（zh-CN） |
| `useSpeechSynthesis` | TTS 语音播报（rate=0.9，适合老年） |

### 长辈模式

- **触发**: Settings → 长辈模式 Switch → 确认弹窗
- **效果**: `document.body.classList.add('elderly-mode')`
- **CSS**: `elderly-mode.css` — 18px 字体，48px 触控
- **布局**: ElderlyLayout — 3 Tab（首页/AI问答/我的）
- **持久化**: localStorage `family_doctor_elderly_mode`

### 语音输入

ChatPage 集成 Web Speech API：
- 麦克风按钮（48x48px，录音时红色脉冲动画）
- SpeechRecognition → zh-CN → 实时转写填充输入框
- SpeechSynthesis → AI 回复可选语音播报
- 不支持的浏览器优雅降级（禁用按钮 + tooltip）

## AntD 设计规范

| 场景 | 规范 |
|------|------|
| 列表页 | 页头（标题+操作）→ 筛选栏 → Table（middle/20条） |
| Drawer | 480px 表单 / 560px 详情，`destroyOnClose` + `maskClosable={false}` |
| 加载 | `<Skeleton active />`（不用 Spin） |
| 空状态 | `<Empty description="..." />` |
| 状态标签 | `<StatusTag status colorMap />` 组件 |
| 颜色常量 | `constants.ts` 集中管理 |
| 删除确认 | `<Popconfirm>` 或 `Modal.confirm` |

## 构建

```bash
npm run build
# → dist/assets/index-[hash].js   (29KB gzip: 10KB) — 入口
# → dist/assets/antd-vendor.js    (1.27MB gzip: 394KB) — Ant Design（1年缓存）
# → dist/assets/knowledgeGraphRuntime-[hash].js (943KB gzip: 270KB) — G6 按需扩展（仅图谱页加载）
# → dist/assets/react-vendor.js   (161KB gzip: 53KB)
# → dist/assets/markdown-vendor.js(118KB gzip: 36KB)
# → dist/assets/[PageName].js     (3-30KB each) — 路由级懒加载
# 构建时间: ~15s
# 首屏 gzip 传输量: 455KB（不含G6）
```

### 性能优化

| 优化 | 效果 |
|------|------|
| nginx gzip 压缩 | 所有 JS/CSS 传输时压缩 |
| G6 按需注册 | 仅加载图谱页使用的节点、边、布局、交互和小地图扩展；运行时约 943KB（gzip 270KB），较原包体缩小约 33%（gzip 34%） |
| manualChunks 函数化 | rc-* 子包正确归入 antd-vendor |
| React.lazy 路由分块 | 35 个页面各自独立 chunk |
| 静态资源 1 年缓存 | vendor chunk 永久缓存（immutable） |

生产 Docker 构建：`Dockerfile`（多阶段：node:22 build → nginx:alpine serve）

## E2E 测试

```bash
npx playwright test                      # 全部 37 test files
npx playwright test e2e/auth             # 认证
npx playwright test e2e/reminders        # 提醒
npx playwright test e2e/constitution     # 体质
npx playwright test e2e/profile-elderly  # 档案+长辈模式
npx playwright test e2e/admin-knowledge-agent  # 管理页+知识浏览
npx playwright test --ui                 # 交互模式
```

| 测试文件 | 覆盖 |
|---------|------|
| auth.spec.ts | 登录/注册/退出/AuthGuard |
| dashboard.spec.ts | 首页/统计/养生卡 |
| herbs.spec.ts | 列表/搜索/详情导航 |
| medicines.spec.ts | CRUD 全生命周期 |
| reminders.spec.ts | 导航/创建/今日/toggle/删除 |
| constitution.spec.ts | 问卷流程/分页/结果 |
| profile-elderly.spec.ts | 档案CRUD/长辈模式/3-Tab导航 |
| admin-knowledge-agent.spec.ts | AdminPage/KnowledgeBrowse/KnowledgeHub |
| personas/*.spec.ts (10个) | 多角色用户旅程（老人/父母/医生/学生等） |

## 技术约束

- 不用 Redux/Zustand（React Context + 模块级单例）
- 不用 axios（自定义 fetch 封装）
- 不用 chart 库（CSS bars 实现图表）
- 不用 `as any` / `@ts-ignore`
- 中文领域枚举不翻译
