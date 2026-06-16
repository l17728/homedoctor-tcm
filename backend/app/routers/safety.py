"""Safety router — drug interaction check + five-layer safety engine."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.database import DbAdapter, get_db
from app.models import (
    SafetyCheckRequest,
    SafetyCheckRequestV2,
    SafetyCheckResponse,
    SafetyCheckResponseV2,
    SafetyWarning,
    SafetyWarningV2,
)
from app.repository import SafetyRepository
from app.safety_engine import run_safety_check

router = APIRouter(prefix="/api/safety", tags=["safety"])


@router.post("/check", response_model=SafetyCheckResponse)
async def safety_check(body: SafetyCheckRequest, db: DbAdapter = Depends(get_db)):
    """Check for drug interactions between herbs and medicines (V1 legacy)."""
    repo = SafetyRepository(db)
    conflicts = await repo.find_conflicts(body.herbs, body.medicines)

    warnings = [
        SafetyWarning(
            severity=c["severity"],
            rule_type=c["rule_type"],
            drug_a=c["drug_a"],
            drug_b=c["drug_b"] or "",
            mechanism=c["mechanism"],
            action=c["action"],
            source=c["source"],
        )
        for c in conflicts
    ]

    return SafetyCheckResponse(
        safe=len(warnings) == 0,
        warnings=warnings,
    )


@router.post("/check-v2", response_model=SafetyCheckResponseV2)
async def safety_check_v2(body: SafetyCheckRequestV2, db: DbAdapter = Depends(get_db)):
    """Five-layer safety check (spec §15.3).

    Layer 1a: 中药×中药配伍禁忌 (十八反十九畏)
    Layer 1b: 中西药交互检查
    Layer 2:  剂量范围检查
    Layer 3:  特殊人群检查
    Layer 4:  AI 辅助分析 (placeholder)
    Layer 5:  免责声明
    """
    result = await run_safety_check(
        db=db,
        herb_names=body.herbs,
        medicine_names=body.medicines,
        user_profile=body.user_profile,
        dosages=body.dosages,
    )

    warnings_v2 = [
        SafetyWarningV2(
            layer=w.layer,
            severity=w.severity,
            title=w.title,
            detail=w.detail,
            herbs=w.herbs,
            action=w.action,
            source=w.source,
        )
        for w in result.warnings
    ]

    # Extract interaction messages (layer 1b) for top-level interactions field
    interactions = [w.title for w in warnings_v2 if w.layer == 1 and '交互' in w.source]

    return SafetyCheckResponseV2(
        safe=result.safe,
        warnings=warnings_v2,
        interactions=interactions,
        disclaimer=result.disclaimer,
        checked_herbs=result.checked_herbs,
        checked_medicines=result.checked_medicines,
        unknown_herbs=result.unknown_herbs,
        unknown_medicines=result.unknown_medicines,
    )
