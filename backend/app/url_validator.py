"""URL validation — SSRF protection for external URL fetching.

Blocks private IPs, loopback, link-local, IPv4-mapped IPv6, non-http schemes,
and ports other than 80/443. Used for per-hop validation inside
:func:`app.knowledge_parser.safe_fetch` — every redirect hop must pass.
"""

from __future__ import annotations


import logging

logger = logging.getLogger(__name__)
import ipaddress
import socket
from urllib.parse import urlparse

PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("::/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("::ffff:0:0/96"),
]

ALLOWED_PORTS = frozenset({80, 443})


def _is_private_ip(ip) -> bool:
    """True if the address (or its IPv4-mapped form) is in a blocked network."""
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None and any(mapped in net for net in PRIVATE_NETWORKS):
        return True
    return any(ip in net for net in PRIVATE_NETWORKS)


def validate_external_url(url: str) -> bool:
    """Return True if URL is safe to fetch (not internal/private)."""
    if not url or not url.strip():
        return False

    parsed = urlparse(url.strip())

    if parsed.scheme not in ("http", "https"):
        return False

    hostname = parsed.hostname
    if not hostname:
        return False

    if hostname in ("localhost", "ip6-localhost") or hostname.endswith(".localhost"):
        return False

    try:
        port = parsed.port
    except ValueError:
        return False
    if port is not None and port not in ALLOWED_PORTS:
        return False

    try:
        addr_info = socket.getaddrinfo(hostname, None)
        for family, _, _, _, sockaddr in addr_info:
            ip = ipaddress.ip_address(sockaddr[0])
            if _is_private_ip(ip):
                return False
    except (socket.gaierror, ValueError):
        return False

    return True
