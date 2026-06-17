"""Multi-format knowledge document parser (spec §18).

Extracts text from uploaded files (PDF, Word, TXT, images) and produces a
structured result that can be persisted as ``knowledge_entries`` rows.

Design notes:
- **PyMuPDF (fitz)** is used for PDF extraction — pure-Python binding, no
  external binary beyond what the wheel bundles, supports CJK text natively.
- **python-docx** extracts text from ``.docx`` files. Legacy ``.doc`` binary
  format is not supported directly (would require LibreOffice); the parser
  raises a clear error directing the user to convert.
- **tesseract** (subprocess, ``chi_sim+eng``) handles image OCR. It is already
  present in the Docker image; when absent the parser degrades gracefully.
- All public functions are ``async`` so callers can ``await`` them inside
  FastAPI endpoints; heavy CPU work (PyMuPDF/tesseract) is offloaded to a
  thread pool via ``asyncio.to_thread`` to avoid blocking the event loop.
- Chinese domain language throughout (spec §1.7): section headings, metadata
  keys, and error messages are Chinese.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Maximum chars per section when no explicit heading is found.
SECTION_CHAR_LIMIT = 500

#: Supported file extensions → parser type. (spec §18)
EXTENSION_MAP: dict[str, str] = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".doc": "doc",  # legacy Word — flagged as unsupported for direct parse
    ".txt": "txt",
    ".md": "txt",
    ".jpg": "image",
    ".jpeg": "image",
    ".png": "image",
    ".webp": "image",
    ".gif": "image",
    ".bmp": "image",
    ".tiff": "image",
}

#: Extensions accepted by the upload endpoint (spec §18 acceptance list).
ALLOWED_EXTENSIONS: frozenset[str] = frozenset(
    {".pdf", ".docx", ".doc", ".txt", ".md", ".jpg", ".jpeg", ".png", ".webp"}
)

#: Tesseract language pack combo — Chinese simplified + English.
TESSERACT_LANG = os.environ.get("HOMEDOCTOR_TESSERACT_LANG", "chi_sim+eng")


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class ParseResult:
    """Structured output of :func:`parse_file`.

    ``sections`` is a list of ``{heading, text}`` dicts; for single-section
    sources (TXT/image) there is exactly one section with an empty heading.
    """

    type: str
    sections: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    @property
    def full_text(self) -> str:
        return "\n\n".join(s.get("text", "") for s in self.sections)

    @property
    def word_count(self) -> int:
        # Count CJK chars + ASCII words. Cheap heuristic good enough for
        # metadata; not a precise token count.
        text = self.full_text
        cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
        ascii_words = len(re.findall(r"[A-Za-z0-9]+", text))
        return cjk + ascii_words

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "sections": self.sections,
            "metadata": self.metadata,
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# File-type detection
# ---------------------------------------------------------------------------

def detect_file_type(filename: str) -> str:
    """Return the parser type for ``filename`` based on its extension.

    Returns one of: ``pdf``, ``docx``, ``doc``, ``txt``, ``image``.
    Raises :class:`ValueError` for unsupported extensions.
    """
    if not filename:
        raise ValueError("文件名不能为空")
    _, ext = os.path.splitext(filename.lower())
    if ext not in EXTENSION_MAP:
        raise ValueError(
            f"不支持的文件格式：{ext or '(无扩展名)'}。"
            f"支持：{', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )
    return EXTENSION_MAP[ext]


# ---------------------------------------------------------------------------
# PDF parsing (PyMuPDF / fitz)
# ---------------------------------------------------------------------------

async def parse_pdf(file_path: str) -> list[dict[str, Any]]:
    """Extract text from a PDF using PyMuPDF.

    Returns ``[{page: 1, text: "..."}, ...]`` — one entry per page that
    contains extractable text. Scanned/image-only PDFs will yield empty
    strings here; callers may fall back to OCR per-page if needed (V2).
    """
    sections = await asyncio.to_thread(_parse_pdf_sync, file_path)
    return sections


def _parse_pdf_sync(file_path: str) -> list[dict[str, Any]]:
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:  # pragma: no cover - dependency declared
        raise RuntimeError(
            "PyMuPDF 未安装，无法解析 PDF。请运行 pip install PyMuPDF"
        ) from exc

    sections: list[dict[str, Any]] = []
    with fitz.open(file_path) as doc:
        for i, page in enumerate(doc, start=1):
            text = page.get_text("text").strip()
            if text:
                sections.append({"page": i, "text": text})
    return sections


# ---------------------------------------------------------------------------
# DOCX parsing (python-docx)
# ---------------------------------------------------------------------------

async def parse_docx(file_path: str) -> list[dict[str, Any]]:
    """Extract text from a ``.docx`` file using python-docx.

    Returns ``[{paragraph: 1, text: "...", heading: "..."}, ...]``. Heading
    paragraphs (Word built-in heading styles) carry a ``heading`` key so the
    caller can split sections by structure.
    """
    return await asyncio.to_thread(_parse_docx_sync, file_path)


def _parse_docx_sync(file_path: str) -> list[dict[str, Any]]:
    try:
        import docx  # python-docx
    except ImportError as exc:  # pragma: no cover - dependency declared
        raise RuntimeError(
            "python-docx 未安装，无法解析 Word 文档。请运行 pip install python-docx"
        ) from exc

    document = docx.Document(file_path)
    sections: list[dict[str, Any]] = []
    for idx, para in enumerate(document.paragraphs, start=1):
        text = (para.text or "").strip()
        if not text:
            continue
        entry: dict[str, Any] = {"paragraph": idx, "text": text}
        style = (para.style.name or "") if para.style else ""
        if style.lower().startswith("heading"):
            entry["heading"] = text
        sections.append(entry)
    return sections


# ---------------------------------------------------------------------------
# TXT parsing
# ---------------------------------------------------------------------------

async def parse_txt(file_path: str) -> str:
    """Read a plain-text file, auto-detecting encoding (UTF-8 → GBK fallback).

    Returns the full text. Many legacy Chinese TXTs are GBK-encoded; falling
    back avoids mojibake.
    """
    return await asyncio.to_thread(_parse_txt_sync, file_path)


def _parse_txt_sync(file_path: str) -> str:
    for encoding in ("utf-8", "gbk", "gb18030", "utf-16"):
        try:
            with open(file_path, "r", encoding=encoding) as fh:
                return fh.read()
        except UnicodeDecodeError:
            continue
    # Last resort: read bytes, ignore errors
    with open(file_path, "r", encoding="utf-8", errors="ignore") as fh:
        return fh.read()


# ---------------------------------------------------------------------------
# Image OCR (tesseract subprocess)
# ---------------------------------------------------------------------------

async def parse_image(file_path: str) -> str:
    """Extract text from an image via tesseract OCR (``chi_sim+eng``).

    Returns the recognized text. If tesseract is not installed, returns an
    empty string and logs a warning rather than raising — callers can still
    create a knowledge entry with a note that OCR was unavailable.
    """
    return await asyncio.to_thread(_parse_image_sync, file_path)


def _parse_image_sync(file_path: str) -> str:
    if shutil.which("tesseract") is None:
        logger.warning("tesseract 未安装，跳过图片 OCR（%s）", file_path)
        return ""

    try:
        proc = subprocess.run(
            ["tesseract", file_path, "-", "-l", TESSERACT_LANG],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except subprocess.TimeoutExpired:
        logger.warning("tesseract OCR 超时（%s）", file_path)
        return ""
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("tesseract OCR 失败（%s）: %s", file_path, exc)
        return ""

    if proc.returncode != 0:
        logger.warning(
            "tesseract 返回非零退出码 %s（%s）: %s",
            proc.returncode, file_path, proc.stderr.strip(),
        )
        return ""
    return proc.stdout.strip()


# ---------------------------------------------------------------------------
# Section splitting
# ---------------------------------------------------------------------------

def split_into_sections(
    text: str, *, char_limit: int = SECTION_CHAR_LIMIT
) -> list[dict[str, Any]]:
    """Split free text into sections.

    Strategy:
    1. Split on Markdown-style headings (``#``, ``##``, lines ending with
       ``：`` or consisting of a short title) to respect document structure.
    2. Any remaining chunk longer than ``char_limit`` is split further on
       paragraph/line boundaries, then hard-truncated as a last resort.
    """
    if not text or not text.strip():
        return [{"heading": "", "text": ""}]

    # Split on lines that look like headings: Markdown #, or short lines
    # (≤30 chars) ending with a CJK colon or consisting mainly of CJK.
    lines = text.splitlines()
    sections: list[dict[str, Any]] = []
    current_heading = ""
    current_buf: list[str] = []

    def _flush() -> None:
        nonlocal current_buf
        if current_buf:
            body = "\n".join(current_buf).strip()
            if body:
                # Further split very long bodies by char_limit
                for chunk in _chunk_by_size(body, char_limit):
                    sections.append({"heading": current_heading, "text": chunk})
            current_buf = []

    for line in lines:
        stripped = line.strip()
        if _looks_like_heading(stripped):
            _flush()
            current_heading = stripped.lstrip("#").strip().rstrip("：:").strip()
        else:
            current_buf.append(line)
    _flush()

    if not sections:
        for chunk in _chunk_by_size(text.strip(), char_limit):
            sections.append({"heading": "", "text": chunk})
    return sections


def _looks_like_heading(line: str) -> bool:
    if not line:
        return False
    if line.startswith("#"):
        return True
    # Short line ending with full-width colon → likely a section title
    if len(line) <= 30 and line.endswith(("：", ":")):
        return True
    return False


def _chunk_by_size(text: str, limit: int) -> list[str]:
    text = text.strip()
    if len(text) <= limit:
        return [text] if text else []
    chunks: list[str] = []
    # Prefer splitting on blank lines first
    paragraphs = re.split(r"\n\s*\n", text)
    buf = ""
    for para in paragraphs:
        if len(buf) + len(para) + 2 <= limit:
            buf = f"{buf}\n\n{para}".strip() if buf else para
        else:
            if buf:
                chunks.append(buf)
                buf = ""
            if len(para) <= limit:
                buf = para
            else:
                # Split long paragraph on line boundaries first
                for line in para.splitlines(keepends=True):
                    if len(line) <= limit:
                        if len(buf) + len(line) <= limit:
                            buf += line
                        else:
                            if buf:
                                chunks.append(buf.rstrip())
                            buf = line
                    else:
                        # Single line exceeds limit → hard-split by char count
                        if buf:
                            chunks.append(buf.rstrip())
                            buf = ""
                        for i in range(0, len(line), limit):
                            chunks.append(line[i : i + limit])
    if buf and buf.strip():
        chunks.append(buf.rstrip())
    return [c for c in chunks if c]


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def parse_file(file_path: str, filename: str) -> ParseResult:
    """Detect file type and dispatch to the appropriate parser.

    Returns a :class:`ParseResult` with normalized sections and metadata.
    On unsupported/legacy formats the result carries ``error`` instead of
    raising, so the caller can surface a friendly message.
    """
    try:
        ftype = detect_file_type(filename)
    except ValueError as exc:
        return ParseResult(type="unknown", error=str(exc))

    metadata: dict[str, Any] = {"filename": filename, "type": ftype}
    sections: list[dict[str, Any]] = []

    if ftype == "pdf":
        try:
            raw = await parse_pdf(file_path)
        except Exception as exc:
            return ParseResult(type="pdf", error=f"PDF 解析失败：{exc}")
        # Merge consecutive pages into char-limited sections
        full = "\n\n".join(p["text"] for p in raw)
        metadata["pages"] = len(raw)
        sections = split_into_sections(full)
        # Tag each section with page origin if possible
        for s in sections:
            s.setdefault("page", 1)

    elif ftype == "docx":
        try:
            raw = await parse_docx(file_path)
        except Exception as exc:
            return ParseResult(type="docx", error=f"Word 文档解析失败：{exc}")
        metadata["paragraphs"] = len(raw)
        # Group by heading structure
        sections = _docx_to_sections(raw)

    elif ftype == "doc":
        return ParseResult(
            type="doc",
            error=(
                "旧版 .doc 格式暂不支持直接解析。"
                "请将文档另存为 .docx 后重新上传。"
            ),
        )

    elif ftype == "txt":
        try:
            full = await parse_txt(file_path)
        except Exception as exc:
            return ParseResult(type="txt", error=f"文本文件解析失败：{exc}")
        metadata["lines"] = full.count("\n") + 1
        sections = split_into_sections(full)

    elif ftype == "image":
        try:
            ocr_text = await parse_image(file_path)
        except Exception as exc:
            return ParseResult(type="image", error=f"图片 OCR 失败：{exc}")
        metadata["ocr"] = bool(ocr_text)
        sections = [{"heading": "", "text": ocr_text}] if ocr_text else []

    else:  # pragma: no cover - detect_file_type guards this
        return ParseResult(type=ftype, error=f"未知文件类型：{ftype}")

    metadata["sections"] = len(sections)
    metadata["words"] = sum(
        len(re.findall(r"[\u4e00-\u9fff]", s.get("text", "")))
        + len(re.findall(r"[A-Za-z0-9]+", s.get("text", "")))
        for s in sections
    )

    if not sections or all(not s.get("text", "").strip() for s in sections):
        metadata["empty"] = True

    return ParseResult(type=ftype, sections=sections, metadata=metadata)


def _docx_to_sections(
    raw: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Group python-docx paragraphs into sections by heading.

    Each heading starts a new section; non-heading paragraphs accumulate
    under the current heading. Very long sections are further split by
    :func:`split_into_sections`.
    """
    sections: list[dict[str, Any]] = []
    current_heading = ""
    current_buf: list[str] = []

    def _flush() -> None:
        nonlocal current_buf
        if current_buf:
            body = "\n".join(current_buf).strip()
            if body:
                for chunk in _chunk_by_size(body, SECTION_CHAR_LIMIT):
                    sections.append({"heading": current_heading, "text": chunk})
            current_buf = []

    for para in raw:
        if para.get("heading"):
            _flush()
            current_heading = para["heading"]
            current_buf.append(para["text"])
        else:
            current_buf.append(para["text"])
    _flush()

    if not sections:
        full = "\n".join(p["text"] for p in raw)
        sections = split_into_sections(full)
    return sections
