"""Database layer: DbAdapter ABC + SqliteAdapter with aiosqlite."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import aiosqlite


# ---------------------------------------------------------------------------
# DDL — all tables from spec §10.6
# ---------------------------------------------------------------------------


from app.db.adapter import DbAdapter, SqliteAdapter, set_db, get_db, _db_adapter
from app.db.schema import DDL_STATEMENTS, FTS_STATEMENTS, FTS_TRIGGERS
from app.db.migrations import (
    init_db,
    _migrate_reminders_member_id,
    _migrate_user_profiles_liver_kidney,
    _migrate_knowledge_tenant_id,
    _migrate_chunks_source,
)
from app.db.seeds import seed_safety_rules, seed_test_data, seed_therapy_data
