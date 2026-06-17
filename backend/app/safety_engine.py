"""Five-layer safety check engine — spec §15.3.

Layer 1a: 中药×中药配伍禁忌 (十八反十九畏) — hardcoded rules from DB
Layer 1b: 中西药交互检查 — drug×herb matching from DB
Layer 2:  剂量范围检查 — verify dosage within safe range
Layer 3:  特殊人群检查 — pregnancy/children/elderly contraindications
Layer 4:  AI 辅助分析 (placeholder for MVP)
Layer 5:  免责声明 — always attach disclaimer
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from app.database import DbAdapter


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class SafetyWarning:
    layer: int           # 1-5
    severity: str        # "critical" | "high" | "medium" | "low"
    title: str
    detail: str
    herbs: list[str]     # affected herbs
    action: str          # "禁止" | "谨慎" | "告知医生"
    source: str


@dataclass
class SafetyCheckResult:
    safe: bool
    warnings: list[SafetyWarning] = field(default_factory=list)
    disclaimer: str = ""
    checked_herbs: list[str] = field(default_factory=list)
    checked_medicines: list[str] = field(default_factory=list)
    # Extra fields for backward-compatible API response
    unknown_herbs: list[str] = field(default_factory=list)
    unknown_medicines: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Disclaimer (Layer 5)
# ---------------------------------------------------------------------------

DISCLAIMER = (
    "⚠️ 以上安全检查结果由系统硬编码规则匹配生成，仅供参考。"
    "请务必在调整任何用药方案前咨询执业医师或药师。"
)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def run_safety_check(
    db: DbAdapter,
    herb_names: list[str],
    medicine_names: list[str] | None = None,
    user_profile: dict | None = None,
    dosages: dict[str, float] | None = None,
) -> SafetyCheckResult:
    """Run all 5 layers of safety checks.

    Args:
        db: Database adapter for querying rules and herbs.
        herb_names: List of herb names to check.
        medicine_names: Optional list of western medicine names.
        user_profile: Optional dict with keys:
            is_pregnant (bool), age (int), weight_kg (float), constitution (str)
        dosages: Optional dict mapping herb_name → dosage in grams.

    Returns:
        SafetyCheckResult with all warnings and disclaimer.
    """
    if medicine_names is None:
        medicine_names = []
    if dosages is None:
        dosages = {}

    warnings: list[SafetyWarning] = []
    dedup: set[str] = set()  # warning deduplication key → avoid duplicates

    def _add(w: SafetyWarning) -> None:
        key = f"{w.layer}|{w.severity}|{w.title}|{'|'.join(sorted(w.herbs))}"
        if key not in dedup:
            dedup.add(key)
            warnings.append(w)

    # --- Resolve herbs: look up DB info ---
    herb_info: dict[str, dict] = {}
    unknown_herbs: list[str] = []
    for name in herb_names:
        row = await db.query_one(
            "SELECT * FROM herbs WHERE name = ?", (name,)
        )
        if row:
            herb_info[name] = row
        else:
            # Try aliases
            row = await db.query_one(
                "SELECT * FROM herbs WHERE aliases LIKE ?", (f"%{name}%",)
            )
            if row:
                herb_info[name] = row
            else:
                unknown_herbs.append(name)

    unknown_medicines: list[str] = []
    for med in medicine_names:
        row = await db.query_one(
            "SELECT * FROM medicines WHERE name = ?", (med,)
        )
        if not row:
            unknown_medicines.append(med)

    # --- Layer 1a: 中药×中药配伍禁忌 (十八反十九畏) ---
    layer1a_warnings = await _check_herb_herb_contraindications(db, herb_names)
    for w in layer1a_warnings:
        _add(w)

    # --- Layer 1b: 中西药交互检查 ---
    layer1b_warnings = await _check_herb_drug_interactions(db, herb_names, medicine_names)
    for w in layer1b_warnings:
        _add(w)

    # --- Layer 2: 剂量范围检查 ---
    layer2_warnings = await _check_dosage(herb_names, herb_info, dosages)
    for w in layer2_warnings:
        _add(w)

    # --- Layer 3: 特殊人群检查 ---
    layer3_warnings = _check_special_populations(herb_names, herb_info, user_profile)
    for w in layer3_warnings:
        _add(w)

    # --- Layer 4: AI 辅助分析 (placeholder) ---
    # No-op for MVP. Future: send structured prompt to AI, parse response.

    # --- Determine safety ---
    has_blocking = any(w.severity in ("critical", "high") for w in warnings)

    result = SafetyCheckResult(
        safe=not has_blocking,
        warnings=warnings,
        disclaimer=DISCLAIMER,
        checked_herbs=list(herb_names),
        checked_medicines=list(medicine_names),
        unknown_herbs=unknown_herbs,
        unknown_medicines=unknown_medicines,
    )
    return result


# ---------------------------------------------------------------------------
# Layer 1a: 中药×中药配伍禁忌
# ---------------------------------------------------------------------------

async def _check_herb_herb_contraindications(
    db: DbAdapter, herb_names: list[str]
) -> list[SafetyWarning]:
    """Check 十八反 and 十九畏 rules between herb pairs."""
    warnings: list[SafetyWarning] = []
    if len(herb_names) < 2:
        return warnings

    seen_ids: set[str] = set()
    for i, a in enumerate(herb_names):
        for b in herb_names[i + 1:]:
            rows = await db.query(
                """SELECT * FROM safety_rules WHERE enabled = 1
                   AND ((drug_a = ? AND drug_b = ?) OR (drug_a = ? AND drug_b = ?))
                   AND rule_type IN ('十八反', '十九畏')""",
                (a, b, b, a),
            )
            for r in rows:
                if r["id"] not in seen_ids:
                    seen_ids.add(r["id"])
                    warnings.append(SafetyWarning(
                        layer=1,
                        severity="critical",
                        title=f"配伍禁忌（{r['rule_type']}）",
                        detail=r["mechanism"],
                        herbs=[r["drug_a"], r["drug_b"]],
                        action="禁止",
                        source=r["source"],
                    ))
    return warnings


# ---------------------------------------------------------------------------
# Layer 1b: 中西药交互检查
# ---------------------------------------------------------------------------

async def _get_medicine_drug_class(db: DbAdapter, medicine_name: str) -> str:
    """Look up a medicine's drugClass from its properties JSON.

    Returns '西药' if not found (backward compatible default).
    Only medicines whose drugClass is '西药' should trigger Layer 1b.
    '中药' and '中成药' go through Layer 1a (配伍禁忌) instead.
    """
    row = await db.query_one(
        "SELECT properties FROM medicines WHERE name = ?", (medicine_name,)
    )
    if row:
        props = row["properties"]
        if isinstance(props, str):
            try:
                props = json.loads(props)
            except (json.JSONDecodeError, TypeError):
                props = {}
        if isinstance(props, dict):
            dc = props.get("drugClass", "")
            if dc in ("中药", "西药", "中成药"):
                return dc
    return "西药"  # backward compatible default


async def _check_herb_drug_interactions(
    db: DbAdapter, herb_names: list[str], medicine_names: list[str]
) -> list[SafetyWarning]:
    """Check herb-drug interaction rules."""
    warnings: list[SafetyWarning] = []
    if not medicine_names or not herb_names:
        return warnings

    seen_ids: set[str] = set()

    for drug in medicine_names:
        # --- drugClass awareness (spec §15.2) ---
        # Only 西药 medicines trigger Layer 1b (中西药交互).
        # 中药 / 中成药 medicines go through Layer 1a (配伍禁忌) instead.
        drug_class = await _get_medicine_drug_class(db, drug)
        if drug_class != "西药":
            continue

        for herb in herb_names:
            # Exact match: drug_a = western drug, drug_b = herb
            rows = await db.query(
                """SELECT * FROM safety_rules WHERE enabled = 1
                   AND drug_a = ? AND drug_b = ?
                   AND rule_type = '中西药交互'""",
                (drug, herb),
            )
            for r in rows:
                if r["id"] not in seen_ids:
                    seen_ids.add(r["id"])
                    sev = r["severity"]
                    action = "禁止" if sev == "critical" else "谨慎"
                    warnings.append(SafetyWarning(
                        layer=1,
                        severity=sev,
                        title=f"中西药交互（{r.get('source', '')}）",
                        detail=r["mechanism"],
                        herbs=[herb],
                        action=action,
                        source=r.get("source", ""),
                    ))

        # Also check fuzzy match (drug_a contains drug name, e.g. "华法林" in name)
        rows = await db.query(
            """SELECT * FROM safety_rules WHERE enabled = 1
               AND drug_a LIKE ? AND rule_type = '中西药交互'""",
            (f"%{drug}%",),
        )
        for r in rows:
            if r["id"] not in seen_ids and r["drug_b"] in herb_names:
                seen_ids.add(r["id"])
                sev = r["severity"]
                action = "禁止" if sev == "critical" else "谨慎"
                warnings.append(SafetyWarning(
                    layer=1,
                    severity=sev,
                    title=f"中西药交互（{r.get('source', '')}）",
                    detail=r["mechanism"],
                    herbs=[r["drug_b"]],
                    action=action,
                    source=r.get("source", ""),
                ))

    return warnings


# ---------------------------------------------------------------------------
# Layer 2: 剂量范围检查
# ---------------------------------------------------------------------------

async def _check_dosage(
    herb_names: list[str],
    herb_info: dict[str, dict],
    dosages: dict[str, float],
) -> list[SafetyWarning]:
    """Check if specified dosages are within safe ranges."""
    warnings: list[SafetyWarning] = []

    for name in herb_names:
        info = herb_info.get(name)
        if not info:
            continue

        dosage_min = info.get("dosage_min_g")
        dosage_max = info.get("dosage_max_g")
        if dosage_min is None or dosage_max is None:
            continue

        dosage = dosages.get(name)
        if dosage is not None:
            if dosage > dosage_max:
                warnings.append(SafetyWarning(
                    layer=2,
                    severity="high",
                    title="剂量超出安全范围",
                    detail=f"{name}用量{dosage}g超出最大安全剂量{dosage_max}g",
                    herbs=[name],
                    action="告知医生",
                    source="剂量检查",
                ))
            elif dosage < dosage_min:
                warnings.append(SafetyWarning(
                    layer=2,
                    severity="low",
                    title="剂量低于最小有效量",
                    detail=f"{name}用量{dosage}g低于最小有效剂量{dosage_min}g",
                    herbs=[name],
                    action="告知医生",
                    source="剂量检查",
                ))
        # If no dosage specified, no warning needed — just informational

    return warnings


# ---------------------------------------------------------------------------
# Layer 3: 特殊人群检查
# ---------------------------------------------------------------------------

def _check_special_populations(
    herb_names: list[str],
    herb_info: dict[str, dict],
    user_profile: dict | None,
) -> list[SafetyWarning]:
    """Check contraindications for special populations."""
    warnings: list[SafetyWarning] = []

    if not user_profile:
        return warnings

    is_pregnant = user_profile.get("is_pregnant", False)
    age = user_profile.get("age")

    # --- Pregnancy check ---
    if is_pregnant:
        pregnancy_keywords = ["孕妇", "妊娠", "怀孕", "慎用", "禁用"]
        for name in herb_names:
            info = herb_info.get(name)
            if not info:
                continue
            contraindications = info.get("contraindications") or ""
            # Check if any pregnancy keyword appears in contraindications
            # But we want to flag herbs that are specifically dangerous for pregnant women
            pregnancy_dangerous = [
                "桃仁", "红花", "三棱", "莪术", "水蛭", "虻虫", "斑蝥",
                "麝香", "巴豆", "甘遂", "大戟", "芫花", "牵牛子", "商陆",
                "麝香", "蜈蚣", "全蝎", "附子", "川乌", "草乌",
            ]
            if name in pregnancy_dangerous:
                warnings.append(SafetyWarning(
                    layer=3,
                    severity="high",
                    title="孕妇禁用",
                    detail=f"{name}为孕妇禁忌药物，可能影响胎儿安全",
                    herbs=[name],
                    action="禁止",
                    source="特殊人群检查-孕妇",
                ))
            elif any(kw in contraindications for kw in pregnancy_keywords):
                warnings.append(SafetyWarning(
                    layer=3,
                    severity="high",
                    title="孕妇慎用",
                    detail=f"{name}的禁忌说明中包含孕妇相关警告",
                    herbs=[name],
                    action="谨慎",
                    source="特殊人群检查-孕妇",
                ))

    # --- Children check ---
    if age is not None:
        if isinstance(age, (int, float)):
            if age < 3:
                warnings.append(SafetyWarning(
                    layer=3,
                    severity="critical",
                    title="3岁以下婴幼儿禁止自行用药",
                    detail="3岁以下婴幼儿用药必须由儿科医生指导，请立即就医",
                    herbs=list(herb_names),
                    action="禁止",
                    source="特殊人群检查-婴幼儿",
                ))
            elif age < 14:
                # Child safety note
                has_potentially_dangerous = False
                toxic_herbs = [
                    "附子", "川乌", "草乌", "天雄", "马钱子", "斑蝥",
                    "蟾酥", "砒霜", "雄黄", "轻粉", "红粉",
                ]
                for name in herb_names:
                    if name in toxic_herbs:
                        has_potentially_dangerous = True
                        warnings.append(SafetyWarning(
                            layer=3,
                            severity="high",
                            title="儿童慎用有毒药材",
                            detail=f"{name}含有毒性成分，儿童（{int(age)}岁）使用需严格遵医嘱",
                            herbs=[name],
                            action="谨慎",
                            source="特殊人群检查-儿童",
                        ))
                if not has_potentially_dangerous and herb_names:
                    warnings.append(SafetyWarning(
                        layer=3,
                        severity="medium",
                        title="儿童用药提醒",
                        detail=f"儿童（{int(age)}岁）用药剂量需遵医嘱调整",
                        herbs=list(herb_names),
                        action="告知医生",
                        source="特殊人群检查-儿童",
                    ))

            # --- Elderly check ---
            if age >= 65:
                if herb_names:
                    warnings.append(SafetyWarning(
                        layer=3,
                        severity="medium",
                        title="老年人用药提醒",
                        detail=f"老年患者（{int(age)}岁）肝肾功能可能减退，建议酌减用量",
                        herbs=list(herb_names),
                        action="告知医生",
                        source="特殊人群检查-老年",
                    ))

    return warnings
