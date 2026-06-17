"""Knowledge graph derived edge builder — port of /fighting kg-rebuild.ts.

清除所有派生边，从权威结构化数据（herbs/formulas/therapies/safety_rules）重建。
图谱损坏 → 删了重建，不可修复（spec §1.4）。
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.database import DbAdapter
from app.routers.formulas import _parse_formula, extract_herb_names

DERIVED_EDGE_TYPES = ("组成", "主治", "配伍禁忌", "中西药交互")

_SYM_SPLIT = re.compile(r"[，,。；;、\s]+")
_SYM_MAX_LEN = 12


def _symptom_id(text: str) -> str:
    return "symptom:" + text


def _safe_props(extra: dict[str, Any]) -> str:
    return json.dumps(extra, ensure_ascii=False)


async def rebuild_all_edges(db: DbAdapter) -> dict[str, int]:
    """Wipe all derived edges + nodes, rebuild from structured data.

    Returns per-type edge counts: {组成: N, 主治: N, 配伍禁忌: N, 中西药交互: N}.
    """
    for et in DERIVED_EDGE_TYPES:
        await db.execute("DELETE FROM graph_edges WHERE edge_type = ?", (et,))
    await db.execute("DELETE FROM graph_nodes")

    counts = {"组成": 0, "主治": 0, "配伍禁忌": 0, "中西药交互": 0}

    herb_name_to_id: dict[str, str] = {}
    herbs = await db.query(
        "SELECT id, name, aliases, nature, flavor, efficacy, indications, category FROM herbs"
    )
    for h in herbs:
        search_text = " ".join(
            str(h.get(k) or "")
            for k in ("name", "aliases", "efficacy", "indications", "category")
        )
        await db.execute(
            "INSERT OR IGNORE INTO graph_nodes (id, node_type, label, properties, search_text) "
            "VALUES (?, 'herb', ?, '{}', ?)",
            (h["id"], h["name"], search_text),
        )
        herb_name_to_id[h["name"]] = h["id"]

    formulas = await db.query("SELECT * FROM formulas")
    for f in formulas:
        parsed = _parse_formula(f)
        search_text = " ".join(
            str(parsed.get(k) or "")
            for k in ("name", "source", "category", "efficacy", "indications")
        )
        await db.execute(
            "INSERT OR IGNORE INTO graph_nodes (id, node_type, label, properties, search_text) "
            "VALUES (?, 'formula', ?, '{}', ?)",
            (parsed["id"], parsed.get("name", parsed["id"]), search_text),
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

    therapies = await db.query(
        "SELECT id, name, category, description, indications FROM therapies"
    )
    for t in therapies:
        search_text = " ".join(
            str(t.get(k) or "") for k in ("name", "category", "description", "indications")
        )
        await db.execute(
            "INSERT OR IGNORE INTO graph_nodes (id, node_type, label, properties, search_text) "
            "VALUES (?, 'therapy', ?, '{}', ?)",
            (t["id"], t["name"], search_text),
        )

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

    return counts
