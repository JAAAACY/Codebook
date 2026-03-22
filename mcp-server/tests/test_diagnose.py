"""diagnose 工具测试。

测试覆盖：
1. 关键词提取（中英文混合、camelCase、snake_case）
2. 节点匹配评分
3. 调用链追踪（上下游展开）
4. Mermaid 生成
5. 完整 diagnose 流程（需要 scan_repo 缓存）
6. 错误处理（无缓存、空 query、模块不存在）
"""

from __future__ import annotations

import asyncio
import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.parsers.ast_parser import (
    ParseResult, FunctionInfo, ClassInfo, ImportInfo, CallInfo,
)
from src.parsers.dependency_graph import DependencyGraph
from src.parsers.module_grouper import ModuleGroup
from src.parsers.repo_cloner import CloneResult, FileInfo
from src.summarizer.engine import SummaryContext
from src.tools._repo_cache import repo_cache
from src.tools.diagnose import (
    _extract_keywords,
    _score_node,
    _find_matching_nodes,
    _trace_call_chain,
    _chain_to_mermaid,
    _extract_locations,
    diagnose,
)


# ── fixtures ────────────────────────────────────────────


@pytest.fixture
def temp_repo(tmp_path):
    """创建临时仓库。"""
    # 用户认证模块
    auth_dir = tmp_path / "app" / "auth"
    auth_dir.mkdir(parents=True)
    (auth_dir / "register.py").write_text(textwrap.dedent("""\
        from app.models import User
        from app.notification import send_email

        def register_user(email: str, password: str) -> dict:
            \"\"\"用户注册。\"\"\"
            existing = User.find_by_email(email)
            if existing:
                raise ValueError("邮箱已注册")
            user = User.create(email=email, password=password)
            send_email(email, "欢迎注册", "您的账号已创建")
            return {"status": "ok", "user_id": user.id}

        def login(email: str, password: str) -> dict:
            \"\"\"用户登录。\"\"\"
            user = User.find_by_email(email)
            if not user or not user.check_password(password):
                raise ValueError("邮箱或密码错误")
            return {"status": "ok", "token": "jwt_xxx"}
    """), encoding="utf-8")

    # 模型模块
    models_dir = tmp_path / "app" / "models"
    models_dir.mkdir(parents=True)
    (models_dir / "user.py").write_text(textwrap.dedent("""\
        class User:
            def __init__(self, id, email):
                self.id = id
                self.email = email

            @classmethod
            def find_by_email(cls, email):
                return None

            @classmethod
            def create(cls, email, password):
                return cls(id=1, email=email)

            def check_password(self, password):
                return True
    """), encoding="utf-8")

    # 通知模块
    notify_dir = tmp_path / "app" / "notification"
    notify_dir.mkdir(parents=True)
    (notify_dir / "sender.py").write_text(textwrap.dedent("""\
        def send_email(to: str, subject: str, body: str) -> bool:
            return True

        def send_sms(phone: str, message: str) -> bool:
            return True
    """), encoding="utf-8")

    return tmp_path


