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
app/db/
  ├── adapter.py    — DbAdapter ABC + SqliteAdapter (aiosqlite 封装) + set_db/get_db
  ├── schema.py     — DDL_STATEMENTS (45 张表) + FTS5 索引 + 触发器
  ├── migrations.py — _migrate_* + init_db (ALTER TABLE + 索引迁移)
  └── seeds.py      — seed_safety_rules (67条) + seed_test_data + seed_therapy_data
app/database.py     — 薄 re-export 层（31行，向后兼容）
```

### Agent 工具层

```
app/tools/
  ├── pipeline.py   — 知识管道（extract→analyze→scan→dedup→quality→create→index→push）
  ├── review.py     — 多模型评审 + 冲突检测
  ├── entities.py   — 实体管理（provenance/auto_relate/CRUD/list）
  └── config.py     — 配置管理 + 提示词优化 + 经验泛化 + 配置持久化
app/agent_tools.py  — log_action + 薄 re-export 层（87行）
```

### 认证

- **密码哈希**: Argon2id (passlib)
- **JWT**: python-jose，HS256 签名
- **依赖注入**: `Depends(get_current_user)` 从 Bearer token 提取用户
- **租户隔离**: `contextvars.ContextVar('tenant_id')`
- **中间件链**: AuthMiddleware → RequestAuditMiddleware → CsrfMiddleware → TenantMiddleware → RateLimitMiddleware

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

## 数据库表（45 张）

| 分类 | 表 | 说明 |
|------|----|------|
| 用户 | users, user_profiles, family_members | 用户/档案/家庭成员 |
| 中药 | herbs, herbs_fts, formulas, formulas_fts, therapies, therapies_fts | 中药/方剂/理疗 + FTS5全文索引 |
| 药箱 | medicines, medication_plans, medication_logs | 药箱/用药套餐/服药记录 |
| 提醒 | reminders | 吃药提醒（times JSON, enabled） |
| 健康 | constitution_assessments, daily_health_logs, health_logs, medical_visits | 体质/每日打卡/健康日志/就诊记录 |
| 安全 | safety_rules, safety_keywords | 安全规则（67条）+ 急症关键词 |
| 对话 | conversations, chat_messages, chat_conversations | AI对话历史 |
| 知识 | knowledge_entities, entity_relationships, knowledge_chunks, chunk_embeddings, knowledge_conflicts, knowledge_feedback, knowledge_provenance | 统一知识模型 |
| Agent | agent_logs, agent_memories, agent_conversations, agent_configs | Agent日志/记忆/对话/配置持久化 |
| 模型 | ai_models | AI模型注册表（华为云4模型） |
| 系统 | audit_log, user_interest_profiles, user_notes, bookmarks, comparison_results, favorites, share_cards, backup_history, classics, classic_chapters, classic_annotations, acupoints, meridians, health_practices, practice_variants, processed_herbs | 审计/兴趣/笔记/书签/分享/备份/经典/穴位/功法 |

## Agent 系統

### 8步知識管道（knowledge_agent.py）

```
process_input(db, content/url/title, source_type)
  Step 0: 回讀記憶（memory_search 過去教訓）
  Step 1: 提取（tool_extract）
  Step 2: 分析（tool_analyze + 動態分類 classify_category）
  Step 3: 實體掃描（tool_scan_entities）
  Step 4: 去重（tool_check_duplicates）
  Step 5: 質評 + 多AI評審（tool_assess_quality + tool_multi_model_review）
  Step 5b: 衝突檢測（tool_detect_conflicts）
  Step 6: 入庫 + 血緣（tool_create_or_update_entity + tool_record_provenance）
  Step 7: 增量索引 + 外部內容索引（tool_build_index + tool_index_external_content）
  Step 7b: 自動關聯（tool_auto_relate）
  Step 8: 推送模塊 + 記憶沉澱（tool_push_to_modules + memory_save）
```

### 信任分級 SABC

```
S — 系統權威（種子數據、教材、藥典）
A — 權威來源（官方網站、期刊、AI評審通過）
B — 用戶導入（博客、微信文章）
C — 網頁搜索結果

自動升降級：
  升級：B→A（5+好評/0差評/7天+）→ A→S（10+好評/0差評/30天+）
  降級：3+差評/舉報 → pending_admin_review → 管理員確認降級
```

### 巡檢Agent 定時調度

```
scheduler.py — asyncio 24h 循環
  → run_feeder_scan(db, max_feeds=10)
    → _detect_gaps（發現缺失字段的實體）
    → _search_tcm_content（Exa API web search）
    → _feed_url → process_input（管道處理）
```

### 可觀測性

```
中間件日誌鏈：
  AuthMiddleware    → AUTH_OK/FAIL（user, tenant, path, ip）
  RequestAuditMiddleware → REQ（method, path, user, status, duration_ms）
  CsrfMiddleware    → CSRF_REJECT（origin, path, method）
  RateLimitMiddleware → RATE_LIMIT（ip, path, retry_after）
  TenantMiddleware  → TENANT（tenant, member, path）
