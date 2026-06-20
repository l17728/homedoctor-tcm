"""Classics (经典读诵) router — TCM medical classics bookshelf (spec §7.x).

Features:
- Bookshelf: list classics, get classic detail with chapter list
- Chapter reading: full chapter text + translation + user annotations
- Annotations CRUD: highlight selected text + Markdown notes / QA cards
- AI Q&A: ask questions about a selected passage (LLM)
- AI Translation: 文言文 → 白话文 (LLM, not auto-saved)
- Study notes: per-chapter Markdown notes
- Summarize: LLM aggregates annotations + QA cards into a FAQ
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth import get_current_user
from app.config import settings
from app.database import DbAdapter, get_db
from app.entity_filter import scan_and_link
from app.llm import chat_completion, has_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/classics", tags=["classics"])

CST = timezone(timedelta(hours=8))

_VALID_NOTE_TYPES = {"annotation", "qa_card", "translation_note"}


def _now() -> str:
    return datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")


def _classic_row(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    if "total_chapters" in out:
        out["total_chapters"] = int(out["total_chapters"] or 0)
    return out


def _chapter_row(row: dict[str, Any]) -> dict[str, Any]:
    return dict(row)


def _annotation_row(row: dict[str, Any]) -> dict[str, Any]:
    return dict(row)


async def _get_classic_or_404(db: DbAdapter, classic_id: str) -> dict[str, Any]:
    row = await db.query_one("SELECT * FROM classics WHERE id = ?", (classic_id,))
    if not row:
        raise HTTPException(status_code=404, detail="未找到该典籍")
    return _classic_row(row)


async def _get_chapter_or_404(
    db: DbAdapter, classic_id: str, chapter_id: str
) -> dict[str, Any]:
    row = await db.query_one(
        "SELECT * FROM classic_chapters WHERE id = ? AND classic_id = ?",
        (chapter_id, classic_id),
    )
    if not row:
        raise HTTPException(status_code=404, detail="未找到该章节")
    return _chapter_row(row)


# ---------------------------------------------------------------------------
# Bookshelf
# ---------------------------------------------------------------------------

@router.get("")
async def list_classics(
    category: str | None = Query(None, description="按分类筛选，如「医经」「方书」"),
    db: DbAdapter = Depends(get_db),
):
    """列出全部典籍（无需认证，可浏览书架）。"""
    sql = "SELECT * FROM classics"
    params: list[Any] = []
    if category:
        sql += " WHERE category = ?"
        params.append(category)
    sql += " ORDER BY created_at ASC, id ASC"
    rows = await db.query(sql, tuple(params))
    items = [_classic_row(r) for r in rows]
    return {"items": items, "total": len(items)}


@router.get("/{classic_id}")
async def get_classic(
    classic_id: str,
    db: DbAdapter = Depends(get_db),
):
    """典籍详情 + 章节目录（无需认证）。"""
    classic = await _get_classic_or_404(db, classic_id)
    chapters = await db.query(
        """SELECT id, chapter_number, title, length(original_text) AS text_length,
                  translation IS NOT NULL AS has_translation
           FROM classic_chapters WHERE classic_id = ?
           ORDER BY chapter_number ASC""",
        (classic_id,),
    )
    classic["chapters"] = [
        {
            "id": c["id"],
            "chapter_number": c["chapter_number"],
            "title": c["title"],
            "text_length": int(c["text_length"] or 0),
            "has_translation": bool(c["has_translation"]),
        }
        for c in chapters
    ]
    return classic


# ---------------------------------------------------------------------------
# Chapter reading
# ---------------------------------------------------------------------------

@router.get("/{classic_id}/chapters/{chapter_id}")
async def get_chapter(
    classic_id: str,
    chapter_id: str,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """读取章节全文：原文 + 翻译 + 当前用户的批注。"""
    classic = await _get_classic_or_404(db, classic_id)
    chapter = await _get_chapter_or_404(db, classic_id, chapter_id)

    annotations = await db.query(
        """SELECT * FROM classic_annotations
           WHERE chapter_id = ? AND user_id = ?
           ORDER BY start_offset ASC, created_at ASC""",
        (chapter_id, current_user["id"]),
    )
    chapter["annotations"] = [_annotation_row(a) for a in annotations]
    chapter["classic_title"] = classic["title"]
    return chapter


@router.put("/{classic_id}/chapters/{chapter_id}/translation")
async def save_translation(
    classic_id: str,
    chapter_id: str,
    body: dict,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """保存/更新章节的白话文翻译（用户审阅 AI 翻译后手动保存）。"""
    await _get_chapter_or_404(db, classic_id, chapter_id)

    translation = body.get("translation")
    if translation is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="translation 字段必填",
        )
    translator_notes = body.get("translator_notes")

    await db.execute(
        """UPDATE classic_chapters
           SET translation = ?, translator_notes = COALESCE(?, translator_notes)
           WHERE id = ?""",
        (translation, translator_notes, chapter_id),
    )
    row = await db.query_one("SELECT * FROM classic_chapters WHERE id = ?", (chapter_id,))
    return _chapter_row(row)


# ---------------------------------------------------------------------------
# Annotations CRUD
# ---------------------------------------------------------------------------

@router.get("/{classic_id}/chapters/{chapter_id}/annotations")
async def list_annotations(
    classic_id: str,
    chapter_id: str,
    note_type: str | None = Query(None),
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """列出当前用户在某章节的批注（可按 note_type 过滤）。"""
    await _get_chapter_or_404(db, classic_id, chapter_id)
    sql = (
        "SELECT * FROM classic_annotations "
        "WHERE chapter_id = ? AND user_id = ?"
    )
    params: list[Any] = [chapter_id, current_user["id"]]
    if note_type:
        sql += " AND note_type = ?"
        params.append(note_type)
    sql += " ORDER BY start_offset ASC, created_at ASC"
    rows = await db.query(sql, tuple(params))
    return {"items": [_annotation_row(r) for r in rows], "total": len(rows)}


@router.post(
    "/{classic_id}/chapters/{chapter_id}/annotations",
    status_code=status.HTTP_201_CREATED,
)
async def create_annotation(
    classic_id: str,
    chapter_id: str,
    body: dict,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """创建批注/QA卡/译者注。"""
    chapter = await _get_chapter_or_404(db, classic_id, chapter_id)

    required = ("start_offset", "end_offset", "selected_text", "content")
    missing = [k for k in required if body.get(k) is None]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"缺少必填字段: {', '.join(missing)}",
        )

    start = int(body["start_offset"])
    end = int(body["end_offset"])
    text_len = len(chapter["original_text"] or "")
    if start < 0 or end > text_len or start >= end:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"offset 范围非法 (0 ≤ start < end ≤ {text_len})",
        )

    note_type = body.get("note_type", "annotation")
    if note_type not in _VALID_NOTE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"note_type 必须是 {sorted(_VALID_NOTE_TYPES)} 之一",
        )

    ann_id = str(uuid.uuid4())
    now = _now()
    await db.execute(
        """INSERT INTO classic_annotations
           (id, user_id, classic_id, chapter_id, start_offset, end_offset,
            selected_text, note_type, content, ai_model, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            ann_id,
            current_user["id"],
            classic_id,
            chapter_id,
            start,
            end,
            body["selected_text"],
            note_type,
            body["content"],
            body.get("ai_model"),
            now,
            now,
        ),
    )
    row = await db.query_one(
        "SELECT * FROM classic_annotations WHERE id = ?", (ann_id,)
    )
    # Non-blocking: extract entity mentions from the annotation text.
    try:
        await scan_and_link(
            db, body.get("content"),
            source_type="annotation", source_id=ann_id,
            relationship_type="mentions",
        )
    except Exception:
        pass
    return _annotation_row(row)


