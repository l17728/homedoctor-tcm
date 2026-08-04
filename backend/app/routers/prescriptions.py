"""Prescriptions router — PDF generation for prescription sheets and health reports (spec §21).

Endpoints:
    POST /api/prescriptions/generate      — prescription sheet PDF for a formula
    POST /api/prescriptions/health-report — health summary PDF (体质 + 用药 + 提醒)
"""

from __future__ import annotations


import logging

logger = logging.getLogger(__name__)
import json
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.auth import get_current_user
from app.database import DbAdapter, get_db
from app.models import HealthReportRequest, PrescriptionRequest
from app.pdf_generator import generate_health_report_pdf, generate_prescription_pdf
from app.repository import FormulaRepository

router = APIRouter(prefix="/api/prescriptions", tags=["prescriptions"])


def _parse_formula_row(row: dict[str, Any]) -> dict[str, Any]:
    """Parse a formula DB row, decoding JSON-string fields into objects."""
    result = dict(row)
    for field in ("composition", "modifications", "modifications_structured", "properties"):
        val = result.get(field)
        if isinstance(val, str):
            try:
                result[field] = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                result[field] = [] if field != "properties" else {}
    return result


def _content_disposition(filename: str) -> str:
    """Build a Content-Disposition header with RFC 5987 UTF-8 filename encoding.

    HTTP headers are latin-1; CJK filenames must be percent-encoded via
    the ``filename*=UTF-8''...`` parameter (RFC 5987 §4.2).
    """
    ascii_fallback = filename.encode("ascii", "replace").decode("ascii")
    encoded = quote(filename)
    return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{encoded}"


@router.post("/generate")
async def generate_prescription(
    body: PrescriptionRequest,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Generate a prescription sheet PDF for a TCM formula (spec §21.3).

    Loads the formula by ID, then renders an A4 PDF with:
    patient info, formula details, herb table (君臣佐使), usage, notes, disclaimer.
    """
    repo = FormulaRepository(db)
    row = await repo.get_formula(body.formula_id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到该方剂",
        )

    formula = _parse_formula_row(row)
    pdf_bytes = generate_prescription_pdf(
        formula=formula,
        patient_name=body.patient_name,
        patient_age=body.patient_age,
        patient_gender=body.patient_gender,
        prescriber=body.prescriber,
        notes=body.notes,
        usage_instructions=body.usage_instructions,
    )

    filename = f"处方单_{formula.get('name', 'formula')}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": _content_disposition(filename)},
    )


@router.post("/health-report")
async def generate_health_report(
    body: HealthReportRequest,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Generate a health summary PDF (体质 + 用药 + 提醒) (spec §21.2).

    Aggregates the current user's (or a family member's) profile, constitution,
    medicines, and reminders into a single-page printable health summary.
    """
    user_id = current_user["id"]

    member: dict[str, Any] | None = None
    if body.member_id:
        member = await db.query_one(
            "SELECT * FROM family_members WHERE id = ? AND user_id = ?",
            (body.member_id, user_id),
        )
        if not member:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="未找到该成员",
            )

    profile = await db.query_one(
        "SELECT * FROM user_profiles WHERE user_id = ?",
        (user_id,),
    )

    constitution = await db.query_one(
        "SELECT * FROM constitution_assessments WHERE user_id = ? "
        "ORDER BY assessed_at DESC LIMIT 1",
        (user_id,),
    )

    medicines = await db.query(
        "SELECT * FROM medicines WHERE tenant_id = ? ORDER BY name",
        (current_user.get("family_id", "default"),),
    )

    reminders = await db.query(
        "SELECT * FROM reminders WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,),
    )

    pdf_bytes = generate_health_report_pdf(
        member=member,
        profile=profile or {},
        constitution=constitution or {},
        medicines=medicines,
        reminders=reminders,
        report_type=body.report_type,
    )

    member_name = ""
    if member:
        member_name = f"_{member.get('name', '')}"
    filename = f"健康摘要单{member_name}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": _content_disposition(filename)},
    )
