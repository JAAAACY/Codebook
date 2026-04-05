"""Canvas layout algorithm for Blueprint v2 — overview (topological) and detail (grid) views.

Produces 2D coordinates for module/function nodes suitable for SVG rendering.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any


# ── Data classes ──────────────────────────────────────────


@dataclass(frozen=True)
class OverviewNode:
    id: str
    label: str
    description: str
    health: float
    color: str
    x: float
    y: float
    width: int = 220
    height: int = 80


@dataclass(frozen=True)
class OverviewEdge:
    from_id: str
    to_id: str
    verb: str
    call_count: int


@dataclass(frozen=True)
class DetailNode:
    id: str
    business_name: str
    code_name: str
    file_path: str
    line_start: int
    explanation: str
    params: list[dict[str, str]]
    return_type: str
    x: float
    y: float
    width: int = 280
    height: int = 140


@dataclass(frozen=True)
class DetailEdge:
    from_id: str
    to_id: str
    label: str


# ── Constants ─────────────────────────────────────────────

# Overview
_OV_NODE_W = 220
_OV_NODE_H = 80
_OV_H_GAP = 120
_OV_V_GAP = 40
_OV_MARGIN = 60

# Detail
_DT_NODE_W = 280
_DT_NODE_H = 140
_DT_H_GAP = 80
_DT_V_GAP = 40
_DT_MARGIN = 60
_DT_COLS = 3


# ── Helpers ───────────────────────────────────────────────


def _health_color(health: float) -> str:
    """Map health score [0, 1] to a hex color."""
    if health >= 0.7:
        return "#10b981"  # green
    if health >= 0.4:
        return "#f59e0b"  # yellow
    return "#ef4444"  # red


# ── Overview layout (core path + collapsed groups) ───────

# 主线最多展示多少个核心模块
_MAX_CORE_NODES = 8


def _score_modules(
    modules: list[dict[str, Any]],
    connections: list[dict[str, Any]],
) -> dict[str, float]:
    """为每个模块打分，分数越高越核心。

    评分因素��
    - 连接度（in + out 边数）权重最高
    - 代码量（line_count）作为辅助
    - 被依赖数（used_by）比依赖数（depends_on）更重要
    """
    ids = {m["id"] for m in modules}
    out_degree: dict[str, int] = defaultdict(int)
    in_degree: dict[str, int] = defaultdict(int)

    for c in connections:
        src, dst = c.get("from", ""), c.get("to", "")
        if src in ids and dst in ids:
            out_degree[src] += 1
            in_degree[dst] += 1

    scores: dict[str, float] = {}
    for m in modules:
        mid = m["id"]
        # 被调用（入度）× 2 + 调用别人（出度）× 1
        connectivity = in_degree.get(mid, 0) * 2 + out_degree.get(mid, 0)
        scores[mid] = connectivity
    return scores


def _select_core_modules(
    modules: list[dict[str, Any]],
    connections: list[dict[str, Any]],
    max_core: int = _MAX_CORE_NODES,
) -> tuple[list[dict], list[dict], list[dict]]:
    """将模块分为核心模块和折叠组。

    Returns:
        (core_modules, collapsed_groups, core_connections)
        collapsed_groups 是 [{"id": "group_xxx", "label": "其他 (N 个模块)", ...}]
    """
    if len(modules) <= max_core:
        return modules, [], connections

    scores = _score_modules(modules, connections)
    sorted_mods = sorted(modules, key=lambda m: scores.get(m["id"], 0), reverse=True)

    core = sorted_mods[:max_core]
    peripheral = sorted_mods[max_core:]

    core_ids = {m["id"] for m in core}

    # 将非核心模块按顶层目录分组
    groups: dict[str, list[dict]] = defaultdict(list)
    for m in peripheral:
        path = m["id"]
        top = path.split("/")[0] if "/" in path else "other"
        groups[top].append(m)

    collapsed: list[dict] = []
    for group_name, members in groups.items():
        collapsed.append({
            "id": f"__group_{group_name}",
            "label": f"{group_name} ({len(members)} 个模块)",
            "description": "双击展开查看详情",
            "health": 0.7,
            "is_group": True,
            "member_ids": [m["id"] for m in members],
        })

    # 过滤连接：只保留核心模块间的 + 核心到折叠组的
    peripheral_to_group = {}
    for g in collapsed:
        for mid in g["member_ids"]:
            peripheral_to_group[mid] = g["id"]

    core_connections = []
    group_edge_seen: set[tuple[str, str]] = set()
    for c in connections:
        src, dst = c.get("from", ""), c.get("to", "")
        # 核心 → 核心：保留
        if src in core_ids and dst in core_ids:
            core_connections.append(c)
        # 核心 → 折叠组：聚合
        elif src in core_ids and dst in peripheral_to_group:
            gid = peripheral_to_group[dst]
            key = (src, gid)
            if key not in group_edge_seen:
                group_edge_seen.add(key)
                core_connections.append({"from": src, "to": gid, "verb": "调用", "call_count": 1})
        # 折叠组 → 核心：聚合
        elif src in peripheral_to_group and dst in core_ids:
            gid = peripheral_to_group[src]
            key = (gid, dst)
            if key not in group_edge_seen:
                group_edge_seen.add(key)
                core_connections.append({"from": gid, "to": dst, "verb": "调用", "call_count": 1})

    return core, collapsed, core_connections


def layout_overview(
    modules: list[dict[str, Any]],
    connections: list[dict[str, Any]],
) -> tuple[list[OverviewNode], list[OverviewEdge]]:
    """布局 Overview 页：核心模块 + 折叠组。

    只展示最核心的 5-8 个模块（按连接度排序），
    其余折叠为分组节点。连线只保留主线。

    Returns (nodes, edges) with computed (x, y) coordinates.
    """
    if not modules:
        return [], []

    core, collapsed, core_conns = _select_core_modules(modules, connections)
    all_display = core + collapsed

    # 构建拓扑分层
    ids = {m["id"] for m in all_display}
    adjacency: dict[str, list[str]] = defaultdict(list)
    in_deg: dict[str, int] = {mid: 0 for mid in ids}

    for conn in core_conns:
        src, dst = conn.get("from", ""), conn.get("to", "")
        if src in ids and dst in ids:
            adjacency[dst].append(src)
            in_deg[src] = in_deg.get(src, 0) + 1

    # Kahn's algorithm
    queue: deque[str] = deque(mid for mid, deg in in_deg.items() if deg == 0)
    layers: list[list[str]] = []
    visited: set[str] = set()

    while queue:
        layer = sorted(queue)  # 稳定排序
        layers.append(layer)
        visited.update(layer)
        next_queue: deque[str] = deque()
        for nid in layer:
            for neighbor in adjacency.get(nid, []):
                in_deg[neighbor] -= 1
                if in_deg[neighbor] == 0 and neighbor not in visited:
                    next_queue.append(neighbor)
        queue = next_queue

    remaining = sorted(mid for mid in ids if mid not in visited)
    if remaining:
        layers.append(remaining)

    # 坐标分配
    module_map = {m["id"]: m for m in all_display}
    result_nodes: list[OverviewNode] = []

    for col, layer in enumerate(layers):
        x = _OV_MARGIN + col * (_OV_NODE_W + _OV_H_GAP)
        total_h = len(layer) * _OV_NODE_H + (len(layer) - 1) * _OV_V_GAP
        start_y = _OV_MARGIN + max(0, (400 - total_h) // 2)

        for row, nid in enumerate(layer):
            y = start_y + row * (_OV_NODE_H + _OV_V_GAP)
            m = module_map[nid]
            health = m.get("health", 0.5)
            result_nodes.append(
                OverviewNode(
                    id=nid,
                    label=m["label"],
                    description=m.get("description", ""),
                    health=health,
                    color="#3a3f55" if m.get("is_group") else _health_color(health),
                    x=x,
                    y=y,
                )
            )

    result_edges = [
        OverviewEdge(
            from_id=c["from"],
            to_id=c["to"],
            verb=c.get("verb", ""),
            call_count=c.get("call_count", 0),
        )
        for c in core_conns
    ]

    return result_nodes, result_edges


# ── Module detail layout (grid) ──────────────────────────


def layout_module_detail(
    functions: list[dict[str, Any]],
    callers_map: dict[str, list[str]],
    callees_map: dict[str, list[str]],
) -> tuple[list[DetailNode], list[DetailEdge]]:
    """Lay out function nodes in a grid (3 columns) and generate internal call edges.

    Returns (nodes, edges).
    """
    func_ids = {f["id"] for f in functions}
    result_nodes: list[DetailNode] = []

    for idx, fn in enumerate(functions):
        col = idx % _DT_COLS
        row = idx // _DT_COLS
        x = _DT_MARGIN + col * (_DT_NODE_W + _DT_H_GAP)
        y = _DT_MARGIN + row * (_DT_NODE_H + _DT_V_GAP)
        result_nodes.append(
            DetailNode(
                id=fn["id"],
                business_name=fn.get("business_name", ""),
                code_name=fn.get("code_name", ""),
                file_path=fn.get("file_path", ""),
                line_start=fn.get("line_start", 0),
                explanation=fn.get("explanation", ""),
                params=fn.get("params", []),
                return_type=fn.get("return_type", ""),
                x=x,
                y=y,
            )
        )

    # Generate edges from callees_map
    result_edges: list[DetailEdge] = []
    for caller_id, callees in callees_map.items():
        if caller_id not in func_ids:
            continue
        for callee_raw in callees:
            # Support "module/func" format — take the last segment
            callee_id = callee_raw.rsplit("/", 1)[-1]
            if callee_id in func_ids:
                result_edges.append(
                    DetailEdge(
                        from_id=caller_id,
                        to_id=callee_id,
                        label="calls",
                    )
                )

    return result_nodes, result_edges
