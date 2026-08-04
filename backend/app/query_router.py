"""Intent-based query routing for the RAG search pipeline.

Classifies a user query into one of four intents that determine which search
strategies (BM25 / semantic / both) the pipeline runs:

- ``BROWSE`` — hierarchy/listing queries ("有哪些", "分类", "列表") → BM25.
- ``EXACT`` — a known entity name + property word → BM25 only.
- ``CONCEPT`` — how/why/how-to questions ("怎么", "为什么", "如何") → semantic.
- ``COMPLEX`` — multiple entities or relation words → BM25 + semantic (RRF).
- Default → ``COMPLEX`` (safest, runs both strategies).

Design (AGENTS.md §1.7 中文领域语言): intent keywords are Chinese.
"""

from __future__ import annotations


import logging

logger = logging.getLogger(__name__)
import re

BROWSE = "BROWSE"
EXACT = "EXACT"
CONCEPT = "CONCEPT"
COMPLEX = "COMPLEX"

_BROWSE_KEYWORDS = ("有哪些", "分类", "列表", "种类", "哪些", "全部", "罗列", "列举", "列出")
_CONCEPT_KEYWORDS = ("怎么", "为什么", "如何", "怎样", "为何", "原理", "机制", "区别", "对比")
_COMPLEX_RELATION_KEYWORDS = ("配伍", "搭配", "交互", "相互作用", "合用", "同用", "禁忌", "关系", "组合")
_PROPERTY_WORDS = ("功效", "作用", "性味", "归经", "主治", "用法", "用量", "功效与作用", "副作用", "禁忌", "别名", "产地")

# Multi-entity heuristic: separators between distinct names.
_MULTI_ENTITY_HINTS = ("和", "与", "、", "及", "跟", "加")


def classify_query(query: str) -> str:
    """Classify ``query`` into an intent string.

    Priority (first match wins):
      1. CONCEPT — contains a concept keyword (怎么/为什么/如何…).
      2. BROWSE — contains a browsing keyword (有哪些/分类/列表…).
      3. EXACT — looks like ``<entity> + <property>`` with no relation word.
      4. COMPLEX — multiple entities or a relation word (default).
    """
    if not query or not query.strip():
        return COMPLEX

    q = query.strip()

    if any(kw in q for kw in _CONCEPT_KEYWORDS):
        return CONCEPT

    if any(kw in q for kw in _BROWSE_KEYWORDS):
        return BROWSE

    has_relation = any(kw in q for kw in _COMPLEX_RELATION_KEYWORDS)
    multi_entity = any(sep in q for sep in _MULTI_ENTITY_HINTS)
    if has_relation or multi_entity:
        return COMPLEX

    has_property = any(kw in q for kw in _PROPERTY_WORDS)
    if has_property:
        return EXACT

    return COMPLEX


def strategies_for_intent(intent: str) -> list[str]:
    """Return the list of search strategies to run for a given intent."""
    if intent == BROWSE:
        return ["bm25"]
    if intent == EXACT:
        return ["bm25"]
    if intent == CONCEPT:
        return ["semantic"]
    return ["bm25", "semantic"]  # COMPLEX / default
