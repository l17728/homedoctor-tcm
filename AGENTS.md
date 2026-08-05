# 家庭医生·您的养生助手 — AI Agent 开发指令

> **定位**：本文件是所有 AI Agent（Sisyphus、OpenCode、Claude Code 等）在"家庭医生"项目中工作的核心指令。
> **权威源**：产品规格说明书 `/homedoctor/family-doctor-spec.md`（v2.2，3185 行，25 章）。

---

## 0. 项目概况

- **技术栈**：FastAPI (Python) + React SPA (TypeScript) + SQLite WAL (SQLCipher) + Docker Compose
- **前端**：React 18 + Ant Design 5 + Vite + react-router-dom v6（35 页面，首屏 455KB gzip）
- **后端**：FastAPI + aiosqlite（模块化：`app/tools/` 5子模块 + `app/db/` 5子模块）
- **Agent系統**：8步知識管道 + 巡檢Agent(24h定時) + 信任分級SABC(自動升降級) + 多AI評審 + 記憶系統
- **可觀測性**：4中間件日誌(auth/csrf/rate_limit/tenant) + RequestAuditMiddleware(全局追踪) + 118模塊logger
- **部署**：Docker Compose，本地优先，无云端依赖
- **测试**：1888 后端测试（84%+覆盖率）+ 37 E2E 测试文件
- **目标用户**：银发用户 55-70 岁（王阿姨原型）+ 父母 30-45 岁（李芳/张伟原型）

---

## 1. 核心工程原则（★ 从 /fighting 提炼，不可违反）

### 1.1 配置驱动，无 DDL 迁移

**原则**：字段定义在 JSON 配置中，不在 SQL DDL 中。SQLite 用 `properties TEXT` 存 JSON。

```
正确：新增"功效分类"字段 → 修改 config/schemas/herb.json → 前端自动渲染
错误：新增"功效分类"字段 → ALTER TABLE ADD COLUMN → 写迁移脚本
```

- `/fighting` 实现：`config/schemas/*.json` + `FileSchemaRegistry` + `SchemaField` 组件
- **家庭医生适配**：
  - `config/schemas/herb.json`（中药）、`formula.json`（方剂）、`medicine.json`（西药）、`therapy.json`（外治理疗）
  - SQLite 固定表（nodes、edges、users 等）+ `properties TEXT` JSON 灵活字段
  - 前端 `SchemaField` 组件从配置自动渲染表单/详情/表格列
  - 字段操作 API：`addField`、`renameLabel`、`editEnum`、`retire`（与 /fighting 一致）

### 1.2 CLI for Every Backend API

**原则**：每个后端 API 必须有对应的 CLI 命令。AI Agent 通过 CLI 调用，不直接访问数据库。

```
正确：AI Agent → `python cli.py herbs:search "黄芪"` → HTTP → FastAPI handler → SQLite
错误：AI Agent → 直接 SQLite 查询
```

- `/fighting` 实现：`cli-core.ts` 声明式 `COMMANDS` 数组（100+ 命令），CLI 是纯 HTTP 客户端
- **家庭医生适配**：
  - `typer` + `httpx` 实现声明式 CLI
  - 命令示例：`herbs:list`、`herbs:search`、`formulas:detail`、`safety:check`、`reminders:add`
  - Spec §8.7 的 Code Agent 模式通过 CLI 驱动

### 1.3 递归收敛（举一反三）

**原则**：发现一个问题，消灭一类问题，递归检查直到零失败。

```
正确：发现"黄芪"缺 pharmacologicalClass → grep 全库所有药材 → 逐一补全 → 重验 → 递归到零
错误：发现"黄芪"缺字段 → 只补黄芪 → 不检查其他 199 味药
```

- `/fighting` 教训来源：`LRN-20260526-001`，从 `row.locator('a')` 选择器 bug 发现全库 20+ 处同类问题
- **适用场景**：安全规则遗漏、tenant_id 隔离检查、AI 幻觉测试、Schema 字段一致性

