#!/usr/bin/env python3
"""Seed therapy knowledge base (spec §9.6) into SQLite database.

Usage:
    python backend/scripts/seed_therapies.py [--db PATH]

Default DB path: data/homedoctor.db (relative to project root /homedoctor)

Data: 33 therapies (刮痧6/推拿6/艾灸6/拔罐5/针刺5/刺血5) + acupoints + 25 safety rules.
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database import SqliteAdapter, init_db, seed_therapy_data


async def seed(db_path: str) -> None:
    db_file = os.path.dirname(db_path)
    if db_file:
        os.makedirs(db_file, exist_ok=True)

    adapter = SqliteAdapter(db_path)
    await adapter.connect()
    await init_db(adapter)

    existing = await adapter.query_one("SELECT COUNT(*) as cnt FROM therapies")
    before = existing["cnt"] if existing else 0

    await seed_therapy_data(adapter)

    after_row = await adapter.query_one("SELECT COUNT(*) as cnt FROM therapies")
    after = after_row["cnt"] if after_row else 0

    acp_row = await adapter.query_one("SELECT COUNT(*) as cnt FROM therapy_acupoints")
    acp_count = acp_row["cnt"] if acp_row else 0

    rule_row = await adapter.query_one("SELECT COUNT(*) as cnt FROM therapy_safety_rules")
    rule_count = rule_row["cnt"] if rule_row else 0

    cat_rows = await adapter.query(
        "SELECT category, COUNT(*) as cnt FROM therapies GROUP BY category ORDER BY category"
    )

    await adapter.close()

    inserted = after - before
    print(f"Seeded {inserted} new therapies (skipped {before} existing)")
    print(f"Total therapies: {after} | acupoints: {acp_count} | safety rules: {rule_count}")
    print("\nCategory breakdown:")
    for r in cat_rows:
        print(f"  {r['category']}: {r['cnt']}")

    assert after >= 30, f"Expected at least 30 therapies, got {after}"
    print(f"\n✓ Therapy knowledge base seeded successfully ({after} therapies)")


if __name__ == "__main__":
    db_path = os.environ.get("HOMEDOCTOR_DATABASE_URL", "data/homedoctor.db")
    if len(sys.argv) > 1:
        if sys.argv[1] in ("--db", "-d"):
            db_path = sys.argv[2]
        else:
            db_path = sys.argv[1]
    asyncio.run(seed(db_path))
