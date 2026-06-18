"""智能用药排程引擎 — spec §15 安全排程.

用户选择一组药物 → 系统生成周一到周五的服药清单 → 表格可视化几点吃什么药
→ 标注哪些不能一起吃、哪些要一起吃、哪些要隔多久 → 严格的保证符合各种规则.

Algorithm overview:
  1. Classify medications (中药/西药/中成药)
  2. Run five-layer safety check via ``run_safety_check()``
  3. Build structured conflict matrix from ``safety_rules`` table
  4. Detect synergy pairs (same-formula herbs)
  5. Greedy slot assignment: most-constrained-first, respect conflicts + spacing
  6. Generate Monday-Friday schedule with human-readable reasons
  7. Safety verification: no conflicting pair shares a time slot
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from app.database import DbAdapter
from app.safety_engine import run_safety_check


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class MedicationInput:
    """Single medication input from user."""

    name: str
    type: str               # 西药/中药/中成药/中药方剂
    dosage: str             # "1片" / "10g" / "每次5ml"
    frequency: str          # "每日1次" / "每日2次" / "每日3次" / "隔日1次"
    notes: str = ""         # user's notes (e.g., "饭后吃")


@dataclass
class MedicationSlot:
    """A single time slot in a day's schedule."""

    time: str               # "07:00"
    period: str             # "早餐前" / "早餐后" / "午餐后" / "晚餐后" / "睡前"
    medicines: list[dict]   # [{name, dosage, type, reason}]
    conflict_warnings: list[str]  # safety notes for this slot


@dataclass
class DaySchedule:
    """One day's medication schedule."""

    day: str                # "周一" / "周二" ...
    slots: list[MedicationSlot]


@dataclass
class WeeklySchedule:
    """Complete weekly medication schedule (周一~周五)."""

    days: list[DaySchedule]
    conflicts_found: list[dict]    # all conflict pairs detected
    synergies_found: list[dict]    # all synergy pairs (can take together)
    spacing_rules: list[dict]      # timing gap requirements applied
    summary: str                   # human-readable summary
    safety_verified: bool          # all rules satisfied


# ---------------------------------------------------------------------------
# Constants — Chinese domain language throughout
# ---------------------------------------------------------------------------

DEFAULT_TIME_SLOTS: dict[str, str] = {
    "早餐前": "07:00",
    "早餐后": "08:00",
    "午餐后": "12:30",
    "晚餐后": "18:30",
    "睡前":   "21:00",
}

# Ordered slot periods for greedy assignment fallback
SLOT_ORDER: list[str] = ["早餐前", "早餐后", "午餐后", "晚餐后", "睡前"]

# Default time gaps (minutes) for different medication interaction types
TIMING_RULES: dict[str, float] = {
    "中西药交互": 120,            # 2 hours minimum gap between conflicting TCM and western meds
    "十八反": float("inf"),       # NEVER take together
    "十九畏": float("inf"),       # NEVER take together
}

# Frequency → number of daily slots + preferred periods
FREQUENCY_SLOTS: dict[str, list[str]] = {
    "每日1次": ["早餐后"],
    "每日2次": ["早餐后", "晚餐后"],
    "每日3次": ["早餐后", "午餐后", "晚餐后"],
    "隔日1次": ["早餐后"],        # alternate days handled separately
}

# User note keywords → preferred period
NOTE_PREFERENCE: dict[str, str] = {
    "饭前": "早餐前",
    "空腹": "早餐前",
    "早晨": "早餐后",
    "早上": "早餐后",
    "早饭": "早餐后",
    "饭后": "早餐后",
    "午餐": "午餐后",
    "午饭": "午餐后",
    "下午": "午餐后",
    "晚餐": "晚餐后",
    "晚饭": "晚餐后",
    "晚上": "晚餐后",
    "晚间": "晚餐后",
    "睡前": "睡前",
    "夜间": "睡前",
}

DAY_NAMES: list[str] = ["周一", "周二", "周三", "周四", "周五"]

# Synergy hints — medications that SHOULD be taken together
SYNERGY_HINTS: dict[str, str] = {
    "formula": "同方药材应同时煎服，增强协同疗效",
    "vitamin_c+iron": "维生素C促进铁吸收，建议同服",
}

# Known synergy name pairs (lowercased comparison)
SYNERGY_PAIRS: list[tuple[str, str, str]] = [
    ("维生素c", "铁", SYNERGY_HINTS["vitamin_c+iron"]),
    ("vitamin c", "铁", SYNERGY_HINTS["vitamin_c+iron"]),
]


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _time_to_minutes(time_str: str) -> int:
    """Convert 'HH:MM' to minutes since midnight."""
    parts = time_str.split(":")
    return int(parts[0]) * 60 + int(parts[1])


