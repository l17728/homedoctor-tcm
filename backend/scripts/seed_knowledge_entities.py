#!/usr/bin/env python3
"""Seed unified knowledge entities from existing herbs/formulas/therapies.

Mirrors the 300+ herbs, 82 formulas, and 32+ therapies into the unified
``knowledge_entities`` registry, then derives typed relationships:

- Formula CONTAINS herb       (from composition)
- Herb TREATS symptom         (from indications keywords)
- Therapy INDICATED_FOR       (from indications)
- Herb CONTRAINDICATED herb   (from safety_rules 十八反/十九畏)
- Herb INTERACTS_WITH drug    (from safety_rules 中西药交互)

This script makes the knowledge graph authoritative from
``entity_relationships`` (AGENTS.md §1.4 — 结构化是权威，知识图谱是派生).

Usage:
    python backend/scripts/seed_knowledge_entities.py [--db PATH]

Default DB path: data/homedoctor.db
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database import SqliteAdapter, init_db
from app.knowledge_entity import (
    create_relationship,
    get_or_create_entity,
    register_entity,
)
from app.routers.formulas import extract_herb_names, _parse_formula


_SYM_SPLIT = re.compile(r"[，,。；;、\s]+")
_SYM_MAX_LEN = 12


def _split_indications(text: str) -> list[str]:
    """Split a free-text indications field into discrete symptom tokens."""
    if not text:
        return []
    tokens: list[str] = []
    seen: set[str] = set()
    for raw in _SYM_SPLIT.split(text):
        token = raw.strip()
        if not token or len(token) > _SYM_MAX_LEN or token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    return tokens


async def seed_herbs(db) -> dict[str, str]:
    """Register all herbs. Returns ``{herb_name: entity_id}``."""
    rows = await db.query(
        """SELECT id, name, aliases, nature, flavor, efficacy, indications,
                  contraindications, category, toxicity, properties
           FROM herbs"""
    )
    name_to_entity: dict[str, str] = {}
    for h in rows:
        name = (h.get("name") or "").strip()
        if not name:
            continue
        keywords: list[str] = []
        for field in ("nature", "flavor", "meridians", "toxicity"):
            val = (h.get(field) or "").strip()
            if val:
                keywords.extend([p.strip() for p in re.split(r"[,，、;；]", val) if p.strip()])
        tags: list[str] = []
        cat = (h.get("category") or "").strip()
        if cat:
            tags.append(cat)
        summary = (h.get("efficacy") or "").strip()[:200]
        preview = (h.get("indications") or "").strip()[:200]
        properties = {
            k: v for k, v in h.items()
            if k in ("nature", "flavor", "toxicity") and v
        }
        entity_id = await register_entity(
            db,
            entity_type="herb",
            source_table="herbs",
            source_id=h["id"],
            title=name,
            summary=summary,
            keywords=keywords,
            tags=tags,
            category=cat or None,
            content_preview=preview,
            properties=properties,
            source_type="system",
        )
        name_to_entity[name] = entity_id
    return name_to_entity


async def seed_formulas(db, herb_name_to_id: dict[str, str]) -> tuple[dict[str, str], int]:
    """Register all formulas + create CONTAINS relationships.

    Returns ``(formula_name_to_entity_id, contains_count)``.
    """
    rows = await db.query("SELECT * FROM formulas")
    name_to_entity: dict[str, str] = {}
    contains_count = 0
    for row in rows:
        parsed = _parse_formula(row)
        name = (parsed.get("name") or "").strip()
        if not name:
            continue
        category = (parsed.get("category") or "").strip() or None
        efficacy = (parsed.get("efficacy") or "").strip()
        indications = (parsed.get("indications") or "").strip()
        composition = parsed.get("composition") if isinstance(parsed.get("composition"), list) else []
        keywords: list[str] = []
        for item in composition:
            if isinstance(item, dict):
                role = (item.get("role") or "").strip()
                if role:
                    keywords.append(f"君臣佐使:{role}")

        entity_id = await register_entity(
            db,
            entity_type="formula",
            source_table="formulas",
            source_id=parsed["id"],
            title=name,
            summary=efficacy[:200],
            keywords=keywords,
            tags=[category] if category else [],
            category=category,
            content_preview=indications[:200],
            properties={"source": parsed.get("source", ""), "composition_count": len(composition)},
            source_type="system",
        )
        name_to_entity[name] = entity_id

        for herb_name in extract_herb_names(parsed):
            herb_entity_id = herb_name_to_id.get(herb_name)
            if not herb_entity_id:
                continue
            await create_relationship(
                db, entity_id, herb_entity_id, "contains",
                properties={"role": next(
                    (item.get("role", "") for item in composition
                     if isinstance(item, dict) and item.get("name") == herb_name),
                    "",
                )},
            )
            contains_count += 1
    return name_to_entity, contains_count


async def seed_therapies(db) -> tuple[dict[str, str], int]:
    """Register all therapies. Returns ``(therapy_name_to_entity_id, count)``."""
    rows = await db.query(
        """SELECT id, name, category, risk_level, description, indications,
                  contraindications, properties
           FROM therapies"""
    )
    name_to_entity: dict[str, str] = {}
    for t in rows:
        name = (t.get("name") or "").strip()
        if not name:
            continue
        category = (t.get("category") or "").strip() or None
        description = (t.get("description") or "").strip()
        indications = (t.get("indications") or "").strip()
        entity_id = await register_entity(
            db,
            entity_type="therapy",
            source_table="therapies",
            source_id=t["id"],
            title=name,
            summary=description[:200],
            keywords=[t.get("risk_level", "")] if t.get("risk_level") else [],
            tags=[category] if category else [],
            category=category,
            content_preview=indications[:200],
            properties={"risk_level": t.get("risk_level", "")},
            source_type="system",
        )
        name_to_entity[name] = entity_id
    return name_to_entity, len(name_to_entity)


async def create_herb_treats_symptom_relationships(
    db, herb_name_to_id: dict[str, str]
) -> int:
    """Herb TREATS symptom — derived from herb.indications text tokens."""
    rows = await db.query("SELECT id, name, indications FROM herbs")
    count = 0
    for h in rows:
        herb_entity_id = herb_name_to_id.get((h.get("name") or "").strip())
        if not herb_entity_id:
            continue
        for token in _split_indications(h.get("indications") or ""):
            symptom_entity_id = await get_or_create_entity(
                db,
                entity_type="symptom",
                source_table="symptom",
                source_id=f"symptom:{token}",
                title=token,
            )
            await create_relationship(db, herb_entity_id, symptom_entity_id, "treats")
            count += 1
    return count


async def create_therapy_indicated_for_relationships(
    db, therapy_name_to_id: dict[str, str]
) -> int:
    """Therapy INDICATED_FOR condition — derived from therapy.indications."""
    rows = await db.query("SELECT id, name, indications FROM therapies")
    count = 0
    for t in rows:
        therapy_entity_id = therapy_name_to_id.get((t.get("name") or "").strip())
        if not therapy_entity_id:
            continue
        for token in _split_indications(t.get("indications") or ""):
            condition_entity_id = await get_or_create_entity(
                db,
                entity_type="symptom",
                source_table="symptom",
                source_id=f"symptom:{token}",
                title=token,
            )
            await create_relationship(db, therapy_entity_id, condition_entity_id, "indicated_for")
            count += 1
    return count


async def create_contraindicated_relationships(
    db, herb_name_to_id: dict[str, str]
) -> int:
    """Herb CONTRAINDICATED herb — from safety_rules 十八反/十九畏."""
    rules = await db.query(
        """SELECT drug_a, drug_b, severity, mechanism, rule_type
           FROM safety_rules
           WHERE rule_type IN ('十八反', '十九畏') AND drug_b IS NOT NULL"""
    )
    count = 0
    for r in rules:
        a_id = herb_name_to_id.get((r.get("drug_a") or "").strip())
        b_id = herb_name_to_id.get((r.get("drug_b") or "").strip())
        if not a_id or not b_id:
            continue
        await create_relationship(
            db, a_id, b_id, "contraindicated",
            properties={
                "severity": r.get("severity", ""),
                "mechanism": r.get("mechanism", ""),
                "rule_type": r.get("rule_type", ""),
            },
        )
        count += 1
    return count


async def create_interacts_with_relationships(
    db, herb_name_to_id: dict[str, str]
) -> int:
    """Herb INTERACTS_WITH drug — from safety_rules 中西药交互."""
    rules = await db.query(
        """SELECT drug_a, drug_b, severity, mechanism
           FROM safety_rules
           WHERE rule_type = '中西药交互' AND drug_b IS NOT NULL"""
    )
    count = 0
    for r in rules:
        drug_name = (r.get("drug_a") or "").strip()
        herb_name = (r.get("drug_b") or "").strip()
        herb_entity_id = herb_name_to_id.get(herb_name)
        if not herb_entity_id:
            continue
        drug_entity_id = await get_or_create_entity(
            db,
            entity_type="medicine",
            source_table="medicine",
            source_id=f"medicine:{drug_name}",
            title=drug_name,
        )
        await create_relationship(
            db, herb_entity_id, drug_entity_id, "interacts_with",
            properties={
                "severity": r.get("severity", ""),
                "mechanism": r.get("mechanism", ""),
            },
        )
        count += 1
    return count


async def seed(db_path: str) -> dict[str, Any]:
    """Run the full seed pipeline. Returns a stats dict."""
    db_file = os.path.dirname(db_path)
    if db_file:
        os.makedirs(db_file, exist_ok=True)

    adapter = SqliteAdapter(db_path)
    await adapter.connect()
    await init_db(adapter)

    try:
        herb_name_to_id = await seed_herbs(adapter)
        formula_name_to_id, contains_count = await seed_formulas(adapter, herb_name_to_id)
        therapy_name_to_id, therapy_count = await seed_therapies(adapter)
        treats_count = await create_herb_treats_symptom_relationships(adapter, herb_name_to_id)
        indicated_count = await create_therapy_indicated_for_relationships(adapter, therapy_name_to_id)
        contraindicated_count = await create_contraindicated_relationships(adapter, herb_name_to_id)
        interacts_count = await create_interacts_with_relationships(adapter, herb_name_to_id)

        entity_count_row = await adapter.query_one("SELECT COUNT(*) AS cnt FROM knowledge_entities")
        rel_count_row = await adapter.query_one("SELECT COUNT(*) AS cnt FROM entity_relationships")

        stats = {
            "herbs_registered": len(herb_name_to_id),
            "formulas_registered": len(formula_name_to_id),
            "therapies_registered": therapy_count,
            "contains_relationships": contains_count,
            "treats_relationships": treats_count,
            "indicated_for_relationships": indicated_count,
            "contraindicated_relationships": contraindicated_count,
            "interacts_with_relationships": interacts_count,
            "total_entities": entity_count_row["cnt"] if entity_count_row else 0,
            "total_relationships": rel_count_row["cnt"] if rel_count_row else 0,
        }
    finally:
        await adapter.close()

    print("=== 知识实体种子完成 ===")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    return stats


if __name__ == "__main__":
    db_path = os.environ.get("HOMEDOCTOR_DATABASE_URL", "data/homedoctor.db")
    if len(sys.argv) > 1:
        if sys.argv[1] in ("--db", "-d"):
            db_path = sys.argv[2]
        else:
            db_path = sys.argv[1]
    asyncio.run(seed(db_path))
