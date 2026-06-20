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

import httpx

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
    ".mp3": "audio",
    ".wav": "audio",
    ".m4a": "audio",
    ".mp4": "video",
}

#: Extensions accepted by the **legacy** document-only upload endpoint
#: (``/api/knowledge-import/upload``). Kept strict so that router continues
#: to reject multimedia uploads — its tests and UI were built for documents.
DOCUMENT_EXTENSIONS: frozenset[str] = frozenset(
    {".pdf", ".docx", ".doc", ".txt", ".md", ".jpg", ".jpeg", ".png", ".webp"}
)

#: Multimedia file extensions — audio/video handled via whisper + ffmpeg.
MULTIMEDIA_EXTENSIONS: frozenset[str] = frozenset(
    {".mp3", ".wav", ".m4a", ".mp4"}
)

#: Extensions accepted by the unified hub upload endpoint
#: (``/api/knowledge-hub/import-file``) — documents **and** multimedia.
#: This is a mutable ``set`` so callers can ``.add()`` new types at runtime
#: if needed (e.g. future ``.webm`` support).
ALLOWED_EXTENSIONS: set[str] = set(DOCUMENT_EXTENSIONS) | set(MULTIMEDIA_EXTENSIONS)

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
            f"支持：{', '.join(sorted(EXTENSION_MAP))}"
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

    elif ftype == "audio":
        result = await parse_audio(file_path)
        metadata.update(result.metadata)
        if result.error:
            return ParseResult(type="audio", error=result.error, metadata=metadata)
        sections = result.sections

    elif ftype == "video":
        result = await parse_video_file(file_path)
        metadata.update(result.metadata)
        if result.error:
            return ParseResult(type="video", error=result.error, metadata=metadata)
        sections = result.sections

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


# ---------------------------------------------------------------------------
# URL / video-link / audio / video-file parsing (spec §18 — multimedia import)
# ---------------------------------------------------------------------------
#
# All multimedia parsers follow the **graceful degradation** pattern used by
# ``app.routers.voice``: when an optional dependency (whisper, ffmpeg) is
# absent, the parser returns a ``ParseResult`` with ``error`` set rather than
# raising, so callers can surface a friendly message and the import still
# produces a (possibly empty) entity shell.
#
# Chinese domain language throughout (AGENTS.md §1.7).

#: Maximum characters extracted from a fetched web page before truncation.
URL_TEXT_CHAR_LIMIT = 10000

#: Request timeout (seconds) for HTTP fetches.
URL_FETCH_TIMEOUT = 30.0

#: Regex extracting an 11-char YouTube video id from common URL shapes.
_YOUTUBE_ID_RE = re.compile(r"(?:v=|youtu\.be/|embed/|shorts/)([\w-]{11})")

#: substrings that mark a URL as a known video platform.
_VIDEO_HOST_MARKERS = ("youtube.com", "youtu.be", "bilibili.com", "b23.tv")


def is_video_url(url: str) -> bool:
    """Return True if ``url`` points to a known video platform."""
    lower = (url or "").lower()
    return any(marker in lower for marker in _VIDEO_HOST_MARKERS)


async def parse_url(url: str) -> ParseResult:
    """Fetch a web page and extract its main article text.

    Returns a :class:`ParseResult` whose ``metadata`` carries ``source_url``
    and ``title``. On fetch failure, returns a result with ``error`` set
    (no exception) so callers can degrade gracefully.
    """
    try:
        async with httpx.AsyncClient(
            timeout=URL_FETCH_TIMEOUT, follow_redirects=True
        ) as client:
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            html = resp.text
    except Exception as exc:
        return ParseResult(type="url", error=f"网页抓取失败：{exc}")

    title = _extract_html_title(html) or url
    text = _html_to_text(html)
    if len(text) > URL_TEXT_CHAR_LIMIT:
        text = text[:URL_TEXT_CHAR_LIMIT] + "..."

    sections = split_into_sections(text) if text.strip() else []
    return ParseResult(
        type="url",
        sections=sections,
        metadata={
            "source_url": url,
            "title": title,
            "fetched_chars": len(html),
            "extracted_chars": len(text),
        },
    )


def _extract_html_title(html: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL | re.IGNORECASE)
    if not match:
        return ""
    return re.sub(r"\s+", " ", match.group(1)).strip()


def _html_to_text(html: str) -> str:
    """Strip scripts/styles/nav/footer/header tags, then all remaining tags."""
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<nav[^>]*>.*?</nav>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<footer[^>]*>.*?</footer>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<header[^>]*>.*?</header>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


