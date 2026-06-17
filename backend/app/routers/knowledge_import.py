"""Knowledge import router — multi-source document ingestion (spec §18).

Users upload health-knowledge documents (PDF / Word / TXT / images) and the
system extracts text → creates ``knowledge_entries`` rows tagged with
auto-detected herb / formula names.

Endpoints
---------
- ``POST /api/knowledge-import/upload``         — single-file upload
- ``POST /api/knowledge-import/upload-batch``   — multiple files at once
- ``GET  /api/knowledge-import/recent``         — recently imported entries
- ``DELETE /api/knowledge-import/{entry_id}``   — delete an imported entry

All persisted rows use ``source_type='import'`` so they can be distinguished
from extractor-generated entries (``source_type='extractor'``) and bookmarks.
Chinese domain language throughout (spec §1.7).
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)

from app.auth import get_current_user
from app.database import DbAdapter, get_db
from app.knowledge_parser import (
    ALLOWED_EXTENSIONS,
    ParseResult,
    detect_file_type,
    parse_file,
)

router = APIRouter(prefix="/api/knowledge-import", tags=["knowledge-import"])

CST = timezone(timedelta(hours=8))

#: Maximum upload size — 20 MiB (spec §18 acceptance criteria).
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

#: ``source_type`` value used for all rows created by this router.
SOURCE_TYPE = "import"

#: Entry type stored on knowledge_entries.
ENTRY_TYPE = "document"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")


def _ext(filename: str) -> str:
    return os.path.splitext(filename.lower())[1]


def _validate_upload(file: UploadFile) -> None:
    """Validate extension + size before reading the file body."""
    ext = _ext(file.filename or "")
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"不支持的文件格式：{ext or '(无扩展名)'}。"
                f"支持：{', '.join(sorted(ALLOWED_EXTENSIONS))}"
            ),
        )


def _derive_title(filename: str) -> str:
    """Derive a human-readable title from a filename (strip extension)."""
    base = os.path.splitext(filename)[0]
    # Replace common separators with spaces for readability
    return re.sub(r"[_\-]+", " ", base).strip() or filename


async def _detect_tags(db: DbAdapter, text: str) -> list[str]:
    """Detect herb / formula names mentioned in ``text``.

    Loads all herb names + aliases and formula names from the DB and returns
    the distinct set found in the text. Capped to avoid huge tag lists.
    """
    if not text:
        return []

    tags: set[str] = set()

    # Herbs — name + comma-separated aliases
    herb_rows = await db.query("SELECT name, aliases FROM herbs")
    for row in herb_rows:
        name = (row.get("name") or "").strip()
        if name and name in text:
            tags.add(name)
            continue
        aliases = (row.get("aliases") or "").split(",")
        for alias in aliases:
            alias = alias.strip()
            if alias and alias in text:
                tags.add(name)
                break

    # Formulas — name only
    formula_rows = await db.query("SELECT name FROM formulas")
    for row in formula_rows:
        name = (row.get("name") or "").strip()
        if name and name in text:
            tags.add(name)

    # Keep order deterministic and cap length
    return sorted(tags)[:30]


async def _persist_entry(
    db: DbAdapter,
    user_id: str,
    *,
    title: str,
    result: ParseResult,
    source_url: str,
) -> dict[str, Any]:
    """Create a single knowledge_entries row from a parse result.

    Sections are concatenated into ``content``; the structured sections list
    is preserved in ``summary`` for the UI to render.
    """
    entry_id = f"ki-{uuid.uuid4()}"
    full_text = result.full_text
    tags = await _detect_tags(db, full_text)

    summary = json.dumps(
        {
            "sections": result.sections,
            "metadata": result.metadata,
            "type": result.type,
        },
        ensure_ascii=False,
    )

    now = _now()
    await db.execute(
        """INSERT INTO knowledge_entries
           (id, user_id, entry_type, title, content, summary, tags,
            source_type, source_url, is_starred, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)""",
        (
            entry_id, user_id, ENTRY_TYPE, title,
            full_text, summary,
            json.dumps(tags, ensure_ascii=False),
            SOURCE_TYPE, source_url, now, now,
        ),
    )

    row = await db.query_one(
        "SELECT * FROM knowledge_entries WHERE id = ?", (entry_id,)
    )
    return _parse_entry(row)


def _parse_entry(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize a knowledge_entries row for JSON output."""
    result = dict(row)
    for key in ("tags",):
        if isinstance(result.get(key), str):
            try:
                result[key] = json.loads(result[key])
            except (json.JSONDecodeError, TypeError):
                result[key] = []
    if "is_starred" in result:
        result["is_starred"] = bool(result["is_starred"])
    return result


