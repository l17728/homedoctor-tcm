# 设计文档：自主知识生长系统（Self-growing Knowledge System）

> 版本：v1.0
> 日期：2025-06-21
> 状态：**待评审 → 通过后启动开发**
> 核心理念：树根隐喻 — 万物皆输入，精华入库，原文索引，搜索驱动补全，知识图谱自收敛

---

## 1. 系统全景

### 1.1 树根隐喻

```
                    ┌──────────────────────────────────┐
                    │          用户交互层               │
                    │  搜索 · 问答 · 导入 · 对话        │
                    └──────────────┬───────────────────┘
                                   │
                    ┌──────────────▼───────────────────┐
                    │        知识决策 Agent             │
                    │  （状态机 + 多AI专家团评审）      │
                    └──────────────┬───────────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              ▼                    ▼                    ▼
    ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
    │   知识库（本体）  │  │   索引（分布式）  │  │   审计追踪       │
    │                 │  │                 │  │                 │
    │ knowledge_      │  │ BM25 倒排索引   │  │ agent_logs      │
    │ entities        │  │ （内部+外部统一） │  │ 血缘来源        │
    │                 │  │                 │  │ 信任评分        │
    │ entity_         │  │ BGE-M3 语义向量 │  │ 用户审核        │
    │ relationships   │  │ （内部+外部统一） │  │                 │
    │                 │  │                 │  │ knowledge_      │
    │ 精华知识        │  │ 原文指向外部URL  │  │ provenance      │
    │ （提炼后的）     │  │ 不存原文         │  │                 │
    └─────────────────┘  └─────────────────┘  └─────────────────┘
              │                    │                    │
              └────────────────────┼────────────────────┘
                                   │
                    ┌──────────────▼───────────────────┐
                    │        模块消费层                 │
                    │  安全引擎 · 配伍引擎 · AI问答     │
                    │  体质推荐 · 功法推荐 · 知识图谱   │
                    └──────────────────────────────────┘
```

### 1.2 知识生命周期

```
外部输入（URL/文本/对话/Web Search/文件/图片）
    ↓
┌─ Agent 管道 ──────────────────────────────────────────────┐
│                                                          │
│  1. 提取内容（原文 + 元数据）                              │
│  2. AI 分析（类型/关键词/摘要）                            │
│  3. 实体扫描（中药/方剂/症状/穴位）                        │
│  4. 去重检查（标题精确 + BM25 相似 + 语义余弦）            │
│  5. 质量评估 + 多AI专家团评审 → 信任评分                   │
│  6. 入库决策（采纳/合并/拒绝/待审）                        │
│  7. 入库存精华（实体+关系）+ 索引原文（chunks+embeddings）  │
│  8. 推送模块 + 记录血缘                                    │
│                                                          │
└──────────────────────────────────────────────────────────┘
    ↓
知识库（精华） + 外部索引（原文指向URL）
    ↓
用户搜索/问答
    ↓
┌─ 搜索缺口检测 ───────────────────────────────────────────┐
│                                                          │
│  内部知识库有结果？                                       │
│    → YES → 返回结果（标注来源+信任评分）                   │
│    → NO → 外部索引有结果？                                 │
│              → YES → 返回 + 自动提炼入库                   │
│              → NO → 询问用户：是否Web Search？              │
│                       → 同意 → Web Search                  │
│                              → 找到 → 展示摘要             │
│                              → 询问：是否一键入库？         │
│                              → 同意 → Agent 管道处理       │
│                       → 拒绝 → 返回"未找到"                │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

---

## 2. 知识信任分级（免疫系统）

### 2.1 四级信任体系

| 等级 | 标签 | 来源 | 入安全引擎 | 入AI问答 | 搜索可见 | 颜色 |
|------|------|------|-----------|---------|---------|------|
| **S** | 系统权威 | 教材/药典/专家审定/种子数据 | ✅ 直接 | ✅ 引用为依据 | ✅ | 🟢 绿 |
| **A** | 权威来源 | 官方医学网站/期刊/知网 | ✅ 标注来源 | ✅ 标注来源 | ✅ | 🔵 蓝 |
| **B** | 用户导入 | 公众号/博客/用户手动录入 | ❌ | ⚠️ 标注"仅供参考" | ✅ | 🟡 黄 |
| **C** | Web Search | 搜索引擎随机结果 | ❌ | ❌ 仅展示链接 | ✅ | 🟠 橙 |

### 2.2 信任等级流转

```
新知识进入时：
  来源判断 → 初始等级
  
  C级（Web Search）
    → 用户手动确认入库 → 升级为 B级
    → 多AI专家团评审通过 → 升级为 A级
    → 专家人工审定 → 升级为 S级

  B级（用户导入）
    → 多AI专家团评审通过 → 升级为 A级
    → 多用户共识（≥3用户导入相同知识）→ 升级为 A级
    → 专家人工审定 → 升级为 S级

  任何等级
    → 发现与S级知识冲突 → 降级或标记"存疑"
    → 用户举报 → 降级
```

### 2.3 安全沙箱规则

```python
SAFETY_ENGINE_TRUST_THRESHOLD = "A"  # 只用 S+A 级
AI_QA_TRUST_THRESHOLD = "B"          # S+A+B 可引用，B级标注"仅供参考"
SEARCH_VISIBILITY_THRESHOLD = "C"    # 所有等级可见

def can_enter_safety_check(trust_level: str) -> bool:
    return trust_level in ("S", "A")

def can_reference_in_ai(trust_level: str) -> bool:
    return trust_level in ("S", "A", "B")  # B级附加"仅供参考"
```

---

## 3. 多AI专家团评审机制

### 3.1 评审流程

```
新知识候选
    ↓
