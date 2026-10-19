import pytest
from fastapi import HTTPException

from app.upload_utils import read_upload_limited


class FakeUpload:
    def __init__(self, data: bytes):
        self.data = data
        self.offset = 0
        self.read_sizes: list[int] = []

    async def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        if size < 0:
            size = len(self.data)
        chunk = self.data[self.offset:self.offset + size]
        self.offset += len(chunk)
        return chunk


@pytest.mark.asyncio
async def test_bounded_upload_read_returns_small_file_in_chunks():
    upload = FakeUpload(b"a" * 100_000)
    assert await read_upload_limited(upload, 100_000, "too large") == b"a" * 100_000
    assert len(upload.read_sizes) == 3
    assert max(upload.read_sizes) <= 64 * 1024


@pytest.mark.asyncio
async def test_bounded_upload_read_stops_at_limit_plus_one():
    upload = FakeUpload(b"a" * 100_001)
    with pytest.raises(HTTPException) as exc:
        await read_upload_limited(upload, 100_000, "too large")
    assert exc.value.status_code == 413
    assert upload.offset <= 100_001
