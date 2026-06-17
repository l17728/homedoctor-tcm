"""Knowledge graph engine — port of /fighting graph.ts (buildGraph/buildSnapshot).

结构化数据是权威来源；图谱为派生产物。两个核心算法：

* ``build_graph`` — 跨类型收集节点(可按类型/关键词过滤)，再取这些节点之间的边。
* ``build_snapshot`` — 从根节点出发的 BFS 邻域，最多 ``max_depth`` 跳。
"""

from __future__ import annotations

from collections import deque
from typing import Any

from app.database import DbAdapter

ALL_NODE_TYPES = ["herb", "formula", "symptom", "therapy", "medicine"]


def _node_out(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "node_type": row["node_type"],
        "label": row["label"],
    }


async def build_graph(
    db: DbAdapter,
    node_types: list[str] | None = None,
    q: str | None = None,
    limit: int = 500,
) -> dict[str, Any]:
    """Collect nodes filtered by types and/or keyword, then edges between them."""
    limit = max(1, min(limit, 2000))
    types = node_types if node_types else list(ALL_NODE_TYPES)
    q_norm = (q or "").strip().lower()

    where_parts: list[str] = []
    params: list[Any] = []
    placeholders = ",".join("?" for _ in types)
    where_parts.append(f"node_type IN ({placeholders})")
    params.extend(types)
    if q_norm:
        where_parts.append(
            "(LOWER(label) LIKE ? OR LOWER(COALESCE(search_text,'')) LIKE ?)"
        )
        params.extend([f"%{q_norm}%", f"%{q_norm}%"])

    sql = (
        "SELECT id, node_type, label FROM graph_nodes "
        f"WHERE {' AND '.join(where_parts)} ORDER BY node_type, label LIMIT ?"
    )
    params.append(limit)
    rows = await db.query(sql, tuple(params))

    nodes: dict[str, dict[str, Any]] = {}
    for r in rows:
        nodes[r["id"]] = _node_out(r)

    ids = set(nodes.keys())
    edges: dict[str, dict[str, Any]] = {}
    if ids:
        id_placeholders = ",".join("?" for _ in ids)
        edge_rows = await db.query(
            "SELECT source_id, target_id, edge_type FROM graph_edges "
            f"WHERE source_id IN ({id_placeholders}) AND target_id IN ({id_placeholders})",
            tuple(ids) + tuple(ids),
        )
        for e in edge_rows:
            key = f"{e['source_id']}->{e['target_id']}:{e['edge_type']}"
            if key not in edges:
                edges[key] = {
                    "source": e["source_id"],
                    "target": e["target_id"],
                    "edge_type": e["edge_type"],
                }

    return {
        "root_id": "",
        "nodes": list(nodes.values()),
        "edges": list(edges.values()),
    }


async def build_snapshot(
    db: DbAdapter,
    node_type: str,
    node_id: str,
    max_depth: int = 2,
) -> dict[str, Any]:
    """BFS neighborhood from a root node, following edges up to ``max_depth`` hops."""
    root = await db.query_one(
        "SELECT id, node_type, label FROM graph_nodes WHERE id = ?", (node_id,)
    )
    if not root:
        return {"root_id": node_id, "nodes": [], "edges": []}

    nodes: dict[str, dict[str, Any]] = {root["id"]: _node_out(root)}
    if max_depth <= 0:
        return {"root_id": node_id, "nodes": list(nodes.values()), "edges": []}

    edges: dict[str, dict[str, Any]] = {}
    seen: set[str] = {root["id"]}
    queue: deque[tuple[str, int]] = deque([(root["id"], 0)])

    while queue:
        cur_id, depth = queue.popleft()
        if depth >= max_depth:
            continue
        out_rows = await db.query(
            "SELECT source_id, target_id, edge_type FROM graph_edges WHERE source_id = ?",
            (cur_id,),
        )
        in_rows = await db.query(
            "SELECT source_id, target_id, edge_type FROM graph_edges WHERE target_id = ?",
            (cur_id,),
        )
        for e in out_rows + in_rows:
            peer_id = e["target_id"] if e["source_id"] == cur_id else e["source_id"]
            src, tgt = e["source_id"], e["target_id"]
            key = f"{src}->{tgt}:{e['edge_type']}"
            if key not in edges:
                edges[key] = {
                    "source": src,
                    "target": tgt,
                    "edge_type": e["edge_type"],
                }
            if peer_id not in nodes:
                peer = await db.query_one(
                    "SELECT id, node_type, label FROM graph_nodes WHERE id = ?",
                    (peer_id,),
                )
                if peer:
                    nodes[peer_id] = _node_out(peer)
            if peer_id not in seen:
                seen.add(peer_id)
                queue.append((peer_id, depth + 1))

    return {
        "root_id": node_id,
        "nodes": list(nodes.values()),
        "edges": list(edges.values()),
    }
