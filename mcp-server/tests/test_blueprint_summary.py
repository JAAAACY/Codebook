"""Tests for blueprint_summary — data models, fallback builder, LLM context & parser."""

from __future__ import annotations

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
from src.parsers.repo_cloner import CloneResult, FileInfo
from src.summarizer.engine import SummaryContext


# ── Fixture ──────────────────────────────────────────────────


def _make_test_context() -> SummaryContext:
    """Build a minimal SummaryContext with two modules (auth + db) and one call edge."""

    # Files
    auth_file = FileInfo(
        path="src/auth/login.py",
        abs_path="/tmp/repo/src/auth/login.py",
        language="python",
        size_bytes=1200,
        line_count=80,
    )
    db_file = FileInfo(
        path="src/db/connection.py",
        abs_path="/tmp/repo/src/db/connection.py",
        language="python",
        size_bytes=2000,
        line_count=120,
    )

    clone_result = CloneResult(
        repo_path="/tmp/repo",
        files=[auth_file, db_file],
        languages={"python": 2},
        total_lines=200,
    )

    # Parse results
    auth_pr = ParseResult(
        file_path="src/auth/login.py",
        language="python",
        functions=[
            FunctionInfo(
                name="validate_token",
                params=["token"],
                return_type="bool",
                line_start=10,
                line_end=25,
                docstring=None,
                is_method=False,
                parent_class=None,
            ),
            FunctionInfo(
                name="create_session",
                params=["user_id", "ttl"],
                return_type="Session",
                line_start=30,
                line_end=50,
                docstring="创建用户会话",
                is_method=False,
                parent_class=None,
            ),
        ],
        classes=[ClassInfo(name="AuthManager", methods=["validate_token", "create_session"])],
        imports=[ImportInfo(module="src.db.connection", names=["get_connection"])],
        calls=[CallInfo(caller_func="create_session", callee_name="get_connection", line=35)],
        line_count=80,
    )

    db_pr = ParseResult(
        file_path="src/db/connection.py",
        language="python",
        functions=[
            FunctionInfo(
                name="get_connection",
                params=["db_url"],
                return_type="Connection",
                line_start=5,
                line_end=20,
                docstring=None,
                is_method=False,
                parent_class=None,
            ),
            FunctionInfo(
                name="execute_query",
                params=["conn", "sql"],
                return_type="list",
                line_start=25,
                line_end=45,
                docstring=None,
                is_method=False,
                parent_class=None,
            ),
        ],
        classes=[],
        imports=[],
        calls=[],
        line_count=120,
    )

    parse_results = [auth_pr, db_pr]

    # Module groups
    auth_module = ModuleGroup(
        name="auth",
        dir_path="src/auth",
        files=["src/auth/login.py"],
        entry_functions=["validate_token"],
        public_interfaces=["validate_token", "create_session"],
        total_lines=80,
    )
    db_module = ModuleGroup(
        name="db",
        dir_path="src/db",
        files=["src/db/connection.py"],
        entry_functions=["get_connection"],
        public_interfaces=["get_connection", "execute_query"],
        total_lines=120,
    )
    # Special module (should be excluded)
    test_module = ModuleGroup(
        name="tests",
        dir_path="tests",
        files=["tests/test_auth.py"],
        total_lines=50,
        is_special=True,
    )

    modules = [auth_module, db_module, test_module]

    # Dependency graph
    dep_graph = DependencyGraph()
    dep_graph.build(parse_results)
    # Tag nodes with module_group so get_module_graph() returns edges
    for node_id in dep_graph.graph.nodes:
        data = dep_graph.graph.nodes[node_id]
        fp = data.get("file", "")
        if "auth" in fp:
            data["module_group"] = "auth"
        elif "db" in fp:
            data["module_group"] = "db"

    return SummaryContext(
        clone_result=clone_result,
        parse_results=parse_results,
        modules=modules,
        dep_graph=dep_graph,
        role="pm",
        repo_url="https://github.com/example/repo",
    )


# ── Data model tests ────────────────────────────────────────


