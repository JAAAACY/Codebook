"""交互式蓝图功能测试。

测试 Phase 1 新增的交互功能：
- dependency_graph 的邻接/调用链查询方法
- blueprint_renderer 中的交互式 HTML 输出
- codebook_explore 中的 adjacency 数据嵌入
"""

import pytest
from src.parsers.dependency_graph import DependencyGraph
from src.parsers.ast_parser import ParseResult, FunctionInfo, ClassInfo, ImportInfo, CallInfo


# ── Fixtures ──────────────────────────────────────────────

def _make_parse_results() -> list[ParseResult]:
    """构造一个简单的三模块项目用于测试。"""
    return [
        ParseResult(
            file_path="src/server.py",
            language="python",
            functions=[
                FunctionInfo(name="handle_request", line_start=10, line_end=30, is_method=False, parent_class=None),
                FunctionInfo(name="start_server", line_start=32, line_end=50, is_method=False, parent_class=None),
            ],
            classes=[],
            imports=[ImportInfo(module="src.db", names=["query_db"])],
            calls=[
                CallInfo(callee_name="query_db", caller_func="handle_request"),
                CallInfo(callee_name="validate", caller_func="handle_request"),
            ],
            line_count=50,
        ),
        ParseResult(
            file_path="src/db.py",
            language="python",
            functions=[
                FunctionInfo(name="query_db", line_start=5, line_end=20, is_method=False, parent_class=None),
                FunctionInfo(name="connect", line_start=22, line_end=35, is_method=False, parent_class=None),
            ],
            classes=[],
            imports=[],
            calls=[
                CallInfo(callee_name="connect", caller_func="query_db"),
            ],
            line_count=35,
        ),
        ParseResult(
            file_path="src/utils.py",
            language="python",
            functions=[
                FunctionInfo(name="validate", line_start=1, line_end=15, is_method=False, parent_class=None),
            ],
            classes=[],
            imports=[],
            calls=[],
            line_count=15,
        ),
    ]


def _build_graph_with_modules() -> DependencyGraph:
    """构建并设置模块分组的依赖图。"""
    g = DependencyGraph()
    g.build(_make_parse_results())
    module_map = {}
    for node_id, data in g.graph.nodes(data=True):
        f = data.get("file", "")
        if "server" in f:
            module_map[node_id] = "server"
        elif "db" in f:
            module_map[node_id] = "db"
        elif "utils" in f:
            module_map[node_id] = "utils"
    g.set_module_groups(module_map)
    return g


# ── get_node_adjacency tests ─────────────────────────────


class TestGetNodeAdjacency:
    def test_server_has_downstream(self):
        g = _build_graph_with_modules()
        adj = g.get_node_adjacency("server")
        assert "db" in adj["downstream"] or "utils" in adj["downstream"]
        assert adj["upstream"] == []  # nothing calls server

    def test_db_has_upstream(self):
        g = _build_graph_with_modules()
        adj = g.get_node_adjacency("db")
        assert "server" in adj["upstream"]

    def test_nonexistent_module(self):
        g = _build_graph_with_modules()
        adj = g.get_node_adjacency("nonexistent")
        assert adj == {"upstream": [], "downstream": []}

    def test_returns_sorted_lists(self):
        g = _build_graph_with_modules()
        adj = g.get_node_adjacency("server")
        assert adj["downstream"] == sorted(adj["downstream"])


# ── get_function_call_chain tests ─────────────────────────


