"""_repo_cache — 在 scan_repo 和其他工具之间共享解析上下文。

支持两层缓存：
1. 内存缓存（快，进程内共享）
2. 磁盘缓存（慢，重启后恢复）

磁盘缓存存储在 ~/.codebook_cache/contexts/ 下，用 repo_url 的 hash 做文件名。
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

if TYPE_CHECKING:
    from src.summarizer.engine import SummaryContext

logger = structlog.get_logger()

# 磁盘缓存过期时间（秒）：7 天（基于 last_accessed，活跃项目不会过期）
CACHE_TTL_SECONDS = 7 * 24 * 3600


class _ExpiredSentinel:
    """标记缓存已过期（区别于"从未扫描"的 None）。"""

    def __init__(self, repo_url: str):
        self.repo_url = repo_url

# ── 序列化 / 反序列化 ──────────────────────────────────


def _cache_dir() -> str:
    """返回磁盘缓存目录。"""
    d = os.path.join(settings.cache_dir, "contexts")
    os.makedirs(d, exist_ok=True)
    return d


def _url_to_filename(repo_url: str) -> str:
    """repo_url → 安全文件名。"""
    h = hashlib.sha256(repo_url.encode()).hexdigest()[:16]
    # 保留可读部分
    safe = repo_url.rstrip("/").split("/")[-1].replace(".git", "")
    return f"{safe}_{h}.json"


def _serialize_ctx(ctx: "SummaryContext") -> dict:
    """将 SummaryContext 转为可 JSON 序列化的 dict。"""
    from src.parsers.ast_parser import ParseResult, FunctionInfo, ClassInfo, ImportInfo, CallInfo
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
        "clone_result": _clone_to_dict(ctx.clone_result),
        "parse_results": [_pr_to_dict(pr) for pr in ctx.parse_results],
        "modules": [_module_to_dict(m) for m in ctx.modules],
        "graph": graph_data,
    }


def _deserialize_ctx(data: dict) -> "SummaryContext":
    """从 dict 恢复 SummaryContext。"""
    from src.parsers.ast_parser import ParseResult, FunctionInfo, ClassInfo, ImportInfo, CallInfo
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
    )


# ── 核心缓存类 ─────────────────────────────────────────


class RepoCache:
    """两层缓存：内存 + 磁盘。

    store() 同时写内存和磁盘。
    get() 先查内存，miss 则尝试从磁盘恢复。
    """

    def __init__(self):
        self._cache: dict[str, "SummaryContext"] = {}
        self._latest_key: str | None = None

    def store(self, repo_url: str, ctx: "SummaryContext"):
        """缓存一个仓库的解析上下文（内存 + 磁盘）。"""
        self._cache[repo_url] = ctx
        self._latest_key = repo_url
        self._save_to_disk(repo_url, ctx)

    def get(self, repo_url: str | None = None) -> "SummaryContext | None":
        """获取缓存的上下文。

        查找顺序：内存 → 磁盘。repo_url=None 时返回最近一次。
        """
        # 1. 内存命中
        if repo_url and repo_url in self._cache:
            return self._cache[repo_url]
        if not repo_url and self._latest_key:
            return self._cache.get(self._latest_key)

        # 2. 磁盘恢复
        result = self._load_from_disk(repo_url)
        if isinstance(result, _ExpiredSentinel):
            return result  # 调用方可识别过期 vs 从未扫描
        if result is not None:
            key = repo_url or "disk_restored"
            self._cache[key] = result
            self._latest_key = key
            return result

        return None

    def has(self, repo_url: str) -> bool:
        if repo_url in self._cache:
            return True
        # 也检查磁盘
        return self._disk_cache_exists(repo_url)

    def clear(self):
        """仅清除内存缓存（不删磁盘文件）。"""
        self._cache.clear()
        self._latest_key = None

    def clear_all(self):
        """清除内存 + 磁盘缓存。"""
        self._cache.clear()
        self._latest_key = None
        try:
            cache_d = _cache_dir()
            for f in os.listdir(cache_d):
                if f.endswith(".json"):
                    os.remove(os.path.join(cache_d, f))
        except OSError:
            pass

    # ── 磁盘操作 ─────────────────────────────────────

    def _save_to_disk(self, repo_url: str, ctx: "SummaryContext"):
        """序列化并写入磁盘。"""
        try:
            filepath = os.path.join(_cache_dir(), _url_to_filename(repo_url))
            serialized = _serialize_ctx(ctx)
            serialized["repo_url"] = repo_url

            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(serialized, f, ensure_ascii=False, default=str)

            logger.info("cache.saved_to_disk", path=filepath,
                        size_kb=round(os.path.getsize(filepath) / 1024))
        except Exception as e:
            logger.warning("cache.save_failed", error=str(e))

    def _load_from_disk(self, repo_url: str | None) -> "SummaryContext | None":
        """从磁盘恢复缓存。"""
        try:
            cache_d = _cache_dir()

            if repo_url:
                filepath = os.path.join(cache_d, _url_to_filename(repo_url))
                return self._read_cache_file(filepath)

            # repo_url=None → 找最近的缓存文件
            latest_file = None
            latest_mtime = 0.0
            for fname in os.listdir(cache_d):
                if not fname.endswith(".json"):
                    continue
                fpath = os.path.join(cache_d, fname)
                mtime = os.path.getmtime(fpath)
                if mtime > latest_mtime:
                    latest_mtime = mtime
                    latest_file = fpath

            if latest_file:
                return self._read_cache_file(latest_file)

        except Exception as e:
            logger.warning("cache.load_failed", error=str(e))

        return None

    def _read_cache_file(self, filepath: str) -> "SummaryContext | None":
        """读取并反序列化单个缓存文件。"""
        if not os.path.exists(filepath):
            return None

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 版本检查
            if data.get("version") != 1:
                logger.info("cache.version_mismatch", path=filepath)
                return None

            # 过期检查
            age = time.time() - data.get("last_accessed", data.get("timestamp", 0))
            if age > CACHE_TTL_SECONDS:
                repo_url = data.get("repo_url", "?")
                logger.info("cache.expired", path=filepath, age_hours=round(age / 3600))
                os.remove(filepath)
                return _ExpiredSentinel(repo_url)

            # 检查 repo 目录是否还存在
            repo_path = data.get("clone_result", {}).get("repo_path", "")
            if repo_path and not os.path.isdir(repo_path):
                logger.info("cache.repo_dir_missing", path=repo_path)
                # 目录不在了，缓存无效（代码片段读取会失败）
                # 但结构数据仍然有用，继续恢复
                pass

            ctx = _deserialize_ctx(data)
            logger.info("cache.restored_from_disk", filepath=filepath,
                        repo_url=data.get("repo_url", "?"))

            # Touch on read: 刷新 last_accessed，活跃项目不会过期
            self._touch_cache_file(filepath)

            return ctx

        except Exception as e:
            logger.warning("cache.read_failed", path=filepath, error=str(e))
            return None

    def _touch_cache_file(self, filepath: str):
        """更新 last_accessed 字段，延长活跃缓存的生命期。"""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["last_accessed"] = time.time()
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception as e:
            logger.warning("cache.touch_failed", path=filepath, error=str(e))

    def _disk_cache_exists(self, repo_url: str) -> bool:
        filepath = os.path.join(_cache_dir(), _url_to_filename(repo_url))
        return os.path.exists(filepath)


# 全局单例
repo_cache = RepoCache()
