"""Rate limit middleware — sliding window per-IP rate limiting (pure stdlib).

General API: 60 requests / 60 seconds per IP.
/api/chat endpoints: 10 requests / 60 seconds per IP (LLM calls are expensive).
Health & docs endpoints are exempt. Exceeding the limit returns 429 with a
``Retry-After`` header indicating when the client may retry.
"""

from __future__ import annotations

import logging
import os
import time
import ipaddress
from typing import Dict, List

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)
_TRUSTED_PROXY_NETWORKS = tuple(
    ipaddress.ip_network(item.strip(), strict=False)
    for item in os.environ.get("HOMEDOCTOR_TRUSTED_PROXY_IPS", "127.0.0.1,::1").split(",")
    if item.strip()
)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """In-memory sliding-window rate limiter keyed by client IP.

    Two independent buckets per IP:
      * general — applies to all non-exempt, non-chat API paths.
      * chat    — applies to paths starting with ``/api/chat``.

    On every request the current IP's expired timestamps are pruned. Every
    ``CLEANUP_INTERVAL`` requests a global sweep prunes all IPs to prevent
    unbounded memory growth from idle clients.
    """

    # Paths exempt from rate limiting (health checks & API docs).
    EXEMPT_PATHS = frozenset(
        {
            "/api/health",
            "/docs",
            "/redoc",
            "/openapi.json",
        }
    )

    # General rate limit (per IP).
    GENERAL_LIMIT = 60
    GENERAL_WINDOW = 60  # seconds

    # Stricter limit for expensive LLM endpoints.
    CHAT_LIMIT = 10
    CHAT_WINDOW = 60  # seconds

    # Run a global cleanup sweep every N requests.
    CLEANUP_INTERVAL = 100

    def __init__(self, app, **kwargs) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app, **kwargs)
        # Sliding-window storage: ip -> list of monotonic timestamps.
        self._general_hits: Dict[str, List[float]] = {}
        self._chat_hits: Dict[str, List[float]] = {}
        self._request_count = 0

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _get_client_ip(request: Request) -> str:
        """Extract client IP.

        Trust X-Forwarded-For only when the immediate peer is a configured
        reverse proxy. Walk the chain from the proxy side to avoid accepting a
        spoofed client-supplied leftmost address.
        """
        peer = request.client.host if request.client is not None else "unknown"
        forwarded = request.headers.get("X-Forwarded-For")
        try:
            peer_ip = ipaddress.ip_address(peer)
            trusted_peer = any(peer_ip in network for network in _TRUSTED_PROXY_NETWORKS)
        except ValueError:
            trusted_peer = False
        if forwarded and trusted_peer:
            chain = [value.strip() for value in forwarded.split(",") if value.strip()]
            for candidate in reversed(chain):
                try:
                    address = ipaddress.ip_address(candidate)
                except ValueError:
                    continue
                if not any(address in network for network in _TRUSTED_PROXY_NETWORKS):
                    return str(address)
            if chain:
                return chain[0]
        return peer

    @staticmethod
    def _prune_ip(store: Dict[str, List[float]], ip: str, now: float, window: int) -> None:
        """Drop timestamps older than ``window`` for a single IP, removing the
        key entirely when empty to keep the store compact."""
        cutoff = now - window
        fresh = [t for t in store[ip] if t > cutoff]
        if fresh:
            store[ip] = fresh
        else:
            store.pop(ip, None)

    def _global_cleanup(self, now: float) -> None:
        """Prune every IP's stale timestamps across both buckets."""
        for store, window in (
            (self._general_hits, self.GENERAL_WINDOW),
            (self._chat_hits, self.CHAT_WINDOW),
        ):
            for ip in list(store.keys()):
                self._prune_ip(store, ip, now, window)

    def _retry_after(self, hits: List[float], now: float, window: int) -> int:
        """Seconds until the oldest in-window request expires (>=1)."""
        oldest = hits[0]
        wait = oldest + window - now
        retry_after = int(wait) + 1  # ceiling for positive fractional values
        return max(retry_after, 1)

    # ------------------------------------------------------------------ #
    # Dispatch
    # ------------------------------------------------------------------ #
    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        path = request.url.path

        # Health checks & docs must never be throttled.
        if path in self.EXEMPT_PATHS:
            return await call_next(request)

        # Skip rate limiting in test environments to avoid cross-test interference.
        if os.environ.get("HOMEDOCTOR_TESTING"):
            return await call_next(request)

        now = time.monotonic()
        ip = self._get_client_ip(request)

        # Periodic global cleanup to bound memory for idle clients.
        self._request_count += 1
        if self._request_count % self.CLEANUP_INTERVAL == 0:
            self._global_cleanup(now)

        # Choose bucket + limit.
        if path.startswith("/api/chat"):
            store = self._chat_hits
            limit = self.CHAT_LIMIT
            window = self.CHAT_WINDOW
        else:
            store = self._general_hits
            limit = self.GENERAL_LIMIT
            window = self.GENERAL_WINDOW

        # Prune this IP's expired timestamps before counting.
        if ip in store:
            self._prune_ip(store, ip, now, window)

        hits = store.get(ip, [])
        if len(hits) >= limit:
            retry_after = self._retry_after(hits, now, window)
            logger.warning("RATE_LIMIT ip=%s path=%s limit=%d retry_after=%ds", ip, path, limit, retry_after)
            return JSONResponse(
                status_code=429,
                content={"detail": "请求过于频繁，请稍后再试"},
                headers={"Retry-After": str(retry_after)},
            )

        # Record the request and continue.
        store.setdefault(ip, []).append(now)
        return await call_next(request)
