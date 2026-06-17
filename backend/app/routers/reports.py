"""报告中心 router — 体质报告 / 健康趋势报告 / 就诊准备报告 (spec §7 / §13.3 V3 P0).

Endpoints (all require auth):
    GET  /api/reports/constitution            — 体质报告
    GET  /api/reports/health-trend?period=7d  — 健康趋势报告 (period: 7d|30d|90d)
    GET  /api/reports/pre-visit               — 就诊准备报告
    POST /api/reports/generate-pdf            — 生成为 PDF (复用 pdf_generator)

All reports are read-only aggregations over structured SQLite data (spec §1.4).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response

from app.auth import get_current_user
from app.database import DbAdapter, get_db
from app.pdf_generator import generate_health_report_pdf
from app.report_engine import (
    generate_constitution_report,
    generate_health_trend_report,
    generate_pre_visit_report,
    generate_report,
)

router = APIRouter(prefix="/api/reports", tags=["reports"])

VALID_PERIODS = {"7d", "30d", "90d"}
VALID_PDF_TYPES = {"constitution", "health-trend", "pre-visit"}


@router.get("/constitution")
async def get_constitution_report(
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """体质报告 — 最新评估结果 + 得分趋势 + 个性化建议 + 节气养生.

    Aggregates constitution assessment history, scores trends, and
    personalized dietary/exercise/lifestyle recommendations based on the
    user's primary constitution type plus current solar term advice.
    """
    return await generate_constitution_report(db, current_user["id"])


@router.get("/health-trend")
async def get_health_trend_report(
    period: str = Query("30d", description="统计周期：7d / 30d / 90d"),
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """健康趋势报告 — 用药依从性 + 提醒完成率 + 药箱变化 + 对话频率 + 安全检查.

    The ``period`` query parameter controls the time window:
        - ``7d``: 近7天
        - ``30d``: 近30天 (default)
        - ``90d``: 近90天
    """
    if period not in VALID_PERIODS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效的统计周期：{period}，可选值：7d、30d、90d",
        )
    return await generate_health_trend_report(
        db, current_user["id"], current_user.get("family_id", "default"), period
    )


@router.get("/pre-visit")
async def get_pre_visit_report(
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """就诊准备报告 — 当前用药 + 过敏信息 + 体质摘要 + 近期问题 + 安全检查 + 待问问题.

    Designed to be printed or shared with a doctor before a visit. Includes
    auto-generated questions derived from recent chat topics.
    """
    return await generate_pre_visit_report(
        db, current_user["id"], current_user.get("family_id", "default")
    )


@router.post("/generate-pdf")
async def generate_pdf(
    body: dict[str, Any],
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """将任意报告类型生成为 PDF 文档 (复用 pdf_generator).

    Request body:
        ``{"report_type": "constitution" | "health-trend" | "pre-visit",
           "period": "7d" | "30d" | "90d"}``  (period only for health-trend)

    Returns a ``application/pdf`` response with the generated PDF.
    """
    report_type = body.get("report_type", "constitution")
    if report_type not in VALID_PDF_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效的报告类型：{report_type}，可选值：constitution、health-trend、pre-visit",
        )

    period = body.get("period", "30d")
    if period not in VALID_PERIODS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效的统计周期：{period}，可选值：7d、30d、90d",
        )

    # Generate the report data
    report = await generate_report(
        db,
        current_user["id"],
        current_user.get("family_id", "default"),
        report_type,
        period,
    )

    # Build PDF using the existing health report generator
    pdf_bytes = generate_health_report_pdf(
        member=report.get("patient_info"),
        profile=_report_to_profile(report),
        constitution=_report_to_constitution(report),
        medicines=report.get("medications") if report_type == "pre-visit" else [],
        reminders=[],
        report_type=_REPORT_TYPE_LABELS.get(report_type, "健康报告"),
    )

    filename = f"{report_type}-report.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# PDF helper mappers — translate report dicts into pdf_generator inputs
# ---------------------------------------------------------------------------

_REPORT_TYPE_LABELS = {
    "constitution": "体质报告",
    "health-trend": "健康趋势报告",
    "pre-visit": "就诊准备报告",
}


def _report_to_profile(report: dict[str, Any]) -> dict[str, Any]:
    """Extract a profile-like dict for pdf_generator from a report."""
    patient = report.get("patient_info") or {}
    return {
        "display_name": patient.get("display_name"),
        "gender": patient.get("gender"),
        "birth_year": patient.get("birth_year"),
        "allergies": report.get("allergies", []),
        "health_conditions": report.get("health_conditions", []),
    }


def _report_to_constitution(report: dict[str, Any]) -> dict[str, Any]:
    """Extract a constitution-like dict for pdf_generator from a report."""
    # Constitution report
    assessment = report.get("assessment")
    if assessment:
        return {
            "primary_type": assessment.get("primary_type"),
            "secondary_types": assessment.get("secondary_types", []),
        }
    # Pre-visit report
    constitution = report.get("constitution")
    if constitution:
        return {
            "primary_type": constitution.get("primary_type"),
            "secondary_types": constitution.get("secondary_types", []),
        }
    # Health trend has no constitution section
    return {}
