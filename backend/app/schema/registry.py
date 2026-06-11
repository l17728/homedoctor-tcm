"""FileSchemaRegistry: loads JSON config files for entity schemas."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import settings


class SchemaField:
    """A single field definition from a schema JSON."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.id: str = data.get("id", "")
        self.name: str = data.get("name", "")
        self.type: str = data.get("type", "string")
        self.label: str = data.get("label", "")
        self.required: bool = data.get("required", False)
        self.group: str = data.get("group", "")
        self.order: int = data.get("order", 0)
        self.enum_values: list[str] = data.get("enumValues", [])

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "label": self.label,
            "required": self.required,
            "group": self.group,
            "order": self.order,
        }
        if self.enum_values:
            d["enumValues"] = self.enum_values
        return d


class SchemaDefinition:
    """A complete schema definition for one node type."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.node_type: str = data.get("nodeType", "")
        self.label: str = data.get("label", "")
        self.fields: list[SchemaField] = [
            SchemaField(f) for f in data.get("fields", [])
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodeType": self.node_type,
            "label": self.label,
            "fields": [f.to_dict() for f in self.fields],
        }


class FileSchemaRegistry:
    """Loads and caches JSON schema files from config/schemas/."""

    def __init__(self, config_dir: str | None = None) -> None:
        self._config_dir = Path(config_dir or settings.CONFIG_DIR)
        self._schemas: dict[str, SchemaDefinition] = {}
        self._loaded = False

    def load(self) -> None:
        """Load all JSON schema files from the config directory."""
        if self._loaded:
            return

        schemas_dir = self._config_dir
        if not schemas_dir.is_absolute():
            # Resolve relative to the backend directory
            schemas_dir = Path(__file__).parent.parent / schemas_dir

        if schemas_dir.exists():
            for json_file in schemas_dir.glob("*.json"):
                try:
                    data = json.loads(json_file.read_text(encoding="utf-8"))
                    schema = SchemaDefinition(data)
                    self._schemas[schema.node_type] = schema
                except (json.JSONDecodeError, KeyError) as e:
                    import logging
                    logging.getLogger(__name__).warning(
                        f"Failed to load schema {json_file}: {e}"
                    )

        self._loaded = True

    def get_schema(self, node_type: str) -> SchemaDefinition | None:
        """Get a schema definition by node type."""
        self.load()
        return self._schemas.get(node_type)

    def list_schemas(self) -> list[SchemaDefinition]:
        """List all loaded schemas."""
        self.load()
        return list(self._schemas.values())

    def list_schema_dicts(self) -> list[dict[str, Any]]:
        """List all schemas as dicts."""
        return [s.to_dict() for s in self.list_schemas()]


# Global singleton
schema_registry = FileSchemaRegistry()
