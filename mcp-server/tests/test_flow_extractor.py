"""Tests for flow_extractor — business flow skeleton extraction."""

from dataclasses import dataclass, field

import networkx as nx
import pytest

from src.parsers.ast_parser import (
    CallInfo,
    ClassInfo,
    FunctionInfo,
    ImportInfo,
    ParseResult,
)
from src.parsers.dependency_graph import DependencyGraph
from src.parsers.module_grouper import ModuleGroup
from src.parsers.repo_cloner import CloneResult
from src.summarizer.engine import SummaryContext
from src.summarizer.flow_extractor import (
    BusinessFlow,
    FlowExtractionResult,
    FlowStep,
    extract_flows,
    _assign_branch_flows,
    _find_entry_nodes,
    _infer_flow_name,
    _path_to_flow,
    _score_path,
    _select_main_flows,
    _trace_paths,
)


# ── Helpers ──────────────────────────────────────────────────


def _make_graph_with_chain() -> DependencyGraph:
    """Build a small graph: server module with main → handle_request → check_auth → query_db.

    Also adds a branch: handle_request → send_response.
    """
    dg = DependencyGraph()
    g = dg.graph

    # Nodes — server module
    g.add_node("server.py::main", file="server.py", line_start=1, line_end=10,
               module_group="server", node_type="function", label="main")
    g.add_node("server.py::handle_request", file="server.py", line_start=12, line_end=30,
               module_group="server", node_type="function", label="handle_request")
    g.add_node("server.py::send_response", file="server.py", line_start=32, line_end=45,
               module_group="server", node_type="function", label="send_response")

    # Nodes — auth module
    g.add_node("auth.py::check_auth", file="auth.py", line_start=1, line_end=20,
               module_group="auth", node_type="function", label="check_auth")

    # Nodes — db module
    g.add_node("db.py::query_db", file="db.py", line_start=1, line_end=15,
               module_group="db", node_type="function", label="query_db")

    # Edges — main chain
    g.add_edge("server.py::main", "server.py::handle_request",
               data_label="", call_count=5, is_critical_path=True)
    g.add_edge("server.py::handle_request", "auth.py::check_auth",
               data_label="校验", call_count=3, is_critical_path=False)
    g.add_edge("auth.py::check_auth", "db.py::query_db",
               data_label="查询数据", call_count=2, is_critical_path=False)

    # Edges — branch
    g.add_edge("server.py::handle_request", "server.py::send_response",
               data_label="发送", call_count=4, is_critical_path=False)

    return dg


def _make_modules() -> list[ModuleGroup]:
    return [
        ModuleGroup(
            name="server",
            dir_path="server",
            files=["server.py"],
            entry_functions=["main"],
            total_lines=45,
        ),
        ModuleGroup(
            name="auth",
            dir_path="auth",
            files=["auth.py"],
            entry_functions=[],
            total_lines=20,
        ),
        ModuleGroup(
            name="db",
            dir_path="db",
            files=["db.py"],
            entry_functions=[],
            total_lines=15,
        ),
    ]


def _make_parse_results() -> list[ParseResult]:
    return [
        ParseResult(
            file_path="server.py",
            language="python",
            functions=[
                FunctionInfo(name="main", params=[], line_start=1, line_end=10),
                FunctionInfo(name="handle_request", params=["request"], line_start=12, line_end=30),
                FunctionInfo(name="send_response", params=["response"], line_start=32, line_end=45),
            ],
            calls=[
                CallInfo(caller_func="main", callee_name="handle_request"),
                CallInfo(caller_func="handle_request", callee_name="check_auth"),
                CallInfo(caller_func="handle_request", callee_name="send_response"),
                CallInfo(caller_func="check_auth", callee_name="query_db"),
            ],
            line_count=45,
        ),
        ParseResult(
            file_path="auth.py",
            language="python",
            functions=[
                FunctionInfo(name="check_auth", params=["token"], line_start=1, line_end=20),
            ],
            calls=[
                CallInfo(caller_func="check_auth", callee_name="query_db"),
            ],
            line_count=20,
        ),
        ParseResult(
            file_path="db.py",
            language="python",
            functions=[
                FunctionInfo(name="query_db", params=["sql"], line_start=1, line_end=15),
            ],
            calls=[],
            line_count=15,
        ),
    ]


def _make_context() -> SummaryContext:
    return SummaryContext(
        clone_result=CloneResult(repo_path="/tmp/test-repo", total_lines=80),
        parse_results=_make_parse_results(),
        modules=_make_modules(),
        dep_graph=_make_graph_with_chain(),
        role="pm",
        repo_url="https://github.com/test/test-repo",
    )


# ── TestFindEntryNodes ───────────────────────────────────────


