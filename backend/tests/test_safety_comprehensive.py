"""Comprehensive safety tests — 40+ tests covering all 5 layers.

Layer 1a: 中药×中药配伍禁忌 (十八反十九畏) — 10 tests
Layer 1b: 中西药交互检查 — 10 tests
Layer 2:  剂量范围检查 — 5 tests
Layer 3:  特殊人群检查 — 8 tests
Layer 5:  免责声明 — 3 tests
Integration — 5 tests
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.database import DbAdapter


async def _seed_extra_herbs(db: DbAdapter) -> None:
    """Seed additional herbs needed for comprehensive safety tests."""
    herbs = [
        {
            "id": "herb-wutou", "name": "附子", "aliases": "",
            "nature": "大热", "flavor": "辛,甘", "meridians": "心,肾,脾",
            "efficacy": "回阳救逆", "indications": "亡阳证",
            "contraindications": "孕妇禁用。阴虚阳亢者忌用",
            "dosage_min_g": 3, "dosage_max_g": 15, "toxicity": "有毒",
            "category": "温里药", "properties": "{}",
        },
        {
            "id": "herb-banxia", "name": "半夏", "aliases": "",
            "nature": "温", "flavor": "辛", "meridians": "脾,胃,肺",
            "efficacy": "燥湿化痰", "indications": "湿痰咳嗽",
            "contraindications": "阴虚燥咳者慎用",
            "dosage_min_g": 3, "dosage_max_g": 9, "toxicity": "有毒",
            "category": "化痰药", "properties": "{}",
        },
        {
            "id": "herb-gansui", "name": "甘遂", "aliases": "",
            "nature": "寒", "flavor": "苦", "meridians": "肺,肾,大肠",
            "efficacy": "泻水逐饮", "indications": "水肿胀满",
            "contraindications": "孕妇禁用。体虚者慎用",
            "dosage_min_g": 0.5, "dosage_max_g": 1.5, "toxicity": "有毒",
            "category": "泻下药", "properties": "{}",
        },
        {
            "id": "herb-lilu", "name": "藜芦", "aliases": "",
            "nature": "寒", "flavor": "辛,苦", "meridians": "肺,胃",
            "efficacy": "涌吐风痰", "indications": "中风痰壅",
            "contraindications": "孕妇禁用。细辛、芍药等反藜芦",
            "dosage_min_g": 0.3, "dosage_max_g": 0.9, "toxicity": "有毒",
            "category": "涌吐药", "properties": "{}",
        },
        {
            "id": "herb-renshen", "name": "人参", "aliases": "",
            "nature": "微温", "flavor": "甘,微苦", "meridians": "脾,肺,心",
            "efficacy": "大补元气", "indications": "气虚欲脱",
            "contraindications": "实证、热证者慎用",
            "dosage_min_g": 3, "dosage_max_g": 9, "toxicity": "无毒",
            "category": "补虚药", "properties": "{}",
        },
        {
            "id": "herb-liuhuang", "name": "硫磺", "aliases": "",
            "nature": "温", "flavor": "酸", "meridians": "肾,大肠",
            "efficacy": "外用解毒杀虫", "indications": "疥癣",
            "contraindications": "孕妇禁用",
            "dosage_min_g": 1.5, "dosage_max_g": 3, "toxicity": "有毒",
            "category": "外用药", "properties": "{}",
        },
        {
            "id": "herb-puxiao", "name": "朴硝", "aliases": "",
            "nature": "寒", "flavor": "咸,苦", "meridians": "胃,大肠",
            "efficacy": "泻下通便", "indications": "实热积滞",
            "contraindications": "孕妇禁用",
            "dosage_min_g": 6, "dosage_max_g": 12, "toxicity": "无毒",
            "category": "泻下药", "properties": "{}",
        },
        {
            "id": "herb-dingxiang", "name": "丁香", "aliases": "",
            "nature": "温", "flavor": "辛", "meridians": "脾,胃,肾",
            "efficacy": "温中降逆", "indications": "胃寒呕逆",
            "contraindications": "热证及阴虚内热者慎用",
            "dosage_min_g": 1, "dosage_max_g": 3, "toxicity": "无毒",
            "category": "温里药", "properties": "{}",
        },
        {
            "id": "herb-yujin", "name": "郁金", "aliases": "",
            "nature": "寒", "flavor": "辛,苦", "meridians": "肝,心,肺",
            "efficacy": "活血止痛", "indications": "胸胁刺痛",
            "contraindications": "孕妇慎用",
            "dosage_min_g": 3, "dosage_max_g": 10, "toxicity": "无毒",
            "category": "活血化瘀药", "properties": "{}",
        },
        {
            "id": "herb-wulingzhi", "name": "五灵脂", "aliases": "",
            "nature": "温", "flavor": "苦,甘", "meridians": "肝,脾",
            "efficacy": "活血散瘀", "indications": "瘀血阻滞",
            "contraindications": "孕妇慎用。血虚者慎用",
            "dosage_min_g": 3, "dosage_max_g": 10, "toxicity": "无毒",
            "category": "活血化瘀药", "properties": "{}",
        },
        {
            "id": "herb-chuanwu", "name": "川乌", "aliases": "",
            "nature": "热", "flavor": "辛,苦", "meridians": "心,肝,肾,脾",
            "efficacy": "祛风除湿", "indications": "风寒湿痹",
            "contraindications": "孕妇禁用",
            "dosage_min_g": 1.5, "dosage_max_g": 3, "toxicity": "大毒",
            "category": "祛风湿药", "properties": "{}",
        },
        {
            "id": "herb-mahuang", "name": "麻黄", "aliases": "",
            "nature": "温", "flavor": "辛,微苦", "meridians": "肺,膀胱",
            "efficacy": "发汗解表", "indications": "风寒感冒",
            "contraindications": "表虚自汗者慎用",
            "dosage_min_g": 2, "dosage_max_g": 10, "toxicity": "无毒",
            "category": "解表药", "properties": "{}",
        },
        {
            "id": "herb-wuweizi", "name": "五味子", "aliases": "",
            "nature": "温", "flavor": "酸,甘", "meridians": "肺,心,肾",
            "efficacy": "收敛固涩", "indications": "久嗽虚喘",
            "contraindications": "外有表邪内有实热者慎用",
            "dosage_min_g": 2, "dosage_max_g": 6, "toxicity": "无毒",
            "category": "收涩药", "properties": "{}",
        },
        {
            "id": "herb-gugen", "name": "葛根", "aliases": "",
            "nature": "凉", "flavor": "甘,辛", "meridians": "脾,胃",
            "efficacy": "解肌退热", "indications": "外感发热",
            "contraindications": "胃寒者慎用",
            "dosage_min_g": 10, "dosage_max_g": 15, "toxicity": "无毒",
            "category": "解表药", "properties": "{}",
        },
        {
            "id": "herb-yinxingye", "name": "银杏叶", "aliases": "",
            "nature": "平", "flavor": "甘,苦,涩", "meridians": "心,肺",
            "efficacy": "活血化瘀", "indications": "瘀血阻络",
            "contraindications": "孕妇慎用",
            "dosage_min_g": 9, "dosage_max_g": 12, "toxicity": "无毒",
            "category": "活血化瘀药", "properties": "{}",
        },
        {
            "id": "herb-shigao", "name": "石膏", "aliases": "",
            "nature": "大寒", "flavor": "甘,辛", "meridians": "肺,胃",
            "efficacy": "清热泻火", "indications": "壮热烦渴",
            "contraindications": "脾胃虚寒者慎用",
            "dosage_min_g": 15, "dosage_max_g": 60, "toxicity": "无毒",
            "category": "清热药", "properties": "{}",
        },
        {
            "id": "herb-dahuang", "name": "大黄", "aliases": "",
            "nature": "寒", "flavor": "苦", "meridians": "脾,胃,大肠,肝,心",
            "efficacy": "泻下攻积", "indications": "积滞便秘",
            "contraindications": "孕妇慎用。脾胃虚寒者慎用",
            "dosage_min_g": 3, "dosage_max_g": 15, "toxicity": "无毒",
            "category": "泻下药", "properties": "{}",
        },
        {
            "id": "herb-danshen", "name": "丹参", "aliases": "",
            "nature": "微寒", "flavor": "苦", "meridians": "心,心包,肝",
            "efficacy": "活血祛瘀", "indications": "月经不调",
            "contraindications": "孕妇慎用。不宜与藜芦同用",
            "dosage_min_g": 10, "dosage_max_g": 15, "toxicity": "无毒",
            "category": "活血化瘀药", "properties": "{}",
        },
        {
            "id": "herb-sanqi", "name": "三七", "aliases": "",
            "nature": "温", "flavor": "甘,微苦", "meridians": "肝,胃",
            "efficacy": "散瘀止血", "indications": "咯血吐血",
            "contraindications": "孕妇慎用",
            "dosage_min_g": 3, "dosage_max_g": 9, "toxicity": "无毒",
            "category": "止血药", "properties": "{}",
        },
        {
            "id": "herb-honghua", "name": "红花", "aliases": "",
            "nature": "温", "flavor": "辛", "meridians": "心,肝",
            "efficacy": "活血通经", "indications": "经闭痛经",
            "contraindications": "孕妇忌用",
            "dosage_min_g": 3, "dosage_max_g": 10, "toxicity": "无毒",
            "category": "活血化瘀药", "properties": "{}",
        },
        {
            "id": "herb-taoren", "name": "桃仁", "aliases": "",
            "nature": "平", "flavor": "苦,甘", "meridians": "心,肝,大肠",
            "efficacy": "活血祛瘀", "indications": "经闭痛经",
            "contraindications": "孕妇忌用",
            "dosage_min_g": 5, "dosage_max_g": 10, "toxicity": "无毒",
            "category": "活血化瘀药", "properties": "{}",
        },
        {
            "id": "herb-guizhi", "name": "桂枝", "aliases": "",
            "nature": "温", "flavor": "辛,甘", "meridians": "心,肺,膀胱",
            "efficacy": "发汗解肌", "indications": "风寒感冒",
            "contraindications": "温热病者慎用",
            "dosage_min_g": 3, "dosage_max_g": 10, "toxicity": "无毒",
            "category": "解表药", "properties": "{}",
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
# Layer 1a: 中药×中药配伍禁忌 (十八反十九畏) — 10 tests
# ===========================================================================

@pytest.mark.asyncio
async def test_18fan_wutou_banxia(client: AsyncClient, db: DbAdapter):
    """乌头(附子)+半夏 → critical (十八反)."""
    await _seed_extra_herbs(db)
    await db.execute("COMMIT")
    resp = await client.post("/api/safety/check-v2", json={"herbs": ["附子", "半夏"]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["safe"] is False
    layer1 = [w for w in data["warnings"] if w["layer"] == 1]
    assert any("十八反" in w["title"] for w in layer1)
    assert any(w["severity"] == "critical" for w in layer1)


@pytest.mark.asyncio
async def test_18fan_gancao_gansui(client: AsyncClient, db: DbAdapter):
    """甘草+甘遂 → critical (十八反)."""
    await _seed_extra_herbs(db)
    await db.execute("COMMIT")
    resp = await client.post("/api/safety/check-v2", json={"herbs": ["甘草", "甘遂"]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["safe"] is False
    layer1 = [w for w in data["warnings"] if w["layer"] == 1]
    assert any("十八反" in w["title"] for w in layer1)


@pytest.mark.asyncio
async def test_18fan_lilu_renshen(client: AsyncClient, db: DbAdapter):
    """藜芦+人参 → critical (十八反)."""
    await _seed_extra_herbs(db)
    await db.execute("COMMIT")
    resp = await client.post("/api/safety/check-v2", json={"herbs": ["藜芦", "人参"]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["safe"] is False
    layer1 = [w for w in data["warnings"] if w["layer"] == 1]
    assert any("十八反" in w["title"] for w in layer1)


@pytest.mark.asyncio
async def test_19wei_liuhuang_puxiao(client: AsyncClient, db: DbAdapter):
    """硫磺+朴硝 → critical (十九畏)."""
    await _seed_extra_herbs(db)
    await db.execute("COMMIT")
    resp = await client.post("/api/safety/check-v2", json={"herbs": ["硫磺", "朴硝"]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["safe"] is False
    layer1 = [w for w in data["warnings"] if w["layer"] == 1]
    assert any("十九畏" in w["title"] for w in layer1)


@pytest.mark.asyncio
async def test_19wei_dingxiang_yujin(client: AsyncClient, db: DbAdapter):
    """丁香+郁金 → critical (十九畏)."""
    await _seed_extra_herbs(db)
    await db.execute("COMMIT")
    resp = await client.post("/api/safety/check-v2", json={"herbs": ["丁香", "郁金"]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["safe"] is False
    layer1 = [w for w in data["warnings"] if w["layer"] == 1]
    assert any("十九畏" in w["title"] for w in layer1)


@pytest.mark.asyncio
async def test_19wei_renshen_wulingzhi(client: AsyncClient, db: DbAdapter):
    """人参+五灵脂 → critical (十九畏)."""
    await _seed_extra_herbs(db)
    await db.execute("COMMIT")
    resp = await client.post("/api/safety/check-v2", json={"herbs": ["人参", "五灵脂"]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["safe"] is False
    layer1 = [w for w in data["warnings"] if w["layer"] == 1]
    assert any("十九畏" in w["title"] for w in layer1)


@pytest.mark.asyncio
async def test_safe_two_herbs_no_warning(client: AsyncClient, db: DbAdapter):
    """Two safe herbs → no critical Layer 1 warnings."""
    await _seed_extra_herbs(db)
    await db.execute("COMMIT")
    resp = await client.post("/api/safety/check-v2", json={"herbs": ["黄芪", "葛根"]})
    assert resp.status_code == 200
    data = resp.json()
    layer1 = [w for w in data["warnings"] if w["layer"] == 1]
    assert len(layer1) == 0


@pytest.mark.asyncio
async def test_three_herbs_one_conflict(client: AsyncClient, db: DbAdapter):
    """Three-herb combo with one conflict → exactly one warning."""
    await _seed_extra_herbs(db)
    await db.execute("COMMIT")
    resp = await client.post("/api/safety/check-v2", json={"herbs": ["黄芪", "甘草", "甘遂"]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["safe"] is False
    layer1 = [w for w in data["warnings"] if w["layer"] == 1]
    assert len(layer1) >= 1


@pytest.mark.asyncio
async def test_same_herb_twice_no_warning(client: AsyncClient, db: DbAdapter):
    """Same herb listed twice → no self-conflict warning."""
    await _seed_extra_herbs(db)
    await db.execute("COMMIT")
    resp = await client.post("/api/safety/check-v2", json={"herbs": ["黄芪", "黄芪"]})
    assert resp.status_code == 200
    data = resp.json()
    layer1 = [w for w in data["warnings"] if w["layer"] == 1]
    assert len(layer1) == 0


@pytest.mark.asyncio
async def test_19wei_all_pairs(client: AsyncClient, db: DbAdapter):
    """All 10 十九畏 pairs produce critical warnings."""
    await _seed_extra_herbs(db)
    await db.execute("COMMIT")
    pairs = [
        ("硫磺", "朴硝"), ("水银", "砒霜"), ("狼毒", "密陀僧"),
        ("巴豆", "牵牛子"), ("丁香", "郁金"), ("牙硝", "三棱"),
        ("川乌", "犀角"), ("草乌", "犀角"), ("人参", "五灵脂"),
        ("官桂", "石脂"),
    ]
    for a, b in pairs:
        resp = await client.post("/api/safety/check-v2", json={"herbs": [a, b]})
        assert resp.status_code == 200
        data = resp.json()
        layer1 = [w for w in data["warnings"] if w["layer"] == 1 and "十九畏" in w["title"]]
        assert len(layer1) >= 1, f"Failed for {a}+{b}: no 十九畏 warning found"


# ===========================================================================
# Layer 1b: 中西药交互检查 — 10 tests
# ===========================================================================

@pytest.mark.asyncio
async def test_herb_drug_r01_warfarin_danggui(client: AsyncClient, db: DbAdapter):
    """华法林 + 当归 → critical (R-01)."""
    await _seed_extra_herbs(db)
    await db.execute("COMMIT")
    resp = await client.post("/api/safety/check-v2", json={
        "herbs": ["当归"], "medicines": ["华法林"],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["safe"] is False
    layer1b = [w for w in data["warnings"] if w["layer"] == 1 and "中西药交互" in w["title"]]
    assert len(layer1b) >= 1
    assert layer1b[0]["severity"] == "critical"


@pytest.mark.asyncio
async def test_herb_drug_r03_digoxin_mahuang(client: AsyncClient, db: DbAdapter):
    """地高辛 + 麻黄 → critical (R-03)."""
    await _seed_extra_herbs(db)
    await db.execute("COMMIT")
    resp = await client.post("/api/safety/check-v2", json={
        "herbs": ["麻黄"], "medicines": ["地高辛"],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["safe"] is False
    layer1b = [w for w in data["warnings"] if w["layer"] == 1 and "中西药交互" in w["title"]]
    assert len(layer1b) >= 1
    assert layer1b[0]["severity"] == "critical"


@pytest.mark.asyncio
async def test_herb_drug_r07_antihypertensive_gancao(client: AsyncClient, db: DbAdapter):
    """降压药 + 甘草 → warning (R-07)."""
    await _seed_extra_herbs(db)
    await db.execute("COMMIT")
    resp = await client.post("/api/safety/check-v2", json={
        "herbs": ["甘草"], "medicines": ["降压药"],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["safe"] is True
    layer1b = [w for w in data["warnings"] if w["layer"] == 1 and "中西药交互" in w["title"]]
    assert len(layer1b) >= 1


@pytest.mark.asyncio
async def test_herb_drug_r06_hypoglycemic_gugen(client: AsyncClient, db: DbAdapter):
    """降糖药 + 葛根 → warning (R-06)."""
    await _seed_extra_herbs(db)
    await db.execute("COMMIT")
    resp = await client.post("/api/safety/check-v2", json={
        "herbs": ["葛根"], "medicines": ["降糖药"],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["safe"] is True
    layer1b = [w for w in data["warnings"] if w["layer"] == 1 and "中西药交互" in w["title"]]
    assert len(layer1b) >= 1


@pytest.mark.asyncio
async def test_herb_drug_r05_statin_wuweizi(client: AsyncClient, db: DbAdapter):
    """他汀类 + 五味子 → critical (R-05)."""
    await _seed_extra_herbs(db)
    await db.execute("COMMIT")
    resp = await client.post("/api/safety/check-v2", json={
        "herbs": ["五味子"], "medicines": ["他汀类"],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["safe"] is False
    layer1b = [w for w in data["warnings"] if w["layer"] == 1 and "中西药交互" in w["title"]]
    assert len(layer1b) >= 1
    assert layer1b[0]["severity"] == "critical"


@pytest.mark.asyncio
async def test_herb_drug_r09_tetracycline_shigao(client: AsyncClient, db: DbAdapter):
    """四环素 + 石膏 → warning (R-09)."""
    await _seed_extra_herbs(db)
    await db.execute("COMMIT")
    resp = await client.post("/api/safety/check-v2", json={
        "herbs": ["石膏"], "medicines": ["四环素"],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["safe"] is True
    layer1b = [w for w in data["warnings"] if w["layer"] == 1 and "中西药交互" in w["title"]]
    assert len(layer1b) >= 1


@pytest.mark.asyncio
async def test_herb_drug_r10_iron_dahuang(client: AsyncClient, db: DbAdapter):
    """铁剂 + 大黄 → warning (R-10)."""
    await _seed_extra_herbs(db)
    await db.execute("COMMIT")
    resp = await client.post("/api/safety/check-v2", json={
        "herbs": ["大黄"], "medicines": ["铁剂"],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["safe"] is True
    layer1b = [w for w in data["warnings"] if w["layer"] == 1 and "中西药交互" in w["title"]]
    assert len(layer1b) >= 1


@pytest.mark.asyncio
async def test_herb_drug_r04_maoi_mahuang(client: AsyncClient, db: DbAdapter):
    """MAOI类药物 + 麻黄 → critical (R-04)."""
    await _seed_extra_herbs(db)
    await db.execute("COMMIT")
    resp = await client.post("/api/safety/check-v2", json={
        "herbs": ["麻黄"], "medicines": ["MAOI类药物"],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["safe"] is False
    layer1b = [w for w in data["warnings"] if w["layer"] == 1 and "中西药交互" in w["title"]]
    assert len(layer1b) >= 1
    assert layer1b[0]["severity"] == "critical"


@pytest.mark.asyncio
async def test_herb_drug_r08_antiplatelet_yinxingye(client: AsyncClient, db: DbAdapter):
    """抗血小板药 + 银杏叶 → critical (R-08)."""
    await _seed_extra_herbs(db)
    await db.execute("COMMIT")
    resp = await client.post("/api/safety/check-v2", json={
        "herbs": ["银杏叶"], "medicines": ["抗血小板药"],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["safe"] is False
    layer1b = [w for w in data["warnings"] if w["layer"] == 1 and "中西药交互" in w["title"]]
    assert len(layer1b) >= 1
    assert layer1b[0]["severity"] == "critical"


@pytest.mark.asyncio
async def test_herb_drug_safe_combo_ibuprofen_huangqi(client: AsyncClient, db: DbAdapter):
    """布洛芬 + 黄芪 → no herb-drug warning (safe combo)."""
    await _seed_extra_herbs(db)
    await db.execute("COMMIT")
    resp = await client.post("/api/safety/check-v2", json={
        "herbs": ["黄芪"], "medicines": ["布洛芬"],
    })
    assert resp.status_code == 200
    data = resp.json()
    layer1b = [w for w in data["warnings"] if w["layer"] == 1 and "中西药交互" in w["title"]]
    assert len(layer1b) == 0


# ===========================================================================
# Layer 2: 剂量范围检查 — 5 tests
# ===========================================================================

@pytest.mark.asyncio
async def test_dosage_over_max(client: AsyncClient, db: DbAdapter):
    """Dosage > max → high severity warning."""
    await _seed_extra_herbs(db)
    await db.execute("COMMIT")
    resp = await client.post("/api/safety/check-v2", json={
        "herbs": ["黄芪"],
        "dosages": {"黄芪": 50.0},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["safe"] is False
    layer2 = [w for w in data["warnings"] if w["layer"] == 2]
    assert len(layer2) >= 1
    assert layer2[0]["severity"] == "high"
    assert "超出" in layer2[0]["title"]


@pytest.mark.asyncio
async def test_dosage_under_min(client: AsyncClient, db: DbAdapter):
    """Dosage < min → low severity warning."""
    await _seed_extra_herbs(db)
    await db.execute("COMMIT")
    resp = await client.post("/api/safety/check-v2", json={
        "herbs": ["黄芪"],
        "dosages": {"黄芪": 2.0},
    })
    assert resp.status_code == 200
    data = resp.json()
    layer2 = [w for w in data["warnings"] if w["layer"] == 2]
    assert len(layer2) >= 1
    assert layer2[0]["severity"] == "low"
    assert "低于" in layer2[0]["title"]


@pytest.mark.asyncio
async def test_dosage_within_range(client: AsyncClient, db: DbAdapter):
    """Dosage within range → no Layer 2 warning."""
    await _seed_extra_herbs(db)
    await db.execute("COMMIT")
    resp = await client.post("/api/safety/check-v2", json={
        "herbs": ["黄芪"],
        "dosages": {"黄芪": 15.0},
    })
    assert resp.status_code == 200
    data = resp.json()
    layer2 = [w for w in data["warnings"] if w["layer"] == 2]
    assert len(layer2) == 0


@pytest.mark.asyncio
async def test_dosage_not_specified(client: AsyncClient, db: DbAdapter):
    """No dosage specified → no Layer 2 warning."""
    await _seed_extra_herbs(db)
    await db.execute("COMMIT")
    resp = await client.post("/api/safety/check-v2", json={"herbs": ["黄芪"]})
    assert resp.status_code == 200
    data = resp.json()
    layer2 = [w for w in data["warnings"] if w["layer"] == 2]
    assert len(layer2) == 0


@pytest.mark.asyncio
async def test_dosage_exact_max(client: AsyncClient, db: DbAdapter):
    """Dosage exactly at max → no warning (edge case)."""
    await _seed_extra_herbs(db)
    await db.execute("COMMIT")
    resp = await client.post("/api/safety/check-v2", json={
        "herbs": ["黄芪"],
        "dosages": {"黄芪": 30.0},
    })
    assert resp.status_code == 200
    data = resp.json()
    layer2 = [w for w in data["warnings"] if w["layer"] == 2]
    assert len(layer2) == 0


# ===========================================================================
# Layer 3: 特殊人群检查 — 8 tests
# ===========================================================================

@pytest.mark.asyncio
async def test_pregnant_taoren(client: AsyncClient, db: DbAdapter):
    """Pregnant + 桃仁 → high severity pregnancy warning."""
    await _seed_extra_herbs(db)
    await db.execute("COMMIT")
    resp = await client.post("/api/safety/check-v2", json={
        "herbs": ["桃仁"],
        "user_profile": {"is_pregnant": True, "age": 28},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["safe"] is False
    layer3 = [w for w in data["warnings"] if w["layer"] == 3]
    assert len(layer3) >= 1
    assert any("孕妇" in w["title"] for w in layer3)


@pytest.mark.asyncio
async def test_pregnant_safe_herb(client: AsyncClient, db: DbAdapter):
    """Pregnant + 黄芪 (safe for pregnancy) → no pregnancy warning."""
    await _seed_extra_herbs(db)
    await db.execute("COMMIT")
    resp = await client.post("/api/safety/check-v2", json={
        "herbs": ["黄芪"],
        "user_profile": {"is_pregnant": True, "age": 28},
    })
    assert resp.status_code == 200
    data = resp.json()
    layer3 = [w for w in data["warnings"] if w["layer"] == 3 and "孕妇" in w["title"]]
    assert len(layer3) == 0


@pytest.mark.asyncio
async def test_child_age_2_block(client: AsyncClient, db: DbAdapter):
    """Child age 2 → critical BLOCK (3岁以下)."""
    await _seed_extra_herbs(db)
    await db.execute("COMMIT")
    resp = await client.post("/api/safety/check-v2", json={
        "herbs": ["黄芪"],
        "user_profile": {"age": 2},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["safe"] is False
    layer3 = [w for w in data["warnings"] if w["layer"] == 3]
    assert any("3岁以下" in w["title"] or "婴幼儿" in w["detail"] for w in layer3)
    assert any(w["severity"] == "critical" for w in layer3)


@pytest.mark.asyncio
async def test_child_age_5_safety_note(client: AsyncClient, db: DbAdapter):
    """Child age 5 → child safety note."""
    await _seed_extra_herbs(db)
    await db.execute("COMMIT")
    resp = await client.post("/api/safety/check-v2", json={
        "herbs": ["黄芪"],
        "user_profile": {"age": 5},
    })
    assert resp.status_code == 200
    data = resp.json()
    layer3 = [w for w in data["warnings"] if w["layer"] == 3]
    assert any("儿童" in w["title"] for w in layer3)


@pytest.mark.asyncio
async def test_child_age_13_safety_note(client: AsyncClient, db: DbAdapter):
    """Child age 13 → child safety note."""
    await _seed_extra_herbs(db)
    await db.execute("COMMIT")
    resp = await client.post("/api/safety/check-v2", json={
        "herbs": ["黄芪"],
        "user_profile": {"age": 13},
    })
    assert resp.status_code == 200
    data = resp.json()
    layer3 = [w for w in data["warnings"] if w["layer"] == 3]
    assert any("儿童" in w["title"] for w in layer3)


@pytest.mark.asyncio
async def test_elderly_age_70_dosage_note(client: AsyncClient, db: DbAdapter):
    """Elderly age 70 → dosage adjustment note."""
    await _seed_extra_herbs(db)
    await db.execute("COMMIT")
    resp = await client.post("/api/safety/check-v2", json={
        "herbs": ["黄芪"],
        "user_profile": {"age": 70},
    })
    assert resp.status_code == 200
    data = resp.json()
    layer3 = [w for w in data["warnings"] if w["layer"] == 3]
    assert any("老年" in w["title"] for w in layer3)


@pytest.mark.asyncio
async def test_adult_age_40_no_population_warning(client: AsyncClient, db: DbAdapter):
    """Adult age 40 → no population warning."""
    await _seed_extra_herbs(db)
    await db.execute("COMMIT")
    resp = await client.post("/api/safety/check-v2", json={
        "herbs": ["黄芪"],
        "user_profile": {"age": 40},
    })
    assert resp.status_code == 200
    data = resp.json()
    layer3 = [w for w in data["warnings"] if w["layer"] == 3]
    assert len(layer3) == 0


@pytest.mark.asyncio
async def test_missing_user_profile_no_population_check(client: AsyncClient, db: DbAdapter):
    """Missing user_profile → no Layer 3 warnings."""
    await _seed_extra_herbs(db)
    await db.execute("COMMIT")
    resp = await client.post("/api/safety/check-v2", json={"herbs": ["黄芪"]})
    assert resp.status_code == 200
    data = resp.json()
    layer3 = [w for w in data["warnings"] if w["layer"] == 3]
    assert len(layer3) == 0


# ===========================================================================
# Layer 5: 免责声明 — 3 tests
# ===========================================================================

@pytest.mark.asyncio
async def test_disclaimer_always_present(client: AsyncClient, db: DbAdapter):
    """Disclaimer is always present regardless of input."""
    resp = await client.post("/api/safety/check-v2", json={"herbs": ["黄芪"]})
    assert resp.status_code == 200
    data = resp.json()
    assert "disclaimer" in data
    assert len(data["disclaimer"]) > 0


@pytest.mark.asyncio
async def test_disclaimer_content(client: AsyncClient, db: DbAdapter):
    """Disclaimer contains required phrases."""
    resp = await client.post("/api/safety/check-v2", json={"herbs": ["黄芪"]})
    data = resp.json()
    assert "仅供参考" in data["disclaimer"]
    assert "咨询" in data["disclaimer"] or "医师" in data["disclaimer"]


@pytest.mark.asyncio
async def test_disclaimer_not_duplicated(client: AsyncClient, db: DbAdapter):
    """Disclaimer is a single string, not duplicated."""
    resp = await client.post("/api/safety/check-v2", json={"herbs": ["甘草", "甘遂"]})
    data = resp.json()
    assert data["disclaimer"].count("仅供参考") == 1


# ===========================================================================
# Integration tests — 5 tests
# ===========================================================================

@pytest.mark.asyncio
async def test_multi_layer_trigger(client: AsyncClient, db: DbAdapter):
    """Multi-layer: 十八反 + overdosage + pregnancy → multiple warnings across layers."""
    await _seed_extra_herbs(db)
    await db.execute("COMMIT")
    resp = await client.post("/api/safety/check-v2", json={
        "herbs": ["甘草", "甘遂"],
        "user_profile": {"is_pregnant": True, "age": 28},
        "dosages": {"甘草": 50.0},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["safe"] is False
    layers_hit = set(w["layer"] for w in data["warnings"])
    assert 1 in layers_hit, "Layer 1 (十八反) should trigger"
    assert 2 in layers_hit, "Layer 2 (overdosage) should trigger"
    assert 3 in layers_hit, "Layer 3 (pregnancy) should trigger"


@pytest.mark.asyncio
async def test_safe_comprehensive_check(client: AsyncClient, db: DbAdapter):
    """Safe comprehensive check: all layers, no critical warnings."""
    await _seed_extra_herbs(db)
    await db.execute("COMMIT")
    resp = await client.post("/api/safety/check-v2", json={
        "herbs": ["黄芪", "葛根"],
        "medicines": ["布洛芬"],
        "user_profile": {"age": 40},
        "dosages": {"黄芪": 15.0},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["safe"] is True
    assert len(data["warnings"]) == 0


@pytest.mark.asyncio
async def test_empty_herbs_list(client: AsyncClient, db: DbAdapter):
    """Empty herbs list → safe with disclaimer."""
    resp = await client.post("/api/safety/check-v2", json={"herbs": []})
    assert resp.status_code == 200
    data = resp.json()
    assert data["safe"] is True
    assert len(data["warnings"]) == 0
    assert len(data["disclaimer"]) > 0


@pytest.mark.asyncio
async def test_unknown_herb_note(client: AsyncClient, db: DbAdapter):
    """Unknown herb → safe with herb listed in unknown_herbs."""
    await _seed_extra_herbs(db)
    await db.execute("COMMIT")
    resp = await client.post("/api/safety/check-v2", json={"herbs": ["灵芝仙草"]})
    assert resp.status_code == 200
    data = resp.json()
    assert "灵芝仙草" in data["unknown_herbs"]
    assert data["safe"] is True


@pytest.mark.asyncio
async def test_full_lifecycle_structure(client: AsyncClient, db: DbAdapter):
    """Full lifecycle: check → verify complete response structure."""
    await _seed_extra_herbs(db)
    await db.execute("COMMIT")
    resp = await client.post("/api/safety/check-v2", json={
        "herbs": ["甘草", "甘遂"],
        "medicines": ["华法林"],
        "user_profile": {"is_pregnant": True, "age": 30},
        "dosages": {"甘草": 20.0},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["safe"], bool)
    assert isinstance(data["warnings"], list)
    assert isinstance(data["disclaimer"], str)
    assert isinstance(data["checked_herbs"], list)
    assert isinstance(data["checked_medicines"], list)
    assert isinstance(data["unknown_herbs"], list)
    assert isinstance(data["unknown_medicines"], list)
    assert "甘草" in data["checked_herbs"]
    assert "甘遂" in data["checked_herbs"]
    assert "华法林" in data["checked_medicines"]
    for w in data["warnings"]:
        assert "layer" in w
        assert "severity" in w
        assert "title" in w
        assert "detail" in w
        assert "herbs" in w
        assert "action" in w
        assert "source" in w
        assert w["layer"] in (1, 2, 3, 4, 5)
        assert w["severity"] in ("critical", "high", "medium", "low")
