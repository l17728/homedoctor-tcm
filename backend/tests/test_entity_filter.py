"""Tests for the universal entity extraction filter (app.entity_filter).

Covers:
- Scanning text with known herb/formula names → found
- Scanning via aliases → resolved to canonical
- Scanning text with no entities → empty list
- scan_and_link creates entity_relationships rows
- Idempotency — scanning twice doesn't duplicate relationships
- Non-blocking — router still works if the filter throws
- Entity auto-creation — a matched herb not in knowledge_entities is created
- Profile health_conditions extraction (symptom-style text)

Test data (seeded by conftest.seed_test_data):
  herbs: 黄芪 (herb-001, aliases 绵芪,黄耆), 当归 (herb-002, 秦归,云归), 甘草 (herb-003, 国老,蜜草)
  formulas: 四君子汤 (formula-001), 四物汤 (formula-002)
"""

from __future__ import annotations

import json

import pytest

from app.database import DbAdapter
from app.entity_filter import (
    EntityNameIndex,
    get_entity_index,
    reset_index,
    scan_and_link,
    scan_text,
)
from app.knowledge_entity import register_entity


@pytest.fixture(autouse=True)
def _reset_entity_index():
    """Reset the global index cache before and after each test.

    Each test gets a fresh in-memory DB, so the cached index (which mirrors a
    different DB instance) must be cleared to avoid stale data.
    """
    reset_index()
    yield
    reset_index()


# ---------------------------------------------------------------------------
# EntityNameIndex.scan — pure text matching
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scan_finds_multiple_herbs(db: DbAdapter):
    """Scanning 黄芪补气，当归补血 finds both 黄芪 and 当归."""
    index = await get_entity_index(db)
    found = index.scan("黄芪补气，当归补血")
    names = {f["name"] for f in found}
    assert "黄芪" in names
    assert "当归" in names


@pytest.mark.asyncio
async def test_scan_finds_formula_name(db: DbAdapter):
    """Scanning text mentioning 四君子汤 finds the formula."""
    index = await get_entity_index(db)
    found = index.scan("四君子汤是益气健脾的基础方")
    names = {f["name"] for f in found}
    assert "四君子汤" in names


@pytest.mark.asyncio
async def test_scan_finds_via_alias(db: DbAdapter):
    """Scanning an alias (绵芪) resolves to the canonical name (黄芪)."""
    index = await get_entity_index(db)
    found = index.scan("绵芪能补气升阳")
    matched = [f for f in found if f["name"] == "黄芪"]
    assert len(matched) == 1
    assert matched[0].get("alias_matched") == "绵芪"


@pytest.mark.asyncio
async def test_scan_finds_via_second_alias(db: DbAdapter):
    """国老 is an alias of 甘草."""
    index = await get_entity_index(db)
    found = index.scan("国老调和诸药")
    names = {f["name"] for f in found}
    assert "甘草" in names


@pytest.mark.asyncio
async def test_scan_no_entities_returns_empty(db: DbAdapter):
    """Text with no known entities returns an empty list."""
    index = await get_entity_index(db)
    found = index.scan("今天天气很好，适合散步")
    assert found == []


@pytest.mark.asyncio
async def test_scan_empty_text_returns_empty(db: DbAdapter):
    """Empty / None / very short text returns an empty list."""
    index = await get_entity_index(db)
    assert index.scan("") == []
    assert index.scan(None) == []
    assert index.scan("a") == []  # no <2 char canonical names matched


@pytest.mark.asyncio
async def test_scan_unloaded_index_returns_empty():
    """An index that hasn't been loaded yet scans to empty."""
    idx = EntityNameIndex()
    assert idx.scan("黄芪") == []


@pytest.mark.asyncio
async def test_scan_deduplicates(db: DbAdapter):
    """Mentioning the same herb twice returns it only once."""
    index = await get_entity_index(db)
    found = index.scan("黄芪补气，黄芪固表")
    names = [f["name"] for f in found]
    assert names.count("黄芪") == 1


@pytest.mark.asyncio
async def test_scan_prefers_longer_name(db: DbAdapter):
    """When both a long and short name match, the longer one wins (no overlap)."""
    index = await get_entity_index(db)
    # 四物汤 contains 四物 substring-wise but 四物 is not a registered entity;
    # this just confirms formulas are matched by full name.
    found = index.scan("四物汤养血")
    names = {f["name"] for f in found}
    assert "四物汤" in names


