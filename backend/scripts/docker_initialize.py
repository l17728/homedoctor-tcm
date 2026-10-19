"""Initialize Docker's persistent database once, then start the API.

Seed completion is recorded only after every seed process succeeds. If a seed
fails, Docker restarts and retries the idempotent seed set instead of silently
starting with an incomplete knowledge base. Existing volumes without markers
are treated as established user data and are never reseeded.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


SEED_SCRIPTS = (
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
    "seed_ai_models.py",
)


def _seed(database_path: Path, marker: Path, progress: Path) -> None:
    scripts = Path(__file__).resolve().parent
    database_path.parent.mkdir(parents=True, exist_ok=True)
    progress.touch(exist_ok=True)
    env = os.environ.copy()
    env["HOMEDOCTOR_DATABASE_URL"] = str(database_path)
    env.setdefault("DATABASE_URL", f"sqlite:///{database_path}")

    for name in SEED_SCRIPTS:
        script = scripts / name
        print(f"[init] seeding {name}", flush=True)
        subprocess.run(
            [sys.executable, str(scripts / "seed_with_adapter.py"), str(script)],
            check=True,
            cwd=scripts.parent,
            env=env,
        )

    marker.write_text("complete\n", encoding="ascii")
    progress.unlink(missing_ok=True)


def main() -> None:
    database_path = Path(os.environ.get("HOMEDOCTOR_DATABASE_URL", "data/homedoctor.db"))
    if not database_path.is_absolute():
        database_path = Path.cwd() / database_path
    marker = database_path.parent / ".homedoctor-seed-complete"
    progress = database_path.parent / ".homedoctor-seed-in-progress"

    if progress.exists():
        _seed(database_path, marker, progress)
    elif not database_path.exists() or database_path.stat().st_size == 0:
        _seed(database_path, marker, progress)
    elif not marker.exists():
        # Preserve established user volumes created before this marker existed.
        marker.write_text("existing database\n", encoding="ascii")

    os.execvp(
        "uvicorn",
        ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"],
    )


if __name__ == "__main__":
    main()