@pytest.fixture
def build_ctx(temp_repo):
    """构建完整 SummaryContext 并缓存。"""
    repo_path = str(temp_repo)

    files = [
        FileInfo(path="app/auth/register.py",
                 abs_path=str(temp_repo / "app/auth/register.py"),
                 language="python", size_bytes=500, line_count=20, is_config=False),
        FileInfo(path="app/models/user.py",
                 abs_path=str(temp_repo / "app/models/user.py"),
                 language="python", size_bytes=300, line_count=15, is_config=False),
        FileInfo(path="app/notification/sender.py",
                 abs_path=str(temp_repo / "app/notification/sender.py"),
                 language="python", size_bytes=100, line_count=6, is_config=False),
    ]

    clone_result = CloneResult(
        repo_path=repo_path,
        files=files,
        languages={"python": 3},
        total_lines=41,
    )

    auth_pr = ParseResult(
        file_path="app/auth/register.py",
        language="python",
        functions=[
            FunctionInfo(name="register_user", params=["email", "password"],
                         return_type="dict", line_start=4, line_end=12,
                         docstring="用户注册。", is_method=False),
            FunctionInfo(name="login", params=["email", "password"],
                         return_type="dict", line_start=14, line_end=20,
                         docstring="用户登录。", is_method=False),
        ],
        imports=[
            ImportInfo(module="app.models", names=["User"], line=1),
            ImportInfo(module="app.notification", names=["send_email"], line=2),
        ],
        calls=[
            CallInfo(caller_func="register_user", callee_name="find_by_email", line=6),
            CallInfo(caller_func="register_user", callee_name="create", line=9),
            CallInfo(caller_func="register_user", callee_name="send_email", line=10),
            CallInfo(caller_func="login", callee_name="find_by_email", line=15),
            CallInfo(caller_func="login", callee_name="check_password", line=16),
        ],
        line_count=20,
    )

    user_pr = ParseResult(
        file_path="app/models/user.py",
        language="python",
        classes=[ClassInfo(name="User", methods=["find_by_email", "create", "check_password"],
                           line_start=1, line_end=15)],
        functions=[
            FunctionInfo(name="find_by_email", params=["cls", "email"],
                         line_start=7, line_end=8, is_method=True, parent_class="User"),
            FunctionInfo(name="create", params=["cls", "email", "password"],
                         line_start=10, line_end=11, is_method=True, parent_class="User"),
            FunctionInfo(name="check_password", params=["self", "password"],
                         line_start=13, line_end=14, is_method=True, parent_class="User"),
        ],
        imports=[],
        calls=[],
        line_count=15,
    )

    notify_pr = ParseResult(
        file_path="app/notification/sender.py",
        language="python",
        functions=[
            FunctionInfo(name="send_email", params=["to", "subject", "body"],
                         return_type="bool", line_start=1, line_end=2, is_method=False),
            FunctionInfo(name="send_sms", params=["phone", "message"],
                         return_type="bool", line_start=4, line_end=5, is_method=False),
        ],
        imports=[],
        calls=[],
        line_count=6,
    )

    parse_results = [auth_pr, user_pr, notify_pr]

    modules = [
        ModuleGroup(name="用户认证", dir_path="app/auth",
                    files=["app/auth/register.py"],
                    entry_functions=["register_user", "login"],
                    public_interfaces=["register_user", "login"],
                    total_lines=20),
        ModuleGroup(name="数据模型", dir_path="app/models",
                    files=["app/models/user.py"],
                    entry_functions=["find_by_email", "create"],
                    public_interfaces=["User"],
                    total_lines=15),
        ModuleGroup(name="通知服务", dir_path="app/notification",
                    files=["app/notification/sender.py"],
                    entry_functions=["send_email", "send_sms"],
                    public_interfaces=["send_email", "send_sms"],
                    total_lines=6),
    ]

    dep_graph = DependencyGraph()
    dep_graph.build(parse_results)

    # 设置模块分组
    module_map = {}
    for pr in parse_results:
        for m in modules:
            if pr.file_path in m.files:
                for func in pr.functions:
                    if func.parent_class:
                        nid = f"{pr.file_path}::{func.parent_class}.{func.name}"
                    else:
                        nid = f"{pr.file_path}::{func.name}"
                    module_map[nid] = m.name
                for cls in pr.classes:
                    nid = f"{pr.file_path}::{cls.name}"
                    module_map[nid] = m.name
    dep_graph.set_module_groups(module_map)

    ctx = SummaryContext(
        clone_result=clone_result,
        parse_results=parse_results,
        modules=modules,
        dep_graph=dep_graph,
        role="pm",
    )

    # 存入缓存
    repo_cache.store("https://test.example.com/repo", ctx)

    yield ctx

    # 清理
    repo_cache.clear_all()


# ── 关键词提取测试 ──────────────────────────────────────