@router.put("/annotations/{annotation_id}")
async def update_annotation(
    annotation_id: str,
    body: dict,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """更新批注内容。"""
    existing = await db.query_one(
        "SELECT * FROM classic_annotations WHERE id = ? AND user_id = ?",
        (annotation_id, current_user["id"]),
    )
    if not existing:
        raise HTTPException(status_code=404, detail="未找到该批注")

    set_parts: list[str] = []
    values: list[Any] = []

    if body.get("content") is not None:
        set_parts.append("content = ?")
        values.append(body["content"])

    if body.get("note_type") is not None:
        if body["note_type"] not in _VALID_NOTE_TYPES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"note_type 必须是 {sorted(_VALID_NOTE_TYPES)} 之一",
            )
        set_parts.append("note_type = ?")
        values.append(body["note_type"])

    for k in ("start_offset", "end_offset", "selected_text"):
        if body.get(k) is not None:
            set_parts.append(f"{k} = ?")
            values.append(body[k])

    if not set_parts:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="未提供任何可更新字段",
        )

    set_parts.append("updated_at = ?")
    values.append(_now())
    values.append(annotation_id)
    values.append(current_user["id"])

    await db.execute(
        f"""UPDATE classic_annotations
            SET {', '.join(set_parts)}
            WHERE id = ? AND user_id = ?""",
        tuple(values),
    )
    row = await db.query_one(
        "SELECT * FROM classic_annotations WHERE id = ?", (annotation_id,)
    )
    return _annotation_row(row)