class TestDataModels:
    """Verify dataclass fields and serialisation."""

    def test_function_summary_fields(self):
        from src.summarizer.blueprint_summary import FunctionSummary

        fs = FunctionSummary(
            code_name="validate_token",
            business_name="验证 token",
            explanation="验证用户 token 是否有效",
            file_path="src/auth/login.py",
            line_start=10,
            params=["token"],
            return_type="bool",
        )
        assert fs.code_name == "validate_token"
        assert fs.business_name == "验证 token"
        assert fs.explanation == "验证用户 token 是否有效"
        assert fs.file_path == "src/auth/login.py"
        assert fs.line_start == 10
        assert fs.params == ["token"]
        assert fs.return_type == "bool"

    def test_module_summary_fields(self):
        from src.summarizer.blueprint_summary import ModuleSummary

        ms = ModuleSummary(
            code_path="src/auth",
            business_name="认证系统",
            description="负责用户认证",
            health="green",
            functions=[],
            depends_on=["db"],
            used_by=[],
        )
        assert ms.code_path == "src/auth"
        assert ms.business_name == "认证系统"
        assert ms.health == "green"
        assert ms.depends_on == ["db"]
        assert ms.used_by == []

    def test_connection_summary_fields(self):
        from src.summarizer.blueprint_summary import ConnectionSummary

        cs = ConnectionSummary(
            from_module="auth",
            to_module="db",
            verb="读写数据",
            call_count=3,
        )
        assert cs.from_module == "auth"
        assert cs.to_module == "db"
        assert cs.verb == "读写数据"
        assert cs.call_count == 3

    def test_blueprint_summary_fields(self):
        from src.summarizer.blueprint_summary import BlueprintSummary

        bp = BlueprintSummary(
            project_name="example-repo",
            project_description="示例项目",
            modules=[],
            connections=[],
        )
        assert bp.project_name == "example-repo"
        assert bp.project_description == "示例项目"
        assert bp.modules == []
        assert bp.connections == []

    def test_blueprint_summary_to_dict(self):
        from src.summarizer.blueprint_summary import (
            BlueprintSummary,
            ConnectionSummary,
            FunctionSummary,
            ModuleSummary,
        )

        fs = FunctionSummary(
            code_name="f",
            business_name="函数",
            explanation="说明",
            file_path="a.py",
            line_start=1,
            params=[],
            return_type=None,
        )
        ms = ModuleSummary(
            code_path="src/a",
            business_name="A 模块",
            description="描述",
            health="green",
            functions=[fs],
            depends_on=[],
            used_by=[],
        )
        cs = ConnectionSummary(from_module="a", to_module="b", verb="调用", call_count=1)
        bp = BlueprintSummary(
            project_name="proj",
            project_description="desc",
            modules=[ms],
            connections=[cs],
        )

        d = bp.to_dict()
        assert isinstance(d, dict)
        assert d["project_name"] == "proj"
        assert len(d["modules"]) == 1
        assert d["modules"][0]["code_path"] == "src/a"
        assert len(d["modules"][0]["functions"]) == 1
        assert len(d["connections"]) == 1
        assert d["connections"][0]["verb"] == "调用"

        # Verify JSON-serializable (no dataclass objects left)
        import json
        json.dumps(d, ensure_ascii=False)


# ── build_fallback_summary tests ────────────────────────────


