"""Child emergency triage data — age-based questionnaires and red-flag rules.

Per spec §23.1: MVP P0 feature for child health safety.
All text in Chinese per domain language policy (AGENTS.md §1.7).

This module is pure data + pure functions — no DB, no side effects.
The triage assessment is a conservative computation that always defers
to professional medical care when any red-flag symptom is present.

Relationship to safety_keywords.py (spec §14.6):
    Several triage red-flag symptoms overlap with the 29 existing
    EMERGENCY_KEYWORDS already used by the chat safety interception layer.
    See RED_FLAG_KEYWORD_MAP below for the cross-reference. The triage
    system provides structured assessment for the same conditions that
    the keyword interceptor catches in free-text chat.
"""

from __future__ import annotations


import logging

logger = logging.getLogger(__name__)
# ---------------------------------------------------------------------------
# Disclaimer — ALWAYS attached to every triage result (non-negotiable)
# ---------------------------------------------------------------------------

TRIAGE_DISCLAIMER = (
    "本系统提供的分诊建议仅供参考，不能替代专业医疗诊断。如有疑问请立即就医。"
)

# ---------------------------------------------------------------------------
# Age groups — per pediatric triage guidelines
# ---------------------------------------------------------------------------

AGE_GROUPS = {
    "新生儿": {
        "min_days": 0,
        "max_days": 28,
        "description": "出生0-28天",
        "key_clinical_note": "新生儿任何发热都需立即就医，免疫系统未发育完善",
    },
    "婴儿": {
        "min_months": 1,
        "max_months": 12,
        "description": "1-12月龄",
        "key_clinical_note": "关注吃奶、尿量、精神状态，高热需紧急就诊",
    },
    "幼儿": {
        "min_months": 13,
        "max_months": 36,
        "description": "13-36月龄（1-3岁）",
        "key_clinical_note": "高热超过3天或呼吸困难需就诊",
    },
    "学龄前": {
        "min_months": 37,
        "max_months": 72,
        "description": "37-72月龄（3-6岁）",
        "key_clinical_note": "标准儿科分诊，关注持续高热和精神状态",
    },
    "学龄": {
        "min_months": 73,
        "max_months": 168,
        "description": "73-168月龄（6-14岁）",
        "key_clinical_note": "标准儿科分诊，可参考儿童自述症状",
    },
}

# Ordered list for API responses
AGE_GROUP_ORDER = ["新生儿", "婴儿", "幼儿", "学龄前", "学龄"]


def determine_age_group(age_months: int, age_days: int | None = None) -> str:
    """Determine the age group for a child.

    Args:
        age_months: Age in months (0-168).
        age_days: Optional age in days for newborn precision.
                  If provided and <= 28, always returns 新生儿.

    Returns:
        Age group name (one of AGE_GROUP_ORDER).

    Raises:
        ValueError: If age is negative or exceeds 168 months (14 years).
    """
    if age_months < 0:
        raise ValueError("月龄不能为负数")

    # age_days takes priority for newborn precision (0-28 days)
    if age_days is not None and 0 <= age_days <= 28 and age_months == 0:
        return "新生儿"

    if age_months == 0:
        return "新生儿"  # <1 month = newborn
    if age_months <= 12:
        return "婴儿"
    if age_months <= 36:
        return "幼儿"
    if age_months <= 72:
        return "学龄前"
    if age_months <= 168:
        return "学龄"

    raise ValueError(
        f"月龄{age_months}超出儿童分诊范围（0-168个月/0-14岁），"
        f"成人请使用其他健康咨询渠道"
    )


# ---------------------------------------------------------------------------
# RED FLAG symptoms — ANY of these = immediate emergency room visit
# ---------------------------------------------------------------------------

