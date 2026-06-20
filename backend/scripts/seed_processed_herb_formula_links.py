"""Seed processed herb ↔ formula relationships.

Links processed herb variants (炮制品) to classical formulas that specifically
require them. For example, 四君子汤 uses 茯苓 but 四逆汤 uses 炙甘草.
Idempotent (INSERT OR REPLACE). Standalone (aiosqlite direct).
"""
import asyncio, json, os, aiosqlite

DB = os.environ.get("HOMEDOCTOR_DATABASE_URL", "data/homedoctor.db")

# (processed_herb_name, formula_name, role_in_formula)
# These are formulas where the SPECIFIC processed variant matters clinically.
LINKS = [
    ("炙甘草", "炙甘草汤", "君药"),
    ("炙甘草", "四君子汤", "使药"),
    ("炙甘草", "补中益气汤", "使药"),
    ("熟地黄", "六味地黄丸", "君药"),
    ("熟地黄", "四物汤", "君药"),
    ("熟地黄", "左归丸", "君药"),
    ("制何首乌", "七宝美髯丹", "君药"),
    ("制何首乌", "何人饮", "君药"),
    ("酒当归", "生化汤", "君药"),
    ("酒当归", "复元活血汤", "臣药"),
    ("醋柴胡", "逍遥散", "君药"),
    ("醋柴胡", "柴胡疏肝散", "君药"),
    ("炒白术", "参苓白术散", "臣药"),
    ("炒白术", "完带汤", "臣药"),
    ("醋延胡索", "金铃子散", "君药"),
    ("盐杜仲", "右归丸", "臣药"),
    ("盐杜仲", "杜仲汤", "君药"),
    ("姜半夏", "小半夏汤", "君药"),
    ("姜半夏", "半夏泻心汤", "君药"),
    ("法半夏", "二陈汤", "君药"),
    ("酒大黄", "复元活血汤", "君药"),
    ("熟大黄", "大黄蟅虫丸", "君药"),
    ("大黄炭", "十灰散", "臣药"),
    ("酒黄精", "黄精膏", "君药"),
    ("盐黄柏", "知柏地黄丸", "臣药"),
    ("酒黄柏", "当归龙荟丸", "臣药"),
    ("姜厚朴", "平胃散", "臣药"),
    ("姜厚朴", "厚朴温中汤", "君药"),
    ("酒川芎", "血府逐瘀汤", "臣药"),
    ("酒川芎", "生化汤", "臣药"),
    ("朱麦冬", "天王补心丹", "臣药"),
    ("土炒白术", "参苓白术散", "臣药"),
]


async def main():
    async with aiosqlite.connect(DB) as db:
        rel_count = 0
        not_found = 0
        for herb_name, formula_name, role in LINKS:
            herb_rows = await db.execute(
                "SELECT id FROM knowledge_entities WHERE title=? AND category='炮制品' LIMIT 1",
                (herb_name,),
            )
            herb_row = await herb_rows.fetchone()
            formula_rows = await db.execute(
                "SELECT id FROM knowledge_entities WHERE title=? AND entity_type='formula' LIMIT 1",
                (formula_name,),
            )
            formula_row = await formula_rows.fetchone()

            if not herb_row or not formula_row:
                not_found += 1
                continue

            rid = f"rel-pf-{herb_row[0]}-{formula_row[0]}"
            await db.execute(
                """INSERT OR REPLACE INTO entity_relationships
                   (id, source_entity_id, target_entity_id, relationship_type, properties, weight)
                   VALUES (?, ?, ?, '方剂用药', ?, 1.0)""",
                (
                    rid, formula_row[0], herb_row[0],
                    json.dumps({"role": role, "note": f"{formula_name}使用{herb_name}"}, ensure_ascii=False),
                ),
            )
            rel_count += 1

        await db.commit()
        print(f"炮制品↔方剂: {rel_count} 关系, {not_found} 未匹配")


if __name__ == "__main__":
    asyncio.run(main())
