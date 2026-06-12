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

---

## 中药

### GET /api/herbs

**Query**: `page=1&pageSize=20`

**Response 200**
```json
{
  "items": [
    {
      "id": "herb-001",
      "name": "黄芪",
      "properties": {
        "性味": "甘，温",
        "归经": "脾、肺经",
        "功效": "补气固表，利尿托毒",
        "用量": "9-30g",
        "drugClass": "补气药"
      }
    }
  ],
  "total": 203,
  "page": 1,
  "pageSize": 20,
  "totalPages": 11
}
```

### GET /api/herbs/search

**Query**: `q=黄芪`

FTS5 全文搜索，匹配名称、功效、归经。

**Response 200** — 同列表格式

### GET /api/herbs/{herb_id}

**Response 200** — 单条中药详情

**Response 404** — 未找到

---

## 方剂

### GET /api/formulas

**Query**: `page=1&pageSize=20`

**Response 200**
```json
{
  "items": [
    {
      "id": "formula-001",
      "name": "四物汤",
      "properties": {
        "组成": "当归12g 川芎8g 白芍12g 熟地黄15g",
        "功效": "补血调血",
        "主治": "营血虚滞证",
        "用法": "水煎服"
      }
    }
  ],
  "total": 82,
  "page": 1,
  "pageSize": 20
}
```

### GET /api/formulas/{formula_id}

单条方剂详情。

### GET /api/formulas/{formula_id}/safety-check

提取方剂中所有 herb names，执行五层安全检查。

**Response 200**
```json
{
  "safe": false,
  "warnings": [
    {
      "layer": 1,
      "severity": "critical",
      "title": "配伍禁忌",
      "detail": "附子与半夏属于十八反，禁止同用",
      "herbs": ["附子", "半夏"],
      "action": "禁止",
      "source": "十八反"
    }
  ],
  "disclaimer": "以上分析仅供参考，不能替代专业医师的诊断和建议。",
  "checked_herbs": ["附子", "半夏", "人参"],
  "checked_medicines": []
}
```

---

## 药箱

### GET /api/medicines

**Response 200**
```json
{
  "items": [
    {
      "id": "med-001",
      "name": "硝苯地平缓释片",
      "type": "西药",
      "quantity": 30,
      "dosage_instructions": "每次1片，每日1次",
      "contraindications": "低血压患者慎用"
    }
  ],
  "total": 5
}
```

### POST /api/medicines

**Request**
```json
{
  "name": "硝苯地平缓释片",
  "type": "西药",
  "dosage_instructions": "每次1片，每日1次",
  "contraindications": "低血压患者慎用"
}
```

### PUT /api/medicines/{medicine_id}

部分更新。

### DELETE /api/medicines/{medicine_id}

**Response 204** — 删除成功

---

## AI 对话

### POST /api/chat

**Request**
```json
{
  "message": "黄芪能长期泡水喝吗？"
}
```

**Response 200**
```json
{
  "reply": "黄芪性味甘温，归脾肺经...",
  "warnings": [],
  "conversation_id": "conv-xxx"
}
```

如果消息包含急症关键词（如"心梗""休克"），warnings 会包含就医提醒。

### GET /api/chat/history

**Query**: `conversation_id=conv-xxx`（可选，默认最近会话）

**Response 200**
```json
{
  "messages": [
    { "role": "user", "content": "黄芪能长期泡水喝吗？" },
    { "role": "assistant", "content": "黄芪性味甘温..." }
  ]
}
```

---

## 安全检查

### POST /api/safety/check-v2

五层安全检查。硬编码层（1a/1b）在 AI 层之前运行。

**Request**
```json
{
  "herbs": ["附子", "半夏"],
  "medicines": ["华法林"],
  "user_profile": {
    "is_pregnant": false,
    "age": 65,
    "weight_kg": 60
  }
}
```

**Response 200**
```json
{
  "safe": false,
  "warnings": [
    {
      "layer": 1,
      "severity": "critical",
      "title": "配伍禁忌：十八反",
      "detail": "附子与半夏属于十八反（乌头反半夏），禁止同用",
      "herbs": ["附子", "半夏"],
      "action": "禁止",
      "source": "十八反"
    },
    {
      "layer": 1,
      "severity": "high",
      "title": "中西药交互",
      "detail": "华法林与当归等活血化瘀药合用可能增加出血风险",
      "herbs": [],
      "action": "谨慎",
      "source": "R-01"
    },
    {
      "layer": 3,
      "severity": "medium",
      "title": "老年用药提醒",
      "detail": "65岁以上老年人肝肾功能减退，建议从小剂量开始",
      "herbs": [],
      "action": "告知医生",
      "source": "特殊人群"
    }
  ],
  "disclaimer": "⚠️ 以上分析基于中药配伍禁忌和中西药交互规则，仅供参考，不能替代专业中医师的诊断和处方。如有不适，请及时就医。",
  "checked_herbs": ["附子", "半夏"],
  "checked_medicines": ["华法林"]
}
```

