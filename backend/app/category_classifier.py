"""Dynamic category classifier — agent decides if new knowledge needs a new category.

When a new entity is imported, this module:
1. Queries all existing categories for the entity type
2. Asks LLM: "does this fit an existing category, or is it a new one?"
3. Returns the best category assignment

Example:
  Input: "李少波真气运行法" (entity_type=health_practice)
  Existing categories: 静功/动功/内家拳法/导引功法/吐纳功法/道家功法/古代导引/内功
  LLM decision: "气功功法" (NEW — it's a modern systematic qigong method,
                distinct from traditional categories)
  Result: category="气功功法", is_new_category=True
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.database import DbAdapter

logger = logging.getLogger(__name__)


async def classify_category(
    db: DbAdapter,
    title: str,
    summary: str,
    entity_type: str,
    content: str = "",
) -> dict[str, Any]:
    """Determine the best category for a new entity.

    Returns: {category, is_new, existing_categories, reason}
    """
    existing_cats = await _get_existing_categories(db, entity_type)

    if not existing_cats:
        return {
            "category": _default_category(entity_type),
            "is_new": False,
            "reason": "无已有分类，使用默认",
        }

    from app.llm import chat_completion, has_api_key

    if not has_api_key():
        cat = _guess_category(title, summary, existing_cats)
        return {
            "category": cat,
            "is_new": cat not in existing_cats,
            "reason": "LLM不可用，启发式匹配",
        }

    prompt = f"""你是中医药知识分类专家。请为以下知识实体确定最合适的分类。

实体标题：{title}
实体摘要：{summary}
实体类型：{entity_type}
内容摘要：{content[:500]}

已有分类列表：{", ".join(existing_cats)}

请判断：
1. 这个实体是否属于已有分类中的某一个？如果是，选择最匹配的。
2. 如果不属于任何已有分类，请创建一个新分类名（中文，简洁，2-6字）。

注意：
- 新分类应该是已有分类的同级或子级，不要过于具体
- 优先匹配已有分类（避免创建过多碎片化分类）
- 只有确实不属于任何已有分类时才创建新分类

返回JSON：{{"category": "分类名", "is_new": true/false, "reason": "选择理由"}}"""

    response = await chat_completion([
        {"role": "user", "content": prompt},
    ])

    import re
    try:
        from app.json_extractor import extract_json
        parsed = extract_json(response)
        if parsed:
            result = json.loads(match.group())
            cat = result.get("category", "").strip()
            if cat:
                return {
                    "category": cat,
                    "is_new": result.get("is_new", cat not in existing_cats),
                    "existing_categories": existing_cats,
                    "reason": result.get("reason", ""),
                }
    except (json.JSONDecodeError, AttributeError):
        pass

    cat = _guess_category(title, summary, existing_cats)
    return {
        "category": cat,
        "is_new": cat not in existing_cats,
        "reason": "LLM解析失败，启发式匹配",
    }


async def _get_existing_categories(db: DbAdapter, entity_type: str) -> list[str]:
    """Get all existing categories for an entity type."""
    rows = await db.query(
        """SELECT DISTINCT category FROM knowledge_entities
            WHERE entity_type = ? AND status = 'active'
              AND category IS NOT NULL AND category != ''""",
        (entity_type,),
    )
    return [r["category"] for r in rows if r.get("category")]


def _guess_category(title: str, summary: str, existing: list[str]) -> str:
    """Heuristic category matching when LLM is unavailable."""
    text = f"{title} {summary}"

    keyword_map = {
        "静功": ["打坐", "静坐", "冥想", "禅修", "静功"],
        "动功": ["动功", "体操", "运动", "活跃"],
        "导引功法": ["导引", "八段锦", "五禽戏", "易筋经", "十二段锦"],
        "内家拳法": ["太极", "拳", "内家"],
        "吐纳功法": ["吐纳", "呼吸", "六字诀", "气"],
        "道家功法": ["道家", "道教", "内丹", "周天", "金刚功", "长寿功"],
        "补虚药": ["补气", "补血", "补阴", "补阳", "补虚"],
        "清热药": ["清热", "解毒", "凉血"],
        "解表药": ["解表", "发汗", "疏散"],
    }

    for cat, keywords in keyword_map.items():
        if cat in existing:
            for kw in keywords:
                if kw in text:
                    return cat

    if any(kw in text for kw in ["气功", "真气", "运行法"]):
        return "气功功法"

    return existing[0] if existing else "其他"


def _default_category(entity_type: str) -> str:
    defaults = {
        "herb": "补虚药",
        "formula": "补益剂",
        "therapy": "针刺",
        "symptom": "气虚",
        "acupoint": "足阳明胃经",
        "meridian": "正经",
        "health_practice": "静功",
        "practice_school": "门派",
        "article": "文章",
    }
    return defaults.get(entity_type, "其他")
