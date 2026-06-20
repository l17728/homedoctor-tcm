# 家庭医生 · 您的养生助手

> Local-first TCM (Traditional Chinese Medicine) health intelligence platform. 银发用户优先，家庭健康管家。

## 功能概览

### 核心功能
- **统一知识库** — 实体注册 + 关系引擎 + AI导入（分类/标签/摘要/关键信息提取）+ 拖拽上传 + 关联可视化
- **RAG 语义搜索** — BGE-M3 向量嵌入 + BM25 关键词 + RRF 融合 + 意图路由（browse/exact/concept/complex）+ 可选 reranker
- **知识图谱** — AntV G6 可视化（中药-方剂-症状-穴位-配伍关系网络）+ 3跳多跳遍历 + 从实体关系自动重建
- **AI 健康问答** — SSE 流式输出 + 推理链面板 + 多模型投票 + 幻觉三层防御 + 语音输入 + TTS + 多模态图片问答 + **知识图谱上下文注入**（自动检测实体 → 2跳关系遍历 → system prompt）
- **中医药知识库** — 300+ 味中药 + 82 首方剂 + 105 项外治理疗，FTS5 全文搜索 + 拼音搜索
- **经络穴位** — 14经络（十二正经+任督二脉）+ 75常用穴位（定位/刺法/灸法/主治/配伍/特定穴分类）+ 经络浏览器 + 穴位详情
- **养生功法** — 太极拳/八段锦/金刚功/长寿功/站桩/打坐/五禽戏/易筋经/六字诀等15核心功法 + 10门派 + 15变体；每功法含精要/心法/呼吸/步骤/功效/禁忌 + 体质适配 + 经络疏通关联
- **中药炮制品** — 炙甘草/酒黄精/法半夏/醋柴胡/熟地黄/制首乌等20种炮制品独立节点 + 炮制关系（同药不同制法 = 不同药性）
- **经典读诵** — 黄帝内经/伤寒论/金匮要略等 5 部经典，双栏阅读器 + 选中批注 + AI 问答 + 文言文翻译 + 学习心得
- **智能服药排程** — 7天排程表 + 安全冲突自动隔开 + 多AI专家评审 + 一键药箱安全检查
- **五层安全检查** — 十八反十九畏 + 中西药交互（drugClass 感知）+ 剂量 + 特殊人群 + 免责声明 + 累积毒性 + 肝肾检查
- **儿童急症分诊** — 5 年龄组 × 8 红旗症状 × 12 步评估 + 50+ 急症关键词同义词匹配
- **体质自测** — 王琦九种体质标准量表（66 题）+ 主体质/兼夹判定
- **智能配伍引擎** — 症状→中药推荐 + 代茶饮一键配方（毒性/交互检查）+ 药箱优先推荐
- **用药管理** — 提醒 + 用药套餐（多药计划）+ 打卡追踪 + 漏服补打 + 浏览器通知推送
- **家庭药箱** — CRUD + drugClass + 过期预警 + 变质检测 + 库存预警 + 拍照 OCR 录入
- **健康档案** — 基本信息 + 体质 + 过敏 + 孕期 + 家庭成员切换 + 每日健康打卡（血压/血糖/体重）
- **个人知识层** — tenant 模型：家庭私有边指向全局实体（has_symptom/takes/has_constitution），不创建重复节点
- **报告体系** — 体质报告 + 健康趋势（SVG图表）+ 就诊准备 + 月度家庭报告
- **外治理疗** — 针刺(20)/推拿(18)/中药外治(15)/灸法(14)/拔罐(12)/刺血(10)/刮痧(10) 共7类105条
- **多源知识采集** — PDF/Word/TXT/图片 OCR + URL/文章/视频链接 + MP3/MP4上传 + Ctrl+V粘贴 + whisper转录 + **视频关键帧提取**（ffmpeg场景检测 + Vision LLM分析）
- **知识提取 AI** — 对话→结构化知识自动沉淀 + AI 分类管理（标签/去重/合并）+ 实体过滤器自动扫描
- **书签系统** — 多态书签 + 合集 + 标签 + 对比分析
- **处方单 PDF** — 一键生成 A4 处方单（君臣佐使 + 用法 + 医嘱）
- **家庭分享卡** — 可视化健康概览卡 + 月度家庭健康报告
- **子女远程协助** — 健康监控 + 每周摘要 + 告警阈值 + 漏服推送
- **每日养生卡** — 24 节气养生建议
- **安全合规** — 限流 + PIPL 同意/删除 + AES-256-GCM 加密备份 + OS keyring + 审计链 + 食物禁忌检查

