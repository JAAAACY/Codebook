"""incremental_scanner — 增量扫描与上下文合并。

仅重新解析发生变更的文件，然后将结果合并到已有的 SummaryContext 中。
DependencyGraph 每次从全量 ParseResult 重建，确保正确性。
"""

from __future__ import annotations

from dataclasses import replace

import structlog

from src.parsers.ast_parser import parse_all, ParseResult
from src.parsers.repo_cloner import FileInfo, _scan_files
from src.parsers.module_grouper import group_modules
from src.parsers.dependency_graph import DependencyGraph
from src.summarizer.engine import SummaryContext
from src.watcher.file_hasher import FileChanges

logger = structlog.get_logger()


async def incremental_rescan(
    repo_path: str,
    changes: FileChanges,
    existing_files: list[FileInfo],
) -> tuple[list[ParseResult], list[str]]:
    """仅重新解析变更的文件。

    Args:
        repo_path: 仓库本地路径。
        changes: 文件变更（added/modified/removed）。
        existing_files: 上次扫描的完整文件列表。

    Returns:
        (新解析结果列表, 需移除的文件路径列表)
    """
    changed_paths = set(changes.added + changes.modified)

    if not changed_paths and not changes.removed:
        return [], []

    # 重新扫描文件系统获取最新 FileInfo（仅变更文件）
    all_files, _ = _scan_files(repo_path)
    files_to_parse = [fi for fi in all_files if fi.path in changed_paths]

    new_results: list[ParseResult] = []
    if files_to_parse:
        new_results = await parse_all(files_to_parse)
        logger.info(
            "incremental_scanner.parsed",
            count=len(new_results),
            added=len(changes.added),
            modified=len(changes.modified),
        )

    return new_results, changes.removed


async def merge_context(
    existing_ctx: SummaryContext,
    new_results: list[ParseResult],
    removed_files: list[str],
) -> SummaryContext:
    """将增量解析结果合并到已有上下文，返回新的 SummaryContext。

    不修改 existing_ctx（immutable 模式）。

    Args:
        existing_ctx: 已有的 SummaryContext。
        new_results: 增量解析的 ParseResult 列表。
        removed_files: 已删除的文件路径列表。

    Returns:
        包含合并结果的新 SummaryContext。
    """
    # 收集需要替换的文件路径
    changed_files = {pr.file_path for pr in new_results}
    removed_set = set(removed_files)
    exclude_set = changed_files | removed_set

    # 保留未变更的旧结果 + 加入新结果
    merged_results = [
        pr for pr in existing_ctx.parse_results
        if pr.file_path not in exclude_set
    ] + list(new_results)

    # 更新 CloneResult.files（移除已删除的文件）
    updated_files = [
        fi for fi in existing_ctx.clone_result.files
        if fi.path not in removed_set
    ]
    updated_clone = replace(existing_ctx.clone_result, files=updated_files)

    # 重建模块分组
    modules = await group_modules(merged_results, existing_ctx.clone_result.repo_path)

    # 重建依赖图（全量重建确保正确性）
    dep_graph = DependencyGraph()
    dep_graph.build(merged_results)

    # 设置模块分组
    module_map: dict[str, str] = {}
    module_files: dict[str, set[str]] = {}
    for mod in modules:
        for f in mod.files:
            module_files.setdefault(mod.name, set()).add(f)
    for node_id, data in dep_graph.graph.nodes(data=True):
        node_file = data.get("file", "")
        for mod_name, files in module_files.items():
            if node_file in files:
                module_map[node_id] = mod_name
                break
    dep_graph.set_module_groups(module_map)

    logger.info(
        "incremental_scanner.merged",
        old_files=len(existing_ctx.parse_results),
        new_files=len(merged_results),
        removed=len(removed_files),
        added=len(new_results),
    )

    return SummaryContext(
        clone_result=updated_clone,
        parse_results=merged_results,
        modules=modules,
        dep_graph=dep_graph,
        role=existing_ctx.role,
        repo_url=existing_ctx.repo_url,
    )
