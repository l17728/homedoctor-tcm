"""Tests for GET /api/herbs/{herb_id}/formulas — 代表方剂 + 常用配伍.

Seeded data (conftest):
    herb-001 黄芪 → not in any seeded formula → empty.
    herb-002 当归 → in formula-002 四物汤 → co-occurring 熟地黄/白芍/川芎.
    herb-003 甘草 → in formula-001 四君子汤 → co-occurring 人参/白术/茯苓.
"""

from __future__ import annotations

import json

import pytest
from httpx import AsyncClient

from app.database import DbAdapter

MANY_FORMULA_HERB_ID = "herb-test-many"
MANY_FORMULA_HERB_NAME = "测试草"
OVER_LIMIT_HERB_ID = "herb-test-overlimit"


async def _seed_many_formulas(db: DbAdapter) -> None:
    """Seed a herb that appears in 25 formulas (tests the 20-item cap)."""
    await db.execute(
        """INSERT OR IGNORE INTO herbs
           (id, name, aliases, nature, flavor, meridians, efficacy, indications,
            contraindications, dosage_min_g, dosage_max_g, toxicity, category, properties)
           VALUES (?, ?, '', '', '', '', '', '', '', 0, 0, '无毒', '', '{}')""",
        (MANY_FORMULA_HERB_ID, MANY_FORMULA_HERB_NAME),
    )
    for i in range(25):
        await db.execute(
            """INSERT OR IGNORE INTO formulas
               (id, name, source, category, composition, efficacy, indications,
                modifications, modifications_structured, properties)
               VALUES (?, ?, '', '测试剂', ?, '', '', '[]', '[]', '{}')""",
            (
                f"formula-many-{i:02d}",
                f"测试方{i:02d}",
                json.dumps(
                    [
                        {"name": MANY_FORMULA_HERB_NAME, "dose": "10g", "role": "君"},
                        {"name": "配伍药A", "dose": "6g", "role": "臣"},
                        {"name": "配伍药B", "dose": "6g", "role": "佐"},
                    ],
                    ensure_ascii=False,
                ),
            ),
        )
    await db.execute("COMMIT")


@pytest.mark.asyncio
async def test_returns_formulas_containing_herb(client: AsyncClient):
    """GET /api/herbs/herb-003/formulas — 甘草 is in 四君子汤."""
    resp = await client.get("/api/herbs/herb-003/formulas")
    assert resp.status_code == 200
    data = resp.json()
    assert data["herb_name"] == "甘草"
    names = [f["name"] for f in data["formulas"]]
    assert "四君子汤" in names


@pytest.mark.asyncio
async def test_formulas_have_required_fields(client: AsyncClient):
    """Each formula item has id/name/category/efficacy."""
    resp = await client.get("/api/herbs/herb-003/formulas")
    data = resp.json()
    assert len(data["formulas"]) >= 1
    for f in data["formulas"]:
        assert {"id", "name", "category", "efficacy"}.issubset(f.keys())


@pytest.mark.asyncio
async def test_common_combinations_has_co_occurring_herbs(client: AsyncClient):
    """甘草 in 四君子汤 co-occurs with 人参/白术/茯苓."""
    resp = await client.get("/api/herbs/herb-003/formulas")
    data = resp.json()
    combo_names = [c["name"] for c in data["common_combinations"]]
    assert "人参" in combo_names
    assert "白术" in combo_names
    assert "茯苓" in combo_names


@pytest.mark.asyncio
async def test_common_combinations_excludes_target_herb(client: AsyncClient):
    """The queried herb itself never appears in common_combinations."""
    resp = await client.get("/api/herbs/herb-003/formulas")
    data = resp.json()
    names = [c["name"] for c in data["common_combinations"]]
    assert "甘草" not in names


@pytest.mark.asyncio
async def test_common_combinations_sorted_descending(client: AsyncClient):
    """common_combinations sorted by count descending."""
    resp = await client.get("/api/herbs/herb-003/formulas")
    data = resp.json()
    counts = [c["count"] for c in data["common_combinations"]]
    assert counts == sorted(counts, reverse=True)


@pytest.mark.asyncio
async def test_common_combinations_each_has_count(client: AsyncClient):
    resp = await client.get("/api/herbs/herb-003/formulas")
    data = resp.json()
    for c in data["common_combinations"]:
        assert isinstance(c["count"], int)
        assert c["count"] >= 1


@pytest.mark.asyncio
async def test_404_for_invalid_herb_id(client: AsyncClient):
    resp = await client.get("/api/herbs/nonexistent-herb/formulas")
    assert resp.status_code == 404
    assert "未找到" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_herb_in_no_formula_returns_empty(client: AsyncClient):
    """herb-001 黄芪 is not in any seeded formula."""
    resp = await client.get("/api/herbs/herb-001/formulas")
    assert resp.status_code == 200
    data = resp.json()
    assert data["herb_name"] == "黄芪"
    assert data["formulas"] == []
    assert data["common_combinations"] == []


@pytest.mark.asyncio
async def test_formulas_limited_to_20(client: AsyncClient, db):
    """When >20 formulas match, only 20 are returned."""
    await _seed_many_formulas(db)
    resp = await client.get(f"/api/herbs/{MANY_FORMULA_HERB_ID}/formulas")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["formulas"]) == 20


@pytest.mark.asyncio
async def test_co_occurrence_count_with_many_formulas(client: AsyncClient, db):
    """配伍药A appears in all 25 formulas → count == 25."""
    await _seed_many_formulas(db)
    resp = await client.get(f"/api/herbs/{MANY_FORMULA_HERB_ID}/formulas")
    data = resp.json()
    by_name = {c["name"]: c["count"] for c in data["common_combinations"]}
    assert by_name.get("配伍药A") == 25
    assert by_name.get("配伍药B") == 25


@pytest.mark.asyncio
async def test_common_combinations_limited_to_10(client: AsyncClient, db):
    """common_combinations capped at 10 items."""
    await _seed_many_formulas(db)
    # add 12 distinct co-occurring herbs
    for i in range(12):
        await db.execute(
            """INSERT OR IGNORE INTO formulas
               (id, name, source, category, composition, efficacy, indications,
                modifications, modifications_structured, properties)
               VALUES (?, ?, '', '测试剂', ?, '', '', '[]', '[]', '{}')""",
            (
                f"formula-extra-{i:02d}",
                f"额外方{i:02d}",
                json.dumps(
                    [
                        {"name": MANY_FORMULA_HERB_NAME, "dose": "10g", "role": "君"},
                        {"name": f"额外药{i:02d}", "dose": "6g", "role": "臣"},
                    ],
                    ensure_ascii=False,
                ),
            ),
        )
    await db.execute("COMMIT")
    resp = await client.get(f"/api/herbs/{MANY_FORMULA_HERB_ID}/formulas")
    data = resp.json()
    assert len(data["common_combinations"]) <= 10


@pytest.mark.asyncio
async def test_当归_in_四物汤(client: AsyncClient):
    """herb-002 当归 is in formula-002 四物汤."""
    resp = await client.get("/api/herbs/herb-002/formulas")
    assert resp.status_code == 200
    data = resp.json()
    assert data["herb_name"] == "当归"
    names = [f["name"] for f in data["formulas"]]
    assert "四物汤" in names
    combo_names = [c["name"] for c in data["common_combinations"]]
    assert "熟地黄" in combo_names
    assert "白芍" in combo_names
    assert "川芎" in combo_names