### 技术特性
- **响应式布局** — 手机/平板/桌面自适应（抽屉菜单 + 表格滚动 + Drawer 全宽）
- **长辈模式** — 5 Tab 简化界面 + 18px 大字体 + 底部导航
- **配置驱动** — JSON Schema 定义字段，SchemaField 组件自动渲染表单
- **多端语音** — 浏览器 Web Speech API + 后端 ASR/TTS 端点

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | FastAPI + aiosqlite + python-jose (JWT) + passlib (Argon2id) + cryptography (AES-256-GCM) |
| 前端 | React 18 + TypeScript + Ant Design 5 + Vite + AntV G6 |
| 数据库 | SQLite + FTS5 + SQLCipher 可选加密 |
| 部署 | Docker Compose + Nginx 反向代理 |
| 测试 | pytest（1070+ 后端）+ Playwright E2E |

## 快速开始

```bash
./start.sh    # Docker 一键启动
```

- 前端：`http://localhost:3000`
- API：`http://localhost:8000`
- 文档：`http://localhost:8000/docs`

## 项目统计

| 指标 | 数量 |
|------|------|
| API 路由 | 200+ |
| 数据库表 | 36+ |
| 后端测试 | 1584 |
| 前端页面 | 34 |
| E2E 测试 | 300+ |
| 中药数据 | 303 味 |
| 方剂数据 | 82 首 |
| 经络穴位 | 14经络 + 75穴 |
| 养生功法 | 15核心 + 10门派 + 15变体 |
| 炮制品 | 20种（炙甘草/酒黄精/熟地黄等） |
| 外治理疗 | 7类105条 |
| 知识实体 | 1594+ |
| 实体关系 | 2874+ |
| RAG 语义索引 | 1536+ chunks (BGE-M3 1024dim) |
| 医学经典 | 5 部（12+ 章节） |
| 安全规则 | 67 条 |

## API 参考

所有 API 需 Bearer Token 认证（除 `/api/auth/*`、`/api/health`、`/api/herbs`、`/api/formulas`、`/api/classics`、`/api/therapies`、`/api/triage/*`）。

### 认证与账户
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/register` | 注册（含 PIPL 同意） |
| POST | `/api/auth/login` | 登录 |
| GET | `/api/auth/me` | 当前用户 |
| GET | `/api/auth/consent-status` | 同意状态 |
| GET | `/api/account/preview` | 数据概况 |
| DELETE | `/api/account` | PIPL 账户删除 |

### 知识库
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/herbs` | 中药列表（分页+分类） |
| GET | `/api/herbs/search` | 全文搜索（FTS5+拼音） |
| GET | `/api/herbs/{id}` | 中药详情 |
| GET | `/api/herbs/{id}/formulas` | 含此药的方剂+常用配伍 |
| GET | `/api/formulas` | 方剂列表 |
| GET | `/api/formulas/{id}` | 方剂详情（含君臣佐使） |
| GET | `/api/formulas/{id}/tree` | 方剂演化树 |
| GET | `/api/formulas/{id}/safety-check` | 方剂安全检查 |
| GET | `/api/therapies` | 外治理疗列表 |
| GET | `/api/therapies/{id}` | 理疗详情 |

