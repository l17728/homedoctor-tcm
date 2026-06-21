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