class TestFindEntryNodes:
    def test_finds_main_function(self):
        ctx = _make_context()
        entries = _find_entry_nodes(ctx)
        assert "server.py::main" in entries

    def test_finds_zero_indegree_nodes(self):
        """Nodes with no incoming edges should be candidates."""
        ctx = _make_context()
        entries = _find_entry_nodes(ctx)
        # main has in-degree 0
        assert "server.py::main" in entries

    def test_recognises_handle_pattern(self):
        """Functions matching entry patterns (handle_*) should be candidates."""
        ctx = _make_context()
        entries = _find_entry_nodes(ctx)
        assert "server.py::handle_request" in entries

    def test_no_duplicates(self):
        ctx = _make_context()
        entries = _find_entry_nodes(ctx)
        assert len(entries) == len(set(entries))


# ── TestTracePaths ───────────────────────────────────────────


class TestTracePaths:
    def test_linear_chain(self):
        """A → B → C → D should produce at least one path containing all four."""
        dg = _make_graph_with_chain()
        paths = _trace_paths(dg.graph, ["server.py::main"])
        # Should have the main chain: main → handle → check_auth → query_db
        long_paths = [p for p in paths if len(p) >= 4]
        assert len(long_paths) >= 1
        assert long_paths[0][0] == "server.py::main"

    def test_branch_produces_multiple_paths(self):
        """handle_request has two successors, so we should get ≥ 2 paths."""
        dg = _make_graph_with_chain()
        paths = _trace_paths(dg.graph, ["server.py::main"])
        assert len(paths) >= 2

    def test_cycle_does_not_hang(self):
        """A graph with a cycle should still terminate."""
        dg = DependencyGraph()
        g = dg.graph
        g.add_node("a.py::a", file="a.py", line_start=1, line_end=5,
                    module_group="m", node_type="function", label="a")
        g.add_node("b.py::b", file="b.py", line_start=1, line_end=5,
                    module_group="m", node_type="function", label="b")
        g.add_node("c.py::c", file="c.py", line_start=1, line_end=5,
                    module_group="m", node_type="function", label="c")
        g.add_edge("a.py::a", "b.py::b", data_label="", call_count=1, is_critical_path=False)
        g.add_edge("b.py::b", "c.py::c", data_label="", call_count=1, is_critical_path=False)
        g.add_edge("c.py::c", "a.py::a", data_label="", call_count=1, is_critical_path=False)

        paths = _trace_paths(g, ["a.py::a"])
        # Should terminate; paths should not be empty
        assert len(paths) >= 1
        # No path should revisit a node
        for p in paths:
            assert len(p) == len(set(p))

    def test_depth_limit(self):
        """Paths should not exceed the depth limit."""
        dg = _make_graph_with_chain()
        paths = _trace_paths(dg.graph, ["server.py::main"], max_depth=2)
        for p in paths:
            assert len(p) <= 3  # depth=2 means at most 3 nodes (entry + 2 hops)


# ── TestSelectMainFlows ──────────────────────────────────────


class TestSelectMainFlows:
    def test_selects_non_overlapping_paths(self):
        paths = [
            ["a", "b", "c", "d"],
            ["a", "b", "e", "f"],
            ["x", "y", "z"],
        ]
        scores = [10.0, 8.0, 6.0]
        selected = _select_main_flows(paths, scores, max_flows=3)
        assert len(selected) >= 2

    def test_max_five_flows(self):
        paths = [["a", "b", "c"] for _ in range(10)]
        scores = [float(i) for i in range(10, 0, -1)]
        selected = _select_main_flows(paths, scores, max_flows=5)
        assert len(selected) <= 5

    def test_short_paths_ignored(self):
        """Paths shorter than 3 nodes should be excluded."""
        paths = [
            ["a", "b"],  # too short
            ["c", "d", "e", "f"],  # ok
        ]
        scores = [10.0, 5.0]
        selected = _select_main_flows(paths, scores)
        assert len(selected) == 1
        assert selected[0] == ["c", "d", "e", "f"]


# ── TestExtractFlows (end-to-end) ────────────────────────────


class TestExtractFlows:
    def test_main_flows_not_empty(self):
        ctx = _make_context()
        result = extract_flows(ctx)
        assert isinstance(result, FlowExtractionResult)
        assert len(result.main_flows) >= 1

    def test_step_descriptions_are_business_language(self):
        """business_description should not contain function names or file paths."""
        ctx = _make_context()
        result = extract_flows(ctx)
        for flow in result.main_flows:
            for step in flow.steps:
                assert step.business_description, "description must not be empty"
                # Should not contain raw function names or file paths
                assert "::" not in step.business_description
                assert ".py" not in step.business_description

    def test_flow_name_is_business_language(self):
        ctx = _make_context()
        result = extract_flows(ctx)
        for flow in result.main_flows:
            assert flow.name, "flow name must not be empty"
            assert "::" not in flow.name
            assert ".py" not in flow.name

    def test_coverage_positive(self):
        ctx = _make_context()
        result = extract_flows(ctx)
        assert result.coverage > 0

    def test_project_name_set(self):
        ctx = _make_context()
        result = extract_flows(ctx)
        assert result.project_name
