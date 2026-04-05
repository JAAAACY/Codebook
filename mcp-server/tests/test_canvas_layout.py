"""Tests for canvas layout algorithm — overview (topological) and detail (grid) views."""

from __future__ import annotations

import math

import pytest


# ── Overview layout tests ──────────────────────────────────


class TestLayoutOverview:
    """Tests for layout_overview(modules, connections)."""

    def test_single_node_position(self) -> None:
        """Single node should have x >= 0, y >= 0 and correct label."""
        from src.tools.canvas_layout import layout_overview

        modules = [
            {"id": "auth", "label": "Auth", "description": "认证模块", "health": 0.9},
        ]
        connections: list[dict] = []

        nodes, edges = layout_overview(modules, connections)

        assert len(nodes) == 1
        node = nodes[0]
        assert node.x >= 0
        assert node.y >= 0
        assert node.label == "Auth"
        assert node.width == 220
        assert node.height == 80

    def test_two_nodes_dependency_order(self) -> None:
        """Depended-upon node (no in-edges) should be left; dependent should be right."""
        from src.tools.canvas_layout import layout_overview

        modules = [
            {"id": "api", "label": "API", "description": "路由层", "health": 0.8},
            {"id": "db", "label": "DB", "description": "数据库层", "health": 0.7},
        ]
        # api depends on db  →  db has no in-edges → db should be left
        connections = [
            {"from": "api", "to": "db", "verb": "imports", "call_count": 5},
        ]

        nodes, edges = layout_overview(modules, connections)

        node_map = {n.id: n for n in nodes}
        assert node_map["db"].x < node_map["api"].x

    def test_ten_nodes_no_overlap(self) -> None:
        """10 nodes must not overlap — pairwise distance > 100."""
        from src.tools.canvas_layout import layout_overview

        modules = [
            {"id": f"mod_{i}", "label": f"Mod{i}", "description": "", "health": 0.5}
            for i in range(10)
        ]
        # Chain: mod_0 → mod_1 → ... → mod_9
        connections = [
            {"from": f"mod_{i}", "to": f"mod_{i + 1}", "verb": "calls", "call_count": 1}
            for i in range(9)
        ]

        nodes, _edges = layout_overview(modules, connections)

        for i, a in enumerate(nodes):
            for b in nodes[i + 1 :]:
                dist = math.hypot(a.x - b.x, a.y - b.y)
                assert dist > 100, f"Overlap: {a.id}({a.x},{a.y}) vs {b.id}({b.x},{b.y})"

    def test_health_affects_color(self) -> None:
        """Red health (< 0.4) and green health (>= 0.7) should produce different colors."""
        from src.tools.canvas_layout import layout_overview

        modules = [
            {"id": "bad", "label": "Bad", "description": "", "health": 0.2},
            {"id": "good", "label": "Good", "description": "", "health": 0.9},
        ]

        nodes, _ = layout_overview(modules, [])

        color_map = {n.id: n.color for n in nodes}
        assert color_map["bad"] != color_map["good"]
        assert color_map["bad"] == "#ef4444"
        assert color_map["good"] == "#10b981"

    def test_edges_generated(self) -> None:
        """Connections should produce matching edges."""
        from src.tools.canvas_layout import layout_overview

        modules = [
            {"id": "a", "label": "A", "description": "", "health": 0.5},
            {"id": "b", "label": "B", "description": "", "health": 0.5},
        ]
        connections = [
            {"from": "a", "to": "b", "verb": "imports", "call_count": 3},
        ]

        _, edges = layout_overview(modules, connections)

        assert len(edges) == 1
        assert edges[0].from_id == "a"
        assert edges[0].to_id == "b"
        assert edges[0].verb == "imports"
        assert edges[0].call_count == 3


# ── Module detail layout tests ─────────────────────────────