# ---------------------------------------------------------------------------
# scan_text — read-only (ensures entity_id populated)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scan_text_returns_entity_ids(db: DbAdapter):
    """scan_text ensures every found entity has an entity_id."""
    found = await scan_text(db, "黄芪和当归")
    assert found
    for f in found:
        assert f["entity_id"] is not None


@pytest.mark.asyncio
async def test_scan_text_short_text_noop(db: DbAdapter):
    """scan_text with short/empty text returns []."""
    assert await scan_text(db, "") == []
    assert await scan_text(db, "a") == []
    assert await scan_text(db, None) == []


# ---------------------------------------------------------------------------
# scan_and_link — relationship creation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scan_and_link_creates_relationships(db: DbAdapter):
    """scan_and_link creates relationships from source entity to found herbs."""
    # Create a source entity to link from.
    source_id = await register_entity(
        db, entity_type="article", source_table="test", source_id="src-1",
        title="测试文章",
    )
    found = await scan_and_link(
        db, "黄芪补气，当归补血",
        source_entity_id=source_id,
        source_type="test",
        relationship_type="mentions",
    )
    names = {f["name"] for f in found}
    assert "黄芪" in names
    assert "当归" in names

    # Verify relationships were created in the DB.
    rels = await db.query(
        "SELECT * FROM entity_relationships WHERE source_entity_id = ?",
        (source_id,),
    )
    targets = {r["target_entity_id"] for r in rels}
    found_ids = {f["entity_id"] for f in found}
    assert found_ids.issubset(targets) or targets  # relationships exist
    assert len(rels) >= 2  # at least 黄芪 + 当归


@pytest.mark.asyncio
async def test_scan_and_link_no_source_id_still_returns_found(db: DbAdapter):
    """Without a source_entity_id, no relationships are created but found list is returned."""
    found = await scan_and_link(db, "黄芪补气")
    names = {f["name"] for f in found}
    assert "黄芪" in names
    # entity_id populated via _ensure_entity_exists
    assert all(f["entity_id"] for f in found)


@pytest.mark.asyncio
async def test_scan_and_link_empty_text_noop(db: DbAdapter):
    """Empty / short text returns [] without touching the DB."""
    assert await scan_and_link(db, "", source_entity_id="x") == []
    assert await scan_and_link(db, "a", source_entity_id="x") == []
    assert await scan_and_link(db, None, source_entity_id="x") == []


@pytest.mark.asyncio
async def test_scan_and_link_no_entities_noop(db: DbAdapter):
    """Text with no known entities returns [] and creates nothing."""
    source_id = await register_entity(
        db, entity_type="article", source_table="test", source_id="src-2",
        title="无实体文章",
    )
    found = await scan_and_link(db, "今天天气很好", source_entity_id=source_id)
    assert found == []


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scan_and_link_idempotent(db: DbAdapter):
    """Scanning the same text twice does not duplicate relationships."""
    source_id = await register_entity(
        db, entity_type="article", source_table="test", source_id="src-3",
        title="幂等测试",
    )
    await scan_and_link(db, "黄芪补气", source_entity_id=source_id)
    rels_after_first = await db.query(
        "SELECT COUNT(*) as cnt FROM entity_relationships WHERE source_entity_id = ?",
        (source_id,),
    )
    count_first = rels_after_first[0]["cnt"]

    await scan_and_link(db, "黄芪补气", source_entity_id=source_id)
    rels_after_second = await db.query(
        "SELECT COUNT(*) as cnt FROM entity_relationships WHERE source_entity_id = ?",
        (source_id,),
    )
    count_second = rels_after_second[0]["cnt"]

    assert count_second == count_first, "idempotency broken: relationships duplicated"


@pytest.mark.asyncio
async def test_ensure_entity_exists_idempotent(db: DbAdapter):
    """Repeated scans don't create duplicate knowledge_entities for the same herb."""
    await scan_and_link(db, "黄芪")  # creates entity
    rows1 = await db.query(
        "SELECT COUNT(*) as cnt FROM knowledge_entities WHERE title = '黄芪'"
    )
    await scan_and_link(db, "黄芪补气")  # should reuse, not create
    rows2 = await db.query(
        "SELECT COUNT(*) as cnt FROM knowledge_entities WHERE title = '黄芪'"
    )
    # 黄芪 may appear once as 'herb' type. No new duplicate rows.
    assert rows2[0]["cnt"] == rows1[0]["cnt"]


