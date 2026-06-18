"""Tests for the 智能配伍引擎 (smart formulation engine) — spec §16.3.

Covers:
- POST /api/formulations/recommend     (symptom match, constitution, exclude, safety)
- POST /api/formulations/tea-recipe    (3-5 herbs, doses, brewing instructions)
- POST /api/formulations/from-inventory (auth required, inventory match, expired skip)
- Engine-level direct calls (recommend_herbs / generate_tea_recipe / recommend_from_inventory)
- Safety check always runs on recommendations
- Disclaimer always present
- Chinese domain language
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.formulation_engine import (
    DISCLAIMER,
    generate_tea_recipe,
    recommend_from_inventory,
    recommend_herbs,
)


# ---------------------------------------------------------------------------
# POST /api/formulations/recommend
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_recommend_returns_relevant_herbs(client: AsyncClient):
    """POST /recommend with 补气 symptom returns 黄芪 (efficacy contains 补气)."""
    response = await client.post("/api/formulations/recommend", json={
        "symptoms": ["补气", "气虚", "乏力"],
    })
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["recommendations"], list)
    assert len(data["recommendations"]) > 0
    names = [r["name"] for r in data["recommendations"]]
    # 黄芪 is in seed data with efficacy "补气升阳..." → must surface.
    assert "黄芪" in names
    # Each recommendation carries a Chinese reason.
    for rec in data["recommendations"]:
        assert rec["score"] > 0
        assert isinstance(rec["reason"], str) and rec["reason"]
        assert rec["category"]  # Chinese category label


@pytest.mark.asyncio
async def test_recommend_includes_safety_check_and_disclaimer(client: AsyncClient):
    """Every recommendation carries a safety_check object and disclaimer."""
    response = await client.post("/api/formulations/recommend", json={
        "symptoms": ["气虚"],
    })
    data = response.json()
    assert "safety_check" in data
    sc = data["safety_check"]
    assert isinstance(sc["safe"], bool)
    assert isinstance(sc["warnings"], list)
    assert isinstance(sc["checked_herbs"], list)
    # Disclaimer must be present and non-empty.
    assert data["disclaimer"] and isinstance(data["disclaimer"], str)
    assert "咨询" in data["disclaimer"]


@pytest.mark.asyncio
async def test_recommend_constitution_filter(client: AsyncClient):
    """Constitution compatibility influences ranking — 气虚质 boosts 补气药."""
    # 气虚质 should surface 补虚药 / 补气 herbs preferentially.
    response = await client.post("/api/formulations/recommend", json={
        "symptoms": ["气虚"],
        "constitution": "气虚质",
    })
    data = response.json()
    assert data["constitution"] == "气虚质"
    cats = [r.get("category", "") for r in data["recommendations"]]
    # At least one recommendation should be from 补虚/补气 family.
    assert any("补" in c for c in cats)


@pytest.mark.asyncio
async def test_recommend_exclude_filters_herbs(client: AsyncClient):
    """Exclude list filters out specific herbs (allergies / preferences)."""
    response = await client.post("/api/formulations/recommend", json={
        "symptoms": ["补气", "气虚"],
        "exclude": ["黄芪"],
    })
    data = response.json()
    names = [r["name"] for r in data["recommendations"]]
    assert "黄芪" not in names


@pytest.mark.asyncio
async def test_recommend_empty_symptoms_returns_400(client: AsyncClient):
    """Missing symptoms → 400 (must provide at least one symptom keyword)."""
    response = await client.post("/api/formulations/recommend", json={
        "symptoms": [],
    })
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_recommend_no_symptoms_missing_key_400(client: AsyncClient):
    """Missing symptoms key entirely → 400."""
    response = await client.post("/api/formulations/recommend", json={
        "constitution": "气虚质",
    })
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_recommend_unmatched_symptom_returns_empty(client: AsyncClient):
    """Symptoms that match nothing yield an empty recommendations list (not error)."""
    response = await client.post("/api/formulations/recommend", json={
        "symptoms": ["完全不存在的奇怪症状词XYZ"],
    })
    assert response.status_code == 200
    data = response.json()
    assert data["recommendations"] == []


@pytest.mark.asyncio
async def test_conflicting_symptoms_handled_gracefully(client: AsyncClient):
    """Conflicting symptoms (怕冷 + 高热不退 + 四肢冰凉) must not crash.

    These describe contradictory states (cold-deficiency vs. high fever). The
    engine should respond gracefully — 200 with whatever it can rank — rather
    than raising an exception or producing a malformed payload.
    """
    response = await client.post("/api/formulations/recommend", json={
        "symptoms": ["怕冷", "高热不退", "四肢冰凉"],
    })
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["recommendations"], list)
    assert "safety_check" in data
    assert isinstance(data["safety_check"]["safe"], bool)
    assert data["disclaimer"]


@pytest.mark.asyncio
async def test_empty_symptoms_handled_without_crash(client: AsyncClient):
    """Empty symptom list must be rejected gracefully (400), never a 500 crash."""
    response = await client.post("/api/formulations/recommend", json={
        "symptoms": [],
    })
    assert response.status_code in (200, 400)
    assert response.status_code != 500


@pytest.mark.asyncio
async def test_recommend_safety_check_runs_on_top_picks(client: AsyncClient):
    """If the top picks include a contraindicated pair, safety_check flags it.

    Seed data: 甘草 and 甘遂 are 十八反 contraindicated. We craft a symptom
    that would surface both — but here we just verify the safety_check field
    reports whatever the engine found (warnings list is structurally correct).
    """
    response = await client.post("/api/formulations/recommend", json={
        "symptoms": ["气虚", "健脾", "止咳", "解毒"],
    })
    data = response.json()
    sc = data["safety_check"]
    # If 甘草 is in the picks, checked_herbs will include it.
    if "甘草" in sc["checked_herbs"]:
        # Either safe or warnings present — structure must be valid either way.
        for w in sc["warnings"]:
            assert "layer" in w and "severity" in w
            assert w["severity"] in ("critical", "high", "medium", "low")


# ---------------------------------------------------------------------------
# POST /api/formulations/tea-recipe
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tea_recipe_has_3_to_5_herbs(client: AsyncClient):
    """Tea recipe contains between 3 and 5 herbs per spec §16.3."""
    response = await client.post("/api/formulations/tea-recipe", json={
        "symptoms": ["气虚", "乏力", "健脾"],
    })
    assert response.status_code == 200
    data = response.json()
    assert 3 <= len(data["herbs"]) <= 5, f"expected 3-5 herbs, got {len(data['herbs'])}"
    # Each herb has a Chinese name, dose in grams, and a 君/臣/佐/使 role.
    for h in data["herbs"]:
        assert h["name"]
        assert isinstance(h["dose_g"], int)
        assert 1 <= h["dose_g"] <= 10  # tea dose is small
        assert h["role"] in {"君", "臣", "佐", "使"}


@pytest.mark.asyncio
async def test_tea_recipe_dose_within_tea_range(client: AsyncClient):
    """Tea doses are within the safe 3-6g range."""
    response = await client.post("/api/formulations/tea-recipe", json={
        "symptoms": ["气虚"],
    })
    data = response.json()
    for h in data["herbs"]:
        assert 3 <= h["dose_g"] <= 6, f"{h['name']} dose {h['dose_g']}g outside 3-6g"


@pytest.mark.asyncio
async def test_tea_recipe_has_brewing_instructions(client: AsyncClient):
    """Tea recipe includes brewing instructions in Chinese."""
    response = await client.post("/api/formulations/tea-recipe", json={
        "symptoms": ["失眠", "心悸"],
    })
    data = response.json()
    brewing = data["brewing"]
    assert isinstance(brewing, str) and len(brewing) > 20
    # Should reference 沸水 / 焖泡 / 冲泡 keywords.
    assert any(kw in brewing for kw in ("沸水", "焖", "冲泡", "温服"))


@pytest.mark.asyncio
async def test_tea_recipe_safety_check_present(client: AsyncClient):
    """Tea recipe carries a safety check (five-layer engine)."""
    response = await client.post("/api/formulations/tea-recipe", json={
        "symptoms": ["气虚"],
    })
    data = response.json()
    assert "safety_check" in data
    assert "safe" in data["safety_check"]
    assert data["disclaimer"]


@pytest.mark.asyncio
async def test_tea_recipe_empty_symptoms_400(client: AsyncClient):
    """Missing symptoms → 400."""
    response = await client.post("/api/formulations/tea-recipe", json={
        "symptoms": [],
    })
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_tea_recipe_harmonizer_added_when_room(client: AsyncClient):
    """When 甘草 is available and not already picked, it's appended as 使药."""
    response = await client.post("/api/formulations/tea-recipe", json={
        "symptoms": ["气虚", "乏力", "健脾"],
    })
    data = response.json()
    if len(data["herbs"]) <= 5:
        names = [h["name"] for h in data["herbs"]]
        # 甘草 from seed data should be added as harmonizer (使药) when present.
        if "甘草" in names:
            envoy = next(h for h in data["herbs"] if h["name"] == "甘草")
            assert envoy["role"] == "使"