class TestExtractKeywords:

    def test_english_simple(self):
        kws = _extract_keywords("register user email duplicate")
        assert "register" in kws
        assert "user" in kws
        assert "email" in kws
        assert "duplicate" in kws

    def test_camel_case(self):
        kws = _extract_keywords("registerUser handlePayment")
        assert "register" in kws
        assert "user" in kws
        assert "handle" in kws
        assert "payment" in kws

    def test_snake_case(self):
        kws = _extract_keywords("register_user send_email")
        assert "register" in kws
        assert "user" in kws
        assert "send" in kws
        assert "email" in kws

    def test_chinese_mixed(self):
        kws = _extract_keywords("注册时邮箱重复报错不友好")
        # 中文单字会被拆分，保留长度 >= 2 的
        assert "注册" in kws or "邮箱" in kws or "报错" in kws or len(kws) > 0

    def test_stop_words_filtered(self):
        kws = _extract_keywords("the user is not able to login")
        assert "the" not in kws
        assert "is" not in kws
        assert "not" not in kws
        assert "login" in kws

    def test_empty_query(self):
        assert _extract_keywords("") == []
        assert _extract_keywords("   ") == []

    def test_dedup(self):
        kws = _extract_keywords("register register register")
        assert kws.count("register") == 1


# ── 节点匹配测试 ────────────────────────────────────────


class TestNodeMatching:

    def test_find_matching_nodes(self, build_ctx):
        ctx = build_ctx
        matches = _find_matching_nodes(ctx.dep_graph, ["register"], None)
        assert len(matches) > 0
        # register_user 应该排在前面
        top_label = ctx.dep_graph.graph.nodes[matches[0][0]].get("label", "")
        assert "register" in top_label.lower()

    def test_module_filter(self, build_ctx):
        ctx = build_ctx
        # 只在通知模块中搜索 "send"
        notify_files = {"app/notification/sender.py"}
        matches = _find_matching_nodes(ctx.dep_graph, ["send"], notify_files)
        assert len(matches) > 0
        for nid, score in matches:
            file_path = ctx.dep_graph.graph.nodes[nid].get("file", "")
            # 通知模块的匹配分应该更高
            if file_path in notify_files:
                assert score > 0

    def test_no_match(self, build_ctx):
        ctx = build_ctx
        matches = _find_matching_nodes(ctx.dep_graph, ["zzzznotexist"], None)
        assert matches == []


# ── 调用链追踪测试 ──────────────────────────────────────


class TestCallChainTracing:

    def test_trace_from_register(self, build_ctx):
        ctx = build_ctx
        # 找到 register_user 节点
        register_id = "app/auth/register.py::register_user"
        chain = _trace_call_chain(ctx.dep_graph, [register_id], max_depth=2)

        assert register_id in chain["nodes"]
        assert chain["nodes"][register_id]["direction"] == "seed"
        # register_user 调用了 send_email, find_by_email, create
        downstream_labels = {
            chain["nodes"][nid]["label"]
            for nid, data in chain["nodes"].items()
            if data.get("direction") == "downstream"
        }
        assert len(downstream_labels) > 0

    def test_trace_with_depth_limit(self, build_ctx):
        ctx = build_ctx
        register_id = "app/auth/register.py::register_user"
        chain_d1 = _trace_call_chain(ctx.dep_graph, [register_id], max_depth=1)
        chain_d3 = _trace_call_chain(ctx.dep_graph, [register_id], max_depth=3)
        # depth=3 should have >= depth=1 nodes
        assert len(chain_d3["nodes"]) >= len(chain_d1["nodes"])

    def test_chain_has_edges(self, build_ctx):
        ctx = build_ctx
        register_id = "app/auth/register.py::register_user"
        chain = _trace_call_chain(ctx.dep_graph, [register_id])
        assert len(chain["edges"]) > 0


# ── Mermaid 生成测试 ─────────────────────────────────────


class TestMermaidGeneration:

    def test_generates_valid_mermaid(self, build_ctx):
        ctx = build_ctx
        register_id = "app/auth/register.py::register_user"
        chain = _trace_call_chain(ctx.dep_graph, [register_id])
        mermaid = _chain_to_mermaid(chain)
        assert mermaid.startswith("graph TD")
        assert "classDef seed" in mermaid

    def test_empty_chain(self):
        chain = {"nodes": {}, "edges": []}
        mermaid = _chain_to_mermaid(chain)
        assert "未找到" in mermaid


