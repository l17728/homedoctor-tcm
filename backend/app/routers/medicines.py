"""Medicines router — full CRUD for family drug cabinet (auth required)."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth import get_current_user
from app.database import DbAdapter, get_db
from app.models import MedicineCreate, MedicineUpdate
from app.repository import MedicineRepository

router = APIRouter(prefix="/api/medicines", tags=["medicines"])


def _parse_medicine(row: dict[str, Any]) -> dict[str, Any]:
    """Parse a medicine row, converting JSON strings to objects."""
    result = dict(row)
    for field in ("active_ingredients", "batches", "photos", "herbal_fields", "properties"):
        if isinstance(result.get(field), str):
            try:
                result[field] = json.loads(result[field])
            except (json.JSONDecodeError, TypeError):
                result[field] = [] if field in ("active_ingredients", "batches", "photos") else {}
    return result


@router.get("")
async def list_medicines(
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List current user's medicines."""
    repo = MedicineRepository(db)
    rows, total = await repo.list_medicines(page=page, page_size=pageSize)
    medicines = [_parse_medicine(r) for r in rows]
    total_pages = (total + pageSize - 1) // pageSize
    return {
        "items": medicines,
        "total": total,
        "page": page,
        "pageSize": pageSize,
        "totalPages": total_pages,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_medicine(
    body: dict,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Add a new medicine to the family drug cabinet."""
    repo = MedicineRepository(db)
    medicine_id = await repo.create_medicine(body)
    medicine = await repo.get_medicine(medicine_id)
    return _parse_medicine(medicine)


@router.get("/{medicine_id}")
async def get_medicine(
    medicine_id: str,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get medicine detail by ID."""
    repo = MedicineRepository(db)
    row = await repo.get_medicine(medicine_id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到该药品",
        )
    return _parse_medicine(row)


@router.put("/{medicine_id}")
async def update_medicine(
    medicine_id: str,
    body: dict,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Update a medicine."""
    repo = MedicineRepository(db)
    # Filter out None values
    update_data = {k: v for k, v in body.items() if v is not None}
    success = await repo.update_medicine(medicine_id, update_data)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到该药品",
        )
    medicine = await repo.get_medicine(medicine_id)
    return _parse_medicine(medicine)


@router.delete("/{medicine_id}")
async def delete_medicine(
    medicine_id: str,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Delete a medicine."""
    repo = MedicineRepository(db)
    success = await repo.delete_medicine(medicine_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到该药品",
        )
    return {"detail": "已删除"}
