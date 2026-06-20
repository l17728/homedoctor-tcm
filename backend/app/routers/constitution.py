"""Constitution assessment router — 王琦九种体质自测 (spec §2.3 / §4.2)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import get_current_user
from app.constitution_data import (
    BIASED_TYPES,
    CONSTITUTION_DESCRIPTIONS,
    CONSTITUTION_QUESTIONS,
    NINE_CONSTITUTION_TYPES,
    QUESTION_MAP,
    QUESTIONS_BY_TYPE,
    REVERSE_QUESTION_IDS,
    SCORE_OPTIONS,
)
from app.database import DbAdapter, get_db

router = APIRouter(prefix="/api/constitution", tags=["constitution"])

PRIMARY_THRESHOLD = 40.0
BALANCED_MIN = 60.0
BALANCED_OTHER_MAX = 40.0


def _effective_score(qid: str, raw: int) -> int:
    """Reverse-score negative 平和质 questions (q60: '你容易忘事吗？')."""
    if qid in REVERSE_QUESTION_IDS:
        return 4 - raw
    return raw


def calculate_scores(answers: dict[str, int]) -> dict[str, float]:
    """Calculate constitution type scores from answers.

    For each type, sum effective scores and convert to a 0-100 scale:
        score = sum / (num_questions * 4) * 100

    Missing answers are treated as 0.
    """
    sums: dict[str, float] = {t: 0.0 for t in NINE_CONSTITUTION_TYPES}
    counts: dict[str, int] = {t: 0 for t in NINE_CONSTITUTION_TYPES}

    for q in CONSTITUTION_QUESTIONS:
        counts[q["type"]] += 1
        raw = answers.get(q["id"], 0)
        sums[q["type"]] += _effective_score(q["id"], raw)

    results: dict[str, float] = {}
    for t in NINE_CONSTITUTION_TYPES:
        max_possible = counts[t] * 4
        if max_possible > 0:
            results[t] = round(sums[t] / max_possible * 100, 1)
        else:
            results[t] = 0.0
    return results


def determine_primary_secondary(
    scores: dict[str, float],
) -> tuple[str, list[str]]:
    """Determine primary constitution type and secondary (兼夹) types.

    Rules (王琦九种体质判定标准):
    - 平和质: score >= 60 AND all biased types < 40 → primary is 平和质
    - 偏颇体质: any biased type >= 40 → primary is the highest-scoring biased type
    - 兼夹体质: other biased types (excluding primary) with score >= 40
    """
    balanced_score = scores.get("平和质", 0.0)
    biased_scores = {t: scores.get(t, 0.0) for t in BIASED_TYPES}
    biased_active = {t: s for t, s in biased_scores.items() if s >= PRIMARY_THRESHOLD}

    all_below = all(s < BALANCED_OTHER_MAX for s in biased_scores.values())

    if balanced_score >= BALANCED_MIN and not biased_active and all_below:
        return "平和质", []

    if biased_active:
        primary = max(biased_active, key=biased_active.get)
        secondary = [
            t for t in BIASED_TYPES
            if t != primary and scores.get(t, 0.0) >= PRIMARY_THRESHOLD
        ]
        return primary, secondary

    if biased_scores:
        primary = max(biased_scores, key=biased_scores.get)
        return primary, []

    return "平和质", []


def _parse_assessment(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    for field in ("results", "raw_answers"):
        if isinstance(result.get(field), str):
            try:
                result[field] = json.loads(result[field])
            except (json.JSONDecodeError, TypeError):
                result[field] = {}
    if isinstance(result.get("secondary_types"), str):
        try:
            result["secondary_types"] = json.loads(result["secondary_types"])
        except (json.JSONDecodeError, TypeError):
            result["secondary_types"] = []
    return result


@router.get("/questionnaire")
async def get_questionnaire():
    """Return all 66 questions grouped by constitution type."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for ctype in NINE_CONSTITUTION_TYPES:
        grouped[ctype] = QUESTIONS_BY_TYPE.get(ctype, [])

    return {
        "total_questions": len(CONSTITUTION_QUESTIONS),
        "types": NINE_CONSTITUTION_TYPES,
        "score_options": SCORE_OPTIONS,
        "questions": CONSTITUTION_QUESTIONS,
        "grouped": grouped,
        "descriptions": CONSTITUTION_DESCRIPTIONS,
    }


@router.post("/assess", status_code=status.HTTP_201_CREATED)
async def assess(
    body: dict[str, Any],
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Submit constitution assessment answers, save result, sync profile."""
    answers = body.get("answers")
    if not isinstance(answers, dict) or len(answers) == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="答案不能为空",
        )

    validated: dict[str, int] = {}
    for qid, val in answers.items():
        if qid not in QUESTION_MAP:
            continue
        try:
            ival = int(val)
        except (TypeError, ValueError):
            continue
        if ival < 0:
            ival = 0
        elif ival > 4:
            ival = 4
        validated[qid] = ival

    if not validated:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="答案不能为空",
        )

    scores = calculate_scores(validated)
    primary_type, secondary_types = determine_primary_secondary(scores)

    assessment_id = str(uuid.uuid4())
    user_id = current_user["id"]
    now = datetime.now(timezone.utc).isoformat()

    await db.execute(
        """INSERT INTO constitution_assessments
           (id, user_id, assessed_at, results, primary_type, secondary_types, raw_answers)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            assessment_id,
            user_id,
            now,
            json.dumps(scores, ensure_ascii=False),
            primary_type,
            json.dumps(secondary_types, ensure_ascii=False),
            json.dumps(validated, ensure_ascii=False),
        ),
    )

    await db.execute(
        """INSERT INTO user_profiles (user_id, constitution_type, constitution_secondary, updated_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(user_id) DO UPDATE SET
             constitution_type = excluded.constitution_type,
             constitution_secondary = excluded.constitution_secondary,
             updated_at = excluded.updated_at""",
        (
            user_id,
            primary_type,
            json.dumps(secondary_types, ensure_ascii=False),
            now,
        ),
    )

    return {
        "id": assessment_id,
        "results": scores,
        "primary_type": primary_type,
        "secondary_types": secondary_types,
        "description": CONSTITUTION_DESCRIPTIONS.get(primary_type, ""),
        "assessed_at": now,
    }


@router.get("/history")
async def get_history(
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get current user's assessment history."""
    rows = await db.query(
        """SELECT * FROM constitution_assessments
           WHERE user_id = ? ORDER BY assessed_at DESC""",
        (current_user["id"],),
    )
    return {
        "items": [_parse_assessment(r) for r in rows],
        "total": len(rows),
    }


@router.get("/latest")
async def get_latest(
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get the user's most recent assessment."""
    row = await db.query_one(
        """SELECT * FROM constitution_assessments
           WHERE user_id = ? ORDER BY assessed_at DESC LIMIT 1""",
        (current_user["id"],),
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="暂无评估记录",
        )
    return _parse_assessment(row)
