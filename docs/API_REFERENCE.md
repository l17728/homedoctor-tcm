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

## 自动生成的 API 路由索引

> 生成日期：2026-10-15。重新运行 `python scripts/gen_api_reference.py` 更新。

### account

- `DELETE /api/account` — Delete Account
- `GET /api/account/preview` — Preview Account Data

### ai-classify

- `POST /api/ai-classify/auto-tag` — Auto Tag Bookmarks
- `POST /api/ai-classify/duplicates` — Detect Duplicates；请求体
- `POST /api/ai-classify/merge` — Merge Entries；请求体
- `POST /api/ai-classify/suggest` — Suggest Tags；请求体

### auth

- `GET /api/auth/consent-status` — Consent Status
- `POST /api/auth/login` — Login；请求体
- `POST /api/auth/logout` — Logout
- `GET /api/auth/me` — Me
- `POST /api/auth/register` — Register；请求体

### backup

- `POST /api/backup` — Create Backup
- `GET /api/backup/list` — List Backups
- `POST /api/backup/restore` — Restore Backup；请求体

### bookmarks

- `GET /api/bookmarks` — List Bookmarks；参数：`entry_type` (query), `is_starred` (query), `tags` (query), `tag_logic` (query)
- `POST /api/bookmarks` — Create Bookmark；请求体
- `POST /api/bookmarks/check` — Check Bookmark；请求体
- `GET /api/bookmarks/collections` — List Collections
- `POST /api/bookmarks/collections` — Create Collection；请求体
- `DELETE /api/bookmarks/collections/{collection_id}` — Delete Collection；参数：`collection_id` (path)
- `GET /api/bookmarks/collections/{collection_id}` — Get Collection；参数：`collection_id` (path)
- `POST /api/bookmarks/collections/{collection_id}/items` — Add To Collection；参数：`collection_id` (path)；请求体
- `DELETE /api/bookmarks/collections/{collection_id}/items/{bookmark_id}` — Remove From Collection；参数：`collection_id` (path), `bookmark_id` (path)
- `DELETE /api/bookmarks/{bookmark_id}` — Delete Bookmark；参数：`bookmark_id` (path)
- `GET /api/bookmarks/{bookmark_id}` — Get Bookmark；参数：`bookmark_id` (path)
- `PUT /api/bookmarks/{bookmark_id}` — Update Bookmark；参数：`bookmark_id` (path)；请求体

### chat

- `POST /api/chat` — Chat；请求体
- `POST /api/chat/conversations` — Save Conversation；请求体
- `GET /api/chat/history` — List Conversations；参数：`page` (query), `pageSize` (query), `q` (query)
- `POST /api/chat/image` — Chat With Image；请求体
- `POST /api/chat/save-card` — Save As Knowledge Card；请求体
- `POST /api/chat/stream` — Chat Stream；请求体

### classics

- `GET /api/classics` — List Classics；参数：`category` (query)
- `DELETE /api/classics/annotations/{annotation_id}` — Delete Annotation；参数：`annotation_id` (path)
- `PUT /api/classics/annotations/{annotation_id}` — Update Annotation；参数：`annotation_id` (path)；请求体
- `GET /api/classics/{classic_id}` — Get Classic；参数：`classic_id` (path)
- `GET /api/classics/{classic_id}/chapters/{chapter_id}` — Get Chapter；参数：`classic_id` (path), `chapter_id` (path)
- `GET /api/classics/{classic_id}/chapters/{chapter_id}/annotations` — List Annotations；参数：`classic_id` (path), `chapter_id` (path), `note_type` (query)
- `POST /api/classics/{classic_id}/chapters/{chapter_id}/annotations` — Create Annotation；参数：`classic_id` (path), `chapter_id` (path)；请求体
- `POST /api/classics/{classic_id}/chapters/{chapter_id}/ask` — Ask About Chapter；参数：`classic_id` (path), `chapter_id` (path)；请求体
- `PUT /api/classics/{classic_id}/chapters/{chapter_id}/study-notes` — Save Study Notes；参数：`classic_id` (path), `chapter_id` (path)；请求体
- `POST /api/classics/{classic_id}/chapters/{chapter_id}/translate` — Translate Chapter；参数：`classic_id` (path), `chapter_id` (path)；请求体
- `PUT /api/classics/{classic_id}/chapters/{chapter_id}/translation` — Save Translation；参数：`classic_id` (path), `chapter_id` (path)；请求体
- `GET /api/classics/{classic_id}/study-notes` — Get Study Notes；参数：`classic_id` (path), `chapter_id` (query)
- `POST /api/classics/{classic_id}/summarize` — Summarize Classic；参数：`classic_id` (path)；请求体