┌─ 专家团评审 ─────────────────────────────────────────────┐
│                                                         │
│  并行发送给 3 个 AI 模型（从 ai_models 表选取）：         │
│                                                         │
│  模型1（如 Kimi-K2.6）→ 评审结果1                        │
│  模型2（如 GLM-5）    → 评审结果2                        │
│  模型3（如 Qwen3-235B）→ 评审结果3                       │
│                                                         │
│  每个模型返回：                                          │
│  {                                                      │
│    "medical_accuracy": 0-100,    // 医学准确性           │
│    "completeness": 0-100,        // 信息完整度            │
│    "source_reliability": 0-100,  // 来源可靠性            │
│    "safety_concerns": [...],     // 安全隐患              │
│    "recommendation": "adopt" / "review" / "reject",      │
│    "reason": "..."                // 理由                │
│  }                                                      │
│                                                         │
│  聚合规则：                                             │
│    ≥2/3 模型 "adopt"  → 采纳，信任评分 = 平均分          │
│    ≥2/3 模型 "reject" → 拒绝                            │
│    其他 → 待人工审核                                    │
│                                                         │
└─────────────────────────────────────────────────────────┘
    ↓
信任评分 = avg(medical_accuracy, completeness, source_reliability)
```

### 3.2 评审 Prompt 设计

```python
REVIEW_PROMPT = """你是一位中医药学专家，请评审以下知识的准确性和安全性。

知识标题：{title}
知识内容：{content}
知识类型：{entity_type}
来源：{source}

请从以下维度评分（0-100）：
1. medical_accuracy（医学准确性）：内容是否符合中医理论和现代药理研究？
2. completeness（信息完整度）：关键信息是否完整（性味/归经/用量/禁忌等）？
3. source_reliability（来源可靠性）：来源是否权威可信？

同时检查：
- 是否有安全隐患（错误用量/禁忌遗漏/夸大疗效）？
- 是否与已知中医知识矛盾？

返回 JSON：
{
  "medical_accuracy": N,
  "completeness": N,
  "source_reliability": N,
  "safety_concerns": ["..."],
  "recommendation": "adopt" | "review" | "reject",
  "reason": "..."
}
"""
```

### 3.3 信任评分计算

```python
def calculate_trust_score(reviews: list[dict]) -> dict:
    scores = []
    for r in reviews:
        avg = (r["medical_accuracy"] + r["completeness"] + r["source_reliability"]) / 3
        scores.append(avg)
    
    consensus = sum(1 for r in reviews if r["recommendation"] == "adopt")
    overall = sum(scores) / len(scores)
    
    if consensus >= 2 and overall >= 80:
        return {"score": round(overall, 1), "level": "A", "decision": "adopted"}
    elif consensus >= 2 and overall >= 60:
        return {"score": round(overall, 1), "level": "B", "decision": "pending_review"}
    else:
        return {"score": round(overall, 1), "level": "C", "decision": "rejected"}
```

---

## 4. 知识血缘（Provenance）

### 4.1 数据模型

```sql
CREATE TABLE IF NOT EXISTS knowledge_provenance (
    id TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL,           -- 关联的知识实体
    source_type TEXT NOT NULL,          -- 'seed'/'url'/'text'/'chat'/'web_search'/'file'/'ocr'
    source_url TEXT,                    -- 外部链接URL
    source_title TEXT,                  -- 来源标题
    source_domain TEXT,                 -- 来源域名（用于信任评估）
    trust_level TEXT DEFAULT 'C',       -- S/A/B/C
    trust_score REAL DEFAULT 0,         -- 0-100
    review_details TEXT DEFAULT '{}',   -- JSON: 多AI评审详情
    imported_by TEXT,                   -- 用户ID（谁导入的）
    imported_at TEXT NOT NULL DEFAULT (datetime('now')),
    verified_by TEXT,                   -- 审核人
    verified_at TEXT,                   -- 审核时间
    FOREIGN KEY (entity_id) REFERENCES knowledge_entities(id)
);
```

### 4.2 血缘信息展示

用户点击知识实体 → 查看"知识属性卡"：

```
┌─────────────────────────────────────────────┐
│  黄芪                                        │
│  ─────────────────────────────────────────  │
│  📊 信任等级：S级（系统权威）                 │
│  ⭐ 信任评分：95.0                            │
│                                             │
│  📋 知识来源：                               │
│  ├── 📗 系统种子数据（《中药学》教材）  S级   │
│  │     导入时间：2025-06-01                  │
│  ├── 🌐 用户导入（某公众号文章）       B级   │
│  │     URL: https://mp.weixin.qq.com/...    │
│  │     导入时间：2025-06-15                  │
│  │     评审：3模型通过，评分 72.3            │
│  └── 🔍 Web Search 补全                C级   │
│        搜索词："黄芪 药理研究"                │
│        来源：cnki.net                       │
│        导入时间：2025-06-20                  │
│        评审：2模型通过，评分 65.0            │
│                                             │
│  🤖 AI评审详情：                             │
│  ├── Kimi-K2.6: 准确性 85 / 完整度 80       │
│  ├── GLM-5: 准确性 78 / 完整度 75           │
│  └── Qwen3-235B: 准确性 82 / 完整度 78      │
│                                             │
│  ⚠️ 安全提示：                              │
│  本知识引用了 B/C 级来源，仅供参考           │
│  [提升信任等级] [举报问题] [查看冲突]        │
└─────────────────────────────────────────────┘
```

---

## 5. 知识冲突检测

### 5.1 冲突类型

| 类型 | 示例 | 处理 |
|------|------|------|
| **数值冲突** | 用量 9-30g vs 3-120g | 保留保守值入安全引擎，展示范围给用户 |
| **属性冲突** | 性"微温" vs 性"温" | 保留高信任等级的，低等级标注为"异说" |
| **禁忌冲突** | 无禁忌 vs 阴虚禁用 | 有禁忌更安全，采纳有禁忌版本 |
| **功效冲突** | 补气 vs 泻气 | 严重冲突，标记"存疑"，待人工审核 |

### 5.2 冲突检测算法

```python
CONFLICT_FIELDS = {
    "dosage_min_g": "数值冲突",
    "dosage_max_g": "数值冲突",
    "nature": "属性冲突",
    "toxicity": "属性冲突",
    "contraindications": "禁忌冲突",
}