# ---------------------------------------------------------------------------
# POST /api/formulations/from-inventory (auth required)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_from_inventory_requires_auth(client: AsyncClient):
    """Without auth → 401."""
    response = await client.post("/api/formulations/from-inventory", json={
        "symptoms": ["气虚"],
    })
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_from_inventory_empty_cabinet(client: AsyncClient, auth_headers: dict):
    """User with empty cabinet returns no inventory matches but may have missing_suggestions."""
    response = await client.post(
        "/api/formulations/from-inventory",
        json={"symptoms": ["气虚", "乏力"]},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["recommendations"], list)
    assert isinstance(data["missing_suggestions"], list)
    # Empty cabinet → no inventory recommendations.
    assert data["recommendations"] == []


@pytest.mark.asyncio
async def test_from_inventory_matches_user_medicine(
    client: AsyncClient, auth_headers: dict
):
    """A medicine whose name matches a symptom keyword is recommended."""
    # Add a 中成药 medicine whose name contains "补气".
    create = await client.post(
        "/api/medicines",
        json={
            "name": "补气养血丸",
            "type": "chinese_patent",
            "quantity": 2,
            "properties": {"drugClass": "中成药"},
        },
        headers=auth_headers,
    )
    assert create.status_code == 201

    response = await client.post(
        "/api/formulations/from-inventory",
        json={"symptoms": ["补气"]},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    rec_names = [r["medicine"]["name"] for r in data["recommendations"]]
    assert "补气养血丸" in rec_names
    # Marked as already in inventory.
    match = next(r for r in data["recommendations"] if r["medicine"]["name"] == "补气养血丸")
    assert match["in_inventory"] is True
    assert match["score"] > 0
    assert "药箱已有" in match["reason"]


@pytest.mark.asyncio
async def test_from_inventory_excludes_expired(
    client: AsyncClient, auth_headers: dict
):
    """Expired medicines are not recommended (spec §16.4)."""
    await client.post(
        "/api/medicines",
        json={
            "name": "过期补气丸",
            "type": "chinese_patent",
            "quantity": 5,
            "expiry_date": "2020-01-01",  # already expired
        },
        headers=auth_headers,
    )
    response = await client.post(
        "/api/formulations/from-inventory",
        json={"symptoms": ["补气"]},
        headers=auth_headers,
    )
    data = response.json()
    rec_names = [r["medicine"]["name"] for r in data["recommendations"]]
    assert "过期补气丸" not in rec_names


@pytest.mark.asyncio
async def test_from_inventory_empty_symptoms_400(
    client: AsyncClient, auth_headers: dict
):
    """Missing symptoms → 400 even when authenticated."""
    response = await client.post(
        "/api/formulations/from-inventory",
        json={"symptoms": []},
        headers=auth_headers,
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_from_inventory_safety_check_and_disclaimer(
    client: AsyncClient, auth_headers: dict
):
    """from-inventory also attaches a safety_check and disclaimer."""
    response = await client.post(
        "/api/formulations/from-inventory",
        json={"symptoms": ["气虚"]},
        headers=auth_headers,
    )
    data = response.json()
    assert "safety_check" in data
    assert data["disclaimer"] == DISCLAIMER or data["disclaimer"]


@pytest.mark.asyncio
async def test_from_inventory_missing_suggestions_are_not_in_inventory(
    client: AsyncClient, auth_headers: dict
):
    """missing_suggestions should not duplicate items already in the cabinet."""
    await client.post(
        "/api/medicines",
        json={
            "name": "黄芪颗粒",
            "type": "chinese_patent",
            "quantity": 3,
        },
        headers=auth_headers,
    )
    response = await client.post(
        "/api/formulations/from-inventory",
        json={"symptoms": ["补气", "气虚"]},
        headers=auth_headers,
    )
    data = response.json()
    inv_names = {r["medicine"]["name"] for r in data["recommendations"]}
    missing_names = {m["name"] for m in data["missing_suggestions"]}
    # No overlap between inventory picks and missing suggestions.
    assert not (inv_names & missing_names)


# ---------------------------------------------------------------------------
# Engine-level direct calls (no HTTP)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_engine_recommend_herbs_direct(db):
    """recommend_herbs engine function works when called directly with db."""
    result = await recommend_herbs(
        db=db,
        symptoms=["气虚", "健脾"],
        constitution="气虚质",
    )
    assert "recommendations" in result
    assert "safety_check" in result
    assert result["disclaimer"]


@pytest.mark.asyncio
async def test_engine_generate_tea_recipe_direct(db):
    """generate_tea_recipe returns 3-5 herbs with doses and brewing guide."""
    recipe = await generate_tea_recipe(db=db, symptoms=["气虚", "乏力"])
    assert 3 <= len(recipe["herbs"]) <= 5
    assert recipe["brewing"]
    assert recipe["name"].endswith("代茶饮")
    for h in recipe["herbs"]:
        assert h["dose_g"] >= 1


@pytest.mark.asyncio
async def test_engine_recommend_from_inventory_direct(db):
    """recommend_from_inventory engine works with a direct medicine list."""
    medicines = [
        {
            "id": "m1",
            "name": "补气丸",
            "type": "chinese_patent",
            "quantity": 5,
            "active_ingredients": [],
            "herbal_fields": {},
            "properties": {},
        },
    ]
    result = await recommend_from_inventory(
        db=db, symptoms=["补气"], user_medicines=medicines
    )
    assert len(result["recommendations"]) == 1
    assert result["recommendations"][0]["medicine"]["name"] == "补气丸"


@pytest.mark.asyncio
async def test_engine_constitution_excludes_contraindicated(db):
    """A herb with the user's constitution in its contraindications is filtered.

    黄芪 seed data has '阴虚阳亢' in contraindications → excluded for 阴虚质.
    """
    result = await recommend_herbs(
        db=db,
        symptoms=["补气", "气虚"],
        constitution="阴虚质",
    )
    names = [r["name"] for r in result["recommendations"]]
    assert "黄芪" not in names, "黄芪 should be excluded for 阴虚质 (contraindicated)"


@pytest.mark.asyncio
async def test_engine_inventory_skips_expired(db):
    """Expired medicines are skipped by the engine."""
    from datetime import datetime, timezone, timedelta
    CST = timezone(timedelta(hours=8))
    past = (datetime.now(CST) - timedelta(days=10)).strftime("%Y-%m-%d")
    medicines = [
        {
            "id": "m1",
            "name": "过期补气丸",
            "type": "chinese_patent",
            "quantity": 5,
            "expiry_date": past,
            "active_ingredients": [],
            "herbal_fields": {},
            "properties": {},
        },
    ]
    result = await recommend_from_inventory(
        db=db, symptoms=["补气"], user_medicines=medicines
    )
    assert result["recommendations"] == []


@pytest.mark.asyncio
async def test_engine_inventory_keeps_non_expired(db):
    """Non-expired medicines with matching symptoms are kept."""
    from datetime import datetime, timezone, timedelta
    CST = timezone(timedelta(hours=8))
    future = (datetime.now(CST) + timedelta(days=365)).strftime("%Y-%m-%d")
    medicines = [
        {
            "id": "m1",
            "name": "补气丸",
            "type": "chinese_patent",
            "quantity": 5,
            "expiry_date": future,
            "active_ingredients": [],
            "herbal_fields": {},
            "properties": {},
        },
    ]
    result = await recommend_from_inventory(
        db=db, symptoms=["补气"], user_medicines=medicines
    )
    assert len(result["recommendations"]) == 1
