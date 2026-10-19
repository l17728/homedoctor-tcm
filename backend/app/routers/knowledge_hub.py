"""Knowledge Hub router — unified knowledge entity API (spec §9).

Endpoints
---------
- ``GET  /api/knowledge-hub/search``                     — unified search
- ``GET  /api/knowledge-hub/entities/{entity_id}``       — entity detail + relationships
- ``GET  /api/knowledge-hub/entities/{entity_id}/relationships`` — all relationships
- ``GET  /api/knowledge-hub/types``                      — entity type facets
- ``POST /api/knowledge-hub/import``                     — text → AI process → entity
- ``POST /api/knowledge-hub/import-file``                — file → parse → AI process
- ``PUT  /api/knowledge-hub/entities/{entity_id}``       — update entity
- ``POST /api/knowledge-hub/entities/{entity_id}/view``  — bump view_count
- ``GET  /api/knowledge-hub/popular``                    — most viewed
- ``GET  /api/knowledge-hub/recent``                     — recently added

All endpoints require authentication (AGENTS.md §T1 — security boundary).
"""

from __future__ import annotations


import logging

logger = logging.getLogger(__name__)
import json
import os
import tempfile
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
from pydantic import BaseModel, Field

from app.auth import get_current_user
from app.database import DbAdapter, get_db
from app.knowledge_entity import (
    RELATIONSHIP_TYPES,
    create_relationship,
    get_entity,
    get_relationships,
    get_type_facets,
    increment_view_count,
    list_by_type,
    list_popular,
    list_recent,
    process_imported_content,
    search_entities,
    update_entity,
)
from app.knowledge_parser import (
    ALLOWED_EXTENSIONS,
    MULTIMEDIA_EXTENSIONS,
    is_video_url,
    parse_audio,
    parse_file,
    parse_url,
    parse_video_file,
    parse_video_url,
)
from app.url_validator import validate_external_url
from app.upload_utils import read_upload_limited

router = APIRouter(prefix="/api/knowledge-hub", tags=["knowledge-hub"])

MAX_IMPORT_BYTES = 20 * 1024 * 1024


def _ext(filename: str) -> str:
    return os.path.splitext(filename.lower())[1]


def _tenant_of(current_user: dict) -> str | None:
    return current_user.get("family_id") or None


def _ensure_can_modify(entity: dict, current_user: dict) -> None:
    """Write guard: global entities are admin-only; tenant entities owner-only.

    Invisible (other-tenant) entities never reach this check — the scoped
    ``get_entity`` lookup in the endpoint already turned them into 404s.
    """
    if entity.get("tenant_id") is None:
        if current_user.get("role") != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="需要管理员权限",
            )
    elif entity.get("tenant_id") != current_user.get("family_id"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="实体不存在",
        )


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class ImportRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=500, description="知识条目标题")
    content: str = Field(..., min_length=1, description="知识条目正文内容")
    source_type: str = Field("import", description="来源类型标记，默认 import")


class ImportUrlRequest(BaseModel):
    url: str = Field(..., min_length=1, max_length=2048, description="网页或视频链接")
    title: str | None = Field(None, max_length=500, description="可选自定义标题")


class UpdateEntityRequest(BaseModel):
    summary: str | None = Field(None, description="新的内容摘要")
    tags: list[str] | None = Field(None, description="新的标签列表")
    keywords: list[str] | None = Field(None, description="新的关键词列表")
    category: str | None = Field(None, description="新的分类")
    status: str | None = Field(None, description="状态：active / archived")


class CreateRelationshipRequest(BaseModel):
    source_entity_id: str = Field(..., description="源实体ID")
    target_entity_id: str = Field(..., description="目标实体ID")
    relationship_type: str = Field(..., description="关系类型代码或中文标签")
    properties: dict[str, Any] = Field(default_factory=dict)
    weight: float = Field(1.0, ge=0.0, le=10.0)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/search")
