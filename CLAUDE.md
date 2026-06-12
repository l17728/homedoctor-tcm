# CLAUDE.md — 家庭医生项目 AI Agent 指南

> 本文件是所有 AI Agent（Sisyphus、Claude Code、OpenCode 等）在本项目工作的核心指令。
> 权威源：`/homedoctor/family-doctor-spec.md`（v2.2，3185 行，25 章）。
> 参考项目：`/fighting`（739 后端测试 + 185 E2E，生产验证）。

## 当前状态

**版本**: v0.2.0 MVP 完成
**测试**: 190 后端 + 83 E2E = 273 全绿
**仓库**: `github.com/l17728/homedoctor-tcm` (private)

## 技术栈速查

| 层 | 技术 | 关键文件 |
|----|------|---------|
| 后端 | FastAPI + aiosqlite + JWT(Argon2id) | `backend/app/main.py` |
| 前端 | React 18 + AntD 5 + Vite + TypeScript | `frontend/src/App.tsx` |
| DB | SQLite + FTS5 | `backend/data/homedoctor.db` |
| 部署 | Docker Compose + Nginx | `docker-compose.yml` |

## 不可违反的规则

1. **`as any` / `@ts-ignore` 禁止** — 类型安全零容忍
2. **部署绝不删 data/** — `data/` 是 named volume，rsync `--exclude='data/'`
3. **硬编码规则 > AI** — 配伍禁忌在 AI 层之前运行
4. **tenant_id 强制过滤** — 所有 Repository 查询注入 WHERE tenant_id
5. **中文领域枚举** — `{ status: "风寒感冒" }` 不翻译成英文
6. **TDD** — 先写失败测试 → 最小实现 → 全绿 → commit
7. **递归收敛** — 修一个 bug → grep 全库同类 → 逐一修 → 重测到零

## 项目结构（关键路径）

```
backend/
  app/
    main.py              ← FastAPI 入口，所有 router 注册
    database.py          ← DDL + DbAdapter + 种子安全规则
    repository.py        ← 数据访问层，tenant_id 隔离
    models.py            ← Pydantic 请求/响应模型
    auth.py              ← JWT 生成/验证，Argon2id
    safety_engine.py     ← 五层安全检查引擎（核心）
    safety_keywords.py   ← 29 个急症关键词
    solar_terms.py       ← 24 节气算法
    constitution_data.py ← 九种体质 66 题问卷
    routers/             ← 11 个 APIRouter
  tests/                 ← 190 个测试
  scripts/               ← 种子数据脚本

frontend/
  src/
    App.tsx              ← 路由 + 布局切换（标准/长辈）
    api/                 ← 12 个 API 客户端（fetch 封装）
    pages/               ← 12 个页面
    hooks/               ← useAuth/useTheme/useSpeech*
    contexts/            ← ElderlyModeContext
    layouts/             ← AppLayout（侧边栏）/ ElderlyLayout（3 Tab）
```

## 开发命令

```bash
# 后端
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
python3 -m pytest tests/ -v           # 190 tests

# 前端
cd frontend
npm install
npm run dev                            # localhost:3000
npx tsc --noEmit                       # 0 errors required
npm run build                          # production build

# E2E
npx playwright test                    # 83 tests
npx playwright test --ui               # interactive

# 部署
./start.sh                             # Docker 一键
./smoke_test.sh                        # 冒烟测试
```

## 数据库

- **路径**: `backend/data/homedoctor.db`
- **种子数据**: 203 中药 + 82 方剂 + 60+ 安全规则
- **表**: users, herbs, formulas, medicines, reminders, constitution_assessments, user_profiles, safety_rules, chat_messages, chat_conversations, audit_log
- **FTS5**: herbs_fts, formulas_fts（全文搜索虚拟表）
- **灵活字段**: `properties TEXT`（JSON），字段定义在 config/schemas/

## API 模式

```python
# Router 注册（main.py）
app.include_router(herbs.router)
app.include_router(safety.router)

# Router 定义模式
router = APIRouter(prefix="/api/xxx", tags=["xxx"])

# 认证依赖
@router.get("/")
async def list_items(user: User = Depends(get_current_user), db: DbAdapter = Depends(get_db)):
    ...
```

## 前端模式

```typescript
// API 客户端模式
import { request } from './client';
export async function getXxx(): Promise<T> {
  return request<T>('/api/xxx');
}

// 页面模式：useEffect → API → setState → Skeleton/Empty/Table
// Drawer: destroyOnClose + maskClosable={false}
// 状态: StatusTag 组件 + constants.ts 颜色映射
// 长辈模式: ElderlyModeContext + body.elderly-mode class
```

## E2E 测试教训（从 /fighting 提炼）

| # | 教训 | 解决方案 |
|---|------|---------|
| T1 | AntD 5 两字中文按钮自动插空格 | `getByText(/删\s?除/)` |
| T2 | Select 下拉 "outside viewport" | `dispatchEvent('click')` |
| T3 | 多次 Toast 严格模式违规 | `.first()` |
| T4 | Drawer 关闭不触发表单提交 | 回归测试覆盖 |
| T5 | 行操作列选择器匹配多列 | `row.locator('td').last()` |

## 完工检查清单

每个功能完成后：
1. [ ] 后端测试通过（`pytest tests/ -q`）
2. [ ] TypeScript 0 错误（`npx tsc --noEmit`）
3. [ ] 前端构建通过（`npm run build`）
4. [ ] 新 API → 新 CLI 命令
5. [ ] 涉及药物 → 安全检查覆盖
6. [ ] 新枚举 → constants.ts
7. [ ] 新页面 → E2E 测试
8. [ ] 适老化：16px/44px/图标+文字

## 常见陷阱

- **DB 路径**: 种子脚本用 `DATABASE_URL` env，FastAPI 用 `HOMEDOCTOR_DATABASE_URL`（前缀不同）
- **FTS5**: 搜索用虚拟表，不直接查 herbs 表
- **JWT 过期**: client.ts 自动检测 401 → 重定向 /login
- **长辈模式**: CSS 类加在 `document.body` 上，全局影响 AntD 组件大小
- **Web Speech API**: 需要 Chrome 浏览器，其他浏览器优雅降级