### 1.4 结构化是权威，知识图谱是派生

**原则**：所有写入走结构化模型（SQLite），知识图谱从结构化数据自动同步/可重建。

```
正确：用户修改"黄芪"属性 → UPDATE nodes SET properties → 知识图谱自动同步
错误：用户修改"黄芪"属性 → 直接改知识图谱节点 → SQLite 和图谱不一致
```

- **家庭医生适配**：Spec §9.3 知识图谱是 V2 功能，但必须在架构上保证：
  - SQLite `nodes` + `edges` 是权威数据源
  - 知识图谱（Neo4j/内存图）从 SQLite 自动构建
  - 图谱损坏 → 删了重建，不可修复
  - 永远不允许直接写入图谱

### 1.5 部署绝不删数据

**原则**：Docker 部署时 `data/` 目录必须排除在 rsync/copy 之外。

```
正确：docker compose up → 新代码挂载到 /app → /app/data/ 是 volume，不受镜像更新影响
错误：Dockerfile COPY . /app → 覆盖了 data/ 目录 → 用户数据丢失
```

- `/fighting` 教训：`F1` 致命错误——rsync --delete 未排除 data/ 导致生产数据库被删
- **家庭医生适配**：
  - `docker-compose.yml` 中 `data/` 必须是 named volume
  - 部署脚本硬编码 `--exclude='data/'`
  - 备份策略：SQLite `.backup()` + 定时 + 原子恢复（移植 /fighting backup.ts 逻辑）

### 1.6 并行开发

**原则**：独立子任务（文件不相交 + 无共享状态 + 无顺序依赖）必须并行，不串行。

```
正确：同时启动 3 个 Agent → herb API + formula API + safety engine（文件不相交）
错误：串行 → herb API 完成后才开始 formula API
```

- **12 周 MVP 需要最大化并行度**——单人开发更要靠 AI Agent 并行

### 1.7 中文领域语言

**原则**：所有领域枚举值使用中文原文，不翻译成英文。代码、测试、UI 一致。

```
正确：{ status: "风寒感冒", constitution: "阳虚质", category: "补气药" }
错误：{ status: "wind_cold_cold", constitution: "yang_deficiency", category: "qi_tonifying" }
```

- `/fighting` 实现：`properties` JSON 中的 key 和 value 都是中文
- **家庭医生适配**：
  - JSON 字段 key：中文（"功效"、"性味"、"归经"）
  - API 返回值：中文枚举
  - 测试断言：中文
  - 前端常量：中文 `STATUS_COLOR: { "风寒感冒": "blue" }`

### 1.8 特性完工例行检查

**原则**：每个功能完成后必须通过检查清单，不跳步。

检查清单（Spec §25.5）：
1. E2E 测试 — Playwright 覆盖新功能，全量通过
2. 后端测试 — pytest 覆盖 API 端点，全量通过
3. CLI 命令 — 新 API → 新 CLI 命令，验证可用
4. 安全规则 — 涉及药物/疗法 → 五层安全检查覆盖
5. 数据模型 — 新表/新字段 → JSON 配置更新
6. API 文档 — 新端点写入 API 参考文档
7. 常量更新 — 新枚举/颜色/标签 → constants.ts
8. Docker 验证 — docker compose up → 全功能可用
9. 适老化检查 — 新页面满足 §6.6 最低标准（16px/44px/图标+文字）
10. 部署验证 — 部署后确认数据未丢失

---

## 2. 前端设计规范（★ Ant Design 5 实战，从 /fighting 提炼）

### 2.1 页面三段式

所有列表/CRUD 页面遵循：

```
Zone A — 页头：标题 + HelpButton（左） | 操作按钮（右）
Zone B — 筛选栏：Select + Input.Search + 列选择器
Zone C — 内容区：Table（默认）/ Cards（移动端）/ Calendar（日历视图）
```