RED_FLAG_SYMPTOMS: list[dict[str, object]] = [
    {
        "id": "RF01",
        "symptom": "抽搐或惊厥",
        "detail": "出现全身或局部抽搐，眼神上翻，意识丧失",
        "action": "立即拨打120或前往急诊",
        "max_age_months": None,  # All ages
    },
    {
        "id": "RF02",
        "symptom": "呼吸困难",
        "detail": "呼吸急促、费力、鼻翼扇动、嘴唇发紫",
        "action": "立即就医",
        "max_age_months": None,
    },
    {
        "id": "RF03",
        "symptom": "意识改变",
        "detail": "嗜睡难醒、意识模糊、对呼唤无反应",
        "action": "立即就医",
        "max_age_months": None,
    },
    {
        "id": "RF04",
        "symptom": "持续呕吐",
        "detail": "无法进食进水，呕吐持续超过12小时",
        "action": "尽快就医",
        "max_age_months": None,
    },
    {
        "id": "RF05",
        "symptom": "皮疹按压不褪色",
        "detail": "皮肤出现紫红色皮疹，玻璃杯按压不褪色",
        "action": "立即就医（脑膜炎征象）",
        "max_age_months": None,
    },
    {
        "id": "RF06",
        "symptom": "囟门膨隆",
        "detail": "婴儿头顶囟门凸起、饱满（仅适用于18月龄以下）",
        "action": "立即就医",
        "max_age_months": 18,  # Only infants
    },
    {
        "id": "RF07",
        "symptom": "脱水征象",
        "detail": "哭时无泪、口唇干燥、尿量明显减少（婴儿>8小时无湿尿布）",
        "action": "尽快就医",
        "max_age_months": None,
    },
    {
        "id": "RF08",
        "symptom": "高热不退",
        "detail": "体温≥39°C持续超过3天，退烧药无效",
        "action": "尽快就医",
        "max_age_months": None,
    },
]

# Quick lookup: id → red flag dict
RED_FLAG_MAP: dict[str, dict[str, object]] = {
    rf["id"]: rf for rf in RED_FLAG_SYMPTOMS  # type: ignore[index]
}

# ---------------------------------------------------------------------------
# Cross-reference with safety_keywords.py (spec §14.6)
#
# These existing EMERGENCY_KEYWORDS are already used by the chat safety
# interception layer. The triage system's structured red flags cover the
# same conditions — this mapping documents the relationship so that
# future integrations can cross-reference free-text detection with
# structured triage assessment.
# ---------------------------------------------------------------------------

RED_FLAG_KEYWORD_MAP: dict[str, list[str]] = {
    "RF01": ["抽搐", "惊厥"],
    "RF02": ["呼吸困难"],
    "RF03": ["意识丧失", "昏迷"],
    "RF08": ["高热", "持续高烧"],
}

# ---------------------------------------------------------------------------
# Age-specific urgent thresholds
# ---------------------------------------------------------------------------

URGENT_THRESHOLDS: dict[str, dict[str, object]] = {
    "新生儿": {
        "fever": 38.0,
        "fever_is_emergency": True,  # Any newborn fever = emergency, not just urgent
        "detail": "新生儿任何发热（≥38°C）都需立即就医",
    },
    "婴儿": {
        "fever": 39.0,
        "fever_is_emergency": False,
        "detail": "婴儿高热（≥39°C）需紧急就诊",
    },
    "幼儿": {
        "fever": 39.0,
        "duration_days": 3,
        "fever_is_emergency": False,
        "detail": "幼儿高热超过3天需就诊",
    },
    "学龄前": {
        "fever": 39.0,
        "duration_days": 3,
        "fever_is_emergency": False,
        "detail": "持续高热需就诊",
    },
    "学龄": {
        "fever": 39.0,
        "duration_days": 3,
        "fever_is_emergency": False,
        "detail": "持续高热需就诊",
    },
}

# Low-grade fever threshold (applies to all ages except newborn)
LOW_GRADE_FEVER = 38.0


# ---------------------------------------------------------------------------
# Answer values that trigger urgent triage level
# Mapped by question category for flexible lookup
# ---------------------------------------------------------------------------

URGENT_ANSWER_VALUES: dict[str, list[str]] = {
    "mental_status": ["嗜睡", "昏睡"],
    "feeding": ["拒奶", "拒食"],
    "urine": ["无尿>8小时"],
    "breathing": ["费力", "困难"],
    "cry": ["不哭"],  # Newborn-specific: no cry is very concerning
    "skin_color": ["发紫"],  # Cyanosis = emergency-level
}


