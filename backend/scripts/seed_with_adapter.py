"""Run a seed script after activating the configured SQLite/SQLCipher adapter."""

from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: seed_with_adapter.py SCRIPT [ARGS ...]")

    script = Path(sys.argv[1]).resolve()
    if not script.is_file():
        raise SystemExit(f"seed script not found: {script}")
    sys.path.insert(0, str(script.parent.parent))

    # This import applies the app's SQLCipher compatibility shim to stdlib
    # sqlite3 users as well as initializing SqliteAdapter for adapter seeds.
    from app.db.adapter import _SQLCIPHER_ACTIVE, _pragma_key_sql

    if os.environ.get("HOMEDOCTOR_DB_ENCRYPTION_KEY") and not _SQLCIPHER_ACTIVE:
        raise SystemExit("SQLCipher is required to seed an encrypted database")

    key = os.environ.get("HOMEDOCTOR_DB_ENCRYPTION_KEY")
    if key:
        import sqlite3

        raw_connect = sqlite3.connect

        def encrypted_connect(*args, **kwargs):
            connection = raw_connect(*args, **kwargs)
            connection.execute(_pragma_key_sql(key))
            connection.execute("PRAGMA cipher_compatibility = 4")
            return connection

        # Legacy seed scripts that use sqlite3 directly now open keyed databases.
        # Adapter-based scripts use this same connection factory, so tell the
        # adapter not to issue PRAGMA key a second time.
        sqlite3.connect = encrypted_connect
        os.environ["HOMEDOCTOR_SQLCIPHER_KEY_APPLIED_BY_CONNECT"] = "1"

    sys.argv = [str(script), *sys.argv[2:]]
    runpy.run_path(str(script), run_name="__main__")


if __name__ == "__main__":
    main()
