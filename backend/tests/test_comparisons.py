"""Tests for comparisons endpoints — 对比分析 (spec §3.4 V2)."""

import pytest
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Herb comparison
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_compare_two_herbs_post(client: AsyncClient):
    """POST /api/comparisons/herbs compares two herbs side by side."""
    resp = await client.post("/api/comparisons/herbs", json={
        "herb_ids": ["herb-001", "herb-002"],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["herbs"]) == 2

    names = [h["name"] for h in data["herbs"]]
    assert "黄芪" in names
    assert "当归" in names


@pytest.mark.asyncio
async def test_compare_herbs_property_table(client: AsyncClient):
    """POST /api/comparisons/herbs returns property comparison table."""
    resp = await client.post("/api/comparisons/herbs", json={
        "herb_ids": ["herb-001", "herb-002"],
    })
    assert resp.status_code == 200
    data = resp.json()

    table = data["property_table"]
    assert isinstance(table, list)
    assert len(table) > 0

    # Check table structure
    for row in table:
        assert "field" in row
        assert "label" in row
        assert "values" in row
        assert "same" in row
        assert "黄芪" in row["values"]
        assert "当归" in row["values"]

    # 黄芪 and 当归 have different nature → not same
    nature_row = next(r for r in table if r["field"] == "nature")
    assert nature_row["same"] is False


@pytest.mark.asyncio
async def test_compare_herbs_similarities(client: AsyncClient):
    """POST /api/comparisons/herbs returns similarities."""
    resp = await client.post("/api/comparisons/herbs", json={
        "herb_ids": ["herb-001", "herb-002", "herb-003"],
    })
    assert resp.status_code == 200
    data = resp.json()

    # All three herbs are 补虚药 category → should have category similarity
    assert isinstance(data["similarities"], list)
    category_sim = [s for s in data["similarities"] if "补虚药" in s]
    assert len(category_sim) > 0


@pytest.mark.asyncio
async def test_compare_herbs_differences(client: AsyncClient):
    """POST /api/comparisons/herbs returns differences."""
    resp = await client.post("/api/comparisons/herbs", json={
        "herb_ids": ["herb-001", "herb-002"],
    })
    assert resp.status_code == 200
    data = resp.json()

    assert isinstance(data["differences"], list)
    # 黄芪 nature=微温, 当归 nature=温 → different
    nature_diff = [d for d in data["differences"] if "药性" in d]
    assert len(nature_diff) > 0


@pytest.mark.asyncio
async def test_compare_herbs_safety_notes(client: AsyncClient):
    """POST /api/comparisons/herbs returns safety notes for combined usage."""
    resp = await client.post("/api/comparisons/herbs", json={
        "herb_ids": ["herb-001", "herb-002"],
    })
    assert resp.status_code == 200
    data = resp.json()

    assert isinstance(data["safety_notes"], list)


@pytest.mark.asyncio
async def test_compare_herbs_quick_get(client: AsyncClient):
    """GET /api/comparisons/herbs/{a}/{b} quick two-herb comparison."""
    resp = await client.get("/api/comparisons/herbs/herb-001/herb-002")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["herbs"]) == 2