# ---------------------------------------------------------------------------
# Questionnaires by age group
#
# Each question has:
#   - id: Unique within the age group (Q01, Q02, ...)
#   - category: Semantic category for assess logic lookup
#   - symptom: Chinese display label
#   - type: "number" or "choice"
#   - unit: For number types (°C, 天)
#   - threshold: For number types with a clinical threshold
#   - options: For choice types
# ---------------------------------------------------------------------------

QUESTIONNAIRES: dict[str, list[dict[str, object]]] = {
    "新生儿": [
        {
            "id": "Q01",
            "category": "temperature",
            "symptom": "体温",
            "type": "number",
            "unit": "°C",
            "threshold": 38.0,
        },
        {
            "id": "Q02",
            "category": "feeding",
            "symptom": "吃奶情况",
            "type": "choice",
            "options": ["正常", "减少", "拒奶"],
        },
        {
            "id": "Q03",
            "category": "mental_status",
            "symptom": "精神状态",
            "type": "choice",
            "options": ["正常", "嗜睡", "烦躁", "昏睡"],
        },
        {
            "id": "Q04",
            "category": "cry",
            "symptom": "哭声",
            "type": "choice",
            "options": ["正常", "微弱", "尖锐", "不哭"],
        },
        {
            "id": "Q05",
            "category": "skin_color",
            "symptom": "皮肤颜色",
            "type": "choice",
            "options": ["正常", "发黄", "苍白", "发紫"],
        },
    ],
    "婴儿": [
        {
            "id": "Q01",
            "category": "temperature",
            "symptom": "体温",
            "type": "number",
            "unit": "°C",
            "threshold": 39.0,
        },
        {
            "id": "Q02",
            "category": "fever_duration",
            "symptom": "发热天数",
            "type": "number",
            "unit": "天",
        },
        {
            "id": "Q03",
            "category": "mental_status",
            "symptom": "精神状态",
            "type": "choice",
            "options": ["正常", "嗜睡", "烦躁", "昏睡"],
        },
        {
            "id": "Q04",
            "category": "feeding",
            "symptom": "进食情况",
            "type": "choice",
            "options": ["正常", "减少", "拒食"],
        },
        {
            "id": "Q05",
            "category": "urine",
            "symptom": "尿量",
            "type": "choice",
            "options": ["正常", "减少", "很少", "无尿>8小时"],
        },
        {
            "id": "Q06",
            "category": "breathing",
            "symptom": "呼吸",
            "type": "choice",
            "options": ["正常", "急促", "费力", "困难"],
        },
    ],
    "幼儿": [
        {
            "id": "Q01",
            "category": "temperature",
            "symptom": "体温",
            "type": "number",
            "unit": "°C",
            "threshold": 39.0,
        },
        {
            "id": "Q02",
            "category": "fever_duration",
            "symptom": "发热天数",
            "type": "number",
            "unit": "天",
        },
        {
            "id": "Q03",
            "category": "mental_status",
            "symptom": "精神状态",
            "type": "choice",
            "options": ["正常", "嗜睡", "烦躁", "昏睡"],
        },
        {
            "id": "Q04",
            "category": "feeding",
            "symptom": "进食情况",
            "type": "choice",
            "options": ["正常", "减少", "拒食"],
        },
        {
            "id": "Q05",
            "category": "urine",
            "symptom": "尿量",
            "type": "choice",
            "options": ["正常", "减少", "很少", "无尿>8小时"],
        },
        {
            "id": "Q06",
            "category": "breathing",
            "symptom": "呼吸",
            "type": "choice",
            "options": ["正常", "急促", "费力", "困难"],
        },
        {
            "id": "Q07",
            "category": "cough",
            "symptom": "咳嗽",
            "type": "choice",
            "options": ["无", "轻微", "频繁", "剧烈"],
        },
    ],
    "学龄前": [
        {
            "id": "Q01",
            "category": "temperature",
            "symptom": "体温",
            "type": "number",
            "unit": "°C",
            "threshold": 39.0,
        },
        {
            "id": "Q02",
            "category": "fever_duration",
            "symptom": "发热天数",
            "type": "number",
            "unit": "天",
        },
        {
            "id": "Q03",
            "category": "mental_status",
            "symptom": "精神状态",
            "type": "choice",
            "options": ["正常", "嗜睡", "烦躁", "昏睡"],
        },
        {
            "id": "Q04",
            "category": "feeding",
            "symptom": "进食情况",
            "type": "choice",
            "options": ["正常", "减少", "拒食"],
        },
        {
            "id": "Q05",
            "category": "urine",
            "symptom": "尿量",
            "type": "choice",
            "options": ["正常", "减少", "很少", "无尿>8小时"],
        },
        {
            "id": "Q06",
            "category": "breathing",
            "symptom": "呼吸",
            "type": "choice",
            "options": ["正常", "急促", "费力", "困难"],
        },
        {
            "id": "Q07",
            "category": "cough",
            "symptom": "咳嗽",
            "type": "choice",
            "options": ["无", "轻微", "频繁", "剧烈"],
        },
        {
            "id": "Q08",
            "category": "throat",
            "symptom": "咽痛",
            "type": "choice",
            "options": ["无", "轻微", "明显", "严重"],
        },
    ],
    "学龄": [
        {
            "id": "Q01",
            "category": "temperature",
            "symptom": "体温",
            "type": "number",
            "unit": "°C",
            "threshold": 39.0,
        },
        {
            "id": "Q02",
            "category": "fever_duration",
            "symptom": "发热天数",
            "type": "number",
            "unit": "天",
        },
        {
            "id": "Q03",
            "category": "mental_status",
            "symptom": "精神状态",
            "type": "choice",
            "options": ["正常", "嗜睡", "烦躁", "昏睡"],
        },
        {
            "id": "Q04",
            "category": "feeding",
            "symptom": "进食情况",
            "type": "choice",
            "options": ["正常", "减少", "拒食"],
        },
        {
            "id": "Q05",
            "category": "urine",
            "symptom": "尿量",
            "type": "choice",
            "options": ["正常", "减少", "很少", "无尿>8小时"],
        },
        {
            "id": "Q06",
            "category": "breathing",
            "symptom": "呼吸",
            "type": "choice",
            "options": ["正常", "急促", "费力", "困难"],
        },
        {
            "id": "Q07",
            "category": "cough",
            "symptom": "咳嗽",
            "type": "choice",
            "options": ["无", "轻微", "频繁", "剧烈"],
        },
        {
            "id": "Q08",
            "category": "throat",
            "symptom": "咽痛",
            "type": "choice",
            "options": ["无", "轻微", "明显", "严重"],
        },
        {
            "id": "Q09",
            "category": "headache",
            "symptom": "头痛",
            "type": "choice",
            "options": ["无", "轻微", "明显", "严重"],
        },
    ],
}


