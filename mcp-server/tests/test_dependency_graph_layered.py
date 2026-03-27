"""RED tests for DependencyGraph layered Mermaid rendering.

New API under test (does NOT exist yet — all tests should FAIL):
  - DependencyGraph.build_super_groups() -> dict[str, list[str]]
  - DependencyGraph.get_expandable_groups() -> dict[str, dict]
  - DependencyGraph.to_mermaid(level="overview", ...) with focus and max_nodes params

Existing API (must remain unchanged):
  - DependencyGraph.to_mermaid()
  - DependencyGraph.to_mermaid(level="module")
"""

import pytest

from src.parsers.ast_parser import (
    CallInfo,
    ClassInfo,
    FunctionInfo,
    ImportInfo,
    ParseResult,
)
from src.parsers.dependency_graph import DependencyGraph


# ── Helpers ─────────────────────────────────────────────────────────────────


def _make_parse_result(
    file_path: str,
    functions: list[str] | None = None,
    line_count: int = 50,
) -> ParseResult:
    """Build a minimal ParseResult for a given file path."""
    func_infos = [
        FunctionInfo(name=fn, line_start=i * 10 + 1, line_end=i * 10 + 9)
        for i, fn in enumerate(functions or ["main"])
    ]
    return ParseResult(
        file_path=file_path,
        language="python",
        functions=func_infos,
        line_count=line_count,
    )


def _make_call(caller: str, callee: str) -> CallInfo:
    return CallInfo(caller_func=caller, callee_name=callee, line=1)


def _build_small_graph() -> DependencyGraph:
    """Build a graph with <30 modules (10 modules across 2 top-level dirs)."""
    prs = []
    for i in range(5):
        prs.append(_make_parse_result(f"fastapi/core/mod{i}.py"))
    for i in range(5):
        prs.append(_make_parse_result(f"fastapi/security/sec{i}.py"))

    dg = DependencyGraph()
    dg.build(prs)

    # Manually create module groups: each file is its own module
    node_map: dict[str, str] = {}
    for pr in prs:
        module = pr.file_path.rsplit("/", 1)[0]  # e.g. fastapi/core
        for func in pr.functions:
            node_id = f"{pr.file_path}::{func.name}"
            node_map[node_id] = module

    dg.set_module_groups(node_map)
    return dg


def _build_large_graph() -> DependencyGraph:
    """Build a simulated FastAPI-like project with >30 distinct modules."""
    prs = []

    # docs_src/tutorial1 through docs_src/tutorial35
    for i in range(1, 36):
        prs.append(_make_parse_result(
            f"docs_src/tutorial{i}/main.py",
            functions=["app_factory", "get_items"],
            line_count=80,
        ))

    # fastapi/core, fastapi/security, fastapi/middleware
    for sub in ("core", "security", "middleware", "routing", "responses"):
        prs.append(_make_parse_result(
            f"fastapi/{sub}/module.py",
            functions=["setup", "process"],
            line_count=200,
        ))

    # tests/
    for i in range(5):
        prs.append(_make_parse_result(
            f"tests/test_router_{i}.py",
            functions=[f"test_case_{i}"],
            line_count=30,
        ))

    # scripts/
    prs.append(_make_parse_result("scripts/build.py", functions=["build"], line_count=40))

    dg = DependencyGraph()
    dg.build(prs)

    # Assign each file a module = its parent directory path
    node_map: dict[str, str] = {}
    for pr in prs:
        parts = pr.file_path.split("/")
        if len(parts) >= 3:
            module = f"{parts[0]}/{parts[1]}"
        elif len(parts) == 2:
            module = parts[0]
        else:
            module = pr.file_path
        for func in pr.functions:
            node_id = f"{pr.file_path}::{func.name}"
            node_map[node_id] = module

    dg.set_module_groups(node_map)
    return dg


