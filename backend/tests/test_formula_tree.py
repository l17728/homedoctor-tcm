"""Tests for formula derivation tree endpoint and modifications data.

Covers spec §4.2 US-4: 加减变化 + 演化树.
  - GET /api/formulas/{id}/tree: parent, ancestors chain, children, has_tree
  - modifications_structured data in formula detail
"""

from __future__ import annotations

import json

import pytest
from httpx import AsyncClient

from app.database import DbAdapter


# ---------------------------------------------------------------------------
# Test data: formula derivation chain
# formula-001 四君子汤 → formula-003 异功散 → formula-004 六君子汤 → formula-005 香砂六君子汤
# ---------------------------------------------------------------------------

TREE_FORMULA_001 = "formula-001"  # 四君子汤 (already in seed_test_data)
TREE_FORMULA_002 = "formula-002"  # 四物汤   (already in seed_test_data)

DERIVED_CHAIN_IDS = {
    "formula-003": ("异功散", "formula-001"),
    "formula-004": ("六君子汤", "formula-003"),
    "formula-005": ("香砂六君子汤", "formula-004"),
    "formula-006": ("八珍汤", "formula-002"),
}

SAMPLE_MODIFICATIONS = {
    TREE_FORMULA_001: [
        {"symptom": "气虚兼气滞", "add": ["陈皮"], "remove": [], "note": "→ 异功散"},
        {"symptom": "气虚兼痰湿", "add": ["陈皮", "半夏"], "remove": [], "note": "→ 六君子汤"},
        {"symptom": "气虚兼气滞痰湿", "add": ["陈皮", "半夏", "木香", "砂仁"], "remove": [], "note": "→ 香砂六君子汤"},
        {"symptom": "脾胃虚寒", "add": ["干姜"], "remove": [], "note": "温中散寒"},
    ],
    TREE_FORMULA_002: [
        {"symptom": "兼气虚", "add": ["人参", "黄芪"], "remove": [], "note": "→ 圣愈汤"},
        {"symptom": "兼血瘀", "add": ["桃仁", "红花"], "remove": [], "note": "→ 桃红四物汤"},
        {"symptom": "血虚有热", "add": ["黄芩", "牡丹皮"], "remove": ["熟地黄"], "note": "清热凉血"},
    ],
}


async def _seed_tree_data(db: DbAdapter) -> None:
    for fid, (name, parent_id) in DERIVED_CHAIN_IDS.items():
        await db.execute(
            """INSERT OR REPLACE INTO formulas
               (id, name, source, category, composition, efficacy, indications,
                modifications, modifications_structured, derived_from_id, properties)
               VALUES (?, ?, '《测试》', '补益剂', '[]', '', '', '[]', '[]', ?, '{}')""",
            (fid, name, parent_id),
        )

    for fid, mods in SAMPLE_MODIFICATIONS.items():
        await db.execute(
            "UPDATE formulas SET modifications_structured = ? WHERE id = ?",
            (json.dumps(mods, ensure_ascii=False), fid),
        )

    await db.execute("COMMIT")


# ---------------------------------------------------------------------------
# Tree endpoint tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tree_returns_formula_info(client: AsyncClient, db: DbAdapter):
    await _seed_tree_data(db)
    response = await client.get(f"/api/formulas/{TREE_FORMULA_001}/tree")
    assert response.status_code == 200
    data = response.json()
    assert data["formula"]["id"] == TREE_FORMULA_001
    assert data["formula"]["name"] == "四君子汤"
    assert "category" in data["formula"]
    assert "source" in data["formula"]


@pytest.mark.asyncio
async def test_tree_has_children(client: AsyncClient, db: DbAdapter):
    await _seed_tree_data(db)
    response = await client.get(f"/api/formulas/{TREE_FORMULA_001}/tree")
    data = response.json()
    assert data["has_tree"] is True
    assert len(data["children"]) >= 1
    child_ids = [c["id"] for c in data["children"]]
    assert "formula-003" in child_ids


