"""Knowledge Feeder — 巡检Agent (knowledge patrol agent).

Runs periodically (daily via cron or startup trigger). Acts as a "知识feeder":
  1. Scans knowledge base for gaps (missing fields, thin entities)
  2. Constructs TCM-focused search queries (中医/中药/方剂/经络/功法 only)
  3. Web searches for relevant content
  4. Feeds URLs to the app's process_input pipeline
  5. App handles the rest: extract → review → import → index → relate

IMPORTANT: Only feeds Chinese traditional culture + TCM content.
Western medicine is excluded — manually entered only.

Usage:
    # Manual trigger
    POST /api/admin/feeder/scan

    # Check last scan results
    GET /api/admin/feeder/status
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from app.database import DbAdapter

logger = logging.getLogger(__name__)

TCM_DOMAINS = [
    "cnki.net", "wanfangdata.com.cn", "39yst.com",
    "zyys.com", "cntcm.org.cn", "satcm.gov.cn",
]

GAP_QUERIES = {
    "herb": [
        "中药 {name} 功效主治 用量 禁忌",
        "{name} 现代药理研究 临床应用",
        "{name} 炮制方法 配伍禁忌",
    ],
    "formula": [
        "方剂 {name} 组成 君臣佐使 加减变化",
        "{name} 现代临床研究 医案",
    ],
    "acupoint": [
        "穴位 {name} 定位 刺法 主治 配伍",
        "{name} 现代研究 针灸临床",
    ],
    "health_practice": [
        "功法 {name} 练习步骤 呼吸方法 心法要诀",
        "{name} 功效 适应人群 禁忌",
    ],
}


async def run_feeder_scan(db: DbAdapter, max_feeds: int = 10) -> dict[str, Any]:
    """Run a knowledge gap scan and feed URLs to process_input.

    Returns summary: {gaps_found, urls_discovered, feeds_sent, adopted}
    """
    gaps = await _detect_gaps(db)
    if not gaps:
        return {"gaps_found": 0, "feeds_sent": 0, "message": "知识库完整，无缺口"}

    feeds_sent = 0
    adopted = 0
    results: list[dict] = []

    for gap in gaps[:max_feeds]:
        query = gap["query"]
        urls = await _search_tcm_content(query)

        for url in urls[:2]:
            if not _is_tcm_safe_url(url.get("url", "")):
                continue

            result = await _feed_url(db, url, gap)
            feeds_sent += 1
            results.append({
                "gap": gap["entity_title"],
                "url": url.get("url", ""),
                "decision": result.get("decision", "unknown"),
            })
            if result.get("decision") in ("created", "merged", "adopted"):
                adopted += 1
            break

    return {
        "gaps_found": len(gaps),
        "feeds_sent": feeds_sent,
        "adopted": adopted,
        "results": results[:10],
        "message": f"巡检完成：发现{len(gaps)}个缺口，投喂{feeds_sent}个链接，采纳{adopted}个",
    }


async def _detect_gaps(db: DbAdapter) -> list[dict[str, Any]]:
    """Detect knowledge gaps — entities with incomplete data."""
    gaps: list[dict[str, Any]] = []

    rows = await db.query(
        """SELECT id, title, entity_type, properties, summary
             FROM knowledge_entities
            WHERE status = 'active'
              AND entity_type IN ('herb', 'formula', 'acupoint', 'health_practice')
              AND tenant_id IS NULL
            ORDER BY view_count ASC
            LIMIT 50"""
    )

    for row in rows:
        props = _parse_json(row.get("properties"), {})
        entity_type = row.get("entity_type", "")
        templates = GAP_QUERIES.get(entity_type, [])

        if not templates:
            continue

        is_thin = False
        if entity_type == "herb":
            required = ["nature", "flavor", "meridians", "dosage_min_g", "contraindications"]
            missing = [f for f in required if not props.get(f)]
            if len(missing) >= 2:
                is_thin = True
        elif entity_type == "acupoint":
            required = ["location", "needling", "functions"]
            missing = [f for f in required if not props.get(f)]
            if len(missing) >= 2:
                is_thin = True
        elif entity_type == "health_practice":
            required = ["breathing", "mental_focus", "indications"]
            missing = [f for f in required if not props.get(f)]
            if len(missing) >= 2:
                is_thin = True
        elif entity_type == "formula":
            if not props.get("composition") or not props.get("modifications"):
                is_thin = True

        if is_thin:
            query = templates[0].format(name=row["title"])
            gaps.append({
                "entity_id": row["id"],
                "entity_title": row["title"],
                "entity_type": entity_type,
                "missing_fields": missing if entity_type in ("herb", "acupoint", "health_practice") else ["composition", "modifications"],
                "query": query,
            })

    return gaps


async def _search_tcm_content(query: str) -> list[dict[str, str]]:
    """Search for TCM content using real web search API.

    Falls back to LLM topic suggestion (no URLs) if no search API configured.
    Never returns hallucinated URLs.
    """
    import os
    api_key = os.environ.get("WEB_SEARCH_API_KEY", "")

    if api_key:
        try:
            return await _search_via_api(query, 3, api_key)
        except Exception as exc:
            logger.warning("feeder: web search API failed: %s", exc)

    from app.llm_unified import llm_chat
    prompt = f"""搜索需求：{query}

