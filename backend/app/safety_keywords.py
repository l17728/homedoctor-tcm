"""Emergency keyword detection from spec §14.6.

Safety-first design: hard-coded keyword check runs BEFORE any AI processing.
If emergency keywords are detected, the system immediately warns the user
to seek emergency medical attention (dial 120).
"""

from __future__ import annotations


import logging

logger = logging.getLogger(__name__)
# Spec §14.6 — 急症关键词列表 (expanded from 29 to 63 based on medical expert review)
EMERGENCY_KEYWORDS: list[str] = [
    # --- Original 29 ---
    "胸痛",
    "胸闷",
    "呼吸困难",
    "气喘",
    "咯血",
    "意识丧失",
    "昏迷",
    "抽搐",
    "惊厥",
    "大出血",
    "呕血",
    "便血",
    "休克",
    "心跳骤停",
    "剧烈头痛",
    "突然失语",
    "偏瘫",
    "瞳孔不等大",
    "高热",
    "持续高烧",
    "过敏性休克",
    "喉头水肿",
    "窒息",
    "中毒",
    "烧伤",
    "骨折",
    "颅脑损伤",
    "溺水",
    "电击伤",
    # --- Added: abdominal / neurological ---
    "剧烈腹痛",
    "急性腹痛",
    "意识模糊",
    "言语不清",
    "大小便失禁",
    "吞咽困难",
    "声音嘶哑",
    "无尿",
    "少尿",
    "严重心悸",
    "心律不齐",
    "阴道出血",
    "胎动异常",
    "视物模糊",
    "突然失明",
    "肢体麻木",
    "面部歪斜",
    "面瘫",
    "半身不遂",
    # --- Added: allergy / poisoning / overdose ---
    "药物过敏",
    "服用过量",
    "药物中毒",
    "食物中毒",
    "一氧化碳中毒",
    "煤气中毒",
    # --- Added: respiratory / cardiac variants ---
    "急性喉炎",
    "喘不上气",
    "喘不过气",
    "胸口疼",
    "胸口闷",
    # --- Added: unconsciousness / bleeding variants ---
    "晕过去",
    "人事不省",
    "吐血",
    "血尿",
]

# Colloquial / variant phrases mapped to canonical emergency keywords.
# When a synonym phrase appears in user text, the canonical keyword is reported.
SYNONYM_MAP: dict[str, list[str]] = {
    "胸痛": ["胸口疼", "胸口痛", "胸部疼痛", "心口疼", "心口痛"],
    "呼吸困难": ["喘不上气", "喘不过气", "憋气", "气不够用"],
    "昏迷": ["人事不省", "晕过去", "不省人事", "叫不醒"],
    "抽搐": ["抽风", "羊癫疯", "癫痫发作"],
}

# Warning message returned when emergency keywords are detected
EMERGENCY_WARNING = "⚠️ 您描述的症状可能需要紧急就医，请拨打120急救电话"


def check_emergency_keywords(text: str) -> list[str]:
    """Check text for emergency medical keywords.

    Performs two passes:
    1. Direct match against EMERGENCY_KEYWORDS.
    2. Fuzzy match via SYNONYM_MAP — colloquial phrases are mapped to
       their canonical keyword so the caller sees a consistent term.

    Args:
        text: User input text to check.

    Returns:
        List of matched emergency keywords (empty if none found).
        Synonym matches report the canonical keyword, not the raw phrase.
    """
    matched: list[str] = []
    seen: set[str] = set()

    for keyword in EMERGENCY_KEYWORDS:
        if keyword in text and keyword not in seen:
            matched.append(keyword)
            seen.add(keyword)

    for canonical, synonyms in SYNONYM_MAP.items():
        for synonym in synonyms:
            if synonym in text and canonical not in seen:
                matched.append(canonical)
                seen.add(canonical)
                break

    return matched
