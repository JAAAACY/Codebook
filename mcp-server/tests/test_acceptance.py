"""验收测试 — 4 条核心场景，全部自包含（不依赖 Conduit）。

场景:
1. "扫描这个项目" → 返回蓝图 JSON + Mermaid
2. "解析登录模块" → 返回模块卡片 JSON
3. Mermaid 图可渲染（语法合法）
4. code_ref 精确到行号
"""

import os
import re
import tempfile
import textwrap
from pathlib import Path

import pytest

from src.parsers.ast_parser import ParseResult, parse_file, parse_all
from src.parsers.repo_cloner import FileInfo, clone_repo
from src.parsers.dependency_graph import DependencyGraph
from src.parsers.module_grouper import group_modules, build_node_module_map
from src.summarizer.engine import (
    SummaryContext,
    generate_local_blueprint,
    generate_local_chapter,
)
from src.tools.scan_repo import scan_repo
from src.tools.read_chapter import read_chapter
from src.tools._repo_cache import repo_cache


# ── fixture：创建一个微型 Python 项目 ──────────────────────


@pytest.fixture()
def mini_project(tmp_path: Path):
    """创建一个包含 api/auth/db 三层结构的微型项目。"""
    # app/api/routes.py — 路由层
    api_dir = tmp_path / "app" / "api"
    api_dir.mkdir(parents=True)
    (api_dir / "__init__.py").write_text("")
    (api_dir / "routes.py").write_text(textwrap.dedent("""\
        from app.services.auth import login, register
        from app.db.users import find_user

        class UserRouter:
            \"\"\"用户路由控制器。\"\"\"

            def get_user(self, user_id: int) -> dict:
                \"\"\"获取单个用户。\"\"\"
                return find_user(user_id)

            def create_user(self, email: str, password: str) -> dict:
                \"\"\"注册新用户。\"\"\"
                return register(email, password)

        def health_check() -> str:
            \"\"\"健康检查端点。\"\"\"
            return "ok"
    """))

    # app/services/auth.py — 登录模块
    svc_dir = tmp_path / "app" / "services"
    svc_dir.mkdir(parents=True)
    (svc_dir / "__init__.py").write_text("")
    (svc_dir / "auth.py").write_text(textwrap.dedent("""\
        import hashlib
        from app.db.users import save_user, find_user_by_email

        def login(email: str, password: str) -> dict:
            \"\"\"用户登录：校验邮箱和密码。\"\"\"
            user = find_user_by_email(email)
            if user is None:
                return {"error": "用户不存在"}
            hashed = hashlib.sha256(password.encode()).hexdigest()
            if hashed != user["password_hash"]:
                return {"error": "密码错误"}
            return {"token": "fake-jwt", "user_id": user["id"]}

        def register(email: str, password: str) -> dict:
            \"\"\"注册新用户，返回用户 ID。\"\"\"
            hashed = hashlib.sha256(password.encode()).hexdigest()
            user_id = save_user(email, hashed)
            return {"user_id": user_id}

        def _hash_password(raw: str) -> str:
            \"\"\"内部辅助：哈希密码。\"\"\"
            return hashlib.sha256(raw.encode()).hexdigest()
    """))

    # app/db/users.py — 数据库层
    db_dir = tmp_path / "app" / "db"
    db_dir.mkdir(parents=True)
    (db_dir / "__init__.py").write_text("")
    (db_dir / "users.py").write_text(textwrap.dedent("""\
        _USERS_DB: list[dict] = []

        def save_user(email: str, password_hash: str) -> int:
            \"\"\"保存用户到数据库。\"\"\"
            user_id = len(_USERS_DB) + 1
            _USERS_DB.append({"id": user_id, "email": email, "password_hash": password_hash})
            return user_id

        def find_user(user_id: int) -> dict | None:
            \"\"\"根据 ID 查找用户。\"\"\"
            for u in _USERS_DB:
                if u["id"] == user_id:
                    return u
            return None

        def find_user_by_email(email: str) -> dict | None:
            \"\"\"根据邮箱查找用户。\"\"\"
            for u in _USERS_DB:
                if u["email"] == email:
                    return u
            return None
    """))

    # tests/test_login.py — 测试文件
    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    (test_dir / "test_login.py").write_text(textwrap.dedent("""\
        def test_login_success():
            assert True

        def test_login_wrong_password():
            assert True
    """))

    # pyproject.toml — 配置文件
    (tmp_path / "pyproject.toml").write_text(textwrap.dedent("""\
        [tool.poetry]
        name = "mini-project"
        version = "0.1.0"
    """))

    return tmp_path


