# 设计文档：分布式知识索引 — 外部链接索引化

> 状态：**设计完成**
> 日期：2025-06-21
> 核心理念：一套索引基础设施，内容分布在内（知识库）和外（链接原文）

## 1. 需求理解

当用户提供一个外部链接（如微信公众号文章）：

```
用户输入: https://mp.weixin.qq.com/s?...
    ↓
Agent 处理:
    ├── 提取摘要 → 存入 knowledge_entities（内部知识）
    ├── 提取实体（中药/方剂/症状/穴位）→ 创建/合并到 knowledge_entities
    ├── 提取关键信息（药方/疗法/症状对应）→ 创建关系
    └── 原文不保存到知识库
    
    但对原文构建索引:
    ├── BM25 倒排索引（分块后的关键词）
    ├── BGE-M3 语义向量（1024维嵌入）
    ├── RRF 混合融合排名
    └── 交叉编码器重排（可选）
    
    索引条目指向外部 URL，而非内部 entity_id
```

搜索时：
```
查询 "黄芪补气"
    → 命中内部知识实体
    → 命中外部链接的索引分块
    → 统一 RRF 融合排名
    → 结果标注：[知识库] 或 [外部: 微信文章]
```

## 2. 与现有索引的统一

**核心原则**：外部内容使用与内部知识完全相同的索引管道。

| 索引类型 | 内部知识 | 外部链接 | 共用基础设施 |
|---------|---------|---------|-------------|
| BM25 | knowledge_chunks | external_chunks | ✅ 相同的 BM25 算法 |
| 语义向量 | chunk_embeddings | external_embeddings | ✅ 相同的 BGE-M3 模型 |
| RRF 融合 | 内部 BM25 + 语义 | 外部 BM25 + 语义 | ✅ 相同的 RRF 公式 |
| 重排序 | BGE-reranker | BGE-reranker | ✅ 相同的交叉编码器 |

**实现选择**：两种方案

### 方案 A：统一表 + source_type 区分（推荐）

```sql
-- 现有 knowledge_chunks 表增加来源标识
ALTER TABLE knowledge_chunks ADD COLUMN source_url TEXT;
ALTER TABLE knowledge_chunks ADD COLUMN source_type TEXT DEFAULT 'internal';
-- source_type: 'internal' (知识库) / 'external' (外部链接)

-- chunk_embeddings 不需要改 — 它已通过 chunk_id 关联
```

搜索时，`source_type='external'` 的结果标注来源 URL。

### 方案 B：独立外部索引表

```sql
CREATE TABLE external_chunks (
    id TEXT PRIMARY KEY,
    source_url TEXT NOT NULL,
    source_title TEXT,
    chunk_index INTEGER,
    chunk_text TEXT NOT NULL,
    extracted_entity_ids TEXT DEFAULT '[]',  -- 关联的内部实体
    created_at TEXT
);
CREATE TABLE external_embeddings (
    chunk_id TEXT PRIMARY KEY,
    embedding TEXT,  -- JSON array
    model_name TEXT,
    FOREIGN KEY (chunk_id) REFERENCES external_chunks(id)
);
```

**推荐方案 A**：改动最小，一套索引完全统一，只是 chunk 多了 `source_url` 字段。

## 3. 数据流设计

```
外部链接输入
    ↓
Step 1: 提取原文 (knowledge_parser.parse_url)
    → raw_text + title + metadata
    ↓
Step 2: AI 分析 (agent_tools.tool_analyze)
    → entity_type / keywords / summary
    ↓
Step 3: 实体抽取 (agent_tools.tool_scan_entities)
    → 识别中药/方剂/症状等
    ↓
Step 4: 创建知识实体 (agent_tools.tool_create_or_update_entity)
    → 摘要+实体存入 knowledge_entities
    → 不存原文
    ↓
Step 5: 构建外部索引 (新工具: tool_index_external_content)
    → 原文分块 (chunker.chunk_text)
    → 每个 chunk 存入 knowledge_chunks
      - entity_id = 创建的知识实体ID（关联）
      - source_url = 原始URL
      - source_type = 'external'
      - chunk_text = 原文分块文本
    → 每个 chunk 生成 BGE-M3 embedding
      - 存入 chunk_embeddings
    ↓
Step 6: BM25 索引自动覆盖
    → search_pipeline.bm25_search 扫描 knowledge_chunks
    → 自然覆盖 source_type='external' 的 chunks
    → 无需额外代码
```

## 4. 搜索行为

```python
# search_pipeline.py — 无需修改
# bm25_search 已经扫描全部 knowledge_chunks
# vector_search 已经扫描全部 chunk_embeddings
# RRF 融合已经统一排名

# 唯一新增：结果格式增加来源标注
{
    "results": [
        {
            "title": "黄芪",
            "source": "internal",      # 知识库
            "entity_id": "ke-herb-001",
            "score": 0.033
        },
        {
            "title": "中药黄芪的补气功效详解",
            "source": "external",      # 外部链接
            "source_url": "https://mp.weixin.qq.com/s?...",
            "chunk_text": "黄芪性甘微温，归脾肺经...",
            "entity_id": "ke-agent-xxx",  # 关联的知识实体
            "score": 0.028
        }
    ]
}
```

