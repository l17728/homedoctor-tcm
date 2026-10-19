"""SSRF protection tests — safe_fetch per-hop validation, redirects, size caps.

Mock pattern follows the project convention (see test_multimedia_import.py):
``app.knowledge_parser.httpx.AsyncClient`` is patched with an AsyncMock whose
``get`` returns canned responses — no real network access except DNS lookups
for ``example.com`` (already required by test_qa_gaps.py).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.knowledge_parser import UnsafeUrlError, parse_url, safe_fetch
from app.url_validator import validate_external_url


class _MockResponse:
    def __init__(self, text: str = "", status_code: int = 200, headers: dict | None = None):
        self.text = text
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


def _mock_client(responses: list) -> AsyncMock:
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.get = AsyncMock(side_effect=list(responses))
    return client


# ---------------------------------------------------------------------------
# url_validator — direct unit tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://127.8.8.8/",              # whole 127.0.0.0/8
        "http://0.0.0.0/",
        "http://10.0.0.1/",
        "http://172.16.0.1/",
        "http://172.31.255.255/",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
        "http://[fe80::1]/",
        "http://[::ffff:127.0.0.1]/",     # IPv4-mapped IPv6
        "http://localhost/",
        "http://sub.localhost/",
        "https://example.com:8080/",      # non-standard port (checked pre-DNS)
        "https://example.com:8443/",
        "ftp://example.com/",
        "file:///etc/passwd",
        "",
        "   ",
    ],
)
def test_validator_rejects_unsafe_urls(url):
    assert validate_external_url(url) is False


@pytest.mark.parametrize(
    "url",
    ["https://example.com/page", "http://example.com", "https://example.com:443/", "http://example.com:80/"],
)
def test_validator_accepts_safe_urls(url):
    assert validate_external_url(url) is True


# ---------------------------------------------------------------------------
# safe_fetch — per-hop validation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_safe_fetch_rejects_private_url_before_any_request():
    client = _mock_client([_MockResponse("internal")])
    with patch("app.knowledge_parser.httpx.AsyncClient", return_value=client):
        with pytest.raises(UnsafeUrlError):
            await safe_fetch("http://192.168.1.1/admin")
    client.get.assert_not_called()


@pytest.mark.asyncio
async def test_safe_fetch_rejects_redirect_to_private_network():
    redirect = _MockResponse(status_code=302, headers={"location": "http://10.0.0.5/secret"})
    client = _mock_client([redirect, _MockResponse("internal")])
    with patch("app.knowledge_parser.httpx.AsyncClient", return_value=client):
        with pytest.raises(UnsafeUrlError):
            await safe_fetch("https://example.com/redirect")
    client.get.assert_called_once()  # second hop must never be fetched


@pytest.mark.asyncio
async def test_safe_fetch_rejects_redirect_to_metadata_endpoint():
    redirect = _MockResponse(status_code=301, headers={"location": "http://169.254.169.254/meta"})
    client = _mock_client([redirect])
    with patch("app.knowledge_parser.httpx.AsyncClient", return_value=client):
        with pytest.raises(UnsafeUrlError):
            await safe_fetch("https://example.com/a")
    client.get.assert_called_once()


@pytest.mark.asyncio
async def test_safe_fetch_rejects_redirect_to_non_standard_port():
    redirect = _MockResponse(status_code=302, headers={"location": "https://example.com:8080/x"})
    client = _mock_client([redirect])
    with patch("app.knowledge_parser.httpx.AsyncClient", return_value=client):
        with pytest.raises(UnsafeUrlError):
            await safe_fetch("https://example.com/b")
    client.get.assert_called_once()


@pytest.mark.asyncio
async def test_safe_fetch_follows_legitimate_redirects():
    first = _MockResponse(status_code=302, headers={"location": "/final"})
    second = _MockResponse("<html><body>黄芪补气</body></html>")
    client = _mock_client([first, second])
    with patch("app.knowledge_parser.httpx.AsyncClient", return_value=client):
        text = await safe_fetch("https://example.com/start")
    assert "黄芪补气" in text
    assert client.get.await_count == 2


@pytest.mark.asyncio
async def test_safe_fetch_redirect_loop_hits_limit():
    responses = [
        _MockResponse(status_code=302, headers={"location": f"https://example.com/loop{i}"})
        for i in range(10)
    ]
    client = _mock_client(responses)
    with patch("app.knowledge_parser.httpx.AsyncClient", return_value=client):
        with pytest.raises(UnsafeUrlError):
            await safe_fetch("https://example.com/entry")
    assert client.get.await_count == 4  # initial request + 3 redirect hops


@pytest.mark.asyncio
async def test_safe_fetch_truncates_oversized_body():
    huge = "芪" * 200_000
    client = _mock_client([_MockResponse(huge)])
    with patch("app.knowledge_parser.httpx.AsyncClient", return_value=client):
        text = await safe_fetch("https://example.com/big", max_bytes=5000)
    assert len(text.encode("utf-8")) <= 5000


# ---------------------------------------------------------------------------
# parse_url / import endpoints
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_parse_url_unsafe_url_returns_error():
    result = await parse_url("http://169.254.169.254/latest/meta-data/")
    assert result.error is not None
    assert "不安全" in result.error


@pytest.mark.asyncio
async def test_parse_url_redirect_to_internal_returns_error():
    redirect = _MockResponse(status_code=302, headers={"location": "http://127.0.0.1:8000/api/secret"})
    client = _mock_client([redirect])
    with patch("app.knowledge_parser.httpx.AsyncClient", return_value=client):
        result = await parse_url("https://example.com/phishing")
    assert result.error is not None
    assert "不安全" in result.error
    client.get.assert_called_once()


@pytest.mark.asyncio
async def test_import_url_endpoint_rejects_internal_url(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/knowledge-hub/import-url",
        headers=auth_headers,
        json={"url": "http://192.168.1.1/admin"},
    )
    assert resp.status_code == 400
    assert "不安全" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_import_url_endpoint_rejects_localhost_with_port(
    client: AsyncClient, auth_headers: dict
):
    resp = await client.post(
        "/api/knowledge-hub/import-url",
        headers=auth_headers,
        json={"url": "http://localhost:8000/api"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_import_video_url_endpoint_rejects_internal_url(
    client: AsyncClient, auth_headers: dict
):
    resp = await client.post(
        "/api/knowledge-hub/import-video-url",
        headers=auth_headers,
        json={"url": "http://10.0.0.1/video"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_smart_search_import_rejects_internal_url(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/smart-search/import",
        headers=auth_headers,
        json={"url": "http://169.254.169.254/latest/meta-data/", "title": "x"},
    )
    assert resp.status_code == 400