### comparisons

- `POST /api/comparisons/formulas` — Compare Formulas；请求体
- `POST /api/comparisons/herbs` — Compare Herbs；请求体
- `GET /api/comparisons/herbs/{herb_a}/{herb_b}` — Compare Two Herbs；参数：`herb_a` (path), `herb_b` (path)

### constitution

- `POST /api/constitution/assess` — Assess；请求体
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
- `POST /api/extractor/extract` — Extract Endpoint；请求体
- `GET /api/extractor/recent` — Recent Extractions；参数：`limit` (query)

### family-members

- `GET /api/family-members` — List Family Members
- `POST /api/family-members` — Create Family Member；请求体
- `POST /api/family-members/clear-switch` — Clear Member Switch
- `GET /api/family-members/current` — Get Current Member
- `DELETE /api/family-members/{member_id}` — Delete Family Member；参数：`member_id` (path)
- `PUT /api/family-members/{member_id}` — Update Family Member；参数：`member_id` (path)；请求体
- `POST /api/family-members/{member_id}/switch` — Switch Member；参数：`member_id` (path)

### favorites

- `GET /api/favorites` — List Favorites；参数：`entry_type` (query), `is_starred` (query)
- `POST /api/favorites` — Create Favorite；请求体
- `POST /api/favorites/check` — Check Favorite；请求体
- `DELETE /api/favorites/{entry_id}` — Delete Favorite；参数：`entry_id` (path)
- `GET /api/favorites/{entry_id}` — Get Favorite；参数：`entry_id` (path)
- `PUT /api/favorites/{entry_id}` — Update Favorite；参数：`entry_id` (path)；请求体

### formulas

- `GET /api/formulas` — List Formulas；参数：`page` (query), `pageSize` (query), `category` (query)
- `GET /api/formulas/{formula_id}` — Get Formula；参数：`formula_id` (path)
- `GET /api/formulas/{formula_id}/roles` — Get Formula Herb Roles；参数：`formula_id` (path)
- `GET /api/formulas/{formula_id}/safety-check` — Check Formula Safety；参数：`formula_id` (path)
- `GET /api/formulas/{formula_id}/safety-text` — Formula Safety Text；参数：`formula_id` (path)
- `GET /api/formulas/{formula_id}/tree` — Get Formula Tree；参数：`formula_id` (path)

### formulations

- `POST /api/formulations/from-inventory` — From Inventory Endpoint；请求体
- `POST /api/formulations/joint-recommend` — Joint Recommend Endpoint；请求体
- `POST /api/formulations/recommend` — Recommend Endpoint；请求体
- `POST /api/formulations/tea-recipe` — Tea Recipe Endpoint；请求体

### health

- `GET /api/health` — Health Check

### health-logs

- `GET /api/health-logs` — List Health Logs；参数：`days` (query)
- `POST /api/health-logs` — Create Health Log；请求体
- `GET /api/health-logs/latest` — Get Latest Health Log
- `DELETE /api/health-logs/{log_id}` — Delete Health Log；参数：`log_id` (path)
- `GET /api/health-logs/{log_id}` — Get Health Log；参数：`log_id` (path)
- `PUT /api/health-logs/{log_id}` — Update Health Log；参数：`log_id` (path)；请求体

### herbs