async def search_endpoint(
    q: str = Query("", description="搜索关键词（匹配 title/summary/keywords/tags）"),
    type: str | None = Query(None, alias="type", description="实体类型过滤"),
    category: str | None = Query(None, description="分类过滤"),
    tag: str | None = Query(None, description="标签过滤（模糊匹配）"),
    page: int = Query(1, ge=1, le=1000),
    page_size: int = Query(20, ge=1, le=100),
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """统一搜索 — 跨所有实体类型的全文搜索。

    返回 ``{items, total, page, page_size, facets}``，其中 ``facets`` 是
    ``{entity_type: count}``（不受 ``type`` 参数影响），便于前端展示类型标签。
    """
    return await search_entities(
        db, q=q, entity_type=type, category=category, tag=tag,
        page=page, page_size=page_size,
    )


@router.get("/types")
async def types_endpoint(
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """实体类型 facets — 返回 ``{entity_type: count}``。

    每个活跃实体的类型计数，便于前端渲染「全部 / 中药 / 方剂 / 理疗」标签。
    """
    facets = await get_type_facets(db)
    return {"facets": facets, "total": sum(facets.values())}


@router.get("/entities/{entity_id}")
async def entity_detail_endpoint(
    entity_id: str,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """实体详情 — 返回完整字段（JSON 字段已解析为对象）。"""
    entity = await get_entity(db, entity_id)
    if not entity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="实体不存在")
    relationships = await get_relationships(db, entity_id, direction="both")
    return {**entity, "relationships": relationships}


@router.get("/entities/{entity_id}/relationships")
async def entity_relationships_endpoint(
    entity_id: str,
    direction: str = Query("both", pattern="^(both|outgoing|incoming)$"),
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """实体的所有关系 — 可指定方向（both/outgoing/incoming）。"""
    entity = await get_entity(db, entity_id)
    if not entity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="实体不存在")
    relationships = await get_relationships(db, entity_id, direction=direction)
    return {"entity_id": entity_id, "direction": direction, "items": relationships, "total": len(relationships)}


@router.post("/entities/{entity_id}/relationships", status_code=status.HTTP_201_CREATED)
async def create_relationship_endpoint(
    entity_id: str,
    body: CreateRelationshipRequest,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """为实体创建一条关系。``source_entity_id`` 或 ``target_entity_id`` 必须等于 ``entity_id``。

    Both endpoints must be visible to the current tenant (global or
    own-family) — relationships to another family's private entities are
    rejected with 404. Edges between two global entities are global when
    created by an admin, tenant-scoped otherwise.
    """
    if body.source_entity_id != entity_id and body.target_entity_id != entity_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="source_entity_id 或 target_entity_id 必须等于路径中的 entity_id",
        )
    src = await get_entity(db, body.source_entity_id)
    tgt = await get_entity(db, body.target_entity_id)
    if not src:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="源实体不存在")
    if not tgt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="目标实体不存在")

    rel_tenant: str | None = None
    if src.get("tenant_id") is not None or tgt.get("tenant_id") is not None:
        rel_tenant = _tenant_of(current_user)
    elif current_user.get("role") != "admin":
        rel_tenant = _tenant_of(current_user)

    rel_id = await create_relationship(
        db, body.source_entity_id, body.target_entity_id,
        body.relationship_type, body.properties, body.weight,
        tenant_id=rel_tenant,
    )
    return {"relationship_id": rel_id, "detail": "关系已创建"}


@router.put("/entities/{entity_id}")
async def update_entity_endpoint(
    entity_id: str,
    body: UpdateEntityRequest,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """更新实体可编辑字段（summary / tags / keywords / category / status）。

    全局实体（tenant_id IS NULL）仅管理员可改；租户实体仅本家庭成员可改；
    其他家庭的实体返回 404（不泄露存在性）。
    """
    entity = await get_entity(db, entity_id)
    if not entity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="实体不存在")
    _ensure_can_modify(entity, current_user)

    updated = await update_entity(
        db, entity_id,
        summary=body.summary, tags=body.tags, keywords=body.keywords,
        category=body.category, status=body.status,
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="实体不存在")
    return updated


@router.post("/entities/{entity_id}/view")
async def view_endpoint(
    entity_id: str,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """浏览计数 +1 — 用户点开详情时由前端调用。"""
    entity = await get_entity(db, entity_id)
    if not entity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="实体不存在")
    await increment_view_count(db, entity_id)
    refreshed = await get_entity(db, entity_id)
    return {"entity_id": entity_id, "view_count": refreshed["view_count"] if refreshed else 0}


