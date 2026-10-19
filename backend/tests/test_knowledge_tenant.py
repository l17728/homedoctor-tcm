"""Tenant isolation tests for knowledge_entities / entity_relationships.

Covers the security review findings:
- Entities imported by user A (tenant-scoped) are invisible to user B:
  search / browse / list / detail / PUT / relationship creation
- Global entities (tenant_id IS NULL) are visible to everyone
- Global entity writes (update / archive) are admin-only; tenant entities
  are owner-only
- User-curated relationships between global entities are tenant-scoped and
  hidden from other families
- Another family's private "person" entities never leak through the hub,
  while the personal-knowledge API keeps working for the owning user
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.database import DbAdapter
from app.knowledge_entity import register_entity


PRIVATE_TITLE = "A家的私有养生笔记"
GLOBAL_TITLE = "全局共享测试药材"
PERSON_TITLE = "别人家的个人健康档案"


async def _import_private(client: AsyncClient, headers: dict, title: str) -> str:
    resp = await client.post(
        "/api/knowledge-hub/import",
        headers=headers,
        json={"title": title, "content": f"{title}的正文：黄芪补气升阳，固表止汗。"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["entity"]["id"]


async def _seed_global(db: DbAdapter, title: str, source_id: str) -> str:
    return await register_entity(
        db, "herb", "herbs", source_id, title, summary="全局实体摘要",
    )


# ---------------------------------------------------------------------------
# Private entities: invisible to other families
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_private_entity_invisible_in_search_to_other_family(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    private_id = await _import_private(client, auth_headers, PRIVATE_TITLE)

    resp_a = await client.get(
        "/api/knowledge-hub/search", params={"q": PRIVATE_TITLE}, headers=auth_headers
    )
    assert resp_a.status_code == 200
    assert any(e["id"] == private_id for e in resp_a.json()["items"])

    resp_b = await client.get(
        "/api/knowledge-hub/search", params={"q": PRIVATE_TITLE}, headers=second_user_headers
    )
    assert resp_b.status_code == 200
    data = resp_b.json()
    assert all(e["id"] != private_id for e in data["items"])
    assert all(e["title"] != PRIVATE_TITLE for e in data["items"])


@pytest.mark.asyncio
async def test_private_entity_invisible_in_browse_and_listings_to_other_family(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    private_id = await _import_private(client, auth_headers, PRIVATE_TITLE)

    browse_b = await client.get(
        "/api/knowledge/browse", params={"type": "article"}, headers=second_user_headers
    )
    assert browse_b.status_code == 200
    assert all(item["id"] != private_id for item in browse_b.json()["items"])

    browse_a = await client.get(
        "/api/knowledge/browse", params={"type": "article"}, headers=auth_headers
    )
    assert any(item["id"] == private_id for item in browse_a.json()["items"])

    recent_b = await client.get("/api/knowledge-hub/recent", headers=second_user_headers)
    assert all(e["id"] != private_id for e in recent_b.json()["items"])

    types_b = await client.get("/api/knowledge-hub/types", headers=second_user_headers)
    total_b_before = types_b.json()["total"]

    await _import_private(client, auth_headers, "A家第二篇私有文章")
    types_b_after = (
        await client.get("/api/knowledge-hub/types", headers=second_user_headers)
    ).json()["total"]
    assert types_b_after == total_b_before


@pytest.mark.asyncio
async def test_private_entity_detail_and_put_404_for_other_family(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    private_id = await _import_private(client, auth_headers, PRIVATE_TITLE)

    detail_b = await client.get(
        f"/api/knowledge-hub/entities/{private_id}", headers=second_user_headers
    )
    assert detail_b.status_code == 404

    put_b = await client.put(
        f"/api/knowledge-hub/entities/{private_id}",
        headers=second_user_headers,
        json={"summary": "B试图篡改", "status": "archived"},
    )
    assert put_b.status_code == 404

    put_a = await client.put(
        f"/api/knowledge-hub/entities/{private_id}",
        headers=auth_headers,
        json={"summary": "A更新自己的实体"},
    )
    assert put_a.status_code == 200
    assert put_a.json()["summary"] == "A更新自己的实体"


@pytest.mark.asyncio
async def test_cannot_create_relationship_to_invisible_entity(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict
):
    private_a = await _import_private(client, auth_headers, PRIVATE_TITLE)
    own_b = await _import_private(client, second_user_headers, "B家的文章")

    resp = await client.post(
        f"/api/knowledge-hub/entities/{own_b}/relationships",
        headers=second_user_headers,
        json={
            "source_entity_id": own_b,
            "target_entity_id": private_a,
            "relationship_type": "synergy_with",
        },
    )
    assert resp.status_code == 404
    assert "目标实体不存在" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_imported_entity_is_tenant_scoped_in_db(
    client: AsyncClient, auth_headers: dict, db: DbAdapter
):
    private_id = await _import_private(client, auth_headers, PRIVATE_TITLE)
    row = await db.query_one(
        "SELECT tenant_id FROM knowledge_entities WHERE id = ?", (private_id,)
    )
    assert row is not None
    assert row["tenant_id"] is not None
    assert row["tenant_id"] != ""


# ---------------------------------------------------------------------------
# Global entities: visible to everyone, writable by admin only
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_global_entity_visible_to_all_families(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict, db: DbAdapter
):
    global_id = await _seed_global(db, GLOBAL_TITLE, "tenant-test-g1")

    for headers in (auth_headers, second_user_headers):
        found = await client.get(
            "/api/knowledge-hub/search", params={"q": GLOBAL_TITLE}, headers=headers
        )
        assert any(e["id"] == global_id for e in found.json()["items"])

        detail = await client.get(
            f"/api/knowledge-hub/entities/{global_id}", headers=headers
        )
        assert detail.status_code == 200


@pytest.mark.asyncio
async def test_normal_user_cannot_update_or_archive_global_entity(
    client: AsyncClient, auth_headers: dict, db: DbAdapter
):
    global_id = await _seed_global(db, GLOBAL_TITLE, "tenant-test-g2")

    resp = await client.put(
        f"/api/knowledge-hub/entities/{global_id}",
        headers=auth_headers,
        json={"summary": "普通用户篡改全局实体"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "需要管理员权限"

    archive = await client.put(
        f"/api/knowledge-hub/entities/{global_id}",
        headers=auth_headers,
        json={"status": "archived"},
    )
    assert archive.status_code == 403

    row = await db.query_one(
        "SELECT summary, status FROM knowledge_entities WHERE id = ?", (global_id,)
    )
    assert row["status"] == "active"


@pytest.mark.asyncio
async def test_admin_can_update_global_entity(
    client: AsyncClient, db: DbAdapter
):
    global_id = await _seed_global(db, GLOBAL_TITLE, "tenant-test-g3")

    resp = await client.put(
        f"/api/knowledge-hub/entities/{global_id}",
        json={"summary": "管理员更新全局实体"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["summary"] == "管理员更新全局实体"


# ---------------------------------------------------------------------------
# Relationship isolation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_user_relationship_between_globals_hidden_from_other_family(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict, db: DbAdapter
):
    g1 = await _seed_global(db, "关系测试全局甲", "tenant-test-r1")
    g2 = await _seed_global(db, "关系测试全局乙", "tenant-test-r2")

    create = await client.post(
        f"/api/knowledge-hub/entities/{g1}/relationships",
        headers=auth_headers,
        json={
            "source_entity_id": g1,
            "target_entity_id": g2,
            "relationship_type": "synergy_with",
        },
    )
    assert create.status_code == 201, create.text
    rel_id = create.json()["relationship_id"]

    rels_a = await client.get(
        f"/api/knowledge-hub/entities/{g1}/relationships", headers=auth_headers
    )
    assert any(r["id"] == rel_id for r in rels_a.json()["items"])

    rels_b = await client.get(
        f"/api/knowledge-hub/entities/{g1}/relationships", headers=second_user_headers
    )
    assert all(r["id"] != rel_id for r in rels_b.json()["items"])

    row = await db.query_one(
        "SELECT tenant_id FROM entity_relationships WHERE id = ?", (rel_id,)
    )
    assert row is not None and row["tenant_id"] is not None


# ---------------------------------------------------------------------------
# Person entities: no cross-family leakage, own flows keep working
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_other_family_person_entity_not_leaked(
    client: AsyncClient, auth_headers: dict, second_user_headers: dict, db: DbAdapter
):
    await db.execute(
        """INSERT INTO knowledge_entities
           (id, entity_type, source_table, source_id, title, summary,
            keywords, tags, category, properties, source_type, status, tenant_id)
           VALUES ('ke-person-other', 'person', 'users', 'user-other', ?,
                   '私人档案', '[]', '[]', '个人', '{}', 'user', 'active', 'family-other')""",
        (PERSON_TITLE,),
    )

    for headers in (auth_headers, second_user_headers):
        found = await client.get(
            "/api/knowledge-hub/search", params={"q": PERSON_TITLE}, headers=headers
        )
        assert all(e["title"] != PERSON_TITLE for e in found.json()["items"])

        detail = await client.get(
            "/api/knowledge-hub/entities/ke-person-other", headers=headers
        )
        assert detail.status_code == 404


@pytest.mark.asyncio
async def test_personal_symptom_flow_still_works_for_own_user(
    client: AsyncClient, auth_headers: dict, db: DbAdapter
):
    await db.execute(
        """INSERT INTO knowledge_entities
           (id, entity_type, source_table, source_id, title, summary,
            keywords, tags, category, properties, source_type, status, tenant_id)
           VALUES ('ke-symptom-tenant-test', 'symptom', 'seed', 'st1', '气虚乏力',
                   '可由黄芪治疗', '[]', '[]', '气虚', '{}', 'system', 'active', NULL)"""
    )

    log = await client.post(
        "/api/personal/symptoms",
        headers=auth_headers,
        json={"symptom_name": "气虚乏力", "severity": "轻度", "note": "劳累后加重"},
    )
    assert log.status_code == 200, log.text

    listed = await client.get("/api/personal/symptoms", headers=auth_headers)
    assert listed.status_code == 200
    symptoms = listed.json()["symptoms"]
    assert any(s["target"]["title"] == "气虚乏力" for s in symptoms)
