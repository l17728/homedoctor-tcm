# Backend — 家庭医生 API

FastAPI + aiosqlite + JWT + FTS5 全文搜索。

## 快速开始

```bash
pip install -r requirements.txt

# 初始化数据库 + 种子数据
python3 scripts/seed_herbs_batch1.py
python3 scripts/seed_herbs_batch2.py
python3 scripts/seed_herbs_batch3.py
python3 scripts/seed_formulas.py

# 启动
uvicorn app.main:app --reload --port 8000

# API 文档
# http://localhost:8000/docs (Swagger UI)
# http://localhost:8000/redoc (ReDoc)
```

## 架构

```
请求 → AuthMiddleware (JWT) → CsrfMiddleware (Origin) → RateLimitMiddleware
     → APIRouter → Depends(get_current_user) → Repository (tenant_id)
     → DbAdapter (aiosqlite) → SQLite
```

### 数据层

```
DbAdapter (ABC)
  └── SqliteAdapter (aiosqlite 封装)
Repository (所有 SQL 通过 adapter)
  └── 每个 Repository 方法强制 tenant_id 过滤
JSON Schema (config/schemas/*.json)
  └── SchemaRegistry 加载 + 校验
```

### 认证

- **密码哈希**: Argon2id (passlib)
- **JWT**: python-jose，HS256 签名
- **依赖注入**: `Depends(get_current_user)` 从 Bearer token 提取用户
- **租户隔离**: `contextvars.ContextVar('tenant_id')`

### 安全引擎（五层）

```
run_safety_check(herbs, medicines, user_profile)
  → Layer 1a: 中药配伍禁忌（DB safety_rules, rule_type='配伍禁忌'）
  → Layer 1b: 中西药交互（DB safety_rules, rule_type='中西药交互'）
  → Layer 2: 剂量检查（herbs 表 dosage_min_g/dosage_max_g）
  → Layer 3: 特殊人群（孕妇/儿童<3 BLOCK/3-14/老年65+）
  → Layer 4: AI 辅助分析（MVP placeholder）
  → Layer 5: 免责声明（始终附加）
  → SafetyCheckResult { safe, warnings[], disclaimer }
```

详见 `docs/SAFETY_DESIGN.md`。

### 24 节气算法

`solar_terms.py` — 天文近似算法 + 查表，计算当前节气和养生建议。

### 体质评分

`constitution.py` — 王琦九种体质标准量表：
- 66 题（每种体质 6-8 题）
- 5 级评分（没有=0 到 总是=4）
- 得分 = (该体质总分 / 最大可能分) × 100
- 判定：≥60% 为该体质"是"，最高分偏颇体质为主体质

## 数据库表

| 表 | 说明 |
|----|------|
| users | 用户（id, username, password_hash, tenant_id） |
| herbs | 中药（id, name, properties JSON, FTS5） |
| herbs_fts | 全文搜索虚拟表 |
| formulas | 方剂（id, name, properties JSON, FTS5） |
| formulas_fts | 全文搜索虚拟表 |
| medicines | 药箱（user_id 关联） |
| reminders | 吃药提醒（user_id, times JSON, enabled） |
| constitution_assessments | 体质评估记录 |
| user_profiles | 健康档案 |
| safety_rules | 硬编码安全规则（60+ 条） |
| chat_conversations | 对话会话 |
| chat_messages | 对话消息 |
| audit_log | 审计日志（hash 链） |

## 种子数据

| 脚本 | 数据量 | 说明 |
|------|--------|------|
| seed_herbs_batch1.py | 50 味中药 | 补气药/补血药/补阴药/补阳药/清热药 |
| seed_herbs_batch2.py | 50 味中药 | 解表药/祛风湿药/化湿药/利水渗湿药 |
| seed_herbs_batch3.py | 103 味中药 | 温里药/理气药/消食药/止血药/活血化瘀药/化痰止咳平喘药/安神药/平肝息风药/开窍药/收涩药/攻毒杀虫止痒药/拔毒化腐生肌药 |
| seed_formulas.py | 82 首方剂 | 解表剂/泻下剂/和解剂/清热剂/温里剂/补益剂/安神剂/开窍剂/理气剂/理血剂/治风剂/治燥剂/祛湿剂/祛痰剂/消食剂/驱虫剂/痈疡剂 |

安全规则在 `database.py` 的 `seed_safety_rules()` 函数中硬编码，数据库初始化时自动写入。

## 测试

```bash
# 全量
python3 -m pytest tests/ -v                    # 190 tests

# 按模块
python3 -m pytest tests/test_safety_comprehensive.py -v
python3 -m pytest tests/test_reminders.py -v
python3 -m pytest tests/test_constitution.py -v

# 按关键词
python3 -m pytest tests/ -k "safety" -v
python3 -m pytest tests/ -k "constitution" -v
```

| 测试文件 | 数量 | 覆盖 |
|---------|------|------|
| test_auth.py | ~15 | 注册/登录/JWT/用户隔离 |
| test_herbs.py | ~12 | 列表/FTS5搜索/详情/分页 |
| test_formulas.py | ~10 | 列表/详情 |
| test_medicines.py | ~12 | CRUD 全生命周期 |
| test_chat.py | 10 | 急症拦截/AI回复/历史 |
| test_safety.py | ~6 | V1 安全检查基础 |
| test_safety_comprehensive.py | 41 | 十八反×10/中西药交互×10/剂量×5/特殊人群×8/免责×3/集成×5 |
| test_dashboard.py | 12 | 统计准确性/数据一致性 |
| test_daily_health.py | 6 | 节气计算/养生建议 |
| test_reminders.py | 25 | CRUD/今日展开/toggle/状态/验证 |
| test_constitution.py | 42 | 问卷/评分/历史/档案同步/兼夹体质 |
| test_formula_safety.py | 15 | 方剂→herb提取→安全检查 |
| test_health.py | ~4 | 健康检查端点 |

## CLI

```bash
python3 cli.py --help

# 用户管理
python3 cli.py users:list
python3 cli.py users:create --username USER --password PASS

# 中药
python3 cli.py herbs:list --page 1
python3 cli.py herbs:search --query "黄芪"
python3 cli.py herbs:detail --id HERB_ID

# 方剂
python3 cli.py formulas:list
python3 cli.py formulas:detail --id FORMULA_ID

# 安全
python3 cli.py safety:check --herbs "附子" --herbs "半夏"
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `HOMEDOCTOR_DATABASE_URL` | `data/homedoctor.db` | SQLite 路径 |
| `HOMEDOCTOR_SECRET_KEY` | `change-me-in-production` | JWT 签名密钥 |
| `DATABASE_URL` | `sqlite:///data/family-doctor.db` | 种子脚本使用 |