### 安全级别

| severity | 含义 | safe 字段 |
|----------|------|-----------|
| `critical` | 禁止使用 | false |
| `high` | 高风险 | false |
| `medium` | 谨慎使用 | 取决于其他警告 |
| `low` | 提示 | true |

---

## 体质自测

### GET /api/constitution/questionnaire

**Response 200**
```json
{
  "questions": [
    { "id": "q1", "type": "气虚质", "text": "你容易疲乏吗？" },
    { "id": "q2", "type": "气虚质", "text": "你容易气短，呼吸短促吗？" }
    // ... 共 66 题
  ]
}
```

### POST /api/constitution/assess

**Request**
```json
{
  "answers": {
    "q1": 3,
    "q2": 2,
    "q3": 0
    // ... 所有题目
  }
}
```

评分：没有=0, 很少=1, 有时=2, 经常=3, 总是=4

**Response 200**
```json
{
  "id": "assessment-uuid",
  "assessed_at": "2026-06-12T10:30:00",
  "results": {
    "平和质": 75.0,
    "气虚质": 62.5,
    "阳虚质": 28.6,
    "阴虚质": 12.5,
    "痰湿质": 0.0,
    "湿热质": 0.0,
    "血瘀质": 14.3,
    "气郁质": 0.0,
    "特禀质": 0.0
  },
  "primary_type": "气虚质",
  "secondary_types": ["平和质"],
  "description": "元气不足，易疲乏、气短、自汗，需要益气健脾。"
}
```

### GET /api/constitution/history

**Response 200** — 评估记录列表

### GET /api/constitution/latest

**Response 200** — 最近一次评估 / **404** 尚无评估

---

## 吃药提醒

### POST /api/reminders

**Request**
```json
{
  "title": "服用降压药",
  "medicine_name": "硝苯地平缓释片",
  "dosage": "1片",
  "frequency": "daily",
  "times": ["08:00", "20:00"],
  "start_date": "2026-06-12",
  "notes": "饭后服用",
  "enabled": true
}
```

**Response 201** — 完整 Reminder 对象

### GET /api/reminders

**Response 200** — 当前用户所有提醒列表

### GET /api/reminders/today

展开为今日时间槽，每槽含状态。

**Response 200**
```json
[
  {
    "reminder_id": "rem-001",
    "title": "服用降压药",
    "time": "08:00",
    "dosage": "1片",
    "medicine_name": "硝苯地平缓释片",
    "status": "已服",
    "notes": "饭后服用"
  },
  {
    "reminder_id": "rem-001",
    "title": "服用降压药",
    "time": "20:00",
    "dosage": "1片",
    "medicine_name": "硝苯地平缓释片",
    "status": "待服",
    "notes": "饭后服用"
  }
]
```

状态规则：当前时间 > 预定时间 + 2小时 = "漏服"

### PUT /api/reminders/{reminder_id}

部分更新。

### PUT /api/reminders/{reminder_id}/toggle

切换 enabled 状态。

### DELETE /api/reminders/{reminder_id}

**Response 204**

---

## 健康档案

### GET /api/profile

**Response 200**
```json
{
  "user_id": "uuid-xxx",
  "display_name": "王阿姨",
  "birth_year": 1962,
  "gender": "女",
  "height_cm": 158,
  "weight_kg": 55,
  "constitution_type": "气虚质",
  "constitution_secondary": ["阳虚质"],
  "allergies": ["海鲜"],
  "health_conditions": ["高血压"],
  "is_pregnant": false,
  "blood_type": "A",
  "notes": "有胃病史",
  "updated_at": "2026-06-12T10:00:00"
}
```

新用户返回空字段（null / 空数组）。

### PUT /api/profile

**Request** — 只传需要更新的字段

```json
{
  "display_name": "王阿姨",
  "gender": "女",
  "allergies": ["海鲜", "青霉素"],
  "health_conditions": ["高血压"]
}
```

**Response 200** — 完整 profile

---

## 其他

### GET /api/health

健康检查，无需认证。

**Response 200**
```json
{
  "status": "healthy"
}
```

### GET /api/dashboard/stats

**Response 200**
```json
{
  "herb_count": 203,
  "formula_count": 82,
  "medicine_count": 5,
  "reminder_count": 3,
  "today_reminders": 2
}
```

### GET /api/daily-health

**Response 200**
```json
{
  "solar_term": "芒种",
  "term_advice": "芒种时节，湿热渐盛...",
  "diet_advice": "宜清淡，多食健脾祛湿之品",
  "lifestyle_advice": "晚睡早起，适当午休"
}
```

---

## 错误格式

所有错误返回统一格式：

```json
{
  "detail": "错误描述信息"
}
```

| 状态码 | 含义 |
|--------|------|
| 400 | 请求参数错误 |
| 401 | 未认证 / token 过期 |
| 404 | 资源不存在 |
| 409 | 冲突（如用户名已存在） |
| 422 | 请求体验证失败（Pydantic 校验） |
| 500 | 服务器内部错误 |