# ---------------------------------------------------------------------------
# Triage levels — ordered by urgency (highest first)
# ---------------------------------------------------------------------------

TRIAGE_LEVELS: dict[str, dict[str, str]] = {
    "emergency": {
        "level": "紧急",
        "color": "red",
        "action": "立即拨打120或前往最近急诊",
        "time": "立即",
    },
    "urgent": {
        "level": "急诊",
        "color": "orange",
        "action": "请在2小时内就诊",
        "time": "2小时内",
    },
    "routine": {
        "level": "常规",
        "color": "green",
        "action": "可在家观察，如症状加重及时就医",
        "time": "24小时内",
    },
    "self_care": {
        "level": "居家护理",
        "color": "blue",
        "action": "居家护理，注意观察",
        "time": "观察",
    },
}


# ---------------------------------------------------------------------------
# Core triage assessment function — pure, no side effects
# ---------------------------------------------------------------------------

def _to_number(value: object) -> float | None:
    """Safely convert a value to float, returning None if not numeric."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def perform_triage(
    age_months: int,
    answers_by_category: dict[str, object],
    red_flag_ids: list[str],
    age_days: int | None = None,
) -> dict[str, object]:
    """Perform triage assessment — the core medical safety computation.

    This function is intentionally conservative: when in doubt, escalate.
    It never provides actual medical advice — always defers to "请就医".

    Triage priority (first match wins):
        1. ANY red flag symptom → emergency
        2. Newborn (0-28 days) fever ≥38°C → emergency
        3. Cyanosis (皮肤发紫) → emergency
        4. No cry in newborn (不哭) → emergency
        5. Age-specific fever threshold → urgent
        6. Fever duration exceeds threshold → urgent
        7. Mental status 嗜睡/昏睡 → urgent
        8. Feeding 拒奶/拒食 → urgent
        9. Urine 无尿>8小时 → urgent
       10. Breathing 费力/困难 → urgent
       11. Low-grade fever (38-39°C) → routine
       12. Otherwise → self_care

    Args:
        age_months: Child's age in months (0-168).
        answers_by_category: Dict mapping question category → answer value.
            e.g. {"temperature": 38.5, "mental_status": "嗜睡"}
        red_flag_ids: List of red flag IDs the parent confirmed (RF01-RF08).
        age_days: Optional age in days for newborn precision.

    Returns:
        Triage result dict with keys:
            - level_key: "emergency" | "urgent" | "routine" | "self_care"
            - level: Chinese level name
            - color: UI color
            - action: Action instruction
            - time: Time frame
            - age_group: Determined age group name
            - age_months: Echoed age_months
            - warnings: List of warning strings (Chinese)
            - recommendations: List of recommendation strings (Chinese)
            - triggered_red_flags: List of triggered red flag dicts
            - disclaimer: Always-present medical disclaimer
    """
    age_group = determine_age_group(age_months, age_days)
    threshold_cfg = URGENT_THRESHOLDS[age_group]

    warnings: list[str] = []
    recommendations: list[str] = []

    # --- Step 1: Red flags = immediate emergency (highest priority) ---
    triggered_flags: list[dict[str, object]] = []
    for rf_id in red_flag_ids:
        rf = RED_FLAG_MAP.get(rf_id)
        if rf:
            triggered_flags.append(rf)
            warnings.append(
                f"🔴 {rf['symptom']}：{rf['detail']} — {rf['action']}"
            )

    if triggered_flags:
        return _build_result(
            level_key="emergency",
            age_group=age_group,
            age_months=age_months,
            warnings=warnings,
            recommendations=recommendations,
            triggered_red_flags=triggered_flags,
        )

    # --- Extract numeric answers ---
    temp = _to_number(answers_by_category.get("temperature"))
    duration = _to_number(answers_by_category.get("fever_duration"))
    fever_threshold = float(threshold_cfg["fever"])  # type: ignore[arg-type]

    # --- Step 2: Newborn fever = emergency ---
    if age_group == "新生儿" and temp is not None and temp >= 38.0:
        warnings.append(
            f"新生儿体温{temp}°C ≥ 38°C — "
            f"{threshold_cfg['detail']}，免疫系统未发育完善，任何发热均需立即就医"
        )
        return _build_result(
            level_key="emergency",
            age_group=age_group,
            age_months=age_months,
            warnings=warnings,
            recommendations=recommendations,
            triggered_red_flags=[],
        )

    # --- Step 3: Cyanosis = emergency (skin turning blue/purple) ---
    skin_color = answers_by_category.get("skin_color")
    if skin_color == "发紫":
        warnings.append(
            "皮肤发紫（紫绀）— 可能存在严重缺氧，需立即就医"
        )
        return _build_result(
            level_key="emergency",
            age_group=age_group,
            age_months=age_months,
            warnings=warnings,
            recommendations=recommendations,
            triggered_red_flags=[],
        )

    # --- Step 4: Newborn not crying = emergency ---
    cry = answers_by_category.get("cry")
    if age_group == "新生儿" and cry == "不哭":
        warnings.append(
            "新生儿不哭 — 反应极差，需立即就医评估"
        )
        return _build_result(
            level_key="emergency",
            age_group=age_group,
            age_months=age_months,
            warnings=warnings,
            recommendations=recommendations,
            triggered_red_flags=[],
        )

    # --- Steps 5-10: Check urgent conditions ---
    is_urgent = False

    # Step 5: Fever ≥ age threshold
    if temp is not None and temp >= fever_threshold:
        is_urgent = True
        warnings.append(
            f"体温{temp}°C ≥ {fever_threshold}°C — {threshold_cfg['detail']}"
        )

    # Step 6: Fever duration exceeds threshold
    max_days = threshold_cfg.get("duration_days")
    if max_days is not None and duration is not None and duration > float(max_days):
        is_urgent = True
        warnings.append(
            f"发热已{int(duration)}天，超过{max_days}天阈值 — "
            f"{threshold_cfg['detail']}"
        )

    # Step 7: Mental status abnormal
    mental = answers_by_category.get("mental_status")
    if mental in URGENT_ANSWER_VALUES["mental_status"]:
        is_urgent = True
        warnings.append(
            f"精神状态异常（{mental}）— 需紧急评估神经系统状况"
        )

    # Step 8: Feeding refusal
    feeding = answers_by_category.get("feeding")
    if feeding in URGENT_ANSWER_VALUES["feeding"]:
        is_urgent = True
        warnings.append(
            f"进食异常（{feeding}）— 需关注脱水和营养摄入"
        )

    # Step 9: Urine output severely reduced
    urine = answers_by_category.get("urine")
    if urine in URGENT_ANSWER_VALUES["urine"]:
        is_urgent = True
        warnings.append(
            f"尿量异常（{urine}）— 存在严重脱水风险"
        )

    # Step 10: Breathing difficulty
    breathing = answers_by_category.get("breathing")
    if breathing in URGENT_ANSWER_VALUES["breathing"]:
        is_urgent = True
        warnings.append(
            f"呼吸异常（{breathing}）— 需评估呼吸系统"
        )

    if is_urgent:
        recommendations.append("请尽快带孩子到医院儿科就诊")
        recommendations.append("就诊前保持孩子安静，记录体温变化")
        return _build_result(
            level_key="urgent",
            age_group=age_group,
            age_months=age_months,
            warnings=warnings,
            recommendations=recommendations,
            triggered_red_flags=[],
        )

    # --- Step 11: Low-grade fever → routine ---
    if temp is not None and temp >= LOW_GRADE_FEVER:
        recommendations.append(
            f"体温{temp}°C为低热，建议多饮水、物理降温、观察体温变化"
        )
        recommendations.append("如体温持续升高或超过3天未退，请及时就诊")
        recommendations.append("注意休息，保持室内通风")
        return _build_result(
            level_key="routine",
            age_group=age_group,
            age_months=age_months,
            warnings=warnings,
            recommendations=recommendations,
            triggered_red_flags=[],
        )

    # --- Step 12: No concerning symptoms → self_care ---
    recommendations.append("目前症状较轻，可居家观察护理")
    recommendations.append("保持充足休息和水分摄入")
    recommendations.append("如出现任何红旗症状（抽搐、呼吸困难、意识改变等）请立即就医")
    return _build_result(
        level_key="self_care",
        age_group=age_group,
        age_months=age_months,
        warnings=warnings,
        recommendations=recommendations,
        triggered_red_flags=[],
    )


def _build_result(
    level_key: str,
    age_group: str,
    age_months: int,
    warnings: list[str],
    recommendations: list[str],
    triggered_red_flags: list[dict[str, object]],
) -> dict[str, object]:
    """Build the standardized triage result dict with level info + disclaimer."""
    level_info = TRIAGE_LEVELS[level_key]
    return {
        "level_key": level_key,
        "level": level_info["level"],
        "color": level_info["color"],
        "action": level_info["action"],
        "time": level_info["time"],
        "age_group": age_group,
        "age_months": age_months,
        "warnings": warnings,
        "recommendations": recommendations,
        "triggered_red_flags": triggered_red_flags,
        "disclaimer": TRIAGE_DISCLAIMER,
    }


# ---------------------------------------------------------------------------
# Helper: convert raw answers list [{id, value}] to category-keyed dict
# ---------------------------------------------------------------------------

def answers_to_categories(
    age_group: str,
    raw_answers: list[dict[str, object]],
) -> dict[str, object]:
    """Convert raw answers (list of {id, value}) to a category-keyed dict.

    Uses the questionnaire definition to map question IDs to categories.
    Unknown question IDs are silently skipped.

    Args:
        age_group: The age group to look up questionnaire for.
        raw_answers: List of {"id": "Q01", "value": 38.5} dicts.

    Returns:
        Dict mapping category → value, e.g. {"temperature": 38.5, ...}
    """
    questionnaire = QUESTIONNAIRES.get(age_group, [])
    id_to_category: dict[str, str] = {
        str(q["id"]): str(q["category"]) for q in questionnaire
    }

    result: dict[str, object] = {}
    for ans in raw_answers:
        qid = str(ans.get("id", ""))
        category = id_to_category.get(qid)
        if category:
            result[category] = ans.get("value")
    return result
