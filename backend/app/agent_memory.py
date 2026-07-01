"""Agent memory system — experience accumulation, retrieval, and evolution.

Implements 6 memory tools that enable agents to learn from experience,
retrieve relevant memories, reflect on patterns, and share knowledge.

Memory types:
  experience — successful approaches
  lesson     — failure/warning records
  strategy   — processing rules
  pattern    — recognition templates
  rule       — hard constraints
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from app.database import DbAdapter

logger = logging.getLogger(__name__)

KNOWLEDGE_AGENT = "knowledge_agent"
PATROL_AGENT = "patrol_agent"
SHARED = "shared"


async def memory_save(
    db: DbAdapter,
    agent_name: str,
    content: str,
    memory_type: str = "experience",
    tags: list[str] | None = None,
    context: dict[str, Any] | None = None,
    confidence: float = 0.5,
) -> str:
    """Save a memory entry. Returns memory ID."""
    mid = f"mem-{uuid.uuid4()}"
    await db.execute(
        """INSERT INTO agent_memories
           (id, agent_name, memory_type, content, tags, context, confidence)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            mid, agent_name, memory_type, content,
            json.dumps(tags or [], ensure_ascii=False),
            json.dumps(context or {}, ensure_ascii=False),
            confidence,
        ),
    )
    logger.info("memory_save: %s/%s: %s...", agent_name, memory_type, content[:50])
    return mid