async def parse_video_url(url: str) -> ParseResult:
    """Extract transcript/subtitle text from a video-platform URL.

    Detects YouTube / Bilibili and delegates; unknown hosts fall back to
    :func:`parse_url` (generic web-page extraction).
    """
    lower = (url or "").lower()
    if "youtube.com" in lower or "youtu.be" in lower:
        return await _parse_youtube(url)
    if "bilibili.com" in lower or "b23.tv" in lower:
        return await _parse_bilibili(url)
    return await parse_url(url)


def _fetch_youtube_transcript(api_cls, video_id: str):
    """Fetch transcript from YouTube, supporting both API versions.

    - ``youtube-transcript-api < 1.0``: classmethod ``get_transcript(id, languages=[...])``
      returns ``list[dict]`` with ``"text"`` key.
    - ``youtube-transcript-api >= 1.0``: instance method ``fetch(id, languages=[...])``
      returns ``FetchedTranscript`` (iterable of dataclass objects with ``.text``).
    """
    langs = ["zh-Hans", "zh", "en"]
    get_transcript = getattr(api_cls, "get_transcript", None)
    if callable(get_transcript):
        return get_transcript(video_id, languages=langs)
    instance = api_cls()
    return instance.fetch(video_id, languages=langs)


def _transcript_seg_text(seg) -> str:
    """Extract text from a transcript segment — dict (v0.x) or dataclass (v1.x)."""
    if isinstance(seg, dict):
        return str(seg.get("text", ""))
    return str(getattr(seg, "text", "") or "")