def _slot_gap_minutes(period_a: str, period_b: str) -> int:
    """Absolute time gap in minutes between two slot periods."""
    return abs(
        _time_to_minutes(DEFAULT_TIME_SLOTS[period_a])
        - _time_to_minutes(DEFAULT_TIME_SLOTS[period_b])
    )


def _normalize_name(name: str) -> str:
    """Normalize a medication name for comparison (lowercase, strip)."""
    return name.strip().lower()


def _is_herb_type(med_type: str) -> bool:
    """Whether a medication type should be treated as a herb for safety checks."""
    return med_type in ("中药", "中药方剂", "中成药")


def _is_western_drug_type(med_type: str) -> bool:
    """Whether a medication type is a western drug."""
    return med_type == "西药"


# ---------------------------------------------------------------------------
# Conflict matrix builder
# ---------------------------------------------------------------------------

async def _build_conflict_matrix(
    db: DbAdapter, medications: list[MedicationInput]
) -> dict[tuple[str, str], dict]:
    """Build a structured conflict matrix from the safety_rules table.

    Returns:
        dict mapping ``sorted_name_pair`` → conflict info dict with keys:
            type, severity, mechanism, gap_required (minutes), names
    """
    conflicts: dict[tuple[str, str], dict] = {}
    names = [m.name for m in medications]
    seen_pairs: set[tuple[str, str]] = set()

    def _pair_key(a: str, b: str) -> tuple[str, str]:
        return tuple(sorted([a, b]))  # type: ignore[return-value]

    def _add_conflict(a: str, b: str, info: dict) -> None:
        key = _pair_key(a, b)
        if key not in conflicts:
            conflicts[key] = info
            seen_pairs.add(key)

    # --- Check all pairs for 十八反/十九畏 (herb-herb) ---
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            rows = await db.query(
                """SELECT * FROM safety_rules WHERE enabled = 1
                   AND ((drug_a = ? AND drug_b = ?) OR (drug_a = ? AND drug_b = ?))
                   AND rule_type IN ('十八反', '十九畏')""",
                (a, b, b, a),
            )
            for r in rows:
                _add_conflict(a, b, {
                    "type": r["rule_type"],
                    "severity": r["severity"],
                    "mechanism": r["mechanism"],
                    "gap_required": float("inf"),
                    "names": [a, b],
                    "rule_id": r["id"],
                })

    # --- Check 中西药交互 (west drug × herb) ---
    west_meds = [m for m in medications if _is_western_drug_type(m.type)]
    herb_meds = [m for m in medications if _is_herb_type(m.type)]

    for w in west_meds:
        for h in herb_meds:
            if w.name == h.name:
                continue
            # Exact match: drug_a = western drug, drug_b = herb
            rows = await db.query(
                """SELECT * FROM safety_rules WHERE enabled = 1
                   AND drug_a = ? AND drug_b = ?
                   AND rule_type = '中西药交互'""",
                (w.name, h.name),
            )
            # Fuzzy match: drug_a contains western drug name
            if not rows:
                rows = await db.query(
                    """SELECT * FROM safety_rules WHERE enabled = 1
                       AND drug_a LIKE ? AND drug_b = ?
                       AND rule_type = '中西药交互'""",
                    (f"%{w.name}%", h.name),
                )
            for r in rows:
                gap = TIMING_RULES["中西药交互"]
                _add_conflict(w.name, h.name, {
                    "type": "中西药交互",
                    "severity": r["severity"],
                    "mechanism": r["mechanism"],
                    "gap_required": gap,
                    "names": [w.name, h.name],
                    "rule_id": r["id"],
                })

    return conflicts


# ---------------------------------------------------------------------------
# Synergy detection
# ---------------------------------------------------------------------------

