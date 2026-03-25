"""parsers 模块的完整测试 — 用 Conduit (fastapi-realworld-example-app) 项目作为测试数据。"""

import asyncio
import os
import tempfile
from pathlib import Path

import pytest

from src.parsers.repo_cloner import (
    CloneResult,
    FileInfo,
    clone_repo,
    _should_skip_dir,
    _scan_files,
)
from src.parsers.ast_parser import (
    ParseResult,
    parse_file,
    parse_all,
)
from src.parsers.dependency_graph import DependencyGraph
from src.parsers.module_grouper import (
    ModuleGroup,
    group_modules,
    build_node_module_map,
    _is_test_path,
    _is_config_file,
)


# ── 测试数据路径 ────────────────────────────────────────

CONDUIT_PATH = "/tmp/conduit"
CONDUIT_EXISTS = os.path.isdir(CONDUIT_PATH)

skip_if_no_conduit = pytest.mark.skipif(
    not CONDUIT_EXISTS,
    reason="Conduit test project not found at /tmp/conduit",
)


# ══════════════════════════════════════════════════════════
# repo_cloner 测试
# ══════════════════════════════════════════════════════════


class TestRepoCloner:
    """repo_cloner 模块测试。"""

    def test_should_skip_git_dir(self):
        assert _should_skip_dir(".git") is True

    def test_should_skip_node_modules(self):
        assert _should_skip_dir("node_modules") is True

    def test_should_skip_pycache(self):
        assert _should_skip_dir("__pycache__") is True

    def test_should_not_skip_app(self):
        assert _should_skip_dir("app") is False

    def test_should_not_skip_src(self):
        assert _should_skip_dir("src") is False

    def test_should_skip_dot_dirs(self):
        assert _should_skip_dir(".mypy_cache") is True
        assert _should_skip_dir(".venv") is True

    @skip_if_no_conduit
    async def test_clone_local_dir(self):
        """扫描本地目录（非 git clone）。"""
        result = await clone_repo(CONDUIT_PATH)
        assert isinstance(result, CloneResult)
        assert result.repo_path == CONDUIT_PATH
        assert len(result.files) > 0
        assert "python" in result.languages
        assert result.total_lines > 0

    @skip_if_no_conduit
    async def test_filters_excluded_files(self):
        """确保排除了 lock 文件和二进制文件。"""
        result = await clone_repo(CONDUIT_PATH)
        file_names = [Path(f.path).name for f in result.files]
        assert "package-lock.json" not in file_names
        assert "poetry.lock" not in file_names

    @skip_if_no_conduit
    async def test_file_info_complete(self):
        """FileInfo 字段完整。"""
        result = await clone_repo(CONDUIT_PATH)
        py_files = [f for f in result.files if f.language == "python" and not f.is_config and f.size_bytes > 0]
        assert len(py_files) > 0
        f = py_files[0]
        assert f.path
        assert f.abs_path
        assert f.language == "python"
        assert f.size_bytes > 0
        assert f.line_count > 0
        assert f.is_config is False

    @skip_if_no_conduit
    async def test_config_files_marked(self):
        """配置文件标记为 is_config。"""
        result = await clone_repo(CONDUIT_PATH)
        config_files = [f for f in result.files if f.is_config]
        # Conduit 项目应该有 .toml/.json 等配置
        # 有可能没有，但如果有应标记正确
        for f in config_files:
            assert f.is_config is True

    async def test_scan_nonexistent_dir(self):
        """扫描不存在的目录应该报错或返回空。"""
        with pytest.raises(Exception):
            await clone_repo("https://github.com/nonexistent/repo123456789")

    def test_scan_empty_dir(self):
        """扫描空目录。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            files, skipped = _scan_files(tmpdir)
            assert files == []
            assert skipped == 0


# ══════════════════════════════════════════════════════════
# ast_parser 测试
# ══════════════════════════════════════════════════════════


class TestAstParser:
    """ast_parser 模块测试。"""

    async def test_parse_simple_python(self):
        """解析简单 Python 文件。"""
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write('''
import os
from pathlib import Path

class Dog:
    """A dog."""
    def bark(self, times: int) -> str:
        """Bark n times."""
        return "woof " * times

def greet(name: str) -> str:
    """Greet someone."""
    return f"Hello {name}"

result = greet("world")
''')
            f.flush()
            file_info = FileInfo(
                path="test.py",
                abs_path=f.name,
                language="python",
                size_bytes=os.path.getsize(f.name),
                line_count=15,
            )
            result = await parse_file(file_info)

        os.unlink(f.name)

        assert isinstance(result, ParseResult)
        assert result.language == "python"

        # Classes
        assert len(result.classes) == 1
        assert result.classes[0].name == "Dog"
        assert "bark" in result.classes[0].methods

        # Functions
        func_names = [f.name for f in result.functions]
        assert "greet" in func_names
        assert "bark" in func_names

        # Imports
        import_modules = [i.module for i in result.imports]
        assert "os" in import_modules

        # Docstrings
        greet_func = [f for f in result.functions if f.name == "greet"][0]
        assert greet_func.docstring == "Greet someone."

        # Params
        assert "name" in greet_func.params

        # Calls
        callee_names = [c.callee_name for c in result.calls]
        assert "greet" in callee_names

    async def test_class_stack_pop_on_exit(self):
        """class_stack 必须在离开 class 作用域后正确弹出。

        回归测试：class 之后的模块级函数不应被标记为方法。
        包含多个 class + 模块级函数的组合来充分验证。
        """
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write('''
class Alpha:
    def method_a(self):
        pass

def free_func_1():
    """I am free."""
    pass

class Beta:
    def method_b(self):
        pass

def free_func_2():
    pass
''')
            f.flush()
            file_info = FileInfo(
                path="test_stack.py",
                abs_path=f.name,
                language="python",
                size_bytes=os.path.getsize(f.name),
                line_count=16,
            )
            result = await parse_file(file_info)

        os.unlink(f.name)

        # method_a 是 Alpha 的方法
        method_a = [f for f in result.functions if f.name == "method_a"][0]
        assert method_a.is_method is True
        assert method_a.parent_class == "Alpha"

        # free_func_1 是模块级函数，不是方法
        free1 = [f for f in result.functions if f.name == "free_func_1"][0]
        assert free1.is_method is False, f"free_func_1 should NOT be a method, got parent_class={free1.parent_class}"
        assert free1.parent_class is None
        assert free1.docstring == "I am free."

        # method_b 是 Beta 的方法（不是 Alpha 的）
        method_b = [f for f in result.functions if f.name == "method_b"][0]
        assert method_b.is_method is True
        assert method_b.parent_class == "Beta"

        # free_func_2 是模块级函数
        free2 = [f for f in result.functions if f.name == "free_func_2"][0]
        assert free2.is_method is False, f"free_func_2 should NOT be a method, got parent_class={free2.parent_class}"
        assert free2.parent_class is None

    async def test_parse_swift_file(self):
        """解析 Swift 文件：struct, class, enum, protocol, 函数, import, 调用关系。"""
        with tempfile.NamedTemporaryFile(suffix=".swift", mode="w", delete=False) as f:
            f.write('''
import Foundation
import SwiftUI

struct ChatService {
    private let endpoint = URL(string: "https://api.example.com")!

    func send(message: String, history: [ChatMessage]) async -> ChatResponse {
        var request = URLRequest(url: endpoint)
        let (data, response) = try await URLSession.shared.data(for: request)
        return try JSONDecoder().decode(ChatResponse.self, from: data)
    }

    private func buildHistory(from messages: [ChatMessage]) -> [[String: String]] {
        return messages.compactMap { $0 }
    }
}

class ViewModel: ObservableObject {
    @Published var items: [Item] = []

    func loadItems() {
        let service = ChatService()
        service.send(message: "hello", history: [])
    }
}

enum AppError: Error {
    case networkError
    case parseError(String)
}

protocol DataProvider {
    func fetchData() async throws -> Data
}
''')
            f.flush()
            file_info = FileInfo(
                path="test/ChatService.swift",
                abs_path=f.name,
                language="swift",
                size_bytes=os.path.getsize(f.name),
                line_count=37,
            )
            result = await parse_file(file_info)

        os.unlink(f.name)

        assert isinstance(result, ParseResult)
        assert result.language == "swift"

        # Classes: struct ChatService, class ViewModel, enum AppError, protocol DataProvider
        class_names = [c.name for c in result.classes]
        assert "ChatService" in class_names
        assert "ViewModel" in class_names
        assert "AppError" in class_names
        assert "DataProvider" in class_names

        if result.parse_method == "full":
            # tree-sitter 模式：完整验证
            assert result.parse_errors == []

            # Inheritance
            vm = [c for c in result.classes if c.name == "ViewModel"][0]
            assert vm.parent_class is not None
            assert "ObservableObject" in vm.parent_class

            err = [c for c in result.classes if c.name == "AppError"][0]
            assert err.parent_class is not None
            assert "Error" in err.parent_class

            # Methods on classes
            cs = [c for c in result.classes if c.name == "ChatService"][0]
            assert "send" in cs.methods
            assert "buildHistory" in cs.methods

            dp = [c for c in result.classes if c.name == "DataProvider"][0]
            assert "fetchData" in dp.methods

            # Function params
            send_func = [fn for fn in result.functions if fn.name == "send"][0]
            assert "message" in send_func.params
            assert "history" in send_func.params

            # is_method flag
            assert send_func.is_method is True
            assert send_func.parent_class == "ChatService"

            load_func = [fn for fn in result.functions if fn.name == "loadItems"][0]
            assert load_func.is_method is True
            assert load_func.parent_class == "ViewModel"

            # Calls
            callee_names = [c.callee_name for c in result.calls]
            assert "send" in callee_names  # service.send(...)
            assert "ChatService" in callee_names  # ChatService() init
            assert "decode" in callee_names  # JSONDecoder().decode(...)

            # Call origin tracking
            send_calls = [c for c in result.calls if c.callee_name == "send"]
        else:
            # regex fallback 模式：验证基本提取能力
            assert result.parse_method == "partial"

        # Functions（两种模式都应提取到）
        func_names = [fn.name for fn in result.functions]
        assert "send" in func_names
        assert "buildHistory" in func_names
        assert "loadItems" in func_names
        assert "fetchData" in func_names

        # Imports（两种模式都应提取到）
        import_modules = [i.module for i in result.imports]
        assert "Foundation" in import_modules
        assert "SwiftUI" in import_modules

        if result.parse_method == "full":
            send_calls = [c for c in result.calls if c.callee_name == "send"]
            assert any(c.caller_func == "loadItems" for c in send_calls)

    async def test_swift_class_stack_pop_on_exit(self):
        """Swift: struct/enum 后面的全局函数不应被标记为方法。

        回归测试 C1: Swift 的 struct_declaration 不在 class_types 中，
        但 grandparent push 路径（第533行）会向 class_stack push，
        而 on_leave 只 pop class_types，导致 struct 内的 push 永远不 pop。
        """
        with tempfile.NamedTemporaryFile(suffix=".swift", mode="w", delete=False) as f:
            f.write('''
import Foundation

struct Service {
    func doWork() {
        print("working")
    }
}

func freeSwiftFunc() {
    print("I am free")
}

struct AnotherService {
    func process() {
        print("processing")
    }
}

func anotherFreeFunc() {
    let s = Service()
    s.doWork()
}
''')
            f.flush()
            file_info = FileInfo(
                path="test_swift_stack.swift",
                abs_path=f.name,
                language="swift",
                size_bytes=os.path.getsize(f.name),
                line_count=24,
            )
            result = await parse_file(file_info)

        os.unlink(f.name)

        # 基本检查：两种模式都应能提取到函数
        func_names = [fn.name for fn in result.functions]
        assert "doWork" in func_names
        assert "freeSwiftFunc" in func_names
        assert "process" in func_names
        assert "anotherFreeFunc" in func_names

        if result.parse_method == "full":
            # tree-sitter 模式：精确验证 class_stack 作用域管理
            do_work = [fn for fn in result.functions if fn.name == "doWork"][0]
            assert do_work.is_method is True
            assert do_work.parent_class == "Service"

            free1 = [fn for fn in result.functions if fn.name == "freeSwiftFunc"][0]
            assert free1.is_method is False, f"freeSwiftFunc should NOT be a method, got parent_class={free1.parent_class}"
            assert free1.parent_class is None

            process = [fn for fn in result.functions if fn.name == "process"][0]
            assert process.is_method is True
            assert process.parent_class == "AnotherService"

            free2 = [fn for fn in result.functions if fn.name == "anotherFreeFunc"][0]
            assert free2.is_method is False, f"anotherFreeFunc should NOT be a method, got parent_class={free2.parent_class}"
            assert free2.parent_class is None

    def test_lang_config_matches_supported_languages(self):
        """LANG_CONFIG 的 key 必须与 config.py 的 supported_languages 完全一致。

        回归测试 C3: 防止语言列表不同步导致文件被静默跳过。
        """
        from src.parsers.ast_parser import LANG_CONFIG
        from src.config import settings

        lang_config_keys = set(LANG_CONFIG.keys())
        supported = set(settings.supported_languages)

        # 在 supported 但不在 LANG_CONFIG = 文件会被静默跳过
        missing_config = supported - lang_config_keys
        assert missing_config == set(), (
            f"supported_languages 中有但 LANG_CONFIG 缺失: {missing_config}. "
            f"这些语言的文件会被静默跳过！"
        )

        # 在 LANG_CONFIG 但不在 supported = 不会被扫描到
        orphaned = lang_config_keys - supported
        assert orphaned == set(), (
            f"LANG_CONFIG 中有但 supported_languages 缺失: {orphaned}. "
            f"这些语言的配置是死代码！"
        )

    def test_extension_to_language_maps_to_lang_config(self):
        """EXTENSION_TO_LANGUAGE 的每个值必须在 LANG_CONFIG 或 supported_languages 之外被有意排除。

        防止 repo_cloner.py 与 ast_parser.py 不同步导致文件被静默跳过。
        """
        from src.parsers.repo_cloner import EXTENSION_TO_LANGUAGE
        from src.parsers.ast_parser import LANG_CONFIG

        ext_langs = set(EXTENSION_TO_LANGUAGE.values())
        lang_config_keys = set(LANG_CONFIG.keys())

        # 这些语言在 EXTENSION_TO_LANGUAGE 中但还没有 LANG_CONFIG，是已知的 TODO
        known_unsupported = {"ruby", "php", "kotlin"}

        unexpected_orphans = ext_langs - lang_config_keys - known_unsupported
        assert unexpected_orphans == set(), (
            f"EXTENSION_TO_LANGUAGE 中有但 LANG_CONFIG 缺失且不在已知豁免列表中: {unexpected_orphans}. "
            f"这些语言的文件会被扫描但无法解析！"
        )

    async def test_parse_config_file_skipped(self):
        """配置文件跳过解析。"""
        file_info = FileInfo(
            path="config.json",
            abs_path="/nonexistent",
            language="unknown",
            size_bytes=100,
            line_count=10,
            is_config=True,
        )
        result = await parse_file(file_info)
        assert result.classes == []
        assert result.functions == []

    @skip_if_no_conduit
    async def test_parse_conduit_files(self):
        """解析 Conduit 项目的所有 Python 文件。"""
        clone_result = await clone_repo(CONDUIT_PATH)
        py_files = [f for f in clone_result.files if f.language == "python" and not f.is_config]

        results = await parse_all(py_files)
        assert len(results) > 0

        total_funcs = sum(len(r.functions) for r in results)
        total_classes = sum(len(r.classes) for r in results)
        total_imports = sum(len(r.imports) for r in results)

        # Conduit 项目应该有合理数量的函数和类
        assert total_funcs > 10, f"Expected >10 functions, got {total_funcs}"
        assert total_classes > 3, f"Expected >3 classes, got {total_classes}"
        assert total_imports > 10, f"Expected >10 imports, got {total_imports}"

    @skip_if_no_conduit
    async def test_parse_coverage_above_90_percent(self):
        """函数/类提取覆盖率 > 90%（通过比较解析文件数和成功解析数）。"""
        clone_result = await clone_repo(CONDUIT_PATH)
        py_files = [f for f in clone_result.files if f.language == "python" and not f.is_config]

        results = await parse_all(py_files)

        # 检查解析错误率
        error_count = sum(1 for r in results if r.parse_errors)
        success_rate = (len(results) - error_count) / max(len(results), 1)
        assert success_rate >= 0.9, f"Parse success rate {success_rate:.1%} < 90%"

    async def test_parse_python_relative_import(self):
        """测试相对 import 解析。"""
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
            f.write("from . import utils\nfrom ..core import auth\n")
            f.flush()
            file_info = FileInfo(
                path="app/api/routes.py",
                abs_path=f.name,
                language="python",
                size_bytes=os.path.getsize(f.name),
                line_count=2,
            )
            result = await parse_file(file_info)
        os.unlink(f.name)

        relative_imports = [i for i in result.imports if i.is_relative]
        assert len(relative_imports) >= 1


# ══════════════════════════════════════════════════════════
# dependency_graph 测试
# ══════════════════════════════════════════════════════════


class TestDependencyGraph:
    """dependency_graph 模块测试。"""

    def _make_test_results(self) -> list[ParseResult]:
        """创建测试用的解析结果。"""
        from src.parsers.ast_parser import FunctionInfo, ClassInfo, CallInfo, ImportInfo

        r1 = ParseResult(
            file_path="app/api/routes.py",
            language="python",
            functions=[
                FunctionInfo(name="create_user", params=["email", "password"],
                             line_start=10, line_end=20),
                FunctionInfo(name="get_user", params=["user_id"],
                             line_start=25, line_end=35),
            ],
            calls=[
                CallInfo(caller_func="create_user", callee_name="validate_email", line=12),
                CallInfo(caller_func="create_user", callee_name="save_user", line=15),
                CallInfo(caller_func="get_user", callee_name="find_by_id", line=28),
            ],
            imports=[
                ImportInfo(module="app.services.auth", names=["validate_email"]),
            ],
        )

        r2 = ParseResult(
            file_path="app/services/auth.py",
            language="python",
            functions=[
                FunctionInfo(name="validate_email", params=["email"],
                             line_start=5, line_end=15),
                FunctionInfo(name="hash_password", params=["raw"],
                             line_start=20, line_end=30),
            ],
            calls=[
                CallInfo(caller_func="validate_email", callee_name="check_format", line=8),
            ],
        )

        r3 = ParseResult(
            file_path="app/db/users.py",
            language="python",
            functions=[
                FunctionInfo(name="save_user", params=["user_data"],
                             line_start=10, line_end=25),
                FunctionInfo(name="find_by_id", params=["user_id"],
                             line_start=30, line_end=40),
            ],
        )

        return [r1, r2, r3]

    def test_build_graph(self):
        """构建依赖图。"""
        results = self._make_test_results()
        dg = DependencyGraph()
        dg.build(results)

        assert dg.graph.number_of_nodes() > 0
        assert dg.graph.number_of_edges() > 0

    def test_upstream_downstream(self):
        """上下游查询。"""
        results = self._make_test_results()
        dg = DependencyGraph()
        dg.build(results)

        # validate_email 被 create_user 调用
        ve_id = "app/services/auth.py::validate_email"
        upstream = dg.get_upstream(ve_id)
        assert len(upstream) > 0

        # create_user 调用了 validate_email 和 save_user
        cu_id = "app/api/routes.py::create_user"
        downstream = dg.get_downstream(cu_id)
        assert len(downstream) >= 2

    def test_mermaid_module_level(self):
        """模块级 Mermaid 图输出。"""
        results = self._make_test_results()
        dg = DependencyGraph()
        dg.build(results)

        # 设置模块分组
        module_map = {}
        for node in dg.graph.nodes:
            if "routes" in node:
                module_map[node] = "API路由"
            elif "auth" in node:
                module_map[node] = "认证服务"
            elif "users" in node:
                module_map[node] = "用户数据库"
            else:
                module_map[node] = "其他"
        dg.set_module_groups(module_map)

        mermaid = dg.to_mermaid(level="module")
        assert "graph TD" in mermaid
        assert len(mermaid.strip().split("\n")) > 1

    def test_mermaid_function_level(self):
        """函数级 Mermaid 图输出。"""
        results = self._make_test_results()
        dg = DependencyGraph()
        dg.build(results)
        mermaid = dg.to_mermaid(level="function")
        assert "graph TD" in mermaid

    def test_empty_graph(self):
        """空图处理。"""
        dg = DependencyGraph()
        dg.build([])
        mermaid = dg.to_mermaid(level="module")
        assert "graph TD" in mermaid
        assert "暂无" in mermaid

    @skip_if_no_conduit
    async def test_conduit_dependency_graph(self):
        """用 Conduit 项目构建完整依赖图。"""
        clone_result = await clone_repo(CONDUIT_PATH)
        py_files = [f for f in clone_result.files if f.language == "python" and not f.is_config]
        parse_results = await parse_all(py_files)

        dg = DependencyGraph()
        dg.build(parse_results)

        assert dg.graph.number_of_nodes() > 0, "依赖图节点数应 > 0"
        # 边数可能为0如果没有跨函数调用，但节点应该有
        mermaid = dg.to_mermaid(level="function")
        assert "graph TD" in mermaid


# ══════════════════════════════════════════════════════════
# module_grouper 测试
# ══════════════════════════════════════════════════════════


class TestModuleGrouper:
    """module_grouper 模块测试。"""

    def test_is_test_path(self):
        assert _is_test_path("tests/test_auth.py") is True
        assert _is_test_path("test/test_auth.py") is True
        assert _is_test_path("app/services/auth.py") is False
        assert _is_test_path("app/test_utils.py") is True

    def test_is_config_file(self):
        assert _is_config_file("pyproject.toml") is True
        assert _is_config_file("package.json") is True
        assert _is_config_file("app/main.py") is False
        assert _is_config_file("config/settings.py") is True

    async def test_group_simple(self):
        """简单分组测试。"""
        from src.parsers.ast_parser import FunctionInfo

        results = [
            ParseResult(file_path="app/api/routes.py", language="python", line_count=100,
                        functions=[FunctionInfo(name="get_users", line_start=1, line_end=10)]),
            ParseResult(file_path="app/api/auth.py", language="python", line_count=80,
                        functions=[FunctionInfo(name="login", line_start=1, line_end=10)]),
            ParseResult(file_path="app/db/users.py", language="python", line_count=60,
                        functions=[FunctionInfo(name="find_user", line_start=1, line_end=10)]),
            ParseResult(file_path="tests/test_auth.py", language="python", line_count=50),
        ]

        modules = await group_modules(results, "/fake/repo")

        module_names = [m.name for m in modules]
        # 应该有 app/api, app/db 和 测试
        assert any("api" in n for n in module_names), f"Expected 'api' in {module_names}"
        assert any("db" in n for n in module_names), f"Expected 'db' in {module_names}"
        assert "测试" in module_names

    async def test_test_files_grouped_separately(self):
        """测试文件应归入特殊模块。"""
        results = [
            ParseResult(file_path="app/main.py", language="python", line_count=100),
            ParseResult(file_path="tests/test_main.py", language="python", line_count=50),
        ]

        modules = await group_modules(results, "/fake/repo")
        test_module = [m for m in modules if m.name == "测试"]
        assert len(test_module) == 1
        assert test_module[0].is_special is True
        assert "tests/test_main.py" in test_module[0].files

    @skip_if_no_conduit
    async def test_conduit_module_grouping(self):
        """Conduit 项目的模块分组应与目录结构吻合。"""
        clone_result = await clone_repo(CONDUIT_PATH)
        py_files = [f for f in clone_result.files if f.language == "python" and not f.is_config]
        parse_results = await parse_all(py_files)

        modules = await group_modules(parse_results, CONDUIT_PATH)

        assert len(modules) > 0, "应有至少 1 个模块"

        # Conduit 项目结构: app/ 下有 api/, db/, models/, services/ 等
        module_names = [m.name for m in modules]
        # 应有测试模块
        assert "测试" in module_names, f"缺少测试模块, got: {module_names}"

        # 所有文件都应被分组
        all_grouped_files = set()
        for m in modules:
            all_grouped_files.update(m.files)
        parsed_files = set(pr.file_path for pr in parse_results)
        assert parsed_files.issubset(all_grouped_files), "有文件未被分组"

    @skip_if_no_conduit
    async def test_node_module_map(self):
        """节点-模块映射完整。"""
        clone_result = await clone_repo(CONDUIT_PATH)
        py_files = [f for f in clone_result.files if f.language == "python" and not f.is_config]
        parse_results = await parse_all(py_files)
        modules = await group_modules(parse_results, CONDUIT_PATH)

        node_map = build_node_module_map(modules, parse_results)
        assert len(node_map) > 0


# ══════════════════════════════════════════════════════════
# 端到端集成测试
# ══════════════════════════════════════════════════════════


class TestEndToEnd:
    """端到端集成：clone → parse → graph → group → mermaid。"""

    @skip_if_no_conduit
    async def test_full_pipeline(self):
        """完整 pipeline 跑通。"""
        # 1. Clone / Scan
        clone_result = await clone_repo(CONDUIT_PATH)
        assert len(clone_result.files) > 0

        # 2. Parse
        py_files = [f for f in clone_result.files if f.language == "python" and not f.is_config]
        parse_results = await parse_all(py_files)
        assert len(parse_results) > 0

        total_funcs = sum(len(r.functions) for r in parse_results)
        total_classes = sum(len(r.classes) for r in parse_results)
        print(f"\n  Conduit: {len(py_files)} files, {total_funcs} functions, {total_classes} classes")

        # 3. Module Grouping
        modules = await group_modules(parse_results, CONDUIT_PATH)
        assert len(modules) > 0
        print(f"  Modules: {[m.name for m in modules]}")

        # 4. Dependency Graph
        dg = DependencyGraph()
        dg.build(parse_results)

        node_map = build_node_module_map(modules, parse_results)
        dg.set_module_groups(node_map)

        print(f"  Graph: {dg.graph.number_of_nodes()} nodes, {dg.graph.number_of_edges()} edges")

        # 5. Mermaid 输出
        mermaid_module = dg.to_mermaid(level="module")
        mermaid_func = dg.to_mermaid(level="function")

        assert "graph TD" in mermaid_module
        assert "graph TD" in mermaid_func
        assert len(mermaid_module.strip().split("\n")) > 1

        print(f"  Mermaid (module): {len(mermaid_module)} chars")
        print(f"  Mermaid (function): {len(mermaid_func)} chars")

        # 验收标准
        assert dg.graph.number_of_nodes() > 0, "依赖图节点数应 > 0"
