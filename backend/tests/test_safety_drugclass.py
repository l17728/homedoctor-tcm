"""drugClass awareness tests for Layer 1b (中西药交互) — spec §15.2.

Verifies that the safety engine correctly distinguishes between:
  - 西药 (western medicine) → Layer 1b (中西药交互) fires
  - 中成药 (Chinese patent medicine) → Layer 1b skipped, Layer 1a only
  - 中药 (Chinese herbal medicine) → Layer 1b skipped, Layer 1a only
  - No drugClass → defaults to 西药 (backward compatible)
"""

from __future__ import annotations

import json

import pytest
from httpx import AsyncClient

from app.database import DbAdapter
from app.safety_engine import _get_medicine_drug_class, run_safety_check


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _seed_herbs(db: DbAdapter) -> None:
    herbs = [
        {"id": "dc-herb-001", "name": "当归", "aliases": "", "nature": "温",
         "flavor": "甘,辛", "meridians": "肝,心,脾", "efficacy": "补血活血",
         "indications": "血虚萎黄", "contraindications": "湿盛中满者慎用",
         "dosage_min_g": 6, "dosage_max_g": 12, "toxicity": "无毒",
         "category": "补虚药", "properties": "{}"},
        {"id": "dc-herb-002", "name": "甘草", "aliases": "", "nature": "平",
         "flavor": "甘", "meridians": "心,肺,脾,胃", "efficacy": "补脾益气",
         "indications": "脾胃虚弱", "contraindications": "湿盛胀满者慎用",
         "dosage_min_g": 2, "dosage_max_g": 10, "toxicity": "无毒",
         "category": "补虚药", "properties": "{}"},
        {"id": "dc-herb-003", "name": "甘遂", "aliases": "", "nature": "寒",
         "flavor": "苦", "meridians": "肺,肾,大肠", "efficacy": "泻水逐饮",
         "indications": "水肿胀满", "contraindications": "孕妇禁用",
         "dosage_min_g": 0.5, "dosage_max_g": 1.5, "toxicity": "有毒",
         "category": "泻下药", "properties": "{}"},
        {"id": "dc-herb-004", "name": "麻黄", "aliases": "", "nature": "温",
         "flavor": "辛,微苦", "meridians": "肺,膀胱", "efficacy": "发汗解表",
         "indications": "风寒感冒", "contraindications": "表虚自汗者慎用",
         "dosage_min_g": 2, "dosage_max_g": 10, "toxicity": "无毒",
         "category": "解表药", "properties": "{}"},
    ]
    for h in herbs:
        await db.execute(
            """INSERT OR IGNORE INTO herbs
               (id, name, aliases, nature, flavor, meridians, efficacy, indications,
                contraindications, dosage_min_g, dosage_max_g, toxicity, category, properties)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (h["id"], h["name"], h["aliases"], h["nature"], h["flavor"], h["meridians"],
             h["efficacy"], h["indications"], h["contraindications"],
             h["dosage_min_g"], h["dosage_max_g"], h["toxicity"], h["category"], h["properties"]),
        )


async def _insert_medicine(
    db: DbAdapter,
    name: str,
    drug_class: str | None,
    tenant_id: str = "test-tenant",
) -> None:
    props = json.dumps({"drugClass": drug_class}, ensure_ascii=False) if drug_class else "{}"
    await db.execute(
        """INSERT INTO medicines
           (id, tenant_id, name, type, drug_class, properties)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (f"med-{name}", tenant_id, name, "western", drug_class or "", props),
    )


# ===========================================================================
# _get_medicine_drug_class unit tests
# ===========================================================================

@pytest.mark.asyncio
async def test_get_drug_class_xiyao(db: DbAdapter):
    await _insert_medicine(db, "测试西药", "西药")
    assert await _get_medicine_drug_class(db, "测试西药") == "西药"


@pytest.mark.asyncio
async def test_get_drug_class_zhongchengyao(db: DbAdapter):
    await _insert_medicine(db, "测试中成药", "中成药")
    assert await _get_medicine_drug_class(db, "测试中成药") == "中成药"


@pytest.mark.asyncio
async def test_get_drug_class_zhongyao(db: DbAdapter):
    await _insert_medicine(db, "测试中药", "中药")
    assert await _get_medicine_drug_class(db, "测试中药") == "中药"


@pytest.mark.asyncio
async def test_get_drug_class_not_in_table_defaults_xiyao(db: DbAdapter):
    assert await _get_medicine_drug_class(db, "不存在的药品") == "西药"


@pytest.mark.asyncio
async def test_get_drug_class_empty_properties_defaults_xiyao(db: DbAdapter):
    await _insert_medicine(db, "无分类药品", None)
    assert await _get_medicine_drug_class(db, "无分类药品") == "西药"