@pytest.mark.asyncio
async def test_compare_herbs_not_enough(client: AsyncClient):
    """POST /api/comparisons/herbs requires at least 2 herbs."""
    resp = await client.post("/api/comparisons/herbs", json={
        "herb_ids": ["herb-001"],
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_compare_herbs_invalid_id(client: AsyncClient):
    """POST /api/comparisons/herbs with invalid herb ID returns 422."""
    resp = await client.post("/api/comparisons/herbs", json={
        "herb_ids": ["herb-001", "nonexistent"],
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_compare_three_herbs(client: AsyncClient):
    """POST /api/comparisons/herbs works with 3+ herbs."""
    resp = await client.post("/api/comparisons/herbs", json={
        "herb_ids": ["herb-001", "herb-002", "herb-003"],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["herbs"]) == 3
    assert len(data["property_table"]) > 0

    # Each property row should have values for all 3 herbs
    for row in data["property_table"]:
        assert len(row["values"]) == 3


@pytest.mark.asyncio
async def test_compare_herbs_shared_meridian(client: AsyncClient):
    """黄苠 (脾,肺) and 甘草 (心,肺,脾,胃) share 脾 meridian."""
    resp = await client.post("/api/comparisons/herbs", json={
        "herb_ids": ["herb-001", "herb-003"],
    })
    assert resp.status_code == 200
    data = resp.json()

    # Should find shared meridian
    meridian_sim = [s for s in data["similarities"] if "脾" in s]
    assert len(meridian_sim) > 0


@pytest.mark.asyncio
async def test_compare_herbs_not_found_list(client: AsyncClient):
    """POST /api/comparisons/herbs returns not_found list for missing IDs."""
    resp = await client.post("/api/comparisons/herbs", json={
        "herb_ids": ["herb-001", "herb-002", "missing-001"],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "missing-001" in data["not_found"]


# ---------------------------------------------------------------------------
# Formula comparison
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_compare_two_formulas(client: AsyncClient):
    """POST /api/comparisons/formulas compares two formulas."""
    resp = await client.post("/api/comparisons/formulas", json={
        "formula_ids": ["formula-001", "formula-002"],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["formulas"]) == 2

    names = [f["name"] for f in data["formulas"]]
    assert "四君子汤" in names
    assert "四物汤" in names


@pytest.mark.asyncio
async def test_compare_formulas_shared_herbs(client: AsyncClient):
    """四君子汤 (含甘草) and 四物汤 (不含甘草) — shared_herbs should work correctly."""
    resp = await client.post("/api/comparisons/formulas", json={
        "formula_ids": ["formula-001", "formula-002"],
    })
    assert resp.status_code == 200
    data = resp.json()

    assert "shared_herbs" in data
    assert isinstance(data["shared_herbs"], list)
    assert "shared_herb_count" in data

    # 四君子汤: 人参, 白术, 茯苓, 甘草
    # 四物汤:   熟地黄, 当归, 白芍, 川芎
    # → no shared herbs
    assert data["shared_herb_count"] == 0


@pytest.mark.asyncio
async def test_compare_formulas_unique_herbs(client: AsyncClient):
    """POST /api/comparisons/formulas identifies herbs unique to each formula."""
    resp = await client.post("/api/comparisons/formulas", json={
        "formula_ids": ["formula-001", "formula-002"],
    })
    assert resp.status_code == 200
    data = resp.json()

    unique = data["herbs_unique_to_each"]
    assert "四君子汤" in unique
    assert "四物汤" in unique
    # 四君子汤 has 人参, 白术, 茯苓, 甘草 — all unique
    assert "人参" in unique["四君子汤"]
    assert "当归" in unique["四物汤"]


@pytest.mark.asyncio
async def test_compare_formulas_overlap(client: AsyncClient):
    """POST /api/comparisons/formulas returns composition overlap data."""
    resp = await client.post("/api/comparisons/formulas", json={
        "formula_ids": ["formula-001", "formula-002"],
    })
    assert resp.status_code == 200
    data = resp.json()

    overlap = data["composition_overlap"]
    assert isinstance(overlap, list)
    assert len(overlap) == 1  # one pair
    pair = overlap[0]
    assert pair["formula_a"] == "四君子汤"
    assert pair["formula_b"] == "四物汤"
    assert pair["overlap_ratio"] == 0.0  # no shared herbs


@pytest.mark.asyncio
async def test_compare_formulas_efficacy(client: AsyncClient):
    """POST /api/comparisons/formulas returns efficacy comparison."""
    resp = await client.post("/api/comparisons/formulas", json={
        "formula_ids": ["formula-001", "formula-002"],
    })
    assert resp.status_code == 200
    data = resp.json()

    eff = data["efficacy_comparison"]
    assert len(eff) == 2
    efficacies = {e["name"]: e["efficacy"] for e in eff}
    assert efficacies["四君子汤"] == "益气健脾"
    assert efficacies["四物汤"] == "补血调血"


@pytest.mark.asyncio
async def test_compare_formulas_safety_notes(client: AsyncClient):
    """POST /api/comparisons/formulas returns safety notes for all combined herbs."""
    resp = await client.post("/api/comparisons/formulas", json={
        "formula_ids": ["formula-001", "formula-002"],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["safety_notes"], list)


@pytest.mark.asyncio
async def test_compare_formulas_property_table(client: AsyncClient):
    """POST /api/comparisons/formulas returns property comparison table."""
    resp = await client.post("/api/comparisons/formulas", json={
        "formula_ids": ["formula-001", "formula-002"],
    })
    assert resp.status_code == 200
    data = resp.json()

    table = data["property_table"]
    assert isinstance(table, list)
    # Both formulas are 补益剂 category → same
    category_row = next(r for r in table if r["field"] == "category")
    assert category_row["same"] is True


@pytest.mark.asyncio
async def test_compare_formulas_not_enough(client: AsyncClient):
    """POST /api/comparisons/formulas requires at least 2 formulas."""
    resp = await client.post("/api/comparisons/formulas", json={
        "formula_ids": ["formula-001"],
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_compare_formulas_invalid_id(client: AsyncClient):
    """POST /api/comparisons/formulas with invalid formula ID returns 422."""
    resp = await client.post("/api/comparisons/formulas", json={
        "formula_ids": ["formula-001", "nonexistent"],
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_compare_formulas_not_found(client: AsyncClient):
    """POST /api/comparisons/formulas returns not_found for missing IDs."""
    resp = await client.post("/api/comparisons/formulas", json={
        "formula_ids": ["formula-001", "formula-002", "missing-f"],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "missing-f" in data["not_found"]