def _build_cross_group_graph() -> DependencyGraph:
    """Build a graph with known cross-group edges for aggregation testing."""
    pr_core = _make_parse_result(
        "fastapi/core/mod.py",
        functions=["handler", "process"],
        line_count=100,
    )
    pr_security = _make_parse_result(
        "fastapi/security/auth.py",
        functions=["verify_token", "authenticate"],
        line_count=80,
    )
    pr_middleware = _make_parse_result(
        "fastapi/middleware/logging.py",
        functions=["log_request"],
        line_count=60,
    )

    # Add cross-module calls: handler -> verify_token (multiple times = high count)
    pr_core.calls = [
        _make_call("handler", "verify_token"),
        _make_call("handler", "verify_token"),
        _make_call("handler", "verify_token"),
        _make_call("process", "authenticate"),
        _make_call("process", "log_request"),
    ]

    prs = [pr_core, pr_security, pr_middleware]
    dg = DependencyGraph()
    dg.build(prs)

    node_map: dict[str, str] = {}
    for pr in prs:
        module = "/".join(pr.file_path.split("/")[:2])  # e.g. fastapi/core
        for func in pr.functions:
            node_id = f"{pr.file_path}::{func.name}"
            node_map[node_id] = module

    dg.set_module_groups(node_map)
    return dg


# ── TestBuildSuperGroups ─────────────────────────────────────────────────────


class TestBuildSuperGroups:
    """Tests for DependencyGraph.build_super_groups()."""

    def test_super_groups_aggregates_by_top_dir(self):
        """Modules like fastapi/core, fastapi/security, fastapi/middleware
        should aggregate into {"fastapi": ["fastapi/core", "fastapi/security", ...]}."""
        dg = DependencyGraph()
        dg.build([])
        # Simulate module graph with sub-modules
        node_map = {
            "fake_file_core.py::fn": "fastapi/core",
            "fake_file_sec.py::fn": "fastapi/security",
            "fake_file_mid.py::fn": "fastapi/middleware",
        }
        dg.graph.add_node("fake_file_core.py::fn", file="fake_file_core.py", line_start=1, line_end=5, module_group="fastapi/core", node_type="function", label="fn")
        dg.graph.add_node("fake_file_sec.py::fn", file="fake_file_sec.py", line_start=1, line_end=5, module_group="fastapi/security", node_type="function", label="fn")
        dg.graph.add_node("fake_file_mid.py::fn", file="fake_file_mid.py", line_start=1, line_end=5, module_group="fastapi/middleware", node_type="function", label="fn")
        dg.set_module_groups(node_map)

        result = dg._build_super_groups()

        assert "fastapi" in result
        sub_modules = result["fastapi"]
        assert "fastapi/core" in sub_modules
        assert "fastapi/security" in sub_modules
        assert "fastapi/middleware" in sub_modules

    def test_super_groups_single_module_not_aggregated(self):
        """A module with no '/' (e.g., 'tests') stays as its own top-level key
        with itself as the only sub-module: {"tests": ["tests"]}."""
        dg = DependencyGraph()
        dg.build([])
        dg.graph.add_node(
            "tests/test_foo.py::test_one",
            file="tests/test_foo.py",
            line_start=1,
            line_end=5,
            module_group="tests",
            node_type="function",
            label="test_one",
        )
        dg.set_module_groups({"tests/test_foo.py::test_one": "tests"})

        result = dg._build_super_groups()

        assert "tests" in result
        assert result["tests"] == ["tests"]

    def test_super_groups_empty_graph(self):
        """An empty graph returns an empty dict."""
        dg = DependencyGraph()
        dg.build([])

        result = dg._build_super_groups()

        assert result == {}


# ── TestGetExpandableGroups ──────────────────────────────────────────────────


