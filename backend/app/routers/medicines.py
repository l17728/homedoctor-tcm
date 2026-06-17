"""Medicines router — full CRUD for family drug cabinet (auth required)."""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth import get_current_user
from app.audit import log_audit
from app.database import DbAdapter, get_db
from app.models import MedicineCreate, MedicineUpdate
from app.repository import MedicineRepository, current_tenant_id, current_member_id

router = APIRouter(prefix="/api/medicines", tags=["medicines"])

CST = timezone(timedelta(hours=8))


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
    """Add a new medicine to the family drug cabinet.

    The ``properties`` dict may include a ``drugClass`` key with one of:
    ``"中药"``, ``"西药"``, ``"中成药"``. The safety engine uses this value
    to decide whether Layer 1b (中西药交互) applies. When omitted the medicine
    defaults to ``"西药"`` (backward compatible).
    """
    repo = MedicineRepository(db)
    medicine_id = await repo.create_medicine(body)
    medicine = await repo.get_medicine(medicine_id)
    await log_audit(db, tenant_id=current_tenant_id.get(), user_id=current_user["id"],
                    action="create", entity_type="medicine", entity_id=medicine_id, changes=body)
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
    await log_audit(db, tenant_id=current_tenant_id.get(), user_id=current_user["id"],
                    action="update", entity_type="medicine", entity_id=medicine_id, changes=update_data)
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
    await log_audit(db, tenant_id=current_tenant_id.get(), user_id=current_user["id"],
                    action="delete", entity_type="medicine", entity_id=medicine_id)
    return {"detail": "已删除"}


@router.get("/alerts/expiring")
async def get_medicine_alerts(
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get medicines needing attention: expired, expiring soon (≤30 days), low stock (≤5)."""
    repo = MedicineRepository(db)
    tid = repo._tenant_id()
    mid = current_member_id.get()
    now = datetime.now(CST)
    today = now.strftime("%Y-%m-%d")
    soon_date = (now + timedelta(days=30)).strftime("%Y-%m-%d")

    member_clause = " AND family_member_id = ?" if mid else ""
    member_params = (mid,) if mid else ()

    expired = await db.query(
        f"""SELECT * FROM medicines
           WHERE tenant_id = ?{member_clause} AND expiry_date IS NOT NULL AND expiry_date < ? AND expiry_date != ''
           ORDER BY expiry_date ASC""",
        (tid,) + member_params + (today,),
    )

    expiring_soon = await db.query(
        f"""SELECT * FROM medicines
           WHERE tenant_id = ?{member_clause} AND expiry_date IS NOT NULL
             AND expiry_date >= ? AND expiry_date <= ? AND expiry_date != ''
           ORDER BY expiry_date ASC""",
        (tid,) + member_params + (today, soon_date),
    )

    low_stock = await db.query(
        f"""SELECT * FROM medicines
           WHERE tenant_id = ?{member_clause} AND quantity <= 5
           ORDER BY quantity ASC""",
        (tid,) + member_params,
    )

    return {
        "expired": [_parse_medicine(r) for r in expired],
        "expiring_soon": [_parse_medicine(r) for r in expiring_soon],
        "low_stock": [_parse_medicine(r) for r in low_stock],
    }
