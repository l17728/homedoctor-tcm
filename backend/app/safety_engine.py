"""Five-layer safety check engine — spec §15.3.

Layer 1a: 中药×中药配伍禁忌 (十八反十九畏) — hardcoded rules from DB
Layer 1b: 中西药交互检查 — drug×herb matching from DB
Layer 2:  剂量范围检查 — verify dosage within safe range
Layer 3:  特殊人群检查 — pregnancy/children/elderly contraindications
Layer 4:  AI 辅助分析 (placeholder for MVP)
Layer 5:  免责声明 — always attach disclaimer
"""

from __future__ import annotations


import logging

logger = logging.getLogger(__name__)
import json
from dataclasses import dataclass, field

from app.database import DbAdapter
from app.repository import current_tenant_id


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
# Cumulative toxicity — multiple herbs sharing the same toxic compound
# (checked after Layer 2 dosage, before Layer 3 special populations)
# ---------------------------------------------------------------------------

TOXIC_COMPONENT_GROUPS: dict[str, list[str]] = {
    "乌头碱": ["附子", "川乌", "草乌", "天雄", "雪上一枝蒿"],
    "马兜铃酸": ["关木通", "广防己", "青木香", "马兜铃", "天仙藤"],
    "雷公藤甲素": ["雷公藤", "昆明山海棠"],
    "汞": ["朱砂", "轻粉", "红粉"],
    "砷": ["砒石", "雄黄"],
}

HEPATOTOXIC_HERBS: list[str] = ["雷公藤", "黄药子", "苍耳子", "千里光", "艾叶", "川楝子", "苦楝皮"]
NEPHROTOXIC_HERBS: list[str] = ["关木通", "广防己", "青木香", "马兜铃", "寻骨风", "天仙藤"]

ALLERGY_CROSS_REACT: dict[str, list[str]] = {
    "青霉素": ["穿心莲", "功劳木"],
    "磺胺": ["黄芩苷"],
    "头孢": ["穿心莲"],
}

PROCESSING_MAP: dict[str, list[str]] = {
    "附子": ["制附子", "黑顺片", "白附片"],
    "半夏": ["法半夏", "姜半夏", "清半夏"],
    "川乌": ["制川乌"],
    "草乌": ["制草乌"],
    "天南星": ["制天南星", "胆南星"],
    "甘遂": ["醋甘遂"],
    "巴豆": ["巴豆霜"],
    "斑蝥": ["米斑蝥"],
}

_REVERSE_PROCESSING_MAP: dict[str, str] = {
    variant: base for base, variants in PROCESSING_MAP.items() for variant in variants
}


def _find_base_herb_for_processing(name: str) -> str | None:
    """If *name* is a processed variant, return its raw (more toxic) base herb."""
    return _REVERSE_PROCESSING_MAP.get(name)


# ---------------------------------------------------------------------------
# 儿童西药禁用清单 (spec §15.2.4) — Layer 3 硬规则，先于任何 AI 判断
# max_age: 该年龄以下禁用；keywords: 药品名称包含任一关键词即命中
# ---------------------------------------------------------------------------

PEDIATRIC_MEDICINE_PROHIBITIONS: list[dict] = [
    {
        "label": "氟喹诺酮类",
        "keywords": ["沙星", "左氧氟沙星", "环丙沙星", "莫西沙星", "诺氟沙星", "加替沙星"],
        "max_age": 14,
        "reason": "可能影响儿童软骨发育",
    },
    {
        "label": "四环素类",
        "keywords": ["四环素", "多西环素", "米诺环素", "土霉素"],
        "max_age": 8,
        "reason": "导致牙齿黄染及牙釉质发育不良（牙齿着色）",
    },
    {
        "label": "氨基糖苷类",
        "keywords": ["庆大霉素", "阿米卡星", "链霉素", "妥布霉素"],
        "max_age": 14,
        "reason": "具有耳毒性和肾毒性，可能造成不可逆听力损伤",
    },
    {
        "label": "含可待因制剂",
        "keywords": ["可待因"],
        "max_age": 12,
        "reason": "儿童使用可能引起危及生命的呼吸抑制",
    },
    {
        "label": "阿司匹林",
        "keywords": ["阿司匹林", "巴米尔"],
        "max_age": 16,
        "reason": "病毒感染期间使用可能诱发瑞氏综合征（急性脑病伴肝功能损害）",
    },
]