## 5. 新增工具

```python
# agent_tools.py — 新增一个工具

async def tool_index_external_content(
    db: DbAdapter,
    raw_text: str,
    source_url: str,
    title: str,
    entity_id: str,  # 关联的内部知识实体
) -> dict:
    """为外部内容构建索引（不存原文到知识库，但索引指向外部URL）。
    
    - 分块：raw_text → chunks (chunker.chunk_text)
    - 每块存入 knowledge_chunks: source_url + source_type='external'
    - 每块生成 BGE-M3 embedding → chunk_embeddings
    - BM25 自动覆盖（无需额外代码）
    """
    from app.chunker import chunk_text, estimate_tokens
    from app.embedding import get_embedding_model
    from app.vector_store import store_embedding
    
    chunks = chunk_text(raw_text, max_tokens=512, overlap=50)
    model = get_embedding_model()
    
    count = 0
    for cd in chunks:
        chunk_id = f"ext-chunk-{uuid.uuid4()}"
        await db.execute(
            """INSERT INTO knowledge_chunks
               (id, entity_id, chunk_index, chunk_text, chunk_type,
                hierarchy_path, hierarchy_level, token_count, metadata)
               VALUES (?, ?, ?, ?, 'external', ?, ?, ?, ?)""",
            (chunk_id, entity_id, cd["index"], cd["text"],
             "", cd.get("hierarchy_level", 0),
             cd.get("token_count", estimate_tokens(cd["text"])),
             json.dumps({"source_url": source_url, "source_title": title})),
        )
        
        if model.available:
            vec = model.embed_one(cd["text"])
            if vec:
                await store_embedding(db, chunk_id, vec)
                count += 1
    
    await log_action(db, "index_external", "url", source_url, entity_id,
                     {"chunks": len(chunks), "embedded": count}, "indexed")
    return {"chunks": len(chunks), "embedded": count}
```

## 6. knowledge_agent.py 集成

```python
# knowledge_agent.py — process_input() Step 7 修改

# Step 7: Build index (内部 + 外部)
if entity_id:
    # 7a: 为知识实体构建常规索引（标题+摘要）
    await tool_build_index(db, entity_id)
    
    # 7b: 如果有外部原文，为原文构建索引（指向URL）
    if url and raw_text:
        await tool_index_external_content(
            db, raw_text, url, title, entity_id
        )
```

## 7. 数据库变更

```sql
-- knowledge_chunks 增加来源标识（向后兼容）
-- 通过 migration 添加（已有数据默认 'internal'）

-- DDL 更新
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    ...existing columns...
    -- 以下两个新列通过 ALTER TABLE 添加
    -- source_url TEXT,
    -- source_type TEXT DEFAULT 'internal'
);

-- 迁移函数
async def _migrate_chunks_source(db):
    cols = await db.query("PRAGMA table_info(knowledge_chunks)")
    if not any(c["name"] == "source_type" for c in cols):
        await db.execute("ALTER TABLE knowledge_chunks ADD COLUMN source_url TEXT")
        await db.execute("ALTER TABLE knowledge_chunks ADD COLUMN source_type TEXT DEFAULT 'internal'")
```

## 8. 搜索结果增强

```python
# search_pipeline.py — bm25_search 和 vector_search 结果增加来源信息

# 在 vector_search 的结果中：
results.append({
    ...existing fields...,
    "source_type": chunk_meta.get("source_type", "internal"),
    "source_url": chunk_meta.get("source_url"),
})
```

## 9. RRF 融合不变

```
内部 BM25 结果 + 外部 BM25 结果 → 统一 RRF 融合
内部语义结果 + 外部语义结果 → 统一 RRF 融合
→ 最终排名不区分来源，完全按相关性
```

这是设计的精妙之处：**用户不需要关心结果来自内部还是外部，系统自动混合排名**。

## 10. 去重策略

外部内容可能与已有知识重复：
- 如果 tool_check_duplicates 发现精确匹配 → 合并到已有实体
- 但外部原文的 chunks 仍然独立索引（因为内容可能补充已有知识）
- 同一 URL 的重复提交 → 检查 source_url 去重

```python
# 检查同一 URL 是否已索引
existing = await db.query(
    "SELECT DISTINCT json_extract(metadata, '$.source_url') as url "
    "FROM knowledge_chunks WHERE source_type='external'"
)
```

## 11. 优势

1. **一套索引**：BM25/语义/RRF/reranker 完全复用，零重复代码
2. **内容分布式**：知识库只存提炼后的实体+摘要，原文留在源站
3. **搜索统一**：用户不感知来源，相关性排名自然混合
4. **增量友好**：新链接入库只增量索引其内容，不影响已有索引
5. **可追溯**：每个外部 chunk 都有 source_url，用户可点击查看原文

## 12. 待实施检查清单

- [ ] `knowledge_chunks` 增加 `source_url` + `source_type` 列
- [ ] `agent_tools.py` 增加 `tool_index_external_content()`
- [ ] `knowledge_agent.py` Step 7 集成外部索引
- [ ] `search_pipeline.py` 结果增加 `source_type` / `source_url`
- [ ] 前端搜索结果标注来源（内部/外部链接）
- [ ] 去重：同 URL 不重复索引
- [ ] 测试覆盖
