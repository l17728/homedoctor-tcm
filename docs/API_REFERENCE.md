# API Reference — 家庭医生

> Base URL: `http://localhost:8000`
> 所有需认证的端点在 Header 中携带 `Authorization: Bearer <token>`
> 401 响应自动触发前端跳转登录页

---

## 认证

### POST /api/auth/register

注册新用户。

**Request**
```json
{
  "username": "wangayi",
  "password": "mypassword123"
}
```

**Response 201**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "user": { "id": "uuid-xxx", "username": "wangayi" }
}
```

**Response 409** — 用户名已存在

### POST /api/auth/login

**Request**
```json
{
  "username": "wangayi",
  "password": "mypassword123"
}
```

**Response 200** — 同注册响应

### GET /api/auth/me

**Response 200**
```json
{
  "id": "uuid-xxx",
  "username": "wangayi"
}
```

<!-- BEGIN AUTO-GENERATED API ROUTES -->
## 自动生成的 API 路由索引

> 来源：FastAPI OpenAPI。运行 `python backend/scripts/gen_api_reference.py` 更新。

> 路由数：262

### account

- `DELETE /api/account` — Delete Account
- `GET /api/account/preview` — Preview Account Data

### ai-classify

- `POST /api/ai-classify/auto-tag` — Auto Tag Bookmarks
- `POST /api/ai-classify/duplicates` — Detect Duplicates；参数：请求体，必填：application/json
- `POST /api/ai-classify/merge` — Merge Entries；参数：请求体，必填：application/json
- `POST /api/ai-classify/suggest` — Suggest Tags；参数：请求体，必填：application/json

### auth

- `GET /api/auth/consent-status` — Consent Status
- `POST /api/auth/login` — Login；参数：请求体，必填：application/json
- `POST /api/auth/logout` — Logout
- `GET /api/auth/me` — Me
- `POST /api/auth/register` — Register；参数：请求体，必填：application/json

### backup

- `POST /api/backup` — Create Backup
- `GET /api/backup/list` — List Backups
- `POST /api/backup/restore` — Restore Backup；参数：请求体，必填：application/json

### bookmarks

- `GET /api/bookmarks` — List Bookmarks；参数：`entry_type`（query，可选）、`is_starred`（query，可选）、`tags`（query，可选）、`tag_logic`（query，可选）
- `POST /api/bookmarks` — Create Bookmark；参数：请求体，必填：application/json
- `POST /api/bookmarks/check` — Check Bookmark；参数：请求体，必填：application/json
- `GET /api/bookmarks/collections` — List Collections
- `POST /api/bookmarks/collections` — Create Collection；参数：请求体，必填：application/json
- `DELETE /api/bookmarks/collections/{collection_id}` — Delete Collection；参数：`collection_id`（path，必填）
- `GET /api/bookmarks/collections/{collection_id}` — Get Collection；参数：`collection_id`（path，必填）
- `POST /api/bookmarks/collections/{collection_id}/items` — Add To Collection；参数：`collection_id`（path，必填）、请求体，必填：application/json
- `DELETE /api/bookmarks/collections/{collection_id}/items/{bookmark_id}` — Remove From Collection；参数：`collection_id`（path，必填）、`bookmark_id`（path，必填）
- `DELETE /api/bookmarks/{bookmark_id}` — Delete Bookmark；参数：`bookmark_id`（path，必填）
- `GET /api/bookmarks/{bookmark_id}` — Get Bookmark；参数：`bookmark_id`（path，必填）
- `PUT /api/bookmarks/{bookmark_id}` — Update Bookmark；参数：`bookmark_id`（path，必填）、请求体，必填：application/json

### chat

- `POST /api/chat` — Chat；参数：请求体，必填：application/json
- `POST /api/chat/conversations` — Save Conversation；参数：请求体，必填：application/json
- `GET /api/chat/history` — List Conversations；参数：`page`（query，可选）、`pageSize`（query，可选）、`q`（query，可选）
- `POST /api/chat/image` — Chat With Image；参数：请求体，必填：multipart/form-data
- `POST /api/chat/save-card` — Save As Knowledge Card；参数：请求体，必填：application/json
- `POST /api/chat/stream` — Chat Stream；参数：请求体，必填：application/json

### classics

- `GET /api/classics` — List Classics；参数：`category`（query，可选）
- `DELETE /api/classics/annotations/{annotation_id}` — Delete Annotation；参数：`annotation_id`（path，必填）
- `PUT /api/classics/annotations/{annotation_id}` — Update Annotation；参数：`annotation_id`（path，必填）、请求体，必填：application/json
- `GET /api/classics/{classic_id}` — Get Classic；参数：`classic_id`（path，必填）
- `GET /api/classics/{classic_id}/chapters/{chapter_id}` — Get Chapter；参数：`classic_id`（path，必填）、`chapter_id`（path，必填）
- `GET /api/classics/{classic_id}/chapters/{chapter_id}/annotations` — List Annotations；参数：`classic_id`（path，必填）、`chapter_id`（path，必填）、`note_type`（query，可选）
- `POST /api/classics/{classic_id}/chapters/{chapter_id}/annotations` — Create Annotation；参数：`classic_id`（path，必填）、`chapter_id`（path，必填）、请求体，必填：application/json
- `POST /api/classics/{classic_id}/chapters/{chapter_id}/ask` — Ask About Chapter；参数：`classic_id`（path，必填）、`chapter_id`（path，必填）、请求体，必填：application/json
- `PUT /api/classics/{classic_id}/chapters/{chapter_id}/study-notes` — Save Study Notes；参数：`classic_id`（path，必填）、`chapter_id`（path，必填）、请求体，必填：application/json
- `POST /api/classics/{classic_id}/chapters/{chapter_id}/translate` — Translate Chapter；参数：`classic_id`（path，必填）、`chapter_id`（path，必填）、请求体，可选：application/json
- `PUT /api/classics/{classic_id}/chapters/{chapter_id}/translation` — Save Translation；参数：`classic_id`（path，必填）、`chapter_id`（path，必填）、请求体，必填：application/json
- `GET /api/classics/{classic_id}/study-notes` — Get Study Notes；参数：`classic_id`（path，必填）、`chapter_id`（query，可选）
- `POST /api/classics/{classic_id}/summarize` — Summarize Classic；参数：`classic_id`（path，必填）、请求体，必填：application/json

### comparisons

- `POST /api/comparisons/formulas` — Compare Formulas；参数：请求体，必填：application/json
- `POST /api/comparisons/herbs` — Compare Herbs；参数：请求体，必填：application/json
- `GET /api/comparisons/herbs/{herb_a}/{herb_b}` — Compare Two Herbs；参数：`herb_a`（path，必填）、`herb_b`（path，必填）

### constitution

- `POST /api/constitution/assess` — Assess；参数：请求体，必填：application/json
- `GET /api/constitution/history` — Get History
- `GET /api/constitution/latest` — Get Latest
- `GET /api/constitution/questionnaire` — Get Questionnaire

### daily-health

- `GET /api/daily-health` — Get Daily Health Card

### dashboard

- `GET /api/dashboard/stats` — Get Dashboard Stats

### export

- `GET /api/export` — Export User Data

### extractor

- `POST /api/extractor/auto-extract` — Auto Extract Endpoint
- `POST /api/extractor/extract` — Extract Endpoint；参数：请求体，必填：application/json
- `GET /api/extractor/recent` — Recent Extractions；参数：`limit`（query，可选）

### family-members

- `GET /api/family-members` — List Family Members
- `POST /api/family-members` — Create Family Member；参数：请求体，必填：application/json
- `POST /api/family-members/clear-switch` — Clear Member Switch
- `GET /api/family-members/current` — Get Current Member
- `DELETE /api/family-members/{member_id}` — Delete Family Member；参数：`member_id`（path，必填）
- `PUT /api/family-members/{member_id}` — Update Family Member；参数：`member_id`（path，必填）、请求体，必填：application/json
- `POST /api/family-members/{member_id}/switch` — Switch Member；参数：`member_id`（path，必填）

### favorites

- `GET /api/favorites` — List Favorites；参数：`entry_type`（query，可选）、`is_starred`（query，可选）
- `POST /api/favorites` — Create Favorite；参数：请求体，必填：application/json
- `POST /api/favorites/check` — Check Favorite；参数：请求体，必填：application/json
- `DELETE /api/favorites/{entry_id}` — Delete Favorite；参数：`entry_id`（path，必填）
- `GET /api/favorites/{entry_id}` — Get Favorite；参数：`entry_id`（path，必填）
- `PUT /api/favorites/{entry_id}` — Update Favorite；参数：`entry_id`（path，必填）、请求体，必填：application/json

### formulas

- `GET /api/formulas` — List Formulas；参数：`page`（query，可选）、`pageSize`（query，可选）、`category`（query，可选）
- `GET /api/formulas/{formula_id}` — Get Formula；参数：`formula_id`（path，必填）
- `GET /api/formulas/{formula_id}/roles` — Get Formula Herb Roles；参数：`formula_id`（path，必填）
- `GET /api/formulas/{formula_id}/safety-check` — Check Formula Safety；参数：`formula_id`（path，必填）
- `GET /api/formulas/{formula_id}/safety-text` — Formula Safety Text；参数：`formula_id`（path，必填）
- `GET /api/formulas/{formula_id}/tree` — Get Formula Tree；参数：`formula_id`（path，必填）

### formulations

- `POST /api/formulations/from-inventory` — From Inventory Endpoint；参数：请求体，必填：application/json
- `POST /api/formulations/joint-recommend` — Joint Recommend Endpoint；参数：请求体，必填：application/json
- `POST /api/formulations/recommend` — Recommend Endpoint；参数：请求体，必填：application/json
- `POST /api/formulations/tea-recipe` — Tea Recipe Endpoint；参数：请求体，必填：application/json

### health

- `GET /api/health` — Health Check

### health-logs

- `GET /api/health-logs` — List Health Logs；参数：`days`（query，可选）
- `POST /api/health-logs` — Create Health Log；参数：请求体，必填：application/json
- `GET /api/health-logs/latest` — Get Latest Health Log
- `DELETE /api/health-logs/{log_id}` — Delete Health Log；参数：`log_id`（path，必填）
- `GET /api/health-logs/{log_id}` — Get Health Log；参数：`log_id`（path，必填）
- `PUT /api/health-logs/{log_id}` — Update Health Log；参数：`log_id`（path，必填）、请求体，必填：application/json

### herbs

- `GET /api/herbs` — List Herbs；参数：`page`（query，可选）、`pageSize`（query，可选）、`category`（query，可选）
- `GET /api/herbs/search` — Search Herbs；参数：`q`（query，必填）
- `GET /api/herbs/{herb_id}` — Get Herb；参数：`herb_id`（path，必填）
- `PATCH /api/herbs/{herb_id}/aliases` — Update Herb Aliases；参数：`herb_id`（path，必填）、请求体，必填：application/json
- `GET /api/herbs/{herb_id}/formulas` — Get Herb Formulas；参数：`herb_id`（path，必填）

### index-management

- `POST /api/admin/deletion-execute` — Execute Deletion；参数：请求体，必填：application/json
- `POST /api/admin/deletion-exempt` — Add Exemption；参数：请求体，必填：application/json
- `DELETE /api/admin/deletion-exempt/{target_id}` — Remove Exemption；参数：`target_id`（path，必填）
- `GET /api/admin/deletion-exemptions` — List Exemptions
- `GET /api/admin/deletion-recommendations` — Get Recommendations；参数：`days_threshold`（query，可选）、`min_hits`（query，可选）、`limit`（query，可选）
- `GET /api/admin/index-stats` — Index Stats

### knowledge-browse

- `GET /api/knowledge/browse` — Browse；参数：`type`（query，必填）、`category`（query，可选）、`q`（query，可选）、`page`（query，可选）、`page_size`（query，可选）
- `GET /api/knowledge/categories` — List Categories
- `POST /api/knowledge/{entity_id}/append` — Request Append；参数：`entity_id`（path，必填）、请求体，必填：application/json
- `GET /api/knowledge/{entity_id}/append/history` — Append History；参数：`entity_id`（path，必填）
- `GET /api/knowledge/{entity_id}/note` — Get Note；参数：`entity_id`（path，必填）
- `PUT /api/knowledge/{entity_id}/note` — Save Note；参数：`entity_id`（path，必填）、请求体，必填：application/json

### knowledge-graph

- `GET /api/kg/graph` — Get Graph；参数：`types`（query，可选）、`q`（query，可选）、`limit`（query，可选）
- `GET /api/kg/node/{node_id}` — Get Node；参数：`node_id`（path，必填）
- `POST /api/kg/rebuild` — Rebuild
- `GET /api/kg/snapshot/{node_type}/{node_id}` — Get Snapshot；参数：`node_type`（path，必填）、`node_id`（path，必填）、`depth`（query，可选）

### knowledge-hub

- `GET /api/knowledge-hub/entities/{entity_id}` — Entity Detail Endpoint；参数：`entity_id`（path，必填）
- `PUT /api/knowledge-hub/entities/{entity_id}` — Update Entity Endpoint；参数：`entity_id`（path，必填）、请求体，必填：application/json
- `GET /api/knowledge-hub/entities/{entity_id}/relationships` — Entity Relationships Endpoint；参数：`entity_id`（path，必填）、`direction`（query，可选）
- `POST /api/knowledge-hub/entities/{entity_id}/relationships` — Create Relationship Endpoint；参数：`entity_id`（path，必填）、请求体，必填：application/json
- `POST /api/knowledge-hub/entities/{entity_id}/view` — View Endpoint；参数：`entity_id`（path，必填）
- `POST /api/knowledge-hub/import` — Import Endpoint；参数：请求体，必填：application/json
- `POST /api/knowledge-hub/import-file` — Import File Endpoint；参数：`title`（query，可选）、请求体，必填：multipart/form-data
- `POST /api/knowledge-hub/import-url` — Import Url Endpoint；参数：请求体，必填：application/json
- `POST /api/knowledge-hub/import-video-url` — Import Video Url Endpoint；参数：请求体，必填：application/json
- `GET /api/knowledge-hub/popular` — Popular Endpoint；参数：`limit`（query，可选）
- `GET /api/knowledge-hub/recent` — Recent Endpoint；参数：`limit`（query，可选）
- `GET /api/knowledge-hub/relationship-types` — Relationship Types Endpoint
- `GET /api/knowledge-hub/search` — Search Endpoint；参数：`q`（query，可选）、`type`（query，可选）、`category`（query，可选）、`tag`（query，可选）、`page`（query，可选）、`page_size`（query，可选）
- `GET /api/knowledge-hub/types` — Types Endpoint

### knowledge-import

- `GET /api/knowledge-import/recent` — Recent Imports；参数：`limit`（query，可选）
- `POST /api/knowledge-import/upload` — Upload；参数：请求体，必填：multipart/form-data
- `POST /api/knowledge-import/upload-batch` — Upload Batch；参数：请求体，必填：multipart/form-data
- `DELETE /api/knowledge-import/{entry_id}` — Delete Import；参数：`entry_id`（path，必填）

### medical-visits

- `GET /api/visits` — List Visits；参数：`page`（query，可选）、`page_size`（query，可选）
- `POST /api/visits` — Create Visit；参数：请求体，必填：application/json
- `POST /api/visits/ocr` — Ocr Lab Report；参数：请求体，必填：multipart/form-data
- `DELETE /api/visits/{visit_id}` — Delete Visit；参数：`visit_id`（path，必填）
- `GET /api/visits/{visit_id}` — Get Visit；参数：`visit_id`（path，必填）
- `PUT /api/visits/{visit_id}` — Update Visit；参数：`visit_id`（path，必填）、请求体，必填：application/json

### medication-plans

- `GET /api/medication-plans` — List Plans
- `POST /api/medication-plans` — Create Plan；参数：请求体，必填：application/json
- `POST /api/medication-plans/auto-schedule` — Auto Schedule；参数：请求体，必填：application/json
- `POST /api/medication-plans/auto-schedule/expert-review` — Expert Review；参数：请求体，必填：application/json
- `POST /api/medication-plans/auto-schedule/verify` — Verify Schedule；参数：请求体，必填：application/json
- `DELETE /api/medication-plans/{plan_id}` — Delete Plan；参数：`plan_id`（path，必填）
- `GET /api/medication-plans/{plan_id}` — Get Plan；参数：`plan_id`（path，必填）
- `PUT /api/medication-plans/{plan_id}` — Update Plan；参数：`plan_id`（path，必填）、请求体，必填：application/json
- `POST /api/medication-plans/{plan_id}/pause` — Pause Plan；参数：`plan_id`（path，必填）
- `POST /api/medication-plans/{plan_id}/resume` — Resume Plan；参数：`plan_id`（path，必填）

### medicine-ocr

- `POST /api/medicines/barcode-lookup` — Barcode Lookup；参数：请求体，必填：application/json
- `POST /api/medicines/ocr-recognize` — Ocr Recognize；参数：请求体，必填：multipart/form-data

### medicines

- `GET /api/medicines` — List Medicines；参数：`page`（query，可选）、`pageSize`（query，可选）
- `POST /api/medicines` — Create Medicine；参数：请求体，必填：application/json
- `GET /api/medicines/alerts/expiring` — Get Medicine Alerts
- `GET /api/medicines/quality-alerts` — Get Quality Alerts
- `DELETE /api/medicines/{medicine_id}` — Delete Medicine；参数：`medicine_id`（path，必填）
- `GET /api/medicines/{medicine_id}` — Get Medicine；参数：`medicine_id`（path，必填）
- `PUT /api/medicines/{medicine_id}` — Update Medicine；参数：`medicine_id`（path，必填）、请求体，必填：application/json
- `GET /api/medicines/{medicine_id}/quality` — Get Medicine Quality；参数：`medicine_id`（path，必填）

### model-registry

- `GET /api/agent/logs` — Get Logs；参数：`entity_id`（query，可选）、`action_type`（query，可选）、`page`（query，可选）、`page_size`（query，可选）
- `GET /api/agent/logs/{log_id}` — Get Log；参数：`log_id`（path，必填）
- `PUT /api/agent/logs/{log_id}/review` — Review Log；参数：`log_id`（path，必填）、请求体，必填：application/json
- `POST /api/agent/process` — Process Knowledge；参数：请求体，必填：application/json
- `GET /api/models` — Get Models；参数：`enabled_only`（query，可选）
- `POST /api/models` — Add Model；参数：请求体，必填：application/json
- `POST /api/models/vote` — Vote；参数：请求体，必填：application/json
- `DELETE /api/models/{model_id}` — Remove Model；参数：`model_id`（path，必填）
- `PUT /api/models/{model_id}` — Edit Model；参数：`model_id`（path，必填）、请求体，必填：application/json

### notifications

- `GET /api/notifications` — List Notifications
- `POST /api/notifications/{notification_id}/read` — Mark Notification Read；参数：`notification_id`（path，必填）

### p2-features

- `POST /api/admin/freshness-check` — Freshness Check
- `GET /api/admin/freshness-stats` — Freshness Stats
- `POST /api/chat/{conversation_id}/summarize` — Summarize Conversation；参数：`conversation_id`（path，必填）、请求体，必填：application/json
- `GET /api/knowledge/{entity_id}/feedback` — Get Feedback；参数：`entity_id`（path，必填）
- `POST /api/knowledge/{entity_id}/feedback` — Submit Feedback；参数：`entity_id`（path，必填）、请求体，必填：application/json

### p3-features

- `GET /api/admin/agent/config` — Get Agent Config；参数：`agent_name`（query，可选）
- `PUT /api/admin/agent/config` — Set Agent Config；参数：请求体，必填：application/json
- `GET /api/admin/agent/conversations` — List Agent Conversations；参数：`agent_name`（query，可选）、`limit`（query，可选）
- `GET /api/admin/agent/memories` — List Agent Memories；参数：`agent_name`（query，可选）、`memory_type`（query，可选）、`q`（query，可选）、`limit`（query，可选）
- `POST /api/admin/agent/memories` — Save Agent Memory；参数：请求体，必填：application/json
- `DELETE /api/admin/agent/memories/{memory_id}` — Delete Agent Memory；参数：`memory_id`（path，必填）
- `POST /api/admin/agent/optimize-prompt` — Optimize Agent Prompt；参数：请求体，必填：application/json
- `POST /api/admin/community-consensus-scan` — Community Consensus Scan
- `POST /api/admin/feeder/scan` — Feeder Scan；参数：`max_feeds`（query，可选）
- `POST /api/admin/knowledge/scan-all` — Comprehensive Knowledge Scan；参数：请求体，可选：application/json
- `POST /api/admin/translate-check` — Translate Check
- `POST /api/admin/url-health-check` — Url Health Check
- `GET /api/admin/url-health-stats` — Url Health Stats
- `GET /api/user/interests` — Get User Interests

### personal-knowledge

- `GET /api/personal/edges` — List Edges；参数：`relationship_type`（query，可选）
- `POST /api/personal/edges` — Create Edge；参数：请求体，必填：application/json
- `DELETE /api/personal/edges/{edge_id}` — Delete Edge；参数：`edge_id`（path，必填）
- `GET /api/personal/graph` — Personal Graph
- `GET /api/personal/symptoms` — List Symptoms
- `POST /api/personal/symptoms` — Log Symptom；参数：请求体，必填：application/json

### prescriptions

- `POST /api/prescriptions/generate` — Generate Prescription；参数：请求体，必填：application/json
- `POST /api/prescriptions/health-report` — Generate Health Report；参数：请求体，必填：application/json

### profile

- `GET /api/profile` — Get Profile
- `PUT /api/profile` — Update Profile；参数：请求体，必填：application/json

### push

- `GET /api/push/config` — Get Push Config
- `DELETE /api/push/subscriptions` — Unsubscribe Push；参数：请求体，必填：application/json
- `POST /api/push/subscriptions` — Subscribe Push；参数：请求体，必填：application/json

### rag

- `POST /api/rag/index/rebuild` — Rag Index Rebuild
- `GET /api/rag/index/status` — Rag Index Status
- `GET /api/rag/intent` — Rag Intent；参数：`q`（query，必填）
- `GET /api/rag/search` — Rag Search；参数：`q`（query，必填）、`top_k`（query，可选）、`rerank`（query，可选）

### reminders

- `GET /api/reminders` — List Reminders；参数：`enabled`（query，可选）
- `POST /api/reminders` — Create Reminder；参数：请求体，必填：application/json
- `GET /api/reminders/history` — Get Reminder History；参数：`days`（query，可选）
- `GET /api/reminders/today` — Get Today Reminders
- `DELETE /api/reminders/{reminder_id}` — Delete Reminder；参数：`reminder_id`（path，必填）
- `GET /api/reminders/{reminder_id}` — Get Reminder；参数：`reminder_id`（path，必填）
- `PUT /api/reminders/{reminder_id}` — Update Reminder；参数：`reminder_id`（path，必填）、请求体，必填：application/json
- `POST /api/reminders/{reminder_id}/check-in` — Check In Reminder；参数：`reminder_id`（path，必填）、请求体，必填：application/json
- `PUT /api/reminders/{reminder_id}/toggle` — Toggle Reminder；参数：`reminder_id`（path，必填）

### remote-assist

- `GET /api/remote-assist/consent` — Get Share Consent
- `PUT /api/remote-assist/consent` — Set Share Consent；参数：请求体，必填：application/json
- `POST /api/remote-assist/invite` — Invite Viewer；参数：请求体，必填：application/json
- `DELETE /api/remote-assist/invite/{share_id}` — Revoke Share；参数：`share_id`（path，必填）
- `GET /api/remote-assist/shared-with-me` — List Shared With Me
- `POST /api/remote-assist/{user_id}/alert` — Set Alert Thresholds；参数：`user_id`（path，必填）、请求体，必填：application/json
- `GET /api/remote-assist/{user_id}/alerts` — Check Alerts；参数：`user_id`（path，必填）
- `GET /api/remote-assist/{user_id}/missed-alerts` — Get Missed Alerts；参数：`user_id`（path，必填）
- `GET /api/remote-assist/{user_id}/summary` — Get Health Summary；参数：`user_id`（path，必填）
- `GET /api/remote-assist/{user_id}/weekly-report` — Get Weekly Report；参数：`user_id`（path，必填）

### reports

- `GET /api/reports/constitution` — Get Constitution Report
- `POST /api/reports/generate-pdf` — Generate Pdf；参数：请求体，必填：application/json
- `GET /api/reports/health-trend` — Get Health Trend Report；参数：`period`（query，可选）
- `GET /api/reports/pre-visit` — Get Pre Visit Report

### safety

- `POST /api/safety/check` — Safety Check；参数：请求体，必填：application/json
- `POST /api/safety/check-v2` — Safety Check V2；参数：请求体，必填：application/json

### schemas

- `GET /api/schemas` — List Schemas
- `GET /api/schemas/{node_type}` — Get Schema；参数：`node_type`（path，必填）

### seasonal-health

- `GET /api/seasonal-health` — Get Seasonal Health；参数：`term`（query，可选）

### share-cards

- `POST /api/share-cards/generate` — Generate Card；参数：请求体，必填：application/json
- `GET /api/share-cards/list` — List Cards
- `POST /api/share-cards/monthly-report` — Create Monthly Report；参数：请求体，可选：application/json
- `GET /api/share-cards/monthly-report/latest` — Get Latest Monthly Report
- `DELETE /api/share-cards/{card_id}` — Delete Card；参数：`card_id`（path，必填）
- `GET /api/share-cards/{card_id}` — Get Card；参数：`card_id`（path，必填）

### smart-search

- `GET /api/smart-search` — Smart Search；参数：`q`（query，必填）、`top_k`（query，可选）
- `POST /api/smart-search/expand` — Expand Search；参数：请求体，必填：application/json
- `POST /api/smart-search/import` — Import Web Result；参数：请求体，必填：application/json

### therapies

- `GET /api/therapies` — List Therapies；参数：`page`（query，可选）、`pageSize`（query，可选）、`category`（query，可选）
- `GET /api/therapies/categories` — List Categories
- `GET /api/therapies/search` — Search Therapies；参数：`q`（query，必填）、`category`（query，可选）
- `GET /api/therapies/{therapy_id}` — Get Therapy；参数：`therapy_id`（path，必填）
- `GET /api/therapies/{therapy_id}/safety` — Get Therapy Safety；参数：`therapy_id`（path，必填）

### triage

- `GET /api/triage/age-groups` — Get Age Groups
- `POST /api/triage/assess` — Assess；参数：请求体，必填：application/json
- `GET /api/triage/questionnaire` — Get Questionnaire；参数：`age_months`（query，可选）、`age_group`（query，可选）
- `GET /api/triage/red-flags` — Get Red Flags

### unified-knowledge

- `GET /api/knowledge/acupoints` — List Acupoints；参数：`q`（query，可选）、`meridian`（query，可选）、`page`（query，可选）、`page_size`（query，可选）
- `GET /api/knowledge/acupoints/{entity_id}` — Get Acupoint；参数：`entity_id`（path，必填）
- `GET /api/knowledge/formulas` — List Formulas；参数：`q`（query，可选）、`category`（query，可选）、`page`（query，可选）、`page_size`（query，可选）
- `GET /api/knowledge/formulas/{entity_id}` — Get Formula；参数：`entity_id`（path，必填）
- `GET /api/knowledge/graph/{entity_id}` — Get Graph；参数：`entity_id`（path，必填）、`hops`（query，可选）
- `GET /api/knowledge/herbs` — List Herbs；参数：`q`（query，可选）、`category`（query，可选）、`page`（query，可选）、`page_size`（query，可选）
- `GET /api/knowledge/herbs/{entity_id}` — Get Herb；参数：`entity_id`（path，必填）
- `GET /api/knowledge/meridians` — List Meridians；参数：`q`（query，可选）、`category`（query，可选）
- `GET /api/knowledge/meridians/{entity_id}` — Get Meridian；参数：`entity_id`（path，必填）
- `GET /api/knowledge/search` — Unified Search；参数：`q`（query，必填）、`type`（query，可选）、`page`（query，可选）、`page_size`（query，可选）
- `GET /api/knowledge/symptoms` — List Symptoms；参数：`q`（query，可选）、`page`（query，可选）、`page_size`（query，可选）
- `GET /api/knowledge/therapies` — List Therapies；参数：`q`（query，可选）、`category`（query，可选）、`page`（query，可选）、`page_size`（query，可选）
- `GET /api/knowledge/therapies/{entity_id}` — Get Therapy；参数：`entity_id`（path，必填）

### voice

- `POST /api/voice/qa` — Voice Qa；参数：请求体，必填：multipart/form-data
- `POST /api/voice/synthesize` — Synthesize；参数：请求体，必填：application/json
- `POST /api/voice/transcribe` — Transcribe；参数：请求体，必填：multipart/form-data
<!-- END AUTO-GENERATED API ROUTES -->
