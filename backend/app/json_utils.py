"""Shared JSON utility — single parse function used across all modules."""

from __future__ import annotations


import logging

logger = logging.getLogger(__name__)
import json
from typing import Any


def parse_json(raw: Any, default: Any) -> Any:
    """Parse JSON from string, dict, list, or None. Returns default on failure."""
    if isinstance(raw, (list, dict)):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return default
    return default
