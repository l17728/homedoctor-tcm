"""Knowledge graph derived edge builder — port of /fighting kg-rebuild.ts.

清除所有派生边，从权威结构化数据（herbs/formulas/therapies/safety_rules）重建。
图谱损坏 → 删了重建，不可修复（spec §1.4）。

Enhanced with ref-edge sync engine (port of /fighting refs.ts + anchors.ts):
  - 组成/主治/配伍禁忌/中西药交互: structured-domain edges (legacy)
  - 分配/关联: schema-driven ref/anchor edges (new)
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.database import DbAdapter
from app.ref_sync import sync_ref_edges, sync_anchor_edges
from app.routers.formulas import _parse_formula, extract_herb_names
from app.schema.registry import FileSchemaRegistry, schema_registry

DERIVED_EDGE_TYPES = ("组成", "主治", "配伍禁忌", "中西药交互", "分配", "关联")

_SYM_SPLIT = re.compile(r"[，,。；;、\s]+")
_SYM_MAX_LEN = 12


def _symptom_id(text: str) -> str:
    return "symptom:" + text


def _safe_props(extra: dict[str, Any]) -> str:
    return json.dumps(extra, ensure_ascii=False)


async def rebuild_all_edges(
    db: DbAdapter,
    registry: FileSchemaRegistry | None = None,
) -> dict[str, int]:
    """Wipe all derived edges + nodes, rebuild from structured data.

    Returns per-type edge counts including ref/anchor edges.
    Backward compatible: registry defaults to the global singleton.
    """
    if registry is None:
        registry = schema_registry

    for et in DERIVED_EDGE_TYPES:
        await db.execute("DELETE FROM graph_edges WHERE edge_type = ?", (et,))
    await db.execute("DELETE FROM graph_nodes")

    counts: dict[str, int] = {
        "组成": 0,
        "主治": 0,
        "配伍禁忌": 0,
        "中西药交互": 0,
        "分配": 0,
        "关联": 0,
    }

    # --- Build herb nodes with FULL properties (for ref/anchor sync) ---
    herb_name_to_id: dict[str, str] = {}
    herbs = await db.query(
        "SELECT id, name, aliases, nature, flavor, meridians, efficacy, "
        "indications, contraindications, dosage_min_g, dosage_max_g, toxicity, "
        "category, properties FROM herbs"
    )
    for h in herbs:
        props: dict[str, Any] = {
            "name": h["name"],
            "aliases": h.get("aliases") or "",
            "nature": h.get("nature") or "",
            "flavor": h.get("flavor") or "",
            "meridians": h.get("meridians") or "",
            "category": h.get("category") or "",
            "efficacy": h.get("efficacy") or "",
            "indications": h.get("indications") or "",
        }
        search_text = " ".join(str(v or "") for v in props.values())
        await db.execute(
            "INSERT OR IGNORE INTO graph_nodes (id, node_type, label, properties, search_text) "
            "VALUES (?, 'herb', ?, ?, ?)",
            (h["id"], h["name"], _safe_props(props), search_text),
        )
        herb_name_to_id[h["name"]] = h["id"]

    # --- Build formula nodes ---
    formulas = await db.query("SELECT * FROM formulas")
    for f in formulas:
        parsed = _parse_formula(f)
        fprops: dict[str, Any] = {
            "name": parsed.get("name", parsed["id"]),
            "source": parsed.get("source") or "",
            "category": parsed.get("category") or "",
            "efficacy": parsed.get("efficacy") or "",
            "indications": parsed.get("indications") or "",
        }
        search_text = " ".join(str(v or "") for v in fprops.values())
        await db.execute(
            "INSERT OR IGNORE INTO graph_nodes (id, node_type, label, properties, search_text) "
            "VALUES (?, 'formula', ?, ?, ?)",
            (parsed["id"], parsed.get("name", parsed["id"]), _safe_props(fprops), search_text),
        )
        for herb_name in extract_herb_names(parsed):
            herb_id = herb_name_to_id.get(herb_name)
            if not herb_id:
                continue
            eid = f"e:组成:{parsed['id']}->{herb_id}"
            await db.execute(
                "INSERT OR IGNORE INTO graph_edges (id, edge_type, source_id, target_id, properties) "
                "VALUES (?, '组成', ?, ?, '{}')",
                (eid, parsed["id"], herb_id),
            )
            counts["组成"] += 1

    # --- Build therapy nodes ---
    therapies = await db.query(
        "SELECT id, name, category, description, indications FROM therapies"
    )
    for t in therapies:
        tprops: dict[str, Any] = {
            "name": t["name"],
            "category": t.get("category") or "",
        }
        search_text = " ".join(
            str(t.get(k) or "") for k in ("name", "category", "description", "indications")
        )
        await db.execute(
            "INSERT OR IGNORE INTO graph_nodes (id, node_type, label, properties, search_text) "
            "VALUES (?, 'therapy', ?, ?, ?)",
            (t["id"], t["name"], _safe_props(tprops), search_text),
        )

    # --- 主治 edges (herb → symptom) ---
    for h in herbs:
        indications = h.get("indications") or ""
        seen_syms: set[str] = set()
        for token in _SYM_SPLIT.split(indications):
            token = token.strip()
            if not token or len(token) > _SYM_MAX_LEN or token in seen_syms:
                continue
            seen_syms.add(token)
            sym_id = _symptom_id(token)
            await db.execute(
                "INSERT OR IGNORE INTO graph_nodes (id, node_type, label, properties, search_text) "
                "VALUES (?, 'symptom', ?, '{}', ?)",
                (sym_id, token, token),
            )
            eid = f"e:主治:{h['id']}->{sym_id}"
            await db.execute(
                "INSERT OR IGNORE INTO graph_edges (id, edge_type, source_id, target_id, properties) "
                "VALUES (?, '主治', ?, ?, '{}')",
                (eid, h["id"], sym_id),
            )
            counts["主治"] += 1

    # --- 配伍禁忌 edges (十八反/十九畏) ---
    rules = await db.query(
        "SELECT rule_type, drug_a, drug_b, severity, mechanism FROM safety_rules "
        "WHERE rule_type IN ('十八反','十九畏') AND drug_b IS NOT NULL"
    )
    for r in rules:
        a_id = herb_name_to_id.get(r["drug_a"])
        b_id = herb_name_to_id.get(r["drug_b"])
        if not a_id or not b_id:
            continue
        props = _safe_props({"severity": r["severity"], "mechanism": r["mechanism"] or ""})
        eid = f"e:配伍禁忌:{a_id}->{b_id}"
        await db.execute(
            "INSERT OR IGNORE INTO graph_edges (id, edge_type, source_id, target_id, properties) "
            "VALUES (?, '配伍禁忌', ?, ?, ?)",
            (eid, a_id, b_id, props),
        )
        counts["配伍禁忌"] += 1

    # --- 中西药交互 edges ---
    medicine_name_to_id: dict[str, str] = {}
    inter_rules = await db.query(
        "SELECT rule_type, drug_a, drug_b, severity, mechanism FROM safety_rules "
        "WHERE rule_type = '中西药交互' AND drug_b IS NOT NULL"
    )
    for r in inter_rules:
        med_name = r["drug_a"]
        med_id = medicine_name_to_id.get(med_name)
        if not med_id:
            med_id = "medicine:" + med_name
            medicine_name_to_id[med_name] = med_id
            await db.execute(
                "INSERT OR IGNORE INTO graph_nodes (id, node_type, label, properties, search_text) "
                "VALUES (?, 'medicine', ?, '{}', ?)",
                (med_id, med_name, med_name),
            )
        herb_id = herb_name_to_id.get(r["drug_b"])
        if not herb_id:
            continue
        props = _safe_props({"severity": r["severity"], "mechanism": r["mechanism"] or ""})
        eid = f"e:中西药交互:{herb_id}->{med_id}"
        await db.execute(
            "INSERT OR IGNORE INTO graph_edges (id, edge_type, source_id, target_id, properties) "
            "VALUES (?, '中西药交互', ?, ?, ?)",
            (eid, herb_id, med_id, props),
        )
        counts["中西药交互"] += 1

    # --- 分配/关联 edges (ref/anchor sync from schema) ---
    all_nodes = await db.query(
        "SELECT * FROM graph_nodes WHERE node_type != 'concept'"
    )
    for node in all_nodes:
        node_props = node.get("properties")
        if isinstance(node_props, str):
            try:
                node["properties"] = json.loads(node_props or "{}")
            except (json.JSONDecodeError, TypeError):
                node["properties"] = {}
        counts["分配"] += await sync_ref_edges(db, registry, node)
        counts["关联"] += await sync_anchor_edges(db, registry, node)

    return counts
