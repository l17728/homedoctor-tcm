"""Semantic text chunking for RAG ingestion.

Splits long text into semantically meaningful chunks (paragraph → sentence
fallback) suitable for embedding. Chinese-aware token estimation.

Design (AGENTS.md §1.7 — 中文领域语言):
- Token estimate for Chinese text: ``len(text) // 2`` (≈2 chars/token).
- Headers (lines starting with ``#`` or ending with ``：`` / ``:``) open a
  new hierarchy section — recorded in ``hierarchy_path``.
- Overlap between adjacent chunks preserves context across boundaries.
"""

from __future__ import annotations


import logging

logger = logging.getLogger(__name__)
import re
from dataclasses import dataclass, field
from typing import Any


_SENTENCE_ENDS = re.compile(r"[。！？!?；;\n]+")


@dataclass
class Chunk:
    text: str
    index: int
    token_count: int
    hierarchy_path: str = ""
    hierarchy_level: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "index": self.index,
            "token_count": self.token_count,
            "hierarchy_path": self.hierarchy_path,
            "hierarchy_level": self.hierarchy_level,
            "metadata": self.metadata,
        }


def estimate_tokens(text: str) -> int:
    """Estimate token count for mixed CN/EN text (~2 Chinese chars per token)."""
    if not text:
        return 0
    return len(text) // 2


def _is_header(line: str) -> bool:
    """Detect markdown/Chinese header lines."""
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.startswith("#"):
        return True
    if stripped.endswith(("：", ":")) and len(stripped) <= 40:
        return True
    return False


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences on CN/EN punctuation + newlines."""
    parts = _SENTENCE_ENDS.split(text)
    return [p.strip() for p in parts if p.strip()]


def _split_paragraphs(text: str) -> list[str]:
    """Split on blank lines; keep non-empty paragraphs."""
    return [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]


def chunk_text(
    text: str,
    max_tokens: int = 512,
    overlap: int = 50,
) -> list[dict[str, Any]]:
    """Split ``text`` into semantic chunks.

    Algorithm:
      1. Walk lines, tracking header-based ``hierarchy_path``.
      2. Buffer paragraphs until ``max_tokens`` is reached.
      3. If a single paragraph exceeds ``max_tokens``, fall back to
         sentence-level splitting.
      4. Adjacent chunks share ``overlap`` tokens of trailing context.

    Returns a list of chunk dicts (see :class:`Chunk.to_dict`).
    """
    if not text or not text.strip():
        return []

    chunks: list[dict[str, Any]] = []
    hierarchy_parts: list[str] = []
    buffer: list[str] = []
    buffer_tokens = 0
    idx = 0

    paragraphs = _split_paragraphs(text)

    def _flush(level: int, path: str) -> None:
        nonlocal buffer, buffer_tokens, idx
        if not buffer:
            return
        chunk_text_str = "\n\n".join(buffer).strip()
        if chunk_text_str:
            chunks.append(Chunk(
                text=chunk_text_str,
                index=idx,
                token_count=estimate_tokens(chunk_text_str),
                hierarchy_path=path,
                hierarchy_level=level,
            ).to_dict())
            idx += 1
        buffer = []
        buffer_tokens = 0

    for para in paragraphs:
        lines = para.split("\n")
        header_line: str | None = None
        body_lines: list[str] = []
        for ln in lines:
            if _is_header(ln):
                header_line = ln.strip().lstrip("#").strip().rstrip("：:").strip()
                body_lines.append(ln)
            else:
                body_lines.append(ln)

        if header_line:
            _flush(len(hierarchy_parts), "/".join(hierarchy_parts))
            hierarchy_parts.append(header_line)

        body = "\n".join(body_lines).strip()
        if not body:
            continue

        body_tokens = estimate_tokens(body)

        if body_tokens > max_tokens:
            _flush(len(hierarchy_parts), "/".join(hierarchy_parts))
            for sent in _split_sentences(body):
                sent_tokens = estimate_tokens(sent)
                if sent_tokens > max_tokens:
                    # Hard-split very long single sentence by char count.
                    char_step = max_tokens * 2
                    for start in range(0, len(sent), char_step):
                        piece = sent[start:start + char_step]
                        chunks.append(Chunk(
                            text=piece,
                            index=idx,
                            token_count=estimate_tokens(piece),
                            hierarchy_path="/".join(hierarchy_parts),
                            hierarchy_level=len(hierarchy_parts),
                        ).to_dict())
                        idx += 1
                    continue
                if buffer_tokens + sent_tokens > max_tokens and buffer:
                    _flush(len(hierarchy_parts), "/".join(hierarchy_parts))
                buffer.append(sent)
                buffer_tokens += sent_tokens
                if buffer_tokens >= max_tokens:
                    _flush(len(hierarchy_parts), "/".join(hierarchy_parts))
            _flush(len(hierarchy_parts), "/".join(hierarchy_parts))
            continue

        if buffer_tokens + body_tokens > max_tokens and buffer:
            _flush(len(hierarchy_parts), "/".join(hierarchy_parts))
            if overlap > 0 and buffer:
                pass

        buffer.append(body)
        buffer_tokens += body_tokens

        if buffer_tokens >= max_tokens:
            _flush(len(hierarchy_parts), "/".join(hierarchy_parts))

    _flush(len(hierarchy_parts), "/".join(hierarchy_parts))

    if overlap > 0 and len(chunks) > 1:
        chunks = _apply_overlap(chunks, overlap)

    return chunks


def _apply_overlap(chunks: list[dict[str, Any]], overlap: int) -> list[dict[str, Any]]:
    """Prepend a slice of the previous chunk's tail to each chunk (in chars)."""
    char_overlap = overlap * 2
    result: list[dict[str, Any]] = []
    for i, ch in enumerate(chunks):
        text = ch["text"]
        if i > 0 and char_overlap > 0:
            prev_text = chunks[i - 1]["text"]
            tail = prev_text[-char_overlap:]
            if tail and tail not in text:
                text = tail + text
        new_ch = dict(ch)
        new_ch["text"] = text
        new_ch["token_count"] = estimate_tokens(text)
        result.append(new_ch)
    return result


def chunk_entity_content(
    title: str,
    summary: str = "",
    keywords: list[str] | None = None,
    content_preview: str = "",
    properties: dict[str, Any] | None = None,
    max_tokens: int = 512,
) -> list[dict[str, Any]]:
    """Build chunks from a knowledge_entity's denormalized fields.

    Produces a title chunk plus a content chunk from summary/preview/properties.
    """
    properties = properties or {}
    keywords = keywords or []

    parts: list[str] = [f"# {title}"]
    if summary:
        parts.append(summary)
    if keywords:
        parts.append("关键词：" + "、".join(keywords))
    if content_preview:
        parts.append(content_preview)
    for k, v in properties.items():
        if v and isinstance(v, (str, int, float)):
            parts.append(f"{k}：{v}")

    return chunk_text("\n\n".join(parts), max_tokens=max_tokens, overlap=50)
