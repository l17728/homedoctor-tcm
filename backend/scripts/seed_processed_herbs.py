"""Seed processed herb variants (炮制品) as separate knowledge_entities.

In TCM, the same herb processed differently has different properties:
  甘草(生) → 清热解毒
  炙甘草(蜜炙) → 补脾益气
  黄精(生) → 润肺
  酒黄精(酒蒸) → 补肾益精

Each variant is a separate node in the knowledge graph, linked by
"炮制" (processing) relationship to its raw form.

Idempotent (INSERT OR REPLACE). Standalone (aiosqlite direct).
"""
import asyncio, json, os, aiosqlite

DB = os.environ.get("HOMEDOCTOR_DATABASE_URL", "data/homedoctor.db")

# (id, name, raw_herb, processing_method, nature_change, flavor_change,
#  efficacy, indications, meridians, cautions, usage_note)
PROCESSED_HERBS = [
    ("ph-gancao-zhi", "炙甘草", "甘草", "蜜炙",
     "温", "甘", "补脾和胃，益气复脉",
     ["脾胃虚弱", "倦怠乏力", "心动悸", "脉结代"],
     "心,脾,胃,肺",
     "湿盛胀满、浮肿者不宜",
     "蜜炙后温补力增强，偏于补中益气"),
    ("ph-huangjing-jiu", "酒黄精", "黄精", "酒蒸",
     "平", "甘", "补肝肾，益精血",
     ["肝肾阴虚", "腰膝酸软", "须发早白", "头晕耳鸣"],
     "肝,肾",
     "脾虚湿盛者慎用",
     "酒蒸后滋腻性减弱，补肾益精力增强"),
    ("ph-banxia-fa", "法半夏", "半夏", "甘草石灰液泡制",
     "温", "辛", "燥湿化痰",
     ["痰多咳嗽", "胸脘痞闷"],
     "脾,胃,肺",
     "阴虚燥咳者慎用",
     "炮制后毒性降低，化痰力缓和"),
    ("ph-banxia-jiang", "姜半夏", "半夏", "生姜汁浸泡",
     "温", "辛", "降逆止呕，化痰",
     ["胃寒呕吐", "痰饮呕吐"],
     "脾,胃",
     "阴虚燥咳者慎用",
     "姜汁制后止呕力增强"),
    ("ph-chaihu-cu", "醋柴胡", "柴胡", "醋炙",
     "微寒", "苦,辛", "疏肝解郁，升举阳气",
     ["肝气郁结", "胸胁胀痛", "月经不调"],
     "肝,胆",
     "肝阳上亢者慎用",
     "醋炙后升散之性减弱，疏肝止痛力增强"),
    ("ph-baizhu-chao", "炒白术", "白术", "麸炒",
     "温", "苦,甘", "健脾益气，燥湿利水",
     ["脾虚食少", "腹胀泄泻", "痰饮眩悸"],
     "脾,胃",
     "阴虚内热者慎用",
     "麸炒后燥湿力减弱，健脾力增强"),
    ("ph-baizhu-tu", "土炒白术", "白术", "土炒",
     "温", "苦,甘", "健脾止泻",
     ["脾虚泄泻", "久泻不止"],
     "脾,胃",
     "阴虚内热者慎用",
     "土炒后和胃止泻力增强"),
    ("ph-yanhusuo-cu", "醋延胡索", "延胡索", "醋炙",
     "温", "辛,苦", "活血，行气，止痛",
     ["胸胁脘腹疼痛", "经闭痛经", "跌打肿痛"],
     "肝,脾",
     "孕妇慎用",
     "醋炙后有效成分溶出增加，止痛力显著增强"),
    ("ph-duzhong-yan", "盐杜仲", "杜仲", "盐水炒",
     "温", "甘", "补肝肾，强筋骨",
     ["腰膝酸痛", "筋骨痿软", "头晕目眩"],
     "肝,肾",
     "阴虚火旺者慎用",
     "盐炒引药入肾，补肾强骨力增强"),
    ("ph-huangbo-yan", "盐黄柏", "黄柏", "盐水炒",
     "寒", "苦", "滋阴降火，退虚热",
     ["阴虚火旺", "骨蒸劳热", "盗汗遗精"],
     "肾,膀胱",
     "脾胃虚寒者慎用",
     "盐炒引药下行入肾，清虚热力增强"),
    ("ph-huangbo-jiu", "酒黄柏", "黄柏", "酒炒",
     "寒", "苦", "清热泻火，燥湿",
     ["热痢", "黄疸", "湿热淋证"],
     "肾,膀胱",
     "脾胃虚寒者慎用",
     "酒炒引药上行，清上焦湿热"),
    ("ph-danggui-jiu", "酒当归", "当归", "酒炙",
     "温", "甘,辛", "活血调经，止痛",
     ["经闭痛经", "跌打损伤", "风湿痹痛"],
     "肝,心,脾",
     "脾虚便溏者慎用",
     "酒炙后活血力增强，补血力减弱"),
    ("ph-dahuang-jiu", "酒大黄", "大黄", "酒炒",
     "寒", "苦", "清热泻火，解毒",
     ["火热头痛", "目赤肿痛", "咽喉肿痛"],
     "脾,胃,大肠",
     "孕妇禁用",
     "酒炒后泻下力减弱，清上焦热力增强"),
    ("ph-dahuang-shu", "熟大黄", "大黄", "酒蒸",
     "寒", "苦", "缓下热结，凉血解毒",
     ["火毒疮疡", "缓下便秘"],
     "脾,胃,大肠",
     "孕妇禁用",
     "酒蒸后泻下力缓和，凉血解毒力保留"),
    ("ph-dahuang-tan", "大黄炭", "大黄", "炒炭",
     "寒", "苦,涩", "凉血止血",
     ["咯血", "衄血", "便血", "崩漏"],
     "心,肝,大肠",
     "孕妇禁用",
     "炒炭后收敛止血，泻下力消失"),
    ("ph-dihuang-shu", "熟地黄", "地黄", "酒蒸九次",
     "微温", "甘", "滋阴补血，益精填髓",
     ["血虚萎黄", "心悸怔忡", "月经不调", "肾阴不足", "腰膝酸软"],
     "肝,肾",
     "脾虚食少、腹满便溏者慎用",
     "生地性寒清热凉血，熟地微温滋阴补血，九蒸九晒后性变温"),
    ("ph-heshouwu-zhi", "制何首乌", "何首乌", "黑豆汁蒸",
     "微温", "苦,甘,涩", "补肝肾，益精血，乌须发",
     ["血虚萎黄", "眩晕耳鸣", "须发早白", "腰膝酸软"],
     "肝,心,肾",
     "大便溏泻者慎用",
     "生首乌截疟解毒润肠，制首乌补肝肾益精血"),
    ("ph-maidong-zhu", "朱麦冬", "麦冬", "朱砂拌",
     "微寒", "甘,微苦", "清心除烦，养心安神",
     ["心烦失眠", "心悸怔忡"],
     "心,肺,胃",
     "风寒咳嗽者慎用",
     "朱砂拌后清心宁神力增强"),
    ("ph-houpo-jiang", "姜厚朴", "厚朴", "生姜汁炙",
     "温", "苦,辛", "燥湿消痰，下气除满",
     ["湿滞伤中", "脘痞吐泻", "食积气滞", "腹胀便秘"],
     "脾,胃,肺,大肠",
     "孕妇慎用",
     "姜汁炙后消除刺激性，止呕力增强"),
    ("ph-chuanxiong-jiu", "酒川芎", "川芎", "酒炙",
     "温", "辛", "活血行气，祛风止痛",
     ["月经不调", "经闭痛经", "头痛", "风湿痹痛"],
     "肝,胆,心包",
     "阴虚火旺者慎用",
     "酒炙后活血行气力增强"),
]