```

## 种子数据

| 脚本 | 数据量 | 说明 |
|------|--------|------|
| seed_herbs_batch1.py | 50 味中药 | 补气药/补血药/补阴药/补阳药/清热药 |
| seed_herbs_batch2.py | 50 味中药 | 解表药/祛风湿药/化湿药/利水渗湿药 |
| seed_herbs_batch3.py | 103 味中药 | 温里药/理气药/消食药/止血药/活血化瘀药/化痰止咳平喘药/安神药/平肝息风药/开窍药/收涩药/攻毒杀虫止痒药/拔毒化腐生肌药 |
| seed_formulas.py | 82 首方剂 | 解表剂/泻下剂/和解剂/清热剂/温里剂/补益剂/安神剂/开窍剂/理气剂/理血剂/治风剂/治燥剂/祛湿剂/祛痰剂/消食剂/驱虫剂/痈疡剂 |

安全规则在 `app/db/seeds.py` 的 `seed_safety_rules()` 函数中硬编码，数据库初始化时自动写入。

## 测试

```bash
# 全量
python3 -m pytest tests/ -q                    # 2,000+ tests, 84%+ coverage

# 覆盖率报告
python3 -m pytest tests/ --cov=app --cov-report=term-missing

# 按模块
python3 -m pytest tests/test_safety_comprehensive.py -v
python3 -m pytest tests/test_agent_config_group.py -v
python3 -m pytest tests/test_llm_unified.py -v

# 按关键词
python3 -m pytest tests/ -k "safety" -v
```

| 测试文件 | 数量 | 覆盖 |
|---------|------|------|
| test_auth.py | ~15 | 注册/登录/JWT/用户隔离 |
| test_herbs.py | ~12 | 列表/FTS5搜索/详情/分页 |
| test_safety_comprehensive.py | 41 | 十八反/中西药交互/剂量/特殊人群 |
| test_agent_config_group.py | 24 | 配置管理/提示詞優化/經驗泛化 |
| test_agent_entities_group.py | 16 | 實體管理/關係引擎/auto_relate |
| test_agent_review_pipeline_group.py | 11 | 多模型評審/管道核心 |
| test_llm_unified.py | 11 | llm_chat/collective_review/opencode |
| test_knowledge_feeder.py | 10 | 巡檢Agent/gap檢測/URL餵入 |
| test_agent_communication.py | 19 | Agent消息/辯論/自動執行 |
| test_smart_search_router.py | 10 | 智能搜索/擴展/導入/web search |
| test_review_tools.py | 19 | 多模型評審/衝突檢測/解決 |
| test_trust_upgrade.py | 8 | 信任自動升級(B→A→S) |
| test_scheduler.py | 7 | 定時調度器生命周期 |
| test_visits_browse.py | 12 | 就診CRUD/知識瀏覽 |
| test_share_cards.py | 27 | 分享卡/月度報告 |

## CLI

```bash
python3 cli.py --help

# 中药
python3 cli.py herbs:list --page 1
python3 cli.py herbs:search --query "黄芪"
python3 cli.py herbs:detail --id HERB_ID

# 方剂
python3 cli.py formulas:list
python3 cli.py formulas:detail --id FORMULA_ID

# 安全
python3 cli.py safety:check --herbs "附子" --herbs "半夏"

# 任意 API 路由（适用于尚无领域专用命令的端点）
python3 cli.py api:request GET /api/auth/me --token "$TOKEN"
python3 cli.py api:request POST /api/constitution/assess --body '{"answers":[]}'
python3 cli.py auth:logout --token "$TOKEN"
python3 cli.py api:request POST /api/knowledge-import/upload --token "$TOKEN" --file source.pdf --file-field file
# 多文件端点可重复传入 --file，并按路由字段名设置 --file-field（例如 files）
```

CLI 提供专用领域命令作为常用入口，覆盖 262 个 OpenAPI API 操作中的 126 个；
`api:request METHOD PATH` 可调用全部 `/api/` 路由。它只连接配置的本机服务地址，不访问数据库；可用
`--token` 传 Bearer token、`--query` 和 `--body` 传 JSON，`--form`/`--file` 处理表单
与上传，`--output` 保存非 JSON 响应。`tests/test_cli_smoke.py` 会将 OpenAPI 每个方法/路径与专用命令或该通用命令的
覆盖能力对照；当前 OpenAPI 没有排除的 API 路由，框架默认路由不属于 `/api/`。

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `HOMEDOCTOR_DATABASE_URL` | `data/homedoctor.db` | SQLite 路径 |
| `HOMEDOCTOR_SECRET_KEY` | `change-me-in-production` | JWT 签名密钥 |
| `DATABASE_URL` | `sqlite:///data/family-doctor.db` | 种子脚本使用 |
