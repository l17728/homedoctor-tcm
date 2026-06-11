"""Safety router — drug interaction check."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.database import DbAdapter, get_db
from app.models import SafetyCheckRequest, SafetyCheckResponse, SafetyWarning
from app.repository import SafetyRepository

router = APIRouter(prefix="/api/safety", tags=["safety"])


@router.post("/check", response_model=SafetyCheckResponse)
async def safety_check(body: SafetyCheckRequest, db: DbAdapter = Depends(get_db)):
    """Check for drug interactions between herbs and medicines."""
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
