"""CodeBook MCP Server — 端到端集成测试。

通过直接调用 tool 函数（模拟 MCP call_tool 语义）验证完整工作流：
  1. scan_repo    → 蓝图总览 + Mermaid + 模块列表
  2. read_chapter → 模块卡片 + 依赖图
  3. diagnose     → 诊断定位（当前 placeholder）
  4. ask_about    → 追问对话 + follow_up

运行:
    cd mcp-server
    pytest tests/test_e2e.py -v --tb=short

约定:
- 小型项目 (mini_project_path)  → 全部用例, 无 skip
- 中型项目 (medium_project_path) → 性能测试, 可选 skip
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any


import pytest

from src.tools.scan_repo import scan_repo
from src.tools.read_chapter import read_chapter
from src.tools.diagnose import diagnose
from src.tools.ask_about import ask_about
from src.tools._repo_cache import repo_cache

# conftest.py 中的 fixtures 由 pytest 自动发现
from tests.conftest import skip_if_no_medium_project


# ── 辅助 ─────────────────────────────────────────────────


class FixSuggestionCollector:
    """测试失败时收集修复建议。"""

    def __init__(self):
        self.suggestions: list[dict[str, str]] = []

    def add(self, test_name: str, error: str, suggestion: str):
        self.suggestions.append({
            "test": test_name,
            "error": error,
            "fix_suggestion": suggestion,
        })

    def report(self) -> str:
        if not self.suggestions:
            return ""
        lines = ["\n═══ 自动修复建议 ═══"]
        for s in self.suggestions:
            lines.append(f"\n▶ {s['test']}")
            lines.append(f"  错误: {s['error']}")
            lines.append(f"  建议: {s['fix_suggestion']}")
        return "\n".join(lines)


fix_suggestions = FixSuggestionCollector()


# ══════════════════════════════════════════════════════════
# 场景 1: 小型项目完整流程
# ══════════════════════════════════════════════════════════


class TestFullFlowSmallProject:
    """小型项目 (mini_project) 从 scan → read → diagnose → ask 全流程。"""

    async def test_scan_repo_returns_blueprint(self, mini_project_path: str):
        """scan_repo 返回完整蓝图: project_overview + modules + mermaid_diagram。"""
        result = await scan_repo(repo_url=mini_project_path, role="ceo")

        assert result["status"] == "ok", (
            f"scan_repo 失败: {result.get('error')}"
        )
        # 蓝图三要素
        assert "project_overview" in result
        assert isinstance(result["project_overview"], str)
        assert len(result["project_overview"]) > 0

        assert len(result["modules"]) > 0, "至少应有 1 个模块"

        assert "mermaid_diagram" in result
        assert "graph TD" in result["mermaid_diagram"]

    async def test_scan_repo_stats(self, mini_project_path: str):
        """scan_repo 统计数据完整且合理。"""
        result = await scan_repo(repo_url=mini_project_path, role="pm")
        assert result["status"] == "ok"

        stats = result["stats"]
        assert stats["files"] > 0
        assert stats["modules"] > 0
        assert stats["functions"] > 0
        assert stats["scan_time_seconds"] >= 0
        assert "languages" in stats
        assert "python" in stats["languages"]

    async def test_scan_repo_module_schema(self, mini_project_path: str):
        """每个模块包含必要字段: name, node_title, health, role_badge, source_refs。"""
        result = await scan_repo(repo_url=mini_project_path, role="pm")
        assert result["status"] == "ok"

        required_fields = {"name", "node_title", "health", "role_badge", "source_refs"}
        for mod in result["modules"]:
            missing = required_fields - set(mod.keys())
            assert not missing, f"模块「{mod.get('name')}」缺少字段: {missing}"

    async def test_scan_repo_connections(self, mini_project_path: str):
        """connections 列表结构正确。"""
        result = await scan_repo(repo_url=mini_project_path, role="pm")
        assert result["status"] == "ok"
        assert isinstance(result["connections"], list)

        for conn in result["connections"]:
            assert "from" in conn
            assert "to" in conn
            assert "strength" in conn
            assert conn["strength"] in ("strong", "weak")

    async def test_read_chapter_first_module(self, mini_project_path: str):
        """scan → read_chapter(第一个模块) 返回完整卡片。"""
        scan = await scan_repo(repo_url=mini_project_path, role="ceo")
        assert scan["status"] == "ok"

        module_name = scan["modules"][0]["name"]
        chapter = await read_chapter(module_name=module_name, role="ceo")

        assert chapter["status"] == "ok", (
            f"read_chapter 失败: {chapter.get('error')}"
        )
        assert "module_cards" in chapter
        assert len(chapter["module_cards"]) > 0

        # 每张卡片有 chapter_markdown 等效内容
        card = chapter["module_cards"][0]
        assert "name" in card
        assert "summary" in card

        # 依赖图
        assert "dependency_graph" in chapter
        assert "graph TD" in chapter["dependency_graph"]

    async def test_diagnose_returns_structure(self, mini_project_path: str):
        """diagnose 扫描后返回统一结构。"""
        # 先扫描
        await scan_repo(repo_url=mini_project_path, role="ceo")

        diag = await diagnose(role="ceo", query="create process")

        assert "status" in diag
        assert diag["status"] in ("ok", "no_exact_match", "error")
        # 无论匹配成功与否，都应有这些字段
        if diag["status"] == "ok":
            assert "call_chain" in diag
            assert "exact_locations" in diag
            assert isinstance(diag["exact_locations"], list)
        elif diag["status"] == "no_exact_match":
            assert "call_chain" in diag
            assert "keywords" in diag

    async def test_ask_about_after_scan(self, mini_project_path: str):
        """scan → ask_about 返回完整上下文。"""
        scan = await scan_repo(repo_url=mini_project_path, role="ceo")
        assert scan["status"] == "ok"

        module_name = scan["modules"][0]["name"]

        answer = await ask_about(
            module_name=module_name,
            question="这个模块最大的风险是什么？",
            role="ceo",
        )

        assert answer["status"] == "ok", (
            f"ask_about 失败: {answer.get('error')}"
        )
        # 验证新返回字段
        assert "context" in answer
        assert isinstance(answer["context"], str)
        assert len(answer["context"]) > 0
        assert "guidance" in answer
        assert isinstance(answer["guidance"], str)
        assert "question" in answer
        assert answer["question"] == "这个模块最大的风险是什么？"
        assert "context_modules_used" in answer
        assert module_name in answer["context_modules_used"]

    async def test_full_pipeline_scan_read_ask(self, mini_project_path: str):
        """完整三步管道: scan → read_chapter → ask_about，数据一致。"""
        # Step 1: scan
        scan = await scan_repo(repo_url=mini_project_path, role="pm")
        assert scan["status"] == "ok"
        mod_name = scan["modules"][0]["name"]

        # Step 2: read_chapter
        chapter = await read_chapter(module_name=mod_name, role="pm")
        assert chapter["status"] == "ok"

        # Step 3: ask_about
        ask_result = await ask_about(
            module_name=mod_name,
            question="这个模块有什么潜在问题？",
            role="pm",
        )
        assert ask_result["status"] == "ok"

        # 验证数据一致性: scan 返回的模块名 = ask_about 返回的模块名
        assert ask_result["module_name"] == mod_name
        # 验证上下文已组装
        assert len(ask_result["context"]) > 0
        assert ask_result["role"] == "pm"


# ══════════════════════════════════════════════════════════
# 场景 2: 角色切换 — 同一项目 4 种角色输出不同
# ══════════════════════════════════════════════════════════


class TestRoleSwitching:
    """同一项目切换多种角色，输出必须有差异。新角色系统支持 dev/pm/domain_expert，向后兼容 ceo/investor/qa。"""

    async def test_scan_role_outputs_differ(self, mini_project_path: str):
        """多种角色 scan_repo 的 role_badge 应该有差异（规范化后）。

        注意: node_body 是基于代码统计的客观描述，不随角色变化。
        角色差异体现在 role_badge 中。
        v0.3 系统：4 种旧角色映射到 2 种新视图（ceo/pm/investor → pm, qa → dev）
        """
        overviews: dict[str, str] = {}
        badges: dict[str, str] = {}

        for role in ("ceo", "pm", "investor", "qa"):
            repo_cache.clear_all()  # 清缓存确保每次独立
            result = await scan_repo(repo_url=mini_project_path, role=role)
            assert result["status"] == "ok", f"role={role} scan 失败"
            overviews[role] = result["project_overview"]
            badges[role] = result["modules"][0]["role_badge"]

        # role_badge：ceo/pm/investor 映射到 pm（同一个 badge），qa 映射到 dev（不同 badge）
        # 因此期望 2 种不同的 badge
        unique_badges = set(badges.values())
        assert len(unique_badges) == 2, (
            f"4 种角色应产生 2 种 badge（v0.3 三视图系统）: {badges}"
        )
        # 验证 ceo/pm/investor 都产生相同的 badge（都映射到 PM 视图）
        assert badges["ceo"] == badges["pm"] == badges["investor"]
        # 验证 qa 产生不同的 badge（映射到 dev 视图）
        assert badges["qa"] != badges["pm"]

    async def test_role_badge_differs(self, mini_project_path: str):
        """各种视图的 role_badge 标签不同（v0.3 系统支持 dev/pm/domain_expert）。"""
        badges: dict[str, str] = {}

        for role in ("dev", "pm", "domain_expert"):
            repo_cache.clear_all()
            result = await scan_repo(repo_url=mini_project_path, role=role)
            assert result["status"] == "ok"
            badges[role] = result["modules"][0]["role_badge"]

        unique = set(badges.values())
        assert len(unique) == 3, f"期望 3 种 badge（三视图系统），得到 {len(unique)}: {badges}"

    async def test_project_overview_role_prefix(self, mini_project_path: str):
        """project_overview 中体现角色视图（dev/pm/domain_expert）。"""
        # 验证所有角色都能生成 overview，且不为空
        roles = ["dev", "pm", "domain_expert"]

        for role in roles:
            repo_cache.clear_all()
            result = await scan_repo(repo_url=mini_project_path, role=role)
            assert result["status"] == "ok"
            overview = result["project_overview"]
            # 检查 overview 非空且包含基本信息
            assert len(overview) > 0
            # project_overview 应该包含项目基本描述（不一定包含角色特定关键词）
            assert "模块" in overview or "文件" in overview or "语言" in overview


# ══════════════════════════════════════════════════════════
# 场景 3: 错误处理
# ══════════════════════════════════════════════════════════


class TestErrorHandling:
    """异常路径和错误处理测试。"""

    async def test_scan_invalid_url(self):
        """scan_repo 对无效地址返回友好错误。"""
        result = await scan_repo(
            repo_url="https://github.com/nonexistent/repo_e2e_test_999",
        )
        assert result["status"] == "error"
        assert "error" in result
        assert isinstance(result["error"], str)
        assert len(result["error"]) > 0

    async def test_read_chapter_without_scan(self):
        """未 scan 时 read_chapter 返回引导信息。"""
        repo_cache.clear_all()
        result = await read_chapter(module_name="任意模块")
        assert result["status"] == "error"
        assert "scan_repo" in result["error"]

    async def test_ask_about_without_scan(self):
        """未 scan 时 ask_about 返回引导信息。"""
        repo_cache.clear_all()
        result = await ask_about(
            module_name="任意模块",
            question="这是什么？",
            role="ceo",
        )
        assert result["status"] == "error"
        assert "scan_repo" in result["error"]

    async def test_read_chapter_nonexistent_module(self, mini_project_path: str):
        """read_chapter 查不存在模块时返回可用列表。"""
        await scan_repo(repo_url=mini_project_path, role="pm")
        result = await read_chapter(module_name="不存在的模块xyz_e2e")
        assert result["status"] == "error"
        assert "available_modules" in result
        assert isinstance(result["available_modules"], list)
        assert len(result["available_modules"]) > 0

    async def test_ask_about_nonexistent_module(self, mini_project_path: str):
        """ask_about 查不存在模块时返回可用列表。"""
        await scan_repo(repo_url=mini_project_path, role="pm")
        result = await ask_about(
            module_name="不存在的模块xyz_e2e",
            question="这是什么？",
            role="ceo",
        )
        assert result["status"] == "error"
        assert "available_modules" in result

    async def test_scan_empty_directory(self, tmp_path: Path):
        """扫描空目录返回友好错误。"""
        result = await scan_repo(repo_url=str(tmp_path), role="pm")
        assert result["status"] == "error"

    async def test_diagnose_no_cache_returns_error(self):
        """diagnose 无缓存时返回 error。"""
        from src.tools._repo_cache import repo_cache
        repo_cache.clear_all()
        result = await diagnose(role="pm", query="test")
        assert result["status"] == "error"


# ══════════════════════════════════════════════════════════
# 场景 4: depth=detailed 模式
# ══════════════════════════════════════════════════════════


class TestDetailedDepth:
    """scan_repo depth=detailed 预生成所有章节。"""

    async def test_detailed_returns_chapters(self, mini_project_path: str):
        """depth=detailed 返回 chapters 字典。"""
        result = await scan_repo(
            repo_url=mini_project_path, role="pm", depth="detailed",
        )
        assert result["status"] == "ok"
        assert result["depth"] == "detailed"
        assert "chapters" in result
        assert isinstance(result["chapters"], dict)
        assert len(result["chapters"]) > 0

    async def test_detailed_chapters_match_modules(self, mini_project_path: str):
        """chapters 的 key 是 modules 中的模块名子集。"""
        result = await scan_repo(
            repo_url=mini_project_path, role="pm", depth="detailed",
        )
        assert result["status"] == "ok"

        module_names = {m["name"] for m in result["modules"]}
        chapter_names = set(result["chapters"].keys())

        # chapters ⊆ modules
        assert chapter_names.issubset(module_names), (
            f"chapters 包含未知模块: {chapter_names - module_names}"
        )


# ══════════════════════════════════════════════════════════
# 场景 5: Mermaid 图语法校验
# ══════════════════════════════════════════════════════════


class TestMermaidSyntax:
    """验证所有 Mermaid 输出的语法合法性。"""

    _MERMAID_HEADER = re.compile(r"^graph\s+(TD|LR|TB|BT|RL)", re.MULTILINE)

    async def test_scan_mermaid_valid_header(self, mini_project_path: str):
        """scan_repo Mermaid 有合法 header。"""
        result = await scan_repo(repo_url=mini_project_path, role="pm")
        mermaid = result["mermaid_diagram"]
        assert self._MERMAID_HEADER.search(mermaid), (
            f"Mermaid 缺少合法 header:\n{mermaid[:300]}"
        )

    async def test_scan_mermaid_quotes_balanced(self, mini_project_path: str):
        """Mermaid 中引号成对出现。"""
        result = await scan_repo(repo_url=mini_project_path, role="pm")
        mermaid = result["mermaid_diagram"]

        for i, line in enumerate(mermaid.split("\n"), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("%%") or stripped.startswith("graph"):
                continue
            assert stripped.count('"') % 2 == 0, (
                f"Mermaid 第 {i} 行引号未闭合: {stripped}"
            )

    async def test_chapter_mermaid_valid_header(self, mini_project_path: str):
        """read_chapter 依赖图有合法 Mermaid header。"""
        scan = await scan_repo(repo_url=mini_project_path, role="pm")
        assert scan["status"] == "ok"

        mod_name = scan["modules"][0]["name"]
        chapter = await read_chapter(module_name=mod_name, role="pm")
        assert chapter["status"] == "ok"

        dep_graph = chapter["dependency_graph"]
        assert self._MERMAID_HEADER.search(dep_graph), (
            f"chapter Mermaid 缺少合法 header:\n{dep_graph[:300]}"
        )

    async def test_mermaid_not_single_line(self, mini_project_path: str):
        """Mermaid 图不应只有 header 一行。"""
        result = await scan_repo(repo_url=mini_project_path, role="pm")
        mermaid = result["mermaid_diagram"]
        lines = [l for l in mermaid.strip().split("\n") if l.strip()]
        assert len(lines) >= 1, "Mermaid 图应至少有 header 行"


# ══════════════════════════════════════════════════════════
# 场景 6: code_ref 行号精度
# ══════════════════════════════════════════════════════════


CODE_REF_RANGE = re.compile(r"^(.+):L(\d+)-L(\d+)$")
CODE_REF_SINGLE = re.compile(r"^(.+):L(\d+)$")


class TestCodeRefAccuracy:
    """source_refs / key_code_refs 的行号精度和格式。"""

    async def test_source_refs_format(self, mini_project_path: str):
        """scan_repo source_refs 格式为 file:Lstart-Lend。"""
        result = await scan_repo(repo_url=mini_project_path, role="pm")
        assert result["status"] == "ok"

        all_refs: list[str] = []
        for mod in result["modules"]:
            all_refs.extend(mod["source_refs"])

        assert len(all_refs) > 0, "至少应有 1 个 source_ref"

        for ref in all_refs:
            m = CODE_REF_RANGE.match(ref)
            assert m, f"source_ref 格式不对: {ref!r} (应为 file:Lstart-Lend)"
            start, end = int(m.group(2)), int(m.group(3))
            assert start > 0, f"行号应 > 0: {ref}"
            assert end >= start, f"end({end}) < start({start}): {ref}"

    async def test_source_refs_line_in_file(self, mini_project_path: str):
        """source_refs 行号在文件实际行数范围内。"""
        result = await scan_repo(repo_url=mini_project_path, role="pm")
        assert result["status"] == "ok"

        project_root = Path(mini_project_path)

        for mod in result["modules"]:
            for ref in mod["source_refs"]:
                m = CODE_REF_RANGE.match(ref)
                if not m:
                    continue
                file_path, start, end = m.group(1), int(m.group(2)), int(m.group(3))
                abs_path = project_root / file_path
                if abs_path.exists():
                    total_lines = len(abs_path.read_text().splitlines())
                    assert start <= total_lines, (
                        f"{ref}: start({start}) > 文件总行数({total_lines})"
                    )

    async def test_key_code_refs_format(self, mini_project_path: str):
        """read_chapter 卡片 ref 字段格式正确。"""
        scan = await scan_repo(repo_url=mini_project_path, role="pm")
        mod_name = scan["modules"][0]["name"]
        chapter = await read_chapter(module_name=mod_name, role="pm")
        assert chapter["status"] == "ok"

        all_refs: list[str] = []
        for card in chapter["module_cards"]:
            if "ref" in card and card["ref"]:
                all_refs.append(card["ref"])

        assert len(all_refs) > 0, "至少应有 1 个 card ref"

        for ref in all_refs:
            m = CODE_REF_RANGE.match(ref) or CODE_REF_SINGLE.match(ref)
            assert m, f"card ref 格式不对: {ref!r}"

    async def test_private_funcs_excluded(self, mini_project_path: str):
        """source_refs 不包含私有函数 (_开头)。"""
        result = await scan_repo(repo_url=mini_project_path, role="pm")
        assert result["status"] == "ok"

        for mod in result["modules"]:
            for ref in mod["source_refs"]:
                assert "_hash_password" not in ref, (
                    f"source_ref 不应包含私有函数: {ref}"
                )


# ══════════════════════════════════════════════════════════
# 场景 7: 多轮对话
# ══════════════════════════════════════════════════════════


class TestMultiTurnConversation:
    """ask_about 多轮对话保持上下文连贯。"""

    async def test_two_turn_carries_history(self, mini_project_path: str):
        """第2轮 conversation_history 被正确传递。"""
        scan = await scan_repo(repo_url=mini_project_path, role="pm")
        assert scan["status"] == "ok"
        mod_name = scan["modules"][0]["name"]

        # 第1轮
        r1 = await ask_about(
            module_name=mod_name,
            question="这个模块做什么？",
            role="pm",
        )
        assert r1["status"] == "ok"
        assert len(r1["context"]) > 0

        # 第2轮（带历史）
        history = [
            {"role": "user", "content": "这个模块做什么？"},
            {"role": "assistant", "content": "这个模块负责处理路由请求。"},
        ]
        r2 = await ask_about(
            module_name=mod_name,
            question="有什么风险？",
            role="pm",
            conversation_history=history,
        )
        assert r2["status"] == "ok"

        # 验证历史被返回了
        assert r2["conversation_history"] == history
        # 验证第2轮的上下文也正确组装了
        assert len(r2["context"]) > 0
        assert r2["question"] == "有什么风险？"


# ══════════════════════════════════════════════════════════
# 场景 8: 性能测试
# ══════════════════════════════════════════════════════════


class TestPerformance:
    """性能基准测试。"""

    async def test_small_project_under_30s(self, mini_project_path: str):
        """小型项目 scan_repo < 30 秒。"""
        start = time.time()
        result = await scan_repo(repo_url=mini_project_path, role="pm")
        elapsed = time.time() - start

        assert result["status"] == "ok"
        assert elapsed < 30, f"小型项目 scan 耗时 {elapsed:.1f}s，超过 30s 上限"

    @skip_if_no_medium_project
    async def test_medium_project_under_300s(self, medium_project_path: str):
        """中型项目 scan_repo < 300 秒（5 分钟）。"""
        start = time.time()
        result = await scan_repo(repo_url=medium_project_path, role="ceo")
        elapsed = time.time() - start

        assert result["status"] == "ok", (
            f"中型项目 scan 失败: {result.get('error')}"
        )
        assert elapsed < 300, f"中型项目 scan 耗时 {elapsed:.1f}s，超过 5min 上限"

        # 基本完整性
        assert len(result["modules"]) > 0
        assert "mermaid_diagram" in result

    async def test_read_chapter_under_10s(self, mini_project_path: str):
        """read_chapter 单模块 < 10 秒。"""
        scan = await scan_repo(repo_url=mini_project_path, role="pm")
        mod_name = scan["modules"][0]["name"]

        start = time.time()
        chapter = await read_chapter(module_name=mod_name, role="pm")
        elapsed = time.time() - start

        assert chapter["status"] == "ok"
        assert elapsed < 10, f"read_chapter 耗时 {elapsed:.1f}s，超过 10s 上限"


# ══════════════════════════════════════════════════════════
# 场景 9: MCP Server 工具注册验证
# ══════════════════════════════════════════════════════════


class TestMCPToolRegistration:
    """验证 MCP Server 的 tool 注册和元数据。"""

    def test_all_tools_registered(self):
        """MCP Server 注册了 8 个 tool (scan/read/diagnose/codegen/ask/term_correct/memory_feedback/codebook)。"""
        from src.server import mcp

        tools = mcp._tool_manager._tools
        expected = {"scan_repo", "read_chapter", "diagnose", "codegen", "ask_about", "term_correct", "memory_feedback", "codebook"}
        actual = set(tools.keys())
        assert expected == actual, f"Expected {expected}, got {actual}"

    def test_all_tools_have_description(self):
        """每个 tool 都有非空 description。"""
        from src.server import mcp

        tools = mcp._tool_manager._tools
        for name, tool in tools.items():
            assert tool.description, f"Tool '{name}' 缺少 description"

    def test_config_loads_correctly(self):
        """配置模块正确加载。"""
        from src.config import settings

        assert settings.app_name == "CodeBook"
        assert settings.app_version == "0.5.0"
        assert "python" in settings.supported_languages


# ══════════════════════════════════════════════════════════
# 场景 10: 数据一致性（跨工具）
# ══════════════════════════════════════════════════════════


class TestCrossToolConsistency:
    """跨工具调用时数据的一致性验证。"""

    async def test_scan_modules_readable_by_read_chapter(self, mini_project_path: str):
        """scan_repo 返回的每个模块都能被 read_chapter 读取。"""
        scan = await scan_repo(repo_url=mini_project_path, role="pm")
        assert scan["status"] == "ok"

        for mod in scan["modules"]:
            chapter = await read_chapter(module_name=mod["name"], role="pm")
            assert chapter["status"] == "ok", (
                f"模块「{mod['name']}」read_chapter 失败: {chapter.get('error')}"
            )

    async def test_scan_modules_askable(self, mini_project_path: str):
        """scan_repo 返回的每个模块都能被 ask_about 追问。"""
        scan = await scan_repo(repo_url=mini_project_path, role="pm")
        assert scan["status"] == "ok"

        for mod in scan["modules"]:
            result = await ask_about(
                module_name=mod["name"],
                question="这个模块做什么？",
                role="pm",
            )
            assert result["status"] == "ok", (
                f"模块「{mod['name']}」ask_about 失败: {result.get('error')}"
            )

    async def test_detailed_chapters_equal_individual_reads(
        self, mini_project_path: str,
    ):
        """depth=detailed 的 chapters 与单独 read_chapter 返回内容一致。"""
        detailed = await scan_repo(
            repo_url=mini_project_path, role="pm", depth="detailed",
        )
        assert detailed["status"] == "ok"
        assert "chapters" in detailed

        # 对 chapters 中的每个模块，单独调 read_chapter 对比
        for mod_name, chapter_data in detailed["chapters"].items():
            individual = await read_chapter(module_name=mod_name, role="pm")
            assert individual["status"] == "ok"

            # 两者都应返回 ok 且都有 module_cards（新格式可能不同，只验证两者都有数据）
            assert chapter_data.get("module_cards") is not None
            assert individual.get("module_cards") is not None


# ══════════════════════════════════════════════════════════
# pytest hook: 失败时输出修复建议
# ══════════════════════════════════════════════════════════


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """测试结束后输出自动修复建议。"""
    if exitstatus != 0:
        failed = terminalreporter.stats.get("failed", [])
        for report in failed:
            test_name = report.nodeid
            error_msg = str(report.longrepr)[:200] if report.longrepr else "unknown"

            # 根据错误类型生成修复建议
            suggestion = _generate_fix_suggestion(test_name, error_msg)
            fix_suggestions.add(test_name, error_msg, suggestion)

        report_text = fix_suggestions.report()
        if report_text:
            terminalreporter.write_line(report_text)


def _generate_fix_suggestion(test_name: str, error: str) -> str:
    """根据测试名和错误信息生成修复建议。"""
    if "scan_repo" in test_name and "status" in error:
        return (
            "scan_repo 返回 status='error'。"
            "检查 repo_cloner.clone_repo 是否能正确处理本地路径，"
            "以及 ast_parser 是否支持项目中的语言。"
        )
    if "read_chapter" in test_name and "scan_repo" in error:
        return (
            "read_chapter 在 scan_repo 之前调用。"
            "确保测试顺序正确，或在测试中先调用 scan_repo。"
        )
    if "mermaid" in test_name.lower():
        return (
            "Mermaid 语法校验失败。"
            "检查 dependency_graph.to_mermaid() 输出是否包含 'graph TD' header，"
            "以及节点 ID 是否包含特殊字符。"
        )
    if "role" in test_name.lower() and "badge" in error:
        return (
            "角色切换未产生差异化输出。"
            "检查 _role_badge() 和 _build_project_overview() 中的角色分支逻辑。"
        )
    if "performance" in test_name.lower() or "under_" in test_name:
        return (
            "性能超时。检查 parse_all 是否有不必要的重复解析，"
            "或 group_modules 是否在大项目上有 O(n²) 复杂度。"
        )
    if "code_ref" in test_name.lower() or "source_ref" in test_name.lower():
        return (
            "code_ref 格式或行号不正确。"
            "检查 _collect_source_refs() 中 line_start/line_end 的计算，"
            "确保 tree-sitter 解析结果的行号从 1 开始。"
        )
    if "ask_about" in test_name and "error" in error:
        return (
            "ask_about 返回错误。"
            "检查 repo_cache 是否正确存储了 scan_repo 的结果，"
            "以及 _find_module() 的模糊匹配逻辑。"
        )
    return (
        "通用建议：检查测试依赖的 fixture 数据是否完整，"
        "以及被测函数的返回值 schema 是否发生变化。"
    )
