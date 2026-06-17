#!/usr/bin/env python3
"""Populate modifications_structured for clinically important formulas.

Spec §2.2 four-layer 加减 model:
  君药加减 — modify the sovereign herb for different severity
  兼证加减 — address accompanying syndromes
  随症加减 — adjust based on specific symptoms
  体质加减 — adapt to the patient's constitution

Usage:
    python backend/scripts/seed_modifications.py [--db PATH]

Default DB path: data/homedoctor.db (relative to project root /homedoctor)

Each modification entry:
  {"symptom": str, "add": [str], "remove": [str], "note": str}
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys

MODIFICATIONS: dict[str, list[dict]] = {
    "formula-001": [
        {"symptom": "气虚兼气滞", "add": ["陈皮"], "remove": [], "note": "→ 异功散"},
        {"symptom": "气虚兼痰湿", "add": ["陈皮", "半夏"], "remove": [], "note": "→ 六君子汤"},
        {"symptom": "气虚兼气滞痰湿", "add": ["陈皮", "半夏", "木香", "砂仁"], "remove": [], "note": "→ 香砂六君子汤"},
        {"symptom": "脾胃虚寒", "add": ["干姜"], "remove": [], "note": "温中散寒"},
    ],
    "formula-002": [
        {"symptom": "兼气虚", "add": ["人参", "黄芪"], "remove": [], "note": "→ 圣愈汤"},
        {"symptom": "兼血瘀", "add": ["桃仁", "红花"], "remove": [], "note": "→ 桃红四物汤"},
        {"symptom": "血虚有热", "add": ["黄芩", "牡丹皮"], "remove": ["熟地黄"], "note": "清热凉血，熟地黄易生地黄"},
        {"symptom": "兼气滞", "add": ["香附", "延胡索"], "remove": [], "note": "理气止痛"},
    ],
    "formula-003": [
        {"symptom": "咳嗽痰多", "add": ["半夏", "苏子"], "remove": [], "note": "降气化痰"},
        {"symptom": "鼻塞流涕", "add": ["苍耳子", "辛夷"], "remove": [], "note": "通鼻窍"},
        {"symptom": "肢节疼痛", "add": ["羌活", "防风"], "remove": [], "note": "祛风除湿"},
        {"symptom": "里热烦躁", "add": ["石膏", "黄芩"], "remove": [], "note": "兼清里热"},
    ],
    "formula-004": [
        {"symptom": "项背强几几", "add": ["葛根"], "remove": [], "note": "→ 桂枝加葛根汤"},
        {"symptom": "表阳虚漏汗", "add": ["附子"], "remove": [], "note": "→ 桂枝加附子汤"},
        {"symptom": "咳喘", "add": ["厚朴", "杏仁"], "remove": [], "note": "→ 桂枝加厚朴杏子汤"},
        {"symptom": "胸满", "add": ["柴胡", "枳壳"], "remove": ["白芍"], "note": "→ 柴胡桂枝汤之意"},
    ],
    "formula-006": [
        {"symptom": "兼里热", "add": ["石膏"], "remove": [], "note": "清透里热"},
        {"symptom": "咳嗽喘甚", "add": ["杏仁"], "remove": [], "note": "降气平喘"},
        {"symptom": "痰多", "add": ["款冬花", "紫菀"], "remove": [], "note": "温肺化痰"},
    ],
    "formula-008": [
        {"symptom": "热毒较甚", "add": ["大青叶", "板蓝根"], "remove": [], "note": "清热解毒"},
        {"symptom": "伤津口渴", "add": ["天花粉", "知母"], "remove": [], "note": "生津止渴"},
        {"symptom": "兼湿热", "add": ["黄芩", "滑石"], "remove": [], "note": "清热利湿"},
        {"symptom": "咽痛甚", "add": ["马勃", "玄参"], "remove": [], "note": "清热利咽"},
    ],
    "formula-015": [
        {"symptom": "湿热黄疸", "add": ["茵陈", "栀子"], "remove": ["人参", "大枣"], "note": "去壅补加清利"},
        {"symptom": "胸中烦而不呕", "add": ["瓜蒌"], "remove": ["半夏"], "note": "去半夏之燥，加瓜蒌清热"},
        {"symptom": "口渴", "add": ["天花粉"], "remove": ["半夏"], "note": "去半夏加花粉生津"},
        {"symptom": "腹痛", "add": ["白芍"], "remove": ["黄芩"], "note": "加芍药缓急止痛"},
        {"symptom": "胁下痞硬", "add": ["牡蛎"], "remove": ["大枣"], "note": "软坚散结"},
    ],
    "formula-017": [
        {"symptom": "肝郁化火", "add": ["牡丹皮", "栀子"], "remove": [], "note": "→ 丹栀逍遥散"},
        {"symptom": "血虚甚", "add": ["熟地黄"], "remove": [], "note": "→ 黑逍遥散"},
        {"symptom": "兼湿热", "add": ["茵陈", "栀子"], "remove": ["当归"], "note": "清利肝胆湿热"},
        {"symptom": "月经不调", "add": ["益母草", "泽兰"], "remove": [], "note": "活血调经"},
    ],
    "formula-031": [
        {"symptom": "阳虚甚", "add": ["附子"], "remove": [], "note": "→ 附子理中丸"},
        {"symptom": "呕吐甚", "add": ["生姜", "半夏"], "remove": [], "note": "温胃止呕"},
        {"symptom": "腹泻甚", "add": ["肉豆蔻", "补骨脂"], "remove": [], "note": "温涩止泻"},
        {"symptom": "兼血虚", "add": ["当归", "白芍"], "remove": [], "note": "养血和营"},
    ],
    "formula-037": [
        {"symptom": "气虚甚", "add": ["黄芪"], "remove": [], "note": "→ 十全大补汤之意"},
        {"symptom": "心悸失眠", "add": ["酸枣仁", "柏子仁"], "remove": [], "note": "养心安神"},
        {"symptom": "食欲不振", "add": ["陈皮", "砂仁"], "remove": [], "note": "理气醒脾"},
        {"symptom": "兼阳虚", "add": ["肉桂"], "remove": [], "note": "→ 十全大补汤"},
    ],
    "formula-038": [
        {"symptom": "兼阳虚畏寒", "add": ["附子", "肉桂"], "remove": [], "note": "温阳散寒"},
        {"symptom": "兼阴虚", "add": ["麦冬", "五味子"], "remove": ["肉桂"], "note": "去肉桂之温，加养阴"},
        {"symptom": "兼心悸失眠", "add": ["远志", "酸枣仁"], "remove": [], "note": "→ 人参养荣汤之意"},
        {"symptom": "兼食少便溏", "add": ["山药", "薏苡仁"], "remove": [], "note": "健脾止泻"},
    ],
    "formula-040": [
        {"symptom": "阴虚火旺", "add": ["知母", "黄柏"], "remove": [], "note": "→ 知柏地黄丸"},
        {"symptom": "肺肾阴虚咳嗽", "add": ["麦冬", "五味子"], "remove": [], "note": "→ 麦味地黄丸"},
        {"symptom": "肝肾阴虚目涩", "add": ["枸杞子", "菊花"], "remove": [], "note": "→ 杞菊地黄丸"},
        {"symptom": "兼血瘀", "add": ["当归", "白芍"], "remove": [], "note": "养血活血"},
    ],
    "formula-044": [
        {"symptom": "兼胃脘痛", "add": ["延胡索", "佛手"], "remove": [], "note": "理气止痛"},
        {"symptom": "兼口苦便秘", "add": ["龙胆草", "大黄"], "remove": [], "note": "泻火通便"},
        {"symptom": "兼虚热", "add": ["地骨皮", "银柴胡"], "remove": [], "note": "清虚热"},
        {"symptom": "兼腹胀", "add": ["砂仁", "陈皮"], "remove": [], "note": "理气消胀"},
    ],
    "formula-046": [
        {"symptom": "气虚甚", "add": ["人参", "白术"], "remove": [], "note": "重用黄芪加人参"},
        {"symptom": "兼气滞腹胀", "add": ["木香", "砂仁"], "remove": [], "note": "理气消胀"},
        {"symptom": "兼血虚", "add": ["龙眼肉", "当归"], "remove": [], "note": "养血补心"},
        {"symptom": "兼阳虚畏寒", "add": ["桂枝", "干姜"], "remove": [], "note": "温阳散寒"},
        {"symptom": "兼阴虚", "add": ["麦冬", "五味子"], "remove": ["白术"], "note": "养阴生津"},
    ],
    "formula-047": [
        {"symptom": "气虚甚", "add": ["黄芪"], "remove": [], "note": "益气固表"},
        {"symptom": "阴虚甚", "add": ["生地黄", "玄参"], "remove": [], "note": "养阴生津"},
        {"symptom": "兼咳嗽", "add": ["紫菀", "款冬花"], "remove": [], "note": "润肺止咳"},
        {"symptom": "兼失眠", "add": ["酸枣仁", "柏子仁"], "remove": [], "note": "养心安神"},
    ],
    "formula-048": [
        {"symptom": "兼阳虚畏寒", "add": ["附子", "干姜"], "remove": [], "note": "温阳散寒"},
        {"symptom": "兼心悸失眠", "add": ["酸枣仁", "远志"], "remove": [], "note": "养心安神"},
        {"symptom": "兼气滞", "add": ["木香", "砂仁"], "remove": [], "note": "理气醒脾"},
        {"symptom": "兼血瘀", "add": ["丹参", "川芎"], "remove": [], "note": "活血化瘀"},
    ],
    "formula-080": [
        {"symptom": "食积腹胀甚", "add": ["枳实", "厚朴"], "remove": [], "note": "行气消痞"},
        {"symptom": "食积化热", "add": ["黄连", "连翘"], "remove": [], "note": "清热泻火"},
        {"symptom": "酒积", "add": ["葛花", "枳椇子"], "remove": [], "note": "解酒化积"},
        {"symptom": "兼脾虚", "add": ["白术", "党参"], "remove": [], "note": "健脾化积"},
        {"symptom": "兼便秘", "add": ["大黄"], "remove": [], "note": "泻下导滞"},
    ],
    "formula-082": [
        {"symptom": "湿热甚", "add": ["茵陈", "滑石"], "remove": [], "note": "清利湿热"},
        {"symptom": "食积腹胀", "add": ["山楂", "莱菔子"], "remove": [], "note": "消食化积"},
        {"symptom": "兼气滞", "add": ["木香", "槟榔"], "remove": [], "note": "行气导滞"},
        {"symptom": "兼泻痢", "add": ["白芍", "木香"], "remove": ["大黄"], "note": "去大黄泻下，加芍药缓急"},
    ],
}


def seed(db_path: str) -> None:
    if not os.path.isabs(db_path):
        db_path = os.path.join("/homedoctor", db_path)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")

    updated = 0
    skipped = 0

    for formula_id, mods in MODIFICATIONS.items():
        row = conn.execute(
            "SELECT id FROM formulas WHERE id = ?", (formula_id,)
        ).fetchone()
        if not row:
            skipped += 1
            continue

        conn.execute(
            "UPDATE formulas SET modifications_structured = ? WHERE id = ?",
            (json.dumps(mods, ensure_ascii=False), formula_id),
        )
        updated += 1

    conn.commit()
    conn.close()

    print(f"Updated modifications_structured for {updated} formulas (skipped {skipped} missing)")
    print(f"\n✓ Modifications data populated ({updated} formulas)")


if __name__ == "__main__":
    db_path = "data/homedoctor.db"
    if len(sys.argv) > 1:
        if sys.argv[1] in ("--db", "-d"):
            db_path = sys.argv[2]
        else:
            db_path = sys.argv[1]
    seed(db_path)
