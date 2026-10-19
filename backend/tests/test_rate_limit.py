"""Tests for RateLimitMiddleware.

A dedicated minimal FastAPI app is built per-test so that the in-memory rate
limit state starts fresh for every scenario (the middleware is not registered
in ``app.main`` yet, and even after it is, isolating state avoids cross-test
interference).
"""

from __future__ import annotations

from typing import AsyncIterator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.middleware.rate_limit import RateLimitMiddleware


@pytest.fixture(autouse=True)
def _disable_test_bypass(monkeypatch):
    """Remove the global test bypass so the middleware actually rate-limits."""
    monkeypatch.delenv("HOMEDOCTOR_TESTING", raising=False)


def _build_app() -> FastAPI:
    """Minimal FastAPI app exercising general, chat and exempt paths."""
    app = FastAPI()

    @app.get("/api/health")
    async def _health() -> dict:
        return {"status": "ok"}

    @app.get("/api/herbs")
    async def _herbs() -> dict:
        return {"herbs": []}

    @app.post("/api/chat")
    async def _chat() -> dict:
        return {"reply": "hello"}

    @app.get("/api/chat/history")
    async def _chat_history() -> dict:
        return {"messages": []}

    # Middleware added last → executes first (outermost) in Starlette stack.
    app.add_middleware(RateLimitMiddleware)
    return app


@pytest_asyncio.fixture
async def rl_client() -> AsyncIterator[AsyncClient]:
    """Fresh ASGI test client with isolated rate-limit state per test."""
    app = _build_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# --------------------------------------------------------------------------- #
# 1. Normal traffic under the limit passes through
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_requests_under_limit_pass(rl_client: AsyncClient):
    """Requests below the general limit (60/min) should all return 200."""
    for _ in range(RateLimitMiddleware.GENERAL_LIMIT):
        resp = await rl_client.get("/api/herbs")
        assert resp.status_code == 200, "requests within limit must succeed"


# --------------------------------------------------------------------------- #
# 2. Exceeding the general limit returns 429
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_exceeding_general_limit_returns_429(rl_client: AsyncClient):
    """The 61st request within the window must be rejected with 429."""
    limit = RateLimitMiddleware.GENERAL_LIMIT
    for _ in range(limit):
        resp = await rl_client.get("/api/herbs")
        assert resp.status_code == 200

    over = await rl_client.get("/api/herbs")
    assert over.status_code == 429
    assert over.json()["detail"] == "请求过于频繁，请稍后再试"


# --------------------------------------------------------------------------- #
# 3. /api/chat endpoints have a stricter 10/min limit
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_chat_endpoint_has_stricter_limit(rl_client: AsyncClient):
    """Chat paths are capped at CHAT_LIMIT (10/min), independent of general."""
    chat_limit = RateLimitMiddleware.CHAT_LIMIT
    for _ in range(chat_limit):
        resp = await rl_client.post("/api/chat")
        assert resp.status_code == 200

    over = await rl_client.post("/api/chat")
    assert over.status_code == 429

    # General bucket must still be usable — counters are independent.
    herb = await rl_client.get("/api/herbs")
    assert herb.status_code == 200


@pytest.mark.asyncio
async def test_chat_history_also_uses_strict_limit(rl_client: AsyncClient):
    """Any path under /api/chat (including /history) shares the strict bucket."""
    chat_limit = RateLimitMiddleware.CHAT_LIMIT
    # Exhaust the bucket with history GETs.
    for _ in range(chat_limit):
        resp = await rl_client.get("/api/chat/history")
        assert resp.status_code == 200

    # A subsequent POST /api/chat should now also be throttled (same bucket).
    over = await rl_client.post("/api/chat")
    assert over.status_code == 429


# --------------------------------------------------------------------------- #
# 4. Health & docs endpoints are exempt
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_health_endpoint_exempt(rl_client: AsyncClient):
    """Health checks must never be rate limited, regardless of volume."""
    # Far exceeds any limit.
    for _ in range(RateLimitMiddleware.GENERAL_LIMIT + 20):
        resp = await rl_client.get("/api/health")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_docs_and_openapi_exempt(rl_client: AsyncClient):
    """Docs/schema paths are exempt from rate limiting."""
    for path in ("/openapi.json", "/docs", "/redoc"):
        resp = await rl_client.get(path)
        # FastAPI serves these; status may be 200 (json/html) but never 429.
        assert resp.status_code != 429, f"{path} must not be rate limited"


