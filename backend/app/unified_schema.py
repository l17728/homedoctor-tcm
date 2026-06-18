"""Unified schema layer — Pydantic port of /fighting types.ts + registry.ts.

Phase 2 of the architecture refactoring: graph_nodes becomes the authoritative
entity store with JSON-schema-driven field definitions.

This module is intentionally self-contained — it does NOT import from
``app.schema.registry`` (which still serves the legacy per-table schemas at
``/api/schemas``). Instead it loads the new ``node_*.json`` files from the
project-root ``config/schemas/`` directory.

Key differences from the legacy registry:
- Uses Pydantic v2 models instead of plain classes.
- Supports the full 11-type FieldSchema vocabulary from /fighting
  (string/number/date/enum/ref/anchor/boolean/textarea/json/array/sequence).
- Loads only files matching ``node_*.json`` so legacy ``herb.json`` /
  ``formula.json`` / ``medicine.json`` (which use a different field naming
  convention) are left untouched and the existing routers keep working.
- Adds ``get_ref_fields`` / ``get_anchor_fields`` helpers used by the
  unified repository when materialising graph edges.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Field / Node schema models — Pydantic port of /fighting FieldSchema/NodeSchema
# ---------------------------------------------------------------------------

#: The full field-type vocabulary supported by the unified schema layer.
#: Mirrors /fighting/packages/shared/src/types.ts `FieldType`.
VALID_FIELD_TYPES: frozenset[str] = frozenset(
    {
        "string",
        "number",
        "date",
        "datetime",
        "enum",
        "ref",
        "sequence",
        "boolean",
        "textarea",
        "json",
        "array",
    }
)


class FieldSchema(BaseModel):
    """A single field definition — port of /fighting FieldSchema.

    Chinese field names (e.g. ``名称``, ``药性``) are first-class: the JSON path
    key used inside ``properties`` is exactly the field ``id``. The legacy
    camelCase fields (``name``, ``nature``) continue to live in the per-table
    schemas under ``backend/app/config/schemas/`` and are not used here.
    """

    model_config = ConfigDict(extra="allow")

    id: str
    name: str
    type: str
    label: str = ""
    required: bool = False
    group: str = ""
    order: int = 0
    enum_values: list[str] = Field(default_factory=list)
    # ref-typed fields — pointer to another node type (e.g. "herb")
    ref_type: str = ""
    # anchor-typed fields — soft-indexed concept (e.g. "症状", "经络")
    anchor: str = ""
    # Visibility DSL — small eq/ne/in expression evaluated against the same
    # record's properties. NEVER eval'd — callers parse it themselves.
    visible: str = ""
    # /fighting parity: extra metadata that flows through unchanged.
    aliases: list[str] = Field(default_factory=list)
    concept: str = ""
    retired: bool = False
    source: str = "baseline"  # "baseline" or "user"

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> "FieldSchema":
        """Build a FieldSchema from raw JSON, normalising camelCase keys.

        JSON config uses camelCase (``enumValues``, ``refType``) to match
        /fighting; Pydantic models use snake_case. This helper bridges the two
        so we read either form transparently.
        """
        data = dict(raw)
        # id defaults to name when missing (/fighting invariant).
        if "id" not in data:
            data["id"] = data.get("name", "")
        # camelCase → snake_case aliases.
        if "enumValues" in data:
            data.setdefault("enum_values", data.pop("enumValues"))
        if "refType" in data:
            data.setdefault("ref_type", data.pop("refType"))
        return cls.model_validate(data)


class NodeSchema(BaseModel):
    """A complete schema definition for one node type."""

    model_config = ConfigDict(extra="allow")

    node_type: str
    label: str = ""
    identity_keys: list[str] = Field(default_factory=list)
    derived_to_kg: bool = True
    fields: list[FieldSchema] = Field(default_factory=list)

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> "NodeSchema":
        data = dict(raw)
        if "nodeType" in data:
            data.setdefault("node_type", data.pop("nodeType"))
        if "identityKeys" in data:
            data.setdefault("identity_keys", data.pop("identityKeys"))
        if "derivedToKG" in data:
            data.setdefault("derived_to_kg", data.pop("derivedToKG"))
        fields_raw = data.pop("fields", []) or []
        data["fields"] = [FieldSchema.from_raw(f) for f in fields_raw]
        return cls.model_validate(data)

    def get_field(self, field_id: str) -> FieldSchema | None:
        for f in self.fields:
            if f.id == field_id or f.name == field_id:
                return f
        return None


# ---------------------------------------------------------------------------
# FileSchemaRegistry — loads JSON schemas from config/schemas/node_*.json
# ---------------------------------------------------------------------------

#: Restrictive key whitelist for ``query_nodes_by_property``'s json_extract path.
#: Allows ASCII identifiers plus CJK Unified Ideographs (U+4E00 – U+9FFF).
#: This is the Python equivalent of /fighting's `/^[A-Za-z0-9_一-鿿]+$/`.
_SAFE_JSON_KEY = re.compile(r"^[A-Za-z0-9_\u4e00-\u9fff]+$")


def is_safe_json_key(key: str) -> bool:
    """True when ``key`` is safe to splice into a ``json_extract`` path.

    Mirrors /fighting's defence against JSON-path injection: only ASCII
    identifiers plus CJK ideographs pass. Callers MUST validate before using
    a key in ``json_extract(properties, '$.<key>')``.
    """
    return bool(_SAFE_JSON_KEY.match(key))


class FileSchemaRegistry:
    """Loads and caches ``node_*.json`` schema files.

    The default ``config_dir`` is resolved against the project root (parent of
    ``backend/``) so callers from either backend or scripts see the same set
    of files. Pass an absolute path to override.
    """

    def __init__(self, config_dir: str | Path | None = None) -> None:
        if config_dir is None:
            # app/unified_schema.py → app/ → backend/ → homedoctor/ (project root)
            project_root = Path(__file__).resolve().parent.parent.parent
            config_dir = project_root / "config" / "schemas"
        self._config_dir = Path(config_dir)
        self._schemas: dict[str, NodeSchema] = {}
        self._loaded = False

    @property
    def config_dir(self) -> Path:
        return self._config_dir

    def load(self) -> None:
        """Load all ``node_*.json`` files from the config directory.

        Idempotent — calling ``load`` twice is a no-op. Per-file failures are
        logged and skipped so one broken schema cannot poison the rest (mirrors
        /fighting's tolerant-reload contract). Raises only if no files at all
        can be parsed.
        """
        if self._loaded:
            return

        schemas_dir = self._config_dir
        loaded_any = False
        if schemas_dir.exists():
            # node_*.json keeps legacy herb.json/formula.json/medicine.json
            # untouched and the existing /api/schemas router unaffected.
            for json_file in sorted(schemas_dir.glob("node_*.json")):
                try:
                    raw = json.loads(json_file.read_text(encoding="utf-8"))
                    if not isinstance(raw, dict):
                        raise ValueError("schema root must be a JSON object")
                    if "nodeType" not in raw and "node_type" not in raw:
                        raise ValueError("missing nodeType / node_type")
                    if not isinstance(raw.get("fields"), list):
                        raise ValueError("missing or non-list 'fields'")
                    schema = NodeSchema.from_raw(raw)
                    self._schemas[schema.node_type] = schema
                    loaded_any = True
                except (json.JSONDecodeError, ValueError, TypeError) as e:
                    logger.warning(
                        "unified_schema.load.skip file=%s error=%s", json_file, e
                    )

        if not loaded_any and schemas_dir.exists():
            # Signal a total-failure case explicitly: every node_*.json in the
            # directory was unparseable.
            raise RuntimeError(
                f"unified_schema: no schemas parsed from {schemas_dir} "
                f"(all node_*.json files were corrupt)"
            )

        self._loaded = True

    def reload(self) -> None:
        """Force a fresh load — clears cache then calls :meth:`load`."""
        self._schemas.clear()
        self._loaded = False
        self.load()

    def get_schema(self, node_type: str) -> NodeSchema | None:
        self.load()
        return self._schemas.get(node_type)

    def list_schemas(self) -> list[NodeSchema]:
        self.load()
        return list(self._schemas.values())

    def list_node_types(self) -> list[str]:
        self.load()
        return list(self._schemas.keys())

    def get_ref_fields(self, node_type: str) -> list[FieldSchema]:
        """All ref-typed fields for ``node_type`` — used by edge builders."""
        schema = self.get_schema(node_type)
        if schema is None:
            return []
        return [f for f in schema.fields if f.type == "ref" and not f.retired]

    def get_anchor_fields(self, node_type: str) -> list[FieldSchema]:
        """All anchor-typed fields for ``node_type`` — used by edge builders."""
        schema = self.get_schema(node_type)
        if schema is None:
            return []
        return [f for f in schema.fields if f.type == "anchor" or (f.anchor and not f.retired)]

    def get_identity_key(self, node_type: str) -> str | None:
        """First declared identity key for ``node_type``, or None."""
        schema = self.get_schema(node_type)
        if schema is None or not schema.identity_keys:
            return None
        return schema.identity_keys[0]


# ---------------------------------------------------------------------------
# Module-level singleton — lazily constructed on first access.
# ---------------------------------------------------------------------------

_registry_singleton: FileSchemaRegistry | None = None


def get_unified_registry() -> FileSchemaRegistry:
    """Return the process-wide :class:`FileSchemaRegistry` singleton."""
    global _registry_singleton
    if _registry_singleton is None:
        _registry_singleton = FileSchemaRegistry()
    return _registry_singleton
