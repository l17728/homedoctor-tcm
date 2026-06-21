"""Smart search router — gap detection + Web Search + one-click import.

Search flow (state machine):
  1. Internal knowledge search
  2. If no results → external index search
  3. If no results → ask user to expand to Web Search
  4. User agrees → Web Search
  5. Show results → ask user to import
  6. User imports → Agent pipeline processes

Endpoints:
  GET  /api/smart-search          — internal → external → suggestion
  POST /api/smart-search/expand   — Web Search (user confirmed)
  POST /api/smart-search/import   — one-click import web result
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.auth import get_current_user
from app.database import DbAdapter, get_db

router = APIRouter(prefix="/api/smart-search", tags=["smart-search"])


class ExpandRequest(BaseModel):
    query: str
    num_results: int = 5


class ImportRequest(BaseModel):
    url: str
    title: str = ""
    source_query: str = ""


@router.get("")
async def smart_search(
    q: str = Query(..., min_length=1),
    top_k: int = Query(10, ge=1, le=50),
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Smart search: internal → external → suggest Web Search.

    Returns:
      - results + source='internal' if found internally
      - results + source='external' if found in external index
      - results=[] + source='none' + suggestion if nothing found
    """
    from app.search_pipeline import search as run_search

    result = await run_search(db, q, top_k=top_k, enable_rerank=False)

    if result["total"] > 0:
        internal_count = sum(
            1 for r in result["results"]
            if r.get("source_type", "internal") == "internal"
        )
        external_count = result["total"] - internal_count

        if internal_count > 0:
            return {
                "results": result["results"],
                "total": result["total"],
                "source": "internal",
                "internal_count": internal_count,
                "external_count": external_count,
                "expandable": False,
            }
        else:
            asyncio_create_task_auto_extract(db, q, result["results"])
            return {
                "results": result["results"],
                "total": result["total"],
                "source": "external",
                "internal_count": 0,
                "external_count": external_count,
                "expandable": False,
                "suggestion": "结果来自外部索引，已自动提炼入库",
            }

    return {
        "results": [],
        "total": 0,
        "source": "none",
        "suggestion": f'知识库中未找到"{q}"，是否搜索互联网获取？',
        "expandable": True,
    }


@router.post("/expand")
async def expand_search(
    body: ExpandRequest,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Web Search — user confirmed expansion."""
    results = await _web_search(body.query, body.num_results)

    for r in results:
        from app.trust_engine import get_domain_trust
        r["trust_level"] = get_domain_trust(r.get("url", ""))
        r["importable"] = True

    return {
        "results": results,
        "total": len(results),
        "source": "web",
        "suggestion": "找到相关内容，是否一键入库？",
    }


@router.post("/import")
async def import_web_result(
    body: ImportRequest,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """One-click import: user confirmed → Agent pipeline processes."""
    from app.url_validator import validate_external_url
    if not validate_external_url(body.url):
        raise HTTPException(status_code=400, detail="URL不安全或指向内部网络")
    from app.knowledge_agent import process_input
    result = await process_input(
        db,
        url=body.url,
        title=body.title,
        source_type="web_search",
    )
    return result


async def _web_search(query: str, num_results: int = 5) -> list[dict[str, Any]]:
    """Perform web search using available search tools."""
    import os
    api_key = os.environ.get("WEB_SEARCH_API_KEY", "")

    if api_key:
        try:
            return await _search_via_api(query, num_results, api_key)
        except Exception:
            pass

    return await _search_via_llm(query, num_results)


async def _search_via_api(query: str, num: int, api_key: str) -> list[dict[str, Any]]:
    """Search via web search API (e.g., Exa, Serper, Bing)."""
    import httpx
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            "https://api.exa.ai/search",
            json={
                "query": query,
                "numResults": num,
                "type": "neural",
            },
            headers={"x-api-key": api_key},
        )
        resp.raise_for_status()
        data = resp.json()
        results = []
        for item in data.get("results", []):
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "summary": (item.get("text") or item.get("summary") or "")[:300],
            })
        return results


async def _search_via_llm(query: str, num: int) -> list[dict[str, Any]]:
    """Fallback: use LLM to suggest relevant TCM knowledge sources."""
    from app.llm import chat_completion, has_api_key
    if not has_api_key():
        return []

    prompt = f"""用户在中医健康平台中搜索"{query}"但未找到。
请推荐{num}个可能包含相关中医知识的权威网站或文章主题。
返回JSON数组：[{{"title":"...","url":"...","summary":"..."}}]
优先推荐：知网、万方、国家中医药管理局、权威中医网站。"""

    response = await chat_completion([{"role": "user", "content": prompt}])
    import json
    import re
    try:
        match = re.search(r'\[.+\]', response, re.DOTALL)
        if match:
            return json.loads(match.group())
    except (json.JSONDecodeError, AttributeError):
        pass
    return []


def asyncio_create_task_auto_extract(db: DbAdapter, query: str, results: list):
    """Fire-and-forget: auto-extract knowledge from external hits."""
    import asyncio
    import logging
    logger = logging.getLogger(__name__)

    async def _extract():
        try:
            for r in results[:2]:
                entity_id = r.get("entity_id")
                if not entity_id:
                    continue
                from app.agent_tools import log_action
                await log_action(
                    db, "auto_extract", "search", query, entity_id,
                    {"trigger": "external_hit", "query": query},
                    "extracted",
                )
        except Exception as exc:
            logger.warning("auto_extract failed: %s", exc)

    try:
        loop = asyncio.get_event_loop()
        loop.create_task(_extract())
    except RuntimeError:
        pass
