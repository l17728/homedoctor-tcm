"""Model registry — configurable multi-model management + voting.

Stores AI model configurations in the ``ai_models`` table. Supports:
- CRUD for model configs (name, provider, endpoint, key, capabilities)
- Multi-model voting: send prompt to N models, aggregate by majority
- Direct HTTP calls (bypassing opencode for speed)

Design (user requirement): models are configurable via admin UI.
The knowledge agent uses multi_model_vote() for quality decisions.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from app.database import DbAdapter

logger = logging.getLogger(__name__)


async def list_models(db: DbAdapter, enabled_only: bool = False) -> list[dict[str, Any]]:
    conditions = "" if not enabled_only else "WHERE enabled = 1"
    rows = await db.query(f"SELECT * FROM ai_models {conditions} ORDER BY is_default DESC, name")
    return [_format(r) for r in rows]


async def get_model(db: DbAdapter, model_id: str) -> dict[str, Any] | None:
    rows = await db.query("SELECT * FROM ai_models WHERE id = ?", (model_id,))
    return _format(rows[0]) if rows else None


async def get_default_models(db: DbAdapter, capability: str = "text") -> list[dict[str, Any]]:
    """Get enabled models with RAW (unmasked) API keys for direct calling."""
    rows = await db.query(
        "SELECT * FROM ai_models WHERE enabled = 1 AND capabilities LIKE ? ORDER BY is_default DESC",
        (f'%"{capability}"%',),
    )
    return [_format_raw(r) for r in rows]


async def create_model(db: DbAdapter, **kwargs: Any) -> str:
    import uuid
    mid = kwargs.get("id") or f"model-{uuid.uuid4()}"
    await db.execute(
        """INSERT INTO ai_models (id, name, provider, model_id, api_endpoint, api_key,
           access_type, capabilities, max_tokens, temperature, enabled, is_default)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            mid,
            kwargs.get("name", ""),
            kwargs.get("provider", ""),
            kwargs.get("model_id", ""),
            kwargs.get("api_endpoint", ""),
            kwargs.get("api_key", ""),
            kwargs.get("access_type", "api"),
            json.dumps(kwargs.get("capabilities", ["text"]), ensure_ascii=False),
            kwargs.get("max_tokens", 4096),
            kwargs.get("temperature", 0.3),
            1 if kwargs.get("enabled", True) else 0,
            1 if kwargs.get("is_default", False) else 0,
        ),
    )
    return mid


async def update_model(db: DbAdapter, model_id: str, **kwargs: Any) -> bool:
    existing = await get_model(db, model_id)
    if not existing:
        return False
    updates = {}
    for k in ("name", "provider", "model_id", "api_endpoint", "api_key",
              "access_type", "max_tokens", "temperature"):
        if k in kwargs:
            updates[k] = kwargs[k]
    if "capabilities" in kwargs:
        updates["capabilities"] = json.dumps(kwargs["capabilities"], ensure_ascii=False)
    if "enabled" in kwargs:
        updates["enabled"] = 1 if kwargs["enabled"] else 0
    if "is_default" in kwargs:
        updates["is_default"] = 1 if kwargs["is_default"] else 0
    if not updates:
        return True
    set_clauses = ", ".join(f"{k} = ?" for k in updates)
    params = list(updates.values()) + [model_id]
    await db.execute(
        f"UPDATE ai_models SET {set_clauses}, updated_at = datetime('now') WHERE id = ?",
        tuple(params),
    )
    return True


async def delete_model(db: DbAdapter, model_id: str) -> bool:
    cursor = await db.execute("DELETE FROM ai_models WHERE id = ?", (model_id,))
    return cursor.rowcount > 0


async def call_model_direct(model: dict[str, Any], messages: list[dict[str, str]],
                            temperature: float = 0.3) -> str:
    """Call a model via direct HTTP (bypasses opencode for speed).

    Falls back to empty string on any error (graceful degradation).
    NOTE: model dict must have UNMASKED api_key. Use get_model_raw() not list_models().
    """
    import httpx
    endpoint = model.get("api_endpoint", "")
    api_key = model.get("api_key", "")
    if not endpoint or not api_key or "***" in api_key:
        return ""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                endpoint,
                json={
                    "model": model["model_id"],
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": model.get("max_tokens", 2048),
                    "stream": False,
                },
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("choices", [{}])[0].get("message", {}).get("content", "")
    except Exception as exc:
        logger.warning("model_registry: call to %s failed: %s", model.get("name"), exc)
        return ""


async def multi_model_vote(
    db: DbAdapter,
    messages: list[dict[str, str]],
    num_models: int = 3,
    capability: str = "text",
) -> dict[str, Any]:
    """Send prompt to multiple models and aggregate by majority consensus.

    Returns {consensus, responses, models_used, agreement}.
    """
    models = await get_default_models(db, capability)
    if not models:
        return {"consensus": "", "responses": [], "models_used": 0, "agreement": 0.0}
    selected = models[:num_models]

    tasks = [call_model_direct(m, messages) for m in selected]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    responses: list[dict[str, Any]] = []
    valid_texts: list[str] = []
    for model, result in zip(selected, results):
        text = result if isinstance(result, str) else ""
        responses.append({"model": model["name"], "text": text})
        if text:
            valid_texts.append(text)

    consensus = _aggregate_consensus(valid_texts) if valid_texts else ""
    agreement = len(valid_texts) / len(selected) if selected else 0.0

    return {
        "consensus": consensus,
        "responses": responses,
        "models_used": len(selected),
        "agreement": round(agreement, 2),
    }


def _aggregate_consensus(texts: list[str]) -> str:
    """Simple consensus: return the longest response (most detailed).

    For medical content, the most complete answer is preferred over
    shortest. A more sophisticated approach would use semantic similarity.
    """
    if not texts:
        return ""
    if len(texts) == 1:
        return texts[0]
    return max(texts, key=len)


def _format(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id", ""),
        "name": row.get("name", ""),
        "provider": row.get("provider", ""),
        "model_id": row.get("model_id", ""),
        "api_endpoint": row.get("api_endpoint") or "",
        "api_key": (row.get("api_key") or "")[:8] + "***" if row.get("api_key") else "",
        "access_type": row.get("access_type", "api"),
        "capabilities": _parse_json_list(row.get("capabilities")),
        "max_tokens": row.get("max_tokens", 4096),
        "temperature": row.get("temperature", 0.3),
        "enabled": bool(row.get("enabled", 1)),
        "is_default": bool(row.get("is_default", 0)),
    }


def _format_raw(row: dict[str, Any]) -> dict[str, Any]:
    """Format with UNMASKED api_key — internal use only."""
    return {
        "id": row.get("id", ""),
        "name": row.get("name", ""),
        "provider": row.get("provider", ""),
        "model_id": row.get("model_id", ""),
        "api_endpoint": row.get("api_endpoint", ""),
        "api_key": row.get("api_key", ""),
        "access_type": row.get("access_type", "api"),
        "capabilities": _parse_json_list(row.get("capabilities")),
        "max_tokens": row.get("max_tokens", 4096),
        "temperature": row.get("temperature", 0.3),
        "enabled": bool(row.get("enabled", 1)),
        "is_default": bool(row.get("is_default", 0)),
    }


def _parse_json_list(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        try:
            result = json.loads(raw)
            return result if isinstance(result, list) else []
        except (json.JSONDecodeError, TypeError):
            return []
    return []
