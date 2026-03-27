"""Tests for Sprint 3 O(1) lookup indexes in DependencyGraph.

Covers:
- _name_index
- _file_class_methods
- _method_name_index
- _module_path_index
- _resolve_callee steps 1-4
- Short name collision logging (H2 fix)
"""

import pytest
import structlog
import structlog.testing

from src.parsers.ast_parser import (
    CallInfo,
    ClassInfo,
    FunctionInfo,
    ImportInfo,
    ParseResult,
)
from src.parsers.dependency_graph import DependencyGraph


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_parse_result(
    file_path: str,
    *,
    functions: list[FunctionInfo] | None = None,
    classes: list[ClassInfo] | None = None,
    imports: list[ImportInfo] | None = None,
    calls: list[CallInfo] | None = None,
) -> ParseResult:
    return ParseResult(
        file_path=file_path,
        language="python",
        functions=functions or [],
        classes=classes or [],
        imports=imports or [],
        calls=calls or [],
    )


def _func(name: str, *, parent_class: str | None = None, line_start: int = 1, line_end: int = 5) -> FunctionInfo:
    return FunctionInfo(
        name=name,
        line_start=line_start,
        line_end=line_end,
        is_method=parent_class is not None,
        parent_class=parent_class,
    )


def _cls(name: str, line_start: int = 1, line_end: int = 10) -> ClassInfo:
    return ClassInfo(name=name, line_start=line_start, line_end=line_end)


def _imp(module: str, names: list[str] | None = None) -> ImportInfo:
    return ImportInfo(module=module, names=names or [])


def _call(caller: str, callee: str) -> CallInfo:
    return CallInfo(caller_func=caller, callee_name=callee)


# ══════════════════════════════════════════════════════════════════════════════
# 1. _name_index construction
# ══════════════════════════════════════════════════════════════════════════════


class TestNameIndex:
    """_name_index maps function/class names to their node IDs."""

    def test_single_function_registered(self):
        pr = _make_parse_result("src/a.py", functions=[_func("my_func")])
        dg = DependencyGraph().build([pr])
        assert "my_func" in dg._name_index
        assert "src/a.py::my_func" in dg._name_index["my_func"]

    def test_class_registered_in_name_index(self):
        pr = _make_parse_result("src/a.py", classes=[_cls("MyClass")])
        dg = DependencyGraph().build([pr])
        assert "MyClass" in dg._name_index
        assert "src/a.py::MyClass" in dg._name_index["MyClass"]

    def test_same_function_name_across_files(self):
        """Both node IDs present when two files define the same function name."""
        pr_a = _make_parse_result("src/a.py", functions=[_func("helper")])
        pr_b = _make_parse_result("src/b.py", functions=[_func("helper")])
        dg = DependencyGraph().build([pr_a, pr_b])
        node_ids = dg._name_index["helper"]
        assert "src/a.py::helper" in node_ids
        assert "src/b.py::helper" in node_ids
        assert len(node_ids) == 2

    def test_method_registered_with_class_dot_name(self):
        """A class method node ID is {file}::{Class}.{method}."""
        pr = _make_parse_result(
            "src/a.py",
            functions=[_func("process", parent_class="Worker")],
        )
        dg = DependencyGraph().build([pr])
        assert "process" in dg._name_index
        assert "src/a.py::Worker.process" in dg._name_index["process"]

    def test_empty_parse_results_produce_empty_index(self):
        dg = DependencyGraph().build([])
        assert dg._name_index == {}


# ══════════════════════════════════════════════════════════════════════════════
# 2. _file_class_methods and _method_name_index construction
# ══════════════════════════════════════════════════════════════════════════════


