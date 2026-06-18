#!/usr/bin/env python3
"""Migrate per-table knowledge into unified graph_nodes / graph_edges.

Phase 2 of the architecture refactoring: port herbs / formulas / therapies
into ``graph_nodes`` with schema-driven ``properties`` (one row per entity,
keyed by the ``node_*.json`` schema definitions).

Design rules:

- **Additive only.** Original ``herbs`` / ``formulas`` / ``therapies`` tables
  are NOT deleted — existing routers keep working unchanged.
- **Idempotent.** Re-runs use ``find_or_create`` keyed on the schema's
  identity field (``名称``), so each entity is migrated exactly once.
- **Property keys are Chinese.** Matches the schema JSON: ``名称``, ``药性``,
  ``归经`` etc. (AGENTS.md §1.7 中文领域语言).
- **Edges are derived from composition.** Formula ``组成`` rows yield
  ``组成`` edges pointing at herb nodes. This intentionally mirrors the
  legacy ``kg_rebuild`` pipeline but stores the edge in ``graph_edges``
  through the unified repository, not direct SQL.

Usage:
    python backend/scripts/migrate_to_graph.py [--db PATH] [--dry-run]

Default DB path: data/homedoctor.db
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
from typing import Any

# Resolve imports whether invoked as `python scripts/migrate_to_graph.py`
# from inside backend/ or as `python backend/scripts/migrate_to_graph.py`
# from the project root.
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from app.database import SqliteAdapter, init_db  # noqa: E402
from app.routers.formulas import _parse_formula, extract_herb_names  # noqa: E402
from app.unified_repository import UnifiedRepository  # noqa: E402
from app.unified_schema import FileSchemaRegistry  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger("migrate_to_graph")

# Same splitter as kg_rebuild — keep symptom tokenisation identical so the
# graph stays consistent across the legacy and unified pipelines.
_SYM_SPLIT = re.compile(r"[，,。；;、\s]+")
_SYM_MAX_LEN = 12


# ---------------------------------------------------------------------------
# Per-type mappers — translate SQL rows → schema-shaped property dicts.
# ---------------------------------------------------------------------------


def herb_row_to_properties(row: dict[str, Any]) -> dict[str, Any]:
    """Translate a herbs-table row into node_herb-schema properties."""
    aliases_raw = row.get("aliases") or ""
    aliases = aliases_raw if isinstance(aliases_raw, str) else str(aliases_raw)
    return {
        "名称": row.get("name") or "",
        "别名": aliases,
        "功效分类": row.get("category") or "",
        "药性": row.get("nature") or "",
        "药味": row.get("flavor") or "",
        "归经": _split_csv(row.get("meridians")),
        "功效": row.get("efficacy") or "",
        "主治": row.get("indications") or "",
        "毒性": row.get("toxicity") or "",
        "最小剂量": _safe_float(row.get("dosage_min_g")),
        "最大剂量": _safe_float(row.get("dosage_max_g")),
        "禁忌": row.get("contraindications") or "",
    }


def formula_row_to_properties(row: dict[str, Any]) -> dict[str, Any]:
    """Translate a formulas-table row into node_formula-schema properties."""
    parsed = _parse_formula(row)
    composition_raw = parsed.get("composition", [])
    composition_names = [
        item.get("name", "") for item in composition_raw if isinstance(item, dict)
    ]
    return {
        "名称": parsed.get("name", "") or row.get("name") or "",
        "来源": parsed.get("source", "") or "",
        "分类": parsed.get("category", "") or "",
        # Store the structured composition list intact so ref/anchor-aware
        # downstream tooling can resolve it; ``extract_herb_names`` still
        # works because it reads this list via ``_parse_formula`` on the
        # original row.
        "组成": composition_names,
        "功效": parsed.get("efficacy", "") or "",
        "主治": parsed.get("indications", "") or "",
        "用法": "",
        "加减变化": "",
    }


def therapy_row_to_properties(row: dict[str, Any]) -> dict[str, Any]:
    """Translate a therapies-table row into node_therapy-schema properties."""
    return {
        "名称": row.get("name") or "",
        "分类": row.get("category") or "",
        "描述": row.get("description") or "",
        "适应症": row.get("indications") or "",
        "禁忌": row.get("contraindications") or "",
        "操作步骤": row.get("operation_steps") or "",
        "持续时间": row.get("duration") or "",
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _split_csv(value: Any) -> list[str]:
    """Split a comma/Chinese-comma separated string into a clean list."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if v]
    raw = str(value)
    parts = re.split(r"[，,、\s]+", raw)
    return [p.strip() for p in parts if p.strip()]


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


async def _migrate_herbs(
    repo: UnifiedRepository, db: SqliteAdapter, dry_run: bool
) -> tuple[int, int]:
    rows = await db.query(
        "SELECT id, name, aliases, nature, flavor, meridians, efficacy, indications, "
        "contraindications, dosage_min_g, dosage_max_g, toxicity, category "
        "FROM herbs ORDER BY name"
    )
    created = 0
    reused = 0
    for row in rows:
        name = row.get("name")
        if not name:
            continue
        existing = await repo.query_nodes_by_property("herb", "名称", name)
        if existing:
            reused += 1
            continue
        if dry_run:
            logger.info("[dry-run] would create herb node: %s", name)
            created += 1
            continue
        properties = herb_row_to_properties(row)
        await repo.create_node("herb", properties, label=name)
        created += 1
        if created % 50 == 0:
            logger.info("migrated %d herbs...", created)
    return created, reused


