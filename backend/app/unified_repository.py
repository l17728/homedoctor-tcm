"""Unified repository — schema-aware CRUD over graph_nodes / graph_edges.

Phase 2 of the architecture refactoring. This module ports /fighting's
``SqliteRepository`` (apps/backend/src/repository.ts) to Python, with two key
adaptations for the homedoctor schema:

1. The homedoctor ``graph_nodes`` table does NOT have a ``tenant_id`` column
   (knowledge graph nodes are global reference data). Tenant isolation happens
   at a higher layer (``app.repository.BaseRepository``). The unified
   repository therefore operates globally and is safe to use from CLI tools,
   migration scripts, and the knowledge-graph rebuild pipeline.
2. ``graph_nodes`` does not have ``updated_at`` — only ``created_at``. We
   preserve that contract.

Each row's ``properties`` column stores a JSON object whose keys are the
field ``id`` values declared in the corresponding ``node_*.json`` schema.
``search_text`` is a flattened, space-joined string of all property values
so SQLite's built-in LIKE can do cheap substring matches without FTS5.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from app.database import DbAdapter
from app.unified_schema import FileSchemaRegistry, is_safe_json_key

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    """ISO-8601 UTC timestamp — stable across DB driver quirks."""
    return datetime.now(timezone.utc).isoformat()


def _flatten(properties: dict[str, Any]) -> str:
    """Flatten property values into a space-joined search string.

    Objects/arrays are JSON-encoded; None becomes the empty string. Mirrors
    /fighting's ``SqliteRepository.flatten``.
    """
    parts: list[str] = []
    for value in properties.values():
        if value is None:
            continue
        if isinstance(value, (dict, list)):
            parts.append(json.dumps(value, ensure_ascii=False))
        else:
            parts.append(str(value))
    return " ".join(parts)


def _decode_properties(raw: Any) -> dict[str, Any]:
    """Defensive JSON decode for the ``properties`` column."""
    if raw is None or raw == "":
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            decoded = json.loads(raw)
            return decoded if isinstance(decoded, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}
    return {}


def _row_to_node(row: dict[str, Any] | None) -> dict[str, Any] | None:
    """Map a raw SQL row to the public node dict shape."""
    if row is None:
        return None
    return {
        "id": row["id"],
        "node_type": row["node_type"],
        "label": row.get("label", ""),
        "properties": _decode_properties(row.get("properties")),
        "search_text": row.get("search_text", ""),
        "created_at": row.get("created_at", ""),
    }


def _row_to_edge(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row["id"],
        "edge_type": row["edge_type"],
        "source_id": row["source_id"],
        "target_id": row["target_id"],
        "properties": _decode_properties(row.get("properties")),
        "created_at": row.get("created_at", ""),
    }


class UnifiedRepository:
    """Schema-aware CRUD over the ``graph_nodes`` / ``graph_edges`` tables.

    The repository is intentionally stateless beyond its constructor args:
    each method issues its own SQL through the injected :class:`DbAdapter`,
    so multiple short-lived instances (e.g. one per CLI invocation) are fine.
    """

    def __init__(self, db: DbAdapter, registry: FileSchemaRegistry) -> None:
        self.db = db
        self.registry = registry

    # ------------------------------------------------------------------
    # Node CRUD
    # ------------------------------------------------------------------

    async def create_node(
        self,
        node_type: str,
        properties: dict[str, Any],
        label: str = "",
    ) -> dict[str, Any]:
        """Create a ``graph_node`` row.

        ``label`` defaults to the first identity key value (e.g. the herb's
        ``名称``). ``search_text`` is auto-derived from ``properties`` so
        substring search works without FTS5.
        """
        node_id = str(uuid.uuid4())
        schema = self.registry.get_schema(node_type)

        # Auto-derive a label from the schema's identity key when omitted.
        if not label and schema is not None:
            identity_key = self.registry.get_identity_key(node_type)
            if identity_key:
                label = str(properties.get(identity_key, ""))

        # If still no label and no schema identity hint, fall back to the
        # first string-valued property so the row is never label-less.
        if not label:
            for value in properties.values():
                if isinstance(value, str) and value.strip():
                    label = value.strip()
                    break

        properties_json = json.dumps(properties, ensure_ascii=False)
        search_text = _flatten(properties)

        await self.db.execute(
            "INSERT INTO graph_nodes (id, node_type, label, properties, search_text, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (node_id, node_type, label, properties_json, search_text, _now_iso()),
        )
        node = await self.get_node(node_id)
        assert node is not None, "freshly-inserted node must be readable"
        return node

    async def get_node(self, node_id: str) -> dict[str, Any] | None:
        row = await self.db.query_one(
            "SELECT id, node_type, label, properties, search_text, created_at "
            "FROM graph_nodes WHERE id = ?",
            (node_id,),
        )
        return _row_to_node(row)

    async def update_node(self, node_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        """Shallow-merge ``patch`` into the existing node's properties."""
        current = await self.get_node(node_id)
        if current is None:
            raise KeyError(f"node not found: {node_id}")

        merged: dict[str, Any] = dict(current["properties"])
        merged.update(patch)

        properties_json = json.dumps(merged, ensure_ascii=False)
        search_text = _flatten(merged)

        await self.db.execute(
            "UPDATE graph_nodes SET properties = ?, search_text = ? WHERE id = ?",
            (properties_json, search_text, node_id),
        )
        updated = await self.get_node(node_id)
        assert updated is not None
        return updated

    async def query_nodes(
        self,
        node_type: str,
        filter: dict[str, Any] | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query nodes by type, optionally narrowing by a property filter.

        Without ``filter`` the query is pure SQL. With a filter, results are
        post-processed in Python (``===`` semantics on each key). For
        single-key string equality, prefer :meth:`query_nodes_by_property`
        which pushes the predicate into SQLite via ``json_extract``.
        """
        capped_limit = max(1, min(int(limit), 1000))
        rows = await self.db.query(
            "SELECT id, node_type, label, properties, search_text, created_at "
            "FROM graph_nodes WHERE node_type = ? "
            "ORDER BY created_at DESC LIMIT ?",
            (node_type, capped_limit),
        )
        nodes = [_row_to_node(r) for r in rows]  # type: ignore[arg-type]
        if filter:
            nodes = [
                n
                for n in nodes
                if n is not None
                and all(n["properties"].get(k) == v for k, v in filter.items())
            ]
        return [n for n in nodes if n is not None]

    async def query_nodes_by_property(
        self, node_type: str, key: str, value: str
    ) -> list[dict[str, Any]]:
        """SQL-pushdown single-key string equality via ``json_extract``.

        Equivalent to ``query_nodes(node_type, {key: value})`` but pushes the
        filter into SQLite so we don't pay O(N) JSON decode + Python filter
        for hot paths. Mirrors /fighting ``queryNodesByProperty``.

        ``key`` MUST pass :func:`is_safe_json_key` to prevent JSON-path
        injection. ``value`` is parameterised and is therefore safe by
        construction.
        """
        if not is_safe_json_key(key):
            raise ValueError(f"query_nodes_by_property: unsafe key {key!r}")
        # Coerce value to string — json_extract yields TEXT for JSON strings.
        if not isinstance(value, str):
            value = str(value)
        rows = await self.db.query(
            "SELECT id, node_type, label, properties, search_text, created_at "
            "FROM graph_nodes "
            "WHERE node_type = ? AND json_extract(properties, '$." + key + "') = ? "
            "ORDER BY created_at DESC",
            (node_type, value),
        )
        return [n for n in (_row_to_node(r) for r in rows) if n is not None]

    async def find_or_create(
        self,
        node_type: str,
        identity_key: str,
        identity_value: str,
        label: str = "",
    ) -> dict[str, Any]:
        """Idempotent upsert by identity key.

        Looks up by ``json_extract(properties, '$.<identity_key>') = ?``;
        returns the existing node if found, otherwise creates a new node whose
        properties seed the identity key. Used heavily by the migration
        script and the knowledge-graph rebuild pipeline.
        """
        existing = await self.query_nodes_by_property(
            node_type, identity_key, identity_value
        )
        if existing:
            return existing[0]
        return await self.create_node(
            node_type,
            {identity_key: identity_value},
            label=label or identity_value,
        )

    async def delete_node(self, node_id: str) -> bool:
        """Delete a node and any edges that reference it.

        Returns True if a row was deleted, False if the node did not exist.
        Edge cleanup mirrors /fighting: both ``source_id`` and ``target_id``
        references are pruned so we never leave dangling edges.
        """
        existing = await self.get_node(node_id)
        if existing is None:
            return False
        await self.db.execute(
            "DELETE FROM graph_edges WHERE source_id = ? OR target_id = ?",
            (node_id, node_id),
        )
        await self.db.execute("DELETE FROM graph_nodes WHERE id = ?", (node_id,))
        return True

    # ------------------------------------------------------------------
    # Edge CRUD
    # ------------------------------------------------------------------

    async def create_edge(
        self,
        edge_type: str,
        source_id: str,
        target_id: str,
        properties: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        edge_id = str(uuid.uuid4())
        properties = properties or {}
        properties_json = json.dumps(properties, ensure_ascii=False)
        await self.db.execute(
            "INSERT INTO graph_edges (id, edge_type, source_id, target_id, properties, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (edge_id, edge_type, source_id, target_id, properties_json, _now_iso()),
        )
        row = await self.db.query_one(
            "SELECT id, edge_type, source_id, target_id, properties, created_at "
            "FROM graph_edges WHERE id = ?",
            (edge_id,),
        )
        edge = _row_to_edge(row)
        assert edge is not None
        return edge

    async def query_edges(
        self,
        source_id: str | None = None,
        target_id: str | None = None,
        edge_type: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if source_id is not None:
            clauses.append("source_id = ?")
            params.append(source_id)
        if target_id is not None:
            clauses.append("target_id = ?")
            params.append(target_id)
        if edge_type is not None:
            clauses.append("edge_type = ?")
            params.append(edge_type)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = await self.db.query(
            "SELECT id, edge_type, source_id, target_id, properties, created_at "
            f"FROM graph_edges{where} ORDER BY created_at DESC",
            tuple(params),
        )
        return [e for e in (_row_to_edge(r) for r in rows) if e is not None]

    async def delete_edges(
        self,
        source_id: str | None = None,
        edge_type: str | None = None,
    ) -> int:
        """Delete edges matching the given filters.

        Returns the number of rows deleted. At least one filter MUST be
        supplied — refusing an empty filter is a safety rail against
        accidental ``DELETE FROM graph_edges`` (mirrors /fighting's contract).
        """
        if source_id is None and edge_type is None:
            raise ValueError(
                "delete_edges: refuse to delete all edges — supply at least one filter"
            )
        clauses: list[str] = []
        params: list[Any] = []
        if source_id is not None:
            clauses.append("source_id = ?")
            params.append(source_id)
        if edge_type is not None:
            clauses.append("edge_type = ?")
            params.append(edge_type)
        where = " AND ".join(clauses)
        cursor = await self.db.execute(
            f"DELETE FROM graph_edges WHERE {where}", tuple(params)
        )
        # aiosqlite Cursor exposes ``rowcount``.
        return getattr(cursor, "rowcount", 0) or 0