@pytest.mark.asyncio
async def test_exempt_requests_do_not_consume_general_quota(rl_client: AsyncClient):
    """Hitting /api/health repeatedly must not reduce the general allowance."""
    for _ in range(50):
        await rl_client.get("/api/health")
    # General bucket untouched → all GENERAL_LIMIT herb requests still pass.
    for _ in range(RateLimitMiddleware.GENERAL_LIMIT):
        resp = await rl_client.get("/api/herbs")
        assert resp.status_code == 200


# --------------------------------------------------------------------------- #
# 5. Different IPs maintain separate counters
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_different_ips_have_separate_counters(rl_client: AsyncClient):
    """Distinct client IPs must not share rate-limit state."""
    ip_a = "203.0.113.10"
    ip_b = "198.51.100.20"

    # Exhaust IP A's general allowance.
    for _ in range(RateLimitMiddleware.GENERAL_LIMIT):
        resp = await rl_client.get("/api/herbs", headers={"X-Forwarded-For": ip_a})
        assert resp.status_code == 200
    blocked = await rl_client.get("/api/herbs", headers={"X-Forwarded-For": ip_a})
    assert blocked.status_code == 429

    # IP B is unaffected.
    fresh = await rl_client.get("/api/herbs", headers={"X-Forwarded-For": ip_b})
    assert fresh.status_code == 200


@pytest.mark.asyncio
async def test_x_forwarded_for_uses_first_untrusted_hop(rl_client: AsyncClient, monkeypatch):
    """Walk a trusted proxy chain from right to left to find the client."""
    import ipaddress
    import app.middleware.rate_limit as rate_limit
    monkeypatch.setattr(rate_limit, "_TRUSTED_PROXY_NETWORKS", (
        ipaddress.ip_network("127.0.0.1/32"), ipaddress.ip_network("::1/128"),
        ipaddress.ip_network("10.0.0.0/8"),
    ))
    ip = "203.0.113.55"
    # A multi-hop forwarded chain must still identify the originator.
    headers = {"X-Forwarded-For": f"{ip}, 10.0.0.1, 10.0.0.2"}

    for _ in range(RateLimitMiddleware.GENERAL_LIMIT):
        resp = await rl_client.get("/api/herbs", headers=headers)
        assert resp.status_code == 200

    over = await rl_client.get("/api/herbs", headers=headers)
    assert over.status_code == 429


def test_untrusted_peer_cannot_choose_rate_limit_ip(monkeypatch):
    import ipaddress
    from starlette.requests import Request
    import app.middleware.rate_limit as rate_limit

    monkeypatch.setattr(rate_limit, "_TRUSTED_PROXY_NETWORKS", (ipaddress.ip_network("127.0.0.1/32"),))
    scope = {
        "type": "http", "method": "GET", "path": "/api/herbs",
        "headers": [(b"x-forwarded-for", b"203.0.113.9")],
        "query_string": b"", "client": ("198.51.100.8", 54321),
        "server": ("testserver", 80),
    }
    assert rate_limit.RateLimitMiddleware._get_client_ip(Request(scope)) == "198.51.100.8"


# --------------------------------------------------------------------------- #
# 6. 429 response includes a sane Retry-After header
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_429_includes_retry_after_header(rl_client: AsyncClient):
    """The 429 response must carry a positive integer Retry-After header."""
    for _ in range(RateLimitMiddleware.GENERAL_LIMIT):
        await rl_client.get("/api/herbs")

    over = await rl_client.get("/api/herbs")
    assert over.status_code == 429
    assert "Retry-After" in over.headers
    retry_after = int(over.headers["Retry-After"])
    # Within the 60s window the wait is bounded by the window size.
    assert 1 <= retry_after <= RateLimitMiddleware.GENERAL_WINDOW


@pytest.mark.asyncio
async def test_429_retry_after_for_chat(rl_client: AsyncClient):
    """Chat 429 also reports a Retry-After within its window."""
    for _ in range(RateLimitMiddleware.CHAT_LIMIT):
        await rl_client.post("/api/chat")

    over = await rl_client.post("/api/chat")
    assert over.status_code == 429
    assert "Retry-After" in over.headers
    retry_after = int(over.headers["Retry-After"])
    assert 1 <= retry_after <= RateLimitMiddleware.CHAT_WINDOW


# --------------------------------------------------------------------------- #
# Bonus: cleanup correctness — internal store stays compact
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_internal_store_compact_after_exhaustion(rl_client: AsyncClient):
    """After exhausting a bucket the IP remains tracked but no 429 leaks
    configuration internals (only the documented payload)."""
    for _ in range(RateLimitMiddleware.GENERAL_LIMIT):
        await rl_client.get("/api/herbs")
    over = await rl_client.get("/api/herbs")
    assert over.status_code == 429
    body = over.json()
    assert set(body.keys()) == {"detail"}
