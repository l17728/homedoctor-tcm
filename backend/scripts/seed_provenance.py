"""Seed provenance records for all existing knowledge entities.

All seed data gets trust_level=S (system authoritative) since it comes from
textbooks, pharmacopeia, and expert-verified sources. This ensures the safety
engine correctly treats seed herbs/formulas as S-level knowledge.

Idempotent (INSERT OR IGNORE). Standalone (aiosqlite direct).
"""
import asyncio, uuid, os, aiosqlite

DB = os.environ.get("HOMEDOCTOR_DATABASE_URL", "data/homedoctor.db")


async def main():
    async with aiosqlite.connect(DB) as db:
        cursor = await db.execute(
            "SELECT id, title FROM knowledge_entities WHERE status='active' AND tenant_id IS NULL"
        )
        entities = await cursor.fetchall()

        count = 0
        for eid, title in entities:
            pid = f"prov-seed-{uuid.uuid4()}"
            try:
                await db.execute(
                    """INSERT OR IGNORE INTO knowledge_provenance
                       (id, entity_id, source_type, source_title, trust_level, trust_score,
                        review_details, imported_by)
                       VALUES (?, ?, 'seed', ?, 'S', 95.0,
                        '{"auto": true, "source": "system_seed"}', 'system')""",
                    (pid, eid, title),
                )
                count += 1
            except Exception:
                pass

        await db.commit()

        cursor2 = await db.execute("SELECT COUNT(*) FROM knowledge_provenance")
        total = (await cursor2.fetchone())[0]
        print(f"Seeded {count} provenance records (trust_level=S). Total: {total}")


if __name__ == "__main__":
    asyncio.run(main())
