"""Tests for bookmarks endpoints — 多态收藏 + 标签 + 合集 (spec §7.5)."""

import pytest
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Bookmark CRUD
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_bookmark_herb(client: AsyncClient, auth_headers: dict):
    """POST /api/bookmarks creates a herb bookmark."""
    resp = await client.post("/api/bookmarks", json={
        "entry_type": "herb",
        "title": "黄芪",
        "entry_id": "herb-001",
        "tags": ["补气", "常用"],
        "source_type": "herb_detail",
        "notes": "补气升阳要药",
    }, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["entry_type"] == "herb"
    assert data["title"] == "黄芪"
    assert data["entry_id"] == "herb-001"
    assert "补气" in data["tags"]
    assert data["source_type"] == "herb_detail"


@pytest.mark.asyncio
async def test_create_bookmark_formula(client: AsyncClient, auth_headers: dict):
    """POST /api/bookmarks creates a formula bookmark."""
    resp = await client.post("/api/bookmarks", json={
        "entry_type": "formula",
        "title": "四物汤",
        "entry_id": "formula-002",
        "tags": ["补血"],
        "source_type": "search",
    }, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["entry_type"] == "formula"


@pytest.mark.asyncio
async def test_create_bookmark_external(client: AsyncClient, auth_headers: dict):
    """POST /api/bookmarks creates an external bookmark."""
    resp = await client.post("/api/bookmarks", json={
        "entry_type": "external",
        "title": "中医百科",
        "content": "https://example.com/tcm-wiki",
        "source_type": "manual",
    }, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["entry_type"] == "external"
    assert data["content"] == "https://example.com/tcm-wiki"


@pytest.mark.asyncio
async def test_create_bookmark_invalid_type(client: AsyncClient, auth_headers: dict):
    """POST /api/bookmarks rejects invalid entry_type."""
    resp = await client.post("/api/bookmarks", json={
        "entry_type": "invalid_type",
        "title": "test",
    }, headers=auth_headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_bookmark_missing_title(client: AsyncClient, auth_headers: dict):
    """POST /api/bookmarks requires title."""
    resp = await client.post("/api/bookmarks", json={
        "entry_type": "herb",
    }, headers=auth_headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_bookmark_requires_auth(client: AsyncClient):
    """POST /api/bookmarks requires authentication."""
    resp = await client.post("/api/bookmarks", json={
        "entry_type": "herb",
        "title": "黄芪",
    })
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_list_bookmarks(client: AsyncClient, auth_headers: dict):
    """GET /api/bookmarks returns user's bookmarks."""
    # Create multiple bookmarks
    for name in ["黄芪", "当归", "甘草"]:
        await client.post("/api/bookmarks", json={
            "entry_type": "herb", "title": name,
        }, headers=auth_headers)

    resp = await client.get("/api/bookmarks", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    titles = [b["title"] for b in data["items"]]
    assert "黄芪" in titles
    assert "当归" in titles


@pytest.mark.asyncio
async def test_list_bookmarks_filter_by_type(client: AsyncClient, auth_headers: dict):
    """GET /api/bookmarks?entry_type=herb filters by type."""
    await client.post("/api/bookmarks", json={
        "entry_type": "herb", "title": "黄芪",
    }, headers=auth_headers)
    await client.post("/api/bookmarks", json={
        "entry_type": "formula", "title": "四物汤",
    }, headers=auth_headers)

    resp = await client.get("/api/bookmarks?entry_type=herb", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["entry_type"] == "herb"


@pytest.mark.asyncio
async def test_list_bookmarks_filter_starred(client: AsyncClient, auth_headers: dict):
    """GET /api/bookmarks?is_starred=true filters starred only."""
    await client.post("/api/bookmarks", json={
        "entry_type": "herb", "title": "黄芪", "is_starred": True,
    }, headers=auth_headers)
    await client.post("/api/bookmarks", json={
        "entry_type": "herb", "title": "当归", "is_starred": False,
    }, headers=auth_headers)

    resp = await client.get("/api/bookmarks?is_starred=true", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "黄芪"


@pytest.mark.asyncio
async def test_list_bookmarks_tag_filter_or(client: AsyncClient, auth_headers: dict):
    """GET /api/bookmarks?tags=补气,补血&tag_logic=OR returns bookmarks matching any tag."""
    await client.post("/api/bookmarks", json={
        "entry_type": "herb", "title": "黄芪", "tags": ["补气"],
    }, headers=auth_headers)
    await client.post("/api/bookmarks", json={
        "entry_type": "herb", "title": "当归", "tags": ["补血"],
    }, headers=auth_headers)
    await client.post("/api/bookmarks", json={
        "entry_type": "herb", "title": "甘草", "tags": ["调和"],
    }, headers=auth_headers)

    resp = await client.get(
        "/api/bookmarks?tags=补气,补血&tag_logic=OR", headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    titles = {b["title"] for b in data["items"]}
    assert titles == {"黄芪", "当归"}


@pytest.mark.asyncio
async def test_list_bookmarks_tag_filter_and(client: AsyncClient, auth_headers: dict):
    """GET /api/bookmarks?tags=补气,常用&tag_logic=AND returns bookmarks with ALL tags."""
    await client.post("/api/bookmarks", json={
        "entry_type": "herb", "title": "黄芪", "tags": ["补气", "常用"],
    }, headers=auth_headers)
    await client.post("/api/bookmarks", json={
        "entry_type": "herb", "title": "当归", "tags": ["补血", "常用"],
    }, headers=auth_headers)
    await client.post("/api/bookmarks", json={
        "entry_type": "herb", "title": "甘草", "tags": ["补气"],
    }, headers=auth_headers)

    resp = await client.get(
        "/api/bookmarks?tags=补气,常用&tag_logic=AND", headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "黄芪"


@pytest.mark.asyncio
async def test_get_bookmark(client: AsyncClient, auth_headers: dict):
    """GET /api/bookmarks/{id} returns bookmark detail."""
    create = await client.post("/api/bookmarks", json={
        "entry_type": "herb", "title": "黄芪",
    }, headers=auth_headers)
    bm_id = create.json()["id"]

    resp = await client.get(f"/api/bookmarks/{bm_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["title"] == "黄芪"


@pytest.mark.asyncio
async def test_get_bookmark_not_found(client: AsyncClient, auth_headers: dict):
    """GET /api/bookmarks/{invalid_id} returns 404."""
    resp = await client.get("/api/bookmarks/nonexistent", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_bookmark_tags(client: AsyncClient, auth_headers: dict):
    """PUT /api/bookmarks/{id} updates tags."""
    create = await client.post("/api/bookmarks", json={
        "entry_type": "herb", "title": "黄芪",
    }, headers=auth_headers)
    bm_id = create.json()["id"]

    resp = await client.put(f"/api/bookmarks/{bm_id}", json={
        "tags": ["补气", "升阳"],
        "is_starred": True,
    }, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "补气" in data["tags"]
    assert "升阳" in data["tags"]
    assert data["is_starred"] is True


@pytest.mark.asyncio
async def test_update_bookmark_content(client: AsyncClient, auth_headers: dict):
    """PUT /api/bookmarks/{id} updates content/notes."""
    create = await client.post("/api/bookmarks", json={
        "entry_type": "knowledge", "title": "养生笔记",
    }, headers=auth_headers)
    bm_id = create.json()["id"]

    resp = await client.put(f"/api/bookmarks/{bm_id}", json={
        "content": "每日早晨服用黄芪水",
    }, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["content"] == "每日早晨服用黄芪水"


@pytest.mark.asyncio
async def test_delete_bookmark(client: AsyncClient, auth_headers: dict):
    """DELETE /api/bookmarks/{id} removes bookmark."""
    create = await client.post("/api/bookmarks", json={
        "entry_type": "herb", "title": "黄芪",
    }, headers=auth_headers)
    bm_id = create.json()["id"]

    resp = await client.delete(f"/api/bookmarks/{bm_id}", headers=auth_headers)
    assert resp.status_code == 200

    # Verify deletion
    resp = await client.get(f"/api/bookmarks/{bm_id}", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_bookmark_not_found(client: AsyncClient, auth_headers: dict):
    """DELETE /api/bookmarks/{invalid_id} returns 404."""
    resp = await client.delete("/api/bookmarks/nonexistent", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_check_bookmark_exists(client: AsyncClient, auth_headers: dict):
    """POST /api/bookmarks/check detects existing bookmark."""
    await client.post("/api/bookmarks", json={
        "entry_type": "herb", "title": "黄芪", "entry_id": "herb-001",
    }, headers=auth_headers)

    resp = await client.post("/api/bookmarks/check", json={
        "entry_type": "herb", "entry_id": "herb-001",
    }, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_bookmarked"] is True


@pytest.mark.asyncio
async def test_check_bookmark_not_exists(client: AsyncClient, auth_headers: dict):
    """POST /api/bookmarks/check returns false for non-bookmarked."""
    resp = await client.post("/api/bookmarks/check", json={
        "entry_type": "herb", "entry_id": "herb-999",
    }, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["is_bookmarked"] is False


@pytest.mark.asyncio
async def test_user_isolation(client: AsyncClient, auth_headers: dict, second_user_headers: dict):
    """Bookmarks are isolated per user."""
    await client.post("/api/bookmarks", json={
        "entry_type": "herb", "title": "用户1的黄芪",
    }, headers=auth_headers)

    # User 2 should not see user 1's bookmarks
    resp = await client.get("/api/bookmarks", headers=second_user_headers)
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


# ---------------------------------------------------------------------------
# Collections (合集)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_collection(client: AsyncClient, auth_headers: dict):
    """POST /api/bookmarks/collections creates a collection."""
    resp = await client.post("/api/bookmarks/collections", json={
        "title": "补气药收藏集",
        "tags": ["补气"],
    }, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "补气药收藏集"
    assert data["entry_type"] == "collection"
    assert isinstance(data["content"], list)


@pytest.mark.asyncio
async def test_create_collection_missing_title(client: AsyncClient, auth_headers: dict):
    """POST /api/bookmarks/collections requires title."""
    resp = await client.post("/api/bookmarks/collections", json={}, headers=auth_headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_collections(client: AsyncClient, auth_headers: dict):
    """GET /api/bookmarks/collections lists user's collections."""
    for name in ["合集一", "合集二"]:
        await client.post("/api/bookmarks/collections", json={
            "title": name,
        }, headers=auth_headers)

    resp = await client.get("/api/bookmarks/collections", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2


@pytest.mark.asyncio
async def test_collections_excluded_from_bookmark_list(client: AsyncClient, auth_headers: dict):
    """GET /api/bookmarks does NOT include collections."""
    await client.post("/api/bookmarks", json={
        "entry_type": "herb", "title": "黄芪",
    }, headers=auth_headers)
    await client.post("/api/bookmarks/collections", json={
        "title": "我的合集",
    }, headers=auth_headers)

    resp = await client.get("/api/bookmarks", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1  # only the herb bookmark, not the collection
    assert all(b["entry_type"] != "collection" for b in data["items"])


@pytest.mark.asyncio
async def test_add_bookmarks_to_collection(client: AsyncClient, auth_headers: dict):
    """POST /api/bookmarks/collections/{id}/items adds bookmarks."""
    # Create bookmarks
    bm1 = await client.post("/api/bookmarks", json={
        "entry_type": "herb", "title": "黄芪",
    }, headers=auth_headers)
    bm2 = await client.post("/api/bookmarks", json={
        "entry_type": "herb", "title": "当归",
    }, headers=auth_headers)

    # Create collection
    col = await client.post("/api/bookmarks/collections", json={
        "title": "补虚药",
    }, headers=auth_headers)

    # Add bookmarks
    resp = await client.post(
        f"/api/bookmarks/collections/{col.json()['id']}/items",
        json={"bookmark_ids": [bm1.json()["id"], bm2.json()["id"]]},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_members"] == 2
    assert len(data["added"]) == 2


@pytest.mark.asyncio
async def test_get_collection_with_members(client: AsyncClient, auth_headers: dict):
    """GET /api/bookmarks/collections/{id} returns collection with member bookmarks."""
    bm = await client.post("/api/bookmarks", json={
        "entry_type": "herb", "title": "黄芪",
    }, headers=auth_headers)
    col = await client.post("/api/bookmarks/collections", json={
        "title": "合集",
    }, headers=auth_headers)

    await client.post(
        f"/api/bookmarks/collections/{col.json()['id']}/items",
        json={"bookmark_ids": [bm.json()["id"]]},
        headers=auth_headers,
    )

    resp = await client.get(
        f"/api/bookmarks/collections/{col.json()['id']}", headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["member_count"] == 1
    assert len(data["members"]) == 1
    assert data["members"][0]["title"] == "黄芪"


@pytest.mark.asyncio
async def test_remove_bookmark_from_collection(client: AsyncClient, auth_headers: dict):
    """DELETE /api/bookmarks/collections/{id}/items/{bid} removes a member."""
    bm1 = await client.post("/api/bookmarks", json={
        "entry_type": "herb", "title": "黄芪",
    }, headers=auth_headers)
    bm2 = await client.post("/api/bookmarks", json={
        "entry_type": "herb", "title": "当归",
    }, headers=auth_headers)
    col = await client.post("/api/bookmarks/collections", json={
        "title": "合集",
    }, headers=auth_headers)
    col_id = col.json()["id"]

    await client.post(
        f"/api/bookmarks/collections/{col_id}/items",
        json={"bookmark_ids": [bm1.json()["id"], bm2.json()["id"]]},
        headers=auth_headers,
    )

    resp = await client.delete(
        f"/api/bookmarks/collections/{col_id}/items/{bm1.json()['id']}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["total_members"] == 1


@pytest.mark.asyncio
async def test_delete_bookmark_removes_from_collections(client: AsyncClient, auth_headers: dict):
    """Deleting a bookmark also removes it from all collections."""
    bm = await client.post("/api/bookmarks", json={
        "entry_type": "herb", "title": "黄芪",
    }, headers=auth_headers)
    bm_id = bm.json()["id"]
    col = await client.post("/api/bookmarks/collections", json={
        "title": "合集",
    }, headers=auth_headers)
    col_id = col.json()["id"]

    await client.post(
        f"/api/bookmarks/collections/{col_id}/items",
        json={"bookmark_ids": [bm_id]},
        headers=auth_headers,
    )

    # Delete the bookmark
    await client.delete(f"/api/bookmarks/{bm_id}", headers=auth_headers)

    # Collection should no longer contain it
    resp = await client.get(f"/api/bookmarks/collections/{col_id}", headers=auth_headers)
    assert resp.json()["member_count"] == 0


@pytest.mark.asyncio
async def test_delete_collection(client: AsyncClient, auth_headers: dict):
    """DELETE /api/bookmarks/collections/{id} deletes collection but not bookmarks."""
    bm = await client.post("/api/bookmarks", json={
        "entry_type": "herb", "title": "黄芪",
    }, headers=auth_headers)
    col = await client.post("/api/bookmarks/collections", json={
        "title": "合集",
    }, headers=auth_headers)
    col_id = col.json()["id"]

    resp = await client.delete(f"/api/bookmarks/collections/{col_id}", headers=auth_headers)
    assert resp.status_code == 200

    # Bookmark should still exist
    resp = await client.get(f"/api/bookmarks/{bm.json()['id']}", headers=auth_headers)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_add_invalid_bookmark_to_collection(client: AsyncClient, auth_headers: dict):
    """Adding a non-existent bookmark to a collection is silently ignored."""
    col = await client.post("/api/bookmarks/collections", json={
        "title": "合集",
    }, headers=auth_headers)

    resp = await client.post(
        f"/api/bookmarks/collections/{col.json()['id']}/items",
        json={"bookmark_ids": ["fake-id-999"]},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["total_members"] == 0


@pytest.mark.asyncio
async def test_source_tracking(client: AsyncClient, auth_headers: dict):
    """Bookmark source_type is stored and returned."""
    for source in ["chat", "herb_detail", "search", "manual"]:
        resp = await client.post("/api/bookmarks", json={
            "entry_type": "herb",
            "title": f"测试-{source}",
            "source_type": source,
        }, headers=auth_headers)
        assert resp.status_code == 201
        assert resp.json()["source_type"] == source


@pytest.mark.asyncio
async def test_create_collection_with_initial_members(client: AsyncClient, auth_headers: dict):
    """POST /api/bookmarks/collections with bookmark_ids adds them immediately."""
    bm1 = await client.post("/api/bookmarks", json={
        "entry_type": "herb", "title": "黄芪",
    }, headers=auth_headers)
    bm2 = await client.post("/api/bookmarks", json={
        "entry_type": "herb", "title": "当归",
    }, headers=auth_headers)

    resp = await client.post("/api/bookmarks/collections", json={
        "title": "批量合集",
        "bookmark_ids": [bm1.json()["id"], bm2.json()["id"]],
    }, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert isinstance(data["content"], list)
    assert len(data["content"]) == 2