- `GET /api/herbs` — List Herbs；参数：`page` (query), `pageSize` (query), `category` (query)
- `GET /api/herbs/search` — Search Herbs；参数：`q` (query)
- `GET /api/herbs/{herb_id}` — Get Herb；参数：`herb_id` (path)
- `GET /api/herbs/{herb_id}/formulas` — Get Herb Formulas；参数：`herb_id` (path)

### index-management

- `POST /api/admin/deletion-execute` — Execute Deletion；请求体
- `POST /api/admin/deletion-exempt` — Add Exemption；请求体
- `DELETE /api/admin/deletion-exempt/{target_id}` — Remove Exemption；参数：`target_id` (path)
- `GET /api/admin/deletion-exemptions` — List Exemptions
- `GET /api/admin/deletion-recommendations` — Get Recommendations；参数：`days_threshold` (query), `min_hits` (query), `limit` (query)
- `GET /api/admin/index-stats` — Index Stats

### knowledge-browse

- `GET /api/knowledge/browse` — Browse；参数：`type` (query), `category` (query), `q` (query), `page` (query), `page_size` (query)
- `GET /api/knowledge/categories` — List Categories
- `POST /api/knowledge/{entity_id}/append` — Request Append；参数：`entity_id` (path)；请求体
- `GET /api/knowledge/{entity_id}/append/history` — Append History；参数：`entity_id` (path)
- `GET /api/knowledge/{entity_id}/note` — Get Note；参数：`entity_id` (path)
- `PUT /api/knowledge/{entity_id}/note` — Save Note；参数：`entity_id` (path)；请求体

### knowledge-graph

- `GET /api/kg/graph` — Get Graph；参数：`types` (query), `q` (query), `limit` (query)
- `GET /api/kg/node/{node_id}` — Get Node；参数：`node_id` (path)
- `POST /api/kg/rebuild` — Rebuild
- `GET /api/kg/snapshot/{node_type}/{node_id}` — Get Snapshot；参数：`node_type` (path), `node_id` (path), `depth` (query)

### knowledge-hub

- `GET /api/knowledge-hub/entities/{entity_id}` — Entity Detail Endpoint；参数：`entity_id` (path)
- `PUT /api/knowledge-hub/entities/{entity_id}` — Update Entity Endpoint；参数：`entity_id` (path)；请求体
- `GET /api/knowledge-hub/entities/{entity_id}/relationships` — Entity Relationships Endpoint；参数：`entity_id` (path), `direction` (query)
- `POST /api/knowledge-hub/entities/{entity_id}/relationships` — Create Relationship Endpoint；参数：`entity_id` (path)；请求体
- `POST /api/knowledge-hub/entities/{entity_id}/view` — View Endpoint；参数：`entity_id` (path)
- `POST /api/knowledge-hub/import` — Import Endpoint；请求体
- `POST /api/knowledge-hub/import-file` — Import File Endpoint；参数：`title` (query)；请求体
- `POST /api/knowledge-hub/import-url` — Import Url Endpoint；请求体
- `POST /api/knowledge-hub/import-video-url` — Import Video Url Endpoint；请求体
- `GET /api/knowledge-hub/popular` — Popular Endpoint；参数：`limit` (query)
- `GET /api/knowledge-hub/recent` — Recent Endpoint；参数：`limit` (query)
- `GET /api/knowledge-hub/relationship-types` — Relationship Types Endpoint
- `GET /api/knowledge-hub/search` — Search Endpoint；参数：`q` (query), `type` (query), `category` (query), `tag` (query), `page` (query), `page_size` (query)
- `GET /api/knowledge-hub/types` — Types Endpoint

### knowledge-import

- `GET /api/knowledge-import/recent` — Recent Imports；参数：`limit` (query)
- `POST /api/knowledge-import/upload` — Upload；请求体
- `POST /api/knowledge-import/upload-batch` — Upload Batch；请求体
- `DELETE /api/knowledge-import/{entry_id}` — Delete Import；参数：`entry_id` (path)

### medical-visits