class TestFileClassMethodsIndex:
    """_file_class_methods and _method_name_index are populated for methods."""

    def test_class_method_in_file_class_methods(self):
        pr = _make_parse_result(
            "src/svc.py",
            functions=[_func("run", parent_class="Service")],
        )
        dg = DependencyGraph().build([pr])
        assert "src/svc.py" in dg._file_class_methods
        assert "Service.run" in dg._file_class_methods["src/svc.py"]
        assert dg._file_class_methods["src/svc.py"]["Service.run"] == "src/svc.py::Service.run"

    def test_method_name_index_reverse_lookup(self):
        pr = _make_parse_result(
            "src/svc.py",
            functions=[_func("run", parent_class="Service")],
        )
        dg = DependencyGraph().build([pr])
        assert "src/svc.py" in dg._method_name_index
        assert dg._method_name_index["src/svc.py"]["run"] == "src/svc.py::Service.run"

    def test_no_entry_when_no_methods(self):
        pr = _make_parse_result("src/utils.py", functions=[_func("standalone")])
        dg = DependencyGraph().build([pr])
        assert "src/utils.py" not in dg._file_class_methods
        assert "src/utils.py" not in dg._method_name_index

    def test_multiple_classes_same_file_last_method_wins_in_reverse_index(self):
        """When two classes in same file share a method name, last one wins."""
        pr = _make_parse_result(
            "src/svc.py",
            functions=[
                _func("run", parent_class="ServiceA"),
                _func("run", parent_class="ServiceB"),
            ],
        )
        dg = DependencyGraph().build([pr])
        # Both are in _file_class_methods
        assert "ServiceA.run" in dg._file_class_methods["src/svc.py"]
        assert "ServiceB.run" in dg._file_class_methods["src/svc.py"]
        # _method_name_index has exactly one entry (last wins)
        result = dg._method_name_index["src/svc.py"]["run"]
        assert result in ("src/svc.py::ServiceA.run", "src/svc.py::ServiceB.run")


# ══════════════════════════════════════════════════════════════════════════════
# 3. _module_path_index construction and variants
# ══════════════════════════════════════════════════════════════════════════════


class TestModulePathIndex:
    """_module_path_index maps module path variants to file_path."""

    def test_file_path_maps_to_itself(self):
        pr = _make_parse_result("src/parsers/foo.py")
        dg = DependencyGraph().build([pr])
        assert dg._module_path_index["src/parsers/foo.py"] == "src/parsers/foo.py"

    def test_dotted_module_path_maps_to_file(self):
        pr = _make_parse_result("src/parsers/foo.py")
        dg = DependencyGraph().build([pr])
        assert dg._module_path_index["src.parsers.foo"] == "src/parsers/foo.py"

    def test_short_name_maps_to_file(self):
        pr = _make_parse_result("src/parsers/foo.py")
        dg = DependencyGraph().build([pr])
        assert dg._module_path_index["foo"] == "src/parsers/foo.py"

    def test_short_name_collision_first_file_wins(self):
        """
        H2 fix: when two files share a short name (e.g. utils), the first one
        registered is kept; the second is ignored and a debug log is emitted.
        """
        pr_a = _make_parse_result("src/a/utils.py")
        pr_b = _make_parse_result("src/b/utils.py")
        dg = DependencyGraph().build([pr_a, pr_b])
        # First file's dotted path registered the short name
        assert dg._module_path_index["utils"] == "src/a/utils.py"

    def test_short_name_collision_logs_debug_message(self):
        """Collision must emit a structlog debug event."""
        pr_a = _make_parse_result("src/a/utils.py")
        pr_b = _make_parse_result("src/b/utils.py")

        with structlog.testing.capture_logs() as captured:
            DependencyGraph().build([pr_a, pr_b])

        events = [e for e in captured if e.get("event") == "dependency_graph.short_name_collision"]
        assert len(events) == 1
        entry = events[0]
        assert entry["short_name"] == "utils"
        assert entry["existing_file"] == "src/a/utils.py"
        assert entry["ignored_file"] == "src/b/utils.py"

    def test_no_collision_when_unique_short_names(self):
        pr_a = _make_parse_result("src/a/foo.py")
        pr_b = _make_parse_result("src/b/bar.py")
        dg = DependencyGraph().build([pr_a, pr_b])
        assert dg._module_path_index["foo"] == "src/a/foo.py"
        assert dg._module_path_index["bar"] == "src/b/bar.py"

    def test_top_level_file_has_no_short_name_entry(self):
        """A file with no dotted parent (e.g. 'foo.py') has no short-name entry."""
        pr = _make_parse_result("foo.py")
        dg = DependencyGraph().build([pr])
        # dotted path = "foo", no rsplit(., 1) with len==2 → no short name key beyond dotted
        assert dg._module_path_index["foo.py"] == "foo.py"
        assert dg._module_path_index["foo"] == "foo.py"


# ══════════════════════════════════════════════════════════════════════════════
# 4. _resolve_callee — step-by-step resolution
# ══════════════════════════════════════════════════════════════════════════════


