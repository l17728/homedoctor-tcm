"""Seed the same public reference data used by a fresh Docker installation."""

from __future__ import annotations

import subprocess
import sys
import os
from pathlib import Path


SCRIPTS = (
    "seed_herbs_batch1.py",
    "seed_herbs_batch2.py",
    "seed_herbs_batch3.py",
    "seed_herbs_batch4.py",
    "seed_herbs_batch5.py",
    "seed_formulas.py",
    "seed_classics.py",
    "seed_therapies.py",
    "seed_therapies_expanded.py",
    "seed_modifications.py",
    "seed_knowledge_entities.py",
    "seed_acupoints_meridians.py",
    "seed_health_practices.py",
    "seed_processed_herbs.py",
    "seed_practice_relationships.py",
    "seed_processed_herb_formula_links.py",
)


def main() -> None:
    scripts_dir = Path(__file__).resolve().parent
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    database_url = env.get("HOMEDOCTOR_DATABASE_URL")
    if database_url:
        env["DATABASE_URL"] = f"sqlite:///{database_url}"
    for script in SCRIPTS:
        print(f"[e2e] seeding {script}", flush=True)
        command = [sys.executable, str(scripts_dir / script)]
        if script == "seed_herbs_batch2.py" and database_url:
            # Batch 2 predates HOMEDOCTOR_DATABASE_URL and only accepts --db.
            command.extend(["--db", database_url])
        if script == "seed_modifications.py" and database_url:
            command.append(database_url)
        if script == "seed_formulas.py" and database_url:
            command.append(database_url)
        subprocess.run(command, check=True, env=env)


if __name__ == "__main__":
    main()