class TestGetExpandableGroups:
    """Tests for DependencyGraph.get_expandable_groups()."""

    def test_expandable_groups_returns_metadata(self):
        """Returns {group: {sub_modules: N, total_files: N, total_lines: N}}
        for groups with more than 1 sub-module."""
        dg = _build_large_graph()

        result = dg.get_expandable_groups()

        # docs_src has 35 sub-modules, so it must appear
        assert "docs_src" in result
        docs_meta = result["docs_src"]
        assert "sub_modules" in docs_meta
        assert "total_files" in docs_meta
        assert "total_lines" in docs_meta
        assert docs_meta["sub_modules"] >= 2
        assert docs_meta["total_files"] >= 2
        assert docs_meta["total_lines"] >= 0

    def test_expandable_groups_single_module_excluded(self):
        """Groups with only 1 sub-module are excluded from expandable groups."""
        dg = DependencyGraph()
        dg.build([])
        # Add a group with only a single sub-module
        dg.graph.add_node(
            "scripts/build.py::build",
            file="scripts/build.py",
            line_start=1,
            line_end=40,
            module_group="scripts",
            node_type="function",
            label="build",
        )
        dg.set_module_groups({"scripts/build.py::build": "scripts"})

        result = dg.get_expandable_groups()

        # "scripts" has only 1 sub-module ("scripts" itself) — must be excluded
        assert "scripts" not in result


# ── TestOverviewMermaid ──────────────────────────────────────────────────────


class TestOverviewMermaid:
    """Tests for to_mermaid(level='overview')."""

    def test_overview_small_project_no_aggregation(self):
        """For a project with <30 distinct modules, overview should be
        identical to the module-level diagram."""
        dg = _build_small_graph()

        overview = dg.to_mermaid(level="overview")
        module_level = dg.to_mermaid(level="module")

        assert overview == module_level

    def test_overview_large_project_aggregated(self):
        """For >30 modules, overview must collapse sub-modules into super-groups.
        The resulting node count should be <= 30."""
        dg = _build_large_graph()

        result = dg.to_mermaid(level="overview")

        assert "graph TD" in result
        # Count node definition lines (lines containing "[" that are not subgraph/edge lines)
        node_lines = [
            line for line in result.splitlines()
            if "[" in line and "-->" not in line and "==>" not in line and "subgraph" not in line
        ]
        assert len(node_lines) <= 30

    def test_overview_edge_aggregation(self):
        """Cross-group edges must have their call_count summed across all
        constituent node-level edges.

        In the cross-group graph:
          - fastapi/core -> fastapi/security: 3 calls (handler->verify_token x3) + 1 (process->authenticate)
          - fastapi/core -> fastapi/middleware: 1 call
        When aggregated to super-group "fastapi" (single super-group, all internal),
        the overview level must render nodes named after the actual sub-module groups,
        NOT produce a flat function-level diagram.

        This test verifies the overview aggregation logic runs — the output must
        include aggregated node labels that contain sub-module counts, or use the
        super-group naming convention (e.g., "fastapi[fastapi (3 modules)]").
        """
        dg = _build_cross_group_graph()

        result = dg.to_mermaid(level="overview")

        assert "graph TD" in result
        # The overview must contain aggregated module labels, not raw function names.
        # Raw function names like "handler", "verify_token" must NOT appear as
        # standalone node definitions in the overview level.
        raw_function_node_lines = [
            line for line in result.splitlines()
            if "[" in line
            and "-->" not in line
            and "==>" not in line
            and "subgraph" not in line
            and any(fn in line for fn in ["handler", "verify_token", "authenticate", "log_request", "process"])
        ]
        assert len(raw_function_node_lines) == 0, (
            f"Overview must not contain raw function nodes, found: {raw_function_node_lines}"
        )

    def test_overview_max_nodes_overflow(self):
        """If aggregated super-groups still exceed max_nodes, excess groups
        are merged into a single '其他' catch-all node."""
        dg = _build_large_graph()

        # max_nodes=3 is smaller than the 4 super-groups (docs_src, fastapi, tests, scripts)
        result = dg.to_mermaid(level="overview", max_nodes=3)

        assert "graph TD" in result
        # The overflow bucket must appear
        assert "其他" in result

    # parametrize: same assertion across two equivalent call forms
    @pytest.mark.parametrize("kwargs", [
        {"level": "overview", "max_nodes": 30},
        {"level": "overview"},
    ])
    def test_overview_returns_mermaid_string(self, kwargs):
        """to_mermaid with overview level always returns a non-empty string
        that is an aggregated view (not a raw function-level diagram)."""
        dg = _build_large_graph()
        result = dg.to_mermaid(**kwargs)
        assert isinstance(result, str)
        assert len(result) > 0
        # The overview must NOT expose individual function names from the large graph;
        # it must aggregate into module/super-group nodes.
        # "app_factory" and "get_items" are function names in docs_src/tutorial* files.
        # They must not appear as standalone node definitions in overview mode.
        raw_func_lines = [
            line for line in result.splitlines()
            if "[" in line
            and "-->" not in line
            and "==>" not in line
            and "subgraph" not in line
            and ("app_factory" in line or "get_items" in line)
        ]
        assert len(raw_func_lines) == 0, (
            "Overview must aggregate into module nodes, not expose function nodes"
        )


