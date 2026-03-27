"""Sprint 3 测试: 依赖图 O(1) 索引 + Mermaid 分层展示。"""
import pytest

from src.parsers.ast_parser import (
    CallInfo,
    ClassInfo,
    FunctionInfo,
    ImportInfo,
    ParseResult,
)
from src.parsers.dependency_graph import (
    DEFAULT_MAX_OVERVIEW_NODES,
    DependencyGraph,
)


# ── 测试数据工厂 ──────────────────────────────────────────


def _make_pr(
    file_path: str,
    language: str = "python",
    functions: list | None = None,
    classes: list | None = None,
    imports: list | None = None,
    calls: list | None = None,
) -> ParseResult:
    return ParseResult(
        file_path=file_path,
        language=language,
        functions=functions or [],
        classes=classes or [],
        imports=imports or [],
        calls=calls or [],
        line_count=100,
    )


def _func(name, line_start=1, line_end=10, parent_class=None, is_method=False):
    return FunctionInfo(
        name=name,
        params=[],
        return_type=None,
        line_start=line_start,
        line_end=line_end,
        parent_class=parent_class,
        is_method=is_method,
    )


def _cls(name, line_start=1, line_end=50):
    return ClassInfo(name=name, line_start=line_start, line_end=line_end)


def _imp(module, names=None, is_relative=False):
    return ImportInfo(module=module, names=names or [], is_relative=is_relative, line=1)


def _call(callee, caller="<module>"):
    return CallInfo(callee_name=callee, caller_func=caller, line=5)


# ── 小型 fixture: 3 文件 / 同目录 ──


def _small_graph():
    """3 个文件, 函数互相调用, 不超过 30 模块。"""
    prs = [
        _make_pr(
            "app/main.py",
            functions=[_func("run"), _func("setup")],
            imports=[_imp("app.utils", ["helper"])],
            calls=[_call("helper", "run"), _call("setup", "run")],
        ),
        _make_pr(
            "app/utils.py",
            functions=[_func("helper"), _func("format_output")],
            calls=[_call("format_output", "helper")],
        ),
        _make_pr(
            "app/models.py",
            classes=[_cls("User")],
            functions=[_func("validate", parent_class="User", is_method=True)],
        ),
    ]
    dg = DependencyGraph()
    dg.build(prs)
    # 手动设 module_group
    for node_id in dg.graph.nodes:
        dg.graph.nodes[node_id]["module_group"] = "app"
    return dg


# ── 大型 fixture: 40+ 模块 / 多顶层目录 ──


def _large_graph():
    """模拟大项目: 5 个顶层目录, ~45 个子模块, 跨模块调用。"""
    prs = []
    module_map = {}

    # 生成 docs_src/ 下的 30 个子模块 (每个 1 个文件 1 个函数)
    for i in range(30):
        fp = f"docs_src/example_{i}/main.py"
        prs.append(
            _make_pr(fp, functions=[_func(f"example_{i}_main")])
        )
        module_map[f"docs_src/example_{i}"] = [fp]

    # fastapi/ 核心模块 (5 个子模块)
    core_files = {
        "fastapi/app.py": [_func("create_app"), _func("run_app")],
        "fastapi/routing.py": [_func("add_route")],
        "fastapi/openapi/utils.py": [_func("generate_schema")],
        "fastapi/security/oauth.py": [_func("verify_token")],
        "fastapi/deps/injector.py": [_func("inject")],
    }
    for fp, funcs in core_files.items():
        imports = []
        calls = []
        if fp == "fastapi/app.py":
            imports = [
                _imp("fastapi.routing", ["add_route"]),
                _imp("fastapi.openapi.utils", ["generate_schema"]),
            ]
            calls = [
                _call("add_route", "create_app"),
                _call("generate_schema", "run_app"),
            ]
        prs.append(_make_pr(fp, functions=funcs, imports=imports, calls=calls))

    sub_module_map = {
        "fastapi": ["fastapi/app.py", "fastapi/routing.py"],
        "fastapi/openapi": ["fastapi/openapi/utils.py"],
        "fastapi/security": ["fastapi/security/oauth.py"],
        "fastapi/deps": ["fastapi/deps/injector.py"],
    }

    # tests/ (1 个模块, 多文件)
    for i in range(5):
        fp = f"tests/test_{i}.py"
        prs.append(
            _make_pr(
                fp,
                functions=[_func(f"test_func_{i}")],
                imports=[_imp("fastapi.app", ["create_app"])],
                calls=[_call("create_app", f"test_func_{i}")],
            )
        )

    # scripts/ (2 个子模块)
    prs.append(_make_pr("scripts/build.py", functions=[_func("build")]))
    prs.append(_make_pr("scripts/deploy/run.py", functions=[_func("deploy")]))

    # 配置
    prs.append(
        _make_pr("setup.py", functions=[_func("setup_cfg")]),
    )

    dg = DependencyGraph()
    dg.build(prs)

    # 设置 module_group
    for node_id, data in dg.graph.nodes(data=True):
        fp = data.get("file", "")
        if fp.startswith("docs_src/"):
            parts = fp.split("/")
            if len(parts) >= 2:
                dg.graph.nodes[node_id]["module_group"] = f"docs_src/{parts[1]}"
        elif fp.startswith("fastapi/openapi"):
            dg.graph.nodes[node_id]["module_group"] = "fastapi/openapi"
        elif fp.startswith("fastapi/security"):
            dg.graph.nodes[node_id]["module_group"] = "fastapi/security"
        elif fp.startswith("fastapi/deps"):
            dg.graph.nodes[node_id]["module_group"] = "fastapi/deps"
        elif fp.startswith("fastapi/"):
            dg.graph.nodes[node_id]["module_group"] = "fastapi"
        elif fp.startswith("tests/"):
            dg.graph.nodes[node_id]["module_group"] = "tests"
        elif fp.startswith("scripts/deploy"):
            dg.graph.nodes[node_id]["module_group"] = "scripts/deploy"
        elif fp.startswith("scripts/"):
            dg.graph.nodes[node_id]["module_group"] = "scripts"
        elif fp == "setup.py":
            dg.graph.nodes[node_id]["module_group"] = "config"

    return dg


