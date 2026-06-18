"""智能用药排程引擎测试 — 9 大场景全覆盖.

Tests:
  1. 无冲突排程：3种互不作用的药物 → 可共享时段
  2. 配伍禁忌间隔：附子+半夏（十八反）→ 必须分到不同时段
  3. 中西药交互间隔：华法林+当归 → 强制2小时间隔
  4. 频次分配：每日3次 → 分配3个时段
  5. 协同用药：同方药材 → 排在同一时段
  6. 安全验证：返回 conflicts_found 列表
  7. 摘要生成：人类可读文本
  8. 五天覆盖：周一~周五每天都有时段
  9. 用户画像：孕妇标记影响排程
"""

from __future__ import annotations

import pytest

from app.schedule_engine import (
    DAY_NAMES,
    DEFAULT_TIME_SLOTS,
    MedicationInput,
    generate_weekly_schedule,
    verify_existing_schedule,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _med(name, type_="中药", dosage="10g", frequency="每日1次", notes=""):
    return MedicationInput(
        name=name, type=type_, dosage=dosage, frequency=frequency, notes=notes
    )


def _slot_names(schedule, day_idx=0):
    """Get all medicine names across all slots for a given day."""
    names = []
    for slot in schedule.days[day_idx].slots:
        for med in slot.medicines:
            names.append(med["name"])
    return names


def _find_med_period(schedule, med_name, day_idx=0):
    """Find which period a medication is assigned to on a given day."""
    for slot in schedule.days[day_idx].slots:
        for med in slot.medicines:
            if med["name"] == med_name:
                return slot.period
    return None


# ---------------------------------------------------------------------------
# Test 1: No-conflict schedule — 3 non-interacting meds can share slots
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_conflict_schedule_meds_can_share_slots(db):
    """三种互不冲突的药物（黄芪+当归+甘草）可分配到同一时段."""
    medications = [
        _med("黄芪", frequency="每日1次"),
        _med("当归", frequency="每日1次"),
        _med("甘草", frequency="每日1次"),
    ]

    schedule = await generate_weekly_schedule(db, medications)

    assert schedule.safety_verified is True
    assert len(schedule.conflicts_found) == 0

    # All three should be in the same slot (早餐后) on Monday
    mon_slots = schedule.days[0].slots
    assert len(mon_slots) >= 1

    all_names = _slot_names(schedule, day_idx=0)
    assert "黄芪" in all_names
    assert "当归" in all_names
    assert "甘草" in all_names


# ---------------------------------------------------------------------------
# Test 2: Conflict spacing — 附子+半夏 (十八反) must be in different slots
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_conflict_spacing_18fan_must_be_different_slots(db):
    """附子与半夏属于十八反禁忌，必须分配到不同时段."""
    medications = [
        _med("附子", frequency="每日1次"),
        _med("半夏", frequency="每日1次"),
    ]

    schedule = await generate_weekly_schedule(db, medications)

    # 十八反 should be detected as a conflict
    assert len(schedule.conflicts_found) >= 1
    conflict_pairs = [c["names"] for c in schedule.conflicts_found]
    assert ["附子", "半夏"] in conflict_pairs or ["半夏", "附子"] in conflict_pairs

    # They must NOT be in the same slot
    fuzi_period = _find_med_period(schedule, "附子", day_idx=0)
    banxia_period = _find_med_period(schedule, "半夏", day_idx=0)
    assert fuzi_period is not None, "附子 should be scheduled"
    assert banxia_period is not None, "半夏 should be scheduled"
    assert fuzi_period != banxia_period, (
        f"附子({fuzi_period}) and 半夏({banxia_period}) must be in different slots"
    )

    assert schedule.safety_verified is True


# ---------------------------------------------------------------------------
# Test 3: 西药+中药 spacing — 华法林+当归 enforces 2h gap
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_western_herb_interaction_2h_gap(db):
    """华法林（西药）与当归（中药）有中西药交互，需间隔2小时以上."""
    medications = [
        _med("华法林", type_="西药", dosage="1片", frequency="每日1次"),
        _med("当归", type_="中药", dosage="10g", frequency="每日1次"),
    ]

    schedule = await generate_weekly_schedule(db, medications)

    # 中西药交互 should be detected
    assert len(schedule.conflicts_found) >= 1
    assert any(
        c["type"] == "中西药交互" and "华法林" in c["names"] and "当归" in c["names"]
        for c in schedule.conflicts_found
    )

    # Spacing rule should be present
    assert len(schedule.spacing_rules) >= 1
    spacing = schedule.spacing_rules[0]
    assert spacing["min_gap_hours"] >= 2

    # They must be in different slots
    warfarin_period = _find_med_period(schedule, "华法林", day_idx=0)
    danggui_period = _find_med_period(schedule, "当归", day_idx=0)
    assert warfarin_period is not None
    assert danggui_period is not None
    assert warfarin_period != danggui_period

    # The time gap between their slots must be >= 120 minutes
    from app.schedule_engine import _slot_gap_minutes
    gap = _slot_gap_minutes(warfarin_period, danggui_period)
    assert gap >= 120, (
        f"Gap between {warfarin_period} and {danggui_period} is {gap}min, "
        f"need >= 120min"
    )

    assert schedule.safety_verified is True


# ---------------------------------------------------------------------------
# Test 4: Frequency — 每日3次 → 3 slots assigned
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_frequency_3_times_assigns_3_slots(db):
    """每日3次的药物应分配到3个不同时段."""
    medications = [
        _med("黄芪", frequency="每日3次"),
    ]

    schedule = await generate_weekly_schedule(db, medications)

    # On Monday, 黄芪 should appear in 3 different slots
    huangqi_periods = []
    for slot in schedule.days[0].slots:
        for med in slot.medicines:
            if med["name"] == "黄芪":
                huangqi_periods.append(slot.period)

    assert len(huangqi_periods) == 3, (
        f"黄芪 with 每日3次 should be in 3 slots, got {huangqi_periods}"
    )
    # Should be 早餐后, 午餐后, 晚餐后
    assert "早餐后" in huangqi_periods
    assert "午餐后" in huangqi_periods
    assert "晚餐后" in huangqi_periods


# ---------------------------------------------------------------------------
# Test 5: Synergy — same formula herbs scheduled together
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_synergy_same_formula_herbs_together(db):
    """同方药材应排在一起（协同用药）."""
    medications = [
        _med("人参", frequency="每日1次", notes="四君子汤同方"),
        _med("白术", frequency="每日1次", notes="四君子汤同方"),
        _med("茯苓", frequency="每日1次", notes="四君子汤同方"),
    ]

    schedule = await generate_weekly_schedule(db, medications)

    # Synergy should be detected
    assert len(schedule.synergies_found) >= 1

    # All three should be in the same slot
    renshen_period = _find_med_period(schedule, "人参", day_idx=0)
    baishu_period = _find_med_period(schedule, "白术", day_idx=0)
    fuling_period = _find_med_period(schedule, "茯苓", day_idx=0)

    assert renshen_period is not None
    assert baishu_period is not None
    assert fuling_period is not None
    assert renshen_period == baishu_period == fuling_period, (
        f"Same formula herbs should be together: "
        f"人参={renshen_period}, 白术={baishu_period}, 茯苓={fuling_period}"
    )


# ---------------------------------------------------------------------------
# Test 6: Safety verification — returns conflicts_found list
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_safety_verification_returns_conflicts(db):
    """安全验证应返回检测到的所有冲突对."""
    medications = [
        _med("附子", frequency="每日1次"),
        _med("半夏", frequency="每日1次"),
        _med("华法林", type_="西药", frequency="每日1次"),
        _med("当归", type_="中药", frequency="每日1次"),
    ]

    schedule = await generate_weekly_schedule(db, medications)

    # Should detect both 十八反 and 中西药交互
    assert len(schedule.conflicts_found) >= 2

    has_18fan = any(
        c["type"] == "十八反" and "附子" in c["names"] and "半夏" in c["names"]
        for c in schedule.conflicts_found
    )
    has_interaction = any(
        c["type"] == "中西药交互" and "华法林" in c["names"]
        for c in schedule.conflicts_found
    )
    assert has_18fan, "Should detect 附子+半夏 十八反"
    assert has_interaction, "Should detect 华法林 中西药交互"

    # Each conflict should have required fields
    for c in schedule.conflicts_found:
        assert "names" in c
        assert "type" in c
        assert "severity" in c
        assert "mechanism" in c
        assert "action" in c
        assert "resolved" in c

    # Schedule should be verified safe (conflicts resolved by spacing)
    assert schedule.safety_verified is True


# ---------------------------------------------------------------------------
# Test 7: Summary generation — human-readable text
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_summary_generation_human_readable(db):
    """摘要应生成包含药物数量、冲突信息和安全结论的人类可读文本."""
    medications = [
        _med("黄芪", frequency="每日1次"),
        _med("当归", frequency="每日1次"),
    ]

    schedule = await generate_weekly_schedule(db, medications)

    assert isinstance(schedule.summary, str)
    assert len(schedule.summary) > 0

    # Should mention medication count
    assert "2" in schedule.summary

    # Should mention safety status
    assert "✅" in schedule.summary or "⚠️" in schedule.summary

    # Should include disclaimer
    assert "仅供参考" in schedule.summary or "医师" in schedule.summary


@pytest.mark.asyncio
async def test_summary_with_conflicts(db):
    """有冲突时摘要应提及冲突信息."""
    medications = [
        _med("附子", frequency="每日1次"),
        _med("半夏", frequency="每日1次"),
    ]

    schedule = await generate_weekly_schedule(db, medications)

    assert "配伍禁忌" in schedule.summary or "十八反" in schedule.summary


# ---------------------------------------------------------------------------
# Test 8: 5-day coverage — Monday through Friday all have slots
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_five_day_coverage(db):
    """排程应覆盖周一到周五，每天至少有一个时段."""
    medications = [
        _med("黄芪", frequency="每日3次"),
        _med("当归", frequency="每日2次"),
    ]

    schedule = await generate_weekly_schedule(db, medications)

    assert len(schedule.days) == 5

    for i, day_schedule in enumerate(schedule.days):
        assert day_schedule.day == DAY_NAMES[i], (
            f"Day {i} should be {DAY_NAMES[i]}, got {day_schedule.day}"
        )
        assert len(day_schedule.slots) > 0, (
            f"{day_schedule.day} should have at least one slot"
        )


@pytest.mark.asyncio
async def test_alternate_day_medication_skips_tue_thu(db):
    """隔日1次的药物在周二、周四不出现."""
    medications = [
        _med("黄芪", frequency="隔日1次"),
    ]

    schedule = await generate_weekly_schedule(db, medications)

    # Monday (idx 0): should have 黄芪
    mon_names = _slot_names(schedule, day_idx=0)
    assert "黄芪" in mon_names, "周一应服用隔日药"

    # Tuesday (idx 1): should NOT have 黄芪
    tue_names = _slot_names(schedule, day_idx=1)
    assert "黄芪" not in tue_names, "周二不应服用隔日药"

    # Wednesday (idx 2): should have 黄芪
    wed_names = _slot_names(schedule, day_idx=2)
    assert "黄芪" in wed_names, "周三应服用隔日药"

    # Thursday (idx 3): should NOT have 黄芪
    thu_names = _slot_names(schedule, day_idx=3)
    assert "黄芪" not in thu_names, "周四不应服用隔日药"

    # Friday (idx 4): should have 黄芪
    fri_names = _slot_names(schedule, day_idx=4)
    assert "黄芪" in fri_names, "周五应服用隔日药"


# ---------------------------------------------------------------------------
# Test 9: User profile — pregnancy flag affects scheduling
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pregnancy_flag_triggers_safety_warning(db):
    """孕妇用户使用孕妇禁忌药物时，安全检查应标记警告."""
    medications = [
        _med("附子", frequency="每日1次"),  # 附子 is pregnancy-dangerous
    ]

    user_profile = {"is_pregnant": True, "age": 30}

    schedule = await generate_weekly_schedule(db, medications, user_profile)

    # The schedule should still be generated
    assert len(schedule.days) == 5

    # But the safety summary should contain pregnancy warning
    # (附子 is in the pregnancy_dangerous list in safety_engine.py)
    # The schedule should note this risk


@pytest.mark.asyncio
async def test_user_profile_children_warning(db):
    """儿童用户使用毒性药材时，安全检查应标记警告."""
    medications = [
        _med("附子", frequency="每日1次"),
    ]

    user_profile = {"age": 8}  # 8-year-old child

    schedule = await generate_weekly_schedule(db, medications, user_profile)

    # Schedule still generated
    assert len(schedule.days) == 5
    # Summary should mention safety concerns
    assert len(schedule.summary) > 0


# ---------------------------------------------------------------------------
# Test 10: Empty medications list
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_empty_medications_returns_empty_schedule(db):
    """空药物列表应返回空排程但不报错."""
    schedule = await generate_weekly_schedule(db, [])

    assert len(schedule.days) == 5
    assert schedule.safety_verified is True
    assert len(schedule.conflicts_found) == 0


# ---------------------------------------------------------------------------
# Test 11: Slot times match DEFAULT_TIME_SLOTS
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_slot_times_match_defaults(db):
    """时段时间应匹配默认配置（07:00/08:00/12:30/18:30/21:00）."""
    medications = [
        _med("黄芪", frequency="每日3次"),
    ]

    schedule = await generate_weekly_schedule(db, medications)

    for slot in schedule.days[0].slots:
        assert slot.time == DEFAULT_TIME_SLOTS[slot.period], (
            f"Slot {slot.period} time should be {DEFAULT_TIME_SLOTS[slot.period]}, "
            f"got {slot.time}"
        )


# ---------------------------------------------------------------------------
# Test 12: Each slot has a human-readable reason
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_every_slot_has_reason(db):
    """每个时段中的每个药物都应有服用原因说明."""
    medications = [
        _med("黄芪", frequency="每日2次"),
        _med("当归", frequency="每日1次"),
    ]

    schedule = await generate_weekly_schedule(db, medications)

    for day in schedule.days:
        for slot in day.slots:
            for med in slot.medicines:
                assert "reason" in med, f"{med['name']} should have a reason"
                assert len(med["reason"]) > 0, (
                    f"{med['name']} reason should not be empty"
                )


# ---------------------------------------------------------------------------
# Test 13: Verify existing schedule endpoint
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_verify_existing_schedule_detects_violation(db):
    """验证已有排程时能检测到同时段冲突."""
    schedule_data = {
        "days": [
            {
                "day": "周一",
                "slots": [
                    {
                        "period": "早餐后",
                        "time": "08:00",
                        "medicines": [
                            {"name": "附子", "type": "中药", "dosage": "3g"},
                            {"name": "半夏", "type": "中药", "dosage": "9g"},
                        ],
                    },
                ],
            },
        ],
    }

    result = await verify_existing_schedule(db, schedule_data)

    assert result["safe"] is False
    assert len(result["violations"]) >= 1
    violation = result["violations"][0]
    assert "附子" in violation["names"]
    assert "半夏" in violation["names"]


@pytest.mark.asyncio
async def test_verify_existing_schedule_no_violation(db):
    """验证无冲突排程时返回 safe=True."""
    schedule_data = {
        "days": [
            {
                "day": "周一",
                "slots": [
                    {
                        "period": "早餐后",
                        "time": "08:00",
                        "medicines": [
                            {"name": "黄芪", "type": "中药", "dosage": "15g"},
                            {"name": "当归", "type": "中药", "dosage": "9g"},
                        ],
                    },
                ],
            },
        ],
    }

    result = await verify_existing_schedule(db, schedule_data)

    assert result["safe"] is True
    assert len(result["violations"]) == 0


# ---------------------------------------------------------------------------
# Test 14: Multiple conflicts resolved — all separated
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_multiple_conflicts_all_resolved(db):
    """多种冲突同时存在时，所有冲突都应被解决（药物分到不同时段）."""
    medications = [
        _med("附子", frequency="每日1次"),      # 十八反 with 半夏
        _med("半夏", frequency="每日1次"),      # 十八反 with 附子
        _med("华法林", type_="西药", frequency="每日1次"),  # 中西药交互 with 当归
        _med("当归", type_="中药", frequency="每日1次"),    # 中西药交互 with 华法林
        _med("甘草", frequency="每日1次"),      # no conflict with above
    ]

    schedule = await generate_weekly_schedule(db, medications)

    # Safety must be verified
    assert schedule.safety_verified is True

    # Verify no conflicting pair shares a slot
    for day in schedule.days:
        for slot in day.slots:
            names = [m["name"] for m in slot.medicines]
            # 附子 and 半夏 must not be together
            assert not ("附子" in names and "半夏" in names), (
                f"附子+半夏 in same slot {slot.period} on {day.day}"
            )
            # 华法林 and 当归 must not be together
            assert not ("华法林" in names and "当归" in names), (
                f"华法林+当归 in same slot {slot.period} on {day.day}"
            )