### 经典读诵
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/classics` | 经典书柜 |
| GET | `/api/classics/{id}/chapters/{ch_id}` | 章节原文+翻译+批注 |
| POST | `/api/classics/{id}/chapters/{ch_id}/annotations` | 创建批注 |
| POST | `/api/classics/{id}/chapters/{ch_id}/ask` | AI 问答 |
| POST | `/api/classics/{id}/chapters/{ch_id}/translate` | AI 翻译 |
| PUT | `/api/classics/{id}/chapters/{ch_id}/study-notes` | 学习心得 |

### AI 与配伍
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/chat` | AI 对话 |
| POST | `/api/chat/stream` | SSE 流式对话 |
| POST | `/api/chat/image` | 多模态图片问答 |
| POST | `/api/formulations/recommend` | 症状→中药推荐 |
| POST | `/api/formulations/tea-recipe` | 代茶饮配方 |
| POST | `/api/extractor/auto-extract` | AI 知识自动提取 |

### 安全与分诊
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/safety/check-v2` | 五层安全检查 |
| GET | `/api/triage/questionnaire` | 儿童分诊问卷 |
| POST | `/api/triage/assess` | 分诊评估 |

### 健康管理
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/dashboard/stats` | 首页统计 |
| GET/POST | `/api/reminders` | 提醒 CRUD |
| GET/POST | `/api/medication-plans` | 用药套餐 |
| GET/POST | `/api/medicines` | 药箱 CRUD |
| GET | `/api/medicines/{id}/quality` | 药品变质检测 |
| GET/POST | `/api/constitution/*` | 体质自测 |
| GET/PUT | `/api/profile` | 健康档案 |

### 知识图谱与书签
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/kg/graph` | 知识图谱全览 |
| GET | `/api/kg/snapshot/{type}/{id}` | BFS 邻域 |
| POST | `/api/kg/rebuild` | 重建派生边 |
| GET/POST | `/api/bookmarks` | 书签 CRUD + 合集 |
| POST | `/api/comparisons/herbs` | 中药对比 |

### 报告与分享
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/reports/constitution` | 体质报告 |
| GET | `/api/reports/health-trend` | 健康趋势 |
| GET | `/api/reports/pre-visit` | 就诊准备 |
| POST | `/api/prescriptions/generate` | 处方单 PDF |
| POST | `/api/share-cards/generate` | 健康分享卡 |
| POST | `/api/share-cards/monthly-report` | 月度家庭报告 |

### 备份与导入
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/backup` | AES-256-GCM 加密备份 |
| POST | `/api/knowledge-import/upload` | PDF/Word/TXT/OCR 导入 |
| GET | `/api/export` | 全量数据导出 |

## CLI

```bash
cd backend && python3 cli.py --help
# 40+ 命令：herbs/formulas/safety/reminders/constitution/profile/chat/
# triage/account/schemas/favorites/family-members/medication-plans 等
```

## 测试

```bash
cd backend && python3 -m pytest tests/ -v    # 1070+ 个测试
cd frontend && npx playwright test            # E2E 测试
```

## 部署

```bash
./start.sh    # Docker 一键启动（含种子数据自动加载）
```

`data/` 目录是 Docker named volume，部署更新不丢失数据。

### 安全注意事项
1. **SECRET_KEY**：`docker-compose.yml` 中 `HOMEDOCTOR_SECRET_KEY`
2. **SQLCipher**：`HOMEDOCTOR_DB_ENCRYPTION_KEY` 启用数据库加密
3. **限流**：60/min 通用 + 10/min LLM 端点
4. **备份加密**：AES-256-GCM + PBKDF2 密钥派生
5. **API 密钥**：env → OS keyring → 本地文件 三级降级

## 适老化设计

| 维度 | 标准 |
|------|------|
| 最小字体 | 16px（正文），长辈模式 18px |
| 触控目标 | ≥44px |
| 按钮文字 | 图标 + 文字 |
| 导航层级 | ≤2 层 |
| 响应式 | 手机/平板/桌面自适应 |

## 开发规范

详见 [AGENTS.md](./AGENTS.md)。

核心原则：配置驱动 · CLI for every API · 递归收敛 · 结构化权威 · 部署不删数据 · 中文领域语言 · TDD

## 版本

v0.7.0 — 养生功法 + 中药炮制品 + 经络穴位 + RAG语义搜索 + Phase 2统一模型 + 图谱上下文

## License

Private