# ---------------------------------------------------------------------------
# 保健品/成药每日剂量上限 (spec §15.2.5) — 名称命中即输出上限提示
# check-v2 输入只有名称无剂量，因此以"提示核对说明书"的形式归入 Layer 2
# ---------------------------------------------------------------------------

DOSAGE_UPPER_LIMITS: list[dict] = [
    {"name": "鱼油（EPA+DHA）", "limit": "3g", "risk": "出血风险",
     "keywords": ["鱼油", "Omega-3", "欧米伽3", "深海鱼油"]},
    {"name": "辅酶Q10", "limit": "200mg", "risk": "失眠、胃肠不适",
     "keywords": ["辅酶Q10", "Q10辅酶", "CoQ10", "泛醌"]},
    {"name": "人参皂苷制品", "limit": "总皂苷200mg（按说明书）", "risk": "失眠、血压波动",
     "keywords": ["人参皂苷"]},
    {"name": "维生素A", "limit": "3000μg（约10000IU）", "risk": "肝毒性、致畸",
     "keywords": ["维生素A"]},
    {"name": "维生素D", "limit": "4000IU", "risk": "高钙血症",
     "keywords": ["维生素D"]},
    {"name": "维生素C", "limit": "2000mg", "risk": "腹泻、肾结石",
     "keywords": ["维生素C"]},
    {"name": "枸杞", "limit": "20g", "risk": "上火、腹泻",
     "keywords": ["枸杞"]},
    {"name": "黄芪", "limit": "30g", "risk": "高血压、失眠",
     "keywords": ["黄芪"]},
    {"name": "陈皮", "limit": "10g", "risk": "燥热伤津",
     "keywords": ["陈皮"]},
    {"name": "菊花", "limit": "15g", "risk": "脾胃虚寒者腹泻",
     "keywords": ["菊花"]},
]


def _match_medicine_keyword(medicine_name: str, keywords: list[str]) -> bool:
    """药品名称包含任一关键词即命中（如'左氧氟沙星片'含'沙星'）。"""
    return any(kw in medicine_name for kw in keywords)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

NSAID_NAME_KEYWORDS = (
    "布洛芬", "阿司匹林", "双氯芬酸", "萘普生", "吲哚美辛", "美洛昔康",
    "洛索洛芬", "塞来昔布", "依托考昔", "酮洛芬", "尼美舒利",
)


def _medicine_ingredients(row: dict) -> list[str]:
    raw = row.get("active_ingredients") or "[]"
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        parsed = []
    props = row.get("properties") or {}
    if isinstance(props, str):
        try:
            props = json.loads(props or "{}")
        except (json.JSONDecodeError, TypeError):
            props = {}
    if not parsed and isinstance(props, dict):
        parsed = props.get("active_ingredients") or props.get("有效成分") or []
    if isinstance(parsed, str):
        parsed = [part.strip() for part in parsed.replace("，", ",").split(",") if part.strip()]
    ingredients: list[str] = []
    for item in parsed if isinstance(parsed, list) else []:
        if isinstance(item, dict):
            item = item.get("name") or item.get("成分") or item.get("ingredient")
        if isinstance(item, str) and item.strip():
            ingredients.append(item.strip())
    return ingredients