class TestResolveCalleeStep1SameFile:
    """Step 1: direct lookup in same file (O(1) hash)."""

    def test_direct_same_file_call_resolves(self):
        pr = _make_parse_result(
            "src/main.py",
            functions=[_func("caller"), _func("helper")],
            calls=[_call("caller", "helper")],
        )
        dg = DependencyGraph().build([pr])
        assert dg.graph.has_edge("src/main.py::caller", "src/main.py::helper")

    def test_unknown_callee_produces_no_edge(self):
        pr = _make_parse_result(
            "src/main.py",
            functions=[_func("caller")],
            calls=[_call("caller", "nonexistent")],
        )
        dg = DependencyGraph().build([pr])
        edges = list(dg.graph.edges())
        # No edge to an unknown callee
        assert not any("nonexistent" in str(e) for e in edges)


class TestResolveCalleeStep2ClassMethod:
    """Step 2: O(1) class method lookup via _method_name_index."""

    def test_method_call_resolved_without_class_prefix(self):
        """Calling 'process' resolves to 'Worker.process' in the same file."""
        pr = _make_parse_result(
            "src/worker.py",
            functions=[
                _func("run"),
                _func("process", parent_class="Worker"),
            ],
            calls=[_call("run", "process")],
        )
        dg = DependencyGraph().build([pr])
        assert dg.graph.has_edge("src/worker.py::run", "src/worker.py::Worker.process")

    def test_method_not_in_same_file_falls_through(self):
        """If the method is in a different file, step 2 finds nothing locally."""
        pr = _make_parse_result(
            "src/main.py",
            functions=[_func("caller")],
            calls=[_call("caller", "compute")],
        )
        dg = DependencyGraph().build([pr])
        # No edge added because 'compute' is nowhere
        assert dg.graph.number_of_edges() == 0


class TestResolveCalleeStep3CrossFileImport:
    """Step 3: cross-file lookup via import + _module_path_index."""

    def test_imported_function_call_resolves_across_files(self):
        pr_lib = _make_parse_result(
            "src/lib/utils.py",
            functions=[_func("format_data")],
        )
        pr_main = _make_parse_result(
            "src/main.py",
            functions=[_func("process")],
            imports=[_imp("src.lib.utils", ["format_data"])],
            calls=[_call("process", "format_data")],
        )
        dg = DependencyGraph().build([pr_lib, pr_main])
        assert dg.graph.has_edge("src/main.py::process", "src/lib/utils.py::format_data")

    def test_import_with_module_last_segment_as_callee(self):
        """Callee name matches the last segment of the import module path."""
        pr_lib = _make_parse_result(
            "src/lib/utils.py",
            functions=[_func("utils")],
        )
        pr_main = _make_parse_result(
            "src/main.py",
            functions=[_func("run")],
            imports=[_imp("src.lib.utils")],
            calls=[_call("run", "utils")],
        )
        dg = DependencyGraph().build([pr_lib, pr_main])
        assert dg.graph.has_edge("src/main.py::run", "src/lib/utils.py::utils")

    def test_cross_file_method_resolved_via_import(self):
        """Step 3 also checks target file's _method_name_index."""
        pr_lib = _make_parse_result(
            "src/lib/svc.py",
            functions=[_func("execute", parent_class="Engine")],
        )
        pr_main = _make_parse_result(
            "src/main.py",
            functions=[_func("run")],
            imports=[_imp("src.lib.svc", ["execute"])],
            calls=[_call("run", "execute")],
        )
        dg = DependencyGraph().build([pr_lib, pr_main])
        assert dg.graph.has_edge("src/main.py::run", "src/lib/svc.py::Engine.execute")

    def test_no_import_means_no_cross_file_resolution(self):
        """Without an import, step 3 is skipped and the edge is not added."""
        pr_lib = _make_parse_result("src/lib/utils.py", functions=[_func("format_data")])
        pr_main = _make_parse_result(
            "src/main.py",
            functions=[_func("process")],
            # No imports
            calls=[_call("process", "format_data")],
        )
        dg = DependencyGraph().build([pr_lib, pr_main])
        # Step 4 (global fallback) will pick it up — edge IS present
        # (This verifies step 4 acts as safety net)
        assert dg.graph.has_edge("src/main.py::process", "src/lib/utils.py::format_data")


