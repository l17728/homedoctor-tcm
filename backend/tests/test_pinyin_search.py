"""Tests for pinyin search (spec §2.4 — 拼音搜索)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.pinyin_data import HERB_PINYIN, to_pinyin, to_pinyin_abbrev


# ---------------------------------------------------------------------------
# Unit tests for pinyin module
# ---------------------------------------------------------------------------

def test_to_pinyin_huangqi():
    """黄芪 → huangqi."""
    assert to_pinyin("黄芪") == "huangqi"


def test_to_pinyin_gancao():
    """甘草 → gancao."""
    assert to_pinyin("甘草") == "gancao"


def test_to_pinyin_danggui():
    """当归 → danggui."""
    assert to_pinyin("当归") == "danggui"


def test_to_pinyin_abbrev_hq():
    """黄芪 → hq (abbreviation)."""
    assert to_pinyin_abbrev("黄芪") == "hq"


def test_to_pinyin_abbrev_dg():
    """当归 → dg (abbreviation)."""
    assert to_pinyin_abbrev("当归") == "dg"


def test_to_pinyin_passthrough_unknown():
    """Unknown characters pass through unchanged."""
    assert to_pinyin("a") == "a"
    assert to_pinyin_abbrev("a") == ""


def test_herb_pinyin_covers_common_herbs():
    """Common herb characters should be in the mapping."""
    for char in "黄芪当归甘草白术":
        assert char in HERB_PINYIN, f"Missing pinyin for '{char}'"


# ---------------------------------------------------------------------------
# Integration tests via API
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_chinese_huangqi(client: AsyncClient):
    """Search '黄芪' (Chinese) → found."""
    response = await client.get("/api/herbs/search", params={"q": "黄芪"})
    assert response.status_code == 200
    data = response.json()
    names = [h["name"] for h in data["items"]]
    assert "黄芪" in names


@pytest.mark.asyncio
async def test_search_pinyin_full_huangqi(client: AsyncClient):
    """Search 'huangqi' (full pinyin) → found 黄芪."""
    response = await client.get("/api/herbs/search", params={"q": "huangqi"})
    assert response.status_code == 200
    data = response.json()
    names = [h["name"] for h in data["items"]]
    assert "黄芪" in names


@pytest.mark.asyncio
async def test_search_pinyin_abbrev_hq(client: AsyncClient):
    """Search 'hq' (abbreviation) → found 黄芪."""
    response = await client.get("/api/herbs/search", params={"q": "hq"})
    assert response.status_code == 200
    data = response.json()
    names = [h["name"] for h in data["items"]]
    assert "黄芪" in names


@pytest.mark.asyncio
async def test_search_pinyin_gancao(client: AsyncClient):
    """Search 'gancao' (full pinyin) → found 甘草."""
    response = await client.get("/api/herbs/search", params={"q": "gancao"})
    assert response.status_code == 200
    data = response.json()
    names = [h["name"] for h in data["items"]]
    assert "甘草" in names


@pytest.mark.asyncio
async def test_search_pinyin_abbrev_gc(client: AsyncClient):
    """Search 'gc' (abbreviation) → found 甘草."""
    response = await client.get("/api/herbs/search", params={"q": "gc"})
    assert response.status_code == 200
    data = response.json()
    names = [h["name"] for h in data["items"]]
    assert "甘草" in names


@pytest.mark.asyncio
async def test_search_pinyin_abbrev_dg(client: AsyncClient):
    """Search 'dg' (abbreviation) → found 当归."""
    response = await client.get("/api/herbs/search", params={"q": "dg"})
    assert response.status_code == 200
    data = response.json()
    names = [h["name"] for h in data["items"]]
    assert "当归" in names


@pytest.mark.asyncio
async def test_search_pinyin_danggui(client: AsyncClient):
    """Search 'danggui' (full pinyin) → found 当归."""
    response = await client.get("/api/herbs/search", params={"q": "danggui"})
    assert response.status_code == 200
    data = response.json()
    names = [h["name"] for h in data["items"]]
    assert "当归" in names


@pytest.mark.asyncio
async def test_search_nonexistent_pinyin(client: AsyncClient):
    """Search 'zzzzz' → not found."""
    response = await client.get("/api/herbs/search", params={"q": "zzzzz"})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_search_case_insensitive_pinyin(client: AsyncClient):
    """Search 'HUANGQI' (uppercase) → found 黄芪."""
    response = await client.get("/api/herbs/search", params={"q": "HUANGQI"})
    assert response.status_code == 200
    data = response.json()
    names = [h["name"] for h in data["items"]]
    assert "黄芪" in names