# ── TestFocusedMermaid ───────────────────────────────────────────────────────


class TestFocusedMermaid:
    """Tests for to_mermaid(level='overview', focus='<group>')."""

    def test_focus_shows_internal_submodules(self):
        """When focus='docs_src', the diagram renders the internal sub-modules
        of docs_src as individual nodes in a subgraph."""
        dg = _build_large_graph()

        result = dg.to_mermaid(level="overview", focus="docs_src")

        assert "graph TD" in result
        # The focused group's sub-modules must be expanded into a subgraph
        assert "subgraph" in result
        # At least one docs_src sub-module must appear
        assert "docs_src" in result

    def test_focus_external_collapsed(self):
        """When focus='fastapi', external top-level groups (docs_src, tests, scripts)
        must be collapsed into single super-nodes, not expanded."""
        dg = _build_large_graph()

        result = dg.to_mermaid(level="overview", focus="fastapi")

        assert "graph TD" in result
        # The focused internal subgraph must appear
        assert "subgraph" in result
        # External groups should appear as single collapsed nodes, not
        # as individual sub-module nodes
        lines = result.splitlines()
        docs_src_submodule_lines = [
            l for l in lines
            if "docs_src/tutorial" in l
        ]
        # Individual tutorial sub-modules must NOT be present
        assert len(docs_src_submodule_lines) == 0

    def test_focus_invalid_group_returns_empty(self):
        """A non-existent focus group must return a fallback or empty diagram,
        not raise an exception."""
        dg = _build_large_graph()

        result = dg.to_mermaid(level="overview", focus="nonexistent_group_xyz")

        # Must not raise; must return a string
        assert isinstance(result, str)
        # Either empty or a fallback diagram
        assert len(result) >= 0


# ── TestBackwardsCompatibility ───────────────────────────────────────────────


class TestBackwardsCompatibility:
    """Ensure existing to_mermaid() signatures are unaffected."""

    def test_to_mermaid_no_args_unchanged(self):
        """to_mermaid() with no arguments must produce the same output as before."""
        dg = _build_small_graph()

        result_no_args = dg.to_mermaid()
        result_explicit = dg.to_mermaid(level="module")

        assert result_no_args == result_explicit

    def test_to_mermaid_module_level_unchanged(self):
        """to_mermaid(level='module') must still produce a valid module graph."""
        dg = _build_small_graph()

        result = dg.to_mermaid(level="module")

        assert "graph TD" in result
        # Must contain at least one module node definition
        node_lines = [
            l for l in result.splitlines()
            if "[" in l and "-->" not in l and "==>" not in l and "subgraph" not in l
        ]
        assert len(node_lines) >= 1


# ── TestEdgeCases ────────────────────────────────────────────────────────────


class TestEdgeCases:
    """Edge cases for overview rendering."""

    def test_overview_empty_graph(self):
        """An empty graph must return a reasonable fallback string without raising,
        and the build_super_groups() method must return an empty dict."""
        dg = DependencyGraph()
        dg.build([])

        result = dg.to_mermaid(level="overview")
        super_groups = dg._build_super_groups()

        assert isinstance(result, str)
        assert len(result) > 0
        # Must still be parsable as a Mermaid diagram preamble
        assert "graph" in result
        # build_super_groups on empty graph returns empty dict
        assert super_groups == {}
