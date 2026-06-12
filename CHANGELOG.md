# Changelog

本文件记录"家庭医生"项目的所有版本变更。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

---

## [0.2.0] — 2026-06-12

### Added — P0 功能补全

#### 后端
- **吃药提醒系统**：完整 CRUD + 今日提醒时间展开 + 启用/暂停 toggle
  - `POST/GET/PUT/DELETE /api/reminders`
  - `GET /api/reminders/today`（待服/已服/漏服状态计算）
  - 25 个测试
- **体质自测系统**：王琦九种体质标准量表
  - 66 题问卷（9 种体质，每种 6-8 题）
  - `POST /api/constitution/assess`（五级评分 + 主体质/兼夹判定）
  - `GET /api/constitution/questionnaire|history|latest`
  - 体质结果自动同步到用户档案
  - 42 个测试
- **健康档案 API**：`GET/PUT /api/profile`
  - 基本信息（昵称/性别/出生年份/身高/体重/血型）
  - 过敏史（数组）、健康问题（数组）、孕期标记
- **方剂安全检查联动**：`GET /api/formulas/{id}/safety-check`
  - 从方剂 properties 提取 herb names（支持文本格式 + 数组格式）
  - 调用五层安全引擎检查
  - 15 个测试

#### 前端
- **3 个新页面**：
  - `RemindersPage`：今日提醒卡片 + 全部提醒表格 + Drawer 表单
  - `ConstitutionPage`：问卷分页 + 五级评分 + 结果雷达图 + 历史
  - `ProfilePage`：基本信息/体质信息/健康信息三段式
- **长辈模式**：
  - `ElderlyModeContext`（localStorage 持久化）
  - `ElderlyLayout`（3 Tab 底部导航：首页/AI问答/我的）
  - `elderly-mode.css`（18px 字体，48px 触控目标）
  - Settings 确认弹窗切换
- **语音输入**：
  - `useSpeechRecognition` hook（Web Speech API，zh-CN）
  - `useSpeechSynthesis` hook（TTS，rate=0.9）
  - ChatPage 集成：麦克风按钮（录音红色脉冲）+ TTS 播报开关
  - 不支持时优雅降级
- **3 个 API 客户端**：reminderApi / constitutionApi / profileApi
- **路由更新**：App.tsx 添加 4 新路由 + ElderlyModeProvider + LayoutSwitch
- **菜单更新**：AppLayout 添加"提醒"+"健康（体质/档案）"菜单组

#### E2E 测试（+46 cases，总计 83）
- `reminders.spec.ts`（13）：导航/创建/今日/toggle/删除/AuthGuard
- `constitution.spec.ts`（11）：介绍页/问卷流程/分页/结果/AuthGuard
- `profile-elderly.spec.ts`（22）：档案 CRUD/体质信息/长辈模式全生命周期

### Changed
- AppLayout 菜单新增 ClockCircleOutlined / HeartOutlined 图标导入
- SettingsPage 新增长辈模式 Switch + Modal.confirm
- ChatPage 重构：语音输入栏 + TTS 开关 + pulse 动画
- main.tsx 导入 elderly-mode.css
- 版本号 0.1.0 → 0.2.0

### Stats
- 后端测试：102 → 190（+88）
- 前端 src 文件：25 → 39（+14）
- E2E 测试：37 → 83（+46）
- Commit: `ed75b9b` `f30f06d` `adb7bb8`

---

## [0.1.0] — 2026-06-11

### Added — MVP 初始交付（Phase 1 Week 1-12）

#### Week 1-2：技术基座（`460c909`）
- FastAPI 后端：29 个 Python 文件
  - JWT 认证（python-jose + Argon2id）
  - DbAdapter + Repository 模式（tenant_id 隔离）
  - 中间件链：Auth → CSRF → RateLimit
  - 9 个 CLI 命令（typer + httpx）
  - 33 个测试
- React 前端：25 个 src 文件
  - Ant Design 5 + Vite + TypeScript
  - 9 个页面（Dashboard/HerbList/HerbDetail/FormulaList/FormulaDetail/MedicineList/ChatPage/SettingsPage/LoginPage）
  - useAuth / useTheme hooks
  - AppLayout（侧边栏 + 深色模式）
- Docker Compose + named data volume
- 37 个 Playwright E2E 测试

#### Week 3-4：数据入库（`354d533`）
- 203 味中药（20 个分类，覆盖全部中药学分类）
- 82 首方剂（17 个分类，覆盖方剂学分类）
- 4 个种子脚本（batch1-3 + formulas）
- 0 重复数据

#### Week 5-8：核心功能（`232d00b`）
- AI 对话：`POST /api/chat`（安全关键词拦截 → AI 回复）
- 每日养生卡：`GET /api/daily-health`（24 节气算法）
- Dashboard 统计：`GET /api/dashboard/stats`（实时计数）
- 29 个急症关键词模块
- 前端 API 连接（herbs/formulas/medicines/dashboard/chat）
- 28 个新测试（总计 61）

#### Week 9-10：安全加固（`d1cbb65`）
- **五层安全检查引擎**（`app/safety_engine.py`，290 行）
  - 第1a层：中药配伍禁忌（十八反十九畏）
  - 第1b层：中西药交互（R-01 至 R-10）
  - 第2层：剂量范围检查
  - 第3层：特殊人群（孕妇/儿童<3 BLOCK/3-14/老年65+）
  - 第4层：AI 辅助分析（MVP placeholder）
  - 第5层：免责声明
- 新端点：`POST /api/safety/check-v2`
- 41 个安全测试（总计 102）

#### Week 11-12：部署就绪（`4dffd34`）
- Backend Dockerfile（Python 3.10-slim + seed + uvicorn）
- Frontend Dockerfile（多阶段：node:22 → nginx:alpine）
- nginx.conf（SPA fallback + /api 反向代理）
- `start.sh`（一键启动 + 健康检查等待）
- `smoke_test.sh`（10 项冒烟测试）
- docker-compose.yml 修复 env var 对齐

### Stats
- 后端测试：0 → 102
- 前端文件：0 → 25
- E2E 测试：0 → 37
- 中药数据：0 → 203
- 方剂数据：0 → 82
- 安全规则：0 → 60+
- Commit: `eafbab3` `460c909` `354d533` `232d00b` `d1cbb65` `4dffd34`

---

## [Unreleased]

### Planned — V2 功能
- 知识图谱可视化（Neo4j / 内存图）
- 多模型 AI 对比
- 加减变化四层模型
- 语音备忘转写
- OCR 检查报告上传
- 疗效追踪（症状日历 + 趋势图）
- 子女远程协助模式