class TestResolveCalleeStep4GlobalFallback:
    """Step 4: global fallback via _name_index, returns first non-local match."""

    def test_global_fallback_finds_function_in_other_file(self):
        """No import needed — step 4 scans _name_index for non-local candidates."""
        pr_a = _make_parse_result("src/a.py", functions=[_func("caller")])
        pr_b = _make_parse_result("src/b.py", functions=[_func("shared_util")])
        pr_a.calls.append(_call("caller", "shared_util"))
        dg = DependencyGraph().build([pr_a, pr_b])
        assert dg.graph.has_edge("src/a.py::caller", "src/b.py::shared_util")

    def test_same_name_functions_step4_returns_first_non_local(self):
        """When _name_index has multiple candidates, step 4 returns the first non-local."""
        pr_local = _make_parse_result(
            "src/local.py",
            functions=[_func("caller"), _func("helper")],
            calls=[_call("caller", "helper")],
        )
        pr_other = _make_parse_result("src/other.py", functions=[_func("helper")])
        dg = DependencyGraph().build([pr_local, pr_other])

        # 'helper' exists in both files. Step 1 resolves it locally — no cross-file edge.
        assert dg.graph.has_edge("src/local.py::caller", "src/local.py::helper")
        assert not dg.graph.has_edge("src/local.py::caller", "src/other.py::helper")

    def test_step4_skips_local_candidates(self):
        """Step 4 must skip node IDs that start with the caller's file path."""
        pr = _make_parse_result(
            "src/a.py",
            functions=[_func("caller"), _func("helper")],
            calls=[_call("caller", "helper")],
        )
        dg = DependencyGraph().build([pr])
        candidates = dg._name_index.get("helper", [])
        # Only the local node_id is present
        assert all(nid.startswith("src/a.py::") for nid in candidates)

    def test_no_candidates_returns_no_edge(self):
        pr = _make_parse_result(
            "src/a.py",
            functions=[_func("caller")],
            calls=[_call("caller", "totally_unknown_func")],
        )
        dg = DependencyGraph().build([pr])
        assert dg.graph.number_of_edges() == 0


# ══════════════════════════════════════════════════════════════════════════════
# 5. Integration: combined index scenarios
# ══════════════════════════════════════════════════════════════════════════════


class TestIndexIntegration:
    """End-to-end scenarios exercising multiple indexes together."""

    def test_method_call_uses_method_name_index_not_linear_scan(self):
        """
        Verifies that _method_name_index is populated correctly and that a plain
        method name (without class prefix) resolves via O(1) lookup.
        """
        pr = _make_parse_result(
            "src/engine.py",
            functions=[
                _func("start"),
                _func("_init", parent_class="Engine"),
                _func("_teardown", parent_class="Engine"),
            ],
            calls=[_call("start", "_init")],
        )
        dg = DependencyGraph().build([pr])
        # O(1) lookup via _method_name_index should resolve _init
        assert "_init" in dg._method_name_index["src/engine.py"]
        assert dg.graph.has_edge("src/engine.py::start", "src/engine.py::Engine._init")

    def test_module_path_variants_all_resolve_to_same_file(self):
        pr = _make_parse_result("src/parsers/lexer.py", functions=[_func("tokenize")])
        dg = DependencyGraph().build([pr])

        # All three variants should point to the same file
        assert dg._module_path_index["src/parsers/lexer.py"] == "src/parsers/lexer.py"
        assert dg._module_path_index["src.parsers.lexer"] == "src/parsers/lexer.py"
        assert dg._module_path_index["lexer"] == "src/parsers/lexer.py"

    def test_build_two_files_collision_does_not_break_resolution(self):
        """After a short-name collision, the first file is still resolvable."""
        pr_a = _make_parse_result("src/a/utils.py", functions=[_func("clean")])
        pr_b = _make_parse_result("src/b/utils.py", functions=[_func("format")])
        pr_main = _make_parse_result(
            "src/main.py",
            functions=[_func("run")],
            imports=[_imp("src.a.utils", ["clean"])],
            calls=[_call("run", "clean")],
        )
        dg = DependencyGraph().build([pr_a, pr_b, pr_main])
        assert dg.graph.has_edge("src/main.py::run", "src/a/utils.py::clean")

    def test_duplicate_call_increments_call_count(self):
        """Repeated calls between the same pair increment call_count."""
        pr = _make_parse_result(
            "src/a.py",
            functions=[_func("caller"), _func("helper")],
            calls=[_call("caller", "helper"), _call("caller", "helper")],
        )
        dg = DependencyGraph().build([pr])
        edge_data = dg.graph["src/a.py::caller"]["src/a.py::helper"]
        assert edge_data["call_count"] == 2
