"""AI classification management router — 标签推荐 + 重复检测 + 合并 + 自动标注 (spec §7.3 V2).

Endpoints
---------
- ``POST /api/ai-classify/suggest``     — recommend 1-3 classification tags via LLM
- ``POST /api/ai-classify/duplicates``  — detect potential duplicates by title similarity
- ``POST /api/ai-classify/merge``       — merge two knowledge entries into one
- ``POST /api/ai-classify/auto-tag``    — batch-classify all untagged bookmarks

All text values use Chinese domain language (spec §1.7).  When the LLM API
key is not configured, the ``suggest`` and ``auto-tag`` endpoints gracefully
fall back to keyword-based tag heuristics so the system remains functional
offline (spec §0 — 本地优先，无云端依赖).
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import get_current_user
from app.config import settings
from app.database import DbAdapter, get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai-classify", tags=["ai-classify"])

#: Similarity threshold (>80% character overlap) for duplicate detection.
DUPLICATE_SIMILARITY_THRESHOLD = 0.80


# ---------------------------------------------------------------------------
# Keyword-based fallback tag sets (used when LLM is unavailable)
# ---------------------------------------------------------------------------

#: Maps TCM efficacy keywords → recommended tag.
_KEYWORD_TAG_MAP: dict[str, str] = {
    "补气": "补气",
    "益气": "补气",
    "健脾": "健脾",
    "补脾": "健脾",
    "补血": "补血",
    "养血": "补血",
    "滋阴": "滋阴",
    "补阴": "滋阴",
    "温阳": "温阳",
    "补阳": "温阳",
    "清热": "清热",
    "解毒": "清热解毒",
    "活血": "活血化瘀",
    "化瘀": "活血化瘀",
    "安神": "安神",
    "祛湿": "祛湿",
    "化痰": "化痰",
    "止咳": "止咳平喘",
    "平喘": "止咳平喘",
    "补肾": "补肾",
    "明目": "明目",
    "润肺": "润肺",
    "感冒": "感冒调理",
    "风寒": "感冒调理",
    "风热": "感冒调理",
    "失眠": "失眠调理",
    "便秘": "通便",
    "润肠": "通便",
    "消食": "消食导滞",
    "湿气": "祛湿",
    "气虚": "气虚体质",
    "阳虚": "阳虚体质",
    "阴虚": "阴虚体质",
    "痰湿": "痰湿体质",
    "湿热": "湿热体质",
    "日常": "日常保健",
    "保健": "日常保健",
    "养生": "日常保健",
    "食疗": "食疗",
    "茶饮": "代茶饮",
    "穴位": "穴位按摩",
}

#: Categories of tags to suggest when title/content match health keywords.
_HEALTH_TAGS = {"体质调理", "日常保健", "食疗", "代茶饮", "穴位按摩"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _keyword_fallback_tags(title: str, content: str) -> list[str]:
    """Return 1-3 tags based on keyword matching when LLM is unavailable.

    Scans the concatenated title+content for TCM/health keywords and maps
    them to tags.  Caps at 3 unique tags per spec.
    """
    text = f"{title} {content}"
    tags: list[str] = []
    for keyword, tag in _KEYWORD_TAG_MAP.items():
        if keyword in text and tag not in tags:
            tags.append(tag)
        if len(tags) >= 3:
            break
    if not tags:
        tags.append("日常保健")
    return tags[:3]


async def _call_llm_for_tags(prompt: str) -> str | None:
    """Call the LLM with the tag-suggestion prompt.

    Returns the raw text response, or ``None`` if the LLM is unavailable
    (no API key) or the call fails — enabling graceful degradation.
    """
    if not settings.LLM_API_KEY:
        logger.info("AI-classify: LLM_API_KEY not configured — using keyword fallback")
        return None

    chat_url = f"{settings.LLM_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.LLM_API_KEY}",
        "Content-Type": "application/json",
    }

    models = [settings.LLM_MODEL]
    fallbacks = [m.strip() for m in settings.LLM_FALLBACK_MODELS.split(",") if m.strip()]
    for m in fallbacks:
        if m not in models:
            models.append(m)

    last_error = ""
    for model in models:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 256,
        }
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(chat_url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as e:
            last_error = f"HTTP {e.response.status_code}"
            logger.warning("AI-classify: model %s failed (%s), trying next", model, last_error)
        except Exception as e:
            last_error = str(e)
            logger.warning("AI-classify: model %s failed (%s), trying next", model, last_error)

    logger.error("AI-classify: all models failed. Last error: %s", last_error)
    return None


def _parse_tag_list(response: str) -> list[str]:
    """Parse an LLM response into a list of tag strings.

    Handles: raw JSON array, markdown code blocks, comma-separated text.
    """
    if not response or not response.strip():
        return []

    text = response.strip()

    # Extract from markdown code block
    code_match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if code_match:
        text = code_match.group(1).strip()

    # Try JSON array
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [str(t).strip() for t in parsed if str(t).strip()]
        if isinstance(parsed, str):
            text = parsed
    except (json.JSONDecodeError, TypeError):
        pass

    # Try regex extract of a JSON array
    arr_match = re.search(r"\[.*?\]", text, re.DOTALL)
    if arr_match:
        try:
            parsed = json.loads(arr_match.group(0))
            if isinstance(parsed, list):
                return [str(t).strip() for t in parsed if str(t).strip()]
        except (json.JSONDecodeError, TypeError):
            pass

    # Fall back to comma-separated or newline-separated text
    parts = re.split(r"[,，\n]", text)
    tags = [p.strip().strip('"""\'') for p in parts if p.strip()]
    return tags[:3]