- `GET /api/visits` — List Visits；参数：`page` (query), `page_size` (query)
- `POST /api/visits` — Create Visit；请求体
- `POST /api/visits/ocr` — Ocr Lab Report；请求体
- `DELETE /api/visits/{visit_id}` — Delete Visit；参数：`visit_id` (path)
- `GET /api/visits/{visit_id}` — Get Visit；参数：`visit_id` (path)
- `PUT /api/visits/{visit_id}` — Update Visit；参数：`visit_id` (path)；请求体

### medication-plans

- `GET /api/medication-plans` — List Plans
- `POST /api/medication-plans` — Create Plan；请求体
- `POST /api/medication-plans/auto-schedule` — Auto Schedule；请求体
- `POST /api/medication-plans/auto-schedule/expert-review` — Expert Review；请求体
- `POST /api/medication-plans/auto-schedule/verify` — Verify Schedule；请求体
- `DELETE /api/medication-plans/{plan_id}` — Delete Plan；参数：`plan_id` (path)
- `GET /api/medication-plans/{plan_id}` — Get Plan；参数：`plan_id` (path)
- `PUT /api/medication-plans/{plan_id}` — Update Plan；参数：`plan_id` (path)；请求体
- `POST /api/medication-plans/{plan_id}/pause` — Pause Plan；参数：`plan_id` (path)
- `POST /api/medication-plans/{plan_id}/resume` — Resume Plan；参数：`plan_id` (path)

### medicine-ocr

- `POST /api/medicines/barcode-lookup` — Barcode Lookup；请求体
- `POST /api/medicines/ocr-recognize` — Ocr Recognize；请求体

### medicines

- `GET /api/medicines` — List Medicines；参数：`page` (query), `pageSize` (query)
- `POST /api/medicines` — Create Medicine；请求体
- `GET /api/medicines/alerts/expiring` — Get Medicine Alerts
- `GET /api/medicines/quality-alerts` — Get Quality Alerts
- `DELETE /api/medicines/{medicine_id}` — Delete Medicine；参数：`medicine_id` (path)
- `GET /api/medicines/{medicine_id}` — Get Medicine；参数：`medicine_id` (path)
- `PUT /api/medicines/{medicine_id}` — Update Medicine；参数：`medicine_id` (path)；请求体
- `GET /api/medicines/{medicine_id}/quality` — Get Medicine Quality；参数：`medicine_id` (path)

### model-registry

- `GET /api/agent/logs` — Get Logs；参数：`entity_id` (query), `action_type` (query), `page` (query), `page_size` (query)
- `GET /api/agent/logs/{log_id}` — Get Log；参数：`log_id` (path)
- `PUT /api/agent/logs/{log_id}/review` — Review Log；参数：`log_id` (path)；请求体
- `POST /api/agent/process` — Process Knowledge；请求体
- `GET /api/models` — Get Models；参数：`enabled_only` (query)
- `POST /api/models` — Add Model；请求体
- `POST /api/models/vote` — Vote；请求体
- `DELETE /api/models/{model_id}` — Remove Model；参数：`model_id` (path)
- `PUT /api/models/{model_id}` — Edit Model；参数：`model_id` (path)；请求体

### notifications

- `GET /api/notifications` — List Notifications
- `POST /api/notifications/{notification_id}/read` — Mark Notification Read；参数：`notification_id` (path)

### p2-features

- `POST /api/admin/freshness-check` — Freshness Check
- `GET /api/admin/freshness-stats` — Freshness Stats
- `POST /api/chat/{conversation_id}/summarize` — Summarize Conversation；参数：`conversation_id` (path)；请求体
- `GET /api/knowledge/{entity_id}/feedback` — Get Feedback；参数：`entity_id` (path)
- `POST /api/knowledge/{entity_id}/feedback` — Submit Feedback；参数：`entity_id` (path)；请求体

### p3-features