async def memory_search(
    db: DbAdapter,
    agent_name: str | None = None,
    query: str = "",
    memory_type: str | None = None,
    min_confidence: float = 0.0,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Search memories by content/tags/agent/type. Includes shared memories."""
    conditions = ["confidence >= ?"]
    params: list[Any] = [min_confidence]

    if agent_name:
        conditions.append("(agent_name = ? OR agent_name = 'shared')")
        params.append(agent_name)
    if memory_type:
        conditions.append("memory_type = ?")
        params.append(memory_type)
    if query:
        conditions.append("(content LIKE ? OR tags LIKE ?)")
        like = f"%{query}%"
        params.extend([like, like])

    where = " AND ".join(conditions)
    rows = await db.query(
        f"""SELECT * FROM agent_memories WHERE {where}
            ORDER BY confidence DESC, times_used DESC, created_at DESC LIMIT ?""",
        tuple(params + [limit]),
    )
    return [_format_memory(r) for r in rows]


async def memory_update(
    db: DbAdapter,
    memory_id: str,
    content: str | None = None,
    confidence: float | None = None,
    tags: list[str] | None = None,
    increment_used: bool = False,
    increment_success: bool = False,
) -> bool:
    """Update a memory entry. Returns True if updated."""
    updates: dict[str, Any] = {}
    if content is not None:
        updates["content"] = content
    if confidence is not None:
        updates["confidence"] = confidence
    if tags is not None:
        updates["tags"] = json.dumps(tags, ensure_ascii=False)

    if increment_used:
        await db.execute(
            "UPDATE agent_memories SET times_used = times_used + 1, updated_at = datetime('now') WHERE id = ?",
            (memory_id,),
        )
    if increment_success:
        await db.execute(
            "UPDATE agent_memories SET success_count = success_count + 1, confidence = MIN(confidence + 0.05, 1.0), updated_at = datetime('now') WHERE id = ?",
            (memory_id,),
        )

    if updates:
        set_clauses = ", ".join(f"{k} = ?" for k in updates)
        params = list(updates.values()) + [memory_id]
        await db.execute(
            f"UPDATE agent_memories SET {set_clauses}, updated_at = datetime('now') WHERE id = ?",
            tuple(params),
        )
    return True


async def memory_reflect(
    db: DbAdapter,
    agent_name: str,
    limit: int = 20,
) -> dict[str, Any]:
    """LLM-driven reflection on recent memories. Returns insights."""
    from app.llm_unified import llm_chat

    recent = await memory_search(db, agent_name, limit=limit)
    if not recent:
        return {"insights": [], "message": "no memories to reflect on"}

    memories_text = "\n".join(
        f"- [{m['memory_type']}] conf={m['confidence']:.1f} used={m['times_used']} success={m['success_count']}: {m['content'][:100]}"
        for m in recent
    )

    prompt = f"""你是{agent_name}。请审视以下最近的记忆，发现模式、矛盾和改进点。

记忆列表：
{memories_text}

请分析：
1. 哪些记忆被频繁使用且成功率低？（需要修正的策略）
2. 哪些记忆相互矛盾？（需要解决的冲突）
3. 是否发现了可以泛化的模式？（可以举一反三的经验）
4. 有哪些过时的记忆应该被更新或淘汰？

返回JSON：{{"to_fix": [{{"id": "...", "reason": "..."}}], "conflicts": [...], "patterns": [...], "to_retire": [...]}}"""

    reply = await llm_chat(db, [{"role": "user", "content": prompt}])
    from app.json_extractor import extract_json
    parsed = extract_json(reply)

    if isinstance(parsed, dict):
        for item in parsed.get("to_fix", []):
            mid = item.get("id", "")
            if mid:
                await memory_update(db, mid, confidence=0.3)
        for mid in parsed.get("to_retire", []):
            if isinstance(mid, str):
                await memory_update(db, mid, confidence=0.1)
        await memory_save(
            db, agent_name,
            f"反思发现：{json.dumps(parsed, ensure_ascii=False)[:200]}",
            memory_type="experience",
            confidence=0.6,
        )
        return parsed

    return {"insights": reply[:500], "raw": True}


async def memory_share(
    db: DbAdapter,
    memory_id: str,
    target_agent: str = SHARED,
) -> str:
    """Share a memory to another agent or shared pool."""
    rows = await db.query(
        "SELECT * FROM agent_memories WHERE id = ?", (memory_id,)
    )
    if not rows:
        return ""
    source = rows[0]
    new_id = await memory_save(
        db, target_agent,
        source["content"],
        source["memory_type"],
        json.loads(source.get("tags") or "[]"),
        json.loads(source.get("context") or "{}"),
        source.get("confidence", 0.5),
    )
    return new_id


async def memory_consolidate(
    db: DbAdapter,
    agent_name: str,
    similarity_threshold: float = 0.7,
) -> dict[str, int]:
    """Merge similar memories to prevent bloat. Returns stats."""
    rows = await db.query(
        "SELECT id, content, memory_type, tags FROM agent_memories WHERE agent_name = ? AND superseded_by IS NULL ORDER BY created_at DESC",
        (agent_name,),
    )

    merged = 0
    retained = 0
    seen_content: list[dict[str, Any]] = []

    for row in rows:
        content = row["content"].lower()
        is_dup = False
        for seen in seen_content:
            overlap = _text_overlap(content, seen["content"])
            if overlap >= similarity_threshold:
                await db.execute(
                    "UPDATE agent_memories SET superseded_by = ? WHERE id = ?",
                    (seen["id"], row["id"]),
                )
                merged += 1
                is_dup = True
                break
        if not is_dup:
            seen_content.append({"id": row["id"], "content": content})
            retained += 1

    return {"merged": merged, "retained": retained, "total": len(rows)}


def _text_overlap(a: str, b: str) -> float:
    """Calculate word-level overlap ratio between two strings."""
    if not a or not b:
        return 0.0
    words_a = set(a[i:i+2] for i in range(len(a)-1))
    words_b = set(b[i:i+2] for i in range(len(b)-1))
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)


def _format_memory(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id", ""),
        "agent_name": row.get("agent_name", ""),
        "memory_type": row.get("memory_type", ""),
        "content": row.get("content", ""),
        "tags": json.loads(row.get("tags") or "[]"),
        "context": json.loads(row.get("context") or "{}"),
        "confidence": row.get("confidence", 0.5),
        "times_used": row.get("times_used", 0),
        "success_count": row.get("success_count", 0),
        "created_at": row.get("created_at", ""),
        "updated_at": row.get("updated_at", ""),
        "superseded_by": row.get("superseded_by"),
    }