@pytest.mark.asyncio
async def test_get_drug_class_invalid_value_defaults_xiyao(db: DbAdapter):
    await db.execute(
        """INSERT INTO medicines (id, tenant_id, name, type, properties)
           VALUES (?, ?, ?, ?, ?)""",
        ("med-invalid", "t", "无效分类药", "western",
         json.dumps({"drugClass": "保健品"}, ensure_ascii=False)),
    )
    assert await _get_medicine_drug_class(db, "无效分类药") == "西药"


# ===========================================================================
# Layer 1b: 西药 → warnings generated
# ===========================================================================

@pytest.mark.asyncio
async def test_xiyao_medicine_triggers_layer1b(db: DbAdapter):
    """华法林(西药) + 当归 → Layer 1b 中西药交互 warning."""
    await _seed_herbs(db)
    await _insert_medicine(db, "华法林", "西药")

    result = await run_safety_check(db, ["当归"], ["华法林"])
    layer1b = [w for w in result.warnings if w.layer == 1 and "中西药交互" in w.title]
    assert len(layer1b) >= 1
    assert layer1b[0].severity == "critical"


@pytest.mark.asyncio
async def test_xiyao_medicine_multiple_herbs(db: DbAdapter):
    """华法林(西药) + 当归+甘草 → Layer 1b fires for matching herb."""
    await _seed_herbs(db)
    await _insert_medicine(db, "华法林", "西药")

    result = await run_safety_check(db, ["当归", "甘草"], ["华法林"])
    layer1b = [w for w in result.warnings if w.layer == 1 and "中西药交互" in w.title]
    assert len(layer1b) >= 1
    assert any("当归" in w.herbs for w in layer1b)


# ===========================================================================
# Layer 1b: 中成药 → NO warnings (skipped)
# ===========================================================================

@pytest.mark.asyncio
async def test_zhongchengyao_medicine_skips_layer1b(db: DbAdapter):
    """华法林(中成药) + 当归 → NO Layer 1b warning."""
    await _seed_herbs(db)
    await _insert_medicine(db, "华法林", "中成药")

    result = await run_safety_check(db, ["当归"], ["华法林"])
    layer1b = [w for w in result.warnings if w.layer == 1 and "中西药交互" in w.title]
    assert len(layer1b) == 0


@pytest.mark.asyncio
async def test_zhongchengyao_medicine_no_layer1b_with_jiangyayao(db: DbAdapter):
    """降压药(中成药) + 甘草 → NO Layer 1b (R-07 suppressed)."""
    await _seed_herbs(db)
    await _insert_medicine(db, "降压药", "中成药")

    result = await run_safety_check(db, ["甘草"], ["降压药"])
    layer1b = [w for w in result.warnings if w.layer == 1 and "中西药交互" in w.title]
    assert len(layer1b) == 0


# ===========================================================================
# Layer 1b: 中药 → NO warnings (skipped), Layer 1a still checked
# ===========================================================================

@pytest.mark.asyncio
async def test_zhongyao_medicine_skips_layer1b(db: DbAdapter):
    """华法林(中药) + 当归 → NO Layer 1b warning."""
    await _seed_herbs(db)
    await _insert_medicine(db, "华法林", "中药")

    result = await run_safety_check(db, ["当归"], ["华法林"])
    layer1b = [w for w in result.warnings if w.layer == 1 and "中西药交互" in w.title]
    assert len(layer1b) == 0


@pytest.mark.asyncio
async def test_zhongyao_medicine_layer1a_still_checked(db: DbAdapter):
    """中药 medicine + conflicting herbs → Layer 1b skipped but Layer 1a fires.

    甘草+甘遂 is an 十八反 conflict — Layer 1a should catch it regardless
    of the medicine's drugClass.
    """
    await _seed_herbs(db)
    await _insert_medicine(db, "降压药", "中药")

    result = await run_safety_check(db, ["甘草", "甘遂"], ["降压药"])
    layer1b = [w for w in result.warnings if w.layer == 1 and "中西药交互" in w.title]
    assert len(layer1b) == 0
    layer1a = [w for w in result.warnings if w.layer == 1 and "十八反" in w.title]
    assert len(layer1a) >= 1


# ===========================================================================
# Backward compatibility: no drugClass → defaults to 西药
# ===========================================================================

@pytest.mark.asyncio
async def test_no_drugclass_defaults_to_xiyao(db: DbAdapter):
    """Medicine not in table (no drugClass) → defaults to 西药 → Layer 1b fires."""
    await _seed_herbs(db)

    result = await run_safety_check(db, ["当归"], ["华法林"])
    layer1b = [w for w in result.warnings if w.layer == 1 and "中西药交互" in w.title]
    assert len(layer1b) >= 1


