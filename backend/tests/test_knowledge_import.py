"""Tests for multi-source knowledge ingestion (spec §18).

Covers:
- File-type detection (detect_file_type)
- PDF / DOCX / TXT / image parsing (with real test fixtures where feasible)
- Section splitting logic
- Upload endpoint (single + batch) creating knowledge_entries
- Recent listing + deletion
- File-type and size validation
- Herb/formula auto-tagging

Test fixtures for binary formats (PDF/DOCX) are generated at runtime using
PyMuPDF and python-docx so the suite is self-contained — no committed binary
blobs required. Image OCR tests use a real PNG rendered with Pillow so the
tesseract subprocess path is exercised end-to-end when tesseract is present,
and skipped gracefully when it is not.
"""

from __future__ import annotations

import io
import os
import shutil
import sys
from typing import Any

import pytest

from app.knowledge_parser import (
    SECTION_CHAR_LIMIT,
    detect_file_type,
    parse_docx,
    parse_file,
    parse_image,
    parse_pdf,
    parse_txt,
    split_into_sections,
)


# ---------------------------------------------------------------------------
# Fixture builders — generate real PDF / DOCX / image bytes in-memory
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_pdf_bytes() -> bytes:
    """Build a small PDF containing text via PyMuPDF.

    Uses ASCII text because the default MuPDF built-in font lacks CJK glyphs
    (embedding a CJK TTF would require a committed binary). The parsing logic
    is identical for CJK — only the font rendering differs. CJK parsing is
    covered by the DOCX/TXT tests.
    """
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (72, 72),
        "HuangQi tonifies Qi and lifts Yang. Dosage: 9-30g per day.",
        fontsize=12,
    )
    page2 = doc.new_page()
    page2.insert_text((72, 72), "Page two: Si Wu Tang nourishes blood.", fontsize=12)
    return doc.tobytes()


@pytest.fixture
def sample_docx_bytes() -> bytes:
    """Build a small .docx with a heading + body paragraphs."""
    docx = pytest.importorskip("docx")
    doc = docx.Document()
    doc.add_heading("中药知识", level=1)
    doc.add_paragraph("黄芪补气升阳，固表止汗。")
    doc.add_heading("方剂", level=2)
    doc.add_paragraph("四物汤补血调血，主治营血虚滞证。")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


@pytest.fixture
def sample_txt_bytes() -> bytes:
    return "黄芪补气升阳。\n\n四物汤补血调血。\nDosage 9-30g.".encode("utf-8")


