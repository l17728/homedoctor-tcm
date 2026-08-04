"""Schemas router — serves JSON schema definitions for entity types."""

from __future__ import annotations


import logging

logger = logging.getLogger(__name__)
from typing import Any

from fastapi import APIRouter, HTTPException, status

from app.schema.registry import schema_registry

router = APIRouter(prefix="/api/schemas", tags=["schemas"])


@router.get("")
async def list_schemas() -> dict[str, Any]:
    """List all available schema types."""
    return {"items": schema_registry.list_schema_dicts()}


@router.get("/{node_type}")
async def get_schema(node_type: str) -> dict[str, Any]:
    """Get schema definition for a specific type (herb, medicine, formula)."""
    schema = schema_registry.get_schema(node_type)
    if schema is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"未找到类型为「{node_type}」的架构定义",
        )
    return schema.to_dict()