async def detect_conflicts(db, entity_id, new_properties):
    """检测新属性与已有属性的冲突。"""
    existing = await db.query_one(
        "SELECT properties FROM knowledge_entities WHERE id = ?", (entity_id,)
    )
    existing_props = parse_json(existing["properties"], {})
    
    conflicts = []
    for field, conflict_type in CONFLICT_FIELDS.items():
        old_val = existing_props.get(field)
        new_val = new_properties.get(field)
        if old_val and new_val and str(old_val) != str(new_val):
            conflicts.append({
                "field": field,
                "type": conflict_type,
                "existing": old_val,
                "incoming": new_val,
                "resolution": _resolve_conflict(field, old_val, new_val),
            })
    return conflicts

def _resolve_conflict(field, old_val, new_val):
    """冲突解决策略。"""
    if field in ("dosage_min_g", "dosage_max_g"):
        return {"keep": min(old_val, new_val) if "min" in field else max(old_val, new_val),
                "reason": "安全引擎取保守值（较窄范围）"}
    return {"keep": old_val, "reason": "保留高信任等级知识，新值存为'异说'"}
```

---

## 6. 索引生命周期管理（TTL + 命中率）

### 6.1 索引元数据增强

```sql
ALTER TABLE knowledge_chunks ADD COLUMN hit_count INTEGER DEFAULT 0;
ALTER TABLE knowledge_chunks ADD COLUMN last_hit_at TEXT;
ALTER TABLE knowledge_chunks ADD COLUMN text_summary TEXT;  -- 语义向量的人类可读摘要
```

### 6.2 语义向量的人类可读摘要

每个 embedding 对应一个 `text_summary` 字段，方便管理员识别：

```python
# 入库时生成摘要
def generate_chunk_summary(chunk_text: str) -> str:
    """为二进制语义向量生成人类可读摘要。"""
    # 取前80字 + 关键实体标注
    summary = chunk_text[:80].replace("\n", " ").strip()
    if len(chunk_text) > 80:
        summary += "..."
    return summary
```

管理员看到的索引管理界面：
```
┌───────────────────────────────────────────────────────────────┐
│  索引管理                                       [筛选] [清理]  │
├───────────────────────────────────────────────────────────────┤
│  类型：[全部▼] 来源：[全部▼] 排序：[存活时间▼]               │
├───────────────────────────────────────────────────────────────┤
│  ✅ 内部 │ 黄芪补气升阳，固表止汗，利水消肿…    命中: 47次   │
│         │ entity: ke-herb-001                 创建: 06-01    │
│         │ 🟢 S级                              最后命中: 06-21│
├───────────────────────────────────────────────────────────────┤
│  🔗 外部 │ 葛根汤药理研究：葛根含异黄酮…        命中: 3次    │
│         │ URL: cnki.net/article/12345          创建: 06-15   │
│         │ 🟡 B级 评分: 72.3                    最后命中: 06-18│
├───────────────────────────────────────────────────────────────┤
│  🔗 外部 │ 中医养生：冬季进补指南…              命中: 0次    │
│         │ URL: mp.weixin.qq.com/s?...          创建: 06-10   │
│         │ 🟠 C级 评分: 45.0                    最后命中: 未命中│
│         │ ⚠️ 存活45天未命中                    [删除此索引]   │
└───────────────────────────────────────────────────────────────┘
```

### 6.3 TTL + 命中率清理策略

```python
async def get_stale_chunks(db, days_threshold: int = 90, min_hits: int = 0):
    """获取可能需要清理的索引分块。
    
    排序优先级：
    1. 创建时间长 + 命中次数少 = 最高清理优先级
    2. 信任等级低（C级）的优先于高等级
    3. 外部索引优先于内部索引
    """
    rows = await db.query(
        """SELECT kc.*, ke.title,
                  CAST((julianday('now') - julianday(kc.created_at)) AS INTEGER) AS age_days,
                  kc.hit_count, kc.source_type
             FROM knowledge_chunks kc
             LEFT JOIN knowledge_entities ke ON ke.id = kc.entity_id
            WHERE kc.source_type = 'external'
              AND kc.hit_count <= ?
              AND CAST((julianday('now') - julianday(kc.created_at)) AS INTEGER) > ?
            ORDER BY age_days DESC, kc.hit_count ASC""",
        (min_hits, days_threshold),
    )
    return rows