async def _migrate_formulas(
    repo: UnifiedRepository, db: SqliteAdapter, dry_run: bool
) -> tuple[int, int, dict[str, str]]:
    """Returns (created, reused, name_to_node_id) for downstream edge building."""
    rows = await db.query("SELECT * FROM formulas ORDER BY name")
    created = 0
    reused = 0
    name_to_node_id: dict[str, str] = {}
    for row in rows:
        parsed = _parse_formula(row)
        name = parsed.get("name") or row.get("name")
        if not name:
            continue
        existing = await repo.query_nodes_by_property("formula", "名称", name)
        if existing:
            name_to_node_id[name] = existing[0]["id"]
            reused += 1
            continue
        if dry_run:
            logger.info("[dry-run] would create formula node: %s", name)
            created += 1
            continue
        properties = formula_row_to_properties(row)
        node = await repo.create_node("formula", properties, label=name)
        name_to_node_id[name] = node["id"]
        created += 1
        if created % 25 == 0:
            logger.info("migrated %d formulas...", created)
    return created, reused, name_to_node_id


async def _migrate_therapies(
    repo: UnifiedRepository, db: SqliteAdapter, dry_run: bool
) -> tuple[int, int]:
    rows = await db.query(
        "SELECT id, name, category, description, indications, contraindications, "
        "operation_steps, duration FROM therapies ORDER BY name"
    )
    created = 0
    reused = 0
    for row in rows:
        name = row.get("name")
        if not name:
            continue
        existing = await repo.query_nodes_by_property("therapy", "名称", name)
        if existing:
            reused += 1
            continue
        if dry_run:
            logger.info("[dry-run] would create therapy node: %s", name)
            created += 1
            continue
        properties = therapy_row_to_properties(row)
        await repo.create_node("therapy", properties, label=name)
        created += 1
    return created, reused


async def _link_formula_herbs(
    repo: UnifiedRepository,
    db: SqliteAdapter,
    formula_name_to_id: dict[str, str],
    dry_run: bool,
) -> int:
    """Create 组成 edges from each formula node to each herb node it contains.

    Uses the herbs table to resolve herb names to their graph node ids (set
    during :func:`_migrate_herbs`). Idempotent because the edge creation
    reuses find_or_create semantics indirectly — if the formula→herb edge
    already exists we just skip it via a pre-check.
    """
    herb_rows = await db.query("SELECT name FROM herbs")
    herb_names = {r["name"] for r in herb_rows if r.get("name")}
    herb_name_to_id: dict[str, str] = {}
    for name in herb_names:
        nodes = await repo.query_nodes_by_property("herb", "名称", name)
        if nodes:
            herb_name_to_id[name] = nodes[0]["id"]

    formulas = await db.query("SELECT * FROM formulas")
    edge_count = 0
    for f in formulas:
        parsed = _parse_formula(f)
        formula_name = parsed.get("name") or f.get("name")
        if not formula_name:
            continue
        formula_id = formula_name_to_id.get(formula_name)
        if not formula_id:
            continue
        for herb_name in extract_herb_names(parsed):
            herb_id = herb_name_to_id.get(herb_name)
            if not herb_id:
                continue
            # Idempotent: check existing edge before inserting.
            existing = await repo.query_edges(
                source_id=formula_id, target_id=herb_id, edge_type="组成"
            )
            if existing:
                continue
            if dry_run:
                edge_count += 1
                continue
            await repo.create_edge(
                "组成",
                formula_id,
                herb_id,
                properties={"source_field": "组成"},
            )
            edge_count += 1
    return edge_count


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def run_migration(db_path: str, dry_run: bool) -> dict[str, Any]:
    """Run the full migration. Returns a stats dict for logging / assertions."""
    adapter = SqliteAdapter(db_path)
    await adapter.connect()
    try:
        # Ensure graph_nodes / graph_edges exist (idempotent — safe on prod).
        await init_db(adapter)

        registry = FileSchemaRegistry()
        registry.load()  # surface parse errors eagerly

        repo = UnifiedRepository(adapter, registry)

        logger.info("starting migration (db=%s, dry_run=%s)", db_path, dry_run)

        herbs_created, herbs_reused = await _migrate_herbs(repo, adapter, dry_run)
        formulas_created, formulas_reused, formula_name_to_id = await _migrate_formulas(
            repo, adapter, dry_run
        )
        therapies_created, therapies_reused = await _migrate_therapies(
            repo, adapter, dry_run
        )
        edges = await _link_formula_herbs(repo, adapter, formula_name_to_id, dry_run)

        stats = {
            "herbs_created": herbs_created,
            "herbs_reused": herbs_reused,
            "formulas_created": formulas_created,
            "formulas_reused": formulas_reused,
            "therapies_created": therapies_created,
            "therapies_reused": therapies_reused,
            "composition_edges": edges,
        }
        logger.info("migration complete: %s", json.dumps(stats, ensure_ascii=False))
        return stats
    finally:
        await adapter.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        default=os.environ.get("HOMEDOCTOR_DATABASE_URL", "data/homedoctor.db"),
        help="SQLite database path (default: data/homedoctor.db)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be migrated without writing anything",
    )
    args = parser.parse_args()

    stats = asyncio.run(run_migration(args.db, args.dry_run))

    # Pretty-print summary on stdout for ops scripts to grep.
    print(
        json.dumps(
            {
                "status": "dry_run" if args.dry_run else "ok",
                **stats,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
