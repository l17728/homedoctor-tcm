"""User profile router — constitution档案 + 健康信息 (spec §4.2)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import get_current_user
from app.audit import log_audit
from app.database import DbAdapter, get_db
from app.repository import current_tenant_id

router = APIRouter(prefix="/api/profile", tags=["profile"])

JSON_ARRAY_FIELDS = {"allergies", "health_conditions", "constitution_secondary"}
SCALAR_FIELDS = {
    "display_name": "display_name",
    "birth_year": "birth_year",
    "gender": "gender",
    "height_cm": "height_cm",
    "weight_kg": "weight_kg",
    "blood_type": "blood_type",
    "notes": "notes",
}


def _parse_profile(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    for field in ("allergies", "health_conditions", "constitution_secondary"):
        if isinstance(result.get(field), str):
            try:
                result[field] = json.loads(result[field])
            except (json.JSONDecodeError, TypeError):
                result[field] = []
        elif result.get(field) is None:
            result[field] = []
    if "is_pregnant" in result:
        result["is_pregnant"] = bool(result["is_pregnant"])
    return result


@router.get("")
async def get_profile(
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get current user's profile. Returns empty profile if not yet created."""
    row = await db.query_one(
        "SELECT * FROM user_profiles WHERE user_id = ?",
        (current_user["id"],),
    )
    if not row:
        return {
            "user_id": current_user["id"],
            "display_name": None,
            "birth_year": None,
            "gender": None,
            "height_cm": None,
            "weight_kg": None,
            "constitution_type": None,
            "constitution_secondary": [],
            "allergies": [],
            "health_conditions": [],
            "is_pregnant": False,
            "blood_type": None,
            "notes": None,
        }
    return _parse_profile(row)


@router.put("")
async def update_profile(
    body: dict[str, Any],
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Update current user's profile. Creates if not exists."""
    user_id = current_user["id"]
    now = datetime.now(timezone.utc).isoformat()

    existing = await db.query_one(
        "SELECT * FROM user_profiles WHERE user_id = ?", (user_id,)
    )

    set_parts: list[str] = []
    values: list[Any] = []

    for body_key, col_name in SCALAR_FIELDS.items():
        if body_key in body and body[body_key] is not None:
            set_parts.append(f"{col_name} = ?")
            values.append(body[body_key])

    for field in ("allergies", "health_conditions"):
        if field in body and body[field] is not None:
            set_parts.append(f"{field} = ?")
            values.append(json.dumps(body[field], ensure_ascii=False))

    if "is_pregnant" in body and body["is_pregnant"] is not None:
        set_parts.append("is_pregnant = ?")
        values.append(1 if body["is_pregnant"] else 0)

    if not existing:
        col_names = ["user_id", "updated_at"] + [p.split(" = ")[0] for p in set_parts]
        placeholders = ", ".join(["?"] * len(col_names))
        col_str = ", ".join(col_names)
        insert_values: list[Any] = [user_id, now] + values
        await db.execute(
            f"INSERT INTO user_profiles ({col_str}) VALUES ({placeholders})",
            tuple(insert_values),
        )
    else:
        if set_parts:
            set_parts.append("updated_at = ?")
            values.append(now)
            values.append(user_id)
            await db.execute(
                f"UPDATE user_profiles SET {', '.join(set_parts)} WHERE user_id = ?",
                tuple(values),
            )

    row = await db.query_one(
        "SELECT * FROM user_profiles WHERE user_id = ?", (user_id,)
    )
    await log_audit(db, tenant_id=current_tenant_id.get(), user_id=user_id,
                    action="update", entity_type="user_profile", entity_id=user_id,
                    changes={k: v for k, v in body.items() if v is not None})
    return _parse_profile(row)
