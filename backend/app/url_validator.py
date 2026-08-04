"""URL validation — SSRF protection for external URL fetching.

Blocks private IPs, loopback, link-local, and non-http schemes.
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
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


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

    if hostname in ("localhost", "ip6-localhost"):
        return False

    try:
        addr_info = socket.getaddrinfo(hostname, None)
        for family, _, _, _, sockaddr in addr_info:
            ip = ipaddress.ip_address(sockaddr[0])
            for network in PRIVATE_NETWORKS:
                if ip in network:
                    return False
    except (socket.gaierror, ValueError):
        return False

    return True
