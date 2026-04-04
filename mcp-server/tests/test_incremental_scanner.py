"""incremental_scanner 单元测试。"""

import pytest
from unittest.mock import AsyncMock, patch
from dataclasses import replace

from src.watcher.file_hasher import FileChanges
from src.watcher.incremental_scanner import incremental_rescan, merge_context
from src.parsers.ast_parser import ParseResult, FunctionInfo, ImportInfo, CallInfo
from src.parsers.repo_cloner import FileInfo, CloneResult
from src.parsers.dependency_graph import DependencyGraph
from src.parsers.module_grouper import ModuleGroup
from src.summarizer.engine import SummaryContext


# ── Fixtures ──────────────────────────────────────────────

def _make_parse_result(file_path: str, func_name: str = "main") -> ParseResult:
    return ParseResult(
        file_path=file_path,
        language="python",
        functions=[
            FunctionInfo(name=func_name, line_start=1, line_end=10, is_method=False, parent_class=None),
        ],
        classes=[],
        imports=[],
        calls=[],
        line_count=10,
    )


def _make_context(files: list[str]) -> SummaryContext:
    """构造一个最小的 SummaryContext 用于测试。"""
    file_infos = [
        FileInfo(path=f, abs_path=f"/repo/{f}", language="python", size_bytes=100, line_count=10)
        for f in files
    ]
    parse_results = [_make_parse_result(f) for f in files]

    clone_result = CloneResult(
        repo_path="/repo",
        files=file_infos,
        languages={"python": len(files)},
        total_lines=10 * len(files),
    )

    modules = [ModuleGroup(name="src", dir_path="src", files=files, is_special=False)]

    dep_graph = DependencyGraph()
    dep_graph.build(parse_results)

    return SummaryContext(
        clone_result=clone_result,
        parse_results=parse_results,
        modules=modules,
        dep_graph=dep_graph,
        role="dev",
        repo_url="https://github.com/test/repo",
    )


# ── merge_context tests ──────────────────────────────────


class TestMergeContext:
    @pytest.mark.asyncio
    async def test_merge_replaces_modified_file(self):
        ctx = _make_context(["a.py", "b.py"])

        # 模拟 b.py 被修改，新增了一个函数
        new_b = _make_parse_result("b.py", func_name="updated_func")
        updated = await merge_context(ctx, [new_b], [])

        file_paths = [pr.file_path for pr in updated.parse_results]
        assert "a.py" in file_paths
        assert "b.py" in file_paths
        assert len(updated.parse_results) == 2

        # 确认 b.py 使用了新的解析结果
        b_result = next(pr for pr in updated.parse_results if pr.file_path == "b.py")
        assert b_result.functions[0].name == "updated_func"

    @pytest.mark.asyncio
    async def test_merge_removes_deleted_file(self):
        ctx = _make_context(["a.py", "b.py", "c.py"])

        updated = await merge_context(ctx, [], ["b.py"])

        file_paths = [pr.file_path for pr in updated.parse_results]
        assert "a.py" in file_paths
        assert "c.py" in file_paths
        assert "b.py" not in file_paths
        assert len(updated.parse_results) == 2

    @pytest.mark.asyncio
    async def test_merge_adds_new_file(self):
        ctx = _make_context(["a.py"])

        new_d = _make_parse_result("d.py", func_name="new_func")
        updated = await merge_context(ctx, [new_d], [])

        file_paths = [pr.file_path for pr in updated.parse_results]
        assert "a.py" in file_paths
        assert "d.py" in file_paths
        assert len(updated.parse_results) == 2

    @pytest.mark.asyncio
    async def test_merge_rebuilds_dep_graph(self):
        ctx = _make_context(["a.py", "b.py"])

        new_b = _make_parse_result("b.py", func_name="updated_func")
        updated = await merge_context(ctx, [new_b], [])

        # dep_graph 应该是新实例
        assert updated.dep_graph is not ctx.dep_graph
        assert updated.dep_graph.graph.number_of_nodes() >= 0

    @pytest.mark.asyncio
    async def test_merge_does_not_mutate_original(self):
        ctx = _make_context(["a.py", "b.py"])
        original_count = len(ctx.parse_results)

        await merge_context(ctx, [], ["b.py"])

        # 原始 context 不应被修改
        assert len(ctx.parse_results) == original_count

    @pytest.mark.asyncio
    async def test_merge_updates_clone_result_files(self):
        ctx = _make_context(["a.py", "b.py"])

        updated = await merge_context(ctx, [], ["b.py"])

        remaining_paths = [fi.path for fi in updated.clone_result.files]
        assert "a.py" in remaining_paths
        assert "b.py" not in remaining_paths


class TestFileChangesProperties:
    def test_total(self):
        fc = FileChanges(added=["a"], modified=["b", "c"], removed=["d"])
        assert fc.total == 4

    def test_is_empty(self):
        assert FileChanges().is_empty
        assert not FileChanges(added=["a"]).is_empty
