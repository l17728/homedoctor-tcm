"""Tests for knowledge graph endpoints and engine (spec §9/§13.3 V3)."""

import pytest
from httpx import AsyncClient

from app.database import DbAdapter
from app.graph_engine import build_graph, build_snapshot
from app.kg_rebuild import rebuild_all_edges


@pytest.mark.asyncio
async def test_build_graph_returns_nodes_and_edges(db: DbAdapter):
    """build_graph 直接调用：rebuild 后返回节点和边。"""
    await rebuild_all_edges(db)
    result = await build_graph(db, limit=500)
    assert "nodes" in result and "edges" in result
    node_types = {n["node_type"] for n in result["nodes"]}
    assert "herb" in node_types
    assert "formula" in node_types
    assert len(result["nodes"]) >= 3
    edge_types = {e["edge_type"] for e in result["edges"]}
    assert "组成" in edge_types
    for e in result["edges"]:
        assert e["source"] != e["target"] or e["edge_type"] in ("配伍禁忌",)
        assert e["source"] and e["target"]


@pytest.mark.asyncio
async def test_build_snapshot_bfs_traversal(db: DbAdapter):
    """build_snapshot BFS：从方剂出发能到达其组成中药。"""
    await rebuild_all_edges(db)
    snap = await build_snapshot(db, "formula", "formula-001", max_depth=1)
    assert snap["root_id"] == "formula-001"
    node_ids = {n["id"] for n in snap["nodes"]}
    assert "formula-001" in node_ids
    assert "herb-003" in node_ids
    assert any(
        e["edge_type"] == "组成" and e["source"] == "formula-001" and e["target"] == "herb-003"
        for e in snap["edges"]
    )


@pytest.mark.asyncio
async def test_rebuild_creates_edges(client: AsyncClient, auth_headers: dict):
    """POST /api/kg/rebuild 创建正确数量的边。"""
    resp = await client.post("/api/kg/rebuild", headers=auth_headers)
    assert resp.status_code == 200
    counts = resp.json()
    assert counts["组成"] >= 2
    assert counts["主治"] >= 1
    assert counts["中西药交互"] >= 1


@pytest.mark.asyncio
async def test_graph_endpoint_type_filter(client: AsyncClient, auth_headers: dict):
    """GET /api/kg/graph?types=herb 只返回 herb 节点。"""
    await client.post("/api/kg/rebuild", headers=auth_headers)
    resp = await client.get("/api/kg/graph?types=herb", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["nodes"]) > 0
    for n in data["nodes"]:
        assert n["node_type"] == "herb"


@pytest.mark.asyncio
async def test_graph_endpoint_keyword_search(client: AsyncClient, auth_headers: dict):
    """GET /api/kg/graph?q=黄芪 返回含黄芪的节点。"""
    await client.post("/api/kg/rebuild", headers=auth_headers)
    resp = await client.get("/api/kg/graph?q=黄芪", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    labels = [n["label"] for n in data["nodes"]]
    assert "黄芪" in labels


@pytest.mark.asyncio
async def test_snapshot_depth_parameter(client: AsyncClient, auth_headers: dict):
    """snapshot depth 参数：depth=2 比 depth=1 覆盖更多节点。"""
    await client.post("/api/kg/rebuild", headers=auth_headers)
    d1 = await client.get(
        "/api/kg/snapshot/herb/herb-002?depth=1", headers=auth_headers
    )
    d2 = await client.get(
        "/api/kg/snapshot/herb/herb-002?depth=2", headers=auth_headers
    )
    assert d1.status_code == 200 and d2.status_code == 200
    assert len(d2.json()["nodes"]) >= len(d1.json()["nodes"])
    assert d1.json()["root_id"] == "herb-002"


@pytest.mark.asyncio
async def test_node_detail_endpoint(client: AsyncClient, auth_headers: dict):
    """GET /api/kg/node/{id} 返回节点完整属性。"""
    await client.post("/api/kg/rebuild", headers=auth_headers)
    resp = await client.get("/api/kg/node/herb-001", headers=auth_headers)
    assert resp.status_code == 200
    node = resp.json()
    assert node["id"] == "herb-001"
    assert node["node_type"] == "herb"
    assert node["label"] == "黄芪"

    missing = await client.get("/api/kg/node/no-such-id", headers=auth_headers)
    assert missing.status_code == 404


# ---------------------------------------------------------------------------
# Rebuild integrity — no orphan edges after rebuild (audit gap P2.8)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rebuild_produces_no_orphan_edges(db: DbAdapter):
    """After rebuild, every edge's source_id and target_id must exist in graph_nodes."""
    await rebuild_all_edges(db)

    edges = await db.query("SELECT edge_type, source_id, target_id FROM graph_edges")
    assert len(edges) > 0, "rebuild should produce at least some edges"

    node_ids = {
        row["id"] for row in await db.query("SELECT id FROM graph_nodes")
    }

    orphans = [
        (e["edge_type"], e["source_id"], e["target_id"])
        for e in edges
        if e["source_id"] not in node_ids or e["target_id"] not in node_ids
    ]
    assert orphans == [], f"{len(orphans)} orphan edges reference missing nodes: {orphans[:3]}"
