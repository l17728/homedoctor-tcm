"""Formulations router — 智能配伍引擎 API (spec §16.3).

Endpoints:
- POST /api/formulations/recommend     — recommend herbs by symptoms + constitution
- POST /api/formulations/tea-recipe    — generate 代茶饮 (tea infusion) recipe
- POST /api/formulations/from-inventory — recommend from user's medicine cabinet (auth)
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import get_current_user
from app.database import DbAdapter, get_db
from app.formulation_engine import (
    generate_tea_recipe,
    recommend_from_inventory,
    recommend_herbs,
)
from app.repository import MedicineRepository, current_tenant_id, current_member_id

router = APIRouter(prefix="/api/formulations", tags=["formulations"])


@router.post("/recommend")
async def recommend_endpoint(
    body: dict[str, Any],
    db: DbAdapter = Depends(get_db),
):
    """推荐中药组合 — match herbs by symptoms and constitution.

    Request body:
        {
            "symptoms": ["气虚", "乏力"],   # required, free-text keywords
            "constitution": "气虚质",       # optional, one of 九种体质
            "exclude": ["人参"]             # optional, herbs to filter out
        }

    Response: ``{ recommendations, symptoms, constitution, safety_check, disclaimer }``
    """
    symptoms = body.get("symptoms")
    if not isinstance(symptoms, list) or not symptoms:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="symptoms 不能为空，请至少提供一个症状关键词",
        )

    constitution = body.get("constitution")
    if constitution is not None and not isinstance(constitution, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="constitution 必须是字符串（如 '气虚质'）",
        )

    exclude = body.get("exclude")
    if exclude is not None and not isinstance(exclude, list):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="exclude 必须是字符串数组",
        )

    return await recommend_herbs(
        db=db,
        symptoms=[str(s) for s in symptoms],
        constitution=constitution,
        exclude=[str(e) for e in (exclude or [])],
    )


@router.post("/tea-recipe")
async def tea_recipe_endpoint(
    body: dict[str, Any],
    db: DbAdapter = Depends(get_db),
):
    """生成代茶饮配方 — 3-5 herbs with safe tea-range doses and brewing guide.

    Request body:
        {
            "symptoms": ["失眠", "心悸"],
            "constitution": "气虚质",   # optional
            "exclude": ["人参"]         # optional
        }

    Response: ``{ name, herbs, brewing, efficacy, safety_check, disclaimer }``
    """
    symptoms = body.get("symptoms")
    if not isinstance(symptoms, list) or not symptoms:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="symptoms 不能为空，请至少提供一个症状关键词",
        )

    constitution = body.get("constitution")
    if constitution is not None and not isinstance(constitution, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="constitution 必须是字符串",
        )

    exclude = body.get("exclude")
    if exclude is not None and not isinstance(exclude, list):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="exclude 必须是字符串数组",
        )

    return await generate_tea_recipe(
        db=db,
        symptoms=[str(s) for s in symptoms],
        constitution=constitution,
        exclude=[str(e) for e in (exclude or [])],
    )


@router.post("/from-inventory")
async def from_inventory_endpoint(
    body: dict[str, Any],
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """药箱优先推荐 — recommend from the user's medicine cabinet (auth required).

    Loads the current user's medicines (respecting tenant_id / member_id),
    matches them against the supplied symptoms, and additionally suggests
    knowledge-base herbs that are missing from the cabinet.

    Request body:
        { "symptoms": ["失眠", "心悸"] }

    Response: ``{ recommendations, missing_suggestions, symptoms, safety_check, disclaimer }``
    """
    symptoms = body.get("symptoms")
    if not isinstance(symptoms, list) or not symptoms:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="symptoms 不能为空，请至少提供一个症状关键词",
        )

    # Load the user's full medicine cabinet (no pagination — match everything).
    repo = MedicineRepository(db)
    rows, _ = await repo.list_medicines(page=1, page_size=1000)

    # Parse JSON-encoded fields so the engine can read them as objects.
    parsed: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        for field in ("active_ingredients", "herbal_fields", "properties", "batches", "photos"):
            import json
            if isinstance(item.get(field), str):
                try:
                    item[field] = json.loads(item[field])
                except (json.JSONDecodeError, TypeError):
                    item[field] = [] if field in ("active_ingredients", "batches", "photos") else {}
        parsed.append(item)

    return await recommend_from_inventory(
        db=db,
        symptoms=[str(s) for s in symptoms],
        user_medicines=parsed,
    )