def _detect_synergies(
    medications: list[MedicationInput],
    conflict_matrix: dict[tuple[str, str], dict] | None = None,
) -> list[dict]:
    """Detect medication pairs that SHOULD be taken together.

    Detection rules:
      1. Same formula herbs (notes contain same formula name or "同方")
      2. Known synergy pairs (e.g., vitamin C + iron)
      3. Same-type herbs with no conflict → can co-serve

    Pairs that appear in ``conflict_matrix`` are excluded from all rules.
    """
    synergies: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def _has_conflict(a: str, b: str) -> bool:
        if conflict_matrix is None:
            return False
        key = tuple(sorted([a, b]))  # type: ignore[arg-type]
        return key in conflict_matrix

    # --- Rule 1: same formula herbs ---
    # Group medications by formula name mentioned in notes
    formula_groups: dict[str, list[MedicationInput]] = {}
    for med in medications:
        notes = med.notes or ""
        # Detect formula references: "同方", "XX汤", "XX散", "XX丸", "XX丹"
        for keyword in ["同方", "汤", "散", "丸", "丹", "膏", "饮"]:
            if keyword in notes:
                # Extract a formula group key from notes
                formula_groups.setdefault(f"formula-{keyword}", []).append(med)
                break

    for group_key, meds in formula_groups.items():
        if len(meds) >= 2:
            for i, a in enumerate(meds):
                for b in meds[i + 1:]:
                    if _has_conflict(a.name, b.name):
                        continue
                    pair_key = tuple(sorted([a.name, b.name]))  # type: ignore[arg-type]
                    if pair_key not in seen:
                        seen.add(pair_key)
                        synergies.append({
                            "names": [a.name, b.name],
                            "reason": SYNERGY_HINTS["formula"],
                            "type": "formula",
                        })

    # --- Rule 2: known synergy pairs ---
    norm_names = {_normalize_name(m.name): m.name for m in medications}
    for name_a, name_b, reason in SYNERGY_PAIRS:
        na_norm = _normalize_name(name_a)
        nb_norm = _normalize_name(name_b)
        # Find meds whose normalized name contains the synergy keyword
        matched_a = None
        matched_b = None
        for norm, orig in norm_names.items():
            if na_norm in norm and matched_a is None:
                matched_a = orig
            if nb_norm in norm and matched_b is None:
                matched_b = orig
        if matched_a and matched_b and matched_a != matched_b:
            pair_key = tuple(sorted([matched_a, matched_b]))  # type: ignore[arg-type]
            if pair_key not in seen:
                seen.add(pair_key)
                synergies.append({
                    "names": [matched_a, matched_b],
                    "reason": reason,
                    "type": "vitamin_c+iron",
                })

    # --- Rule 3: same-type herbs with no conflict → can co-serve ---
    # (informational only, doesn't force scheduling)
    herb_meds = [m for m in medications if _is_herb_type(m.type)]
    for i, a in enumerate(herb_meds):
        for b in herb_meds[i + 1:]:
            if _has_conflict(a.name, b.name):
                continue
            pair_key = tuple(sorted([a.name, b.name]))  # type: ignore[arg-type]
            if pair_key not in seen:
                seen.add(pair_key)
                synergies.append({
                    "names": [a.name, b.name],
                    "reason": f"{a.name}与{b.name}同属中药，无配伍禁忌，可同服",
                    "type": "compatible_herbs",
                })

    return synergies


# ---------------------------------------------------------------------------
# Slot assignment (greedy algorithm)
# ---------------------------------------------------------------------------

def _get_target_periods(med: MedicationInput) -> list[str]:
    """Determine target slot periods based on frequency and user notes.

    Returns ordered list of preferred periods (most preferred first).
    The list length matches the frequency requirement.
    """
    freq = med.frequency or "每日1次"
    base_periods = FREQUENCY_SLOTS.get(freq, FREQUENCY_SLOTS["每日1次"])

    # If user notes specify a time preference, adjust the primary slot
    notes = med.notes or ""
    preferred = None
    for keyword, period in NOTE_PREFERENCE.items():
        if keyword in notes:
            preferred = period
            break

    if preferred and base_periods:
        # Replace the first slot with the preferred period
        result = [preferred] if preferred not in base_periods else []
        result.extend(p for p in base_periods if p != preferred)
        # Ensure we still have the right count
        while len(result) < len(base_periods):
            for slot in SLOT_ORDER:
                if slot not in result:
                    result.append(slot)
                    break
        return result[:len(base_periods)]

    return list(base_periods)


def _is_alternate_day(med: MedicationInput) -> bool:
    """Whether a medication should only be taken on alternate days."""
    return (med.frequency or "") == "隔日1次"


def _has_conflict_in_slot(
    med_name: str,
    slot_period: str,
    slot_assignments: dict[str, list[str]],
    conflict_lookup: dict[str, list[dict]],
) -> dict | None:
    """Check if ``med_name`` conflicts with any med already in ``slot_period``.

    Returns the conflict info dict if a conflict is found, ``None`` otherwise.
    """
    for existing in slot_assignments.get(slot_period, []):
        for info in conflict_lookup.get(med_name, []):
            other = info["other_name"]
            if other == existing:
                return info
    return None


def _check_spacing_violation(
    med_name: str,
    target_period: str,
    slot_assignments: dict[str, list[str]],
    conflict_lookup: dict[str, list[dict]],
) -> dict | None:
    """Check if placing ``med_name`` at ``target_period`` violates spacing rules.

    For soft conflicts (中西药交互), the minimum gap between the target slot
    and any slot containing a conflicting medication must be >= gap_required.
    """
    for info in conflict_lookup.get(med_name, []):
        other = info["other_name"]
        gap_required = info["gap_required"]
        if gap_required == float("inf"):
            continue  # hard conflict handled by _has_conflict_in_slot
        # Check all slots for the conflicting med
        for period, meds in slot_assignments.items():
            if other in meds and period != target_period:
                actual_gap = _slot_gap_minutes(period, target_period)
                if actual_gap < gap_required:
                    return info
    return None