请列出与此主题相关的权威中医知识来源（书名、期刊、网站名称），但不要编造URL。
返回JSON：{{"topics": ["主题1", "主题2"], "sources": ["来源1", "来源2"]}}"""

    reply = await llm_chat(query_db_adapter(), [{"role": "user", "content": prompt}])

    from app.json_extractor import extract_json
    parsed = extract_json(reply)
    if isinstance(parsed, dict):
        topics = parsed.get("topics", [])
        sources = parsed.get("sources", [])
        logger.info("feeder: LLM suggested topics (no URLs to avoid hallucination): %s, sources: %s", topics, sources)

    return []


async def _search_via_api(query: str, num: int, api_key: str) -> list[dict[str, str]]:
    import httpx
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            "https://api.exa.ai/search",
            json={"query": query, "numResults": num, "type": "neural"},
            headers={"x-api-key": api_key},
        )
        resp.raise_for_status()
        data = resp.json()
        return [
            {"title": item.get("title", ""), "url": item.get("url", ""),
             "summary": (item.get("text") or item.get("summary") or "")[:300]}
            for item in data.get("results", [])
        ]


_db_ref: DbAdapter | None = None

def query_db_adapter() -> DbAdapter:
    """Get the global DB adapter for feeder use."""
    global _db_ref
    if _db_ref is None:
        from app.database import _db_adapter
        _db_ref = _db_adapter
    return _db_ref


def _is_tcm_safe_url(url: str) -> bool:
    """Check URL is TCM-relevant and not western medicine."""
    from app.url_validator import validate_external_url
    if not validate_external_url(url):
        return False
    url_lower = url.lower()
    western_keywords = ["pharmacy", "drugbank", "pubmed", "mayoclinic", "webmd",
                        "fda.gov", "who.int", "ibuprofen", "aspirin", "antibiotic"]
    for kw in western_keywords:
        if kw in url_lower:
            return False
    return True


async def _feed_url(db: DbAdapter, url_info: dict, gap: dict) -> dict[str, Any]:
    """Feed a URL to process_input — the app handles the rest."""
    from app.knowledge_agent import process_input

    try:
        result = await process_input(
            db,
            url=url_info.get("url", ""),
            title=url_info.get("title", gap["entity_title"]),
            source_type="feeder",
        )
        return result
    except Exception as exc:
        logger.warning("feeder: feed failed for %s: %s", url_info.get("url", ""), exc)
        return {"decision": "failed", "message": str(exc)[:100]}


def _parse_json(raw: Any, default: Any) -> Any:
    import json as _json
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, str):
        try:
            return _json.loads(raw)
        except (_json.JSONDecodeError, TypeError):
            return default
    return default
