"""中药饮片变质判断 + 开封后保质期追踪 — spec §16.4.

Provides:
- ``HERB_SHELF_LIFE`` — per-category shelf life (days) after opening.
- ``DETERIORATION_SIGNS`` — the five visual/olfactory deterioration signs for
  中药饮片 (虫蛀/霉变/泛油/变色/气味散失).
- ``check_herb_quality(medicine)`` — structured assessment returning
  ``{status, issues, recommendations}``.

The module is pure logic (no DB / no I/O) so it is trivially unit-testable.
The router in ``app/routers/medicines.py`` wraps it for the HTTP layer.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

# Spec §16.4 references CST (China Standard Time, UTC+8) for date comparisons.
CST = timezone(timedelta(hours=8))

# ---------------------------------------------------------------------------
# Per-category shelf life after opening (in days) — spec §16.4
# ---------------------------------------------------------------------------
# 含挥发油类（薄荷/藿香）: ≤6 个月 (180d)
# 芳香化湿药 / 解表药: volatile-oil rich → same ≤6 个月
# 含糖淀粉类（枸杞/山药）/ 补益药: ≤12 个月 (365d)
# 矿物类: ≤24 个月 (730d) — task spec (prod ≤3年 is a loose upper bound)
HERB_SHELF_LIFE: dict[str, int] = {
    "挥发油类": 180,
    "芳香化湿药": 180,
    "解表药": 180,
    "糖类/树脂类": 365,
    "补益药": 365,
    "矿物类": 730,
    "default": 365,
}

# Chinese numeral → int, for shelf-life strings like "半年" / "一年".
_CN_NUM = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6,
           "七": 7, "八": 8, "九": 9, "十": 10, "半": 0.5}

# ---------------------------------------------------------------------------
# 中药饮片变质判断 — spec §16.4 五大变质特征
# ---------------------------------------------------------------------------
# These are observation-based signs the system cannot auto-detect from data;
# they are surfaced as inspection reminders, prioritised when a herb has been
# open a long time.
DETERIORATION_SIGNS: dict[str, str] = {
    "虫蛀": "药材表面有蛀孔或虫粪",
    "霉变": "药材表面有白色/绿色/黑色霉斑",
    "泛油": "药材表面发亮、发粘，有油渍状",
    "变色": "药材颜色明显改变（发暗/发白/发黑）",
    "气味散失": "药材失去原有气味",
}

# Medicine ``type`` values that represent 中药饮片 / herbal material and thus
# qualify for the deterioration-sign inspection prompts.
_HERB_TYPES = {"herbal", "herbal_tea", "chinese_patent"}

# Thresholds
_EXPIRY_WARNING_DAYS = 30     # 过期前 30 天 → warning (spec §16.4 table)
_OPENED_INSPECT_DAYS = 150    # 开封超过此天数 → prompt deterioration inspection


def _now() -> datetime:
    """Current time in CST. Wrapped for monkeypatching in tests."""
    return datetime.now(CST)


def _parse_date(value: Any) -> datetime | None:
    """Parse a ``YYYY-MM-DD`` (or ISO datetime) string into a tz-aware datetime.

    Returns ``None`` for empty / unparseable values.
    """
    if not value or not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None
    # Accept both date-only and full datetime forms.
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(s[:19], fmt)
            return dt.replace(tzinfo=CST) if dt.tzinfo is None else dt
        except ValueError:
            continue
    return None


def _parse_shelf_life_after_open(raw: Any) -> int | None:
    """Parse ``shelf_life_after_open`` free text into a number of days.

    Accepted forms (Chinese domain language per AGENTS.md §1.7):
      - "6个月" / "6月"   → 180
      - "180天" / "180日" → 180
      - "180"             → 180 (bare number = days)
      - "半年" / "一年"   → 90 / 365
      - "6m" / "6M"       → 180
    Returns ``None`` when unparseable / empty.
    """
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return int(raw)
    s = str(raw).strip()
    if not s:
        return None

    # Detect unit suffix
    has_month = bool(re.search(r"个?月|[mM](?!g)", s))
    has_year = bool(re.search(r"年|[yY](?!g)", s))
    has_day = bool(re.search(r"天|日|[dD]", s))

    # Extract leading numeric (supports Chinese numerals)
    m = re.match(r"\s*(\d+(?:\.\d+)?)", s)
    if m:
        n = float(m.group(1))
    else:
        # Try Chinese numeral prefix like 半年 / 一年 / 六个月
        cn = "".join(c for c in s if c in _CN_NUM)
        if not cn:
            return None
        # Take first meaningful token
        n = _CN_NUM.get(cn[0])
        if n is None:
            return None

    if has_year:
        return int(n * 365)
    if has_month:
        return int(n * 30)
    if has_day:
        return int(n)
    # Bare number with no unit — assume days (safest for a count).
    return int(n)


def _detect_herb_category(medicine: dict[str, Any]) -> str:
    """Determine the herb category key for shelf-life lookup.

    Looks in (priority order):
      1. ``properties.herbCategory`` / ``properties.功效分类`` / ``properties.category``
      2. ``herbal_fields.category`` / ``herbal_fields.功效分类``
      3. keyword scan of name + herbal_fields text against HERB_SHELF_LIFE keys
    Returns the matched key, or ``"default"``.
    """
    def _as_dict(v: Any) -> dict[str, Any]:
        if isinstance(v, dict):
            return v
        return {}

    props = _as_dict(medicine.get("properties"))
    herbal = _as_dict(medicine.get("herbal_fields"))

    # 1 & 2 — explicit category fields
    candidates = (
        props.get("herbCategory"),
        props.get("功效分类"),
        props.get("herb_category"),
        herbal.get("category"),
        herbal.get("功效分类"),
    )
    for cat in candidates:
        if cat and isinstance(cat, str):
            key = _match_category_key(cat)
            if key:
                return key

    # 3 — keyword fallback: scan name + concatenated herbal text
    blob = " ".join(filter(None, [
        medicine.get("name") or "",
        str(herbal.get("efficacy") or ""),
        str(herbal.get("indications") or ""),
        str(herbal.get("category") or ""),
        str(props.get("功效") or ""),
    ]))
    return _match_category_key(blob) or "default"


def _match_category_key(text: str) -> str | None:
    """Return the HERB_SHELF_LIFE key whose label appears in ``text``."""
    if not text:
        return None
    for key in HERB_SHELF_LIFE:
        if key == "default":
            continue
        if key in text:
            return key
    return None


def estimate_shelf_life_days(medicine: dict[str, Any]) -> int:
    """Estimate the post-opening shelf life (days) for a medicine.

    Priority:
      1. Explicit ``shelf_life_after_open`` parsed value (if present & valid).
      2. Category-based lookup via ``HERB_SHELF_LIFE``.
      3. ``HERB_SHELF_LIFE['default']`` (365).
    """
    explicit = _parse_shelf_life_after_open(medicine.get("shelf_life_after_open"))
    if explicit and explicit > 0:
        return explicit
    category = _detect_herb_category(medicine)
    return HERB_SHELF_LIFE.get(category, HERB_SHELF_LIFE["default"])


def check_herb_quality(medicine: dict[str, Any]) -> dict[str, Any]:
    """Assess a medicine for quality issues — spec §16.4.

    Parameters
    ----------
    medicine
        Parsed medicine row (JSON fields already decoded into dicts/lists).

    Returns
    -------
    dict with keys:
      - ``status``: ``"good"`` | ``"warning"`` | ``"critical"``
      - ``issues``: list of ``{severity, type, title, detail}``
      - ``recommendations``: list of actionable Chinese strings
      - ``deterioration_signs``: list of the 5 signs (herbs only) to inspect
      - ``shelf_life_days``: estimated/used post-open shelf life (days)
      - ``category``: detected herb category key
    """
    issues: list[dict[str, Any]] = []
    recommendations: list[str] = []

    med_type = str(medicine.get("type") or "").lower().strip()
    is_herb = med_type in _HERB_TYPES
    category = _detect_herb_category(medicine)

    now = _now()
    today = now.date()

    # --- 1. Expiry date check (applies to all medicine types) ---------------
    expiry = _parse_date(medicine.get("expiry_date"))
    if expiry:
        expiry_day = expiry.date()
        days_to_expiry = (expiry_day - today).days
        if days_to_expiry < 0:
            issues.append({
                "severity": "critical",
                "type": "expired",
                "title": "已过有效期",
                "detail": f"该药品已于 {expiry_day.isoformat()} 过期，请勿继续使用。",
            })
            recommendations.append("立即停止使用并按药品分类妥善废弃，不要随意丢弃。")
        elif days_to_expiry <= _EXPIRY_WARNING_DAYS:
            issues.append({
                "severity": "warning",
                "type": "expiring_soon",
                "title": "即将过期",
                "detail": f"距过期仅 {days_to_expiry} 天（{expiry_day.isoformat()}），请尽快使用。",
            })
            recommendations.append("优先使用此药品，或在到期前更换新品。")

    # --- 2. Opened shelf-life tracking (spec §16.4) -------------------------
    opened = _parse_date(medicine.get("opened_date"))
    shelf_days = estimate_shelf_life_days(medicine)
    opened_exceeded = False
    if opened:
        opened_day = opened.date()
        days_since_open = (today - opened_day).days
        if days_since_open >= shelf_days:
            opened_exceeded = True
            issues.append({
                "severity": "critical",
                "type": "opened_shelf_life_exceeded",
                "title": "开封后保质期已过",
                "detail": (
                    f"开封已 {days_since_open} 天，超出建议保质期 {shelf_days} 天"
                    f"（按{category}类估算）。"
                ),
            })
            recommendations.append("开封后保质期已超，药效可能下降或已变质，建议更换新品。")
        elif days_since_open >= shelf_days * 0.8:
            # Within the final 20% of shelf life → early warning.
            remaining = shelf_days - days_since_open
            issues.append({
                "severity": "warning",
                "type": "opened_near_limit",
                "title": "开封后保质期临近",
                "detail": (
                    f"开封已 {days_since_open} 天，建议保质期 {shelf_days} 天，"
                    f"剩余约 {remaining} 天。"
                ),
            })
            recommendations.append("尽快用完，或留意变质迹象。")

    # --- 3. 中药饮片变质判断 prompts (herb types only) ----------------------
    deterioration_signs: list[dict[str, str]] = []
    if is_herb:
        deterioration_signs = [
            {"sign": k, "description": v} for k, v in DETERIORATION_SIGNS.items()
        ]
        # Prompt inspection more urgently when open long or shelf-life exceeded.
        days_open: int | None = None
        if opened:
            days_open = (today - opened.date()).days
        if opened_exceeded or (days_open is not None and days_open >= _OPENED_INSPECT_DAYS):
            issues.append({
                "severity": "warning",
                "type": "inspect_deterioration",
                "title": "请检查是否变质",
                "detail": (
                    "该中药饮片开封较久，请仔细检查是否存在以下变质迹象："
                    + "、".join(DETERIORATION_SIGNS.keys())
                    + "。若发现任一迹象请立即停用。"
                ),
            })
            recommendations.append("取用时观察外观与气味，发现虫蛀、霉斑、泛油、变色或气味散失即丢弃。")

    # --- Determine overall status -------------------------------------------
    severities = {i["severity"] for i in issues}
    if "critical" in severities:
        status = "critical"
    elif "warning" in severities:
        status = "warning"
    else:
        status = "good"
        if is_herb:
            recommendations.append("保存于阴凉干燥处，避免阳光直射。")

    return {
        "status": status,
        "issues": issues,
        "recommendations": recommendations,
        "deterioration_signs": deterioration_signs,
        "shelf_life_days": shelf_days,
        "category": category,
        "is_herb": is_herb,
    }


def assess_all_quality(medicines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Run ``check_herb_quality`` over many medicines, returning only those
    with ``status != "good"``. Each entry merges the assessment under ``quality``.
    """
    flagged: list[dict[str, Any]] = []
    for med in medicines:
        assessment = check_herb_quality(med)
        if assessment["status"] != "good":
            flagged.append({**med, "quality": assessment})
    return flagged