@router.delete("/annotations/{annotation_id}")
async def delete_annotation(
    annotation_id: str,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """删除批注。"""
    existing = await db.query_one(
        "SELECT * FROM classic_annotations WHERE id = ? AND user_id = ?",
        (annotation_id, current_user["id"]),
    )
    if not existing:
        raise HTTPException(status_code=404, detail="未找到该批注")
    await db.execute(
        "DELETE FROM classic_annotations WHERE id = ? AND user_id = ?",
        (annotation_id, current_user["id"]),
    )
    return {"detail": "已删除"}


# ---------------------------------------------------------------------------
# AI Q&A on selected text
# ---------------------------------------------------------------------------

@router.post("/{classic_id}/chapters/{chapter_id}/ask")
async def ask_about_chapter(
    classic_id: str,
    chapter_id: str,
    body: dict,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """就选中文字向 AI 提问（auth required）。"""
    classic = await _get_classic_or_404(db, classic_id)
    chapter = await _get_chapter_or_404(db, classic_id, chapter_id)

    selected_text = body.get("selected_text")
    question = body.get("question")
    if not selected_text or not question:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="selected_text 和 question 均必填",
        )

    extra_context = body.get("context") or ""
    context_block = f"\n\n上下文：{extra_context}" if extra_context else ""

    prompt = (
        f"以下是《{classic['title']}》{chapter['title']}的内容：\n"
        f"'{selected_text}'\n\n"
        f"用户问题：{question}{context_block}\n\n"
        f"请结合中医理论回答。"
    )

    if not has_api_key():
        return {
            "answer": (
                "当前未配置 AI 大模型，无法进行典籍问答。"
                "请联系管理员配置 HOMEDOCTOR_LLM_API_KEY。"
            ),
            "model_used": None,
        }

    try:
        answer = await chat_completion([{"role": "user", "content": prompt}])
    except Exception as exc:
        logger.warning("Classics ask LLM failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI 服务暂时不可用，请稍后重试",
        )

    model_used = settings.LLM_MODEL
    auto_save = bool(body.get("auto_save", False))
    saved_id: str | None = None
    if auto_save:
        saved_id = str(uuid.uuid4())
        now = _now()
        await db.execute(
            """INSERT INTO classic_annotations
               (id, user_id, classic_id, chapter_id, start_offset, end_offset,
                selected_text, note_type, content, ai_model, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'qa_card', ?, ?, ?, ?)""",
            (
                saved_id,
                current_user["id"],
                classic_id,
                chapter_id,
                int(body.get("start_offset", 0)),
                int(body.get("end_offset", len(selected_text))),
                selected_text,
                answer,
                model_used,
                now,
                now,
            ),
        )

    return {"answer": answer, "model_used": model_used, "annotation_id": saved_id}


# ---------------------------------------------------------------------------
# AI Translation
# ---------------------------------------------------------------------------

@router.post("/{classic_id}/chapters/{chapter_id}/translate")
async def translate_chapter(
    classic_id: str,
    chapter_id: str,
    body: dict | None = None,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """AI 文言文 → 白话文翻译（不自动保存，用户审阅后再调 PUT translation）。"""
    classic = await _get_classic_or_404(db, classic_id)
    chapter = await _get_chapter_or_404(db, classic_id, chapter_id)

    text = (body or {}).get("text") or chapter["original_text"]
    if not text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="原文为空，无法翻译",
        )

    prompt = (
        "请将以下文言文医书内容翻译为现代白话文，保持中医术语准确：\n"
        f"{text}"
    )

    if not has_api_key():
        return {
            "translation": (
                "当前未配置 AI 大模型，无法进行翻译。"
                "请联系管理员配置 HOMEDOCTOR_LLM_API_KEY。"
            ),
            "model_used": None,
        }

    try:
        translation = await chat_completion([{"role": "user", "content": prompt}])
    except Exception as exc:
        logger.warning("Classics translate LLM failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI 服务暂时不可用，请稍后重试",
        )

    return {"translation": translation, "model_used": settings.LLM_MODEL}


# ---------------------------------------------------------------------------
# Study notes
# ---------------------------------------------------------------------------

@router.get("/{classic_id}/study-notes")
async def get_study_notes(
    classic_id: str,
    chapter_id: str | None = Query(None, description="按章节过滤，不传则返回全部章节"),
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """读取学习笔记（全部章节或指定章节）。"""
    await _get_classic_or_404(db, classic_id)
    sql = (
        "SELECT * FROM classic_study_notes "
        "WHERE user_id = ? AND classic_id = ?"
    )
    params: list[Any] = [current_user["id"], classic_id]
    if chapter_id:
        sql += " AND chapter_id = ?"
        params.append(chapter_id)
    sql += " ORDER BY updated_at DESC"
    rows = await db.query(sql, tuple(params))
    return {"items": [dict(r) for r in rows], "total": len(rows)}


@router.put("/{classic_id}/chapters/{chapter_id}/study-notes")
async def save_study_notes(
    classic_id: str,
    chapter_id: str,
    body: dict,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """保存某章节的学习笔记（Markdown，按 user+classic+chapter 唯一）。"""
    await _get_chapter_or_404(db, classic_id, chapter_id)
    content = body.get("content", "")

    existing = await db.query_one(
        """SELECT id FROM classic_study_notes
           WHERE user_id = ? AND classic_id = ? AND chapter_id = ?""",
        (current_user["id"], classic_id, chapter_id),
    )
    now = _now()
    if existing:
        note_id = existing["id"]
        await db.execute(
            "UPDATE classic_study_notes SET content = ?, updated_at = ? WHERE id = ?",
            (content, now, note_id),
        )
    else:
        note_id = str(uuid.uuid4())
        await db.execute(
            """INSERT INTO classic_study_notes
               (id, user_id, classic_id, chapter_id, content, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (note_id, current_user["id"], classic_id, chapter_id, content, now),
        )

    row = await db.query_one(
        "SELECT * FROM classic_study_notes WHERE id = ?", (note_id,)
    )
    return dict(row)


# ---------------------------------------------------------------------------
# Summarize (LLM aggregation of annotations + QA cards)
# ---------------------------------------------------------------------------

@router.post("/{classic_id}/summarize")
async def summarize_classic(
    classic_id: str,
    body: dict,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """汇总用户在某典籍的批注与问答卡，由 LLM 生成 FAQ 总结。"""
    classic = await _get_classic_or_404(db, classic_id)
    chapter_id = body.get("chapter_id")
    include_annotations = body.get("include_annotations", True)
    include_cards = body.get("include_cards", True)

    sql = (
        "SELECT * FROM classic_annotations "
        "WHERE user_id = ? AND classic_id = ?"
    )
    params: list[Any] = [current_user["id"], classic_id]
    if chapter_id:
        sql += " AND chapter_id = ?"
        params.append(chapter_id)

    type_filter: list[str] = []
    if include_annotations:
        type_filter.append("annotation")
    if include_cards:
        type_filter.append("qa_card")
    if type_filter:
        placeholders = ",".join("?" for _ in type_filter)
        sql += f" AND note_type IN ({placeholders})"
        params.extend(type_filter)

    sql += " ORDER BY created_at ASC"
    rows = await db.query(sql, tuple(params))

    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="无可汇总的批注或问答记录",
        )

    parts: list[str] = []
    for r in rows:
        chapter_row = await db.query_one(
            "SELECT title FROM classic_chapters WHERE id = ?",
            (r["chapter_id"],),
        )
        chapter_title = chapter_row["title"] if chapter_row else "未知章节"
        parts.append(
            f"【{chapter_title}】（{r['note_type']}）\n"
            f"原文：「{r['selected_text']}」\n"
            f"内容：{r['content']}"
        )
    all_content = "\n\n---\n\n".join(parts)

    prompt = f"请总结以下学习批注和问答，生成FAQ格式：\n{all_content}"

    if not has_api_key():
        return {
            "summary_markdown": (
                f"## 《{classic['title']}》学习总结\n\n"
                f"共 {len(rows)} 条记录。当前未配置 AI 大模型，"
                "无法生成智能总结。\n\n---\n\n" + all_content
            ),
            "model_used": None,
            "records_count": len(rows),
        }

    try:
        summary = await chat_completion([{"role": "user", "content": prompt}])
    except Exception as exc:
        logger.warning("Classics summarize LLM failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI 服务暂时不可用，请稍后重试",
        )

    return {
        "summary_markdown": summary,
        "model_used": settings.LLM_MODEL,
        "records_count": len(rows),
    }