- `GET /api/admin/agent/config` — Get Agent Config；参数：`agent_name` (query)
- `PUT /api/admin/agent/config` — Set Agent Config；请求体
- `GET /api/admin/agent/conversations` — List Agent Conversations；参数：`agent_name` (query), `limit` (query)
- `GET /api/admin/agent/memories` — List Agent Memories；参数：`agent_name` (query), `memory_type` (query), `q` (query), `limit` (query)
- `POST /api/admin/agent/memories` — Save Agent Memory；请求体
- `DELETE /api/admin/agent/memories/{memory_id}` — Delete Agent Memory；参数：`memory_id` (path)
- `POST /api/admin/agent/optimize-prompt` — Optimize Agent Prompt；请求体
- `POST /api/admin/community-consensus-scan` — Community Consensus Scan
- `POST /api/admin/feeder/scan` — Feeder Scan；参数：`max_feeds` (query)
- `POST /api/admin/knowledge/scan-all` — Comprehensive Knowledge Scan；请求体
- `POST /api/admin/translate-check` — Translate Check
- `POST /api/admin/url-health-check` — Url Health Check
- `GET /api/admin/url-health-stats` — Url Health Stats
- `GET /api/user/interests` — Get User Interests

### personal-knowledge

- `GET /api/personal/edges` — List Edges；参数：`relationship_type` (query)
- `POST /api/personal/edges` — Create Edge；请求体
- `DELETE /api/personal/edges/{edge_id}` — Delete Edge；参数：`edge_id` (path)
- `GET /api/personal/graph` — Personal Graph
- `GET /api/personal/symptoms` — List Symptoms
- `POST /api/personal/symptoms` — Log Symptom；请求体

### prescriptions

- `POST /api/prescriptions/generate` — Generate Prescription；请求体
- `POST /api/prescriptions/health-report` — Generate Health Report；请求体

### profile

- `GET /api/profile` — Get Profile
- `PUT /api/profile` — Update Profile；请求体

### push

- `GET /api/push/config` — Get Push Config
- `DELETE /api/push/subscriptions` — Unsubscribe Push；请求体
- `POST /api/push/subscriptions` — Subscribe Push；请求体

### rag

- `POST /api/rag/index/rebuild` — Rag Index Rebuild
- `GET /api/rag/index/status` — Rag Index Status
- `GET /api/rag/intent` — Rag Intent；参数：`q` (query)
- `GET /api/rag/search` — Rag Search；参数：`q` (query), `top_k` (query), `rerank` (query)

### reminders

- `GET /api/reminders` — List Reminders；参数：`enabled` (query)
- `POST /api/reminders` — Create Reminder；请求体
- `GET /api/reminders/history` — Get Reminder History；参数：`days` (query)
- `GET /api/reminders/today` — Get Today Reminders
- `DELETE /api/reminders/{reminder_id}` — Delete Reminder；参数：`reminder_id` (path)
- `GET /api/reminders/{reminder_id}` — Get Reminder；参数：`reminder_id` (path)
- `PUT /api/reminders/{reminder_id}` — Update Reminder；参数：`reminder_id` (path)；请求体
- `POST /api/reminders/{reminder_id}/check-in` — Check In Reminder；参数：`reminder_id` (path)；请求体
- `PUT /api/reminders/{reminder_id}/toggle` — Toggle Reminder；参数：`reminder_id` (path)

### remote-assist

- `GET /api/remote-assist/consent` — Get Share Consent
- `PUT /api/remote-assist/consent` — Set Share Consent；请求体
- `POST /api/remote-assist/invite` — Invite Viewer；请求体
- `DELETE /api/remote-assist/invite/{share_id}` — Revoke Share；参数：`share_id` (path)
- `GET /api/remote-assist/shared-with-me` — List Shared With Me
- `POST /api/remote-assist/{user_id}/alert` — Set Alert Thresholds；参数：`user_id` (path)；请求体
- `GET /api/remote-assist/{user_id}/alerts` — Check Alerts；参数：`user_id` (path)
- `GET /api/remote-assist/{user_id}/missed-alerts` — Get Missed Alerts；参数：`user_id` (path)
- `GET /api/remote-assist/{user_id}/summary` — Get Health Summary；参数：`user_id` (path)
- `GET /api/remote-assist/{user_id}/weekly-report` — Get Weekly Report；参数：`user_id` (path)