class TestBuildFallbackSummary:
    """Verify fallback (rule-based) summary generation."""

    def test_returns_blueprint_summary(self):
        from src.summarizer.blueprint_summary import BlueprintSummary, build_fallback_summary

        ctx = _make_test_context()
        result = build_fallback_summary(ctx)
        assert isinstance(result, BlueprintSummary)

    def test_modules_have_chinese_business_name(self):
        from src.summarizer.blueprint_summary import build_fallback_summary

        ctx = _make_test_context()
        result = build_fallback_summary(ctx)

        # auth → 认证系统, db → 数据库
        names = [m.business_name for m in result.modules]
        assert any("认证" in n for n in names), f"Expected Chinese auth name, got {names}"
        assert any("数据" in n for n in names), f"Expected Chinese db name, got {names}"

    def test_functions_have_nonempty_explanation(self):
        from src.summarizer.blueprint_summary import build_fallback_summary

        ctx = _make_test_context()
        result = build_fallback_summary(ctx)

        for mod in result.modules:
            for fn in mod.functions:
                assert fn.explanation, f"Function {fn.code_name} has empty explanation"

    def test_connections_have_nonempty_verb(self):
        from src.summarizer.blueprint_summary import build_fallback_summary

        ctx = _make_test_context()
        result = build_fallback_summary(ctx)

        for conn in result.connections:
            assert conn.verb, f"Connection {conn.from_module}->{conn.to_module} has empty verb"

    def test_special_modules_excluded(self):
        from src.summarizer.blueprint_summary import build_fallback_summary

        ctx = _make_test_context()
        result = build_fallback_summary(ctx)

        module_names = [m.code_path for m in result.modules]
        assert "tests" not in module_names
        # Only auth and db should appear
        assert len(result.modules) == 2


# ── build_summary_context tests ─────────────────────────────


class TestBuildSummaryContext:
    """Verify LLM context assembly."""

    def test_returns_dict_with_required_keys(self):
        from src.summarizer.blueprint_summary import build_summary_context

        ctx = _make_test_context()
        result = build_summary_context(ctx)

        assert isinstance(result, dict)
        assert "modules" in result
        assert "connections" in result
        assert "prompt" in result

    def test_prompt_is_nonempty_string(self):
        from src.summarizer.blueprint_summary import build_summary_context

        ctx = _make_test_context()
        result = build_summary_context(ctx)

        assert isinstance(result["prompt"], str)
        assert len(result["prompt"]) > 100, "Prompt should be substantial (>100 chars)"

    def test_modules_count_matches_non_special(self):
        from src.summarizer.blueprint_summary import build_summary_context

        ctx = _make_test_context()
        result = build_summary_context(ctx)

        non_special = [m for m in ctx.modules if not m.is_special]
        assert len(result["modules"]) == len(non_special)


# ── parse_llm_response tests ────────────────────────────────


class TestParseLlmResponse:
    """Verify LLM response parsing with graceful fallback."""

    def test_valid_json_returns_blueprint(self):
        from src.summarizer.blueprint_summary import BlueprintSummary, parse_llm_response

        ctx = _make_test_context()
        response = {
            "project_name": "test-project",
            "project_description": "测试项目",
            "modules": [
                {
                    "code_path": "src/auth",
                    "business_name": "认证系统",
                    "description": "处理用户认证",
                    "health": "green",
                    "functions": [
                        {
                            "code_name": "validate_token",
                            "business_name": "验证令牌",
                            "explanation": "验证用户令牌有效性",
                            "file_path": "src/auth/login.py",
                            "line_start": 10,
                            "params": ["token"],
                            "return_type": "bool",
                        }
                    ],
                    "depends_on": ["db"],
                    "used_by": [],
                },
            ],
            "connections": [
                {
                    "from_module": "auth",
                    "to_module": "db",
                    "verb": "读写数据",
                    "call_count": 1,
                },
            ],
        }

        result = parse_llm_response(response, ctx)
        assert isinstance(result, BlueprintSummary)
        assert result.project_name == "test-project"
        assert len(result.modules) == 1
        assert result.modules[0].business_name == "认证系统"
        assert len(result.connections) == 1

    def test_invalid_json_returns_fallback(self):
        from src.summarizer.blueprint_summary import BlueprintSummary, parse_llm_response

        ctx = _make_test_context()
        # Completely broken response
        result = parse_llm_response("not a dict at all", ctx)
        assert isinstance(result, BlueprintSummary)
        # Should still have modules from fallback
        assert len(result.modules) > 0

    def test_partial_json_returns_fallback(self):
        from src.summarizer.blueprint_summary import BlueprintSummary, parse_llm_response

        ctx = _make_test_context()
        # Dict but missing required keys
        result = parse_llm_response({"broken": True}, ctx)
        assert isinstance(result, BlueprintSummary)
        assert len(result.modules) > 0