### 2.2 Drawer 规范

| 宽度 | 用途 |
|------|------|
| 360px | 简单设置 |
| 480px | 标准创建/编辑表单 |
| 560px | 详情查看 |

**必选 props**：`destroyOnClose`（防残留状态）、`maskClosable={false}`（表单类，防误触）

### 2.3 表格规范

- `size="middle"`，`pageSize=20`，弹性列不设 width 设 `ellipsis`
- 操作列固定右侧：`fixed: "right"`
- 加载状态：`<Skeleton>`（不用 `<Spin>`）
- 行点击导航：跳过 `<a>` / `<input>` / `<checkbox>` 元素
- **操作列选择器**：必须用 `row.locator('td').last()` 限定，不用 `row.locator('a')`

### 2.4 状态管理

**不用 Redux/Zustand**。使用 React Context + Singleton Cache：

```typescript
// useSettings 模式：模块级单例 + TTL + 去重 + 发布订阅
// 适用：药品分类、体质选项、AI 模型配置等全局配置数据
const cache = { data: null, expiry: 0, subscribers: new Set() };
```

### 2.5 常量管理

所有颜色/标签映射集中在 `constants.ts`，不在组件中硬编码：

```typescript
export const DRUG_STATUS_COLOR = { 充足: "green", 低库存: "orange", 已过期: "red" };
export const REMINDER_STATUS_COLOR = { 待服: "blue", 已服: "green", 漏服: "red" };
export const PAGE_SIZE = 20;
export const DATE_FORMAT = "YYYY-MM-DD HH:mm";
```

### 2.6 空状态处理

```
initialLoading → <Skeleton active />
静默刷新 → 不闪（无 loading 状态切换）
空数据 → <Empty description="暂无药品，点击添加" />
```

---

## 3. 后端架构规范（★ FastAPI 适配，从 /fighting Node.js 提炼）

### 3.1 数据层架构

```
DbAdapter（Python ABC）
  └── SqliteAdapter（aiosqlite 封装）
Repository（数据访问层，所有 SQL 通过 adapter）
  └── 方法强制 tenant_id 过滤（contextvars.ContextVar）
JSON 配置 Schema（config/schemas/*.json）
  └── FileSchemaRegistry 加载 + 校验
```

### 3.2 API 路由组织

```python
# FastAPI APIRouter 工厂模式（对应 /fighting 的 makeXxxRouter）
herb_router = APIRouter(prefix="/api/herbs")
formula_router = APIRouter(prefix="/api/formulas")
safety_router = APIRouter(prefix="/api/safety")
# ...

# 中间件链（对应 /fighting 的 app.ts 中间件顺序）
app.add_middleware(AuthMiddleware)       # JWT 验证
app.add_middleware(CsrfMiddleware)       # Origin 检查
app.add_middleware(RateLimitMiddleware)  # 限流
```

### 3.3 租户隔离

```python
# Python 等价于 /fighting 的 AsyncLocalStorage
import contextvars
current_tenant_id: contextvars.ContextVar[str] = contextvars.ContextVar('tenant_id', default='default')

# Repository 所有查询强制注入 WHERE tenant_id = ?
class BaseRepository:
    def _tenant_filter(self) -> str:
        return f"tenant_id = '{current_tenant_id.get()}'"
```

### 3.4 审计链

```python
# 移植 /fighting 的 audit-chain.ts
# 每次 write 生成 hash 链：sha256(prev_hash + action + entity + changes + timestamp)
# 用于：药品变更追踪、安全检查触发记录、AI 推荐审计
```

### 3.5 备份/恢复

```python
# 移植 /fighting 的 backup.ts
# SQLite .backup() + 定时 + 原子恢复（.restore_pending → 重启时应用）
# 关键：恢复时 rename → process.exit(0) → 重启时 apply
```

---

