"""Seed practice-constitution and practice-meridian relationships.

Links health practices to constitution types (适合体质) and meridians (疏通经络).
Idempotent (INSERT OR REPLACE). Standalone (aiosqlite direct).
"""
import asyncio, json, os, aiosqlite

DB = os.environ.get("HOMEDOCTOR_DATABASE_URL", "data/homedoctor.db")

PRACTICE_CONSTITUTION = {
    "hp-taiji": [("阳虚质", "温阳益气"), ("气虚质", "补气健脾"), ("平和质", "日常保健")],
    "hp-baduanjin": [("气虚质", "健脾益气"), ("阳虚质", "温通经脉"), ("痰湿质", "化痰除湿"), ("平和质", "日常保健")],
    "hp-jingang": [("阳虚质", "温阳通经"), ("气虚质", "培补元气"), ("气郁质", "疏肝理气")],
    "hp-changshou": [("阴虚质", "滋阴养血"), ("阳虚质", "温补元阳"), ("气虚质", "培补元气")],
    "hp-zhanzhuang": [("阳虚质", "温补下元"), ("气虚质", "培本固元"), ("痰湿质", "运化水湿")],
    "hp-dazuo": [("阴虚质", "滋阴降火"), ("气郁质", "疏肝安神"), ("平和质", "修身养性"), ("血瘀质", "静心化瘀")],
    "hp-wuqinxi": [("气虚质", "补益肺脾"), ("阳虚质", "温通气血"), ("痰湿质", "运化水湿")],
    "hp-yijinjing": [("气虚质", "强健筋骨"), ("阳虚质", "温通经脉"), ("血瘀质", "活血化瘀")],
    "hp-liuzijue": [("气虚质", "补益肺气"), ("阴虚质", "滋阴降火"), ("阳虚质", "温阳化气"), ("痰湿质", "健脾化痰")],
    "hp-qigong": [("阴虚质", "滋阴养精"), ("阳虚质", "温阳益气"), ("平和质", "修身养性")],
}

PRACTICE_MERIDIAN = {
    "hp-baduanjin": [("ke-meridian-LU", "调理肺经"), ("ke-meridian-ST", "调理胃经"), ("ke-meridian-SP", "调理脾经")],
    "hp-zhanzhuang": [("ke-meridian-KI", "强化肾经"), ("ke-meridian-LR", "疏肝理气")],
    "hp-dazuo": [("ke-meridian-HT", "安心神"), ("ke-meridian-KI", "补肾元")],
    "hp-liuzijue": [("ke-meridian-LU", "调理肺经"), ("ke-meridian-HT", "调理心经"), ("ke-meridian-LR", "调理肝经"), ("ke-meridian-KI", "调理肾经"), ("ke-meridian-SP", "调理脾经")],
    "hp-taiji": [("ke-meridian-LR", "疏肝"), ("ke-meridian-KI", "补肾"), ("ke-meridian-SP", "健脾")],
    "hp-jingang": [("ke-meridian-GV", "通督脉"), ("ke-meridian-BL", "疏通膀胱经")],
}


async def main():
    async with aiosqlite.connect(DB) as db:
        rel_count = 0
        for pid, rels in PRACTICE_CONSTITUTION.items():
            for const_name, effect in rels:
                rows = await db.execute(
                    "SELECT id FROM knowledge_entities WHERE title=? AND entity_type='symptom' LIMIT 1",
                    (const_name,),
                )
                row = await rows.fetchone()
                target = row[0] if row else f"const-{const_name}"
                rid = f"rel-{pid}-suit-{const_name}"
                await db.execute(
                    """INSERT OR REPLACE INTO entity_relationships
                       (id, source_entity_id, target_entity_id, relationship_type, properties, weight)
                       VALUES (?, ?, ?, '适合体质', ?, 1.0)""",
                    (rid, pid, target, json.dumps({"effect": effect}, ensure_ascii=False)),
                )
                rel_count += 1

        for pid, rels in PRACTICE_MERIDIAN.items():
            for mid, effect in rels:
                rid = f"rel-{pid}-meridian-{mid}"
                await db.execute(
                    """INSERT OR REPLACE INTO entity_relationships
                       (id, source_entity_id, target_entity_id, relationship_type, properties, weight)
                       VALUES (?, ?, ?, '疏通经络', ?, 1.0)""",
                    (rid, pid, mid, json.dumps({"effect": effect}, ensure_ascii=False)),
                )
                rel_count += 1

        await db.commit()
        print(f"功法关联: {rel_count} relationships (体质+经络)")


if __name__ == "__main__":
    asyncio.run(main())
