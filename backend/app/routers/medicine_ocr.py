"""Medicine OCR router — 拍照识别药品 + 条形码校验 (spec §16.2 P1).

Endpoints
---------
- ``POST /api/medicines/ocr-recognize`` — multipart image upload, OCR + field parsing
- ``POST /api/medicines/barcode-lookup``  — barcode format validation (offline)

Uses the existing tesseract OCR infrastructure (``chi_sim+eng``) from
``app.knowledge_parser`` for text extraction.  No external drug-database APIs
are called — all parsing is done locally with regex patterns (spec §0:
本地优先，无云端依赖).

Chinese domain language throughout (spec §1.7).
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.auth import get_current_user
from app.database import DbAdapter, get_db
from app.knowledge_parser import parse_image

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/medicines", tags=["medicine-ocr"])

#: Accepted image extensions.
_IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"})

#: Maximum upload size — 10 MiB.
_MAX_BYTES = 10 * 1024 * 1024


# ---------------------------------------------------------------------------
# Regex patterns for parsing medicine-box text
# ---------------------------------------------------------------------------

#: Drug-name patterns — e.g. 感冒清热片, 六味地黄丸, 藿香正气胶囊.
_NAME_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"([\u4e00-\u9fff]{2,8}(?:片|胶囊|丸|颗粒|口服液|糖浆|喷剂|膏药|散|丹|合剂|冲剂))"),
    re.compile(r"([\u4e00-\u9fff]{2,8}(?:滴丸|缓释片|肠溶片|分散片|含片|栓|搽剂))"),
]

#: Drug-type mapping from dosage-form suffix.
_TYPE_MAP: dict[str, str] = {
    "片": "片剂",
    "缓释片": "片剂",
    "肠溶片": "片剂",
    "分散片": "片剂",
    "含片": "片剂",
    "胶囊": "胶囊剂",
    "丸": "丸剂",
    "滴丸": "丸剂",
    "颗粒": "颗粒剂",
    "冲剂": "颗粒剂",
    "口服液": "口服液",
    "合剂": "口服液",
    "糖浆": "糖浆剂",
    "喷剂": "喷雾剂",
    "膏药": "贴膏",
    "散": "散剂",
    "丹": "丸剂",
    "栓": "栓剂",
    "搽剂": "搽剂",
}

#: Specification patterns — e.g. 0.25g, 10mg, 100ml, 0.5g×24片.
_SPEC_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?\s*(?:mg|g|kg|ml|l|ug|μg|IU|单位)\s*(?:[×x*]\s*\d+\s*(?:片|粒|丸|袋|支|瓶|枚))?)",
    re.IGNORECASE,
)

#: Dosage-instruction patterns — e.g. 每日3次, 每次2片, 一日2次.
_DOSAGE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(每日|一日|每天|1日)\s*[0-9一二三四五六七八九十]+\s*次"),
    re.compile(r"(每次|1次|一次)\s*[0-9一二三四五六七八九十]+\s*(?:片|粒|丸|袋|支|瓶|ml|g|mg|滴)"),
    re.compile(r"(每日|一日|每天)\s*[0-9一二三四五六七八九十]+\s*(?:片|粒|丸|袋|支)"),
]


def _ext(filename: str) -> str:
    return os.path.splitext(filename.lower())[1]


def _parse_medicine_name(text: str) -> tuple[str | None, str | None]:
    """Extract medicine name and drug type from OCR text.

    Returns ``(name, type)`` where either may be ``None`` if not found.
    """
    for pattern in _NAME_PATTERNS:
        for match in pattern.finditer(text):
            name = match.group(1).strip()
            if len(name) < 2:
                continue
            # Determine drug type from the suffix
            drug_type: str | None = None
            for suffix, dtype in _TYPE_MAP.items():
                if name.endswith(suffix):
                    drug_type = dtype
                    break
            return name, drug_type
    return None, None


def _parse_specification(text: str) -> str | None:
    """Extract specification (e.g. 0.25g, 10mg) from OCR text."""
    match = _SPEC_PATTERN.search(text)
    if match:
        return match.group(1).strip()
    return None


def _parse_dosage_instructions(text: str) -> str | None:
    """Extract dosage instructions (e.g. 每日3次，每次2片) from OCR text."""
    found: list[str] = []
    seen: set[str] = set()
    for pattern in _DOSAGE_PATTERNS:
        for match in pattern.finditer(text):
            val = match.group(0).strip()
            if val not in seen:
                seen.add(val)
                found.append(val)
    if not found:
        return None
    return "，".join(found[:3])


def _compute_confidence(
    name: str | None,
    drug_type: str | None,
    spec: str | None,
    dosage: str | None,
    raw_text_len: int,
) -> str:
    """Compute overall recognition confidence level.

    Returns ``"high"``, ``"medium"``, or ``"low"``.
    """
    if raw_text_len < 10:
        return "low"

    found_count = sum(1 for v in (name, drug_type, spec, dosage) if v)
    if found_count >= 3:
        return "high"
    if found_count >= 2:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/ocr-recognize")
async def ocr_recognize(
    file: UploadFile = File(..., description="药品包装/说明书照片"),
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """拍照识别药品 — OCR 提取文字后解析药品信息.

    Uses tesseract OCR (``chi_sim+eng``) to extract text from the uploaded
    image, then parses for:
    - Medicine name (XX片/XX胶囊/XX丸/XX颗粒/XX口服液)
    - Drug type (片剂/胶囊剂/丸剂/...)
    - Specification (0.25g, 10mg, ...)
    - Dosage instructions (每日X次, 每次X片)

    Returns parsed fields + ``raw_text`` + ``confidence`` (high/medium/low).
    Fields not confidently recognised are omitted (``None``) so the frontend
    can highlight them for manual verification.
    """
    ext = _ext(file.filename or "")
    if ext not in _IMAGE_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"不支持的文件格式：{ext or '(无扩展名)'}。"
                f"支持：{', '.join(sorted(_IMAGE_EXTENSIONS))}"
            ),
        )

    raw = await file.read()
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="文件内容为空",
        )
    if len(raw) > _MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"文件过大：{len(raw)} 字节，上限 {_MAX_BYTES} 字节（10MB）",
        )

    # Write to temp file for tesseract subprocess
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=ext, prefix="ocr_")
    try:
        with os.fdopen(tmp_fd, "wb") as fh:
            fh.write(raw)

        raw_text = await parse_image(tmp_path)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    raw_text = (raw_text or "").strip()

    if not raw_text:
        return {
            "raw_text": "",
            "confidence": "low",
            "message": "未能识别到文字，请尝试拍摄更清晰的照片或手动录入",
        }

    # Parse fields
    name, drug_type = _parse_medicine_name(raw_text)
    specification = _parse_specification(raw_text)
    dosage_instructions = _parse_dosage_instructions(raw_text)
    confidence = _compute_confidence(
        name, drug_type, specification, dosage_instructions, len(raw_text)
    )

    result: dict[str, Any] = {
        "raw_text": raw_text,
        "confidence": confidence,
    }
    if name:
        result["name"] = name
    if drug_type:
        result["type"] = drug_type
    if specification:
        result["specification"] = specification
    if dosage_instructions:
        result["dosage_instructions"] = dosage_instructions

    return result


@router.post("/barcode-lookup")
async def barcode_lookup(
    body: dict,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """条形码格式校验（离线）.

    Validates the barcode format:
    - EAN-13: 13 digits, with checksum verification
    - EAN-8: 8 digits, with checksum verification

    No external drug-database API is called (offline-first per spec §0).
    Returns ``{"valid": bool, "barcode": str}``.

    Future: integrate with a drug database API for product lookup.
    """
    barcode = str(body.get("barcode", "")).strip()

    if not barcode:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="barcode 为必填项",
        )

    if not barcode.isdigit():
        return {"valid": False, "barcode": barcode, "reason": "条形码必须为纯数字"}

    valid = False
    fmt = "未知"

    if len(barcode) == 13:
        fmt = "EAN-13"
        valid = _validate_ean13(barcode)
    elif len(barcode) == 8:
        fmt = "EAN-8"
        valid = _validate_ean8(barcode)
    else:
        return {
            "valid": False,
            "barcode": barcode,
            "reason": "条形码长度应为 13 位（EAN-13）或 8 位（EAN-8）",
        }

    return {
        "valid": valid,
        "barcode": barcode,
        "format": fmt,
        "reason": "校验通过" if valid else "校验位不匹配",
    }


def _validate_ean13(barcode: str) -> bool:
    """Validate an EAN-13 barcode using the standard checksum algorithm."""
    if len(barcode) != 13 or not barcode.isdigit():
        return False
    digits = [int(d) for d in barcode]
    # Weighting: positions 1,3,5,... = 1; positions 2,4,6,... = 3 (0-indexed: even=1, odd=3)
    total = sum(d * (1 if i % 2 == 0 else 3) for i, d in enumerate(digits[:12]))
    checksum = (10 - (total % 10)) % 10
    return checksum == digits[12]


def _validate_ean8(barcode: str) -> bool:
    """Validate an EAN-8 barcode using the standard checksum algorithm."""
    if len(barcode) != 8 or not barcode.isdigit():
        return False
    digits = [int(d) for d in barcode]
    # Weighting: positions 0,2,4,6 = 3; positions 1,3,5 = 1
    total = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(digits[:7]))
    checksum = (10 - (total % 10)) % 10
    return checksum == digits[7]