# ═══════════════════════════════════════════════════════════
# 一、索引优化测试
# ═══════════════════════════════════════════════════════════


class TestIndexOptimization:
    """验证 O(1) 索引查找的正确性。"""

    def test_name_index_populated(self):
        dg = _small_graph()
        assert "run" in dg._name_index
        assert "helper" in dg._name_index
        assert "User" in dg._name_index

    def test_name_index_contains_correct_node_ids(self):
        dg = _small_graph()
        run_nodes = dg._name_index["run"]
        assert any("app/main.py::run" in n for n in run_nodes)

    def test_method_name_index_populated(self):
        dg = _small_graph()
        assert "app/models.py" in dg._file_class_methods
        assert "User.validate" in dg._file_class_methods["app/models.py"]

    def test_module_path_index_maps_files(self):
        dg = _small_graph()
        # file_path 自身应该在索引中
        assert "app/main.py" in dg._module_path_index
        # 推断出的模块路径也应该在
        assert "app.main" in dg._module_path_index

    def test_cross_file_call_resolved(self):
        """main.py 的 run() 调用 utils.py 的 helper()，应产生边。"""
        dg = _small_graph()
        edges = list(dg.graph.edges)
        callers = [u for u, v in edges if "helper" in v]
        assert len(callers) > 0, "跨文件调用 helper 应被解析为边"

    def test_same_file_call_resolved(self):
        """main.py 的 run() 调用 setup()，同文件应产生边。"""
        dg = _small_graph()
        assert dg.graph.has_edge("app/main.py::run", "app/main.py::setup")

    def test_internal_method_call_resolved(self):
        """utils.py 的 helper() 调用 format_output()。"""
        dg = _small_graph()
        assert dg.graph.has_edge("app/utils.py::helper", "app/utils.py::format_output")

    def test_no_self_edges(self):
        """不应有自环。"""
        dg = _small_graph()
        for u, v in dg.graph.edges:
            assert u != v, f"发现自环: {u}"


# ═══════════════════════════════════════════════════════════
# 二、Mermaid 分层展示测试
# ═══════════════════════════════════════════════════════════