## 4. 安全底线（★ Spec §15，5 专家全票共识）

### 4.1 硬编码规则优先于 AI

```
用户请求 → 第1a层（中药×中药配伍禁忌）→ 第1b层（中西药交互）→ 第2-5层（AI分析）
硬编码层拦截 → 不经过 AI → 直接返回警告
```

### 4.2 致命错误记录（不可重犯）

| # | 错误 | 预防 |
|---|------|------|
| F1 | 部署时 rsync --delete 未排除 data/ | 部署脚本硬编码 `--exclude='data/'` |
| F2 | git archive HEAD 只包含已提交文件 | 部署前必须 git commit |
| F3 | 遗漏 tenant_id 的查询导致跨家庭泄露 | BaseRepository 强制过滤 + AST 级静态检查 |
| F4 | AI 幻觉未被硬规则前置拦截 | 硬编码层在 AI 层之前运行 |

---

## 5. E2E 测试惊艳教训（★ 从 /fighting 185 个测试中提炼）

| # | 教训 | 解决方案 |
|---|------|---------|
| T1 | Ant Design 5 两字中文按钮自动插空格 | `getByText(/删\s?除/)` |
| T2 | Select 下拉 "outside viewport" | `dispatchEvent('click')` 代替 `.click()` |
| T3 | 多次 Toast 严格模式违规 | `.first()` 或更精确选择器 |
| T4 | Drawer 关闭不触发表单提交 | 回归测试覆盖 |
| T5 | 行操作列选择器匹配多列 | `row.locator('td').last()` 限定 |

---

## 6. 适老化设计规范（★ Spec §6.6，王阿姨原型）

**所有新页面必须满足的最低标准**：

| 维度 | 最低标准 |
|------|---------|
| 最小字体 | 16px（正文）、14px（辅助） |
| 触控目标 | ≥44×44px |
| 按钮文字 | 图标 + 文字，不能仅图标 |
| 对比度 | ≥4.5:1（WCAG AA） |
| 导航层级 | ≤2 层（长辈模式 3 Tab） |
| 交互步骤 | 核心操作 ≤4 步 |

**长辈模式**：首页 / AI 语音问答 / 我的（仅 3 Tab，字体 18px，语音播报确认）

---

## 7. API 客户端规范（★ 从 /fighting api.ts 提炼）

### 7.1 前端 API 客户端

```typescript
// 自定义 fetch 封装（不用 axios）
// 按域拆分（不像 /fighting 的 2100 行单文件）
// - drugApi.ts：药品 CRUD + 搜索
// - formulaApi.ts：方剂 CRUD + 搜索
// - safetyApi.ts：安全检查
// - reminderApi.ts：提醒管理
// - chatApi.ts：AI 对话
// - settingsApi.ts：配置管理
```

### 7.2 system-paths.ts 单一来源

```typescript
// 所有角色限定的路径定义在一处，所有消费者引用
export const ELDERLY_PATHS = ['/dashboard', '/chat', '/profile'];
export const ADMIN_PATHS = ['/settings', '/users', '/schema', '/backup'];
export function isSystemPath(pathname: string): boolean { ... }
```

---

## 8. 关键技术映射（/fighting → 家庭医生）

| /fighting (Node.js) | 家庭医生 (FastAPI) |
|---------------------|-------------------|
| `DbAdapter` + `SqliteAdapter` | Python ABC + `aiosqlite` |
| `AsyncLocalStorage` 租户隔离 | `contextvars.ContextVar` |
| `FileSchemaRegistry` JSON 加载 | 同样的 JSON 配置加载逻辑 |
| `validation.ts` 手写校验 | Pydantic 自动校验（更优雅） |
| Express Router Factory | FastAPI `APIRouter()` + `Depends()` |
| `cli-core.ts` 声明式 CLI | `typer` + `httpx` 声明式命令 |
| `audit-chain.ts` Merkle 链 | 直接移植（sha256 逻辑相同） |
| `backup.ts` SQLite backup | `aiosqlite` 同样支持 `.backup()` |
| React Context + Singleton Cache | 同样的模式（useSettings/useSchema） |
| Ant Design 5 ThemeConfig | 同样的主题系统 |

