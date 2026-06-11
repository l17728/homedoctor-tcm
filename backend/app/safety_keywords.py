"""Emergency keyword detection from spec §14.6.

Safety-first design: hard-coded keyword check runs BEFORE any AI processing.
If emergency keywords are detected, the system immediately warns the user
to seek emergency medical attention (dial 120).
"""

from __future__ import annotations

# Spec §14.6 — 急症关键词列表
EMERGENCY_KEYWORDS: list[str] = [
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
]

# Warning message returned when emergency keywords are detected
EMERGENCY_WARNING = "⚠️ 您描述的症状可能需要紧急就医，请拨打120急救电话"


def check_emergency_keywords(text: str) -> list[str]:
    """Check text for emergency medical keywords.

    Args:
        text: User input text to check.

    Returns:
        List of matched emergency keywords (empty if none found).
    """
    matched: list[str] = []
    for keyword in EMERGENCY_KEYWORDS:
        if keyword in text:
            matched.append(keyword)
    return matched