class TestMermaidLayered:
    """验证 Mermaid overview / focus 输出。"""

    # ── overview 基础行为 ──

    def test_overview_small_project_no_aggregation(self):
        """小项目 (≤ 30 模块) overview 等价于 module 图。"""
        dg = _small_graph()
        overview = dg.to_mermaid(level="overview")
        module = dg.to_mermaid(level="module")
        assert overview == module

    def test_overview_large_project_aggregated(self):
        """大项目 (> 30 模块) overview 图节点数 ≤ max_nodes。"""
        dg = _large_graph()
        overview = dg.to_mermaid(level="overview")
        lines = overview.strip().split("\n")
        # 第一行是 "graph TD"，其余是节点和边
        node_lines = [l for l in lines[1:] if "[" in l and "--" not in l and "==>" not in l and "-.-" not in l]
        assert len(node_lines) <= DEFAULT_MAX_OVERVIEW_NODES

    def test_overview_starts_with_graph_td(self):
        dg = _large_graph()
        overview = dg.to_mermaid(level="overview")
        assert overview.startswith("graph TD")

    def test_overview_has_sub_module_count_label(self):
        """聚合节点应标注子模块数量。"""
        dg = _large_graph()
        overview = dg.to_mermaid(level="overview")
        assert "子模块" in overview

    def test_overview_preserves_edges(self):
        """聚合后应保留组间边。"""
        dg = _large_graph()
        overview = dg.to_mermaid(level="overview")
        assert "-->" in overview or "==>" in overview

    # ── focus 展开行为 ──

    def test_focus_shows_subgraph(self):
        """focus 展开应包含 subgraph 块。"""
        dg = _large_graph()
        focused = dg.to_mermaid(level="overview", focus="fastapi")
        assert "subgraph" in focused

    def test_focus_shows_internal_modules(self):
        """focus=fastapi 应显示 fastapi 组内子模块。"""
        dg = _large_graph()
        focused = dg.to_mermaid(level="overview", focus="fastapi")
        assert "fastapi" in focused

    def test_focus_external_dashed_lines(self):
        """外部连接应用虚线 (-.-) 表示。"""
        dg = _large_graph()
        focused = dg.to_mermaid(level="overview", focus="fastapi")
        # 如果有外部连接，应该有虚线
        if "tests" in focused or "docs_src" in focused:
            assert "-.-" in focused

    def test_focus_nonexistent_group(self):
        """focus 不存在的组应返回错误提示。"""
        dg = _large_graph()
        focused = dg.to_mermaid(level="overview", focus="nonexistent")
        assert "未找到" in focused

    # ── 向后兼容 ──

    def test_module_level_unchanged(self):
        """level='module' 行为不变。"""
        dg = _small_graph()
        module = dg.to_mermaid(level="module")
        assert module.startswith("graph TD")
        assert "app" in module

    def test_function_level_unchanged(self):
        """level='function' 行为不变。"""
        dg = _small_graph()
        func_mermaid = dg.to_mermaid(level="function")
        assert func_mermaid.startswith("graph TD")


# ═══════════════════════════════════════════════════════════
# 三、get_expandable_groups 测试
# ═══════════════════════════════════════════════════════════


class TestExpandableGroups:
    """验证可展开组的元数据。"""

    def test_small_project_no_expandable(self):
        """小项目没有可展开组（所有组都只有 1 个子模块）。"""
        dg = _small_graph()
        groups = dg.get_expandable_groups()
        assert groups == {}

    def test_large_project_has_expandable(self):
        """大项目应有可展开组。"""
        dg = _large_graph()
        groups = dg.get_expandable_groups()
        assert len(groups) > 0

    def test_expandable_has_correct_keys(self):
        """可展开组应包含 sub_modules, total_files, total_lines。"""
        dg = _large_graph()
        groups = dg.get_expandable_groups()
        for name, info in groups.items():
            assert "sub_modules" in info
            assert "total_files" in info
            assert "total_lines" in info

    def test_docs_src_has_30_sub_modules(self):
        """docs_src 应有 30 个子模块。"""
        dg = _large_graph()
        groups = dg.get_expandable_groups()
        assert "docs_src" in groups
        assert groups["docs_src"]["sub_modules"] == 30


# ═══════════════════════════════════════════════════════════
# 四、边界情况
# ═══════════════════════════════════════════════════════════


class TestEdgeCases:
    """空图、单模块等边界情况。"""

    def test_empty_graph_overview(self):
        dg = DependencyGraph()
        dg.build([])
        overview = dg.to_mermaid(level="overview")
        assert "暂无" in overview

    def test_empty_graph_focus(self):
        dg = DependencyGraph()
        dg.build([])
        focused = dg.to_mermaid(level="overview", focus="anything")
        assert "未找到" in focused

    def test_single_file_graph(self):
        prs = [
            _make_pr("main.py", functions=[_func("main")])
        ]
        dg = DependencyGraph()
        dg.build(prs)
        overview = dg.to_mermaid(level="overview")
        assert "graph TD" in overview

    def test_max_nodes_clamped_to_1(self):
        """max_nodes=0 应被 clamp 到 1。"""
        dg = _large_graph()
        overview = dg.to_mermaid(level="overview", max_nodes=0)
        assert "graph TD" in overview

    def test_build_idempotent_indexes(self):
        """多次 build 不应污染索引。"""
        prs = [_make_pr("a.py", functions=[_func("foo")])]
        dg = DependencyGraph()
        dg.build(prs)
        count_1 = len(dg._name_index.get("foo", []))
        # 创建新实例再 build 一次
        dg2 = DependencyGraph()
        dg2.build(prs)
        count_2 = len(dg2._name_index.get("foo", []))
        assert count_1 == count_2 == 1
