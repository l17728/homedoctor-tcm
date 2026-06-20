"""Sync herbs/formulas full data into knowledge_entities.properties (Phase 2 migration).

For each knowledge_entity with source_table='herbs' or 'formulas', pulls ALL
columns from the source table and merges them into the entity's properties JSON.

This makes knowledge_entities the single source of truth with complete data.
Idempotent — safe to run multiple times.

Usage:
    cd backend && python3 scripts/sync_entities_to_unified.py
"""

import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SqliteAdapter, set_db, init_db


HERB_COLUMNS = [
    "aliases", "nature", "flavor", "meridians", "efficacy", "indications",
    "contraindications", "dosage_min_g", "dosage_max_g", "toxicity",
    "category", "processing_method", "origin", "source_ref",
]

FORMULA_COLUMNS = [
    "source", "category", "composition", "efficacy", "indications",
    "modifications", "modifications_structured", "derived_from_id",
]


async def sync_herbs(db) -> int:
    rows = await db.query(
        "SELECT ke.id AS entity_id, ke.source_id, ke.properties AS entity_props, "
        "h.* FROM knowledge_entities ke "
        "JOIN herbs h ON h.id = ke.source_id "
        "WHERE ke.source_table = 'herbs' AND ke.entity_type = 'herb'"
    )
    updated = 0
    for row in rows:
        entity_props = {}
        if row.get("entity_props"):
            try:
                entity_props = json.loads(row["entity_props"])
            except (json.JSONDecodeError, TypeError):
                pass

        for col in HERB_COLUMNS:
            val = row.get(col)
            if val is not None and val != "":
                if isinstance(val, float) and val.is_integer():
                    val = int(val)
                entity_props[col] = val

        herb_props = {}
        if row.get("properties"):
            try:
                herb_props = json.loads(row.get("properties"))
            except (json.JSONDecodeError, TypeError):
                pass
        for k, v in herb_props.items():
            if k not in entity_props:
                entity_props[k] = v

        await db.execute(
            "UPDATE knowledge_entities SET properties = ?, summary = ?, "
            "content_preview = ?, category = ?, updated_at = datetime('now') "
            "WHERE id = ?",
            (
                json.dumps(entity_props, ensure_ascii=False),
                row.get("efficacy") or row.get("summary") or "",
                row.get("indications") or row.get("content_preview") or "",
                row.get("category") or row.get("entity_category"),
                row["entity_id"],
            ),
        )
        updated += 1
    return updated


async def sync_formulas(db) -> int:
    rows = await db.query(
        "SELECT ke.id AS entity_id, ke.source_id, ke.properties AS entity_props, "
        "f.* FROM knowledge_entities ke "
        "JOIN formulas f ON f.id = ke.source_id "
        "WHERE ke.source_table = 'formulas' AND ke.entity_type = 'formula'"
    )
    updated = 0
    for row in rows:
        entity_props = {}
        if row.get("entity_props"):
            try:
                entity_props = json.loads(row["entity_props"])
            except (json.JSONDecodeError, TypeError):
                pass

        for col in FORMULA_COLUMNS:
            val = row.get(col)
            if val is not None and val != "":
                entity_props[col] = val

        formula_props = {}
        if row.get("properties"):
            try:
                formula_props = json.loads(row.get("properties"))
            except (json.JSONDecodeError, TypeError):
                pass
        for k, v in formula_props.items():
            if k not in entity_props:
                entity_props[k] = v

        await db.execute(
            "UPDATE knowledge_entities SET properties = ?, summary = ?, "
            "content_preview = ?, category = ?, updated_at = datetime('now') "
            "WHERE id = ?",
            (
                json.dumps(entity_props, ensure_ascii=False),
                row.get("efficacy") or "",
                row.get("indications") or "",
                row.get("category") or "",
                row["entity_id"],
            ),
        )
        updated += 1
    return updated


async def main():
    db_path = os.environ.get("HOMEDOCTOR_DATABASE_URL", "data/homedoctor.db")
    adapter = SqliteAdapter(db_path)
    await adapter.connect()
    set_db(adapter)
    await init_db(adapter)

    print("Syncing herbs → knowledge_entities...")
    herbs_synced = await sync_herbs(adapter)
    print(f"  {herbs_synced} herbs enriched")

    print("Syncing formulas → knowledge_entities...")
    formulas_synced = await sync_formulas(adapter)
    print(f"  {formulas_synced} formulas enriched")

    total = herbs_synced + formulas_synced
    print(f"\nDone: {total} entities synced to unified model.")

    sample = await adapter.query(
        "SELECT title, properties FROM knowledge_entities "
        "WHERE entity_type = 'herb' AND title = '黄芪'"
    )
    if sample:
        props = json.loads(sample[0]["properties"]) if isinstance(sample[0]["properties"], str) else sample[0]["properties"]
        print(f"\nSample (黄芪) properties keys: {list(props.keys())}")

    await adapter.close()


if __name__ == "__main__":
    asyncio.run(main())
