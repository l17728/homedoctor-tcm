from __future__ import annotations

import json
import logging
from typing import Any

from app.database import DbAdapter

logger = logging.getLogger(__name__)

__all__ = [
    "tool_query_logs",
    "tool_optimize_prompt",
    "tool_apply_prompt_optimization",
    "tool_optimize_and_apply",
    "tool_generalize_experience",
    "memory_save_tool",
    "_AGENT_CONFIGS",
    "_load_configs_from_db",
    "tool_get_config",
    "tool_set_config",
]


async def tool_query_logs(
    db: DbAdapter,
    entity_id: str | None = None,
    action_type: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    conditions = []
    params: list[Any] = []
    if entity_id:
        conditions.append("entity_id = ?")
        params.append(entity_id)
    if action_type:
        conditions.append("action_type = ?")
        params.append(action_type)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = await db.query(
        f"SELECT * FROM agent_logs {where} ORDER BY created_at DESC LIMIT ?",
        tuple(params + [limit]),
    )
    return [dict(r) for r in rows]


async def tool_optimize_prompt(
    db: DbAdapter, agent_name: str, current_prompt: str,
) -> dict[str, Any]:
    from app.llm_unified import llm_chat
    from app.agent_memory import memory_search
    from app.json_extractor import extract_json

    lessons = await memory_search(db, agent_name, memory_type="lesson", min_confidence=0.6, limit=10)

    prompt = f"""你是{agent_name}。请审视你的系统提示词和最近的教训，提出优化建议。

当前提示词：
{current_prompt[:1000]}

最近的教训（高置信度）：
{chr(10).join(f'- {m["content"][:80]}' for m in lessons) if lessons else '无'}

请分析：
1. 哪些教训应该融入提示词？
2. 提示词中哪些规则可以被简化？
3. 是否有新规则应该添加？

返回JSON：{{"additions": [...], "deletions": [...], "modifications": [...]}}"""

    reply = await llm_chat(db, [{"role": "user", "content": prompt}])
    suggestions = extract_json(reply)

    await memory_save_tool(db, agent_name,
        f"提示词优化建议：{json.dumps(suggestions, ensure_ascii=False)[:200] if isinstance(suggestions, dict) else reply[:200]}",
        "experience", confidence=0.6)

    return suggestions if isinstance(suggestions, dict) else {"raw_suggestions": reply[:500]}


async def tool_apply_prompt_optimization(
    db: DbAdapter, agent_name: str, suggestions: dict[str, Any],
) -> dict[str, Any]:
    applied: list[dict[str, Any]] = []

    for suggestion in suggestions.get("modifications", []):
        field = suggestion.get("field")
        new_value = suggestion.get("new_value", suggestion.get("new"))
        if field and new_value is not None:
            result = await tool_set_config(db, agent_name, f"prompt_{field}", new_value)
            applied.append(result)

    for i, addition in enumerate(suggestions.get("additions", [])):
        if addition:
            result = await tool_set_config(db, agent_name, f"prompt_addition_{i}", addition)
            applied.append(result)

    summary = {
        "agent": agent_name,
        "applied_count": len(applied),
        "changes": applied,
    }

    await memory_save_tool(db, agent_name,
        f"提示词优化已应用：{len(applied)}项变更",
        "experience", confidence=0.7)

    return summary


async def tool_optimize_and_apply(
    db: DbAdapter, agent_name: str, current_prompt: str,
) -> dict[str, Any]:
    suggestions = await tool_optimize_prompt(db, agent_name, current_prompt)

    has_actionable = bool(
        suggestions.get("modifications") or suggestions.get("additions")
    )

    applied: dict[str, Any] = {}
    if has_actionable:
        applied = await tool_apply_prompt_optimization(db, agent_name, suggestions)

    return {"suggestions": suggestions, "applied": applied}


async def tool_generalize_experience(
    db: DbAdapter, agent_name: str, case_description: str,
) -> dict[str, Any]:
    from app.llm_unified import llm_chat
    from app.json_extractor import extract_json

    prompt = f"""从以下具体处理案例中，提取通用规则：

案例：{case_description}

请提取：
1. 这属于哪类问题？
2. 适用的通用解决方案是什么？
3. 下次遇到类似问题应该怎么做？

返回JSON：{{"problem_type": "...", "pattern": "...", "strategy": "..."}}"""

    reply = await llm_chat(db, [{"role": "user", "content": prompt}])
    result = extract_json(reply)

    if isinstance(result, dict):
        await memory_save_tool(db, agent_name,
            f"通用模式[{result.get('problem_type', '')}]：{result.get('strategy', '')}",
            "pattern", confidence=0.7)

    return result if isinstance(result, dict) else {"raw": reply[:500]}


async def memory_save_tool(db: DbAdapter, agent_name: str, content: str,
                           memory_type: str = "experience", confidence: float = 0.5) -> str:
    from app.agent_memory import memory_save
    return await memory_save(db, agent_name, content, memory_type, confidence=confidence)


_AGENT_CONFIGS: dict[str, dict[str, Any]] = {
    "knowledge_agent": {
        "temperature": 0.3,
        "max_tokens": 2048,
        "quality_threshold": 50,
        "trust_threshold_adopt": 80,
        "dedup_mode": "exact_title",
        "auto_relate_enabled": True,
        "structured_extraction_enabled": True,
        "max_entities_per_import": 10,
    },
    "patrol_agent": {
        "scan_interval_hours": 24,
        "max_feeds_per_scan": 10,
        "tcm_only": True,
        "gap_threshold": 2,
        "search_query_limit": 3,
    },
    "shared": {
        "enhanced_mode": False,
        "enhanced_num_models": 4,
        "min_trust_for_safety": "A",
        "bm25_field_weights": {"title": 3.0, "summary": 2.0, "keywords": 1.0, "tags": 1.0},
    },
}


async def _load_configs_from_db(db: DbAdapter) -> None:
    try:
        rows = await db.query("SELECT agent_name, config_key, config_value FROM agent_configs")
        for row in rows:
            agent = row["agent_name"]
            key = row["config_key"]
            try:
                value = json.loads(row["config_value"])
            except (json.JSONDecodeError, TypeError):
                continue
            _AGENT_CONFIGS.setdefault(agent, {})[key] = value
    except Exception:
        logger.warning("Failed to load agent configs from DB", exc_info=True)


async def tool_get_config(db: DbAdapter, agent_name: str = "shared", key: str | None = None) -> dict[str, Any]:
    config = _AGENT_CONFIGS.get(agent_name, {})
    if key:
        return {"agent": agent_name, "key": key, "value": config.get(key)}
    return {"agent": agent_name, "config": config}


async def tool_set_config(db: DbAdapter, agent_name: str, key: str, value: Any) -> dict[str, Any]:
    if agent_name not in _AGENT_CONFIGS:
        _AGENT_CONFIGS[agent_name] = {}
    old_value = _AGENT_CONFIGS[agent_name].get(key)
    _AGENT_CONFIGS[agent_name][key] = value
    try:
        await db.execute(
            "INSERT OR REPLACE INTO agent_configs (agent_name, config_key, config_value, updated_at) "
            "VALUES (?, ?, ?, datetime('now'))",
            (agent_name, key, json.dumps(value)),
        )
    except Exception:
        logger.warning("Failed to persist agent config to DB", exc_info=True)
    from app.agent_tools import log_action
    await log_action(db, "config_change", "config", key, "",
                     {"agent": agent_name, "key": key, "old": old_value, "new": value},
                     "updated")
    return {"agent": agent_name, "key": key, "old_value": old_value, "new_value": value}