@pytest.mark.asyncio
async def test_tree_no_parent_for_root(client: AsyncClient, db: DbAdapter):
    await _seed_tree_data(db)
    response = await client.get(f"/api/formulas/{TREE_FORMULA_001}/tree")
    data = response.json()
    assert data["parent"] is None
    assert data["ancestors"] == []


@pytest.mark.asyncio
async def test_tree_ancestors_chain(client: AsyncClient, db: DbAdapter):
    """formula-004 (六君子汤) should have ancestors [四君子汤, 异功散]."""
    await _seed_tree_data(db)
    response = await client.get("/api/formulas/formula-004/tree")
    data = response.json()
    assert data["parent"]["id"] == "formula-003"
    assert data["parent"]["name"] == "异功散"
    ancestor_ids = [a["id"] for a in data["ancestors"]]
    assert ancestor_ids == [TREE_FORMULA_001, "formula-003"]
    ancestor_names = [a["name"] for a in data["ancestors"]]
    assert ancestor_names == ["四君子汤", "异功散"]


@pytest.mark.asyncio
async def test_tree_descendants_and_ancestors(client: AsyncClient, db: DbAdapter):
    """Middle node: formula-003 (异功散) has parent 四君子汤 and child 六君子汤."""
    await _seed_tree_data(db)
    response = await client.get("/api/formulas/formula-003/tree")
    data = response.json()
    assert data["parent"]["id"] == TREE_FORMULA_001
    assert len(data["children"]) >= 1
    child_ids = [c["id"] for c in data["children"]]
    assert "formula-004" in child_ids
    assert data["has_tree"] is True


@pytest.mark.asyncio
async def test_tree_404_for_invalid_formula(client: AsyncClient):
    response = await client.get("/api/formulas/nonexistent-formula/tree")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_tree_no_tree_for_leaf_formula(client: AsyncClient, db: DbAdapter):
    """A formula with no parent and no children has has_tree=False."""
    await db.execute(
        """INSERT OR REPLACE INTO formulas
           (id, name, source, category, composition, efficacy, indications,
            modifications, modifications_structured, derived_from_id, properties)
           VALUES ('formula-lonely', '孤方', '《测试》', '补益剂', '[]', '', '',
                   '[]', '[]', NULL, '{}')"""
    )
    await db.execute("COMMIT")
    response = await client.get("/api/formulas/formula-lonely/tree")
    data = response.json()
    assert data["has_tree"] is False
    assert data["parent"] is None
    assert data["children"] == []
    assert data["ancestors"] == []


# ---------------------------------------------------------------------------
# Modifications data tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_modifications_in_formula_detail(client: AsyncClient, db: DbAdapter):
    await _seed_tree_data(db)
    response = await client.get(f"/api/formulas/{TREE_FORMULA_001}")
    data = response.json()
    assert "modifications_structured" in data
    mods = data["modifications_structured"]
    assert isinstance(mods, list)
    assert len(mods) >= 3
    first = mods[0]
    assert "symptom" in first
    assert "add" in first
    assert isinstance(first["add"], list)


@pytest.mark.asyncio
async def test_modifications_add_remove_structure(client: AsyncClient, db: DbAdapter):
    await _seed_tree_data(db)
    response = await client.get(f"/api/formulas/{TREE_FORMULA_002}")
    data = response.json()
    mods = data["modifications_structured"]
    has_remove = any(m.get("remove") for m in mods)
    assert has_remove


@pytest.mark.asyncio
async def test_tree_summary_does_not_include_full_composition(client: AsyncClient, db: DbAdapter):
    """Tree endpoint should return lightweight summaries, not full composition."""
    await _seed_tree_data(db)
    response = await client.get(f"/api/formulas/{TREE_FORMULA_001}/tree")
    data = response.json()
    assert "composition" not in data["formula"]
    for child in data["children"]:
        assert "composition" not in child