async def _parse_youtube(url: str) -> ParseResult:
    """Try the YouTube transcript API; fall back to page-text extraction."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        logger.info("youtube-transcript-api 未安装，回退到网页文本提取")
        return await parse_url(url)

    match = _YOUTUBE_ID_RE.search(url)
    if not match:
        return await parse_url(url)
    video_id = match.group(1)

    try:
        transcript = await asyncio.to_thread(
            _fetch_youtube_transcript, YouTubeTranscriptApi, video_id,
        )
        text = " ".join(_transcript_seg_text(seg) for seg in transcript).strip()
    except Exception as exc:
        logger.info("YouTube 字幕获取失败 (%s)，回退到网页文本： %s", video_id, exc)
        return await parse_url(url)

    sections = split_into_sections(text) if text else []
    return ParseResult(
        type="video",
        sections=sections,
        metadata={
            "source_url": url,
            "platform": "youtube",
            "video_id": video_id,
            "title": f"YouTube视频 {video_id}",
        },
    )


async def _parse_bilibili(url: str) -> ParseResult:
    """Bilibili subtitle API requires auth — fall back to page text for MVP."""
    result = await parse_url(url)
    result.metadata["platform"] = "bilibili"
    result.metadata["note"] = "Bilibili 字幕需登录，已提取页面文本"
    return result


def _load_whisper():
    """Lazily import openai-whisper. Returns the module or ``None``."""
    try:
        import whisper  # type: ignore[import-untyped]
        return whisper
    except ImportError:
        return None


async def parse_audio(file_path: str) -> ParseResult:
    """Transcribe an audio file via whisper.

    Returns a :class:`ParseResult` with ``error`` set when whisper is not
    installed — callers can still create an entity shell.
    """
    whisper = _load_whisper()
    if whisper is None:
        return ParseResult(
            type="audio",
            error="Whisper 未安装，无法转录音频。请运行：pip install openai-whisper",
        )

    try:
        text = await asyncio.to_thread(_transcribe_with_whisper, whisper, file_path)
    except Exception as exc:
        return ParseResult(type="audio", error=f"音频转录失败：{exc}")

    sections = split_into_sections(text) if text.strip() else []
    return ParseResult(
        type="audio",
        sections=sections,
        metadata={"engine": "whisper", "transcribed_chars": len(text)},
    )


def _transcribe_with_whisper(whisper_module, file_path: str) -> str:
    model = whisper_module.load_model("base")
    result = model.transcribe(file_path, language="zh")
    return (result.get("text") or "").strip()


async def parse_video_file(file_path: str) -> ParseResult:
    """Extract audio from a video file (ffmpeg) then transcribe (whisper).

    Also extracts keyframes via ffmpeg scene detection and analyzes them
    with the Vision LLM (Qwen2.5-VL-72b) for visual content understanding.

    Both ffmpeg and whisper are optional; missing either yields a result
    with ``error`` set rather than raising.
    """
    if shutil.which("ffmpeg") is None:
        return ParseResult(
            type="video",
            error="ffmpeg 未安装，无法从视频中提取音频",
        )

    audio_path = file_path.rsplit(".", 1)[0] + "_audio.wav"
    try:
        proc = await asyncio.to_thread(_ffmpeg_extract_audio, file_path, audio_path)
    except subprocess.TimeoutExpired:
        _safe_unlink(audio_path)
        return ParseResult(type="video", error="ffmpeg 提取音频超时（>300秒）")
    except Exception as exc:
        _safe_unlink(audio_path)
        return ParseResult(type="video", error=f"ffmpeg 执行失败：{exc}")
    if proc.returncode != 0:
        _safe_unlink(audio_path)
        return ParseResult(
            type="video",
            error=f"ffmpeg 提取音频失败：{proc.stderr.strip()[:200]}",
        )

    transcript_result: ParseResult | None = None
    try:
        transcript_result = await parse_audio(audio_path)
        transcript_result.type = "video"
        transcript_result.metadata["extracted_audio"] = True
    finally:
        _safe_unlink(audio_path)

    visual_descriptions = await _extract_keyframe_descriptions(file_path, max_frames=5)

    if visual_descriptions:
        visual_section = ParsedSection(
            heading="视频画面内容",
            paragraphs=visual_descriptions,
        )
        if transcript_result and transcript_result.sections:
            transcript_result.sections.append(visual_section)
        elif transcript_result:
            transcript_result.sections = [visual_section]
        if transcript_result:
            transcript_result.metadata["keyframe_count"] = len(visual_descriptions)
            transcript_result.metadata["visual_analysis"] = True

    if transcript_result:
        return transcript_result
    return ParseResult(type="video", error="音频和画面提取均失败")


async def _extract_keyframe_descriptions(
    video_path: str, max_frames: int = 5
) -> list[str]:
    """Extract keyframes via ffmpeg scene detection + Vision LLM analysis.

    Returns a list of description strings, one per analyzed keyframe.
    Fails gracefully: returns [] if ffmpeg or Vision LLM is unavailable.
    """
    import tempfile

    tmpdir = tempfile.mkdtemp(prefix="keyframes_")
    frame_pattern = os.path.join(tmpdir, "frame_%03d.jpg")

    try:
        proc = await asyncio.to_thread(
            _ffmpeg_extract_keyframes, video_path, frame_pattern, max_frames
        )
        if proc is None or proc.returncode != 0:
            return []

        frames = sorted(
            f for f in os.listdir(tmpdir) if f.endswith(".jpg")
        )[:max_frames]
        if not frames:
            return []

        descriptions: list[str] = []
        for i, fname in enumerate(frames):
            fpath = os.path.join(tmpdir, fname)
            desc = await _analyze_frame_with_vision(fpath, i + 1)
            if desc:
                descriptions.append(desc)
        return descriptions
    except Exception as exc:
        logger.info("keyframe extraction failed: %s", exc)
        return []
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _ffmpeg_extract_keyframes(
    video_path: str, output_pattern: str, max_frames: int
) -> subprocess.CompletedProcess[bytes] | None:
    """Run ffmpeg scene detection to extract keyframes as JPEG."""
    cmd = [
        "ffmpeg", "-i", video_path,
        "-filter:v", f"select='gt(scene,0.3)',showinfo",
        "-vsync", "vfr",
        "-frames:v", str(max_frames),
        "-q:v", "2",
        output_pattern,
        "-y",
    ]
    try:
        return subprocess.run(
            cmd, capture_output=True, timeout=120,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


async def _analyze_frame_with_vision(image_path: str, frame_num: int) -> str | None:
    """Send a keyframe to the Vision LLM (Qwen2.5-VL-72b) for description."""
    try:
        from app.llm import chat_completion_with_image, encode_image, has_api_key

        if not has_api_key():
            return None

        with open(image_path, "rb") as f:
            image_b64 = encode_image(f.read())

        prompt = (
            "这是中医药健康视频的一个关键帧。请简要描述画面中的内容，"
            "包括：药材、方剂、穴位、疗法、人体部位、文字信息等。"
            "用中文回答，不超过100字。"
        )
        description = await chat_completion_with_image(
            text=prompt,
            image_base64=image_b64,
        )
        if description and len(description) > 5:
            return f"【画面{frame_num}】{description.strip()}"
    except Exception as exc:
        logger.info("vision LLM analysis failed for frame %d: %s", frame_num, exc)
    return None


def _safe_unlink(path: str) -> None:
    if os.path.exists(path):
        try:
            os.unlink(path)
        except OSError:
            pass


def _ffmpeg_extract_audio(video_path: str, audio_path: str):
    """Run ffmpeg to extract mono 16kHz PCM WAV. Returns the CompletedProcess."""
    return subprocess.run(
        [
            "ffmpeg", "-i", video_path,
            "-vn", "-acodec", "pcm_s16le",
            "-ar", "16000", "-ac", "1",
            audio_path, "-y",
        ],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