---

## 9. 开发流程规范

### 9.1 TDD（测试驱动）

```
写失败测试 → 最小实现 → 全绿 → commit
不要：先写代码 → 再补测试
```

### 9.2 分支策略

```
main（随时可部署）
  └── feature/xxx（开发分支，完成后 PR 合并）
```

### 9.3 提交规范

```
feat: 新功能
fix: 修复 bug
refactor: 重构（不改变行为）
test: 测试
docs: 文档
chore: 构建/配置
```

---

## 10. 项目文件索引

| 文件 | 说明 |
|------|------|
| `/homedoctor/family-doctor-spec.md` | 产品规格说明书 v2.2（3185 行，25 章） |
| `/homedoctor/AGENTS.md` | 本文件 — AI Agent 开发指令 |
| `/homedoctor/README.md` | 项目总览 + API 参考 + 统计 |
| `/homedoctor/backend/README.md` | 后端架构 + Agent系统 + 测试 + CLI |
| `/homedoctor/frontend/README.md` | 前端页面 + 构建 + 性能 + E2E |
| `/homedoctor/docs/design-self-growing-knowledge-system.md` | 自成长知识系统设计（25章） |
| `/homedoctor/docs/design-self-evolving-dual-agent-system.md` | 双Agent系统设计（9章） |
| `/homedoctor/docs/design-distributed-knowledge-index.md` | 分布式知识索引设计 |
| `/homedoctor/docs/SAFETY_DESIGN.md` | 安全引擎五层设计 |
| `/homedoctor/docs/DEPLOYMENT.md` | 部署指南 |
| `/homedoctor/docs/API_REFERENCE.md` | API 参考文档 |

### 关键源文件索引

| 文件 | 说明 |
|------|------|
| `backend/app/tools/pipeline.py` | 知识管道（提取→分析→入库→索引，433行） |
| `backend/app/tools/review.py` | 多模型评审 + 冲突检测（158行） |
| `backend/app/tools/entities.py` | 实体管理 + 关系引擎（262行） |
| `backend/app/tools/config.py` | 配置持久化 + 提示词优化（227行） |
| `backend/app/agent_tools.py` | log_action + re-export 层（87行） |
| `backend/app/db/schema.py` | 45 张表 DDL + FTS5（679行） |
| `backend/app/db/adapter.py` | DbAdapter + SqliteAdapter（209行） |
| `backend/app/db/migrations.py` | 迁移 + init_db（109行） |
| `backend/app/db/seeds.py` | 安全规则 + 种子数据（581行） |
| `backend/app/database.py` | 薄 re-export 层（31行） |
| `backend/app/knowledge_agent.py` | 8步管道 + 记忆回读 |
| `backend/app/knowledge_feeder.py` | 巡检Agent |
| `backend/app/agent_communication.py` | Agent对话 + 辩论自动执行 |
| `backend/app/scheduler.py` | 24h asyncio 定时调度 |
| `backend/app/trust_engine.py` | SABC信任 + 自动升降级 |
| `backend/app/search_pipeline.py` | BM25(IDF) + 语义 + RRF融合 |
| `backend/app/safety_engine.py` | 五层安全检查（批量优化） |
| `backend/app/llm_unified.py` | 统一LLM调用（单模型+多模型评审） |
| `backend/app/middleware/` | 4中间件 + 请求追踪（5文件） |
| `frontend/src/App.tsx` | React.lazy 路由分块（35页面） |
| `frontend/vite.config.ts` | manualChunks 函数化 vendor分块 |
| `frontend/nginx.conf` | gzip压缩 + 静态资源缓存 |