class TestLayoutModuleDetail:
    """Tests for layout_module_detail(functions, callers_map, callees_map)."""

    def test_function_node_fields(self) -> None:
        """Function node should carry business_name and explanation."""
        from src.tools.canvas_layout import layout_module_detail

        functions = [
            {
                "id": "login",
                "business_name": "用户登录",
                "code_name": "login",
                "file_path": "auth.py",
                "line_start": 10,
                "explanation": "校验邮箱密码",
                "params": [{"name": "email", "type": "str"}],
                "return_type": "dict",
            },
        ]

        nodes, edges = layout_module_detail(functions, callers_map={}, callees_map={})

        assert len(nodes) == 1
        node = nodes[0]
        assert node.business_name == "用户登录"
        assert node.explanation == "校验邮箱密码"
        assert node.width == 280
        assert node.height == 140

    def test_internal_call_edges(self) -> None:
        """Callees map should produce edges with correct from/to ids."""
        from src.tools.canvas_layout import layout_module_detail

        functions = [
            {
                "id": "register",
                "business_name": "注册",
                "code_name": "register",
                "file_path": "auth.py",
                "line_start": 20,
                "explanation": "注册新用户",
                "params": [],
                "return_type": "dict",
            },
            {
                "id": "save_user",
                "business_name": "保存用户",
                "code_name": "save_user",
                "file_path": "db.py",
                "line_start": 5,
                "explanation": "写入数据库",
                "params": [],
                "return_type": "int",
            },
        ]
        callees_map = {
            "register": ["save_user"],
        }

        nodes, edges = layout_module_detail(functions, callers_map={}, callees_map=callees_map)

        assert len(edges) == 1
        assert edges[0].from_id == "register"
        assert edges[0].to_id == "save_user"

    def test_cross_module_callee_format(self) -> None:
        """Callee in 'module/func' format should match by the func part."""
        from src.tools.canvas_layout import layout_module_detail

        functions = [
            {
                "id": "handler",
                "business_name": "处理器",
                "code_name": "handler",
                "file_path": "api.py",
                "line_start": 1,
                "explanation": "处理请求",
                "params": [],
                "return_type": "None",
            },
            {
                "id": "validate",
                "business_name": "验证",
                "code_name": "validate",
                "file_path": "utils.py",
                "line_start": 1,
                "explanation": "验证输入",
                "params": [],
                "return_type": "bool",
            },
        ]
        callees_map = {
            "handler": ["utils/validate"],
        }

        _, edges = layout_module_detail(functions, callers_map={}, callees_map=callees_map)

        assert len(edges) == 1
        assert edges[0].to_id == "validate"

    def test_grid_layout_positions(self) -> None:
        """Functions should be laid out in a grid with 3 columns."""
        from src.tools.canvas_layout import layout_module_detail

        functions = [
            {
                "id": f"fn_{i}",
                "business_name": f"函数{i}",
                "code_name": f"fn_{i}",
                "file_path": "mod.py",
                "line_start": i * 10,
                "explanation": "",
                "params": [],
                "return_type": "None",
            }
            for i in range(5)
        ]

        nodes, _ = layout_module_detail(functions, callers_map={}, callees_map={})

        # First row: fn_0, fn_1, fn_2  — same y
        assert nodes[0].y == nodes[1].y == nodes[2].y
        # Second row: fn_3, fn_4 — same y, different from first row
        assert nodes[3].y == nodes[4].y
        assert nodes[3].y > nodes[0].y
        # Columns: fn_0.x < fn_1.x < fn_2.x
        assert nodes[0].x < nodes[1].x < nodes[2].x


# ── Flow line layout tests ────────────────────────────────


class TestLayoutFlows:
    """Tests for layout_flows(flows)."""

    def test_single_flow(self) -> None:
        """A single flow with 3 steps should produce 3 nodes in one row."""
        from src.tools.canvas_layout import layout_flows

        flows = [
            {
                "name": "用户消息处理",
                "description": "接收并处理用户输入",
                "steps": ["接收消息", "理解意图", "执行返回"],
            }
        ]

        result = layout_flows(flows)

        assert len(result) == 1
        fl = result[0]
        assert fl.name == "用户消息处理"
        assert len(fl.nodes) == 3
        assert fl.nodes[0].text == "接收消息"
        assert fl.nodes[1].text == "理解意图"
        assert fl.nodes[2].text == "执行返回"
        # All nodes same y (single row)
        assert fl.nodes[0].y == fl.nodes[1].y == fl.nodes[2].y
        # Nodes left-to-right
        assert fl.nodes[0].x < fl.nodes[1].x < fl.nodes[2].x

    def test_multiple_flows_vertical(self) -> None:
        """Multiple flows should be arranged top-to-bottom with increasing y."""
        from src.tools.canvas_layout import layout_flows

        flows = [
            {"name": "流程A", "description": "", "steps": ["步骤1"]},
            {"name": "流程B", "description": "", "steps": ["步骤1"]},
            {"name": "流程C", "description": "", "steps": ["步骤1"]},
        ]

        result = layout_flows(flows)

        assert len(result) == 3
        y_values = [fl.nodes[0].y for fl in result]
        assert y_values[0] < y_values[1] < y_values[2]

    def test_step_connections(self) -> None:
        """Consecutive steps should be connected."""
        from src.tools.canvas_layout import layout_flows

        flows = [
            {"name": "流程", "description": "", "steps": ["A", "B", "C", "D"]},
        ]

        result = layout_flows(flows)

        fl = result[0]
        assert len(fl.connections) == 3
        assert fl.connections[0].from_id == "flow_0_step_0"
        assert fl.connections[0].to_id == "flow_0_step_1"
        assert fl.connections[1].from_id == "flow_0_step_1"
        assert fl.connections[1].to_id == "flow_0_step_2"
        assert fl.connections[2].from_id == "flow_0_step_2"
        assert fl.connections[2].to_id == "flow_0_step_3"

    def test_flow_colors(self) -> None:
        """Different flows should have different colors; first is #6366f1."""
        from src.tools.canvas_layout import layout_flows

        flows = [
            {"name": f"流程{i}", "description": "", "steps": ["步骤"]}
            for i in range(5)
        ]

        result = layout_flows(flows)

        assert result[0].color == "#6366f1"
        assert result[1].color == "#10b981"
        assert result[2].color == "#f59e0b"
        assert result[3].color == "#3b82f6"
        assert result[4].color == "#ef4444"
        # All colors unique
        colors = [fl.color for fl in result]
        assert len(set(colors)) == 5

    def test_empty_flows(self) -> None:
        """Empty flows list should return empty result."""
        from src.tools.canvas_layout import layout_flows

        assert layout_flows([]) == []

    def test_node_dimensions(self) -> None:
        """Flow step nodes should have width 200 and height 50."""
        from src.tools.canvas_layout import layout_flows

        flows = [{"name": "流程", "description": "", "steps": ["步骤"]}]
        result = layout_flows(flows)
        node = result[0].nodes[0]
        assert node.width == 200
        assert node.height == 50
