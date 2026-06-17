# 家庭医生 · 您的养生助手

> Local-first TCM (Traditional Chinese Medicine) health intelligence platform. 银发用户优先，家庭健康管家。

## 功能概览

### MVP 已交付
- **AI 健康问答** — SSE 流式输出 + 推理链面板 + 安全关键词拦截 + 语音输入 + TTS 播报 + 多模态图片问答
- **中医药知识库** — 203 味中药 + 82 首方剂，FTS5 全文搜索
- **五层安全检查** — 十八反十九畏 + 中西药交互（drugClass 感知）+ 剂量 + 特殊人群 + 免责声明
- **儿童急症分诊** — 5 年龄组 × 8 红旗症状 × 12 步评估，新生儿发热=紧急
- **体质自测** — 王琦九种体质标准量表（66 题）+ 主体质/兼夹体质判定
- **吃药提醒** — 每日时间轴 + 状态追踪（待服/已服/漏服）
- **家庭药箱** — 西药/中成药 CRUD + drugClass 分类
- **健康档案** — 基本信息 + 体质 + 过敏史 + 健康问题 + 孕期标记
- **每日养生卡** — 24 节气养生建议
- **长辈模式** — 5 Tab 界面 + 18px 大字体 + 底部导航
- **安全合规** — RateLimitMiddleware 限流 + PIPL 账户删除 + AES-256-GCM 备份加密 + OS keyring 密钥存储
- **审计链** — SHA-256 hash chain 全量操作追踪 + AI 幻觉防御 + 模型降级链

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | FastAPI + aiosqlite + python-jose (JWT) + passlib (Argon2id) + cryptography (AES-256-GCM) |
| 前端 | React 18 + TypeScript + Ant Design 5 + Vite |
| 数据库 | SQLite + FTS5（本地优先，无云端依赖）+ SQLCipher 可选加密 |
| 部署 | Docker Compose + Nginx 反向代理 |
| 测试 | pytest（485+ 后端）+ Playwright（83 E2E） |

## 快速开始

### 方式一：Docker 一键启动（推荐）

```bash
./start.sh
```

自动执行：`docker compose build` → `docker compose up -d` → 等待健康检查 → 数据种子化

启动后：
- 前端：`http://localhost:3000`
- API：`http://localhost:8000`
- API 文档：`http://localhost:8000/docs`

### 方式二：本地开发

```bash
# 后端
cd backend
pip install -r requirements.txt
python3 scripts/seed_herbs_batch1.py  # 录入中药数据
python3 scripts/seed_herbs_batch2.py
python3 scripts/seed_herbs_batch3.py
python3 scripts/seed_formulas.py       # 录入方剂数据
uvicorn app.main:app --reload --port 8000

# 前端（另一个终端）
cd frontend
npm install
npm run dev    # http://localhost:3000
```

### 冒烟测试

```bash
./smoke_test.sh
```

验证：健康检查 / 注册 / 中药列表 / 方剂列表 / Dashboard / 安全检查 / 前端页面

## 项目结构