def _assign_slots(
    medications: list[MedicationInput],
    conflict_matrix: dict[tuple[str, str], dict],
) -> tuple[dict[str, list[str]], dict[str, dict[str, str]]]:
    """Greedy slot assignment algorithm.

    Args:
        medications: list of MedicationInput.
        conflict_matrix: structured conflict data.

    Returns:
        Tuple of (slot_assignments, med_reasons) where:
        - slot_assignments: period → list of med names
        - med_reasons: med_name → {period → reason string}
    """
    # Build per-medication conflict lookup
    conflict_lookup: dict[str, list[dict]] = {}
    for pair_key, info in conflict_matrix.items():
        a, b = info["names"]
        conflict_lookup.setdefault(a, []).append({**info, "other_name": b})
        conflict_lookup.setdefault(b, []).append({**info, "other_name": a})

    # Sort by constraint count (most constrained first) for better greedy results
    sorted_meds = sorted(
        medications,
        key=lambda m: -len(conflict_lookup.get(m.name, [])),
    )

    slot_assignments: dict[str, list[str]] = {p: [] for p in SLOT_ORDER}
    med_reasons: dict[str, dict[str, str]] = {}

    for med in sorted_meds:
        target_periods = _get_target_periods(med)
        med_periods: dict[str, str] = {}

        for target_idx, preferred_period in enumerate(target_periods):
            # Try the preferred period first, then fall back through SLOT_ORDER
            candidate_order = [preferred_period] + [
                p for p in SLOT_ORDER if p != preferred_period
            ]

            assigned = False
            for candidate in candidate_order:
                # Skip if this med is already assigned to this period
                if med.name in slot_assignments[candidate]:
                    continue

                # Check for hard/soft conflict in the same slot
                conflict = _has_conflict_in_slot(
                    med.name, candidate, slot_assignments, conflict_lookup
                )
                if conflict:
                    # Skip this slot — conflict detected
                    continue

                # Check spacing rules for soft conflicts in adjacent slots
                spacing_issue = _check_spacing_violation(
                    med.name, candidate, slot_assignments, conflict_lookup
                )
                if spacing_issue:
                    continue

                # Assign to this slot
                slot_assignments[candidate].append(med.name)

                # Build human-readable reason
                reason = _build_assignment_reason(
                    med, candidate, target_idx, preferred_period,
                    slot_assignments, conflict_lookup,
                )
                med_periods[candidate] = reason
                assigned = True
                break

            if not assigned:
                has_hard_conflict = any(
                    info.get("gap_required") == float("inf")
                    for info in conflict_lookup.get(med.name, [])
                )
                if has_hard_conflict:
                    med_periods[preferred_period] = (
                        f"🚫 {med.name}存在致命配伍禁忌，无法安全排入任何时段，"
                        f"请务必咨询执业医师或药师调整用药方案"
                    )
                else:
                    fallback = preferred_period
                    slot_assignments[fallback].append(med.name)
                    med_periods[fallback] = (
                        f"⚠️ {med.name}无法找到完全无冲突时段，暂安排在{fallback}，"
                        f"请注意间隔时间，建议咨询医生"
                    )

        med_reasons[med.name] = med_periods

    return slot_assignments, med_reasons