def _check_medication_overlap(medicines: list[dict]) -> list[SafetyWarning]:
    """Flag repeated active ingredients and duplicate NSAID use in the cabinet.

    Reference: NHS advises against taking ibuprofen with other NSAIDs; FDA OTC
    labeling highlights NSAIDs and duplicate active ingredients such as
    acetaminophen. The app warns conservatively when dose details are missing.
    """
    warnings: list[SafetyWarning] = []
    by_ingredient: dict[str, tuple[str, set[str]]] = {}
    nsaids: list[str] = []
    for medicine in medicines:
        name = str(medicine.get("name") or "")
        drug_class = str(medicine.get("drug_class") or "").casefold()
        if "nsaid" in drug_class or "非甾体抗炎" in drug_class or any(k in name for k in NSAID_NAME_KEYWORDS):
            nsaids.append(name)
        for ingredient in _medicine_ingredients(medicine):
            key = ingredient.casefold().replace(" ", "")
            display, names = by_ingredient.setdefault(key, (ingredient, set()))
            names.add(name)

    for ingredient, names in by_ingredient.values():
        if len(names) < 2:
            continue
        joined_names = "、".join(sorted(names))
        warnings.append(SafetyWarning(
            layer=2, severity="medium", title=f"有效成分重复用药（{ingredient}）",
            detail=(f"{joined_names}均含有效成分“{ingredient}”。请核对每种药品的含量及累计日剂量；"
                    "系统未获得可靠的每次剂量，不能判定是否超量。"),
            herbs=[], action="告知医生", source="成分重叠检查",
        ))
    if len(set(nsaids)) >= 2:
        joined_names = "、".join(sorted(set(nsaids)))
        warnings.append(SafetyWarning(
            layer=1, severity="high", title="重复使用非甾体抗炎药",
            detail=(f"药箱中同时选择了 {joined_names}。两种 NSAID 不应自行同时使用，"
                    "除非医生明确指示；请先向医生或药师确认。"),
            herbs=[], action="告知医生", source="重复药理机制检查（NSAID）",
        ))
    return warnings

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

    # --- Resolve herbs: look up DB info (Expert #14: processing-state aware) ---
    herb_info: dict[str, dict] = {}
    unknown_herbs: list[str] = []
    processed_variants_found: dict[str, str] = {}

    if herb_names:
        placeholders = ",".join("?" * len(herb_names))
        ke_rows = await db.query(
            f"""SELECT ke.id, ke.title, ke.properties, ke.category,
                      COALESCE((SELECT trust_level FROM knowledge_provenance
                        WHERE entity_id = ke.id ORDER BY imported_at DESC LIMIT 1), 'C') AS trust_level
                 FROM knowledge_entities ke
                WHERE ke.entity_type='herb' AND ke.title IN ({placeholders}) AND ke.status='active'
                ORDER BY CASE COALESCE((SELECT trust_level FROM knowledge_provenance
                        WHERE entity_id = ke.id ORDER BY imported_at DESC LIMIT 1), 'C')
                    WHEN 'S' THEN 0 WHEN 'A' THEN 1 WHEN 'B' THEN 2 ELSE 3 END""",
            tuple(herb_names),
        )
        ke_by_name: dict[str, dict] = {}
        for row in ke_rows:
            name = row["title"]
            if name not in ke_by_name or row.get("trust_level", "C") < ke_by_name[name].get("trust_level", "C"):
                ke_by_name[name] = row

        legacy_rows = await db.query(
            f"SELECT * FROM herbs WHERE name IN ({placeholders})",
            tuple(herb_names),
        )
        legacy_by_name = {r["name"]: r for r in legacy_rows}

        for name in herb_names:
            ke_row = ke_by_name.get(name)
            if ke_row and ke_row.get("trust_level") in ("S", "A"):
                import json as _json
                props = _json.loads(ke_row["properties"]) if isinstance(ke_row.get("properties"), str) else ke_row.get("properties", {})
                herb_info[name] = {
                    "name": ke_row["title"],
                    "nature": props.get("nature", ""),
                    "flavor": props.get("flavor", ""),
                    "toxicity": props.get("toxicity", "无毒"),
                    "dosage_min_g": props.get("dosage_min_g"),
                    "dosage_max_g": props.get("dosage_max_g"),
                    "contraindications": props.get("contraindications", ""),
                    "category": props.get("category", ke_row.get("category", "")),
                    "properties": ke_row.get("properties", "{}"),
                }
            else:
                legacy_row = legacy_by_name.get(name)
                if legacy_row:
                    herb_info[name] = legacy_row
                else:
                    unknown_herbs.append(name)

            base_herb = _find_base_herb_for_processing(name)
            if base_herb:
                processed_variants_found[name] = base_herb

    unknown_medicines: list[str] = []
    tenant = current_tenant_id.get()
    if medicine_names:
        med_placeholders = ",".join("?" * len(medicine_names))
        med_rows = await db.query(
            f"SELECT name, drug_class, active_ingredients, properties FROM medicines "
            f"WHERE name IN ({med_placeholders}) AND tenant_id = ?",
            (*medicine_names, tenant),
        )
        known_meds = {r["name"] for r in med_rows}
        unknown_medicines = [m for m in medicine_names if m not in known_meds]
        for warning in _check_medication_overlap(med_rows):
            _add(warning)

    # --- P0 炮制品归一化：炮制品名按基原名参与全部规则匹配 ---
    # 展示层保留"原始名(基原名)"（如 制附子(附子)），匹配层使用基原名（附子），
    # 使 Layer1a/1b、妊娠禁忌、儿童毒性、累积毒性全部按生品标准执行。
    effective_herbs: list[str] = []
    display_of: dict[str, str] = {}
    for name in herb_names:
        base = _find_base_herb_for_processing(name)
        effective = base if base else name
        if effective in display_of:
            continue  # 炮制品与基原同时出现时按基原去重
        display_of[effective] = f"{name}({base})" if base else name
        effective_herbs.append(effective)

    def _to_display(w: SafetyWarning) -> SafetyWarning:
        w.herbs = [display_of.get(h, h) for h in w.herbs]
        return w

    # 基原药材信息补全：炮制品的剂量/禁忌说明按基原名从库中解析
    missing_bases = sorted({b for b in processed_variants_found.values() if b not in herb_info})
    if missing_bases:
        base_rows = await db.query(
            f"SELECT * FROM herbs WHERE name IN ({','.join('?' * len(missing_bases))})",
            tuple(missing_bases),
        )
        for r in base_rows:
            herb_info.setdefault(r["name"], r)

    # --- Layer 1a: 中药×中药配伍禁忌 (十八反十九畏) — 炮制品按基原名匹配 ---
    layer1a_warnings = await _check_herb_herb_contraindications(db, effective_herbs)
    for w in layer1a_warnings:
        _add(_to_display(w))

    # --- Layer 1b: 中西药交互检查 ---
    layer1b_warnings = await _check_herb_drug_interactions(db, effective_herbs, medicine_names)
    for w in layer1b_warnings:
        _add(_to_display(w))

    # --- Layer 1c: 食物禁忌检查 (food-drug / food-herb interactions) ---
    layer1c_warnings = await _check_food_interactions(db, effective_herbs, medicine_names)
    for w in layer1c_warnings:
        _add(_to_display(w))

    # --- Layer 2: 剂量范围检查（按用户提供的原始名 + 剂量） ---
    layer2_warnings = await _check_dosage(herb_names, herb_info, dosages)
    for w in layer2_warnings:
        _add(w)

    # --- Layer 2: 保健品/成药每日剂量上限提示 (spec §15.2.5) ---
    for w in _check_medicine_dosage_limits(medicine_names):
        _add(w)

    # --- Cumulative toxicity (after dosage check, before special populations) ---
    cumulative_warnings = await _check_cumulative_toxicity(effective_herbs, herb_info, dosages)
    for w in cumulative_warnings:
        _add(_to_display(w))

    # --- Layer 3: 特殊人群检查（含儿童西药禁用清单 §15.2.4） ---
    layer3_warnings = _check_special_populations(
        effective_herbs, herb_info, user_profile, medicine_names,
    )
    for w in layer3_warnings:
        _add(_to_display(w))

    # Pediatric dosing follows spec §15.2.6. This is an upper-bound reference
    # only; absence of child-specific data always requires clinician review.
    if user_profile:
        try:
            child_age = float(user_profile.get("age"))
            child_weight = float(user_profile.get("weight_kg")) if user_profile.get("weight_kg") else None
        except (TypeError, ValueError):
            child_age, child_weight = 0, None
        if 0 < child_age < 18:
            for herb in effective_herbs:
                info = herb_info.get(herb, {})
                props = info.get("properties", {})
                if isinstance(props, str):
                    try:
                        props = json.loads(props or "{}")
                    except (json.JSONDecodeError, TypeError):
                        props = {}
                if isinstance(props, dict) and props.get("儿童剂量"):
                    continue
                adult_max = info.get("dosage_max_g")
                if child_weight and adult_max is not None:
                    try:
                        reference_max = float(adult_max) * (child_weight / 50) * 0.8
                        dose_detail = (
                            f"按规格中的 Young's 体重折算，成人上限 {adult_max}g 对应参考上限 "
                            f"约 {reference_max:.2f}g；该值不构成儿童用药建议，须由医生/药师确认。"
                        )
                    except (TypeError, ValueError):
                        dose_detail = "缺少可用的成人剂量数据，无法折算；请咨询医生/药师。"
                else:
                    dose_detail = "缺少体重或可用的成人剂量数据，无法折算；请咨询医生/药师。"
                _add(SafetyWarning(
                    layer=3, severity="medium", title="儿童剂量需专业确认",
                    detail=f"{herb}未配置儿童专用剂量。{dose_detail}",
                    herbs=[display_of.get(herb, herb)], action="告知医生",
                    source="特殊人群检查-儿童剂量（spec §15.2.6）",
                ))

    # --- Layer 4: AI 辅助分析 (placeholder) ---
    # No-op for MVP. Future: send structured prompt to AI, parse response.

    # --- Processing-state awareness (Expert #14) ---
    for processed_name, base_herb in processed_variants_found.items():
        _add(SafetyWarning(
            layer=3,
            severity="low",
            title="炮制减毒提示",
            detail=f"{processed_name}为{base_herb}的炮制品，毒性已降低，"
                   f"但配伍禁忌规则仍按{base_herb}生品标准执行",
            herbs=[processed_name],
            action="告知医生",
            source="炮制状态识别",
        ))

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

    all_rules = await db.query(
        """SELECT * FROM safety_rules WHERE enabled = 1
           AND rule_type IN ('十八反', '十九畏')"""
    )
    herb_set = set(herb_names)
    seen_ids: set[str] = set()
    for r in all_rules:
        if r["id"] in seen_ids:
            continue
        a, b = r.get("drug_a", ""), r.get("drug_b", "")
        if a in herb_set and b in herb_set:
            seen_ids.add(r["id"])
            warnings.append(SafetyWarning(
                layer=1,
                severity="critical",
                title=f"配伍禁忌（{r['rule_type']}）",
                detail=r["mechanism"],
                herbs=[a, b],
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
    tenant = current_tenant_id.get()
    row = await db.query_one(
        "SELECT properties FROM medicines WHERE name = ? AND tenant_id = ? LIMIT 1",
        (medicine_name, tenant),
    )
    # SECURITY (F3): no cross-tenant fallback — a same-named medicine from
    # another family's cabinet must never influence this family's safety
    # verdict. Fall through to the conservative default instead.
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

    western_drugs: list[str] = []
    for drug in medicine_names:
        drug_class = await _get_medicine_drug_class(db, drug)
        if drug_class == "西药":
            western_drugs.append(drug)
    if not western_drugs:
        return warnings

    all_rules = await db.query(
        """SELECT * FROM safety_rules WHERE enabled = 1
           AND rule_type = '中西药交互'"""
    )
    herb_set = set(herb_names)
    drug_set = set(western_drugs)
    seen_ids: set[str] = set()
    for r in all_rules:
        if r["id"] in seen_ids:
            continue
        drug_a = r.get("drug_a", "")
        drug_b = r.get("drug_b", "")
        matched_herb = None
        if drug_a in drug_set and drug_b in herb_set:
            matched_herb = drug_b
        elif drug_a in drug_set:
            for wd in western_drugs:
                if wd in drug_a and drug_b in herb_set:
                    matched_herb = drug_b
                    break
        if matched_herb:
            seen_ids.add(r["id"])
            sev = r["severity"]
            action = "禁止" if sev == "critical" else "谨慎"
            warnings.append(SafetyWarning(
                layer=1,
                severity=sev,
                title=f"中西药交互（{r.get('source', '')}）",
                detail=r["mechanism"],
                herbs=[matched_herb],
                action=action,
                source=r.get("source", ""),
            ))
    return warnings


# ---------------------------------------------------------------------------
# Layer 1c: 食物禁忌检查 (food-drug / food-herb interactions)
# ---------------------------------------------------------------------------

async def _check_food_interactions(
    db: DbAdapter, herb_names: list[str], medicine_names: list[str]
) -> list[SafetyWarning]:
    """Check food-drug and food-herb interaction rules (rule_type='食物禁忌').

    Matches where a herb name or medicine name appears as drug_a or drug_b
    in a 食物禁忌 rule.
    """
    warnings: list[SafetyWarning] = []
    all_items = list(herb_names) + list(medicine_names)
    if not all_items:
        return warnings

    all_rules = await db.query(
        """SELECT * FROM safety_rules WHERE enabled = 1
           AND rule_type = '食物禁忌'"""
    )
    item_set = set(all_items)
    seen_ids: set[str] = set()
    for r in all_rules:
        if r["id"] in seen_ids:
            continue
        drug_a = r.get("drug_a", "")
        drug_b = r.get("drug_b", "")
        matched_item = None
        other = None
        if drug_a in item_set:
            matched_item = drug_a
            other = drug_b
        elif drug_b in item_set:
            matched_item = drug_b
            other = drug_a
        if matched_item:
            seen_ids.add(r["id"])
            sev = r["severity"]
            action = "禁止" if sev == "critical" else "谨慎"
            affected = [matched_item]
            if other:
                affected.append(other)
            warnings.append(SafetyWarning(
                layer=1,
                severity=sev,
                title=f"食物禁忌（{r.get('source', '')}）",
                detail=r["mechanism"],
                herbs=affected,
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
        # 炮制品按基原的剂量范围校验（如 制附子 按 附子 3-15g）
        info = herb_info.get(name)
        if not info:
            base = _find_base_herb_for_processing(name)
            if base:
                info = herb_info.get(base)
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


def _check_medicine_dosage_limits(medicine_names: list[str]) -> list[SafetyWarning]:
    """保健品/成药每日剂量上限提示 (spec §15.2.5).

    check-v2 输入只有药品名称没有剂量，因此名称命中（含别名/关键词）时
    输出 high 级提示，提醒用户核对说明书、不要超过每日上限。
    """
    warnings: list[SafetyWarning] = []
    for med in medicine_names:
        for rule in DOSAGE_UPPER_LIMITS:
            if _match_medicine_keyword(med, rule["keywords"]):
                warnings.append(SafetyWarning(
                    layer=2,
                    severity="high",
                    title="剂量上限提示",
                    detail=(f"服用{rule['name']}请勿超过每日上限{rule['limit']}，"
                            f"超量风险：{rule['risk']}，请核对说明书"),
                    herbs=[med],
                    action="告知医生",
                    source="剂量上限（spec §15.2.5）",
                ))
                break  # 每个药品只命中第一条规则，避免重复提示
    return warnings


async def _check_cumulative_toxicity(
    herb_names: list[str],
    herb_info: dict[str, dict],
    dosages: dict[str, float],
) -> list[SafetyWarning]:
    """Check if multiple herbs share the same toxic compound.

    Even if no single herb exceeds its dosage limit, combining two or more
    herbs that contain the same toxic compound (e.g. 乌头碱 from both 附子
    and 川乌) can cause cumulative poisoning.
    """
    warnings: list[SafetyWarning] = []
    for compound, herbs in TOXIC_COMPONENT_GROUPS.items():
        found = [h for h in herb_names if h in herbs]
        if len(found) >= 2:
            warnings.append(SafetyWarning(
                layer=2,
                severity="critical",
                title=f"累积毒性风险（{compound}）",
                detail=f"{', '.join(found)}均含{compound}，联合使用可能导致{compound}累积中毒",
                herbs=found,
                action="禁止",
                source="累积毒性检查",
            ))
    return warnings


# ---------------------------------------------------------------------------
# Layer 3: 特殊人群检查
# ---------------------------------------------------------------------------

def _check_special_populations(
    herb_names: list[str],
    herb_info: dict[str, dict],
    user_profile: dict | None,
    medicine_names: list[str] | None = None,
) -> list[SafetyWarning]:
    """Check contraindications for special populations."""
    warnings: list[SafetyWarning] = []

    if medicine_names is None:
        medicine_names = []

    if not user_profile:
        return warnings

    is_pregnant = user_profile.get("is_pregnant", False)
    age = user_profile.get("age")

    # --- Liver disease check ---
    if user_profile.get("liver_disease"):
        for name in herb_names:
            if name in HEPATOTOXIC_HERBS:
                warnings.append(SafetyWarning(
                    layer=3,
                    severity="high",
                    title="肝病患者慎用",
                    detail=f"{name}具有肝毒性，肝功能不全患者禁用或慎用",
                    herbs=[name],
                    action="禁止",
                    source="特殊人群-肝病",
                ))

    # --- Kidney disease check ---
    if user_profile.get("kidney_disease"):
        for name in herb_names:
            if name in NEPHROTOXIC_HERBS:
                warnings.append(SafetyWarning(
                    layer=3,
                    severity="high",
                    title="肾病患者禁用",
                    detail=f"{name}具有肾毒性，肾功能不全患者禁用",
                    herbs=[name],
                    action="禁止",
                    source="特殊人群-肾病",
                ))

    # --- Pregnancy check ---
    if is_pregnant:
        pregnancy_keywords = ["孕妇", "妊娠", "怀孕", "慎用", "禁用"]
        # 硬编码绝对禁忌清单（spec §15.2.4）— 不依赖 DB 是否有该药材记录
        pregnancy_dangerous = [
            "桃仁", "红花", "三棱", "莪术", "水蛭", "虻虫", "斑蝥",
            "麝香", "巴豆", "甘遂", "大戟", "芫花", "牵牛子", "商陆",
            "麝香", "蜈蚣", "全蝎", "附子", "川乌", "草乌",
        ]
        for name in herb_names:
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
                continue
            info = herb_info.get(name)
            if not info:
                continue
            contraindications = info.get("contraindications") or ""
            # Check if any pregnancy keyword appears in contraindications
            if any(kw in contraindications for kw in pregnancy_keywords):
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
            # --- 儿童西药禁用清单 (spec §15.2.4) — 硬规则，先于 AI 判断 ---
            for med in medicine_names:
                for rule in PEDIATRIC_MEDICINE_PROHIBITIONS:
                    if age < rule["max_age"] and _match_medicine_keyword(med, rule["keywords"]):
                        warnings.append(SafetyWarning(
                            layer=3,
                            severity="high",
                            title=f"儿童禁用（{rule['label']}）",
                            detail=(f"{med}属{rule['label']}，{rule['max_age']}岁以下儿童禁用："
                                    f"{rule['reason']}，请咨询儿科医生"),
                            herbs=[med],
                            action="禁止",
                            source="特殊人群检查-儿童",
                        ))

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

    # --- Allergy cross-reactivity check (Clinical gap #6) ---
    allergies = user_profile.get("allergies", []) if user_profile else []
    if allergies and isinstance(allergies, list):
        for allergy in allergies:
            cross_herbs = ALLERGY_CROSS_REACT.get(allergy)
            if not cross_herbs:
                continue
            for herb_name in herb_names:
                if herb_name in cross_herbs:
                    warnings.append(SafetyWarning(
                        layer=3,
                        severity="high",
                        title="药物过敏交叉反应",
                        detail=f"患者对{allergy}过敏，{herb_name}可能存在交叉过敏风险",
                        herbs=[herb_name],
                        action="谨慎",
                        source="过敏交叉反应检查",
                    ))

    return warnings