def _title_similarity(a: str, b: str) -> float:
    """Compute title similarity as character-overlap ratio.

    Uses the Jaccard coefficient on character sets (spec §7.3: ">80% char overlap").
    Returns a value in ``[0.0, 1.0]``.
    """
    if not a or not b:
        return 0.0
    set_a = set(a)
    set_b = set(b)
    if not set_a and not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union) if union else 0.0


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/suggest")
async def suggest_tags(
    body: dict,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """推荐 1-3 个分类标签.

    Sends ``{title}`` and ``{content[:500]}`` to the LLM with a classification
    prompt.  When the LLM is unavailable, falls back to keyword-based tag
    matching so the endpoint remains functional offline.

    Returns ``{"suggested_tags": ["补气药", "健脾", "日常保健"]}``.
    """
    entry_type = body.get("entry_type", "knowledge")
    title = body.get("title", "")
    content = body.get("content", "")

    if not title and not content:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="title 或 content 至少需要一个",
        )

    prompt = (
        f"请为以下内容推荐1-3个分类标签（JSON数组）：\n"
        f"标题：{title}\n"
        f"内容：{content[:500]}"
    )

    raw_response = await _call_llm_for_tags(prompt)

    if raw_response is not None:
        tags = _parse_tag_list(raw_response)
        if tags:
            return {"suggested_tags": tags[:3]}

    # Fallback: keyword-based matching
    tags = _keyword_fallback_tags(title, content)
    return {"suggested_tags": tags}


@router.post("/duplicates")
async def detect_duplicates(
    body: dict,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """检测潜在重复条目 (>80% 字符重叠).

    Accepts ``{"entries": [{"id", "title", "content"}, ...]}`` and returns
    pairs whose title similarity exceeds the threshold.

    Returns ``{"duplicates": [{"id_a", "id_b", "similarity", "reason"}]}``.
    """
    entries = body.get("entries", [])
    if not isinstance(entries, list) or len(entries) < 2:
        return {"duplicates": []}

    duplicates: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str]] = set()

    for i, a in enumerate(entries):
        for j in range(i + 1, len(entries)):
            b = entries[j]
            id_a = a.get("id")
            id_b = b.get("id")
            if not id_a or not id_b:
                continue
            key = tuple(sorted([str(id_a), str(id_b)]))
            if key in seen_pairs:
                continue

            title_a = str(a.get("title", ""))
            title_b = str(b.get("title", ""))
            sim = _title_similarity(title_a, title_b)

            if sim >= DUPLICATE_SIMILARITY_THRESHOLD:
                seen_pairs.add(key)
                duplicates.append({
                    "id_a": id_a,
                    "id_b": id_b,
                    "similarity": round(sim, 3),
                    "reason": f"标题相似度 {round(sim * 100)}%（{title_a} vs {title_b}）",
                })

    return {"duplicates": duplicates}