async def main():
    async with aiosqlite.connect(DB) as db:
        count = 0
        rel_count = 0

        for (pid, name, raw_herb, method, nature, flavor, efficacy,
             indications, meridians, cautions, note) in PROCESSED_HERBS:

            props = json.dumps({
                "raw_herb": raw_herb,
                "processing_method": method,
                "nature": nature,
                "flavor": flavor,
                "efficacy": efficacy,
                "indications": indications,
                "meridians": meridians,
                "cautions": cautions,
                "usage_note": note,
                "is_processed": True,
            }, ensure_ascii=False)

            await db.execute(
                """INSERT OR REPLACE INTO knowledge_entities
                   (id, entity_type, source_table, source_id, title, summary,
                    keywords, tags, category, content_preview, properties,
                    source_type, status, tenant_id)
                   VALUES (?, 'herb', 'processed', ?, ?, ?, '[]', '[]',
                           '炮制品', ?, ?, 'system', 'active', NULL)""",
                (pid, pid, name, efficacy,
                 "；".join(indications[:4]), props),
            )
            count += 1

            raw_rows = await db.execute(
                "SELECT id FROM knowledge_entities WHERE title = ? AND entity_type = 'herb' LIMIT 1",
                (raw_herb,),
            )
            raw_row = await raw_rows.fetchone()
            if raw_row:
                raw_id = raw_row[0]
                rel_id = f"rel-{pid}-processing"
                rel_props = json.dumps({
                    "method": method,
                    "effect": note,
                }, ensure_ascii=False)
                await db.execute(
                    """INSERT OR REPLACE INTO entity_relationships
                       (id, source_entity_id, target_entity_id, relationship_type,
                        properties, weight)
                       VALUES (?, ?, ?, '炮制', ?, 1.0)""",
                    (rel_id, pid, raw_id, rel_props),
                )
                rel_count += 1

        await db.commit()
        print(f"炮制品: {count} 实体, {rel_count} 炮制关系")


if __name__ == "__main__":
    asyncio.run(main())