# ── 精确定位测试 ─────────────────────────────────────────


class TestExtractLocations:

    def test_locations_have_ref(self, build_ctx):
        ctx = build_ctx
        register_id = "app/auth/register.py::register_user"
        chain = _trace_call_chain(ctx.dep_graph, [register_id])
        locations = _extract_locations(chain)
        assert len(locations) > 0
        for loc in locations:
            assert "ref" in loc
            assert "label" in loc
            assert "file" in loc

    def test_seed_has_high_priority(self, build_ctx):
        ctx = build_ctx
        register_id = "app/auth/register.py::register_user"
        chain = _trace_call_chain(ctx.dep_graph, [register_id])
        locations = _extract_locations(chain)
        # 第一个应该是 seed（高优先）
        assert locations[0]["priority"] == "high"

    def test_code_snippet_loaded(self, build_ctx, temp_repo):
        ctx = build_ctx
        register_id = "app/auth/register.py::register_user"
        chain = _trace_call_chain(ctx.dep_graph, [register_id])
        locations = _extract_locations(chain, str(temp_repo))
        seed_locs = [l for l in locations if l["priority"] == "high"]
        assert len(seed_locs) > 0
        # register_user 的代码片段应该被加载
        has_snippet = any("code_snippet" in l for l in seed_locs)
        assert has_snippet


# ── 完整 diagnose 流程测试 ──────────────────────────────


class TestDiagnoseIntegration:

    def test_basic_diagnose(self, build_ctx):
        result = asyncio.get_event_loop().run_until_complete(
            diagnose(module_name="all", role="pm", query="register user email")
        )
        assert result["status"] == "ok"
        assert result["keywords"]
        assert result["matched_nodes"]
        assert result["call_chain"]
        assert "graph TD" in result["call_chain"]
        assert result["exact_locations"]
        assert result["context"]
        assert result["guidance"]

    def test_diagnose_with_module_filter(self, build_ctx):
        result = asyncio.get_event_loop().run_until_complete(
            diagnose(module_name="用户认证", role="pm", query="register login")
        )
        assert result["status"] == "ok"
        assert "用户认证" in result["matched_modules"]

    def test_diagnose_no_cache(self):
        """无缓存时应返回错误。"""
        repo_cache.clear_all()
        result = asyncio.get_event_loop().run_until_complete(
            diagnose(query="something")
        )
        assert result["status"] == "error"
        assert "scan_repo" in result["error"]

    def test_diagnose_empty_query(self, build_ctx):
        result = asyncio.get_event_loop().run_until_complete(
            diagnose(query="")
        )
        assert result["status"] == "error"
        assert "关键词" in result["error"]

    def test_diagnose_nonexistent_module(self, build_ctx):
        result = asyncio.get_event_loop().run_until_complete(
            diagnose(module_name="不存在的模块", query="test")
        )
        assert result["status"] == "error"
        assert "available_modules" in result

    def test_diagnose_no_match_fallback(self, build_ctx):
        """关键词完全不匹配时，应返回模块级概览。"""
        result = asyncio.get_event_loop().run_until_complete(
            diagnose(query="zzzznotexist xyzabc")
        )
        assert result["status"] == "no_exact_match"
        assert result["call_chain"]  # 模块级图

    def test_diagnose_dev_role(self, build_ctx):
        result = asyncio.get_event_loop().run_until_complete(
            diagnose(role="dev", query="register user")
        )
        assert result["status"] == "ok"
        assert "开发者" in result["guidance"]

    def test_diagnose_chinese_query(self, build_ctx):
        """中文查询也能匹配（通过函数名中的英文部分）。"""
        result = asyncio.get_event_loop().run_until_complete(
            diagnose(query="用户 register email 注册")
        )
        assert result["status"] in ("ok", "no_exact_match")