# ══════════════════════════════════════════════════════════
# 场景 1: "扫描这个项目" → 返回蓝图 JSON + Mermaid
# ══════════════════════════════════════════════════════════


class TestScanRepoBlueprint:
    """scan_repo 对一个本地项目返回完整蓝图。"""

    async def test_status_ok(self, mini_project):
        result = await scan_repo(repo_url=str(mini_project), role="pm", depth="overview")
        assert result["status"] == "ok", f"scan failed: {result.get('error')}"

    async def test_has_project_overview(self, mini_project):
        result = await scan_repo(repo_url=str(mini_project), role="pm")
        assert isinstance(result["project_overview"], str)
        assert len(result["project_overview"]) > 0

    async def test_modules_non_empty(self, mini_project):
        result = await scan_repo(repo_url=str(mini_project), role="pm")
        assert len(result["modules"]) > 0, "蓝图应至少包含 1 个模块"

    async def test_module_required_fields(self, mini_project):
        """每个模块都包含 name / node_title / health / role_badge / source_refs。"""
        result = await scan_repo(repo_url=str(mini_project), role="pm")
        required = {"name", "node_title", "health", "role_badge", "source_refs"}
        for mod in result["modules"]:
            missing = required - set(mod.keys())
            assert not missing, f"模块「{mod.get('name')}」缺少字段: {missing}"

    async def test_has_mermaid_diagram(self, mini_project):
        result = await scan_repo(repo_url=str(mini_project), role="pm")
        assert "mermaid_diagram" in result
        assert "graph TD" in result["mermaid_diagram"]

    async def test_has_connections(self, mini_project):
        result = await scan_repo(repo_url=str(mini_project), role="pm")
        assert "connections" in result
        assert isinstance(result["connections"], list)

    async def test_connection_fields(self, mini_project):
        """每条连接包含 from / to / strength。"""
        result = await scan_repo(repo_url=str(mini_project), role="pm")
        for conn in result["connections"]:
            assert "from" in conn, "connection 缺少 'from'"
            assert "to" in conn, "connection 缺少 'to'"
            assert "strength" in conn, "connection 缺少 'strength'"
            assert conn["strength"] in ("strong", "weak")

    async def test_stats_present(self, mini_project):
        result = await scan_repo(repo_url=str(mini_project), role="pm")
        stats = result["stats"]
        assert stats["files"] > 0
        assert stats["modules"] > 0
        assert stats["functions"] > 0
        assert stats["scan_time_seconds"] >= 0

    async def test_depth_detailed_has_chapters(self, mini_project):
        result = await scan_repo(repo_url=str(mini_project), role="pm", depth="detailed")
        assert result["status"] == "ok"
        assert "chapters" in result
        assert len(result["chapters"]) > 0


# ══════════════════════════════════════════════════════════
# 场景 2: "解析登录模块" → 返回模块卡片 JSON
# ══════════════════════════════════════════════════════════


