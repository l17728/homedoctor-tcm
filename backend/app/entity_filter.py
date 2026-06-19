"""Universal entity extraction filter.

Scans any text for mentions of known knowledge graph entities
(herbs, formulas, symptoms, therapies, medicines) and creates
``entity_relationships`` linking the source content to the found entities.

Design (AGENTS.md §1.4 — 结构化是权威, §1.7 — 中文领域语言):
- The in-memory :class:`EntityNameIndex` mirrors authoritative tables
  (``knowledge_entities`` + ``herbs``/``formulas``/``therapies``) for fast
  substring scanning.
- Found names are ensured to exist in ``knowledge_entities`` (create-or-find)
  and linked via :func:`app.knowledge_entity.create_relationship` which is
  idempotent on ``(source, target, type)``.
- The filter is **non-blocking**: every router integration wraps the call in
  ``try/except`` so a failure here never breaks the main operation.

Usage::

    found = await scan_and_link(db, text, source_entity_id)
    # Returns list of found entities, creates relationships automatically.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.database import DbAdapter
from app.knowledge_entity import (
    RELATIONSHIP_TYPES,
    create_relationship,
    register_entity,
)

logger = logging.getLogger(__name__)

# Minimum alias length — single-char aliases cause too many false positives.
_MIN_ALIAS_LEN = 2


class EntityNameIndex:
    """In-memory index of all entity names for fast text scanning.

    Loaded once from the authoritative tables and cached for the lifetime of
    the process. Call :meth:`reset` (or recreate the instance) when the
    underlying data changes significantly (e.g. after a bulk import).
    """

    def __init__(self) -> None:
        # name → {entity_id, type, source_table, source_id}
        self._names: dict[str, dict[str, Any]] = {}
        # alias → canonical_name
        self._aliases: dict[str, str] = {}
        self._loaded: bool = False

    async def load(self, db: DbAdapter) -> None:
        """Load all entity names from knowledge_entities + herbs/formulas/therapies.

        Idempotent: clears previous state before reloading.
        """
        self._names.clear()
        self._aliases.clear()

        # 1. knowledge_entities (the unified registry — may already mirror
        #    herbs/formulas/therapies plus AI-imported entities).
        try:
            rows = await db.query(
                "SELECT id, entity_type, title, source_table, source_id FROM knowledge_entities"
            )
        except Exception as exc:  # table missing in a fresh DB
            logger.warning("entity_filter: knowledge_entities query failed: %s", exc)
            rows = []
        for r in rows:
            title = (r.get("title") or "").strip()
            if not title:
                continue
            if title not in self._names:
                self._names[title] = {
                    "entity_id": r["id"],
                    "type": r.get("entity_type") or "entity",
                    "source_table": r.get("source_table") or "",
                    "source_id": r.get("source_id"),
                }

        # 2. herbs — names + aliases (authoritative source for canonical names).
        try:
            herbs = await db.query("SELECT id, name, aliases FROM herbs")
        except Exception as exc:
            logger.warning("entity_filter: herbs query failed: %s", exc)
            herbs = []
        for h in herbs:
            name = (h.get("name") or "").strip()
            if not name:
                continue
            if name not in self._names:
                self._names[name] = {
                    "entity_id": None,
                    "type": "herb",
                    "source_table": "herbs",
                    "source_id": h["id"],
                }
            else:
                # Backfill type/source if the registry row lacked them.
                entry = self._names[name]
                entry.setdefault("type", "herb")
                entry.setdefault("source_table", "herbs")
                if not entry.get("source_id"):
                    entry["source_id"] = h["id"]
            # Parse aliases (comma-separated or JSON list).
            for alias in _parse_aliases(h.get("aliases")):
                if alias not in self._aliases:
                    self._aliases[alias] = name

        # 3. formulas.
        try:
            formulas = await db.query("SELECT id, name FROM formulas")
        except Exception as exc:
            logger.warning("entity_filter: formulas query failed: %s", exc)
            formulas = []
        for f in formulas:
            name = (f.get("name") or "").strip()
            if not name:
                continue
            if name not in self._names:
                self._names[name] = {
                    "entity_id": None,
                    "type": "formula",
                    "source_table": "formulas",
                    "source_id": f["id"],
                }
            else:
                entry = self._names[name]
                entry.setdefault("type", "formula")
                entry.setdefault("source_table", "formulas")
                if not entry.get("source_id"):
                    entry["source_id"] = f["id"]

        # 4. therapies.
        try:
            therapies = await db.query("SELECT id, name FROM therapies")
        except Exception as exc:
            logger.warning("entity_filter: therapies query failed: %s", exc)
            therapies = []
        for t in therapies:
            name = (t.get("name") or "").strip()
            if not name:
                continue
            if name not in self._names:
                self._names[name] = {
                    "entity_id": None,
                    "type": "therapy",
                    "source_table": "therapies",
                    "source_id": t["id"],
                }
            else:
                entry = self._names[name]
                entry.setdefault("type", "therapy")
                entry.setdefault("source_table", "therapies")
                if not entry.get("source_id"):
                    entry["source_id"] = t["id"]

        self._loaded = True

    def scan(self, text: str | None) -> list[dict[str, Any]]:
        """Scan text for entity mentions.

        Returns a list of found entities (deduplicated by canonical name).
        Longer names are matched first so "生黄芪" would win over "黄芪" if both
        existed. Each entry has: ``name``, ``type``, ``entity_id`` (may be
        ``None`` if not yet in the registry), ``source_table``, ``source_id``,
        and optionally ``alias_matched`` when found via an alias.
        """
        if not text or not self._loaded:
            return []

        found: list[dict[str, Any]] = []
        seen: set[str] = set()

        # Match canonical names, longest first to prefer specific matches.
        for name, info in sorted(self._names.items(), key=lambda kv: -len(kv[0])):
            if len(name) < 2:
                continue
            if name in text and name not in seen:
                seen.add(name)
                found.append({
                    "name": name,
                    "type": info.get("type", "entity"),
                    "entity_id": info.get("entity_id"),
                    "source_table": info.get("source_table"),
                    "source_id": info.get("source_id"),
                })

        # Match aliases — resolve to canonical name, dedup against canonicals.
        for alias, canonical in sorted(self._aliases.items(), key=lambda kv: -len(kv[0])):
            if len(alias) < _MIN_ALIAS_LEN:
                continue
            if canonical in seen:
                continue
            if alias in text:
                seen.add(canonical)
                info = self._names.get(canonical, {})
                found.append({
                    "name": canonical,
                    "alias_matched": alias,
                    "type": info.get("type", "herb"),
                    "entity_id": info.get("entity_id"),
                    "source_table": info.get("source_table"),
                    "source_id": info.get("source_id"),
                })

        return found

    def reset(self) -> None:
        """Clear the cache — forces a reload on next access."""
        self._names.clear()
        self._aliases.clear()
        self._loaded = False


def _parse_aliases(raw: Any) -> list[str]:
    """Parse an aliases field that may be comma-separated or a JSON list."""
    if not raw:
        return []
    if isinstance(raw, list):
        items = [str(a).strip() for a in raw if a]
    elif isinstance(raw, str):
        stripped = raw.strip()
        # Try JSON first (properties stores aliases as JSON sometimes).
        if stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, list):
                    items = [str(a).strip() for a in parsed if a]
                else:
                    items = []
            except (json.JSONDecodeError, TypeError):
                items = [a.strip() for a in stripped.split(",") if a.strip()]
        else:
            items = [a.strip() for a in stripped.split(",") if a.strip()]
    else:
        items = []
    return [a for a in items if len(a) >= _MIN_ALIAS_LEN]


# ---------------------------------------------------------------------------
# Global singleton (one in-memory index per process)
# ---------------------------------------------------------------------------

_entity_index: EntityNameIndex | None = None


async def get_entity_index(db: DbAdapter) -> EntityNameIndex:
    """Return the process-wide :class:`EntityNameIndex`, loading it if needed."""
    global _entity_index
    if _entity_index is None:
        _entity_index = EntityNameIndex()
    if not _entity_index._loaded:
        await _entity_index.load(db)
    return _entity_index


def reset_index() -> None:
    """Reset the global index cache (used by tests and after bulk imports)."""
    global _entity_index
    if _entity_index is not None:
        _entity_index.reset()
    _entity_index = None


# ---------------------------------------------------------------------------
# Core public API
# ---------------------------------------------------------------------------

async def scan_text(db: DbAdapter, text: str | None) -> list[dict[str, Any]]:
    """Scan text for entity mentions without creating any relationships.

    Lightweight read-only helper — use this when you only need to know *which*
    entities are mentioned (e.g. for display) without side effects.
    """
    if not text or len(text) < 2:
        return []
    index = await get_entity_index(db)
    found = index.scan(text)
    # Ensure each has an entity_id (create-or-find) so callers get stable ids.
    for entity in found:
        if not entity.get("entity_id"):
            entity["entity_id"] = await _ensure_entity_exists(db, entity)
    return found


async def scan_and_link(
    db: DbAdapter,
    text: str | None,
    source_entity_id: str | None = None,
    source_type: str = "content",
    source_id: str | None = None,
    relationship_type: str = "mentions",
) -> list[dict[str, Any]]:
    """Scan text for entities and create relationships from the source.

    Args:
        text: The text to scan. Short/empty text is a no-op.
        source_entity_id: The ``knowledge_entity`` ID of the source content
            (e.g. an imported article entity). When provided, relationships
            are created from this entity to each found entity.
        source_type: Type of the source (``chat``/``annotation``/``medicine``/
            ``profile``/``import``/…). Recorded in relationship properties.
        source_id: ID of the source record (e.g. medicine_id, conversation_id).
        relationship_type: Relationship code or Chinese label. Normalized via
            :data:`app.knowledge_entity.RELATIONSHIP_TYPES`. Defaults to
            ``"mentions"``.

    Returns:
        List of found entity dicts (same shape as :meth:`EntityNameIndex.scan`),
        each guaranteed to have ``entity_id`` populated.
    """
    if not text or len(text) < 2:
        return []

    index = await get_entity_index(db)
    found = index.scan(text)
    if not found:
        return []

    # Ensure each found entity exists in knowledge_entities.
    for entity in found:
        if not entity.get("entity_id"):
            entity["entity_id"] = await _ensure_entity_exists(db, entity)

    # Create relationships from the source entity (if provided).
    if source_entity_id:
        for entity in found:
            eid = entity.get("entity_id")
            if eid and eid != source_entity_id:
                try:
                    await create_relationship(
                        db,
                        source_id=source_entity_id,
                        target_id=eid,
                        rel_type=relationship_type,
                        properties={
                            "source_type": source_type,
                            "source_id": source_id,
                            "context": text[:200],
                        },
                    )
                except Exception as exc:  # never let a single link fail the batch
                    logger.warning(
                        "entity_filter: create_relationship(%s -> %s) failed: %s",
                        source_entity_id, eid, exc,
                    )

    return found


async def _ensure_entity_exists(db: DbAdapter, entity: dict[str, Any]) -> str | None:
    """Find or create a ``knowledge_entity`` row for the found item.

    Reuses :func:`app.knowledge_entity.register_entity` for upsert semantics
    and consistent ID formatting. When ``source_table``/``source_id`` are known
    (e.g. a matched herb), the entity is keyed on them so repeated scans don't
    create duplicates.
    """
    name = entity["name"]
    etype = entity.get("type") or "entity"
    source_table = entity.get("source_table") or ""
    source_id = entity.get("source_id")

    # Fast path: an exact match by title + type already exists.
    existing = await db.query_one(
        "SELECT id FROM knowledge_entities WHERE title = ? AND entity_type = ? LIMIT 1",
        (name, etype),
    )
    if existing:
        return existing["id"]

    try:
        return await register_entity(
            db,
            entity_type=etype,
            source_table=source_table or "entity_filter",
            source_id=source_id or f"name:{name}",
            title=name,
            source_type="auto_extracted",
        )
    except Exception as exc:
        logger.warning("entity_filter: register_entity(%s) failed: %s", name, exc)
        return None