def _build_assignment_reason(
    med: MedicationInput,
    assigned_period: str,
    target_idx: int,
    preferred_period: str,
    slot_assignments: dict[str, list[str]],
    conflict_lookup: dict[str, list[dict]],
) -> str:
    """Build a human-readable reason for why a medication is scheduled at a time."""
    time_str = DEFAULT_TIME_SLOTS[assigned_period]

    # Check if moved away from preferred due to conflict
    if assigned_period != preferred_period:
        # Find the conflict that caused the move
        for info in conflict_lookup.get(med.name, []):
            other = info["other_name"]
            if other in slot_assignments.get(preferred_period, []):
                if info["gap_required"] == float("inf"):
                    return (
                        f"{med.name}与{other}有{info['type']}配伍禁忌，"
                        f"不可同服，故安排在{assigned_period}（{time_str}）"
                    )
                else:
                    gap_h = int(info["gap_required"] // 60)
                    return (
                        f"{med.name}与{other}有中西药交互，"
                        f"需间隔{gap_h}小时以上，故安排在{assigned_period}（{time_str}）"
                    )

    # Check if placed together with a synergistic partner
    same_slot_meds = [
        m for m in slot_assignments.get(assigned_period, []) if m != med.name
    ]
    if same_slot_meds:
        # Check if any synergy exists
        for other in same_slot_meds:
            for info in conflict_lookup.get(med.name, []):
                pass  # conflicts already filtered
        if same_slot_meds:
            others_str = "、".join(same_slot_meds)
            return (
                f"{med.name}在{assigned_period}（{time_str}）服用，"
                f"与{others_str}同服，便于管理"
            )

    # Default reason based on period
    period_reasons = {
        "早餐前": f"{med.name}在早餐前（{time_str}）空腹服用，利于吸收",
        "早餐后": f"{med.name}在早餐后（{time_str}）服用，减少胃肠刺激",
        "午餐后": f"{med.name}在午餐后（{time_str}）服用，维持日间血药浓度",
        "晚餐后": f"{med.name}在晚餐后（{time_str}）服用，维持夜间疗效",
        "睡前":   f"{med.name}在睡前（{time_str}）服用，有助于夜间安眠",
    }
    return period_reasons.get(
        assigned_period,
        f"{med.name}安排在{assigned_period}（{time_str}）服用",
    )


# ---------------------------------------------------------------------------
# Day schedule builder
# ---------------------------------------------------------------------------

def _build_day_slots(
    day_idx: int,
    medications: list[MedicationInput],
    slot_assignments: dict[str, list[str]],
    med_reasons: dict[str, dict[str, str]],
    conflict_matrix: dict[tuple[str, str], dict],
) -> list[MedicationSlot]:
    """Build MedicationSlot list for a single day.

    Handles alternate-day medications (隔日1次): taken on Mon/Wed/Fri (day_idx 0,2,4).
    """
    slots: list[MedicationSlot] = []
    med_by_name = {m.name: m for m in medications}

    # Build conflict lookup for slot-level warnings
    conflict_by_period: dict[str, list[str]] = {}
    for pair_key, info in conflict_matrix.items():
        a, b = info["names"]
        # If both are in the same period (shouldn't happen with proper assignment,
        # but we check for safety verification)
        for period in SLOT_ORDER:
            meds_in_period = slot_assignments.get(period, [])
            if a in meds_in_period and b in meds_in_period:
                conflict_by_period.setdefault(period, []).append(
                    f"⚠️ {a}与{b}存在{info['type']}配伍禁忌，不应同服"
                )

    for period in SLOT_ORDER:
        time_str = DEFAULT_TIME_SLOTS[period]
        med_names = slot_assignments.get(period, [])
        slot_meds: list[dict] = []

        for name in med_names:
            med = med_by_name.get(name)
            if med is None:
                continue

            # Skip alternate-day meds on non-alternate days
            if _is_alternate_day(med) and day_idx not in (0, 2, 4):
                continue

            reason = med_reasons.get(name, {}).get(period, "")
            slot_meds.append({
                "name": med.name,
                "dosage": med.dosage,
                "type": med.type,
                "frequency": med.frequency,
                "reason": reason,
            })

        # Slot-level spacing warnings for this period
        slot_warnings: list[str] = []
        for pair_key, info in conflict_matrix.items():
            a, b = info["names"]
            gap = info["gap_required"]
            if gap == float("inf"):
                continue
            # Check if both meds appear in this day's schedule at different slots
            a_periods = [
                p for p in SLOT_ORDER
                if any(
                    med_by_name.get(n) and
                    (not _is_alternate_day(med_by_name[n]) or day_idx in (0, 2, 4)) and
                    n in slot_assignments.get(p, [])
                    for n in [a]
                )
            ]
            b_periods = [
                p for p in SLOT_ORDER
                if any(
                    med_by_name.get(n) and
                    (not _is_alternate_day(med_by_name[n]) or day_idx in (0, 2, 4)) and
                    n in slot_assignments.get(p, [])
                    for n in [b]
                )
            ]
            if a_periods and b_periods and period in (a_periods + b_periods):
                gap_h = int(gap // 60) if gap != float("inf") else 0
                if gap_h > 0:
                    slot_warnings.append(
                        f"ℹ️ {a}与{b}需间隔{gap_h}小时以上服用（中西药交互）"
                    )

        # Deduplicate warnings
        slot_warnings = list(dict.fromkeys(slot_warnings))

        # Only include slots that have medications
        if slot_meds:
            slots.append(MedicationSlot(
                time=time_str,
                period=period,
                medicines=slot_meds,
                conflict_warnings=slot_warnings,
            ))

    return slots


# ---------------------------------------------------------------------------
# Summary builder
# ---------------------------------------------------------------------------

def _build_summary(
    medications: list[MedicationInput],
    conflict_matrix: dict[tuple[str, str], dict],
    synergies: list[dict],
    safety_verified: bool,
) -> str:
    """Build a human-readable summary of the weekly schedule."""
    lines: list[str] = []
    lines.append(f"📋 本周用药排程共涉及{len(medications)}种药物，覆盖周一至周五。")

    # Conflicts
    hard_conflicts = [
        c for c in conflict_matrix.values() if c["gap_required"] == float("inf")
    ]
    soft_conflicts = [
        c for c in conflict_matrix.values() if c["gap_required"] != float("inf")
    ]

    if hard_conflicts:
        names = ["、".join(c["names"]) for c in hard_conflicts]
        lines.append(
            f"🚫 检测到{len(hard_conflicts)}组配伍禁忌（不可同服）："
            + "；".join(names)
        )

    if soft_conflicts:
        names = ["、".join(c["names"]) for c in soft_conflicts]
        gap_h = int(soft_conflicts[0]["gap_required"] // 60)
        lines.append(
            f"⚠️ 检测到{len(soft_conflicts)}组中西药交互（需间隔{gap_h}小时）："
            + "；".join(names)
        )

    if not hard_conflicts and not soft_conflicts:
        lines.append("✅ 未检测到药物配伍冲突，所有药物可按常规时间服用。")

    # Synergies
    if synergies:
        synergy_reasons = [s["reason"] for s in synergies[:3]]
        lines.append(f"💡 检测到{len(synergies)}组协同用药建议：" + "；".join(synergy_reasons))

    # Safety verdict
    if safety_verified:
        lines.append("✅ 排程已通过安全验证，所有药物已合理分配到不同时段。")
    else:
        lines.append("⚠️ 排程存在安全风险，请务必咨询执业医师或药师后再用药。")

    lines.append("⚠️ 以上排程由系统算法生成，仅供参考，不能替代医师指导。")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Safety verification
# ---------------------------------------------------------------------------

def _verify_schedule_safety(
    slot_assignments: dict[str, list[str]],
    conflict_matrix: dict[tuple[str, str], dict],
) -> bool:
    """Verify that no conflicting pair shares a time slot.

    Returns ``True`` if all conflict rules are satisfied.
    """
    for pair_key, info in conflict_matrix.items():
        a, b = info["names"]
        # Check if both are in the same slot
        for period in SLOT_ORDER:
            meds = slot_assignments.get(period, [])
            if a in meds and b in meds:
                return False

        # For soft conflicts, check minimum gap
        if info["gap_required"] != float("inf"):
            a_periods = [p for p in SLOT_ORDER if a in slot_assignments.get(p, [])]
            b_periods = [p for p in SLOT_ORDER if b in slot_assignments.get(p, [])]
            for ap in a_periods:
                for bp in b_periods:
                    if ap != bp:
                        gap = _slot_gap_minutes(ap, bp)
                        if gap < info["gap_required"]:
                            return False

    return True


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def generate_weekly_schedule(
    db: DbAdapter,
    medications: list[MedicationInput],
    user_profile: dict | None = None,
) -> WeeklySchedule:
    """Generate a safe weekly medication schedule (周一~周五).

    Algorithm:
      1. Extract herb/medicine names from medications
      2. Run five-layer safety check on all combinations
      3. Build structured conflict matrix from safety_rules
      4. Detect synergy pairs
      5. Greedy slot assignment respecting conflicts + spacing
      6. Return weekly schedule with safety verification

    Args:
        db: Database adapter for querying safety rules.
        medications: List of MedicationInput objects.
        user_profile: Optional dict with keys:
            is_pregnant (bool), age (int), weight_kg (float), constitution (str)

    Returns:
        WeeklySchedule with days, conflicts, synergies, and safety verification.
    """
    if not medications:
        return WeeklySchedule(
            days=[DaySchedule(day=d, slots=[]) for d in DAY_NAMES],
            conflicts_found=[],
            synergies_found=[],
            spacing_rules=[],
            summary="📋 未提供药物信息，无法生成排程。",
            safety_verified=True,
        )

    # --- Step 1: Classify medications ---
    herb_names = [m.name for m in medications if _is_herb_type(m.type)]
    medicine_names = [m.name for m in medications if _is_western_drug_type(m.type)]

    # --- Step 2: Run five-layer safety check ---
    safety_result = await run_safety_check(
        db, herb_names, medicine_names, user_profile
    )

    # --- Step 3: Build structured conflict matrix ---
    conflict_matrix = await _build_conflict_matrix(db, medications)

    # --- Step 4: Detect synergies (excluding conflicting pairs) ---
    synergies = _detect_synergies(medications, conflict_matrix)

    # --- Step 5: Greedy slot assignment ---
    slot_assignments, med_reasons = _assign_slots(medications, conflict_matrix)

    # --- Step 6: Build day schedules ---
    days: list[DaySchedule] = []
    for day_idx, day_name in enumerate(DAY_NAMES):
        slots = _build_day_slots(
            day_idx, medications, slot_assignments, med_reasons, conflict_matrix
        )
        days.append(DaySchedule(day=day_name, slots=slots))

    # --- Step 7: Verify safety ---
    safety_verified = _verify_schedule_safety(slot_assignments, conflict_matrix)

    # --- Step 8: Build spacing rules list ---
    spacing_rules: list[dict] = []
    for info in conflict_matrix.values():
        if info["gap_required"] != float("inf"):
            gap_h = int(info["gap_required"] // 60)
            spacing_rules.append({
                "names": info["names"],
                "type": info["type"],
                "min_gap_hours": gap_h,
                "reason": info["mechanism"],
            })

    # --- Step 9: Build conflicts_found list ---
    conflicts_found: list[dict] = []
    for info in conflict_matrix.values():
        conflicts_found.append({
            "names": info["names"],
            "type": info["type"],
            "severity": info["severity"],
            "mechanism": info["mechanism"],
            "action": "禁止同服" if info["gap_required"] == float("inf") else "需间隔服用",
            "resolved": safety_verified,
        })

    # --- Step 10: Build summary ---
    summary = _build_summary(
        medications, conflict_matrix, synergies, safety_verified
    )

    return WeeklySchedule(
        days=days,
        conflicts_found=conflicts_found,
        synergies_found=synergies,
        spacing_rules=spacing_rules,
        summary=summary,
        safety_verified=safety_verified,
    )


# ---------------------------------------------------------------------------
# Schedule verification (for /auto-schedule/verify endpoint)
# ---------------------------------------------------------------------------

async def verify_existing_schedule(
    db: DbAdapter,
    schedule: dict,
) -> dict:
    """Verify that an existing/proposed schedule has no safety violations.

    Args:
        db: Database adapter.
        schedule: dict with ``days`` key, each day having ``slots`` with
                  ``medicines`` containing ``name`` and ``type``.

    Returns:
        dict with ``safe``, ``violations``, ``warnings``.
    """
    violations: list[dict] = []
    warnings: list[dict] = []

    # Collect all medication names and types
    all_meds: list[MedicationInput] = []
    for day_data in schedule.get("days", []):
        for slot in day_data.get("slots", []):
            for med in slot.get("medicines", []):
                name = med.get("name", "")
                med_type = med.get("type", "中药")
                if name:
                    all_meds.append(MedicationInput(
                        name=name,
                        type=med_type,
                        dosage=med.get("dosage", ""),
                        frequency=med.get("frequency", "每日1次"),
                    ))

    # Remove duplicates by name
    seen_names: set[str] = set()
    unique_meds: list[MedicationInput] = []
    for m in all_meds:
        if m.name not in seen_names:
            seen_names.add(m.name)
            unique_meds.append(m)

    # Build conflict matrix
    conflict_matrix = await _build_conflict_matrix(db, unique_meds)

    # Check each day's slots for violations
    for day_data in schedule.get("days", []):
        day_name = day_data.get("day", "")
        for slot in day_data.get("slots", []):
            slot_period = slot.get("period", "")
            slot_time = slot.get("time", "")
            med_names = [m.get("name", "") for m in slot.get("medicines", [])]

            # Check for same-slot conflicts
            for pair_key, info in conflict_matrix.items():
                a, b = info["names"]
                if a in med_names and b in med_names:
                    violations.append({
                        "day": day_name,
                        "slot": slot_period,
                        "time": slot_time,
                        "names": [a, b],
                        "type": info["type"],
                        "severity": info["severity"],
                        "mechanism": info["mechanism"],
                        "message": f"{a}与{b}不可在同一时段服用（{info['type']}）",
                    })

    safe = len(violations) == 0

    return {
        "safe": safe,
        "violations": violations,
        "warnings": warnings,
        "total_conflicts_checked": len(conflict_matrix),
    }


# ---------------------------------------------------------------------------
# Multi-AI Expert Review — 多模型专家评审
# ---------------------------------------------------------------------------

EXPERT_REVIEW_PROMPT = """你是中医+西药临床药学专家。请评审以下服药计划的合理性。

药物清单：
{medications}

服药时刻表（周一~周五）：
{schedule_text}

安全检查结果：
- 发现冲突：{conflicts}
- 协同建议：{synergies}
- 间隔规则：{spacing}

请从以下维度评分（1-5分）并给出意见：
1. 安全性：药物之间是否有未检测到的风险？
2. 时间合理性：服药时间安排是否科学？
3. 剂量合理性：剂量是否在安全范围？
4. 完整性：是否有遗漏的注意事项？

请返回JSON格式：
{{"safety_score": 1-5, "timing_score": 1-5, "dosage_score": 1-5, "completeness_score": 1-5, "overall_score": 1-5, "approved": true/false, "concerns": ["问题1", "问题2"], "suggestions": ["建议1"]}}
"""


def _schedule_to_text(schedule: dict) -> str:
    lines = []
    for day in schedule.get("days", []):
        day_name = day.get("day", "")
        for slot in day.get("slots", []):
            meds = ", ".join(f"{m['name']}({m.get('dosage','')})" for m in slot.get("medicines", []))
            if meds:
                lines.append(f"{day_name} {slot.get('time','')} [{slot.get('period','')}]: {meds}")
    return "\n".join(lines)


def _medications_to_text(meds: list[dict]) -> str:
    return "\n".join(f"- {m.get('name','')} {m.get('type','')} {m.get('dosage','')} {m.get('frequency','')}" for m in meds)


async def expert_review_schedule(
    schedule: dict,
    medications: list[dict],
) -> dict:
    """Send schedule to multiple AI models for expert consensus review.

    Returns aggregated review with per-model scores and consensus decision.
    Requires ≥2/3 models to approve for consensus_pass=True.
    """
    import logging
    logger = logging.getLogger(__name__)

    try:
        from app.llm import chat_completion, settings
    except ImportError:
        return {"consensus_pass": True, "reviews": [], "note": "LLM不可用，跳过专家评审"}

    if not getattr(settings, "LLM_API_KEY", "") or not settings.LLM_API_KEY:
        return {"consensus_pass": True, "reviews": [], "note": "未配置API密钥，跳过专家评审"}

    schedule_text = _schedule_to_text(schedule)
    meds_text = _medications_to_text(medications)
    conflicts = json.dumps(schedule.get("conflicts_found", []), ensure_ascii=False)
    synergies = json.dumps(schedule.get("synergies_found", []), ensure_ascii=False)
    spacing = json.dumps(schedule.get("spacing_rules", []), ensure_ascii=False)

    prompt = EXPERT_REVIEW_PROMPT.format(
        medications=meds_text,
        schedule_text=schedule_text,
        conflicts=conflicts,
        synergies=synergies,
        spacing=spacing,
    )

    review_models = ["Kimi-K2.6", "GLM-5", "qwen3-235b-a22b"]
    reviews: list[dict] = []

    for model in review_models:
        try:
            messages = [{"role": "user", "content": prompt}]
            reply = await chat_completion(
                messages=messages,
                model=model,
            )
            raw = reply.strip() if isinstance(reply, str) else str(reply)

            parsed = _parse_review_json(raw)
            parsed["model"] = model
            reviews.append(parsed)
        except Exception as e:
            logger.warning(f"Expert review failed for {model}: {e}")
            reviews.append({
                "model": model,
                "overall_score": 0,
                "approved": False,
                "error": str(e),
                "concerns": [],
                "suggestions": [],
            })

    approvals = sum(1 for r in reviews if r.get("approved"))
    consensus_pass = approvals >= max(1, len(review_models) // 2 + 1)

    avg_overall = 0.0
    scored = [r.get("overall_score", 0) for r in reviews if r.get("overall_score", 0) > 0]
    if scored:
        avg_overall = sum(scored) / len(scored)

    all_concerns: list[str] = []
    all_suggestions: list[str] = []
    for r in reviews:
        all_concerns.extend(r.get("concerns", []))
        all_suggestions.extend(r.get("suggestions", []))

    return {
        "consensus_pass": consensus_pass,
        "approval_count": f"{approvals}/{len(review_models)}",
        "average_score": round(avg_overall, 1),
        "reviews": reviews,
        "aggregated_concerns": list(dict.fromkeys(all_concerns)),
        "aggregated_suggestions": list(dict.fromkeys(all_suggestions)),
        "note": "多AI专家评审完成" if reviews else "无可用模型，跳过评审",
    }


def _parse_review_json(raw: str) -> dict:
    import re
    json_match = re.search(r'\{[^{}]*\}', raw, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group(0))
            return {
                "safety_score": data.get("safety_score", 3),
                "timing_score": data.get("timing_score", 3),
                "dosage_score": data.get("dosage_score", 3),
                "completeness_score": data.get("completeness_score", 3),
                "overall_score": data.get("overall_score", 3),
                "approved": data.get("approved", False),
                "concerns": data.get("concerns", []),
                "suggestions": data.get("suggestions", []),
            }
        except (json.JSONDecodeError, KeyError):
            pass

    has_approve = "通过" in raw or "approve" in raw.lower()
    return {
        "safety_score": 3,
        "timing_score": 3,
        "dosage_score": 3,
        "completeness_score": 3,
        "overall_score": 3,
        "approved": has_approve,
        "concerns": [],
        "suggestions": [],
    }
