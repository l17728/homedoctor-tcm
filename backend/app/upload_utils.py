"""Bounded streaming reads for multipart uploads."""

from __future__ import annotations

from fastapi import HTTPException, UploadFile, status


async def read_upload_limited(file: UploadFile, max_bytes: int, detail: str) -> bytes:
    """Read an upload in bounded chunks and stop as soon as it exceeds its cap."""
    chunks: list[bytes] = []
    size = 0
    while True:
        chunk = await file.read(min(64 * 1024, max_bytes - size + 1))
        if not chunk:
            break
        size += len(chunk)
        if size > max_bytes:
            raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail=detail)
        chunks.append(chunk)
    return b"".join(chunks)
