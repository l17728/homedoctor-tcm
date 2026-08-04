"""Database seed data — safety rules, test data, therapy data."""

from __future__ import annotations

import json
import logging
from app.db.adapter import DbAdapter

logger = logging.getLogger(__name__)

__all__ = ["seed_safety_rules", "seed_test_data", "seed_therapy_data"]

async def seed_safety_rules(db: DbAdapter) -> None:
    """Seed hardcoded safety rules from spec §15.2 — idempotent."""
    rules: list[dict[str, Any]] = []

    # --- 十八反 (18 mutual incompatibilities) ---
    wutou_herbs = ["附子", "川乌", "草乌", "天雄"]
    for w in wutou_herbs:
        for partner in ["半夏", "瓜蒌", "贝母", "白蔹", "白及"]:
            rules.append({
                "id": f"18fan-{w}-{partner}",
                "rule_type": "十八反",
                "drug_a": w,
                "drug_b": partner,
                "severity": "critical",
                "mechanism": f"乌头类({w})与{partner}属于十八反禁忌配伍",
                "action": "禁止同用",
                "source": "十八反",
            })
    for partner in ["甘遂", "京大戟", "芫花", "海藻"]:
        rules.append({
            "id": f"18fan-甘草-{partner}",
            "rule_type": "十八反",
            "drug_a": "甘草",
            "drug_b": partner,
            "severity": "critical",
            "mechanism": f"甘草与{partner}属于十八反禁忌配伍",
            "action": "禁止同用",
            "source": "十八反",
        })
    for partner in ["人参", "党参", "丹参", "玄参", "沙参", "苦参", "细辛", "芍药"]:
        rules.append({
            "id": f"18fan-藜芦-{partner}",
            "rule_type": "十八反",
            "drug_a": "藜芦",
            "drug_b": partner,
            "severity": "critical",
            "mechanism": f"藜芦与{partner}属于十八反禁忌配伍",
            "action": "禁止同用",
            "source": "十八反",
        })

    # --- 十九畏 (19 mutual antagonisms) ---
    antagonisms = [
        ("硫磺", "朴硝"), ("水银", "砒霜"), ("狼毒", "密陀僧"),
        ("巴豆", "牵牛子"), ("丁香", "郁金"), ("牙硝", "三棱"),
        ("川乌", "犀角"), ("草乌", "犀角"), ("人参", "五灵脂"),
        ("官桂", "石脂"),
    ]
    for a, b in antagonisms:
        rules.append({
            "id": f"19wei-{a}-{b}",
            "rule_type": "十九畏",
            "drug_a": a,
            "drug_b": b,
            "severity": "critical",
            "mechanism": f"{a}与{b}属于十九畏禁忌配伍",
            "action": "禁止同用",
            "source": "十九畏",
        })

    # --- 中西药致命交互 R-01 to R-10 ---
    herb_drug_rules = [
        {
            "id": "R-01",
            "rule_type": "中西药交互",
            "drug_a": "华法林",
            "drug_b": None,
            "severity": "critical",
            "mechanism": "协同抗凝，可能导致颅内出血",
            "action": "禁止同用",
            "source": "中西药交互R-01",
            "_herbs": ["当归", "丹参", "三七", "红花", "水蛭", "银杏叶"],
        },
        {
            "id": "R-02",
            "rule_type": "中西药交互",
            "drug_a": "华法林",
            "drug_b": None,
            "severity": "critical",
            "mechanism": "诱导CYP酶，血栓风险",
            "action": "禁止同用",
            "source": "中西药交互R-02",
            "_herbs": ["人参"],
        },
        {
            "id": "R-03",
            "rule_type": "中西药交互",
            "drug_a": "地高辛",
            "drug_b": None,
            "severity": "critical",
            "mechanism": "心律失常协同，洋地黄中毒",
            "action": "禁止同用",
            "source": "中西药交互R-03",
            "_herbs": ["麻黄", "桂枝"],
        },
        {
            "id": "R-04",
            "rule_type": "中西药交互",
            "drug_a": "MAOI类药物",
            "drug_b": None,
            "severity": "critical",
            "mechanism": "高血压危象，致命血压飙升",
            "action": "禁止同用",
            "source": "中西药交互R-04",
            "_herbs": ["麻黄"],
        },
        {
            "id": "R-05",
            "rule_type": "中西药交互",
            "drug_a": "他汀类",
            "drug_b": None,
            "severity": "critical",
            "mechanism": "CYP3A4酶抑制，横纹肌溶解",
            "action": "禁止同用",
            "source": "中西药交互R-05",
            "_herbs": ["五味子"],
        },
        {
            "id": "R-06",
            "rule_type": "中西药交互",
            "drug_a": "降糖药",
            "drug_b": None,
            "severity": "warning",
            "mechanism": "协同降糖，严重低血糖",
            "action": "谨慎同用，需监测血糖",
            "source": "中西药交互R-06",
            "_herbs": ["葛根", "苦瓜", "桑叶"],
        },
        {
            "id": "R-07",
            "rule_type": "中西药交互",
            "drug_a": "降压药",
            "drug_b": None,
            "severity": "warning",
            "mechanism": "甘草含甘草酸导致水钠潴留，血压反升",
            "action": "谨慎同用，需监测血压",
            "source": "中西药交互R-07",
            "_herbs": ["甘草"],
        },
        {
            "id": "R-08",
            "rule_type": "中西药交互",
            "drug_a": "抗血小板药",
            "drug_b": None,
            "severity": "critical",
            "mechanism": "协同抗血小板，出血风险",
            "action": "禁止同用",
            "source": "中西药交互R-08",
            "_herbs": ["银杏叶", "丹参", "当归", "三七"],
        },
        {
            "id": "R-09",
            "rule_type": "中西药交互",
            "drug_a": "四环素",
            "drug_b": None,
            "severity": "warning",
            "mechanism": "鳌合反应，抗生素失效",
            "action": "禁止同用",
            "source": "中西药交互R-09",
            "_herbs": ["石膏", "牡蛎", "龙骨"],
        },
        {
            "id": "R-10",
            "rule_type": "中西药交互",
            "drug_a": "铁剂",
            "drug_b": None,
            "severity": "warning",
            "mechanism": "不溶性鞣酸铁，吸收丧失",
            "action": "禁止同用",
            "source": "中西药交互R-10",
            "_herbs": ["大黄", "虎杖", "地榆"],
        },
        {
            "id": "R-11",
            "rule_type": "中西药交互",
            "drug_a": "SSRI抗抑郁药",
            "drug_b": None,
            "severity": "warning",
            "mechanism": "银杏叶增强5-HT活性，合用增加5-HT综合征风险",
            "action": "谨慎同用",
            "source": "中西药交互R-11",
            "_herbs": ["银杏叶"],
        },
        {
            "id": "R-12",
            "rule_type": "中西药交互",
            "drug_a": "华法林",
            "drug_b": None,
            "severity": "warning",
            "mechanism": "人参可能降低华法林抗凝效果，增加血栓风险",
            "action": "谨慎同用，需监测INR",
            "source": "中西药交互R-12",
            "_herbs": ["人参"],
        },
        {
            "id": "R-13",
            "rule_type": "中西药交互",
            "drug_a": "CYP3A4底物",
            "drug_b": None,
            "severity": "warning",
            "mechanism": "贯叶连翘(圣约翰草)诱导CYP3A4酶，降低多种药物血药浓度",
            "action": "谨慎同用",
            "source": "中西药交互R-13",
            "_herbs": ["贯叶连翘"],
        },
        {
            "id": "R-14",
            "rule_type": "中西药交互",
            "drug_a": "环孢素",
            "drug_b": None,
            "severity": "warning",
            "mechanism": "黄连素可能降低环孢素免疫抑制效果",
            "action": "谨慎同用，需监测血药浓度",
            "source": "中西药交互R-14",
            "_herbs": ["黄连素", "黄连"],
        },
        {
            "id": "R-15",
            "rule_type": "中西药交互",
            "drug_a": "锂剂",
            "drug_b": None,
            "severity": "warning",
            "mechanism": "丹参可能增加锂离子排泄减少或重吸收，导致锂中毒风险",
            "action": "谨慎同用，需监测血锂浓度",
            "source": "中西药交互R-15",
            "_herbs": ["丹参"],
        },
        {
            "id": "R-16",
            "rule_type": "中西药交互",
            "drug_a": "抗凝药",
            "drug_b": None,
            "severity": "warning",
            "mechanism": "大蒜具有抗血小板作用，合用增加出血风险",
            "action": "谨慎同用",
            "source": "中西药交互R-16",
            "_herbs": ["大蒜"],
        },
        {
            "id": "R-17",
            "rule_type": "中西药交互",
            "drug_a": "抗凝药",
            "drug_b": None,
            "severity": "warning",
            "mechanism": "生姜具有轻度抗血小板作用，合用增加出血风险",
            "action": "谨慎同用",
            "source": "中西药交互R-17",
            "_herbs": ["生姜"],
        },
        {
            "id": "R-18",
            "rule_type": "中西药交互",
            "drug_a": "抗凝药",
            "drug_b": None,
            "severity": "warning",
            "mechanism": "鱼油含Omega-3脂肪酸，高剂量可增加出血风险",
            "action": "谨慎同用",
            "source": "中西药交互R-18",
            "_herbs": ["鱼油"],
        },
        {
            "id": "R-19",
            "rule_type": "中西药交互",
            "drug_a": "降糖药",
            "drug_b": None,
            "severity": "warning",
            "mechanism": "苦瓜具有降糖作用，合用可能导致严重低血糖",
            "action": "谨慎同用，需监测血糖",
            "source": "中西药交互R-19",
            "_herbs": ["苦瓜"],
        },
        {
            "id": "R-20",
            "rule_type": "中西药交互",
            "drug_a": "利尿药",
            "drug_b": None,
            "severity": "warning",
            "mechanism": "甘草含甘草酸引起假性醛固酮增多症，合用利尿药可致严重低钾血症",
            "action": "谨慎同用，需监测血钾",
            "source": "中西药交互R-20",
            "_herbs": ["甘草"],
        },
        {
            "id": "R-21",
            "rule_type": "中西药交互",
            "drug_a": "地高辛",
            "drug_b": None,
            "severity": "warning",
            "mechanism": "甘草可致低钾血症，低钾增加地高辛毒性及心律失常风险",
            "action": "谨慎同用，需监测血钾和地高辛浓度",
            "source": "中西药交互R-21",
            "_herbs": ["甘草"],
        },
        {
            "id": "R-22",
            "rule_type": "中西药交互",
            "drug_a": "CYP3A4底物",
            "drug_b": None,
            "severity": "warning",
            "mechanism": "五味子可抑制或诱导CYP3A4酶，影响多种药物代谢",
            "action": "谨慎同用",
            "source": "中西药交互R-22",
            "_herbs": ["五味子"],
        },
        {
            "id": "R-23",
            "rule_type": "中西药交互",
            "drug_a": "CYP1A2底物",
            "drug_b": None,
            "severity": "warning",
            "mechanism": "黄芩可抑制CYP1A2酶，影响茶碱、咖啡因等药物代谢",
            "action": "谨慎同用",
            "source": "中西药交互R-23",
            "_herbs": ["黄芩"],
        },
        {
            "id": "R-24",
            "rule_type": "中西药交互",
            "drug_a": "免疫抑制剂",
            "drug_b": None,
            "severity": "warning",
            "mechanism": "柴胡具有免疫调节作用，可能影响免疫抑制剂疗效",
            "action": "谨慎同用",
            "source": "中西药交互R-24",
            "_herbs": ["柴胡"],
        },
        {
            "id": "R-25",
            "rule_type": "中西药交互",
            "drug_a": "抗凝药",
            "drug_b": None,
            "severity": "warning",
            "mechanism": "蒲黄具有活血化瘀作用，合用抗凝药增加出血风险",
            "action": "谨慎同用",
            "source": "中西药交互R-25",
            "_herbs": ["蒲黄"],
        },
        {
            "id": "R-26",
            "rule_type": "中西药交互",
            "drug_a": "抗血小板药",
            "drug_b": None,
            "severity": "warning",
            "mechanism": "三七具有抗血小板聚集作用，合用增加出血风险",
            "action": "谨慎同用",
            "source": "中西药交互R-26",
            "_herbs": ["三七"],
        },
        {
            "id": "R-27",
            "rule_type": "中西药交互",
            "drug_a": "抗凝药",
            "drug_b": None,
            "severity": "critical",
            "mechanism": "水蛭含水蛭素有强抗凝作用，合用抗凝药可致严重出血",
            "action": "禁止同用",
            "source": "中西药交互R-27",
            "_herbs": ["水蛭"],
        },
        {
            "id": "R-28",
            "rule_type": "中西药交互",
            "drug_a": "铁剂",
            "drug_b": None,
            "severity": "warning",
            "mechanism": "地榆含大量鞣质，与铁剂形成不溶性复合物影响吸收",
            "action": "间隔2小时以上",
            "source": "中西药交互R-28",
            "_herbs": ["地榆"],
        },
        {
            "id": "R-29",
            "rule_type": "中西药交互",
            "drug_a": "铁剂",
            "drug_b": None,
            "severity": "warning",
            "mechanism": "五倍子含大量鞣酸，与铁剂结合形成不溶性鞣酸铁",
            "action": "间隔2小时以上",
            "source": "中西药交互R-29",
            "_herbs": ["五倍子"],
        },
        {
            "id": "R-30",
            "rule_type": "中西药交互",
            "drug_a": "铁剂",
            "drug_b": None,
            "severity": "warning",
            "mechanism": "诃子含鞣质，与铁剂结合影响吸收",
            "action": "间隔2小时以上",
            "source": "中西药交互R-30",
            "_herbs": ["诃子"],
        },
    ]

    # Expand herb-drug rules: each herb × drug becomes one row
    for r in herb_drug_rules:
        herbs_list = r.pop("_herbs")
        for herb in herbs_list:
            rules.append({**r, "id": f"{r['id']}-{herb}", "drug_b": herb})

    # --- 食物禁忌 (Food-drug / food-herb interaction rules) ---
    food_rules = [
        ("食物禁忌-F01", "葡萄柚", "降压药(钙通道阻滞剂)", "warning",
         "葡萄柚汁抑制CYP3A4，显著升高降压药血药浓度", "避免同食", "食物禁忌"),
        ("食物禁忌-F02", "萝卜", "人参", "warning",
         "萝卜破气，与人参补气功效相抵消", "避免同食", "食物禁忌"),
        ("食物禁忌-F03", "浓茶", "铁剂", "warning",
         "茶鞣酸与铁结合形成不溶性复合物，影响铁吸收", "间隔2小时", "食物禁忌"),
        ("食物禁忌-F04", "牛奶", "四环素类", "warning",
         "钙离子与四环素发生螯合反应，影响抗生素吸收", "间隔2小时", "食物禁忌"),
        ("食物禁忌-F05", "酒精", "头孢类", "critical",
         "双硫仑反应——面部潮红、心悸、呼吸困难，严重可危及生命", "绝对禁酒", "食物禁忌"),
        ("食物禁忌-F06", "酒精", "甲硝唑", "critical",
         "双硫仑反应——面部潮红、恶心、心悸", "绝对禁酒", "食物禁忌"),
    ]
    for rule_id, food, drug, severity, mechanism, action, rule_type in food_rules:
        rules.append({
            "id": rule_id,
            "rule_type": rule_type,
            "drug_a": food,
            "drug_b": drug,
            "severity": severity,
            "mechanism": mechanism,
            "action": action,
            "source": rule_type,
        })

    # Insert all rules idempotently
    for rule in rules:
        await db.execute(
            """INSERT OR IGNORE INTO safety_rules
               (id, rule_type, drug_a, drug_b, severity, mechanism, action, source, enabled)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)""",
            (
                rule["id"], rule["rule_type"], rule["drug_a"], rule["drug_b"],
                rule["severity"], rule["mechanism"], rule["action"], rule["source"],
            ),
        )


