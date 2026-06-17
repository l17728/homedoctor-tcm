"""AI Knowledge Extractor (spec §8.4) — 自动从对话中提取健康知识点。

A secondary "Extractor AI" that runs independently from the main chat AI.
It analyses conversation flows and automatically identifies, extracts, and
sinks valuable health knowledge (herb efficacies, formula recommendations,
dietary therapy, acupoint massage, etc.) into structured knowledge cards.

Public API:
    - ``extract_knowledge(messages, db)``  — extract from a single conversation
    - ``auto_extract_for_user(user_id, db)`` — batch extract from recent conversations
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.config import settings
from app.database import DbAdapter

logger = logging.getLogger(__name__)

CST = timezone(timedelta(hours=8))

# ---------------------------------------------------------------------------
# Extraction prompt (spec §8.4)
# ---------------------------------------------------------------------------

EXTRACTION_PROMPT = (
    "你是一个中医药知识提取助手。分析以下对话，提取有价值的健康知识点"
    "（药材功效、方剂推荐、食疗方法、穴位按摩等）。\n"
    "返回JSON数组，每项包含以下字段：\n"
    '- "title": 知识点标题（简洁，不超过20字）\n'
    '- "content": 知识点详细内容（包含具体建议）\n'
    '- "category": 分类，必须是以下之一：'
    '"药材功效"、"方剂推荐"、"食疗方法"、"穴位按摩"、"养生建议"、"体质调理"\n'
    '- "herbs_mentioned": 提到的中药材名称列表（数组，如 ["黄芪", "当归"]）\n\n'
    "要求：\n"
    "1. 只提取有实际参考价值的知识点，忽略寒暄和无关内容\n"
    "2. 如果对话中没有有价值的知识点，返回空数组 []\n"
    "3. 只返回JSON，不要包含任何其他文字或解释\n"
)

VALID_CATEGORIES = frozenset({
    "药材功效",
    "方剂推荐",
    "食疗方法",
    "穴位按摩",
    "养生建议",
    "体质调理",
})

DEFAULT_CATEGORY = "养生建议"

# Max conversations to process in a single auto-extract run
MAX_CONVERSATIONS_PER_RUN = 20

# Rate limit window
RATE_LIMIT_HOURS = 1

# Content similarity threshold for dedup (normalized title match)
DEDUP_TITLE_SIMILARITY = 0.85


# ---------------------------------------------------------------------------
# LLM call for extraction
# ---------------------------------------------------------------------------

async def _call_llm_for_extraction(conversation_text: str) -> str | None:
    """Call the LLM with the extraction prompt.

    Returns the raw text response, or ``None`` if the LLM is unavailable
    (no API key) or the call fails — enabling graceful degradation.
    """
    if not settings.LLM_API_KEY:
        logger.info("Extractor: LLM_API_KEY not configured — skipping extraction")
        return None

    chat_url = f"{settings.LLM_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.LLM_API_KEY}",
        "Content-Type": "application/json",
    }

    # Build messages — extraction system prompt + conversation as user content
    messages = [
        {"role": "system", "content": EXTRACTION_PROMPT},
        {"role": "user", "content": conversation_text},
    ]

    model_chain = _get_model_chain()
    last_error: str = ""

    for model in model_chain:
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.3,  # low temperature for factual extraction
            "max_tokens": 2048,
        }
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(chat_url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                logger.info("Extractor: LLM extraction succeeded with model %s", model)
                return content
        except httpx.HTTPStatusError as e:
            last_error = f"HTTP {e.response.status_code}"
            logger.warning("Extractor: model %s failed (%s), trying next", model, last_error)
        except Exception as e:
            last_error = str(e)
            logger.warning("Extractor: model %s failed (%s), trying next", model, last_error)

    logger.error("Extractor: all models failed. Last error: %s", last_error)
    return None


def _get_model_chain() -> list[str]:
    """Return ordered list of models to try."""
    models = [settings.LLM_MODEL]
    fallbacks = [m.strip() for m in settings.LLM_FALLBACK_MODELS.split(",") if m.strip()]
    for m in fallbacks:
        if m not in models:
            models.append(m)
    return models


# ---------------------------------------------------------------------------
# JSON parsing
# ---------------------------------------------------------------------------

def _parse_extraction_response(response: str) -> list[dict[str, Any]]:
    """Parse the LLM response into a list of knowledge items.

    Handles common LLM output formats:
    - Raw JSON array
    - JSON wrapped in markdown code blocks (```json ... ```)
    - JSON with leading/trailing prose
    - Single JSON object (wrapped into a one-element list)
    """
    if not response or not response.strip():
        return []

    text = response.strip()

    # Try to extract from markdown code block first
    code_block_match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if code_block_match:
        text = code_block_match.group(1).strip()

    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            return [parsed]
    except (json.JSONDecodeError, TypeError):
        pass

    for pattern in (r"\[.*\]", r"\{.*\}"):
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(0))
                if isinstance(parsed, list):
                    return parsed
                if isinstance(parsed, dict):
                    return [parsed]
            except (json.JSONDecodeError, TypeError):
                continue

    logger.warning("Extractor: failed to parse LLM response as JSON")
    return []


def _validate_item(item: Any) -> dict[str, Any] | None:
    """Validate and normalise a single extracted knowledge item.

    Returns the cleaned item dict, or ``None`` if the item is invalid.
    """
    if not isinstance(item, dict):
        return None

    title = item.get("title")
    content = item.get("content")

    if not title or not content:
        return None

    title = str(title).strip()
    content = str(content).strip()

    if not title or not content:
        return None

    category = item.get("category", DEFAULT_CATEGORY)
    if category not in VALID_CATEGORIES:
        category = DEFAULT_CATEGORY

    herbs_mentioned = item.get("herbs_mentioned", [])
    if not isinstance(herbs_mentioned, list):
        herbs_mentioned = []
    herbs_mentioned = [str(h).strip() for h in herbs_mentioned if h]

    return {
        "title": title,
        "content": content,
        "category": category,
        "herbs_mentioned": herbs_mentioned,
    }


# ---------------------------------------------------------------------------
# Herb validation against DB
# ---------------------------------------------------------------------------

async def _validate_herbs(herbs: list[str], db: DbAdapter) -> list[str]:
    """Filter herbs list to only those that exist in the database.

    This prevents hallucinated herb names from being saved as knowledge.
    """
    if not herbs:
        return []

    validated: list[str] = []
    for name in herbs:
        row = await db.query_one(
            "SELECT id FROM herbs WHERE name = ? OR aliases LIKE ? LIMIT 1",
            (name, f"%{name}%"),
        )
        if row:
            validated.append(name)
        else:
            logger.debug("Extractor: herb '%s' not found in DB — filtered out", name)
    return validated


# ---------------------------------------------------------------------------
# Public API: extract_knowledge
# ---------------------------------------------------------------------------

def _build_conversation_text(messages: list[dict[str, Any]]) -> str:
    """Convert message list into a readable conversation string."""
    parts: list[str] = []
    role_labels = {"user": "用户", "assistant": "AI", "system": "系统"}
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if isinstance(content, list):
            # Handle multimodal content
            text_parts = [
                p.get("text", "") for p in content
                if isinstance(p, dict) and p.get("type") == "text"
            ]
            content = " ".join(text_parts)
        label = role_labels.get(role, role)
        parts.append(f"{label}: {content}")
    return "\n".join(parts)


async def extract_knowledge(
    messages: list[dict[str, Any]],
    db: DbAdapter,
) -> list[dict[str, Any]]:
    """Extract structured knowledge items from a conversation.

    Sends the conversation to the LLM with an extraction prompt, parses
    the response as JSON, validates herbs against the DB, and returns
    a list of structured knowledge items.

    Each item has: ``title``, ``content``, ``category``, ``herbs_mentioned``.

    Returns an empty list if the LLM is unavailable or no knowledge is found.
    """
    if not messages:
        return []

    conversation_text = _build_conversation_text(messages)

    # Call LLM for extraction
    raw_response = await _call_llm_for_extraction(conversation_text)
    if raw_response is None:
        logger.info("Extractor: LLM unavailable — returning empty list")
        return []

    # Parse response
    raw_items = _parse_extraction_response(raw_response)

    # Validate and normalise each item
    items: list[dict[str, Any]] = []
    for raw in raw_items:
        validated = _validate_item(raw)
        if validated:
            # Validate herbs against DB
            if validated["herbs_mentioned"]:
                validated["herbs_mentioned"] = await _validate_herbs(
                    validated["herbs_mentioned"], db
                )
            items.append(validated)

    logger.info("Extractor: extracted %d knowledge items from conversation", len(items))
    return items


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def _normalize_title(title: str) -> str:
    """Normalise a title for dedup comparison."""
    # Remove whitespace and common punctuation
    return re.sub(r"[\s,，。.!！?？、:：;；()（）\[\]【】]+", "", title).lower()


def _is_duplicate(
    title: str,
    existing_titles: list[str],
    similarity_threshold: float = DEDUP_TITLE_SIMILARITY,
) -> bool:
    """Check if a title is too similar to any existing title.

    Uses normalised exact match first, then falls back to substring check.
    """
    norm_new = _normalize_title(title)
    if not norm_new:
        return False

    for existing in existing_titles:
        norm_existing = _normalize_title(existing)
        if not norm_existing:
            continue

        # Exact match after normalisation
        if norm_new == norm_existing:
            return True

        # One is a substring of the other (handles "黄芪功效" vs "黄芪的功效")
        if norm_new in norm_existing or norm_existing in norm_new:
            return True

        # Character overlap ratio
        overlap = len(set(norm_new) & set(norm_existing))
        max_len = max(len(norm_new), len(norm_existing))
        if max_len > 0 and overlap / max_len >= similarity_threshold:
            return True

    return False


async def _get_existing_titles(db: DbAdapter, user_id: str) -> list[str]:
    """Get all existing knowledge entry titles for a user (for dedup)."""
    rows = await db.query(
        "SELECT title FROM knowledge_entries WHERE user_id = ? AND source_type = 'extractor'",
        (user_id,),
    )
    return [r["title"] for r in rows if r.get("title")]


# ---------------------------------------------------------------------------
# Public API: auto_extract_for_user
# ---------------------------------------------------------------------------

async def _save_knowledge_entry(
    db: DbAdapter,
    user_id: str,
    item: dict[str, Any],
    conversation_id: str | None = None,
) -> str:
    """Save a knowledge item to the knowledge_entries table.

    Returns the new entry ID.
    """
    entry_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    herbs_json = json.dumps(item.get("herbs_mentioned", []), ensure_ascii=False)

    await db.execute(
        """INSERT INTO knowledge_entries
           (id, user_id, entry_type, title, content, summary, tags,
            category_path, source_type, source_url, is_starred, created_at, updated_at)
           VALUES (?, ?, 'knowledge_card', ?, ?, NULL, ?, ?, 'extractor', ?, 0, ?, ?)""",
        (
            entry_id,
            user_id,
            item["title"],
            item["content"],
            herbs_json,
            item.get("category", DEFAULT_CATEGORY),
            conversation_id,
            now,
            now,
        ),
    )
    return entry_id


async def auto_extract_for_user(user_id: str, db: DbAdapter) -> int:
    """Run knowledge extraction on a user's recent conversations.

    Fetches recent conversations, extracts knowledge from each, deduplicates
    against existing entries, and saves new items. Returns the count of
    newly saved items.

    Rate limited: if the user has auto-extracted in the last hour, returns 0.
    """
    # --- Rate limit check ---
    one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=RATE_LIMIT_HOURS)).isoformat()
    recent_count = await db.query_one(
        """SELECT COUNT(*) as cnt FROM knowledge_entries
           WHERE user_id = ? AND source_type = 'extractor' AND created_at > ?""",
        (user_id, one_hour_ago),
    )
    if recent_count and recent_count["cnt"] > 0:
        logger.info(
            "Extractor: rate limit — user %s already auto-extracted in last hour", user_id
        )
        return 0

    # --- Get recent conversations ---
    conversations = await db.query(
        """SELECT id, messages FROM conversations
           WHERE user_id = ?
           ORDER BY updated_at DESC
           LIMIT ?""",
        (user_id, MAX_CONVERSATIONS_PER_RUN),
    )

    if not conversations:
        logger.info("Extractor: no conversations found for user %s", user_id)
        return 0

    # --- Get existing titles for dedup ---
    existing_titles = await _get_existing_titles(db, user_id)

    saved_count = 0
    for conv in conversations:
        conv_id = conv.get("id")
        messages_raw = conv.get("messages", "[]")

        # Parse messages JSON
        if isinstance(messages_raw, str):
            try:
                messages = json.loads(messages_raw)
            except (json.JSONDecodeError, TypeError):
                continue
        elif isinstance(messages_raw, list):
            messages = messages_raw
        else:
            continue

        if not messages:
            continue

        # Extract knowledge from this conversation
        items = await extract_knowledge(messages, db)

        for item in items:
            # Dedup check
            if _is_duplicate(item["title"], existing_titles):
                logger.debug("Extractor: skipping duplicate '%s'", item["title"])
                continue

            # Save
            await _save_knowledge_entry(db, user_id, item, conv_id)
            existing_titles.append(item["title"])
            saved_count += 1

    logger.info(
        "Extractor: auto-extracted %d items for user %s from %d conversations",
        saved_count, user_id, len(conversations),
    )
    return saved_count
