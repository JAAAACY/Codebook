"""_repo_cache — 在 scan_repo 和其他工具之间共享解析上下文。

支持两层缓存：
1. 内存缓存（快，进程内共享）
2. 磁盘缓存（慢，重启后恢复）

磁盘缓存现在通过 ProjectMemory 系统管理，存储在 ~/.codebook/memory/{repo_hash}/
下。RepoCache 作为兼容层，公开 API 保持不变，内部委托给 ProjectMemory。
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import asdict
from typing import TYPE_CHECKING

import structlog

from src.config import settings
from src.memory.migration import migrate_on_startup
from src.memory.project_memory import ProjectMemory

if TYPE_CHECKING:
    from src.summarizer.engine import SummaryContext

logger = structlog.get_logger()


class _ExpiredSentinel:
    """标记缓存已过期（区别于"从未扫描"的 None）。"""

    def __init__(self, repo_url: str):
        self.repo_url = repo_url


# ── 核心缓存类 ─────────────────────────────────────────


class RepoCache:
    """两层缓存：内存 + 磁盘（通过 ProjectMemory）。

    store() 同时写内存和磁盘（委托给 ProjectMemory）。
    get() 先查内存，miss 则尝试从磁盘恢复（委托给 ProjectMemory）。

    公开 API 保持不变以确保向后兼容。
    """

    def __init__(self):
        self._cache: dict[str, "SummaryContext"] = {}
        self._latest_key: str | None = None
        self._project_memories: dict[str, ProjectMemory] = {}
        self._migration_done: bool = False

    def _ensure_migration(self) -> None:
        """执行迁移检查（仅一次）。"""
        if self._migration_done:
            return
        migrate_on_startup()
        self._migration_done = True
        logger.debug("repo_cache.migration_completed")

    def store(self, repo_url: str, ctx: "SummaryContext") -> None:
        """缓存一个仓库的解析上下文（内存 + ProjectMemory）。

        内部委托给 ProjectMemory.store_context()。
        """
        logger.debug("repo_cache.storing_context", repo_url=repo_url)

        # 内存缓存
        self._cache[repo_url] = ctx
        self._latest_key = repo_url

        # 委托给 ProjectMemory 处理磁盘存储
        try:
            pm = self._get_project_memory(repo_url)
            serialized = self._serialize_summary_context(ctx)
            success = pm.store_context(serialized)

            if success:
                logger.info(
                    "repo_cache.context_stored",
                    repo_url=repo_url,
                    repo_hash=pm.repo_hash,
                )
            else:
                logger.warning(
                    "repo_cache.context_storage_failed",
                    repo_url=repo_url,
                    hint="Memory cache retained; disk storage failed",
                )
        except Exception as e:
            logger.warning(
                "repo_cache.delegation_failed",
                repo_url=repo_url,
                error=str(e),
                hint="Continuing with memory-only cache",
            )

    def get(self, repo_url: str | None = None) -> "SummaryContext | None":
        """获取缓存的上下文。

        查找顺序：内存 → ProjectMemory 磁盘。repo_url=None 时返回最近一次。
        内部委托给 ProjectMemory.get_context()。
        """
        # 1. 内存命中
        if repo_url and repo_url in self._cache:
            logger.debug("repo_cache.hit_memory", repo_url=repo_url)
            return self._cache[repo_url]
        if not repo_url and self._latest_key:
            return self._cache.get(self._latest_key)

        # 2. ProjectMemory 磁盘恢复
        try:
            if not repo_url:
                logger.debug("repo_cache.get_latest_requested")
                return None

            logger.debug("repo_cache.fetching_from_project_memory", repo_url=repo_url)
            pm = self._get_project_memory(repo_url)
            stored_data = pm.get_context()

            if stored_data is None:
                logger.debug("repo_cache.not_found_in_project_memory", repo_url=repo_url)
                return None

            # 反序列化
            ctx = self._deserialize_summary_context(stored_data, repo_url)
            if ctx is not None:
                key = repo_url
                self._cache[key] = ctx
                self._latest_key = key
                logger.info(
                    "repo_cache.restored_from_project_memory",
                    repo_url=repo_url,
                    repo_hash=pm.repo_hash,
                )
                return ctx
            else:
                logger.warning(
                    "repo_cache.deserialization_failed",
                    repo_url=repo_url,
                )
                return None

        except Exception as e:
            logger.warning(
                "repo_cache.get_failed",
                repo_url=repo_url,
                error=str(e),
            )
            return None

    def has(self, repo_url: str) -> bool:
        """检查仓库是否已被缓存。"""
        if repo_url in self._cache:
            return True
        # 也检查 ProjectMemory
        try:
            pm = self._get_project_memory(repo_url)
            return pm.get_context() is not None
        except Exception:
            return False

    def clear(self) -> None:
        """仅清除内存缓存（不删磁盘文件）。"""
        logger.debug("repo_cache.clearing_memory_cache")
        self._cache.clear()
        self._latest_key = None

    def clear_all(self) -> None:
        """清除内存 + 磁盘缓存（通过 ProjectMemory）。"""
        logger.debug("repo_cache.clearing_all_caches")
        self._cache.clear()
        self._latest_key = None
        # 通过 ProjectMemory 清理磁盘（如果需要）
        # 当前实现：保留磁盘数据，仅清内存
        logger.info("repo_cache.cleared")

    def _get_project_memory(self, repo_url: str) -> ProjectMemory:
        """获取或创建指定 repo_url 的 ProjectMemory 实例。"""
        if repo_url not in self._project_memories:
            self._project_memories[repo_url] = ProjectMemory(repo_url)
        return self._project_memories[repo_url]

    def _serialize_summary_context(self, ctx: "SummaryContext") -> dict:
        """将 SummaryContext 序列化为 dict（兼容现有序列化逻辑）。"""
        from src.parsers.ast_parser import (
            ParseResult,
            FunctionInfo,
            ClassInfo,
            ImportInfo,
            CallInfo,
        )
        from src.parsers.module_grouper import ModuleGroup
        from src.parsers.repo_cloner import CloneResult, FileInfo

        def _pr_to_dict(pr: ParseResult) -> dict:
            return {
                "file_path": pr.file_path,
                "language": pr.language,
                "classes": [asdict(c) for c in pr.classes],
                "functions": [asdict(f) for f in pr.functions],
                "imports": [asdict(i) for i in pr.imports],
                "calls": [asdict(c) for c in pr.calls],
                "line_count": pr.line_count,
                "parse_errors": pr.parse_errors,
            }

        def _module_to_dict(m: ModuleGroup) -> dict:
            return asdict(m)

        def _clone_to_dict(cr: CloneResult) -> dict:
            return {
                "repo_path": cr.repo_path,
                "files": [asdict(f) for f in cr.files],
                "languages": cr.languages,
                "total_lines": cr.total_lines,
                "skipped_count": cr.skipped_count,
            }

        # 依赖图：存节点 + 边（NetworkX 不直接可序列化）
        graph_data = {
            "nodes": {},
            "edges": [],
            "module_map": {},
        }
        for nid, data in ctx.dep_graph.graph.nodes(data=True):
            graph_data["nodes"][nid] = dict(data)
        for u, v, data in ctx.dep_graph.graph.edges(data=True):
            graph_data["edges"].append({"from": u, "to": v, "data": dict(data)})
        graph_data["module_map"] = dict(ctx.dep_graph._module_map)

        now = time.time()
        return {
            "version": 1,
            "timestamp": now,
            "last_accessed": now,
            "role": ctx.role,
            "repo_url": ctx.repo_url,
            "clone_result": _clone_to_dict(ctx.clone_result),
            "parse_results": [_pr_to_dict(pr) for pr in ctx.parse_results],
            "modules": [_module_to_dict(m) for m in ctx.modules],
            "graph": graph_data,
        }

    def _deserialize_summary_context(
        self, data: dict, repo_url: str
    ) -> "SummaryContext | None":
        """从 dict 恢复 SummaryContext（兼容现有反序列化逻辑）。"""
        try:
            from src.parsers.ast_parser import (
                ParseResult,
                FunctionInfo,
                ClassInfo,
                ImportInfo,
                CallInfo,
            )
            from src.parsers.dependency_graph import DependencyGraph
            from src.parsers.module_grouper import ModuleGroup
            from src.parsers.repo_cloner import CloneResult, FileInfo
            from src.summarizer.engine import SummaryContext

            # CloneResult
            cr_data = data["clone_result"]
            clone_result = CloneResult(
                repo_path=cr_data["repo_path"],
                files=[FileInfo(**f) for f in cr_data["files"]],
                languages=cr_data["languages"],
                total_lines=cr_data["total_lines"],
                skipped_count=cr_data.get("skipped_count", 0),
            )

            # ParseResults
            parse_results = []
            for pr_data in data["parse_results"]:
                pr = ParseResult(
                    file_path=pr_data["file_path"],
                    language=pr_data["language"],
                    classes=[ClassInfo(**c) for c in pr_data["classes"]],
                    functions=[FunctionInfo(**f) for f in pr_data["functions"]],
                    imports=[ImportInfo(**i) for i in pr_data["imports"]],
                    calls=[CallInfo(**c) for c in pr_data["calls"]],
                    line_count=pr_data["line_count"],
                    parse_errors=pr_data.get("parse_errors", []),
                )
                parse_results.append(pr)

            # Modules
            modules = [ModuleGroup(**m) for m in data["modules"]]

            # DependencyGraph — 从存储的节点和边重建
            dep_graph = DependencyGraph()
            graph_data = data["graph"]
            for nid, attrs in graph_data["nodes"].items():
                dep_graph.graph.add_node(nid, **attrs)
            for edge in graph_data["edges"]:
                dep_graph.graph.add_edge(edge["from"], edge["to"], **edge["data"])
            if graph_data.get("module_map"):
                dep_graph.set_module_groups(graph_data["module_map"])

            return SummaryContext(
                clone_result=clone_result,
                parse_results=parse_results,
                modules=modules,
                dep_graph=dep_graph,
                role=data.get("role", "pm"),
                repo_url=data.get("repo_url"),
            )

        except Exception as e:
            logger.warning(
                "repo_cache.deserialization_error",
                repo_url=repo_url,
                error=str(e),
            )
            return None



# 全局单例
repo_cache = RepoCache()
