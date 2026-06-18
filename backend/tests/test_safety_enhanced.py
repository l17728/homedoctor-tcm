"""Enhanced safety tests — 3 critical features from medical expert review.

Feature 1: Cumulative toxicity check (multiple herbs sharing same toxic compound)
Feature 2: Liver/kidney disease special population checks
Feature 3: Emergency keywords expansion (29 → 63) + synonym matching
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.database import DbAdapter
from app.safety_keywords import EMERGENCY_KEYWORDS, SYNONYM_MAP, check_emergency_keywords


async def _seed_toxic_herbs(db: DbAdapter) -> None:
    """Seed herbs needed for cumulative toxicity and liver/kidney tests."""
    herbs = [
        {
            "id": "herb-fuzi-enh", "name": "附子", "aliases": "",
            "nature": "大热", "flavor": "辛,甘", "meridians": "心,肾,脾",
            "efficacy": "回阳救逆", "indications": "亡阳证",
            "contraindications": "孕妇禁用",
            "dosage_min_g": 3, "dosage_max_g": 15, "toxicity": "有毒",
            "category": "温里药", "properties": "{}",
        },
        {
            "id": "herb-chuanwu-enh", "name": "川乌", "aliases": "",
            "nature": "热", "flavor": "辛,苦", "meridians": "心,肝,肾,脾",
            "efficacy": "祛风除湿", "indications": "风寒湿痹",
            "contraindications": "孕妇禁用",
            "dosage_min_g": 1.5, "dosage_max_g": 3, "toxicity": "大毒",
            "category": "祛风湿药", "properties": "{}",
        },
        {
            "id": "herb-caowu-enh", "name": "草乌", "aliases": "",
            "nature": "热", "flavor": "辛,苦", "meridians": "肝,脾,肺",
            "efficacy": "祛风除湿", "indications": "风寒湿痹",
            "contraindications": "孕妇禁用",
            "dosage_min_g": 1.5, "dosage_max_g": 3, "toxicity": "大毒",
            "category": "祛风湿药", "properties": "{}",
        },
        {
            "id": "herb-leigongteng", "name": "雷公藤", "aliases": "",
            "nature": "寒", "flavor": "苦,辛", "meridians": "肝,肾",
            "efficacy": "祛风除湿", "indications": "类风湿关节炎",
            "contraindications": "肝肾功能不全者禁用",
            "dosage_min_g": 1, "dosage_max_g": 3, "toxicity": "大毒",
            "category": "祛风湿药", "properties": "{}",
        },
        {
            "id": "herb-guanmutong", "name": "关木通", "aliases": "",
            "nature": "寒", "flavor": "苦", "meridians": "心,小肠,膀胱",
            "efficacy": "利水通淋", "indications": "热淋涩痛",
            "contraindications": "肾功能不全者禁用",
            "dosage_min_g": 3, "dosage_max_g": 6, "toxicity": "有毒",
            "category": "利水渗湿药", "properties": "{}",
        },
        {
            "id": "herb-huangyaozi", "name": "黄药子", "aliases": "",
            "nature": "寒", "flavor": "苦", "meridians": "肺,肝",
            "efficacy": "化痰散结", "indications": "瘿瘤",
            "contraindications": "肝功能不全者慎用",
            "dosage_min_g": 3, "dosage_max_g": 9, "toxicity": "有毒",
            "category": "化痰药", "properties": "{}",
        },
        {
            "id": "herb-chaoshi-yixianhao", "name": "雪上一枝蒿", "aliases": "",
            "nature": "温", "flavor": "苦,辛", "meridians": "肝",
            "efficacy": "祛风止痛", "indications": "风湿疼痛",
            "contraindications": "孕妇禁用",
            "dosage_min_g": 0.5, "dosage_max_g": 1, "toxicity": "大毒",
            "category": "祛风湿药", "properties": "{}",
        },
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


# ===========================================================================
# Feature 1: Cumulative Toxicity Check
# ===========================================================================

@pytest.mark.asyncio
async def test_cumulative_toxicity_fuzi_chuanwu(client: AsyncClient, db: DbAdapter):
    """附子+川乌 share 乌头碱 → critical cumulative toxicity warning."""
    await _seed_toxic_herbs(db)
    await db.execute("COMMIT")
    resp = await client.post("/api/safety/check-v2", json={
        "herbs": ["附子", "川乌"],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["safe"] is False
    cumulative = [
        w for w in data["warnings"]
        if w["layer"] == 2 and "累积毒性" in w["title"]
    ]
    assert len(cumulative) >= 1
    assert cumulative[0]["severity"] == "critical"
    assert "乌头碱" in cumulative[0]["title"]
    assert "附子" in cumulative[0]["herbs"]
    assert "川乌" in cumulative[0]["herbs"]
    assert cumulative[0]["action"] == "禁止"


@pytest.mark.asyncio
async def test_cumulative_toxicity_three_herbs(client: AsyncClient, db: DbAdapter):
    """附子+川乌+草乌 all share 乌头碱 → one cumulative warning listing all three."""
    await _seed_toxic_herbs(db)
    await db.execute("COMMIT")
    resp = await client.post("/api/safety/check-v2", json={
        "herbs": ["附子", "川乌", "草乌"],
    })
    assert resp.status_code == 200
    data = resp.json()
    cumulative = [
        w for w in data["warnings"]
        if w["layer"] == 2 and "累积毒性" in w["title"]
    ]
    assert len(cumulative) >= 1
    assert "乌头碱" in cumulative[0]["title"]
    for herb in ["附子", "川乌", "草乌"]:
        assert herb in cumulative[0]["herbs"]


@pytest.mark.asyncio
async def test_cumulative_toxicity_single_herb_no_warning(client: AsyncClient, db: DbAdapter):
    """Single toxic herb (附子 alone) → no cumulative toxicity warning."""
    await _seed_toxic_herbs(db)
    await db.execute("COMMIT")
    resp = await client.post("/api/safety/check-v2", json={
        "herbs": ["附子"],
    })
    assert resp.status_code == 200
    data = resp.json()
    cumulative = [
        w for w in data["warnings"]
        if "累积毒性" in w.get("title", "")
    ]
    assert len(cumulative) == 0


@pytest.mark.asyncio
async def test_cumulative_toxicity_two_different_compounds_no_warning(client: AsyncClient, db: DbAdapter):
    """附子 (乌头碱) + 雷公藤 (雷公藤甲素) → no cumulative warning (different compounds)."""
    await _seed_toxic_herbs(db)
    await db.execute("COMMIT")
    resp = await client.post("/api/safety/check-v2", json={
        "herbs": ["附子", "雷公藤"],
    })
    assert resp.status_code == 200
    data = resp.json()
    cumulative = [
        w for w in data["warnings"]
        if "累积毒性" in w.get("title", "")
    ]
    assert len(cumulative) == 0


@pytest.mark.asyncio
async def test_cumulative_toxicity_madouling_group(client: AsyncClient, db: DbAdapter):
    """关木通 + 马兜铃 share 马兜铃酸 → cumulative warning."""
    await _seed_toxic_herbs(db)
    # 马兜铃 not seeded yet — cumulative check works on herb_names, not DB
    await db.execute("COMMIT")
    resp = await client.post("/api/safety/check-v2", json={
        "herbs": ["关木通", "马兜铃"],
    })
    assert resp.status_code == 200
    data = resp.json()
    cumulative = [
        w for w in data["warnings"]
        if w["layer"] == 2 and "累积毒性" in w["title"]
    ]
    assert len(cumulative) >= 1
    assert "马兜铃酸" in cumulative[0]["title"]


# ===========================================================================
# Feature 2: Liver/Kidney Disease Special Population
# ===========================================================================

@pytest.mark.asyncio
async def test_liver_disease_leigongteng(client: AsyncClient, db: DbAdapter):
    """Liver disease + 雷公藤 (hepatotoxic) → high warning."""
    await _seed_toxic_herbs(db)
    await db.execute("COMMIT")
    resp = await client.post("/api/safety/check-v2", json={
        "herbs": ["雷公藤"],
        "user_profile": {"liver_disease": True, "age": 45},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["safe"] is False
    liver_warnings = [
        w for w in data["warnings"]
        if w["layer"] == 3 and "肝病" in w["source"]
    ]
    assert len(liver_warnings) >= 1
    assert liver_warnings[0]["severity"] == "high"
    assert "雷公藤" in liver_warnings[0]["herbs"]
    assert liver_warnings[0]["action"] == "禁止"


@pytest.mark.asyncio
async def test_liver_disease_huangyaozi(client: AsyncClient, db: DbAdapter):
    """Liver disease + 黄药子 (hepatotoxic) → high warning."""
    await _seed_toxic_herbs(db)
    await db.execute("COMMIT")
    resp = await client.post("/api/safety/check-v2", json={
        "herbs": ["黄药子"],
        "user_profile": {"liver_disease": True, "age": 50},
    })
    assert resp.status_code == 200
    data = resp.json()
    liver_warnings = [
        w for w in data["warnings"]
        if w["layer"] == 3 and "肝病" in w["source"]
    ]
    assert len(liver_warnings) >= 1
    assert "黄药子" in liver_warnings[0]["herbs"]


@pytest.mark.asyncio
async def test_kidney_disease_guanmutong(client: AsyncClient, db: DbAdapter):
    """Kidney disease + 关木通 (nephrotoxic) → high warning."""
    await _seed_toxic_herbs(db)
    await db.execute("COMMIT")
    resp = await client.post("/api/safety/check-v2", json={
        "herbs": ["关木通"],
        "user_profile": {"kidney_disease": True, "age": 55},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["safe"] is False
    kidney_warnings = [
        w for w in data["warnings"]
        if w["layer"] == 3 and "肾病" in w["source"]
    ]
    assert len(kidney_warnings) >= 1
    assert kidney_warnings[0]["severity"] == "high"
    assert "关木通" in kidney_warnings[0]["herbs"]
    assert kidney_warnings[0]["action"] == "禁止"


@pytest.mark.asyncio
async def test_liver_disease_safe_herb_no_warning(client: AsyncClient, db: DbAdapter):
    """Liver disease + 黄芪 (not hepatotoxic) → no liver warning."""
    await _seed_toxic_herbs(db)
    await db.execute("COMMIT")
    resp = await client.post("/api/safety/check-v2", json={
        "herbs": ["黄芪"],
        "user_profile": {"liver_disease": True, "age": 45},
    })
    assert resp.status_code == 200
    data = resp.json()
    liver_warnings = [
        w for w in data["warnings"]
        if "肝病" in w.get("source", "")
    ]
    assert len(liver_warnings) == 0


@pytest.mark.asyncio
async def test_kidney_disease_safe_herb_no_warning(client: AsyncClient, db: DbAdapter):
    """Kidney disease + 黄芪 (not nephrotoxic) → no kidney warning."""
    await _seed_toxic_herbs(db)
    await db.execute("COMMIT")
    resp = await client.post("/api/safety/check-v2", json={
        "herbs": ["黄芪"],
        "user_profile": {"kidney_disease": True, "age": 55},
    })
    assert resp.status_code == 200
    data = resp.json()
    kidney_warnings = [
        w for w in data["warnings"]
        if "肾病" in w.get("source", "")
    ]
    assert len(kidney_warnings) == 0


@pytest.mark.asyncio
async def test_no_liver_kidney_disease_no_extra_warnings(client: AsyncClient, db: DbAdapter):
    """No liver/kidney disease in profile → no liver/kidney warnings even for toxic herbs."""
    await _seed_toxic_herbs(db)
    await db.execute("COMMIT")
    resp = await client.post("/api/safety/check-v2", json={
        "herbs": ["雷公藤", "关木通"],
        "user_profile": {"age": 40},
    })
    assert resp.status_code == 200
    data = resp.json()
    organ_warnings = [
        w for w in data["warnings"]
        if "肝病" in w.get("source", "") or "肾病" in w.get("source", "")
    ]
    assert len(organ_warnings) == 0


@pytest.mark.asyncio
async def test_both_liver_kidney_disease(client: AsyncClient, db: DbAdapter):
    """Both liver+kidney disease + 雷公藤+关木通 → both liver AND kidney warnings."""
    await _seed_toxic_herbs(db)
    await db.execute("COMMIT")
    resp = await client.post("/api/safety/check-v2", json={
        "herbs": ["雷公藤", "关木通"],
        "user_profile": {"liver_disease": True, "kidney_disease": True, "age": 60},
    })
    assert resp.status_code == 200
    data = resp.json()
    liver_warnings = [
        w for w in data["warnings"] if "肝病" in w.get("source", "")
    ]
    kidney_warnings = [
        w for w in data["warnings"] if "肾病" in w.get("source", "")
    ]
    assert len(liver_warnings) >= 1
    assert len(kidney_warnings) >= 1


# ===========================================================================
# Feature 3: Emergency Keywords Expansion + Synonym Matching
# ===========================================================================

def test_emergency_keywords_count_at_least_50():
    """EMERGENCY_KEYWORDS must have at least 50 entries (expanded from 29)."""
    assert len(EMERGENCY_KEYWORDS) >= 50


def test_emergency_keywords_no_duplicates():
    """EMERGENCY_KEYWORDS must not contain duplicates."""
    assert len(EMERGENCY_KEYWORDS) == len(set(EMERGENCY_KEYWORDS))


def test_new_keywords_present():
    """Spot-check several newly added keywords are present."""
    required_new = [
        "剧烈腹痛", "意识模糊", "无尿", "少尿", "心律不齐",
        "药物过敏", "食物中毒", "一氧化碳中毒", "急性喉炎",
        "胸口疼", "胸口闷", "人事不省", "吐血", "血尿",
        "半身不遂", "面瘫", "肢体麻木",
    ]
    for kw in required_new:
        assert kw in EMERGENCY_KEYWORDS, f"Missing keyword: {kw}"


def test_check_keyword_direct_match():
    """Direct keyword match works for new keywords."""
    assert "剧烈腹痛" in check_emergency_keywords("我突然剧烈腹痛，受不了了")
    assert "药物过敏" in check_emergency_keywords("我出现了药物过敏反应")
    assert "食物中毒" in check_emergency_keywords("怀疑食物中毒")
    assert "一氧化碳中毒" in check_emergency_keywords("可能是一氧化碳中毒")


def test_check_keyword_no_false_positive():
    """Normal text should not trigger emergency keywords."""
    assert check_emergency_keywords("黄芪有什么功效？") == []
    assert check_emergency_keywords("我最近有点乏力，想调理一下") == []


def test_synonym_match_xiong_kou_teng():
    """'胸口疼' (synonym of 胸痛) triggers emergency via synonym map."""
    matched = check_emergency_keywords("我胸口疼得厉害")
    assert len(matched) >= 1
    assert "胸痛" in matched


def test_synonym_match_chuan_bu_shang_qi():
    """'喘不上气' (synonym of 呼吸困难) triggers emergency."""
    matched = check_emergency_keywords("老人喘不上气了")
    assert "呼吸困难" in matched


def test_synonym_match_hun_mi_variants():
    """Multiple unconsciousness synonyms map to 昏迷."""
    assert "昏迷" in check_emergency_keywords("病人已经人事不省了")
    assert "昏迷" in check_emergency_keywords("他突然晕过去了")


def test_synonym_map_structure():
    """SYNONYM_MAP must have the 4 canonical entries from the spec."""
    assert "胸痛" in SYNONYM_MAP
    assert "呼吸困难" in SYNONYM_MAP
    assert "昏迷" in SYNONYM_MAP
    assert "抽搐" in SYNONYM_MAP
    for canonical, synonyms in SYNONYM_MAP.items():
        assert canonical in EMERGENCY_KEYWORDS, (
            f"Canonical keyword '{canonical}' must be in EMERGENCY_KEYWORDS"
        )


def test_synonym_no_duplicate_in_results():
    """If both direct and synonym match the same keyword, no duplicate."""
    # '喘不上气' is both a direct keyword and a synonym of '呼吸困难'
    matched = check_emergency_keywords("我喘不上气")
    assert matched.count("呼吸困难") <= 1
    assert matched.count("喘不上气") <= 1


@pytest.mark.asyncio
async def test_chat_new_emergency_keyword_intercepted(client: AsyncClient, auth_headers: dict):
    """New emergency keyword '剧烈腹痛' is intercepted in chat endpoint."""
    resp = await client.post(
        "/api/chat",
        json={"message": "我妈突然剧烈腹痛，怎么办？", "history": []},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["safety_warning"] is not None
    assert "120" in data["safety_warning"]
    assert data["model_used"] == "safety-layer"


@pytest.mark.asyncio
async def test_chat_synonym_keyword_intercepted(client: AsyncClient, auth_headers: dict):
    """Synonym '胸口疼' is intercepted in chat endpoint."""
    resp = await client.post(
        "/api/chat",
        json={"message": "我胸口疼，出汗，难受", "history": []},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["safety_warning"] is not None
    assert "120" in data["safety_warning"]
    assert data["model_used"] == "safety-layer"


@pytest.mark.asyncio
async def test_chat_poisoning_keyword_intercepted(client: AsyncClient, auth_headers: dict):
    """New poisoning keyword '煤气中毒' is intercepted in chat endpoint."""
    resp = await client.post(
        "/api/chat",
        json={"message": "怀疑家人煤气中毒了", "history": []},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["safety_warning"] is not None
    assert data["model_used"] == "safety-layer"


# ===========================================================================
# Database Migration: liver_disease / kidney_disease columns
# ===========================================================================

@pytest.mark.asyncio
async def test_user_profiles_has_liver_kidney_columns(db: DbAdapter):
    """user_profiles table must have liver_disease and kidney_disease columns."""
    cols = await db.query("PRAGMA table_info(user_profiles)")
    col_names = [c["name"] for c in cols]
    assert "liver_disease" in col_names
    assert "kidney_disease" in col_names


@pytest.mark.asyncio
async def test_user_profiles_liver_kidney_defaults(db: DbAdapter):
    """New user_profiles rows default liver_disease/kidney_disease to 0."""
    await db.execute(
        """INSERT OR REPLACE INTO user_profiles
           (user_id, display_name) VALUES ('test-organ-profile', '测试')"""
    )
    row = await db.query_one(
        "SELECT liver_disease, kidney_disease FROM user_profiles WHERE user_id = ?",
        ("test-organ-profile",),
    )
    assert row is not None
    assert row["liver_disease"] == 0
    assert row["kidney_disease"] == 0