class TestGetFunctionCallChain:
    def test_returns_functions_in_module(self):
        g = _build_graph_with_modules()
        chains = g.get_function_call_chain("server")
        func_names = [c["function"] for c in chains]
        assert "handle_request" in func_names
        assert "start_server" in func_names

    def test_callees_populated(self):
        g = _build_graph_with_modules()
        chains = g.get_function_call_chain("server")
        hr = next(c for c in chains if c["function"] == "handle_request")
        # handle_request calls query_db and validate
        callee_funcs = [c.split("/")[-1] for c in hr["callees"]]
        assert "query_db" in callee_funcs or "validate" in callee_funcs

    def test_callers_populated(self):
        g = _build_graph_with_modules()
        chains = g.get_function_call_chain("db")
        qdb = next(c for c in chains if c["function"] == "query_db")
        caller_funcs = [c.split("/")[-1] for c in qdb["callers"]]
        assert "handle_request" in caller_funcs

    def test_empty_module(self):
        g = _build_graph_with_modules()
        chains = g.get_function_call_chain("nonexistent")
        assert chains == []

    def test_excludes_module_nodes(self):
        g = _build_graph_with_modules()
        chains = g.get_function_call_chain("server")
        func_names = [c["function"] for c in chains]
        assert "<module>" not in func_names

    def test_includes_file_and_line(self):
        g = _build_graph_with_modules()
        chains = g.get_function_call_chain("server")
        hr = next(c for c in chains if c["function"] == "handle_request")
        assert hr["file"] == "src/server.py"
        assert hr["line_start"] == 10


# ── Blueprint HTML interactive features ──────────────────


class TestBlueprintInteractive:
    def test_html_contains_search_input(self):
        from src.tools.blueprint_renderer import render_blueprint_html

        report_data = {
            "overview": {"stats": {}, "mermaid_diagram": ""},
            "module_cards": [],
            "role": "dev",
        }
        html = render_blueprint_html(report_data)
        assert 'id="searchInput"' in html
        assert "searchModules" in html

    def test_html_contains_adjacency_data(self):
        from src.tools.blueprint_renderer import render_blueprint_html

        report_data = {
            "overview": {"stats": {}, "mermaid_diagram": ""},
            "module_cards": [
                {
                    "name": "server",
                    "health": "green",
                    "adjacency": {"upstream": [], "downstream": ["db"]},
                },
            ],
            "role": "dev",
        }
        html = render_blueprint_html(report_data)
        assert "_adjacency" in html
        assert '"server"' in html

    def test_html_contains_highlight_functions(self):
        from src.tools.blueprint_renderer import render_blueprint_html

        report_data = {
            "overview": {"stats": {}, "mermaid_diagram": ""},
            "module_cards": [],
            "role": "dev",
        }
        html = render_blueprint_html(report_data)
        assert "highlightModule" in html
        assert "clearHighlights" in html
        assert "bindMermaidClicks" in html

    def test_module_card_has_data_name(self):
        from src.tools.blueprint_renderer import _build_module_card_html

        card = {"name": "server", "health": "green"}
        html = _build_module_card_html(card)
        assert 'data-name="server"' in html

    def test_call_chains_render_in_card(self):
        from src.tools.blueprint_renderer import _build_module_card_html

        card = {
            "name": "server",
            "health": "green",
            "is_selected": True,
            "call_chains": [
                {
                    "function": "handle_request",
                    "file": "src/server.py",
                    "line_start": 10,
                    "callers": [],
                    "callees": ["db/query_db"],
                },
            ],
        }
        html = _build_module_card_html(card)
        assert "handle_request()" in html
        assert "db/query_db" in html
        assert "fn-callees" in html

    def test_dep_links_are_clickable(self):
        from src.tools.blueprint_renderer import _build_module_card_html

        card = {
            "name": "server",
            "health": "green",
            "depends_on": ["db", "utils"],
        }
        html = _build_module_card_html(card)
        assert "dep-link" in html
        assert "highlightModule" in html
        assert 'data-target="db"' in html

    def test_keyboard_shortcut_in_html(self):
        from src.tools.blueprint_renderer import render_blueprint_html

        report_data = {
            "overview": {"stats": {}, "mermaid_diagram": ""},
            "module_cards": [],
            "role": "dev",
        }
        html = render_blueprint_html(report_data)
        # / key focuses search, Escape clears
        assert "e.key==='/'" in html or "e.key=='/'" in html
        assert "Escape" in html