@router.post("/merge")
async def merge_entries(
    body: dict,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """合并两个知识条目.

    - Combines ``content`` (source appended to target)
    - Merges ``tags`` (union, deduplicated)
    - Redirects ``favorites`` that referenced ``source_id`` → ``target_id``
    - Deletes the source entry after merge

    Returns ``{"merged_id": target_id, "deleted_id": source_id}``.
    """
    source_id = body.get("source_id")
    target_id = body.get("target_id")

    if not source_id or not target_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="source_id 和 target_id 为必填项",
        )
    if source_id == target_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="source_id 和 target_id 不能相同",
        )

    user_id = current_user["id"]

    source = await db.query_one(
        "SELECT * FROM knowledge_entries WHERE id = ? AND user_id = ?",
        (source_id, user_id),
    )
    target = await db.query_one(
        "SELECT * FROM knowledge_entries WHERE id = ? AND user_id = ?",
        (target_id, user_id),
    )

    if not source:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到源条目（source_id）",
        )
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到目标条目（target_id）",
        )

    # --- Merge content ---
    source_content = source.get("content") or ""
    target_content = target.get("content") or ""
    merged_content = target_content
    if source_content and source_content not in target_content:
        merged_content = f"{target_content}\n\n---\n\n{source_content}".strip()

    # --- Merge tags ---
    def _parse_tags(raw: Any) -> list[str]:
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return [str(t) for t in parsed]
            except (json.JSONDecodeError, TypeError):
                return []
        if isinstance(raw, list):
            return [str(t) for t in raw]
        return []

    source_tags = _parse_tags(source.get("tags"))
    target_tags = _parse_tags(target.get("tags"))
    merged_tags: list[str] = []
    for t in target_tags + source_tags:
        if t not in merged_tags:
            merged_tags.append(t)

    await db.execute(
        "UPDATE knowledge_entries SET content = ?, tags = ?, updated_at = ? WHERE id = ?",
        (merged_content, json.dumps(merged_tags, ensure_ascii=False), _now(), target_id),
    )

    # --- Redirect favorites that pointed to source_id ---
    await db.execute(
        "UPDATE favorites SET entry_id = ? WHERE entry_id = ? AND user_id = ?",
        (target_id, source_id, user_id),
    )

    # --- Delete source entry ---
    await db.execute(
        "DELETE FROM knowledge_entries WHERE id = ? AND user_id = ?",
        (source_id, user_id),
    )

    return {"merged_id": target_id, "deleted_id": source_id}


@router.post("/auto-tag")
async def auto_tag_bookmarks(
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """批量自动标注无标签书签.

    Finds all bookmarks (``favorites`` table) with empty tags and suggests
    tags for each using the same logic as ``/suggest``.  Updates the tag
    field in-place.

    Returns ``{"classified": N, "failed": N}``.
    """
    user_id = current_user["id"]

    # Find bookmarks with empty or missing tags
    rows = await db.query(
        "SELECT * FROM favorites WHERE user_id = ? AND entry_type != 'collection'",
        (user_id,),
    )

    untagged: list[dict[str, Any]] = []
    for r in rows:
        tags_raw = r.get("tags", "[]")
        tags: list[str] = []
        if isinstance(tags_raw, str):
            try:
                tags = json.loads(tags_raw)
            except (json.JSONDecodeError, TypeError):
                tags = []
        elif isinstance(tags_raw, list):
            tags = tags_raw
        if not tags:
            untagged.append(r)

    classified = 0
    failed = 0

    for entry in untagged:
        entry_id = entry.get("id")
        title = str(entry.get("title", ""))
        content = str(entry.get("content", ""))

        if not title and not content:
            failed += 1
            continue

        prompt = (
            f"请为以下内容推荐1-3个分类标签（JSON数组）：\n"
            f"标题：{title}\n"
            f"内容：{content[:500]}"
        )

        raw_response = await _call_llm_for_tags(prompt)
        tags: list[str] = []

        if raw_response is not None:
            tags = _parse_tag_list(raw_response)

        if not tags:
            # Keyword fallback
            tags = _keyword_fallback_tags(title, content)

        if tags:
            await db.execute(
                "UPDATE favorites SET tags = ?, updated_at = ? WHERE id = ? AND user_id = ?",
                (json.dumps(tags[:3], ensure_ascii=False), _now(), entry_id, user_id),
            )
            classified += 1
        else:
            failed += 1

    return {"classified": classified, "failed": failed}