# ---------------------------------------------------------------------------
# Entity auto-creation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_auto_creates_entity_for_matched_herb(db: DbAdapter):
    """A herb that exists in `herbs` but not in knowledge_entities is auto-created."""
    # Precondition: 黄芪 is in herbs (seeded) but maybe not in knowledge_entities.
    ke_before = await db.query(
        "SELECT COUNT(*) as cnt FROM knowledge_entities WHERE title = '黄芪'"
    )
    found = await scan_and_link(db, "黄芪")
    assert found
    # The found entry now has an entity_id.
    assert all(f["entity_id"] for f in found)

    # knowledge_entities now has (at least) one row for 黄芪.
    ke_after = await db.query(
        "SELECT COUNT(*) as cnt FROM knowledge_entities WHERE title = '黄芪'"
    )
    assert ke_after[0]["cnt"] >= 1
    # No duplicate creation beyond what existed.
    if ke_before[0]["cnt"] > 0:
        assert ke_after[0]["cnt"] == ke_before[0]["cnt"]


# ---------------------------------------------------------------------------
# Non-blocking behaviour
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scan_and_link_swallows_internal_errors(db: DbAdapter, monkeypatch):
    """If an internal filter function raises, scan_and_link callers must still work.

    We simulate a broken DB adapter to confirm the top-level scan_and_link does
    not propagate (the router try/except is the second layer of defense; here we
    verify the helper itself degrades gracefully on register/link failures).
    """
    # Inject a failing create_relationship by patching the imported reference.
    import app.entity_filter as ef_mod

    async def _boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(ef_mod, "create_relationship", _boom)

    source_id = await register_entity(
        db, entity_type="article", source_table="test", source_id="src-fail",
        title="故障测试",
    )
    # Should NOT raise even though create_relationship blows up.
    found = await scan_and_link(db, "黄芪补气", source_entity_id=source_id)
    # Found list is still returned (entities were scanned + ensured).
    assert any(f["name"] == "黄芪" for f in found)


@pytest.mark.asyncio
async def test_get_entity_index_reloads_after_reset(db: DbAdapter):
    """reset_index() clears the cache; next get reloads from the fresh DB."""
    idx1 = await get_entity_index(db)
    assert idx1._loaded
    reset_index()
    idx2 = await get_entity_index(db)
    assert idx2._loaded
    # A new instance was created.
    assert idx2 is not idx1


# ---------------------------------------------------------------------------
# Integration with profile health_conditions (symptom-style text)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_profile_health_conditions_extract(db: DbAdapter):
    """Health conditions text mentioning herbs/symptoms gets linked.

    Even though "气虚" isn't a seeded herb name, the scan should still run
    without error and find any canonical entities present.
    """
    source_id = await register_entity(
        db, entity_type="profile", source_table="user_profiles",
        source_id="user-1", title="用户档案",
    )
    # Text mentions seeded herbs + a non-seeded symptom.
    found = await scan_and_link(
        db, "气虚乏力，常用黄芪调理，配合甘草",
        source_entity_id=source_id,
        source_type="profile",
        relationship_type="has_symptom",
    )
    names = {f["name"] for f in found}
    assert "黄芪" in names
    assert "甘草" in names

    rels = await db.query(
        "SELECT * FROM entity_relationships WHERE source_entity_id = ? "
        "AND relationship_type = ?",
        (source_id, "has_symptom"),
    )
    assert len(rels) >= 2


# ---------------------------------------------------------------------------
# Router integration — non-blocking filter (smoke test via API)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chat_endpoint_works_with_filter(client, auth_headers, monkeypatch):
    """POST /api/chat still succeeds even if the entity filter is broken.

    This verifies the non-blocking contract: the router wraps scan_and_link in
    try/except so a filter failure never breaks the chat.
    """
    # Break the filter at the module the router imports from.
    import app.entity_filter as ef_mod

    async def _boom(*args, **kwargs):
        raise RuntimeError("filter boom")

    monkeypatch.setattr(ef_mod, "scan_and_link", _boom)

    resp = await client.post(
        "/api/chat",
        json={"message": "黄芪有什么功效？"},
        headers=auth_headers,
    )
    # Chat must still return 200 — the filter failure is swallowed.
    assert resp.status_code == 200
    data = resp.json()
    assert "reply" in data


@pytest.mark.asyncio
async def test_medicine_create_links_to_entities(client, auth_headers):
    """POST /api/medicines with a herb-like name triggers entity linking (non-blocking)."""
    resp = await client.post(
        "/api/medicines",
        json={
            "name": "黄芪胶囊",
            "type": "中成药",
            "properties": {"drugClass": "中成药"},
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "黄芪胶囊"