@router.post("/import", status_code=status.HTTP_201_CREATED)
async def import_endpoint(
    body: ImportRequest,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """导入文本内容 → AI 分析 → 创建知识实体。

    若 LLM 不可用（无 API key 或调用失败），仍会创建 ``entity_type='article'``
    的实体，仅缺少 AI 提取的关键词/标签/关系。返回值包含 ``ai_analyzed`` 字段
    指示是否经过了 AI 处理。
    """
    result = await process_imported_content(
        db, title=body.title, content=body.content, source_type=body.source_type,
        tenant_id=_tenant_of(current_user),
    )
    return result


@router.post("/import-file", status_code=status.HTTP_201_CREATED)
async def import_file_endpoint(
    file: UploadFile = File(..., description="待导入文档（PDF/Word/TXT/图片/MP3/MP4）"),
    title: str | None = Query(None, description="可选标题，缺省时从文件名派生"),
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """上传文件 → 解析文本 → AI 分析 → 创建知识实体。

    支持文档 ``.pdf .docx .txt .md .jpg .jpeg .png .webp`` 以及多媒体
    ``.mp3 .wav .m4a .mp4``（音频/视频经 whisper 转录）。单文件上限 20MB。
    """
    ext = _ext(file.filename or "")
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"不支持的文件格式：{ext or '(无扩展名)'}",
        )

    raw = await read_upload_limited(file, MAX_IMPORT_BYTES, "文件过大，上限 20MB")
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="文件内容为空",
        )

    filename = file.filename or "unknown"
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=ext, prefix="kh_")
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
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=result.error)

    full_text = result.full_text
    if not full_text.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="未能从文件中提取到任何文本",
        )

    derived_title = title or os.path.splitext(filename)[0].replace("_", " ").replace("-", " ").strip() or filename

    processed = await process_imported_content(
        db, title=derived_title, content=full_text, source_type="import_file",
        tenant_id=_tenant_of(current_user),
    )
    processed["parse_metadata"] = result.metadata
    processed["filename"] = filename
    return processed


@router.post("/import-url", status_code=status.HTTP_201_CREATED)
async def import_url_endpoint(
    body: ImportUrlRequest,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """从网页链接导入内容 → 提取正文 → AI 分析 → 创建知识实体。

    自动检测视频平台链接（YouTube/Bilibili）并尝试提取字幕；普通网页
    则提取主要文本。抓取或解析失败时返回 422。
    """
    url = body.url.strip()
    if not validate_external_url(url):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="URL不安全或指向内部网络",
        )
    if is_video_url(url):
        result = await parse_video_url(url)
    else:
        result = await parse_url(url)
    if result.error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=result.error)

    full_text = result.full_text
    if not full_text.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="未能从网页中提取到任何文本",
        )

    derived_title = body.title or result.metadata.get("title") or url
    processed = await process_imported_content(
        db, title=derived_title, content=full_text, source_type="import_url",
        tenant_id=_tenant_of(current_user),
    )
    processed["parse_metadata"] = result.metadata
    processed["source_url"] = url
    return processed


@router.post("/import-video-url", status_code=status.HTTP_201_CREATED)
async def import_video_url_endpoint(
    body: ImportUrlRequest,
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """从视频链接（YouTube/Bilibili）导入字幕 → AI 分析 → 创建知识实体。

    YouTube 优先使用 youtube-transcript-api 获取字幕；Bilibili 及其他平台
    回退到网页文本提取。字幕不可用时返回 422。
    """
    url = body.url.strip()
    if not validate_external_url(url):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="URL不安全或指向内部网络",
        )
    result = await parse_video_url(url)
    if result.error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=result.error)

    full_text = result.full_text
    if not full_text.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="未能从视频中提取到字幕或文本",
        )

    derived_title = body.title or result.metadata.get("title") or url
    processed = await process_imported_content(
        db, title=derived_title, content=full_text, source_type="import_video",
        tenant_id=_tenant_of(current_user),
    )
    processed["parse_metadata"] = result.metadata
    processed["source_url"] = url
    return processed


@router.get("/popular")
async def popular_endpoint(
    limit: int = Query(10, ge=1, le=100),
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """热门实体 — 按 view_count 倒序。"""
    items = await list_popular(db, limit=limit)
    return {"items": items, "total": len(items)}


@router.get("/recent")
async def recent_endpoint(
    limit: int = Query(10, ge=1, le=100),
    db: DbAdapter = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """最近添加 — 按 created_at 倒序。"""
    items = await list_recent(db, limit=limit)
    return {"items": items, "total": len(items)}


@router.get("/relationship-types")
async def relationship_types_endpoint(
    current_user: dict = Depends(get_current_user),
):
    """返回支持的关系类型映射（代码 → 中文标签）。"""
    return {"types": RELATIONSHIP_TYPES}