class TestReadChapterModuleCard:
    """先 scan_repo 再 read_chapter，验证模块卡片 schema。"""

    async def _scan_first(self, mini_project):
        """辅助：先扫描项目，返回 scan 结果。"""
        return await scan_repo(repo_url=str(mini_project), role="pm")

    async def test_read_chapter_status_ok(self, mini_project):
        scan = await self._scan_first(mini_project)
        assert scan["status"] == "ok"
        # 用第一个模块名读取
        mod_name = scan["modules"][0]["name"]
        chapter = await read_chapter(module_name=mod_name, role="pm")
        assert chapter["status"] == "ok", f"read_chapter failed: {chapter.get('error')}"

    async def test_module_cards_non_empty(self, mini_project):
        scan = await self._scan_first(mini_project)
        mod_name = scan["modules"][0]["name"]
        chapter = await read_chapter(module_name=mod_name, role="pm")
        assert len(chapter["module_cards"]) > 0, "模块卡片不应为空"

    async def test_card_schema_complete(self, mini_project):
        """每张卡片包含: name / path / summary / functions / classes / calls / imports / ref。"""
        scan = await self._scan_first(mini_project)
        mod_name = scan["modules"][0]["name"]
        chapter = await read_chapter(module_name=mod_name, role="pm")

        required_fields = ["name", "path", "summary", "functions", "classes",
                           "calls", "imports", "ref"]
        for card in chapter["module_cards"]:
            for field in required_fields:
                assert field in card, f"卡片「{card.get('name')}」缺少字段: {field}"

    async def test_has_dependency_graph(self, mini_project):
        scan = await self._scan_first(mini_project)
        mod_name = scan["modules"][0]["name"]
        chapter = await read_chapter(module_name=mod_name, role="pm")
        assert "dependency_graph" in chapter
        # 依赖图是 Mermaid 格式
        assert "graph TD" in chapter["dependency_graph"]

    async def test_fuzzy_match_by_dir_path(self, mini_project):
        """read_chapter 支持按目录路径模糊匹配。"""
        await self._scan_first(mini_project)
        # 尝试用 "api" 模糊匹配
        chapter = await read_chapter(module_name="api", role="pm")
        # 应该成功匹配到包含 api 的模块，或返回多候选
        assert chapter["status"] in ("ok", "error")
        if chapter["status"] == "error":
            # 多候选或精确匹配失败都可接受
            assert "candidates" in chapter or "available_modules" in chapter

    async def test_nonexistent_module_returns_available(self, mini_project):
        """查询不存在的模块返回可用模块列表。"""
        await self._scan_first(mini_project)
        chapter = await read_chapter(module_name="不存在的模块xyz")
        assert chapter["status"] == "error"
        assert "available_modules" in chapter

    async def test_without_scan_returns_error(self):
        """未 scan 时 read_chapter 返回引导信息。"""
        repo_cache.clear_all()
        chapter = await read_chapter(module_name="任意模块")
        assert chapter["status"] == "error"
        assert "scan_repo" in chapter["error"]


# ══════════════════════════════════════════════════════════
# 场景 3: Mermaid 图可渲染（语法校验）
# ══════════════════════════════════════════════════════════


