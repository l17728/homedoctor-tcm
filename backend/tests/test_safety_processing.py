"""炮制品归一化 + 儿童西药禁用 + 剂量上限 + chat 前置配伍安全（spec §15.2.4/§15.2.5/§15.3）.

覆盖：
- P0 炮制品归一化：制附子/法半夏/黑顺片/巴豆霜 按基原名参与全部硬规则匹配
- 儿童西药禁用清单（§15.2.4）：氟喹诺酮/四环素/氨基糖苷/可待因/阿司匹林
- 保健品剂量上限提示（§15.2.5）：鱼油 3g 等
- chat 链路前置五层安全（backend review P2-8）
- check-v2 输入上限（herbs/medicines ≤ 100）
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.database import DbAdapter


async def _seed_gansui(db: DbAdapter) -> None:
    """Seed 甘遂 (chat 提取依赖 herbs 表中存在同名记录)."""
    await db.execute(
        """INSERT OR IGNORE INTO herbs
           (id, name, aliases, nature, flavor, meridians, efficacy, indications,
            contraindications, dosage_min_g, dosage_max_g, toxicity, category, properties)
           VALUES ('herb-gansui-proc', '甘遂', '', '寒', '苦', '肺,肾,大肠',
                   '泻水逐饮', '水肿胀满', '孕妇禁用。体虚者慎用',
                   0.5, 1.5, '有毒', '泻下药', '{}')"""
    )
    await db.execute("COMMIT")


# ===========================================================================
# P0 炮制品归一化 — Layer 1a 十八反
# ===========================================================================

@pytest.mark.asyncio
async def test_zhifuzi_fabanxia_trigger_18fan_critical(client: AsyncClient):
    """制附子×法半夏 → 归一化为 附子×半夏 → 十八反 critical."""
    resp = await client.post("/api/safety/check-v2", json={
        "herbs": ["制附子", "法半夏"],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["safe"] is False
    layer1 = [w for w in data["warnings"] if w["layer"] == 1]
    critical_18fan = [
        w for w in layer1
        if "十八反" in w["title"] and w["severity"] == "critical"
    ]
    assert len(critical_18fan) >= 1
    affected = critical_18fan[0]["herbs"]
    assert any("制附子" in h for h in affected)
    assert any("法半夏" in h for h in affected)
    assert critical_18fan[0]["action"] == "禁止"


@pytest.mark.asyncio
async def test_processed_variant_keeps_low_toxicity_note(client: AsyncClient):
    """炮制品仍输出低级'炮制减毒提示'（原始提示不破坏）."""
    resp = await client.post("/api/safety/check-v2", json={
        "herbs": ["制附子", "法半夏"],
    })
    data = resp.json()
    notes = [
        w for w in data["warnings"]
        if w["severity"] == "low" and "炮制减毒" in w["title"]
    ]
    assert len(notes) >= 2  # 制附子 + 法半夏 各一条


@pytest.mark.asyncio
async def test_processed_variant_cumulative_toxicity(client: AsyncClient):
    """制附子+川乌 → 归一化后同含乌头碱 → 累积毒性 critical."""
    resp = await client.post("/api/safety/check-v2", json={
        "herbs": ["制附子", "川乌"],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["safe"] is False
    cumulative = [
        w for w in data["warnings"]
        if w["layer"] == 2 and "累积毒性" in w["title"]
    ]
    assert len(cumulative) >= 1
    assert "乌头碱" in cumulative[0]["title"]
    assert any("制附子" in h for h in cumulative[0]["herbs"])
    assert "川乌" in cumulative[0]["herbs"]


@pytest.mark.asyncio
async def test_processed_variant_and_base_no_self_conflict(client: AsyncClient):
    """制附子+附子 同时出现 → 归一化去重，不产生自身配伍冲突."""
    resp = await client.post("/api/safety/check-v2", json={
        "herbs": ["制附子", "附子"],
    })
    assert resp.status_code == 200
    data = resp.json()
    layer1 = [w for w in data["warnings"] if w["layer"] == 1]
    assert len(layer1) == 0


# ===========================================================================
# P0 炮制品归一化 — Layer 3 特殊人群
# ===========================================================================

@pytest.mark.asyncio
async def test_badoushuang_pregnancy_forbidden(client: AsyncClient):
    """巴豆霜 + 孕妇 → 归一化为巴豆 → 妊娠禁忌 high."""
    resp = await client.post("/api/safety/check-v2", json={
        "herbs": ["巴豆霜"],
        "user_profile": {"is_pregnant": True, "age": 28},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["safe"] is False
    pregnancy = [
        w for w in data["warnings"]
        if w["layer"] == 3 and "孕妇禁用" in w["title"]
    ]
    assert len(pregnancy) >= 1
    assert pregnancy[0]["severity"] == "high"
    assert any("巴豆霜" in h for h in pregnancy[0]["herbs"])
    assert pregnancy[0]["action"] == "禁止"


@pytest.mark.asyncio
async def test_heishunpian_child_3_toxicity(client: AsyncClient):
    """黑顺片 + 3岁儿童 → 归一化为附子 → 儿童慎用有毒药材 high."""
    resp = await client.post("/api/safety/check-v2", json={
        "herbs": ["黑顺片"],
        "user_profile": {"age": 3},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["safe"] is False
    child = [
        w for w in data["warnings"]
        if w["layer"] == 3 and "儿童慎用有毒药材" in w["title"]
    ]
    assert len(child) >= 1
    assert child[0]["severity"] == "high"
    assert any("黑顺片" in h for h in child[0]["herbs"])


# ===========================================================================
# 儿童西药禁用清单（spec §15.2.4）
# ===========================================================================

@pytest.mark.asyncio
async def test_child_levofloxacin_prohibited(client: AsyncClient):
    """左氧氟沙星 + 3岁儿童 → 氟喹诺酮类禁用 high."""
    resp = await client.post("/api/safety/check-v2", json={
        "medicines": ["左氧氟沙星"],
        "user_profile": {"age": 3},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["safe"] is False
    pediatric = [
        w for w in data["warnings"]
        if w["layer"] == 3 and "儿童禁用" in w["title"]
    ]
    assert len(pediatric) >= 1
    assert "氟喹诺酮类" in pediatric[0]["title"]
    assert pediatric[0]["severity"] == "high"
    assert "左氧氟沙星" in pediatric[0]["herbs"]
    assert pediatric[0]["action"] == "禁止"


@pytest.mark.asyncio
async def test_child_shastra_suffix_matched(client: AsyncClient):
    """名称含'沙星'（如 莫西沙星片）同样命中氟喹诺酮类."""
    resp = await client.post("/api/safety/check-v2", json={
        "medicines": ["莫西沙星片"],
        "user_profile": {"age": 10},
    })
    data = resp.json()
    assert any(
        "氟喹诺酮类" in w["title"]
        for w in data["warnings"] if w["layer"] == 3
    )


@pytest.mark.asyncio
async def test_child_aspirin_reye_syndrome(client: AsyncClient):
    """阿司匹林 + 10岁儿童 → 禁用并提示瑞氏综合征风险（<16岁）."""
    resp = await client.post("/api/safety/check-v2", json={
        "medicines": ["阿司匹林肠溶片"],
        "user_profile": {"age": 10},
    })
    data = resp.json()
    aspirin_warnings = [
        w for w in data["warnings"]
        if w["layer"] == 3 and "阿司匹林" in w["title"]
    ]
    assert len(aspirin_warnings) >= 1
    assert aspirin_warnings[0]["severity"] == "high"
    assert "瑞氏综合征" in aspirin_warnings[0]["detail"]


@pytest.mark.asyncio
async def test_child_tetracycline_age_boundary(client: AsyncClient):
    """多西环素：<8岁禁用（7岁命中），8岁不再命中四环素类规则."""
    resp = await client.post("/api/safety/check-v2", json={
        "medicines": ["多西环素"],
        "user_profile": {"age": 7},
    })
    data = resp.json()
    assert any(
        "四环素类" in w["title"]
        for w in data["warnings"] if w["layer"] == 3
    )

    resp8 = await client.post("/api/safety/check-v2", json={
        "medicines": ["多西环素"],
        "user_profile": {"age": 8},
    })
    data8 = resp8.json()
    assert not any(
        "四环素类" in w["title"]
        for w in data8["warnings"] if w["layer"] == 3
    )


@pytest.mark.asyncio
async def test_adult_not_affected_by_pediatric_rules(client: AsyncClient):
    """成人（40岁）服用左氧氟沙星/阿司匹林 → 不触发儿童禁用规则."""
    resp = await client.post("/api/safety/check-v2", json={
        "medicines": ["左氧氟沙星", "阿司匹林"],
        "user_profile": {"age": 40},
    })
    data = resp.json()
    assert not any("儿童禁用" in w["title"] for w in data["warnings"])


# ===========================================================================
# 保健品/成药剂量上限（spec §15.2.5）
# ===========================================================================

@pytest.mark.asyncio
async def test_yugou_dosage_upper_limit(client: AsyncClient):
    """鱼油 → Layer2 high 剂量上限提示（每日上限 3g）."""
    resp = await client.post("/api/safety/check-v2", json={
        "medicines": ["鱼油"],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["safe"] is False
    limits = [
        w for w in data["warnings"]
        if w["layer"] == 2 and "剂量上限" in w["title"]
    ]
    assert len(limits) >= 1
    assert limits[0]["severity"] == "high"
    assert "鱼油" in limits[0]["detail"]
    assert "3g" in limits[0]["detail"]
    assert "请核对说明书" in limits[0]["detail"]


@pytest.mark.asyncio
async def test_multiple_supplement_limits(client: AsyncClient):
    """维生素D（4000IU）+ 辅酶Q10（200mg）→ 各自命中一条上限提示."""
    resp = await client.post("/api/safety/check-v2", json={
        "medicines": ["维生素D滴剂", "Q10辅酶软胶囊"],
    })
    data = resp.json()
    details = " ".join(
        w["detail"] for w in data["warnings"]
        if w["layer"] == 2 and "剂量上限" in w["title"]
    )
    assert "4000IU" in details
    assert "200mg" in details


# ===========================================================================
# 输入上限（herbs/medicines ≤ 100）
# ===========================================================================

@pytest.mark.asyncio
async def test_check_v2_herbs_over_100_rejected(client: AsyncClient):
    """超过 100 味药材 → 422（中文错误信息）."""
    resp = await client.post("/api/safety/check-v2", json={
        "herbs": [f"药材{i}" for i in range(101)],
    })
    assert resp.status_code == 422
    assert "100项" in resp.text


@pytest.mark.asyncio
async def test_check_v2_medicines_over_100_rejected(client: AsyncClient):
    """超过 100 种药品 → 422."""
    resp = await client.post("/api/safety/check-v2", json={
        "medicines": [f"药品{i}" for i in range(101)],
    })
    assert resp.status_code == 422


# ===========================================================================
# chat 链路前置五层安全（backend review P2-8）
# ===========================================================================

@pytest.mark.asyncio
async def test_chat_combination_warning_prepended(client: AsyncClient, db: DbAdapter):
    """'甘草和甘遂能一起喝吗' → mock 回复前拼接 ⚠ 配伍安全警告（十八反）."""
    await _seed_gansui(db)
    resp = await client.post("/api/chat", json={
        "message": "甘草和甘遂能一起喝吗",
        "history": [],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["safety_warning"] is not None
    assert "十八反" in data["safety_warning"]
    assert data["reply"].startswith("⚠ 配伍安全警告")
    # 推理链路记录前置安全检查步骤
    assert any(t.get("step") == "safety_precheck" for t in data["reasoning_trace"])


@pytest.mark.asyncio
async def test_chat_safe_herb_question_no_combination_warning(client: AsyncClient):
    """单味药咨询（黄芪有什么功效）→ 无配伍警告，回复不带前缀."""
    resp = await client.post("/api/chat", json={
        "message": "黄芪有什么功效？",
        "history": [],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["safety_warning"] is None
    assert not data["reply"].startswith("⚠ 配伍安全警告")