```
homedoctor/
├── family-doctor-spec.md          # 产品规格说明书 v2.2（3185 行）
├── AGENTS.md                       # AI Agent 开发指令
├── docker-compose.yml              # Docker 编排
├── start.sh                        # 一键启动脚本
├── smoke_test.sh                   # 冒烟测试脚本
│
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI 入口，路由注册
│   │   ├── config.py               # Pydantic Settings 配置
│   │   ├── database.py             # DDL + DbAdapter + 种子安全规则
│   │   ├── repository.py           # 数据访问层（tenant_id 隔离）
│   │   ├── models.py               # Pydantic 请求/响应模型
│   │   ├── auth.py                 # JWT + Argon2id 认证
│   │   ├── safety_engine.py        # 五层安全检查引擎（drugClass 感知）
│   │   ├── safety_keywords.py      # 29 个急症关键词
│   │   ├── solar_terms.py          # 24 节气算法
│   │   ├── constitution_data.py    # 九种体质 66 题问卷
│   │   ├── triage_data.py          # 儿童分诊数据（5 组 × 8 红旗）
│   │   ├── audit.py                # SHA-256 审计链
│   │   ├── llm.py                  # LLM 客户端 + 幻觉防御 + 模型降级
│   │   ├── crypto_utils.py         # AES-256-GCM 加密/解密
│   │   ├── secrets.py              # OS keyring 密钥存储
│   │   ├── schema/
│   │   │   └── registry.py         # JSON Schema 注册器
│   │   ├── middleware/
│   │   │   ├── auth.py             # JWT 验证中间件
│   │   │   ├── csrf.py             # Origin 检查
│   │   │   ├── rate_limit.py       # 滑动窗口限流
│   │   │   └── tenant.py           # 租户隔离
│   │   └── routers/
│   │       ├── auth.py             # 注册/登录/当前用户
│   │       ├── herbs.py            # 中药列表/搜索/详情
│   │       ├── formulas.py         # 方剂列表/详情/安全检查
│   │       ├── medicines.py        # 药箱 CRUD + drugClass
│   │       ├── chat.py             # AI 对话（SSE + 图片）
│   │       ├── safety.py           # 五层安全检查 V1/V2
│   │       ├── reminders.py        # 吃药提醒 CRUD + 今日
│   │       ├── constitution.py     # 体质问卷/评估/历史
│   │       ├── profile.py          # 健康档案 GET/PUT
│   │       ├── dashboard.py        # 首页统计
│   │       ├── daily_health.py     # 每日养生卡
│   │       ├── account.py          # PIPL 账户删除
│   │       ├── triage.py           # 儿童急症分诊
│   │       ├── backup.py           # AES-256-GCM 加密备份
│   │       └── health.py           # 健康检查
│   ├── cli.py                      # Typer CLI（30+ 命令）
│   ├── scripts/
│   │   ├── seed_herbs_batch{1,2,3}.py  # 203 味中药
│   │   └── seed_formulas.py            # 82 首方剂
│   ├── tests/                      # 485+ 个测试
│   ├── Dockerfile
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   │   ├── App.tsx                 # 路由 + 布局切换
│   │   ├── main.tsx                # 入口
│   │   ├── constants.ts            # 颜色/标签常量
│   │   ├── theme.ts                # AntD 主题（亮/暗）
│   │   ├── elderly-mode.css        # 长辈模式全局样式
│   │   ├── api/                    # 12 个 API 客户端
│   │   ├── components/
│   │   │   └── StatusTag.tsx       # 状态标签组件
│   │   ├── contexts/
│   │   │   └── ElderlyModeContext.tsx
│   │   ├── hooks/
│   │   │   ├── useAuth.tsx         # 认证状态
│   │   │   ├── useTheme.tsx        # 主题切换
│   │   │   ├── useSpeechRecognition.ts  # 语音输入
│   │   │   └── useSpeechSynthesis.ts    # 语音播报
│   │   ├── layouts/
│   │   │   ├── AppLayout.tsx       # 标准侧边栏布局
│   │   │   └── ElderlyLayout.tsx   # 长辈 3-Tab 布局
│   │   ├── pages/                  # 12 个页面
│   │   │   ├── Dashboard.tsx       # 首页
│   │   │   ├── HerbList.tsx        # 中药列表
│   │   │   ├── HerbDetail.tsx      # 中药详情
│   │   │   ├── FormulaList.tsx     # 方剂列表
│   │   │   ├── FormulaDetail.tsx   # 方剂详情
│   │   │   ├── MedicineList.tsx    # 药箱管理
│   │   │   ├── ChatPage.tsx        # AI 问答（语音+TTS）
│   │   │   ├── RemindersPage.tsx   # 吃药提醒
│   │   │   ├── ConstitutionPage.tsx # 体质自测
│   │   │   ├── ProfilePage.tsx     # 健康档案
│   │   │   ├── SettingsPage.tsx    # 设置
│   │   │   └── LoginPage.tsx       # 登录/注册
│   │   └── types/
│   │       └── speech.d.ts         # Web Speech API 类型
│   ├── e2e/                        # 83 个 E2E 测试
│   ├── Dockerfile
│   ├── nginx.conf
│   ├── vite.config.ts
│   ├── tsconfig.json
│   └── playwright.config.ts
│
└── data/                           # SQLite 数据库（Docker volume）
    └── homedoctor.db               # 生产数据，部署不删除
```

## API 参考

所有 API 需 Bearer Token 认证（除 `/api/auth/*` 和 `/api/health`）。