```

清理决策权在管理员：系统推荐清理列表，管理员确认后才删除。

---

## 7. 搜索缺口检测 + Web Search 闭环

### 7.1 状态机设计

```
                    ┌───────┐
                    │ IDLE  │
                    └───┬───┘
                        │ 用户搜索/提问
                        ▼
                ┌───────────────┐
                │  SEARCHING    │ ← 搜索内部知识库
                └───────┬───────┘
                        │
              ┌─────────┴─────────┐
              ▼                   ▼
        有结果？YES          无结果？
              │                   │
              ▼                   ▼
        ┌───────────┐    ┌───────────────┐
        │ RETURN    │    │ SEARCH_EXT    │ ← 搜索外部索引
        │ + 标注来源 │    └───────┬───────┘
        └───────────┘            │
                          ┌──────┴──────┐
                          ▼             ▼
                    有结果？YES    无结果？
                          │             │
                          ▼             ▼
                   ┌───────────┐ ┌───────────────┐
                   │ AUTO_     │ │ ASK_WEB       │ ← "是否搜索互联网？"
                   │ EXTRACT   │ └───────┬───────┘
                   │ (自动提炼) │         │
                   └───────────┘    ┌────┴────┐
                                   ▼         ▼
                              用户同意    用户拒绝
                                   │         │
                                   ▼         ▼
                           ┌────────────┐ ┌───────┐
                           │ WEB_SEARCH │ │ RETURN│
                           │ (搜索互联网) │ │ "未找到"│
                           └──────┬─────┘ └───────┘
                                  │
                                  ▼
                           ┌────────────┐
                           │ SHOW_RESULT│ ← 展示摘要
                           │ S + 询问入库│
                           └──────┬─────┘
                                  │
                           ┌──────┴────┐
                           ▼           ▼
                      用户同意入库   用户跳过
                           │           │
                           ▼           ▼
                    ┌────────────┐ ┌───────┐
                    │ PROCESS    │ │ IDLE  │
                    │ (Agent管道) │ └───────┘
                    └──────┬─────┘
                           │
                           ▼
                    ┌───────┐
                    │ IDLE  │ ← 知识已入库，下次搜索直接命中
                    └───────┘
```

### 7.2 API 设计

```python
# 搜索端点增强
@router.get("/api/search")
async def smart_search(q: str, auto_expand: bool = False):
    """智能搜索：内部 → 外部 → Web Search（需用户确认）。"""
    
    # Step 1: 内部搜索
    internal = await search(db, q)
    if internal["total"] > 0:
        return {"results": internal, "source": "internal", "expandable": False}
    
    # Step 2: 外部索引搜索
    external = await search_external(db, q)
    if external["total"] > 0:
        # 自动提炼入库（后台）
        asyncio.create_task(auto_extract_and_import(db, external))
        return {"results": external, "source": "external", "expandable": True}
    
    # Step 3: 内外部都无 → 提示用户
    if not auto_expand:
        return {
            "results": [],
            "source": "none",
            "expandable": True,
            "suggestion": f'知识库中未找到"{q}"，是否搜索互联网获取？',
        }
    
    # Step 4: 用户同意 → Web Search
    web_results = await web_search(q)
    return {
        "results": web_results,
        "source": "web",
        "importable": True,
        "suggestion": "找到相关内容，是否一键入库？",
    }


# 一键入库端点
@router.post("/api/agent/import-web")
async def import_from_web(body: WebImportRequest):
    """用户确认后，将 Web Search 结果通过 Agent 管道入库。"""
    result = await process_input(
        db, url=body.url, title=body.title,
        source_type="web_search",
    )
    return result
```

---

## 8. 对话即知识（一键总结入库）

### 8.1 流程

```
AI 多轮对话结束
    ↓
系统检测：对话包含有价值知识？
    （启发式：对话 > 3轮 + 提到中药/方剂/症状）
    ↓
弹出提示条：
  "💡 检测到调理方案，是否保存为知识卡片？"
  [保存] [跳过]
    ↓
用户点击"保存"
    ↓
Agent 提取：
  ├── 症状（用户描述的）→ 创建/关联 symptom 实体
  ├── 证候（AI 判断的）→ 创建 syndrome 实体
  ├── 方剂/中药（AI 推荐的）→ 关联 herb/formula 实体
  ├── 调理建议 → 存为 knowledge_card 实体
  └── 来源：对话记录（存 conversation_id）
    ↓
信任等级：B（用户对话提取）
    ↓
多AI专家团评审 → 信任评分
    ↓
入库 + 索引 + 推送
```

---

## 9. 外部命中自动提炼

### 9.1 触发条件

当外部索引被搜索命中时：

```python
async def check_and_auto_extract(db, search_results):
    """外部索引命中后，检查是否需要提炼知识入库。"""
    for result in search_results:
        if result.get("source_type") != "external":
            continue
        
        entity_id = result.get("entity_id")
        entity = await get_entity(db, entity_id)
        
        # 检查：实体是否缺少外部内容中的关键信息？
        external_text = result.get("chunk_text", "")
        missing = _detect_missing_knowledge(entity, external_text)
        
        if missing:
            # 外部内容包含内部缺失的知识
            extracted = await _ai_extract_missing(entity, external_text, missing)
            await _merge_extracted_knowledge(db, entity_id, extracted)
            await log_action(db, "auto_extract", "search", "", entity_id,
                           {"extracted_fields": missing}, "enriched")
```

---

## 10. 数据库变更汇总

```sql
-- knowledge_chunks 增强
ALTER TABLE knowledge_chunks ADD COLUMN hit_count INTEGER DEFAULT 0;
ALTER TABLE knowledge_chunks ADD COLUMN last_hit_at TEXT;
ALTER TABLE knowledge_chunks ADD COLUMN text_summary TEXT;

-- 知识血缘表
CREATE TABLE IF NOT EXISTS knowledge_provenance (
    id TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_url TEXT,
    source_title TEXT,
    source_domain TEXT,
    trust_level TEXT DEFAULT 'C',
    trust_score REAL DEFAULT 0,
    review_details TEXT DEFAULT '{}',
    imported_by TEXT,
    imported_at TEXT NOT NULL DEFAULT (datetime('now')),
    verified_by TEXT,
    verified_at TEXT,
    FOREIGN KEY (entity_id) REFERENCES knowledge_entities(id)
);

