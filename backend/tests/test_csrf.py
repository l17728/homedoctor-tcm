"""CSRF middleware tests — cross-origin write rejection (audit gap P2.9).

The CsrfMiddleware rejects POST/PUT/DELETE/PATCH whose Origin header is not
in the allow-list (defaults to localhost dev origins). Requests without an
Origin header (CLI/curl/tests) are allowed through.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_cross_origin_post_rejected(
    client: AsyncClient, auth_headers: dict
):
    """A POST with a foreign Origin (https://evil.com) must be rejected with 403."""
    evil_headers = {**auth_headers, "Origin": "https://evil.com"}
    response = await client.post(
        "/api/reminders",
        json={"title": "测试提醒", "times": ["08:00"]},
        headers=evil_headers,
    )
    assert response.status_code == 403
    assert "来源" in response.json()["detail"]


@pytest.mark.asyncio
async def test_cross_origin_put_rejected(
    client: AsyncClient, auth_headers: dict
):
    """A PUT with a foreign Origin must also be rejected with 403."""
    evil_headers = {**auth_headers, "Origin": "https://attacker.example"}
    response = await client.put(
        "/api/profile",
        json={"display_name": "恶意修改"},
        headers=evil_headers,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_allowed_origin_post_accepted(
    client: AsyncClient, auth_headers: dict
):
    """A POST from an allow-listed Origin (localhost) must not be CSRF-blocked."""
    local_headers = {**auth_headers, "Origin": "http://localhost:3000"}
    response = await client.post(
        "/api/reminders",
        json={"title": "正常提醒", "times": ["08:00"]},
        headers=local_headers,
    )
    assert response.status_code != 403


@pytest.mark.asyncio
async def test_missing_origin_post_accepted(
    client: AsyncClient, auth_headers: dict
):
    """A POST with no Origin header (CLI/curl) must not be CSRF-blocked."""
    response = await client.post(
        "/api/reminders",
        json={"title": "无 Origin 提醒", "times": ["08:00"]},
        headers=auth_headers,
    )
    assert response.status_code != 403