### reports

- `GET /api/reports/constitution` — Get Constitution Report
- `POST /api/reports/generate-pdf` — Generate Pdf；请求体
- `GET /api/reports/health-trend` — Get Health Trend Report；参数：`period` (query)
- `GET /api/reports/pre-visit` — Get Pre Visit Report

### safety

- `POST /api/safety/check` — Safety Check；请求体
- `POST /api/safety/check-v2` — Safety Check V2；请求体

### schemas

- `GET /api/schemas` — List Schemas
- `GET /api/schemas/{node_type}` — Get Schema；参数：`node_type` (path)

### seasonal-health

- `GET /api/seasonal-health` — Get Seasonal Health；参数：`term` (query)

### share-cards

- `POST /api/share-cards/generate` — Generate Card；请求体
- `GET /api/share-cards/list` — List Cards
- `POST /api/share-cards/monthly-report` — Create Monthly Report；请求体
- `GET /api/share-cards/monthly-report/latest` — Get Latest Monthly Report
- `DELETE /api/share-cards/{card_id}` — Delete Card；参数：`card_id` (path)
- `GET /api/share-cards/{card_id}` — Get Card；参数：`card_id` (path)

### smart-search

- `GET /api/smart-search` — Smart Search；参数：`q` (query), `top_k` (query)
- `POST /api/smart-search/expand` — Expand Search；请求体
- `POST /api/smart-search/import` — Import Web Result；请求体

### therapies

- `GET /api/therapies` — List Therapies；参数：`page` (query), `pageSize` (query), `category` (query)
- `GET /api/therapies/categories` — List Categories
- `GET /api/therapies/search` — Search Therapies；参数：`q` (query), `category` (query)
- `GET /api/therapies/{therapy_id}` — Get Therapy；参数：`therapy_id` (path)
- `GET /api/therapies/{therapy_id}/safety` — Get Therapy Safety；参数：`therapy_id` (path)

### triage

- `GET /api/triage/age-groups` — Get Age Groups
- `POST /api/triage/assess` — Assess；请求体
- `GET /api/triage/questionnaire` — Get Questionnaire；参数：`age_months` (query), `age_group` (query)
- `GET /api/triage/red-flags` — Get Red Flags

### unified-knowledge

- `GET /api/knowledge/acupoints` — List Acupoints；参数：`q` (query), `meridian` (query), `page` (query), `page_size` (query)
- `GET /api/knowledge/acupoints/{entity_id}` — Get Acupoint；参数：`entity_id` (path)
- `GET /api/knowledge/formulas` — List Formulas；参数：`q` (query), `category` (query), `page` (query), `page_size` (query)
- `GET /api/knowledge/formulas/{entity_id}` — Get Formula；参数：`entity_id` (path)
- `GET /api/knowledge/graph/{entity_id}` — Get Graph；参数：`entity_id` (path), `hops` (query)
- `GET /api/knowledge/herbs` — List Herbs；参数：`q` (query), `category` (query), `page` (query), `page_size` (query)
- `GET /api/knowledge/herbs/{entity_id}` — Get Herb；参数：`entity_id` (path)
- `GET /api/knowledge/meridians` — List Meridians；参数：`q` (query), `category` (query)
- `GET /api/knowledge/meridians/{entity_id}` — Get Meridian；参数：`entity_id` (path)
- `GET /api/knowledge/search` — Unified Search；参数：`q` (query), `type` (query), `page` (query), `page_size` (query)
- `GET /api/knowledge/symptoms` — List Symptoms；参数：`q` (query), `page` (query), `page_size` (query)
- `GET /api/knowledge/therapies` — List Therapies；参数：`q` (query), `category` (query), `page` (query), `page_size` (query)
- `GET /api/knowledge/therapies/{entity_id}` — Get Therapy；参数：`entity_id` (path)

### voice

- `POST /api/voice/qa` — Voice Qa；请求体
- `POST /api/voice/synthesize` — Synthesize；请求体
- `POST /api/voice/transcribe` — Transcribe；请求体
