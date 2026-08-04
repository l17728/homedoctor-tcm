"""Medical visits router — 诊疗时间线 (spec §13.2 V2).

Endpoints:
  GET    /api/visits             — list visits (timeline)
  POST   /api/visits             — create visit record
  GET    /api/visits/{id}        — visit detail
  PUT    /api/visits/{id}        — update visit
  DELETE /api/visits/{id}        — delete visit
  POST   /api/visits/ocr         — upload lab report image → tesseract OCR
"""

from __future__ import annotations


import logging

logger = logging.getLogger(__name__)
import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from pydantic import BaseModel, Field

from app.auth import get_current_user
from app.database import DbAdapter, get_db
from app.repository import current_tenant_id, current_member_id

router = APIRouter(prefix="/api/visits", tags=["medical-visits"])


class VisitCreate(BaseModel):
    visit_date: str = Field(..., description="就诊日期 YYYY-MM-DD")
    hospital: str = Field("", description="医院名称")
    department: str = Field("", description="科室")
    doctor_name: str = Field("", description="医生姓名")
    diagnosis: str = Field("", description="西医诊断")
    tcm_diagnosis: str = Field("", description="中医诊断（证候）")
    prescription: str = Field("", description="处方/用药")
    lab_results: str = Field("", description="化验结果摘要")
    notes: str = Field("", description="备注")


class VisitUpdate(BaseModel):
    visit_date: str | None = None
    hospital: str | None = None
    department: str | None = None
    doctor_name: str | None = None
    diagnosis: str | None = None
    tcm_diagnosis: str | None = None
    prescription: str | None = None
    lab_results: str | None = None
    notes: str | None = None


@router.get("")
async def list_visits(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    tenant = current_tenant_id.get()
    member = current_member_id.get()
    conditions = ["user_id = ?"]
    params: list[Any] = [current_user["id"]]
    if member:
        conditions.append("family_member_id = ?")
        params.append(member)

    where = " AND ".join(conditions)
    count_row = await db.query_one(
        f"SELECT COUNT(*) AS c FROM medical_visits WHERE {where}", tuple(params)
    )
    total = count_row["c"] if count_row else 0

    offset = (page - 1) * page_size
    rows = await db.query(
        f"""SELECT * FROM medical_visits WHERE {where}
            ORDER BY visit_date DESC LIMIT ? OFFSET ?""",
        tuple(params + [page_size, offset]),
    )
    return {
        "items": [_format(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("")
async def create_visit(
    body: VisitCreate,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    visit_id = f"visit-{uuid.uuid4()}"
    member = current_member_id.get()
    await db.execute(
        """INSERT INTO medical_visits
           (id, user_id, family_member_id, visit_date, hospital, department,
            doctor_name, diagnosis, tcm_diagnosis, prescription, lab_results, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            visit_id, current_user["id"], member,
            body.visit_date, body.hospital, body.department,
            body.doctor_name, body.diagnosis, body.tcm_diagnosis,
            body.prescription, body.lab_results, body.notes,
        ),
    )
    return {"id": visit_id, "message": "就诊记录已创建"}


@router.get("/{visit_id}")
async def get_visit(
    visit_id: str,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    rows = await db.query(
        "SELECT * FROM medical_visits WHERE id = ? AND user_id = ?",
        (visit_id, current_user["id"]),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="就诊记录不存在")
    return _format(rows[0])


@router.put("/{visit_id}")
async def update_visit(
    visit_id: str,
    body: VisitUpdate,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    existing = await db.query(
        "SELECT * FROM medical_visits WHERE id = ? AND user_id = ?",
        (visit_id, current_user["id"]),
    )
    if not existing:
        raise HTTPException(status_code=404, detail="就诊记录不存在")

    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        return {"message": "无更新"}

    set_clauses = ", ".join(f"{k} = ?" for k in updates)
    params = list(updates.values()) + [visit_id]
    await db.execute(
        f"UPDATE medical_visits SET {set_clauses}, updated_at = datetime('now') WHERE id = ?",
        tuple(params),
    )
    return {"message": "已更新"}


@router.delete("/{visit_id}")
async def delete_visit(
    visit_id: str,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    cursor = await db.execute(
        "DELETE FROM medical_visits WHERE id = ? AND user_id = ?",
        (visit_id, current_user["id"]),
    )
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="就诊记录不存在")
    return {"message": "已删除"}


@router.post("/ocr")
async def ocr_lab_report(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Upload a lab report image → tesseract OCR extracts text."""
    import subprocess
    import tempfile
    import os

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="文件过大（>10MB）")

    suffix = ".png"
    if file.content_type and "jpeg" in file.content_type:
        suffix = ".jpg"
    elif file.content_type and "pdf" in file.content_type:
        suffix = ".pdf"

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        lang = "chi_sim+eng"
        result = subprocess.run(
            ["tesseract", tmp_path, "stdout", "-l", lang],
            capture_output=True, text=True, timeout=30,
        )
        text = result.stdout.strip() if result.returncode == 0 else ""
        if not text:
            return {
                "text": "",
                "warning": "OCR 未识别到文字，请手动输入",
            }
        return {"text": text[:5000], "chars": len(text)}
    except FileNotFoundError:
        return {"text": "", "warning": "tesseract 未安装"}
    except subprocess.TimeoutExpired:
        return {"text": "", "warning": "OCR 处理超时"}
    finally:
        os.unlink(tmp_path)


def _format(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id", ""),
        "visit_date": row.get("visit_date", ""),
        "hospital": row.get("hospital") or "",
        "department": row.get("department") or "",
        "doctor_name": row.get("doctor_name") or "",
        "diagnosis": row.get("diagnosis") or "",
        "tcm_diagnosis": row.get("tcm_diagnosis") or "",
        "prescription": row.get("prescription") or "",
        "lab_results": row.get("lab_results") or "",
        "notes": row.get("notes") or "",
        "created_at": row.get("created_at") or "",
    }