@pytest.fixture
def sample_image_bytes() -> bytes:
    """Render a PNG with Chinese + ASCII text for OCR."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        pytest.skip("Pillow not available for OCR test image generation")

    img = Image.new("RGB", (400, 100), color="white")
    draw = ImageDraw.Draw(img)
    # ASCII only — PIL default bitmap font lacks CJK glyphs; OCR of CJK
    # requires a CJK TTF which we cannot assume in CI. ASCII text is enough
    # to exercise the tesseract subprocess path end-to-end.
    draw.text((10, 40), "HuangQi 9-30g Dosage", fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# detect_file_type
# ---------------------------------------------------------------------------

class TestDetectFileType:
    def test_pdf(self):
        assert detect_file_type("herbs.pdf") == "pdf"

    def test_pdf_uppercase(self):
        assert detect_file_type("HERBS.PDF") == "pdf"

    def test_docx(self):
        assert detect_file_type("notes.docx") == "docx"

    def test_doc_legacy(self):
        assert detect_file_type("old.doc") == "doc"

    def test_txt(self):
        assert detect_file_type("readme.txt") == "txt"

    def test_markdown(self):
        assert detect_file_type("guide.md") == "txt"

    def test_jpg(self):
        assert detect_file_type("photo.jpg") == "image"

    def test_jpeg(self):
        assert detect_file_type("photo.jpeg") == "image"

    def test_png(self):
        assert detect_file_type("photo.png") == "image"

    def test_webp(self):
        assert detect_file_type("photo.webp") == "image"

    def test_empty_filename_raises(self):
        with pytest.raises(ValueError, match="文件名不能为空"):
            detect_file_type("")

    def test_unsupported_extension_raises(self):
        with pytest.raises(ValueError, match="不支持的文件格式"):
            detect_file_type("movie.mp4")

    def test_no_extension_raises(self):
        with pytest.raises(ValueError, match="不支持的文件格式"):
            detect_file_type("nofile")


# ---------------------------------------------------------------------------
# Parser unit tests (file-path based)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_parse_pdf_real_file(tmp_path, sample_pdf_bytes):
    path = tmp_path / "test.pdf"
    path.write_bytes(sample_pdf_bytes)
    sections = await parse_pdf(str(path))
    assert len(sections) == 2
    assert "HuangQi" in sections[0]["text"]
    assert sections[0]["page"] == 1
    assert sections[1]["page"] == 2
    assert "Si Wu Tang" in sections[1]["text"]


@pytest.mark.asyncio
async def test_parse_docx_real_file(tmp_path, sample_docx_bytes):
    path = tmp_path / "test.docx"
    path.write_bytes(sample_docx_bytes)
    sections = await parse_docx(str(path))
    assert len(sections) >= 3
    texts = [s["text"] for s in sections]
    joined = "\n".join(texts)
    assert "黄芪补气升阳" in joined
    assert "四物汤补血调血" in joined
    # Headings should be detected
    headings = [s for s in sections if s.get("heading")]
    assert len(headings) >= 2


@pytest.mark.asyncio
async def test_parse_txt_utf8(tmp_path):
    path = tmp_path / "test.txt"
    path.write_text("黄芪补气。\nDosage 9-30g.", encoding="utf-8")
    text = await parse_txt(str(path))
    assert "黄芪补气" in text
    assert "Dosage" in text


@pytest.mark.asyncio
async def test_parse_txt_gbk_fallback(tmp_path):
    path = tmp_path / "gbk.txt"
    path.write_bytes("当归补血活血".encode("gbk"))
    text = await parse_txt(str(path))
    assert "当归补血活血" in text


@pytest.mark.asyncio
async def test_parse_image_real_file(tmp_path, sample_image_bytes):
    path = tmp_path / "test.png"
    path.write_bytes(sample_image_bytes)
    text = await parse_image(str(path))
    # If tesseract is installed, text should contain OCR output.
    # OCR on small bitmap fonts is imperfect, so we only assert that *some*
    # alphanumeric text was extracted rather than exact substrings.
    if shutil.which("tesseract"):
        assert len(text) > 0
        assert any(c.isalnum() for c in text)
    else:
        # Graceful degradation — empty string, no exception
        assert text == ""


@pytest.mark.asyncio
async def test_parse_image_missing_file_returns_empty(tmp_path):
    path = tmp_path / "does-not-exist.png"
    text = await parse_image(str(path))
    # tesseract will fail to open → empty string (no raise)
    assert text == ""


# ---------------------------------------------------------------------------
# parse_file — main entry point
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_parse_file_pdf(tmp_path, sample_pdf_bytes):
    path = tmp_path / "herbs.pdf"
    path.write_bytes(sample_pdf_bytes)
    result = await parse_file(str(path), "herbs.pdf")
    assert result.type == "pdf"
    assert result.error is None
    assert len(result.sections) >= 1
    assert result.metadata["type"] == "pdf"
    assert result.metadata["pages"] == 2
    assert result.metadata["sections"] >= 1
    assert result.metadata["words"] > 0


@pytest.mark.asyncio
async def test_parse_file_docx(tmp_path, sample_docx_bytes):
    path = tmp_path / "notes.docx"
    path.write_bytes(sample_docx_bytes)
    result = await parse_file(str(path), "notes.docx")
    assert result.type == "docx"
    assert result.error is None
    assert result.metadata["paragraphs"] >= 3
    assert result.word_count > 0


@pytest.mark.asyncio
async def test_parse_file_txt(tmp_path):
    path = tmp_path / "guide.txt"
    path.write_text("黄芪补气升阳。\n四物汤补血调血。", encoding="utf-8")
    result = await parse_file(str(path), "guide.txt")
    assert result.type == "txt"
    assert result.error is None
    assert result.full_text.count("黄芪") == 1
    assert result.full_text.count("四物汤") == 1


@pytest.mark.asyncio
async def test_parse_file_doc_legacy_returns_error(tmp_path):
    path = tmp_path / "legacy.doc"
    path.write_bytes(b"\xd0\xcf\x11\xe0")  # OLE magic bytes
    result = await parse_file(str(path), "legacy.doc")
    assert result.type == "doc"
    assert result.error is not None
    assert ".docx" in result.error
    assert result.sections == []


@pytest.mark.asyncio
async def test_parse_file_unsupported_extension(tmp_path):
    path = tmp_path / "video.mp4"
    path.write_bytes(b"fake video")
    result = await parse_file(str(path), "video.mp4")
    assert result.type == "unknown"
    assert result.error is not None
    assert "不支持的文件格式" in result.error


@pytest.mark.asyncio
async def test_parse_file_image(tmp_path, sample_image_bytes):
    path = tmp_path / "scan.png"
    path.write_bytes(sample_image_bytes)
    result = await parse_file(str(path), "scan.png")
    assert result.type == "image"
    assert result.error is None
    if shutil.which("tesseract"):
        assert result.metadata.get("ocr") is True
        assert len(result.sections) == 1
    else:
        assert result.metadata.get("empty") is True


@pytest.mark.asyncio
async def test_parse_file_word_count(tmp_path):
    path = tmp_path / "wc.txt"
    path.write_text("黄芪 黄芪 Dosage Test", encoding="utf-8")
    result = await parse_file(str(path), "wc.txt")
    # 2 CJK chars "黄芪" appears twice → 4 chars; "Dosage" + "Test" = 2 ascii words
    assert result.word_count == 6


# ---------------------------------------------------------------------------
# split_into_sections
# ---------------------------------------------------------------------------

class TestSplitIntoSections:
    def test_empty_returns_single_empty(self):
        sections = split_into_sections("")
        assert len(sections) == 1
        assert sections[0]["text"] == ""

    def test_short_text_single_section(self):
        sections = split_into_sections("短文本")
        assert len(sections) == 1
        assert sections[0]["text"] == "短文本"

    def test_markdown_heading_creates_new_section(self):
        text = "# 第一章\n内容一\n# 第二章\n内容二"
        sections = split_into_sections(text)
        assert len(sections) == 2
        assert sections[0]["heading"] == "第一章"
        assert "内容一" in sections[0]["text"]
        assert sections[1]["heading"] == "第二章"
        assert "内容二" in sections[1]["text"]

    def test_colon_heading(self):
        text = "黄芪：\n补气升阳\n当归：\n补血活血"
        sections = split_into_sections(text)
        assert len(sections) >= 2
        headings = [s["heading"] for s in sections]
        assert "黄芪" in headings
        assert "当归" in headings

    def test_long_text_split_by_char_limit(self):
        long_para = "甲" * (SECTION_CHAR_LIMIT * 3)
        sections = split_into_sections(long_para, char_limit=SECTION_CHAR_LIMIT)
        assert len(sections) >= 2
        # Each section should respect the limit (allowing for boundary splits)
        for s in sections:
            assert len(s["text"]) <= SECTION_CHAR_LIMIT + 10


# ---------------------------------------------------------------------------
# HTTP endpoint tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_upload_txt_creates_entry(client, auth_headers, sample_txt_bytes):
    """POST /api/knowledge-import/upload with a TXT file → knowledge entry."""
    resp = await client.post(
        "/api/knowledge-import/upload",
        files={"file": ("guide.txt", io.BytesIO(sample_txt_bytes), "text/plain")},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["entry_id"]
    assert body["title"] == "guide"  # filename without extension
    assert body["sections_parsed"] >= 1
    assert body["word_count"] > 0
    assert body["source_url"] == "guide.txt"
    # Auto-tagging should detect 黄芪 (seed data) in the text
    assert "黄芪" in body["tags"]


@pytest.mark.asyncio
async def test_upload_pdf_creates_entry(client, auth_headers, sample_pdf_bytes):
    resp = await client.post(
        "/api/knowledge-import/upload",
        files={"file": ("herbs.pdf", io.BytesIO(sample_pdf_bytes), "application/pdf")},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["entry_id"]
    assert body["title"] == "herbs"
    assert body["sections_parsed"] >= 1
    # PDF text is ASCII (default font lacks CJK) — verify content extracted
    assert "HuangQi" in body["entry"]["content"]


@pytest.mark.asyncio
async def test_upload_docx_creates_entry(client, auth_headers, sample_docx_bytes):
    resp = await client.post(
        "/api/knowledge-import/upload",
        files={
            "file": (
                "notes.docx",
                io.BytesIO(sample_docx_bytes),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["entry_id"]
    assert body["title"] == "notes"
    assert body["sections_parsed"] >= 1
    assert "黄芪" in body["tags"]


@pytest.mark.asyncio
async def test_upload_image_ocr(client, auth_headers, sample_image_bytes):
    resp = await client.post(
        "/api/knowledge-import/upload",
        files={"file": ("scan.png", io.BytesIO(sample_image_bytes), "image/png")},
        headers=auth_headers,
    )
    if shutil.which("tesseract"):
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["entry_id"]
        content = body["entry"]["content"]
        assert any(c.isalnum() for c in content)
    else:
        # No tesseract → empty extraction → 422 "no text extracted"
        assert resp.status_code == 422


@pytest.mark.asyncio
async def test_upload_invalid_extension_rejected(client, auth_headers):
    resp = await client.post(
        "/api/knowledge-import/upload",
        files={"file": ("video.mp4", io.BytesIO(b"fake"), "video/mp4")},
        headers=auth_headers,
    )
    assert resp.status_code == 422
    assert "不支持的文件格式" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_upload_empty_file_rejected(client, auth_headers):
    resp = await client.post(
        "/api/knowledge-import/upload",
        files={"file": ("empty.txt", io.BytesIO(b""), "text/plain")},
        headers=auth_headers,
    )
    assert resp.status_code == 422
    assert "空" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_upload_oversized_file_rejected(client, auth_headers):
    """Files > 20MB must be rejected with 413."""
    # Generate just over 20MB of bytes
    big = b"x" * (20 * 1024 * 1024 + 1)
    resp = await client.post(
        "/api/knowledge-import/upload",
        files={"file": ("big.txt", io.BytesIO(big), "text/plain")},
        headers=auth_headers,
    )
    assert resp.status_code == 413
    assert "过大" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_upload_requires_auth(client):
    """No auth header → 401/403."""
    resp = await client.post(
        "/api/knowledge-import/upload",
        files={"file": ("a.txt", io.BytesIO(b"hi"), "text/plain")},
    )
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_upload_batch_mixed(client, auth_headers, sample_txt_bytes):
    """Batch upload: one valid TXT + one invalid extension."""
    resp = await client.post(
        "/api/knowledge-import/upload-batch",
        files=[
            ("files", ("ok.txt", io.BytesIO(sample_txt_bytes), "text/plain")),
            ("files", ("bad.mp4", io.BytesIO(b"x"), "video/mp4")),
        ],
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["total_success"] == 1
    assert body["total_failures"] == 1
    assert body["success"][0]["title"] == "ok"
    assert body["failures"][0]["filename"] == "bad.mp4"


@pytest.mark.asyncio
async def test_recent_lists_imported_entries(client, auth_headers, sample_txt_bytes):
    # Upload one entry
    await client.post(
        "/api/knowledge-import/upload",
        files={"file": ("a.txt", io.BytesIO(sample_txt_bytes), "text/plain")},
        headers=auth_headers,
    )
    # Fetch recent
    resp = await client.get("/api/knowledge-import/recent", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    item = body["items"][0]
    assert item["source_type"] == "import"
    assert item["source_url"] == "a.txt"
    assert item["title"] == "a"
    assert "tags" in item
    assert "summary" in item


@pytest.mark.asyncio
async def test_recent_respects_user_isolation(
    client, auth_headers, second_user_headers, sample_txt_bytes
):
    """User A's imports must not appear in User B's recent list."""
    await client.post(
        "/api/knowledge-import/upload",
        files={"file": ("user_a.txt", io.BytesIO(sample_txt_bytes), "text/plain")},
        headers=auth_headers,
    )
    resp = await client.get("/api/knowledge-import/recent", headers=second_user_headers)
    assert resp.status_code == 200
    body = resp.json()
    titles = [it["title"] for it in body["items"]]
    assert "user_a" not in titles


@pytest.mark.asyncio
async def test_delete_entry(client, auth_headers, sample_txt_bytes):
    # Upload
    up = await client.post(
        "/api/knowledge-import/upload",
        files={"file": ("del.txt", io.BytesIO(sample_txt_bytes), "text/plain")},
        headers=auth_headers,
    )
    entry_id = up.json()["entry_id"]
    # Delete
    resp = await client.delete(
        f"/api/knowledge-import/{entry_id}", headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["detail"] == "已删除"
    # Confirm gone from recent
    recent = await client.get("/api/knowledge-import/recent", headers=auth_headers)
    ids = [it["id"] for it in recent.json()["items"]]
    assert entry_id not in ids


@pytest.mark.asyncio
async def test_delete_nonexistent_returns_404(client, auth_headers):
    resp = await client.delete(
        "/api/knowledge-import/nonexistent-id", headers=auth_headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_other_users_entry_forbidden(
    client, auth_headers, second_user_headers, sample_txt_bytes
):
    """User A cannot delete User B's imported entry."""
    up = await client.post(
        "/api/knowledge-import/upload",
        files={"file": ("mine.txt", io.BytesIO(sample_txt_bytes), "text/plain")},
        headers=auth_headers,
    )
    entry_id = up.json()["entry_id"]
    resp = await client.delete(
        f"/api/knowledge-import/{entry_id}", headers=second_user_headers
    )
    assert resp.status_code == 404  # Not visible to other user → 404


@pytest.mark.asyncio
async def test_auto_tagging_detects_herb_and_formula(
    client, auth_headers
):
    """Text mentioning seeded herbs (黄芪) and formulas (四物汤) is auto-tagged."""
    text = "本文介绍黄芪的补气功效，以及四物汤的补血作用。".encode("utf-8")
    resp = await client.post(
        "/api/knowledge-import/upload",
        files={"file": ("tags.txt", io.BytesIO(text), "text/plain")},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    tags = resp.json()["tags"]
    assert "黄芪" in tags
    assert "四物汤" in tags


@pytest.mark.asyncio
async def test_title_derived_from_filename_spaces(
    client, auth_headers
):
    """Underscores/hyphens in filenames become spaces in the title."""
    text = b"some content"
    resp = await client.post(
        "/api/knowledge-import/upload",
        files={"file": ("my_health_notes.txt", io.BytesIO(text), "text/plain")},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["title"] == "my health notes"