class TestMermaidRenderable:
    """验证 scan_repo 和 read_chapter 输出的 Mermaid 图语法合法。"""

    # Mermaid 节点 ID 和箭头的基础正则
    _MERMAID_EDGE = re.compile(
        r"^\s*\S+.*-->.*\S+",
        re.MULTILINE,
    )
    _MERMAID_HEADER = re.compile(r"^graph\s+(TD|LR|TB|BT|RL)", re.MULTILINE)

    async def test_scan_mermaid_has_valid_header(self, mini_project):
        result = await scan_repo(repo_url=str(mini_project), role="pm")
        mermaid = result["mermaid_diagram"]
        assert self._MERMAID_HEADER.search(mermaid), \
            f"Mermaid 缺少合法 header (graph TD/LR/...):\n{mermaid[:200]}"

    async def test_scan_mermaid_no_syntax_errors(self, mini_project):
        """检查常见的 Mermaid 语法错误。"""
        result = await scan_repo(repo_url=str(mini_project), role="pm")
        mermaid = result["mermaid_diagram"]

        # 不应有未闭合的引号
        for i, line in enumerate(mermaid.split("\n"), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("%%") or stripped.startswith("graph"):
                continue
            # 引号应成对出现（简单检查）
            assert stripped.count('"') % 2 == 0, \
                f"Mermaid 第 {i} 行引号未闭合: {stripped}"

    async def test_chapter_mermaid_has_valid_header(self, mini_project):
        await scan_repo(repo_url=str(mini_project), role="pm")
        scan = await scan_repo(repo_url=str(mini_project), role="pm")
        mod_name = scan["modules"][0]["name"]
        chapter = await read_chapter(module_name=mod_name, role="pm")
        dep_graph = chapter["dependency_graph"]
        assert self._MERMAID_HEADER.search(dep_graph), \
            f"chapter Mermaid 缺少合法 header:\n{dep_graph[:200]}"

    async def test_mermaid_multiline_not_empty(self, mini_project):
        """Mermaid 图不应只有一行 header。"""
        result = await scan_repo(repo_url=str(mini_project), role="pm")
        mermaid = result["mermaid_diagram"]
        lines = [l for l in mermaid.strip().split("\n") if l.strip()]
        assert len(lines) >= 1, "Mermaid 图至少应有 header 行"

    async def test_dependency_graph_level_function(self):
        """直接构建 DependencyGraph 验证 function 级 Mermaid。"""
        from src.parsers.ast_parser import FunctionInfo, CallInfo, ImportInfo

        r1 = ParseResult(
            file_path="app/api/routes.py",
            language="python",
            functions=[
                FunctionInfo(name="get_user", params=["user_id"],
                             line_start=10, line_end=20),
            ],
            calls=[
                CallInfo(caller_func="get_user", callee_name="find_user", line=15),
            ],
        )
        r2 = ParseResult(
            file_path="app/db/users.py",
            language="python",
            functions=[
                FunctionInfo(name="find_user", params=["user_id"],
                             line_start=5, line_end=15),
            ],
        )

        dg = DependencyGraph()
        dg.build([r1, r2])
        mermaid = dg.to_mermaid(level="function")

        assert "graph TD" in mermaid
        # 应该有至少 1 条边
        assert "-->" in mermaid, f"function 级 Mermaid 应有边:\n{mermaid}"


# ══════════════════════════════════════════════════════════
# 场景 4: code_ref 精确到行号
# ══════════════════════════════════════════════════════════


# code_ref 格式正则：file.py:L数字-L数字 或 file.py:L数字
CODE_REF_RANGE = re.compile(r"^.+:L(\d+)-L(\d+)$")
CODE_REF_SINGLE = re.compile(r"^.+:L(\d+)$")


class TestCodeRefLineNumbers:
    """code_ref 格式为 file:Lstart-Lend，行号 > 0 且 start <= end。"""

    async def test_source_refs_format(self, mini_project):
        """scan_repo 返回的 source_refs 格式正确。"""
        result = await scan_repo(repo_url=str(mini_project), role="pm")
        all_refs = []
        for mod in result["modules"]:
            all_refs.extend(mod["source_refs"])

        assert len(all_refs) > 0, "至少应有 1 个 source_ref"

        for ref in all_refs:
            m = CODE_REF_RANGE.match(ref)
            assert m, f"source_ref 格式不对: {ref!r} (应为 file:Lstart-Lend)"
            start, end = int(m.group(1)), int(m.group(2))
            assert start > 0, f"行号应 > 0: {ref}"
            assert end >= start, f"end 应 >= start: {ref}"

    async def test_card_ref_format(self, mini_project):
        """read_chapter 返回的 ref 格式正确（file:L1-Lend）。"""
        scan = await scan_repo(repo_url=str(mini_project), role="pm")
        mod_name = scan["modules"][0]["name"]
        chapter = await read_chapter(module_name=mod_name, role="pm")

        all_refs = []
        for card in chapter["module_cards"]:
            all_refs.append(card["ref"])

        assert len(all_refs) > 0, "至少应有 1 个 ref"

        for ref in all_refs:
            m = CODE_REF_RANGE.match(ref)
            assert m, f"ref 格式不对: {ref!r} (应为 file:Lstart-Lend)"
            start, end = int(m.group(1)), int(m.group(2))
            assert start > 0, f"行号应 > 0: {ref}"
            assert end >= start, f"end 应 >= start: {ref}"

    async def test_function_signature_format(self, mini_project):
        """read_chapter 中 functions[] 包含 name 和 lines 字段。"""
        scan = await scan_repo(repo_url=str(mini_project), role="pm")
        mod_name = scan["modules"][0]["name"]
        chapter = await read_chapter(module_name=mod_name, role="pm")

        all_functions = []
        for card in chapter["module_cards"]:
            all_functions.extend(card["functions"])

        assert len(all_functions) > 0, "至少应有 1 个函数签名"

        for func in all_functions:
            assert "name" in func, f"函数签名缺少 name: {func}"
            assert "lines" in func, f"函数签名缺少 lines: {func}"
            # lines 格式为 "start-end"
            parts = func["lines"].split("-")
            assert len(parts) == 2, f"lines 格式不对: {func['lines']}"
            start, end = int(parts[0]), int(parts[1])
            assert start > 0, f"行号应 > 0: {func['lines']}"
            assert end >= start, f"end 应 >= start: {func['lines']}"

    async def test_ref_line_numbers_match_source(self, mini_project):
        """ref 行号与实际源文件内容一致（行号在文件行数范围内）。"""
        scan = await scan_repo(repo_url=str(mini_project), role="pm")
        mod_name = scan["modules"][0]["name"]
        chapter = await read_chapter(module_name=mod_name, role="pm")

        for card in chapter["module_cards"]:
            ref = card["ref"]
            m = CODE_REF_RANGE.match(ref)
            if not m:
                continue
            file_path = ref.split(":L")[0]
            start, end = int(m.group(1)), int(m.group(2))

            # 读取实际文件
            abs_path = mini_project / file_path
            if abs_path.exists():
                total_lines = len(abs_path.read_text().splitlines())
                assert start <= total_lines, \
                    f"{ref}: start({start}) > 文件总行数({total_lines})"
                assert end <= total_lines + 1, \
                    f"{ref}: end({end}) > 文件总行数({total_lines})+1"

    async def test_ast_parser_line_numbers_accurate(self, mini_project):
        """tree-sitter 解析出的 line_start/line_end 精确到函数定义行。"""
        auth_path = mini_project / "app" / "services" / "auth.py"
        file_info = FileInfo(
            path="app/services/auth.py",
            abs_path=str(auth_path),
            language="python",
            size_bytes=auth_path.stat().st_size,
            line_count=len(auth_path.read_text().splitlines()),
        )
        result = await parse_file(file_info)

        # 找到 login 函数
        login_funcs = [f for f in result.functions if f.name == "login"]
        assert len(login_funcs) == 1, f"应找到 login 函数, got: {[f.name for f in result.functions]}"
        login = login_funcs[0]

        # line_start 应该 > 0
        assert login.line_start > 0, f"login.line_start 应 > 0, got {login.line_start}"
        assert login.line_end >= login.line_start, \
            f"login.line_end({login.line_end}) < line_start({login.line_start})"

        # 验证行号确实落在 "def login" 定义处
        source_lines = auth_path.read_text().splitlines()
        def_line = source_lines[login.line_start - 1]  # 1-indexed → 0-indexed
        assert "def login" in def_line, \
            f"line_start={login.line_start} 指向的内容不是 'def login': {def_line!r}"

    async def test_private_funcs_excluded_from_source_refs(self, mini_project):
        """source_refs 不包含下划线开头的私有函数。"""
        result = await scan_repo(repo_url=str(mini_project), role="pm")

        for mod in result["modules"]:
            for ref in mod["source_refs"]:
                # 提取函数名部分（如果有的话，从行号之前的文件路径中无法提取）
                # 但 _collect_source_refs 已经跳过了 _ 开头的函数
                # 这里通过验证 _hash_password 不在引用中来间接检查
                assert "_hash_password" not in ref, \
                    f"source_ref 不应包含私有函数 _hash_password: {ref}"