-- 知识冲突记录表
CREATE TABLE IF NOT EXISTS knowledge_conflicts (
    id TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL,
    field TEXT NOT NULL,
    conflict_type TEXT NOT NULL,
    existing_value TEXT,
    incoming_value TEXT,
    resolution TEXT,
    resolved INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 搜索命中率更新触发器
CREATE TRIGGER IF NOT EXISTS trg_chunk_hit
    AFTER UPDATE OF last_hit_at ON knowledge_chunks
    BEGIN
        UPDATE knowledge_chunks
        SET hit_count = hit_count + 1
        WHERE id = NEW.id AND NEW.last_hit_at IS NOT OLD.last_hit_at;
    END;

-- 删除推荐豁免表（管理员设置的"不再推荐删除"标记）
CREATE TABLE IF NOT EXISTS deletion_exemptions (
    id TEXT PRIMARY KEY,
    target_type TEXT NOT NULL,          -- 'chunk' / 'entity' / 'provenance'
    target_id TEXT NOT NULL,
    exempted_by TEXT NOT NULL,          -- 管理员用户ID
    exempt_reason TEXT,                 -- 管理员给出的豁免理由
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(target_type, target_id)
);
```

---

## 10.1 删除策略设计原则

### 核心原则

**系统永远不自动删除任何知识或索引。所有删除操作必须由管理员手动执行。**

系统的职责是：
1. **定期全方位扫描**，基于 TTL + 命中率 + 信任等级 + 时效性等多维指标生成**删除推荐**
2. 为每条推荐提供**详细的理由**（为什么建议删除）
3. 管理员在管理界面逐条或批量审阅后决定是否采纳

### 扫描行为规则

```
管理员操作                      系统后续行为
──────────                      ──────────
删除某条索引                   → 已删除，不再扫描（目标不存在）
保留某条索引（不做任何操作）   → 下次扫描仍会重新评估并可能再次推荐删除
设置"不再推荐删除此条"         → 加入 deletion_exemptions 表，后续扫描跳过此条
移除"不再推荐"标记             → 恢复扫描，重新纳入评估
```

**关键规则**：管理员"保留"（不做操作）不等于"豁免"。系统会在下一次定期扫描中**重新评估**该条目，如果仍然满足删除推荐条件，会**再次推荐**。只有管理员**显式设置豁免**后，系统才会永久跳过该条目。

### 扫描频率

```python
DELETION_SCAN_CONFIG = {
    "frequency": "weekly",           # 每周执行一次全量扫描
    "last_run_key": "deletion_scan_last_run",  # 存储上次执行时间
    "conditions": {
        "external_chunk_age_days": 90,    # 外部索引存活>90天
        "min_hit_count": 0,               # 命中次数≤此值
        "trust_level_below": "A",         # 信任等级低于A级（B/C）
        "stale_url": True,                # URL已失效(404)
        "outdated_knowledge": True,       # 知识时效性标记为outdated
        "conflict_rejected": True,        # 冲突解决中被拒绝的知识
    },
}
```

### 推荐理由模板

每条删除推荐附带人类可读的理由：

```
推荐删除：[外部索引] "葛根汤药理研究…" (ext-chunk-xxx)
  理由：
    1. 存活时间：127天（创建于 2025-02-15）
    2. 命中次数：0次（从未被搜索命中）
    3. 信任等级：C级（Web Search 来源）
    4. 来源URL：https://example.com/article（状态：404 已失效）
  推荐：精华知识已提炼入库，外部索引可安全清理

  [删除] [保留] [不再推荐删除此条]
```

### 推荐排序

删除推荐按优先级排序，最该清理的排在最前：

```python
def calculate_deletion_priority(chunk: dict) -> float:
    """计算删除优先级（0-100，越高越建议删除）。"""
    score = 0.0

    # 存活时间（权重 30%）
    age_days = chunk.get("age_days", 0)
    score += min(age_days / 365, 1.0) * 30

    # 命中次数（权重 25%，越少越该删）
    hits = chunk.get("hit_count", 0)
    score += max(0, (10 - hits) / 10) * 25

    # 信任等级（权重 20%，越低越该删）
    trust = chunk.get("trust_level", "C")
    trust_weight = {"S": 0, "A": 5, "B": 15, "C": 20}
    score += trust_weight.get(trust, 20)

    # URL状态（权重 15%，失效的优先删）
    if chunk.get("url_status") == 404:
        score += 15

    # 时效性（权重 10%，过时的优先删）
    freshness = chunk.get("freshness_status", "current")
    if freshness == "outdated":
        score += 10
    elif freshness == "aging":
        score += 5

    return round(score, 1)
```

### 管理员操作 API

```
GET  /api/admin/deletion-recommendations     -- 获取删除推荐列表（带理由+优先级）
POST /api/admin/deletion-execute             -- 执行删除（管理员确认，支持批量）
POST /api/admin/deletion-exempt              -- 设置"不再推荐删除此条"
DELETE /api/admin/deletion-exempt/{id}       -- 移除豁免标记
GET  /api/admin/deletion-exemptions          -- 查看所有豁免列表
```

---

## 11. 新增 Agent 工具

| 工具 | 用途 |
|------|------|
| `tool_multi_model_review()` | 多AI专家团评审，返回信任评分 |
| `tool_detect_conflicts()` | 冲突检测 |
| `tool_record_provenance()` | 记录知识血缘 |
| `tool_web_search()` | Web Search（调用搜索引擎API） |
| `tool_auto_extract()` | 外部命中后自动提炼入库 |
| `tool_generate_summary()` | 为二进制向量生成人类可读摘要 |
| `tool_get_stale_indexes()` | 获取可能需清理的索引（TTL+命中率） |
| `tool_clean_indexes()` | 管理员确认后清理索引 |

---

## 12. API 端点新增

| 端点 | 说明 |
|------|------|
| `GET /api/search` | 智能搜索（内部→外部→Web Search提示） |
| `POST /api/search/expand` | 用户同意后执行 Web Search |
| `POST /api/agent/import-web` | 一键入库 Web Search 结果 |
| `POST /api/chat/save-knowledge` | 对话一键总结入库 |
| `GET /api/knowledge/{id}/provenance` | 查看知识血缘 |
| `PUT /api/knowledge/{id}/trust` | 提升/降低信任等级 |
| `GET /api/admin/indexes/stale` | 获取待清理索引列表 |
| `DELETE /api/admin/indexes/{id}` | 删除指定索引 |
| `GET /api/admin/conflicts` | 获取知识冲突列表 |
| `PUT /api/admin/conflicts/{id}/resolve` | 解决知识冲突 |

---

## 13. 前端页面新增

### 13.1 知识属性卡

任何知识实体的详情页面，点击"属性卡"图标查看：
- 信任等级 + 评分（彩色徽章）
- 来源列表（时间线）
- AI评审详情（展开）
- 安全提示
- 操作按钮（提升等级/举报/查看冲突）

### 13.2 索引管理页（管理员）

- 索引列表（内部/外部/全部）
- 筛选：类型/来源/信任等级/命中次数/存活时间
- 排序：存活时间↓ + 命中次数↓
- 每条显示：文本摘要 + 来源URL + 信任等级 + 命中次数 + 创建时间 + 最后命中
- 批量删除（管理员确认）
- 统计：总索引数/外部占比/平均命中率/待清理数

### 13.3 搜索结果增强

每个搜索结果显示：
- 来源标签：🟢 内部知识 / 🔵 外部索引 / 🟠 Web结果
- 信任评分（如 85.3）
- 来源链接（外部可点击跳转原文）
- 如果是外部/ Web 结果：[入库] 按钮

### 13.4 对话总结提示

AI 对话页面底部：
- 对话 > 3轮后自动弹出提示条
- "💡 检测到调理方案，是否保存为知识卡片？"
- 点击保存 → 显示提取预览 → 确认入库

---

## 14. 实施计划

| 阶段 | 内容 | 工作量 | 优先级 |
|------|------|--------|--------|
| **Phase 1** | 信任分级 + 血缘表 + 多AI评审 | 2天 | P0 |
| **Phase 2** | 搜索缺口检测 + Web Search + 一键入库 | 2天 | P1 |
| **Phase 3** | 索引TTL + 命中率 + 文本摘要 + 管理页 | 1天 | P1 |
| **Phase 4** | 知识冲突检测 + 安全沙箱 | 1天 | P0 |
| **Phase 5** | 对话一键总结入库 | 1天 | P2 |
| **Phase 6** | 外部命中自动提炼 | 1天 | P2 |
| **Phase 7** | 前端：属性卡 + 索引管理 + 搜索增强 | 2天 | P1 |
| **总计** | | **10天** | |

---

## 15. 检查清单

### 安全底线
- [ ] 信任分级（S/A/B/C）实现
- [ ] 安全引擎只读 S+A 级
- [ ] AI问答 B级标注"仅供参考"
- [ ] 冲突检测（不覆盖，多源并存）
- [ ] 多AI专家团评审（≥2/3共识）

### 核心体验
- [ ] 搜索缺口检测（内部→外部→Web Search）
- [ ] 用户交互确认（是否扩大搜索/是否入库）
- [ ] Web Search 集成
- [ ] 一键入库（Agent管道处理）
- [ ] 对话一键总结入库

### 索引管理
- [ ] hit_count + last_hit_at 追踪
- [ ] text_summary 人类可读摘要
- [ ] TTL + 命中率排序
- [ ] 管理员清理界面

### 知识治理
- [ ] 知识血缘表 + API
- [ ] 信任评分可见
- [ ] 冲突记录 + 解决界面
- [ ] 信任等级流转（升级/降级）

### 分布式索引（已实现）
- [x] knowledge_chunks source_url + source_type
- [x] tool_index_external_content()
- [x] BM25 + 语义统一覆盖外部内容
- [x] RRF 统一排名

### Agent 工具（已有）
- [x] tool_extract / tool_analyze / tool_scan_entities
- [x] tool_check_duplicates / tool_assess_quality
- [x] tool_create_or_update_entity
- [x] tool_build_index / tool_push_to_modules
- [x] tool_index_external_content

---

## 16. 个性化知识生长方向

### 16.1 设计理念

每个家庭的知识图谱向不同方向生长，取决于用户的关注领域：

```
用户A（老年家庭）：
  常搜索：降压、糖尿病、关节痛、失眠
  → 系统检测高频领域：老年慢性病
  → Web Search 主动偏向：老年中医养生、慢性病调理
  → 知识图谱向"老年养生"方向自然生长
  → 推荐功法偏向：八段锦、站桩（温和）

用户B（年轻父母）：
  常搜索：小儿感冒、脾胃调理、湿疹
  → 系统检测高频领域：儿科中医
  → Web Search 主动偏向：小儿推拿、食疗
  → 知识图谱向"儿科/食疗"方向生长
  → 推荐功法偏向：五禽戏（活泼）
```

### 16.2 实现

```sql
CREATE TABLE IF NOT EXISTS user_interest_profiles (
    user_id TEXT NOT NULL,
    interest_domain TEXT NOT NULL,
    search_count INTEGER DEFAULT 0,
    last_searched TEXT,
    PRIMARY KEY (user_id, interest_domain)
);
```

搜索时记录领域，Web Search 时按用户兴趣调整搜索策略。

---

## 17. 社区知识汇聚

### 17.1 设计理念

多用户导入相同知识时，系统自动检测共识，提升信任等级：

```
用户1 导入文章A："葛根汤治项背强急"  → B级
用户2 导入文章B："葛根汤主治项背强硬"  → B级
用户3 导入文章C："葛根汤适用于颈项强痛" → B级

系统检测：3个独立来源描述了相同知识
→ 自动提升为 A级（社区共识）
→ 标记"社区验证：3个来源一致"
```

### 17.2 共识检测

```python
async def detect_community_consensus(db):
    """定期扫描：多个用户导入了语义相似的知识。"""
    rows = await db.query(
        """SELECT entity_id, COUNT(DISTINCT imported_by) AS source_count,
                  AVG(trust_score) AS avg_score
             FROM knowledge_provenance
            WHERE trust_level = 'B'
            GROUP BY entity_id
            HAVING source_count >= 3"""
    )
    for row in rows:
        await update_trust_level(db, row["entity_id"], "A",
                                 reason=f"社区共识：{row['source_count']}个独立来源")
```

---

## 18. 知识时效性

### 18.1 时间戳标记

```sql
ALTER TABLE knowledge_provenance ADD COLUMN content_date TEXT;
ALTER TABLE knowledge_provenance ADD COLUMN freshness_status TEXT DEFAULT 'current';
-- freshness_status: 'current'(最新) / 'aging'(老化) / 'outdated'(过时)
```

### 18.2 时效性检查

```python
async def check_knowledge_freshness(db):
    """定期检查知识时效性（每周执行）。"""
    rows = await db.query(
        "SELECT id, entity_id, content_date FROM knowledge_provenance WHERE content_date IS NOT NULL"
    )
    for row in rows:
        age_days = (datetime.now() - parse_date(row["content_date"])).days
        if age_days > 365 * 5:
            status = "outdated"
        elif age_days > 365 * 2:
            status = "aging"
        else:
            status = "current"
        await db.execute(
            "UPDATE knowledge_provenance SET freshness_status = ? WHERE id = ?",
            (status, row["id"]),
        )
```

用户看到："此知识发表于 2020年，可能已有更新研究"。

---

## 19. Web Search 智能化增强

### 19.1 多结果交叉验证

```
Web Search "葛根汤 药理" → 返回5篇文章
  → 并行提取每篇的关键信息
  → 交叉比对：

  文章1: "葛根汤含葛根素，扩张血管"     ✓
  文章2: "葛根汤改善脑供血"              ✓ (与文章1一致)
  文章3: "葛根汤可降血压"                ✓ (逻辑一致)
  文章4: "葛根汤无副作用"                ✗ (夸大，与前3篇矛盾)
  文章5: "葛根汤治感冒"                  △ (不矛盾但不完整)

  → 共识提取：文章1/2/3 的共同点 → 高可信入库
  → 矛盾标记：文章4 → 标记"存疑"
```

### 19.2 来源优先级

```python
DOMAIN_TRUST_MAP = {
    "cnki.net": "A",           # 知网 → 学术
    "wanfangdata.com.cn": "A",  # 万方 → 学术
    "satcm.gov.cn": "S",        # 国家中医药管理局 → 官方
    "39yst.com": "B",           # 39健康 → 大众健康媒体
    "mp.weixin.qq.com": "C",    # 微信公众号 → 不确定
}

def get_domain_trust(url: str) -> str:
    domain = urlparse(url).netloc
    for trusted_domain, level in DOMAIN_TRUST_MAP.items():
        if trusted_domain in domain:
            return level
    return "C"
```

### 19.3 共识提取

```python
async def extract_consensus(articles: list[dict]) -> dict:
    """从多篇文章中提取共识知识。"""
    prompt = f"以下是关于'{topic}'的{len(articles)}篇文章摘要。请提取所有文章一致认可的共同知识点。\n\n"
    for i, art in enumerate(articles):
        prompt += f"文章{i+1}: {art['summary']}\n\n"
    consensus = await multi_model_vote(db, [{"role": "user", "content": prompt}])
    return consensus
```

---

## 20. 知识图谱可视化生长

### 20.1 生长动画

```
时间轴：2025-01 ──── 2025-03 ──── 2025-06 ──── 现在

节点状态：
  🟢 S级（系统种子）    — 初始就有
  🔵 A级（权威导入）    — 带时间戳的生长
  🟡 B级（用户导入）    — 标注导入者
  🟠 C级（Web Search）  — 标注搜索词
  🌱 新吸收（<7天）     — 闪烁动画提示
  ✅ 已验证             — 用户/AI审核通过标记
  🔗 外部链接           — 虚线节点，点击跳转原文
```

### 20.2 统计面板

```
┌─────────────────────────────────────┐
│  知识图谱生长统计                    │
│  总节点：1594 (+47本月)             │
│  总关系：2888 (+128本月)            │
│  外部索引：325 chunks               │
│  平均信任评分：78.3                  │
│  知识来源分布：                      │
│    🟢 S级：62% (987)                │
│    🔵 A级：15% (239)                │
│    🟡 B级：18% (287)                │
│    🟠 C级：5%  (81)                 │
│  热门生长领域：                      │
│    1. 补气药 (+12)                  │
│    2. 经络穴位 (+9)                 │
│    3. 养生功法 (+7)                 │
└─────────────────────────────────────┘
```

---

## 21. 跨语言知识吸收

### 21.1 场景

```
用户输入英文链接: "https://pubmed.ncbi.nlm.nih.gov/12345678/"
  → Agent 检测：英文内容
  → 提取关键信息 → 翻译为中文入库
  → 原文英文索引保留（支持英文搜索）
  → 用户看到中文化的知识 + 原文链接
```

### 21.2 实现

```python
async def tool_detect_and_translate(text: str) -> dict:
    """检测语言，非中文则翻译摘要。"""
    has_chinese = any('\u4e00' <= ch <= '\u9fff' for ch in text[:200])
    if has_chinese:
        return {"language": "zh", "text": text, "translated": False}

    translated = await chat_completion([
        {"role": "system", "content": "将以下内容翻译为中文，保持医学术语准确。"},
        {"role": "user", "content": text[:2000]},
    ])
    return {"language": "en", "original_text": text, "translated_text": translated, "translated": True}
```

入库时 `properties` 增加 `original_language` 和 `translated_summary`。双语索引：中文摘要用于内部知识库，英文原文用于外部索引。

---

## 22. 知识质量反馈

### 22.1 用户评分机制

```
搜索结果 → 点击知识详情 → 底部反馈：
  "这个知识对你有帮助吗？"
  👍 有帮助    👎 不准确    🚩 举报问题

  评分影响：
    👍 多次 → 信任评分微升（+1/次，上限+10）
    👎 多次 → 信任评分微降（-2/次）
    🚩 举报 → 立即降级为"待审核"
```

### 22.2 数据模型

```sql
CREATE TABLE IF NOT EXISTS knowledge_feedback (
    id TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    rating TEXT NOT NULL,          -- 'helpful' / 'inaccurate' / 'report'
    comment TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(entity_id, user_id)
);
```

### 22.3 评分反馈循环

```python
async def apply_feedback_to_trust(db, entity_id: str):
    helpful = await db.query_one(
        "SELECT COUNT(*) AS c FROM knowledge_feedback WHERE entity_id=? AND rating='helpful'",
        (entity_id,),
    )
    inaccurate = await db.query_one(
        "SELECT COUNT(*) AS c FROM knowledge_feedback WHERE entity_id=? AND rating='inaccurate'",
        (entity_id,),
    )
    if inaccurate["c"] >= 3:
        await update_trust_level(db, entity_id, new_level="pending_review",
                                 reason="3+用户标记不准确")
```

---

## 23. 定期刷新外部URL

### 23.1 设计

```python
async def refresh_external_urls(db):
    """每周检查外部URL健康状态。"""
    chunks = await db.query(
        "SELECT DISTINCT source_url, entity_id FROM knowledge_chunks WHERE source_type='external'"
    )
    for chunk in chunks:
        url = chunk["source_url"]
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.head(url, follow_redirects=True)
            if resp.status_code == 404:
                await db.execute(
                    "UPDATE knowledge_chunks SET chunk_type='external_stale' WHERE source_url=?",
                    (url,),
                )
                await log_action(db, "url_check", "url", url, chunk["entity_id"],
                               {"status": 404}, "stale")
        except Exception:
            pass
```

### 23.2 管理员通知

```
⚠️ 12个外部链接已失效（404）
→ [查看列表] [批量清理] [重新搜索替代内容]
```

---

## 24. 更新后的实施计划

| 阶段 | 内容 | 工作量 | 优先级 |
|------|------|--------|--------|
| **Phase 1** | 信任分级 + 血缘表 + 多AI评审 + 安全沙箱 | 2天 | P0 |
| **Phase 2** | 搜索缺口检测 + Web Search + 一键入库 | 2天 | P1 |
| **Phase 3** | 索引TTL + 命中率 + 文本摘要 + 管理页 | 1天 | P1 |
| **Phase 4** | 知识冲突检测 | 1天 | P0 |
| **Phase 5** | 对话一键总结入库 | 1天 | P2 |
| **Phase 6** | 外部命中自动提炼 | 1天 | P2 |
| **Phase 7** | 前端：属性卡 + 索引管理 + 搜索增强 | 2天 | P1 |
| **Phase 8** | Web Search 智能化（交叉验证+共识+来源优先级） | 1天 | P2 |
| **Phase 9** | 知识质量反馈（用户评分+反馈循环） | 1天 | P2 |
| **Phase 10** | 定期刷新外部URL + 失效检测 | 0.5天 | P3 |
| **Phase 11** | 个性化知识生长方向 | 1天 | P3 |
| **Phase 12** | 社区知识汇聚 | 1天 | P3 |
| **Phase 13** | 知识图谱可视化生长 | 1天 | P3 |
| **Phase 14** | 跨语言知识吸收 | 0.5天 | P3 |
| **Phase 15** | 知识时效性 | 0.5天 | P3 |
| **总计** | | **16天** | |

---

## 25. 完整检查清单

### 安全底线（P0）
- [ ] 信任分级（S/A/B/C）实现
- [ ] 安全引擎只读 S+A 级
- [ ] AI问答 B级标注"仅供参考"
- [ ] 冲突检测（不覆盖，多源并存）
- [ ] 多AI专家团评审（≥2/3共识）
- [ ] 安全沙箱规则代码化

### 核心体验（P1）
- [ ] 搜索缺口检测（内部→外部→Web Search）
- [ ] 用户交互确认（是否扩大搜索/是否入库）
- [ ] Web Search 集成
- [ ] 一键入库（Agent管道处理）
- [ ] 对话一键总结入库
- [ ] 前端属性卡（信任评分+来源+AI评审）
- [ ] 索引管理页（TTL+命中率+文本摘要）

### 智能增强（P2）
- [ ] Web Search 智能化（交叉验证+共识提取+来源优先级）
- [ ] 外部命中自动提炼入库
- [ ] 知识质量反馈（用户评分+反馈循环）
- [ ] 知识时效性（时间戳+老化检测）

### 未来扩展（P3）
- [ ] 个性化知识生长方向
- [ ] 社区知识汇聚（共识检测+自动升级）
- [ ] 知识图谱可视化生长
- [ ] 跨语言知识吸收
- [ ] 定期刷新外部URL + 失效检测

### 已实现基础
- [x] knowledge_chunks source_url + source_type（分布式索引）
- [x] tool_index_external_content()（外部内容索引）
- [x] BM25 + 语义统一覆盖外部内容
- [x] RRF 统一排名
- [x] Agent 管道（10工具 + 8步）
- [x] 模型注册表（5模型 + 多模型投票）
- [x] agent_logs 审计日志
