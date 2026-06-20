"""Tests for the unified knowledge entity system (spec §9).

Covers:
- Entity registration + deduplication
- Search across types (q / type / category / tag)
- Relationship creation + retrieval (outgoing / incoming / both)
- AI processing pipeline (LLM mocked to return canned JSON)
- Import endpoint (text)
- Type facets
- Popular / recent listing
- View-count increment
- Entity update (PUT)
- Security: every endpoint requires authentication (401 without token)
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.database import DbAdapter
from app.knowledge_entity import (
    RELATIONSHIP_TYPES,
    create_relationship,
    get_entity,
    get_or_create_entity,
    get_related_entities,
    get_relationships,
    get_type_facets,
    increment_view_count,
    list_popular,
    list_recent,
    process_imported_content,
    register_entity,
    search_entities,
    update_entity,
)


# ---------------------------------------------------------------------------
# Entity Registry — registration & deduplication
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_register_entity_returns_id_and_persists(db: DbAdapter):
    """register_entity inserts a row and returns its id."""
    eid = await register_entity(
        db, entity_type="herb", source_table="herbs", source_id="herb-001",
        title="黄芪", summary="补气升阳",
        keywords=["补气", "微温"], tags=["补虚药"], category="补虚药",
    )
    assert eid.startswith("ke-")
    entity = await get_entity(db, eid)
    assert entity is not None
    assert entity["entity_type"] == "herb"
    assert entity["title"] == "黄芪"
    assert entity["keywords"] == ["补气", "微温"]
    assert entity["tags"] == ["补虚药"]
    assert entity["category"] == "补虚药"
    assert entity["view_count"] == 0


@pytest.mark.asyncio
async def test_register_entity_upserts_on_duplicate_source(db: DbAdapter):
    """Re-registering the same (source_table, source_id) updates the row, not duplicates."""
    eid1 = await register_entity(
        db, entity_type="herb", source_table="herbs", source_id="herb-001",
        title="黄芪", summary="original",
    )
    eid2 = await register_entity(
        db, entity_type="herb", source_table="herbs", source_id="herb-001",
        title="黄芪(更新)", summary="updated",
    )
    assert eid1 == eid2
    entity = await get_entity(db, eid1)
    assert entity["title"] == "黄芪(更新)"
    assert entity["summary"] == "updated"

    rows = await db.query(
        "SELECT COUNT(*) AS cnt FROM knowledge_entities WHERE source_id = 'herb-001'"
    )
    assert rows[0]["cnt"] == 1


@pytest.mark.asyncio
async def test_get_or_create_entity_finds_existing(db: DbAdapter):
    """get_or_create_entity returns existing id without duplicating."""
    eid1 = await get_or_create_entity(db, "herb", "herbs", "herb-002", "当归")
    eid2 = await get_or_create_entity(db, "herb", "herbs", "herb-002", "当归")
    assert eid1 == eid2


@pytest.mark.asyncio
async def test_register_entity_with_null_source_id_always_creates_new(db: DbAdapter):
    """Entities with source_id=None are always new (used by AI imports)."""
    eid1 = await register_entity(
        db, entity_type="article", source_table="ai_import", source_id=None,
        title="文章一",
    )
    eid2 = await register_entity(
        db, entity_type="article", source_table="ai_import", source_id=None,
        title="文章二",
    )
    assert eid1 != eid2


@pytest.mark.asyncio
async def test_get_entity_returns_none_for_missing(db: DbAdapter):
    assert await get_entity(db, "ke-does-not-exist") is None


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_entities_matches_title(db: DbAdapter):
    await register_entity(db, "herb", "herbs", "h1", "黄芪", summary="补气")
    await register_entity(db, "herb", "herbs", "h2", "当归", summary="补血")
    result = await search_entities(db, q="黄芪")
    titles = [e["title"] for e in result["items"]]
    assert "黄芪" in titles
    assert "当归" not in titles


@pytest.mark.asyncio
async def test_search_entities_matches_summary_keywords_tags(db: DbAdapter):
    await register_entity(db, "herb", "herbs", "h1", "人参",
                          summary="大补元气", keywords=["补气"], tags=["补虚药"])
    result = await search_entities(db, q="补气")
    assert any(e["title"] == "人参" for e in result["items"])

    result = await search_entities(db, q="补虚药")
    assert any(e["title"] == "人参" for e in result["items"])


@pytest.mark.asyncio
async def test_search_entities_facets_ignore_type_filter(db: DbAdapter):
    """Facets show all matching types even when ``type`` filter is applied."""
    await register_entity(db, "herb", "herbs", "h1", "黄芪", summary="补气")
    await register_entity(db, "formula", "formulas", "f1", "四君子汤", summary="补气")
    result = await search_entities(db, q="补气", entity_type="herb")
    assert all(e["entity_type"] == "herb" for e in result["items"])
    assert result["facets"].get("herb", 0) >= 1
    assert result["facets"].get("formula", 0) >= 1


@pytest.mark.asyncio
async def test_search_entities_filters_by_type_category_tag(db: DbAdapter):
    await register_entity(db, "herb", "herbs", "h1", "黄芪",
                          category="补虚药", tags=["补气"])
    await register_entity(db, "formula", "formulas", "f1", "四物汤",
                          category="补益剂", tags=["补血"])

    by_type = await search_entities(db, entity_type="herb")
    assert all(e["entity_type"] == "herb" for e in by_type["items"])

    by_cat = await search_entities(db, category="补虚药")
    assert all(e["category"] == "补虚药" for e in by_cat["items"])

    by_tag = await search_entities(db, tag="补气")
    assert all("补气" in e["tags"] for e in by_tag["items"])


@pytest.mark.asyncio
async def test_search_entities_pagination(db: DbAdapter):
    for i in range(5):
        await register_entity(db, "herb", "herbs", f"h{i}", f"草药{i}")
    page1 = await search_entities(db, page=1, page_size=2)
    page2 = await search_entities(db, page=2, page_size=2)
    assert len(page1["items"]) == 2
    assert len(page2["items"]) == 2
    assert page1["total"] == 5
    page1_ids = {e["id"] for e in page1["items"]}
    page2_ids = {e["id"] for e in page2["items"]}
    assert not (page1_ids & page2_ids)


# ---------------------------------------------------------------------------
# Relationship Engine
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_relationship_idempotent(db: DbAdapter):
    a = await register_entity(db, "herb", "herbs", "ha", "黄芪")
    b = await register_entity(db, "herb", "herbs", "hb", "人参")
    rid1 = await create_relationship(db, a, b, "synergy_with")
    rid2 = await create_relationship(db, a, b, "synergy_with")
    assert rid1 == rid2
    rels = await get_relationships(db, a, direction="outgoing")
    assert len(rels) == 1


@pytest.mark.asyncio
async def test_create_relationship_accepts_chinese_label(db: DbAdapter):
    """rel_type may be either code ('contains') or Chinese label ('组成')."""
    a = await register_entity(db, "formula", "formulas", "fa", "四君子汤")
    b = await register_entity(db, "herb", "herbs", "hb", "人参")
    rid = await create_relationship(db, a, b, "组成")
    rels = await get_relationships(db, a, direction="outgoing")
    assert len(rels) == 1
    assert rels[0]["relationship_type"] == "组成"
    assert rels[0]["label"] == "组成"


@pytest.mark.asyncio
async def test_get_relationships_both_directions(db: DbAdapter):
    """'both' returns outgoing + incoming with direction tag."""
    a = await register_entity(db, "herb", "herbs", "ha", "黄芪")
    b = await register_entity(db, "herb", "herbs", "hb", "人参")
    await create_relationship(db, a, b, "synergy_with")
    rels = await get_relationships(db, a, direction="both")
    assert len(rels) == 1
    assert rels[0]["direction"] == "outgoing"
    rels_b = await get_relationships(db, b, direction="both")
    assert len(rels_b) == 1
    assert rels_b[0]["direction"] == "incoming"


@pytest.mark.asyncio
async def test_get_related_entities_filter_by_type(db: DbAdapter):
    a = await register_entity(db, "herb", "herbs", "ha", "附子")
    b = await register_entity(db, "herb", "herbs", "hb", "半夏")
    c = await register_entity(db, "symptom", "symptom", "sc", "气虚")
    await create_relationship(db, a, b, "contraindicated")
    await create_relationship(db, a, c, "treats")

    all_related = await get_related_entities(db, a)
    related_ids = {e["id"] for e in all_related}
    assert b in related_ids
    assert c in related_ids

    treated = await get_related_entities(db, a, rel_type="treats")
    assert all(e["id"] == c for e in treated)


# ---------------------------------------------------------------------------
# AI Processing Pipeline — LLM mocked
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_process_imported_content_with_mocked_llm(db: DbAdapter):
    """When LLM returns structured JSON, an enriched entity + relationships are created."""
    fake_analysis = {
        "entity_type": "article",
        "category": "补气药",
        "summary": "黄芪补气升阳的介绍",
        "keywords": ["补气", "升阳"],
        "tags": ["养生"],
        "extracted_entities": [
            {"type": "herb", "name": "黄芪", "context": "黄芪为补气要药"},
            {"type": "symptom", "name": "气虚", "context": "主治气虚乏力"},
        ],
        "relationships": [
            {"source": "黄芪", "target": "气虚", "type": "treats"},
        ],
    }

    with patch(
        "app.knowledge_entity._call_llm_for_analysis",
        new_callable=AsyncMock,
        return_value=fake_analysis,
    ):
        result = await process_imported_content(
            db, title="黄芪补气功效", content="黄芪为补气要药，主治气虚乏力等症。",
        )

    assert result["ai_analyzed"] is True
    entity = result["entity"]
    assert entity["entity_type"] == "article"
    assert entity["category"] == "补气药"
    assert "补气" in entity["keywords"]
    assert "养生" in entity["tags"]
    assert len(result["linked_entities"]) == 2
    assert len(result["relationships_created"]) == 1


@pytest.mark.asyncio
async def test_process_imported_content_falls_back_without_llm(db: DbAdapter):
    """When LLM is unavailable, the entity is still created as a plain article."""
    with patch(
        "app.knowledge_entity._call_llm_for_analysis",
        new_callable=AsyncMock,
        return_value={},
    ):
        result = await process_imported_content(
            db, title="普通养生文章", content="这是一篇关于日常饮食的养生文章。",
        )
    assert result["ai_analyzed"] is False
    entity = result["entity"]
    assert entity["entity_type"] == "article"
    assert result["linked_entities"] == []
    assert result["relationships_created"] == []


@pytest.mark.asyncio
async def test_process_imported_content_rejects_empty_inputs(db: DbAdapter):
    with pytest.raises(ValueError):
        await process_imported_content(db, title="", content="x")
    with pytest.raises(ValueError):
        await process_imported_content(db, title="x", content="")


# ---------------------------------------------------------------------------
# Facets & listings
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_type_facets(db: DbAdapter):
    await register_entity(db, "herb", "herbs", "h1", "黄芪")
    await register_entity(db, "herb", "herbs", "h2", "当归")
    await register_entity(db, "formula", "formulas", "f1", "四物汤")
    facets = await get_type_facets(db)
    assert facets.get("herb") == 2
    assert facets.get("formula") == 1


@pytest.mark.asyncio
async def test_list_popular_and_recent(db: DbAdapter):
    a = await register_entity(db, "herb", "herbs", "h1", "黄芪")
    b = await register_entity(db, "herb", "herbs", "h2", "当归")
    await increment_view_count(db, a)
    await increment_view_count(db, a)
    await increment_view_count(db, b)

    popular = await list_popular(db, limit=10)
    assert popular[0]["id"] == a
    assert popular[0]["view_count"] == 2
    assert popular[1]["id"] == b

    recent = await list_recent(db, limit=10)
    recent_ids = [e["id"] for e in recent]
    assert a in recent_ids and b in recent_ids


@pytest.mark.asyncio
async def test_update_entity_partial(db: DbAdapter):
    eid = await register_entity(db, "herb", "herbs", "h1", "黄芪", summary="old")
    updated = await update_entity(db, eid, summary="new summary", tags=["updated"])
    assert updated["summary"] == "new summary"
    assert updated["tags"] == ["updated"]
    assert updated["title"] == "黄芪"


@pytest.mark.asyncio
async def test_update_entity_returns_none_for_missing(db: DbAdapter):
    result = await update_entity(db, "ke-nope", summary="x")
    assert result is None


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_api_search_requires_auth(raw_client: AsyncClient):
    resp = await raw_client.get("/api/knowledge-hub/search")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_api_search_returns_entities(client: AsyncClient, auth_headers: dict):
    await client.post(
        "/api/knowledge-hub/import",
        headers=auth_headers,
        json={"title": "测试文章", "content": "一篇关于黄芪补气的文章"},
    )
    resp = await client.get(
        "/api/knowledge-hub/search?q=测试", headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert any(e["title"] == "测试文章" for e in data["items"])
    assert "facets" in data


@pytest.mark.asyncio
async def test_api_types_returns_facets(client: AsyncClient, auth_headers: dict):
    await client.post(
        "/api/knowledge-hub/import",
        headers=auth_headers,
        json={"title": "x", "content": "y"},
    )
    resp = await client.get("/api/knowledge-hub/types", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "facets" in data
    assert data["total"] >= 1


@pytest.mark.asyncio
async def test_api_import_creates_entity(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/knowledge-hub/import",
        headers=auth_headers,
        json={"title": "测试导入", "content": "这是一段测试内容"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["entity"]["title"] == "测试导入"
    assert "ai_analyzed" in data


@pytest.mark.asyncio
async def test_api_entity_detail_404(client: AsyncClient, auth_headers: dict):
    resp = await client.get(
        "/api/knowledge-hub/entities/ke-nope", headers=auth_headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_api_entity_detail_returns_relationships(client: AsyncClient, auth_headers: dict):
    create = await client.post(
        "/api/knowledge-hub/import",
        headers=auth_headers,
        json={"title": "文章A", "content": "内容A"},
    )
    entity_id = create.json()["entity"]["id"]

    resp = await client.get(
        f"/api/knowledge-hub/entities/{entity_id}", headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == entity_id
    assert "relationships" in data
    assert isinstance(data["relationships"], list)


@pytest.mark.asyncio
async def test_api_relationships_endpoint(client: AsyncClient, auth_headers: dict):
    create = await client.post(
        "/api/knowledge-hub/import",
        headers=auth_headers,
        json={"title": "实体X", "content": "内容X"},
    )
    entity_id = create.json()["entity"]["id"]

    resp = await client.get(
        f"/api/knowledge-hub/entities/{entity_id}/relationships",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["entity_id"] == entity_id
    assert "items" in data


@pytest.mark.asyncio
async def test_api_view_increments_count(client: AsyncClient, auth_headers: dict):
    create = await client.post(
        "/api/knowledge-hub/import",
        headers=auth_headers,
        json={"title": "计数测试", "content": "内容"},
    )
    entity_id = create.json()["entity"]["id"]
    assert create.json()["entity"]["view_count"] == 0

    r1 = await client.post(
        f"/api/knowledge-hub/entities/{entity_id}/view", headers=auth_headers
    )
    assert r1.status_code == 200
    assert r1.json()["view_count"] == 1

    r2 = await client.post(
        f"/api/knowledge-hub/entities/{entity_id}/view", headers=auth_headers
    )
    assert r2.json()["view_count"] == 2


@pytest.mark.asyncio
async def test_api_update_entity(client: AsyncClient, auth_headers: dict):
    create = await client.post(
        "/api/knowledge-hub/import",
        headers=auth_headers,
        json={"title": "原始", "content": "内容"},
    )
    entity_id = create.json()["entity"]["id"]

    resp = await client.put(
        f"/api/knowledge-hub/entities/{entity_id}",
        headers=auth_headers,
        json={"summary": "更新摘要", "tags": ["新标签"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["summary"] == "更新摘要"
    assert data["tags"] == ["新标签"]


@pytest.mark.asyncio
async def test_api_popular_and_recent(client: AsyncClient, auth_headers: dict):
    await client.post(
        "/api/knowledge-hub/import",
        headers=auth_headers,
        json={"title": "P1", "content": "内容"},
    )

    pop_resp = await client.get("/api/knowledge-hub/popular", headers=auth_headers)
    assert pop_resp.status_code == 200
    assert "items" in pop_resp.json()

    recent_resp = await client.get("/api/knowledge-hub/recent", headers=auth_headers)
    assert recent_resp.status_code == 200
    assert "items" in recent_resp.json()


@pytest.mark.asyncio
async def test_api_relationship_types(client: AsyncClient, auth_headers: dict):
    resp = await client.get(
        "/api/knowledge-hub/relationship-types", headers=auth_headers
    )
    assert resp.status_code == 200
    types = resp.json()["types"]
    assert "contains" in types
    assert types["contains"] == "组成"
    assert types["contraindicated"] == "禁忌"


@pytest.mark.asyncio
async def test_api_create_relationship_endpoint(client: AsyncClient, auth_headers: dict):
    """Manually creating a relationship via API."""
    c1 = await client.post(
        "/api/knowledge-hub/import",
        headers=auth_headers,
        json={"title": "实体A", "content": "内容A"},
    )
    c2 = await client.post(
        "/api/knowledge-hub/import",
        headers=auth_headers,
        json={"title": "实体B", "content": "内容B"},
    )
    a_id = c1.json()["entity"]["id"]
    b_id = c2.json()["entity"]["id"]

    resp = await client.post(
        f"/api/knowledge-hub/entities/{a_id}/relationships",
        headers=auth_headers,
        json={
            "source_entity_id": a_id,
            "target_entity_id": b_id,
            "relationship_type": "synergy_with",
        },
    )
    assert resp.status_code == 201
    assert "relationship_id" in resp.json()


@pytest.mark.asyncio
async def test_api_create_relationship_validates_entity_id(client: AsyncClient, auth_headers: dict):
    """source or target must equal the path entity_id."""
    c1 = await client.post(
        "/api/knowledge-hub/import",
        headers=auth_headers,
        json={"title": "A", "content": "x"},
    )
    c2 = await client.post(
        "/api/knowledge-hub/import",
        headers=auth_headers,
        json={"title": "B", "content": "x"},
    )
    c3 = await client.post(
        "/api/knowledge-hub/import",
        headers=auth_headers,
        json={"title": "C", "content": "x"},
    )
    a_id = c1.json()["entity"]["id"]
    b_id = c2.json()["entity"]["id"]
    c_id = c3.json()["entity"]["id"]

    # Neither source nor target equals path entity_id (c_id) → 422
    resp = await client.post(
        f"/api/knowledge-hub/entities/{c_id}/relationships",
        headers=auth_headers,
        json={
            "source_entity_id": a_id,
            "target_entity_id": b_id,
            "relationship_type": "synergy_with",
        },
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Seed script — exercises the full registration pipeline
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_seed_script_end_to_end(db: DbAdapter):
    """The seed pipeline registers herbs/formulas/therapies + 4 relationship types.

    The conftest seeds only 黄芪/当归/甘草, none of which pair up under 十八反.
    We insert 甘草's 十八反 partner (甘遂) and the 附子/半夏 pair so the
    contraindicated-edge builder has matching herbs to link.
    """
    contraindicated_herbs = [
        ("herb-test-gansui", "甘遂", "泻水逐饮", "水肿胀满,痰饮积聚", "峻下逐水药"),
        ("herb-test-fuzi", "附子", "回阳救逆", "亡阳证,阳虚证", "温里药"),
        ("herb-test-banxia", "半夏", "燥湿化痰", "湿痰寒痰,呕吐", "化痰药"),
    ]
    for hid, name, efficacy, indications, category in contraindicated_herbs:
        await db.execute(
            """INSERT OR IGNORE INTO herbs (id, name, efficacy, indications, category)
               VALUES (?, ?, ?, ?, ?)""",
            (hid, name, efficacy, indications, category),
        )

    from scripts.seed_knowledge_entities import (
        seed_herbs,
        seed_formulas,
        seed_therapies,
        create_herb_treats_symptom_relationships,
        create_therapy_indicated_for_relationships,
        create_contraindicated_relationships,
        create_interacts_with_relationships,
    )

    herb_map = await seed_herbs(db)
    formula_map, contains_n = await seed_formulas(db, herb_map)
    therapy_map, therapy_n = await seed_therapies(db)
    treats_n = await create_herb_treats_symptom_relationships(db, herb_map)
    indicated_n = await create_therapy_indicated_for_relationships(db, therapy_map)
    contra_n = await create_contraindicated_relationships(db, herb_map)
    interact_n = await create_interacts_with_relationships(db, herb_map)

    assert len(herb_map) >= 3, "expected at least 3 herbs seeded by conftest"
    assert "甘草" in herb_map, "甘草 should be seeded (conftest)"
    assert "甘遂" in herb_map, "甘遂 should be seeded (test setup)"
    assert contains_n >= 1, "expected formula-contains-herb edges"
    assert therapy_n >= 1, "expected at least 1 therapy"
    assert treats_n >= 1, "expected herb-treats-symptom edges"
    assert indicated_n >= 1, "expected therapy-indicated_for edges"
    assert contra_n >= 1, "expected contraindicated edges from 十八反/十九畏"
    assert interact_n >= 1, "expected herb-drug interaction edges"


# ---------------------------------------------------------------------------
# JSON parsing helper
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw,expected_keys",
    [
        ('{"entity_type": "herb"}', {"entity_type"}),
        ('```json\n{"entity_type": "herb"}\n```', {"entity_type"}),
        ('some commentary\n{"entity_type": "herb"}\nmore', {"entity_type"}),
        ("not json at all", set()),
        ("", set()),
    ],
)
def test_parse_llm_json_strips_wrappers(raw, expected_keys):
    from app.knowledge_entity import _parse_llm_json
    parsed = _parse_llm_json(raw)
    assert set(parsed.keys()) == expected_keys
