"""Child emergency triage router — spec §23.1 MVP P0.

Provides age-based questionnaires and red-flag symptom routing for
quick child health triage guidance. This is a medical safety feature.

Design decisions:
    - NO auth required: A panicking parent with a sick child must never
      be blocked by a login screen. Triage endpoints are public.
    - NO database access: Pure computation from triage_data.py.
    - ALWAYS includes disclaimer on every result.
    - Conservative: When in doubt, escalate urgency level.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, status

from app.triage_data import (
    AGE_GROUP_ORDER,
    AGE_GROUPS,
    QUESTIONNAIRES,
    RED_FLAG_KEYWORD_MAP,
    RED_FLAG_SYMPTOMS,
    TRIAGE_DISCLAIMER,
    TRIAGE_LEVELS,
    URGENT_THRESHOLDS,
    answers_to_categories,
    determine_age_group,
    perform_triage,
)

router = APIRouter(prefix="/api/triage", tags=["triage"])


# ---------------------------------------------------------------------------
# GET /api/triage/age-groups — list all age groups and criteria
# ---------------------------------------------------------------------------

@router.get("/age-groups")
async def get_age_groups():
    """Return all available age groups and their criteria.

    Public endpoint — no auth required (safety feature).
    """
    groups = []
    for name in AGE_GROUP_ORDER:
        info = AGE_GROUPS[name]
        entry: dict[str, Any] = {"name": name, "description": info["description"]}
        if "min_days" in info:
            entry["min_days"] = info["min_days"]
            entry["max_days"] = info["max_days"]
        if "min_months" in info:
            entry["min_months"] = info["min_months"]
            entry["max_months"] = info["max_months"]
        entry["key_clinical_note"] = info["key_clinical_note"]
        groups.append(entry)

    return {
        "total_groups": len(groups),
        "groups": groups,
        "triage_levels": TRIAGE_LEVELS,
    }


# ---------------------------------------------------------------------------
# GET /api/triage/questionnaire — get questionnaire for an age group
# ---------------------------------------------------------------------------

@router.get("/questionnaire")
async def get_questionnaire(
    age_months: int | None = Query(None, ge=0, le=168, description="月龄（0-168）"),
    age_group: str | None = Query(None, description="直接指定年龄组名称"),
):
    """Return the triage questionnaire + red flag checklist for an age group.

    Provide either `age_months` (recommended) or `age_group` (by name).
    Public endpoint — no auth required (safety feature).
    """
    # Determine the age group
    if age_months is not None:
        try:
            group = determine_age_group(age_months)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            )
    elif age_group is not None:
        if age_group not in AGE_GROUPS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"无效的年龄组：{age_group}，可选值：{', '.join(AGE_GROUP_ORDER)}",
            )
        group = age_group
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="请提供 age_months 或 age_group 参数",
        )

    questions = QUESTIONNAIRES.get(group, [])
    threshold = URGENT_THRESHOLDS.get(group, {})

    return {
        "age_group": group,
        "age_months": age_months,
        "age_group_info": AGE_GROUPS[group],
        "questions": questions,
        "question_count": len(questions),
        "red_flags": RED_FLAG_SYMPTOMS,
        "urgent_threshold": threshold,
        "triage_levels": TRIAGE_LEVELS,
        "disclaimer": TRIAGE_DISCLAIMER,
    }


# ---------------------------------------------------------------------------
# GET /api/triage/red-flags — list all red flag symptoms
# ---------------------------------------------------------------------------

@router.get("/red-flags")
async def get_red_flags():
    """Return all red flag symptoms that require immediate ER visit.

    Public endpoint — no auth required (safety feature).
    """
    return {
        "total": len(RED_FLAG_SYMPTOMS),
        "red_flags": RED_FLAG_SYMPTOMS,
        "keyword_cross_reference": RED_FLAG_KEYWORD_MAP,
        "disclaimer": TRIAGE_DISCLAIMER,
    }


# ---------------------------------------------------------------------------
# POST /api/triage/assess — perform triage assessment
# ---------------------------------------------------------------------------

@router.post("/assess")
async def assess(body: dict[str, Any]):
    """Perform triage assessment and return the urgency level.

    Public endpoint — no auth required (safety feature).

    Request body:
        {
            "age_months": int,          # Required: 0-168
            "age_days": int | null,     # Optional: for newborn precision
            "answers": [                # List of {id, value} objects
                {"id": "Q01", "value": 38.5},
                {"id": "Q03", "value": "嗜睡"},
                ...
            ],
            "red_flags": ["RF01", ...]  # List of confirmed red flag IDs
        }

    Response:
        TriageResult with level, action, warnings, recommendations, disclaimer.

    The assessment is intentionally conservative — when in doubt, it
    escalates. Every result includes a medical disclaimer.
    """
    # --- Validate age_months ---
    age_months = body.get("age_months")
    if age_months is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="必须提供 age_months 参数",
        )
    try:
        age_months = int(age_months)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="age_months 必须是整数",
        )

    age_days = body.get("age_days")
    if age_days is not None:
        try:
            age_days = int(age_days)
        except (TypeError, ValueError):
            age_days = None

    # Determine age group (validates age range)
    try:
        age_group = determine_age_group(age_months, age_days)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    # --- Parse answers ---
    raw_answers = body.get("answers", [])
    if not isinstance(raw_answers, list):
        raw_answers = []

    answers_by_category = answers_to_categories(age_group, raw_answers)

    # --- Parse red flags ---
    red_flag_ids = body.get("red_flags", [])
    if not isinstance(red_flag_ids, list):
        red_flag_ids = []

    # Filter to known red flag IDs
    valid_red_flag_ids = [str(rf) for rf in red_flag_ids if str(rf).startswith("RF")]

    # --- Perform triage ---
    result = perform_triage(
        age_months=age_months,
        answers_by_category=answers_by_category,
        red_flag_ids=valid_red_flag_ids,
        age_days=age_days,
    )

    return result