@pytest.mark.asyncio
async def test_empty_properties_defaults_to_xiyao(db: DbAdapter):
    """Medicine in table but properties={} → defaults to 西药 → Layer 1b fires."""
    await _seed_herbs(db)
    await _insert_medicine(db, "华法林", None)

    result = await run_safety_check(db, ["当归"], ["华法林"])
    layer1b = [w for w in result.warnings if w.layer == 1 and "中西药交互" in w.title]
    assert len(layer1b) >= 1


# ===========================================================================
# Mixed drugClass scenario
# ===========================================================================

@pytest.mark.asyncio
async def test_mixed_drugclass_xiyao_and_zhongchengyao(db: DbAdapter):
    """华法林(西药) triggers Layer 1b; 降压药(中成药) does not."""
    await _seed_herbs(db)
    await _insert_medicine(db, "华法林", "西药")
    await _insert_medicine(db, "降压药", "中成药")

    result = await run_safety_check(db, ["当归", "甘草"], ["华法林", "降压药"])
    layer1b = [w for w in result.warnings if w.layer == 1 and "中西药交互" in w.title]
    titles = [w.title for w in layer1b]
    assert any("华法林" in t or "R-01" in t for t in titles)
    assert not any("降压药" in t or "R-07" in t for t in titles)


# ===========================================================================
# End-to-end via /api/safety/check-v2
# ===========================================================================

@pytest.mark.asyncio
async def test_e2e_xiyao_triggers_layer1b(client: AsyncClient, db: DbAdapter):
    """E2E: 西药 medicine via API → Layer 1b fires."""
    await _seed_herbs(db)
    await _insert_medicine(db, "华法林", "西药")
    await db.execute("COMMIT")

    resp = await client.post("/api/safety/check-v2", json={
        "herbs": ["当归"], "medicines": ["华法林"],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["safe"] is False
    layer1b = [w for w in data["warnings"] if w["layer"] == 1 and "中西药交互" in w["title"]]
    assert len(layer1b) >= 1


@pytest.mark.asyncio
async def test_e2e_zhongchengyao_skips_layer1b(client: AsyncClient, db: DbAdapter):
    """E2E: 中成药 medicine via API → Layer 1b NOT generated."""
    await _seed_herbs(db)
    await _insert_medicine(db, "华法林", "中成药")
    await db.execute("COMMIT")

    resp = await client.post("/api/safety/check-v2", json={
        "herbs": ["当归"], "medicines": ["华法林"],
    })
    assert resp.status_code == 200
    data = resp.json()
    layer1b = [w for w in data["warnings"] if w["layer"] == 1 and "中西药交互" in w["title"]]
    assert len(layer1b) == 0


@pytest.mark.asyncio
async def test_e2e_zhongyao_layer1a_still_works(client: AsyncClient, db: DbAdapter):
    """E2E: 中药 medicine + conflicting herbs → Layer 1a fires, Layer 1b skipped."""
    await _seed_herbs(db)
    await _insert_medicine(db, "降压药", "中药")
    await db.execute("COMMIT")

    resp = await client.post("/api/safety/check-v2", json={
        "herbs": ["甘草", "甘遂"], "medicines": ["降压药"],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["safe"] is False
    layer1b = [w for w in data["warnings"] if w["layer"] == 1 and "中西药交互" in w["title"]]
    assert len(layer1b) == 0
    layer1a = [w for w in data["warnings"] if w["layer"] == 1 and "十八反" in w["title"]]
    assert len(layer1a) >= 1


@pytest.mark.asyncio
async def test_e2e_default_drugclass_xiyao(client: AsyncClient, db: DbAdapter):
    """E2E: medicine not in table → defaults to 西药 → Layer 1b fires (backward compat)."""
    await _seed_herbs(db)
    await db.execute("COMMIT")

    resp = await client.post("/api/safety/check-v2", json={
        "herbs": ["当归"], "medicines": ["华法林"],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["safe"] is False
    layer1b = [w for w in data["warnings"] if w["layer"] == 1 and "中西药交互" in w["title"]]
    assert len(layer1b) >= 1


@pytest.mark.asyncio
async def test_e2e_mixed_drugclass(client: AsyncClient, db: DbAdapter):
    """E2E: mixed drugClass — 西药 triggers, 中成药 doesn't."""
    await _seed_herbs(db)
    await _insert_medicine(db, "华法林", "西药")
    await _insert_medicine(db, "降压药", "中成药")
    await db.execute("COMMIT")

    resp = await client.post("/api/safety/check-v2", json={
        "herbs": ["当归", "甘草"],
        "medicines": ["华法林", "降压药"],
    })
    assert resp.status_code == 200
    data = resp.json()
    layer1b = [w for w in data["warnings"] if w["layer"] == 1 and "中西药交互" in w["title"]]
    sources = [w["source"] for w in layer1b]
    assert any("R-01" in s for s in sources)
    assert not any("R-07" in s for s in sources)