async def _process_one(
    db: DbAdapter,
    user_id: str,
    file: UploadFile,
) -> dict[str, Any]:
    """Validate, save-to-temp, parse, and persist a single uploaded file.

    Returns the created entry dict (or raises HTTPException on failure).
    """
    _validate_upload(file)

    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"文件过大：{len(raw)} 字节，"
                f"上限 {MAX_UPLOAD_BYTES} 字节（20MB）"
            ),
        )
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="文件内容为空",
        )

    filename = file.filename or "unknown"
    ext = _ext(filename)
    # Write to a temp file with the correct extension (tesseract / fitz care)
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=ext, prefix="ki_")
    try:
        with os.fdopen(tmp_fd, "wb") as fh:
            fh.write(raw)

        result = await parse_file(tmp_path, filename)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    if result.error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=result.error,
        )

    if result.metadata.get("empty"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="未能从文件中提取到任何文本（可能是扫描件或空白文件）",
        )

    title = _derive_title(filename)
    entry = await _persist_entry(
        db, user_id,
        title=title, result=result, source_url=filename,
    )
    return entry


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload(
    file: UploadFile = File(..., description="待导入的文档（PDF/Word/TXT/图片）"),
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """上传单个文档并导入知识库.

    支持格式：``.pdf .docx .doc .txt .md .jpg .jpeg .png .webp``
    大小上限：20MB

    返回创建的知识条目，含 ``entry_id``、``title``、``sections_parsed``、
    ``word_count``。
    """
    entry = await _process_one(db, current_user["id"], file)

    # Enrich response with parse-level metadata
    summary_meta = {}
    try:
        parsed = json.loads(entry.get("summary") or "{}")
        summary_meta = parsed.get("metadata", {})
    except (json.JSONDecodeError, TypeError):
        pass

    return {
        "entry_id": entry["id"],
        "title": entry["title"],
        "entry_type": entry.get("entry_type"),
        "source_url": entry.get("source_url"),
        "tags": entry.get("tags", []),
        "sections_parsed": summary_meta.get("sections", 0),
        "word_count": summary_meta.get("words", 0),
        "created_at": entry.get("created_at"),
        "entry": entry,
    }


@router.post("/upload-batch", status_code=status.HTTP_201_CREATED)
async def upload_batch(
    files: list[UploadFile] = File(..., description="多个待导入文档"),
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """批量上传多个文档并导入知识库.

    对每个文件独立处理：成功的创建条目，失败的记录错误信息。
    返回 ``{success: [...], failures: [...]}``。
    """
    if not files:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="至少需要上传一个文件",
        )

    success: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for file in files:
        try:
            entry = await _process_one(db, current_user["id"], file)
            success.append({
                "entry_id": entry["id"],
                "title": entry["title"],
                "source_url": entry.get("source_url"),
                "tags": entry.get("tags", []),
            })
        except HTTPException as exc:
            failures.append({
                "filename": file.filename,
                "detail": exc.detail,
                "status_code": exc.status_code,
            })
        except Exception as exc:  # pragma: no cover - defensive
            failures.append({
                "filename": file.filename,
                "detail": f"处理失败：{exc}",
                "status_code": 500,
            })

    return {
        "success": success,
        "failures": failures,
        "total_success": len(success),
        "total_failures": len(failures),
    }


@router.get("/recent")
async def recent_imports(
    limit: int = Query(20, ge=1, le=100, description="返回条目上限"),
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """列出当前用户最近导入的知识条目.

    只返回 ``source_type='import'`` 的条目，按创建时间倒序。
    """
    user_id = current_user["id"]
    rows = await db.query(
        """SELECT * FROM knowledge_entries
           WHERE user_id = ? AND source_type = ?
           ORDER BY created_at DESC
           LIMIT ?""",
        (user_id, SOURCE_TYPE, limit),
    )
    items = [_parse_entry(r) for r in rows]
    return {"items": items, "total": len(items)}


@router.delete("/{entry_id}")
async def delete_import(
    entry_id: str,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """删除一条已导入的知识条目.

    只允许删除当前用户自己创建的导入条目（``source_type='import'``），
    不会触碰 extractor 生成的条目或他人的数据。
    """
    user_id = current_user["id"]
    existing = await db.query_one(
        """SELECT * FROM knowledge_entries
           WHERE id = ? AND user_id = ? AND source_type = ?""",
        (entry_id, user_id, SOURCE_TYPE),
    )
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到该导入的知识条目",
        )

    await db.execute(
        "DELETE FROM knowledge_entries WHERE id = ? AND user_id = ?",
        (entry_id, user_id),
    )
    return {"detail": "已删除", "entry_id": entry_id}