### 认证

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/register` | 注册（username, password）→ access_token |
| POST | `/api/auth/login` | 登录 → access_token |
| GET | `/api/auth/me` | 当前用户信息 |

### 中药

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/herbs` | 中药列表（分页：page, pageSize） |
| GET | `/api/herbs/search` | 全文搜索（q 参数，FTS5） |
| GET | `/api/herbs/{id}` | 中药详情 |

### 方剂

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/formulas` | 方剂列表（分页） |
| GET | `/api/formulas/{id}` | 方剂详情 |
| GET | `/api/formulas/{id}/safety-check` | 方剂五层安全检查 |

### 药箱

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/medicines` | 药品列表 |
| POST | `/api/medicines` | 添加药品 |
| PUT | `/api/medicines/{id}` | 更新药品 |
| DELETE | `/api/medicines/{id}` | 删除药品 |

### AI 对话

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/chat` | 发送消息（安全关键词拦截 → AI 回复） |
| GET | `/api/chat/history` | 对话历史 |
| POST | `/api/chat/conversations` | 创建会话 |

### 安全检查

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/safety/check-v2` | 五层安全检查（herbs[], medicines[], user_profile） |

**五层架构**：
1. **第1a层**：中药×中药配伍禁忌（十八反十九畏，数据库硬编码）
2. **第1b层**：中西药交互检查（R-01 至 R-10，drugClass 匹配）
3. **第2层**：剂量范围检查（herbs 表 dosage_min/max）
4. **第3层**：特殊人群（孕妇/3岁以下BLOCK/儿童/老年）
5. **第5层**：免责声明（始终附加）

### 体质

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/constitution/questionnaire` | 66 题问卷（9 种体质） |
| POST | `/api/constitution/assess` | 提交答案 → 主体质 + 兼夹 + 得分 |
| GET | `/api/constitution/history` | 评估历史 |
| GET | `/api/constitution/latest` | 最近评估 |

### 提醒

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/reminders` | 全部提醒 |
| POST | `/api/reminders` | 创建提醒 |
| GET | `/api/reminders/today` | 今日提醒（时间展开 + 状态） |
| PUT | `/api/reminders/{id}` | 更新提醒 |
| PUT | `/api/reminders/{id}/toggle` | 启用/暂停 |
| DELETE | `/api/reminders/{id}` | 删除提醒 |

### 健康档案

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/profile` | 获取档案 |
| PUT | `/api/profile` | 更新档案（体质自动同步） |

### 其他

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| GET | `/api/dashboard/stats` | 首页统计 |
| GET | `/api/daily-health` | 每日养生卡（24 节气） |

### 安全合规

| 方法 | 路径 | 说明 |
|------|------|------|
| DELETE | `/api/account` | PIPL 账户删除（硬删全量数据） |
| GET | `/api/account/preview` | 删除预览（各表数据计数） |
| POST | `/api/backup` | 创建 AES-256-GCM 加密备份 |
| GET | `/api/backup/list` | 备份列表（含加密标记） |
| POST | `/api/backup/restore` | 恢复备份（解密 → 重启生效） |

### 儿童急症分诊

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/triage/age-groups` | 年龄组列表（5 组） |
| GET | `/api/triage/questionnaire?age_months=X` | 年龄问卷 + 红旗症状清单 |
| GET | `/api/triage/red-flags` | 全部红旗症状 |
| POST | `/api/triage/assess` | 分诊评估 → 紧急/急诊/常规/居家护理 |

## CLI 命令

```bash
cd backend
python3 cli.py --help

# 示例
python3 cli.py herbs:search "黄芪"
python3 cli.py herbs:list --page 1
python3 cli.py formulas:detail "四物汤"
python3 cli.py safety:check --herbs "附子" --herbs "半夏"
python3 cli.py user:create --username testuser --password testpass123
```

## 测试

### 后端测试

```bash
cd backend
python3 -m pytest tests/ -v          # 全部 485+ 个测试
python3 -m pytest tests/ -k safety   # 只跑安全测试
python3 -m pytest tests/ -k triage   # 只跑分诊测试
python3 -m pytest tests/ -q          # 安静模式
```

### E2E 测试

```bash
cd frontend
npx playwright test                  # 全部 83 个测试
npx playwright test e2e/auth         # 只跑认证测试
npx playwright test --ui             # UI 模式
```

### 测试覆盖

