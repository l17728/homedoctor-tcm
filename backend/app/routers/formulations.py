"""Formulations router — 智能配伍引擎 API (spec §16.3).

Endpoints:
- POST /api/formulations/recommend     — recommend herbs by symptoms + constitution
- POST /api/formulations/tea-recipe    — generate 代茶饮 (tea infusion) recipe
- POST /api/formulations/from-inventory — recommend from user's medicine cabinet (auth)
"""

from __future__ import annotations

import logging
logger = logging.getLogger(__name__)

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import get_current_user
from app.database import DbAdapter, get_db
from app.entity_filter import scan_and_link
from app.formulation_engine import (
    generate_tea_recipe,
    recommend_from_inventory,
    recommend_herbs,
)
from app.safety_engine import DISCLAIMER
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

    result = await recommend_herbs(
        db=db,
        symptoms=[str(s) for s in symptoms],
        constitution=constitution,
        exclude=[str(e) for e in (exclude or [])],
    )

    # Non-blocking: ensure recommended herbs exist as knowledge-graph entities.
    try:
        rec_names = [h.get("name", "") for h in result.get("recommendations", []) if h.get("name")]
        if rec_names:
            await scan_and_link(
                db, "、".join(rec_names),
                source_type="formulation",
                relationship_type="recommends",
            )
    except Exception as exc:
        logger.warning("scan_and_link failed: %s", exc)

    return result


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


@router.post("/joint-recommend")
async def joint_recommend_endpoint(
    body: dict[str, Any],
    db: DbAdapter = Depends(get_db),
):
    """疗法↔方药联合推荐 — herbs + therapies + formulas for given symptoms.

    Combines herb recommendations with matching external therapies (针灸/推拿/
    艾灸/拔罐) and classical formulas, giving a comprehensive treatment plan.

    Request body:
        {
            "symptoms": ["失眠", "心悸"],
            "constitution": "气虚质",
            "exclude": ["人参"]
        }

    Response: ``{ herbs, therapies, formulas, safety_check, disclaimer }``
    """
    symptoms = body.get("symptoms")
    if not isinstance(symptoms, list) or not symptoms:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="symptoms 不能为空",
        )

    constitution = body.get("constitution")
    exclude = body.get("exclude") or []

    herb_result = await recommend_herbs(
        db=db,
        symptoms=[str(s) for s in symptoms],
        constitution=constitution if isinstance(constitution, str) else None,
        exclude=[str(e) for e in exclude],
        limit=8,
    )

    therapy_recs = await _recommend_therapies(db, [str(s) for s in symptoms])
    formula_recs = await _recommend_formulas(db, [str(s) for s in symptoms])

    return {
        "herbs": herb_result.get("recommendations", []),
        "therapies": therapy_recs,
        "formulas": formula_recs,
        "symptoms": list(symptoms),
        "constitution": constitution,
        "safety_check": herb_result.get("safety_check"),
        "disclaimer": DISCLAIMER,
    }


async def _recommend_therapies(
    db: DbAdapter, symptoms: list[str], limit: int = 6
) -> list[dict[str, Any]]:
    """Match therapies by symptom keyword hits in indications."""
    rows = await db.query(
        "SELECT id, title, summary, category, content_preview, properties "
        "FROM knowledge_entities WHERE entity_type = 'therapy' AND status = 'active'"
    )
    scored: list[dict[str, Any]] = []
    import json
    for row in rows:
        text = " ".join(filter(None, [
            row.get("title"), row.get("summary"),
            row.get("content_preview"), row.get("category"),
        ]))
        props = row.get("properties")
        if isinstance(props, str):
            try:
                props = json.loads(props)
            except Exception:
                props = {}
        if isinstance(props, dict):
            for v in props.values():
                if isinstance(v, list):
                    text += " " + " ".join(str(x) for x in v)
                elif isinstance(v, str):
                    text += " " + v

        score = sum(1 for s in symptoms if s in text)
        if score == 0:
            continue
        scored.append({
            "id": row.get("id"),
            "title": row.get("title"),
            "category": row.get("category"),
            "summary": row.get("summary"),
            "indications": props.get("indications", []) if isinstance(props, dict) else [],
            "technique": props.get("technique", "") if isinstance(props, dict) else "",
            "score": score,
        })
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:limit]


async def _recommend_formulas(
    db: DbAdapter, symptoms: list[str], limit: int = 5
) -> list[dict[str, Any]]:
    """Match classical formulas by symptom keyword hits in indications."""
    rows = await db.query(
        "SELECT id, name, efficacy, indications, category, properties "
        "FROM formulas ORDER BY name"
    )
    formula_rows = list(rows)

    ke_rows = await db.query(
        """SELECT id, title, summary, content_preview, category, properties
           FROM knowledge_entities
           WHERE entity_type='formula' AND status='active' AND tenant_id IS NULL"""
    )
    existing_ids = {r.get("id") for r in formula_rows}
    for ke in ke_rows:
        if ke["id"] not in existing_ids:
            formula_rows.append({
                "id": ke["id"],
                "name": ke["title"],
                "efficacy": ke.get("summary", ""),
                "indications": ke.get("content_preview", ""),
                "category": ke.get("category", ""),
                "properties": ke.get("properties", "{}"),
            })

    scored: list[dict[str, Any]] = []
    for row in formula_rows:
        text = " ".join(filter(None, [
            row.get("name"), row.get("efficacy"),
            row.get("indications"), row.get("category"),
        ]))
        score = sum(1 for s in symptoms if s in text)
        if score == 0:
            continue
        scored.append({
            "id": row.get("id"),
            "name": row.get("name"),
            "category": row.get("category"),
            "efficacy": row.get("efficacy"),
            "indications": row.get("indications"),
            "score": score,
        })
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:limit]


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