async def seed_test_data(db: DbAdapter) -> None:
    """Seed 2-3 test herbs and formulas for development."""
    herbs = [
        {
            "id": "herb-001", "name": "黄芪", "aliases": "绵芪,黄耆",
            "nature": "微温", "flavor": "甘", "meridians": "脾,肺",
            "efficacy": "补气升阳，固表止汗，利水消肿，生津养血，行滞通痹，托毒排脓，敛疮生肌",
            "indications": "气虚乏力，食少便溏，中气下陷，久泻脱肛，便血崩漏，表虚自汗",
            "contraindications": "表实邪盛，气滞湿阻，食积内停，阴虚阳亢，疮痈初起或溃后热毒尚盛者",
            "dosage_min_g": 9, "dosage_max_g": 30, "toxicity": "无毒",
            "category": "补虚药", "properties": json.dumps({"pharmacologicalClass": "免疫调节"}, ensure_ascii=False),
        },
        {
            "id": "herb-002", "name": "当归", "aliases": "秦归,云归",
            "nature": "温", "flavor": "甘,辛", "meridians": "肝,心,脾",
            "efficacy": "补血活血，调经止痛，润肠通便",
            "indications": "血虚萎黄，眩晕心悸，月经不调，经闭痛经，虚寒腹痛，风湿痹痛",
            "contraindications": "湿盛中满，大便泄泻者慎用",
            "dosage_min_g": 6, "dosage_max_g": 12, "toxicity": "无毒",
            "category": "补虚药", "properties": json.dumps({"pharmacologicalClass": "补血"}, ensure_ascii=False),
        },
        {
            "id": "herb-003", "name": "甘草", "aliases": "国老,蜜草",
            "nature": "平", "flavor": "甘", "meridians": "心,肺,脾,胃",
            "efficacy": "补脾益气，清热解毒，祛痰止咳，缓急止痛，调和诸药",
            "indications": "脾胃虚弱，倦怠乏力，心悸气短，咳嗽痰多，脘腹四肢挛急疼痛",
            "contraindications": "不宜与京大戟、芫花、甘遂、海藻同用。湿盛胀满者慎用",
            "dosage_min_g": 2, "dosage_max_g": 10, "toxicity": "无毒",
            "category": "补虚药", "properties": json.dumps({"pharmacologicalClass": "抗炎"}, ensure_ascii=False),
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

    formulas = [
        {
            "id": "formula-001", "name": "四君子汤", "source": "《太平惠民和剂局方》",
            "category": "补益剂",
            "composition": json.dumps([
                {"name": "人参", "dose": "9g", "role": "君"},
                {"name": "白术", "dose": "9g", "role": "臣"},
                {"name": "茯苓", "dose": "9g", "role": "佐"},
                {"name": "甘草", "dose": "6g", "role": "使"},
            ], ensure_ascii=False),
            "efficacy": "益气健脾",
            "indications": "脾胃气虚证。面色萎白，语声低微，气短乏力，食少便溏",
            "modifications": "[]", "modifications_structured": "[]",
            "properties": "{}",
        },
        {
            "id": "formula-002", "name": "四物汤", "source": "《太平惠民和剂局方》",
            "category": "补益剂",
            "composition": json.dumps([
                {"name": "熟地黄", "dose": "12g", "role": "君"},
                {"name": "当归", "dose": "9g", "role": "臣"},
                {"name": "白芍", "dose": "9g", "role": "佐"},
                {"name": "川芎", "dose": "6g", "role": "佐"},
            ], ensure_ascii=False),
            "efficacy": "补血调血",
            "indications": "营血虚滞证。头晕目眩，心悸失眠，面色无华，妇人月经不调",
            "modifications": "[]", "modifications_structured": "[]",
            "properties": "{}",
        },
    ]
    for f in formulas:
        await db.execute(
            """INSERT OR IGNORE INTO formulas
               (id, name, source, category, composition, efficacy, indications,
                modifications, modifications_structured, properties)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (f["id"], f["name"], f["source"], f["category"], f["composition"],
             f["efficacy"], f["indications"], f["modifications"],
             f["modifications_structured"], f["properties"]),
        )

    await seed_therapy_data(db)


async def seed_therapy_data(db: DbAdapter) -> None:
    """Seed therapy knowledge base (spec §9.6) — 33 therapies + acupoints + safety rules."""
    from app.therapy_data import THERAPIES, THERAPY_SAFETY_RULES

    for t in THERAPIES:
        acupoints = t.get("acupoints", [])
        props = t.get("properties", {})
        await db.execute(
            """INSERT OR IGNORE INTO therapies
               (id, name, category, risk_level, home_use_safe, display_only,
                description, indications, contraindications, operation_steps,
                duration, frequency, precautions, properties)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                t["id"], t["name"], t["category"], t["risk_level"],
                t["home_use_safe"], t["display_only"],
                t["description"], t["indications"], t["contraindications"],
                t["operation_steps"], t["duration"], t["frequency"],
                t["precautions"], json.dumps(props, ensure_ascii=False),
            ),
        )
        for ap in acupoints:
            ap_id = f"{t['id']}-acp-{ap['acupoint_name']}"
            await db.execute(
                """INSERT OR IGNORE INTO therapy_acupoints
                   (id, therapy_id, acupoint_name, location, function, meridian, is_primary)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    ap_id, t["id"], ap["acupoint_name"], ap.get("location"),
                    ap.get("function"), ap.get("meridian"), ap.get("is_primary", 0),
                ),
            )

    for rule in THERAPY_SAFETY_RULES:
        await db.execute(
            """INSERT OR IGNORE INTO therapy_safety_rules
               (id, therapy_category, rule_type, condition_text, action, severity)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                rule["id"], rule["therapy_category"], rule["rule_type"],
                rule["condition_text"], rule["action"], rule["severity"],
            ),
        )