| 文件 | 测试数 | 覆盖范围 |
|------|--------|---------|
| test_auth.py | ~15 | 注册/登录/JWT/隔离 |
| test_herbs.py | ~12 | 列表/搜索/详情/分页 |
| test_formulas.py | ~10 | 列表/详情 |
| test_medicines.py | ~12 | CRUD 全生命周期 |
| test_chat.py | 10 | 安全拦截/AI回复/历史 |
| test_safety.py + comprehensive | 41 | 十八反/十九畏/中西药交互/剂量/特殊人群 |
| test_safety_drugclass.py | 20 | drugClass 路由：西药/中药/中成药 |
| test_dashboard.py | 12 | 统计/数据一致性 |
| test_daily_health.py | 6 | 节气/养生卡 |
| test_reminders.py | 25 | CRUD/今日/状态/toggle |
| test_constitution.py | 42 | 问卷/评分/历史/档案 |
| test_formula_safety.py | 15 | 方剂联动安全检查 |
| test_rate_limit.py | 12 | 限流：通用/聊天/豁免/IP隔离 |
| test_account.py | ~8 | PIPL 删除：全表清除/审计 |
| test_backup_encryption.py | 17 | AES-256-GCM：加密/解密/兼容 |
| test_secrets.py | 19 | keyring：优先级/降级/配置 |
| test_triage.py | 119 | 分诊：年龄/红旗/阈值/端点 |
| test_audit.py | 9 | 审计链：hash/验证/排序 |
| test_hallucination_defense.py | 13 | AI幻觉防御/模型降级 |
| E2E (83 tests) | 83 | auth/dashboard/herbs/medicines/reminders/constitution/profile |

## 部署

### Docker 部署

```bash
./start.sh
```

`data/` 目录是 Docker named volume，部署更新不会丢失数据。

### 安全注意事项

1. **生产环境必须修改 SECRET_KEY**：`docker-compose.yml` 中 `HOMEDOCTOR_SECRET_KEY`
2. **SQLCipher 可选加密**：设置 `HOMEDOCTOR_DB_ENCRYPTION_KEY` 启用数据库级加密
3. **CORS 默认允许 localhost**：生产环境需配置 `ALLOWED_ORIGINS`
4. **限流已启用**：60/min 通用 API + 10/min LLM 端点，超出返回 429
5. **备份已加密**：AES-256-GCM + PBKDF2 密钥派生，明文即时删除
6. **API 密钥安全存储**：env → OS keyring → 本地文件 三级降级链

### 备份

```bash
# 通过 API 创建加密备份
curl -X POST http://localhost:8000/api/backup \
  -H "Authorization: Bearer <token>"

# 列出备份
curl http://localhost:8000/api/backup/list \
  -H "Authorization: Bearer <token>"

# 恢复（重启后生效）
curl -X POST http://localhost:8000/api/backup/restore \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"filename": "backup_20260617_120000.db.enc"}'
```

## 适老化设计

所有页面满足最低标准：

| 维度 | 标准 |
|------|------|
| 最小字体 | 16px（正文），长辈模式 18px |
| 触控目标 | ≥44px，长辈模式 ≥48px |
| 按钮文字 | 图标 + 文字，不纯图标 |
| 导航层级 | ≤2 层，长辈模式 3 Tab |
| 对比度 | WCAG AA ≥4.5:1 |

长辈模式（3 Tab）：首页 / AI语音问答 / 我的

## 安全体系

### 硬编码规则优先于 AI

```
用户请求 → 第1a层（中药配伍）→ 第1b层（中西药交互）→ 第2层（剂量）
         → 第3层（特殊人群）→ 第4层（AI分析）→ 第5层（免责声明）
```

硬编码层拦截不经过 AI，直接返回警告。

### 急症关键词（29 个）

含"急救""急诊""心梗""脑梗""休克"等 → 强制提示就医。

## 开发规范

详见 [AGENTS.md](./AGENTS.md)。

核心原则：
1. **配置驱动**：字段定义在 JSON，不在 DDL
2. **CLI for every API**：AI Agent 通过 CLI 调用
3. **递归收敛**：发现一个问题，消灭一类问题
4. **结构化是权威**：SQLite 写入，图谱派生
5. **部署绝不删数据**：`data/` 是 named volume
6. **中文领域语言**：枚举值用中文原文
7. **TDD**：先写失败测试 → 最小实现 → 全绿

## 版本

v0.3.0 — MVP P0/P1 gap 收尾（限流 + PIPL + 加密备份 + 分诊 + drugClass + 推理链 + 体质环 + 审计链）

## License

Private
