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


# ── Overview layout (topological layering) ────────────────


def layout_overview(
    modules: list[dict[str, Any]],
    connections: list[dict[str, Any]],
) -> tuple[list[OverviewNode], list[OverviewEdge]]:
    """Lay out module nodes using topological layering (Kahn's algorithm variant).

    Nodes with no in-edges appear in the leftmost column; each subsequent layer
    contains nodes whose dependencies are all in earlier layers.

    Returns (nodes, edges) with computed (x, y) coordinates.
    """
    # Build adjacency and in-degree maps
    ids = {m["id"] for m in modules}
    adjacency: dict[str, list[str]] = defaultdict(list)
    in_degree: dict[str, int] = {mid: 0 for mid in ids}

    # Edge semantics: "from" depends on "to" (importer → dependency).
    # We want dependencies on the LEFT, so build the DAG as dependency → dependent
    # (i.e., reverse the connection direction for topological ordering).
    for conn in connections:
        dependent, dependency = conn["from"], conn["to"]
        if dependent in ids and dependency in ids:
            adjacency[dependency].append(dependent)
            in_degree[dependent] = in_degree.get(dependent, 0) + 1

    # Kahn's algorithm — assign layers
    queue: deque[str] = deque(mid for mid, deg in in_degree.items() if deg == 0)
    layers: list[list[str]] = []
    visited: set[str] = set()

    while queue:
        layer = list(queue)
        layers.append(layer)
        visited.update(layer)
        next_queue: deque[str] = deque()
        for node_id in layer:
            for neighbor in adjacency.get(node_id, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0 and neighbor not in visited:
                    next_queue.append(neighbor)
        queue = next_queue

    # Handle cycles — remaining nodes go into an extra layer
    remaining = [mid for mid in ids if mid not in visited]
    if remaining:
        layers.append(remaining)

    # Assign coordinates
    # Note: "from" in connections means the *dependent* (importer), and "to" is the
    # dependency.  Kahn's starts from nodes with in_degree==0, which are the
    # dependencies (the targets of edges).  We want dependencies on the LEFT, so
    # layer 0 (in_degree==0 nodes) gets the smallest x — which is already the case.
    module_map = {m["id"]: m for m in modules}
    result_nodes: list[OverviewNode] = []

    for col, layer in enumerate(layers):
        x = _OV_MARGIN + col * (_OV_NODE_W + _OV_H_GAP)
        for row, node_id in enumerate(layer):
            y = _OV_MARGIN + row * (_OV_NODE_H + _OV_V_GAP)
            m = module_map[node_id]
            health = m.get("health", 0.5)
            result_nodes.append(
                OverviewNode(
                    id=node_id,
                    label=m["label"],
                    description=m.get("description", ""),
                    health=health,
                    color=_health_color(health),
                    x=x,
                    y=y,
                )
            )

    # Build edges
    result_edges = [
        OverviewEdge(
            from_id=c["from"],
            to_id=c["to"],
            verb=c.get("verb", ""),
            call_count=c.get("call_count", 0),
        )
        for c in connections
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
