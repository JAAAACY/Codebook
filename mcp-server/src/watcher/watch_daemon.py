"""watch_daemon — 文件监听守护进程。

监控仓库目录的文件变更，自动触发增量扫描并更新缓存。
基于 watchfiles（Rust 后端，异步原生），带去抖和排除过滤。

watchfiles 是可选依赖。缺失时 start() 返回友好错误提示。
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

import structlog

from src.parsers.repo_cloner import EXCLUDED_DIRS, CODE_EXTENSIONS, CONFIG_EXTENSIONS
from src.watcher import file_hasher

logger = structlog.get_logger()

# 模块级注册表：repo_url → WatchDaemon
_active_watchers: dict[str, "WatchDaemon"] = {}

# 监控的文件扩展名
_WATCH_EXTENSIONS = CODE_EXTENSIONS | CONFIG_EXTENSIONS


def _should_watch(path: str) -> bool:
    """判断文件变更是否需要关注。"""
    # 排除目录
    parts = path.replace("\\", "/").split("/")
    for part in parts:
        if part in EXCLUDED_DIRS:
            return False
    # 只关注代码和配置文件
    for ext in _WATCH_EXTENSIONS:
        if path.endswith(ext):
            return True
    return False


@dataclass
class WatchEvent:
    """一次增量扫描事件的结果。"""
    repo_url: str
    files_changed: int
    modules_affected: list[str]
    timestamp: float
    duration_ms: int


@dataclass
class WatchDaemon:
    """异步文件监听守护进程。

    每个实例监控一个仓库目录。变更会触发增量扫描更新缓存。
    """
    repo_url: str
    repo_path: str
    debounce_ms: int = 500
    _task: asyncio.Task | None = field(default=None, init=False, repr=False)
    _running: bool = field(default=False, init=False)
    _last_event: WatchEvent | None = field(default=None, init=False)
    _event_count: int = field(default=0, init=False)

    @property
    def is_running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    @property
    def last_event(self) -> WatchEvent | None:
        return self._last_event

    async def start(self) -> str:
        """启动文件监听。

        Returns:
            状态消息。
        """
        try:
            import watchfiles
        except ImportError:
            return (
                "watchfiles 未安装。请运行: pip install watchfiles\n"
                "安装后重启 MCP Server 即可使用 watch 模式。"
            )

        if self.is_running:
            return f"已在监听 {self.repo_path}"

        self._running = True
        self._task = asyncio.create_task(self._watch_loop())
        logger.info(
            "watch_daemon.started",
            repo_url=self.repo_url,
            path=self.repo_path,
            debounce_ms=self.debounce_ms,
        )
        return f"开始监听 {self.repo_path}（去抖 {self.debounce_ms}ms）"

    async def stop(self) -> str:
        """停止文件监听。"""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("watch_daemon.stopped", repo_url=self.repo_url)
        return f"已停止监听 {self.repo_path}"

    async def _watch_loop(self):
        """核心监听循环。"""
        import watchfiles

        try:
            async for changes in watchfiles.awatch(
                self.repo_path,
                debounce=self.debounce_ms,
                step=100,
                watch_filter=lambda _, path: _should_watch(path),
            ):
                if not self._running:
                    break

                # 收集变更的文件路径
                changed_paths = {path for _, path in changes if _should_watch(path)}
                if not changed_paths:
                    continue

                logger.info(
                    "watch_daemon.changes_detected",
                    count=len(changed_paths),
                    repo_url=self.repo_url,
                )

                try:
                    await self._handle_changes(changed_paths)
                except Exception as e:
                    logger.error(
                        "watch_daemon.handle_error",
                        error=str(e),
                        repo_url=self.repo_url,
                    )

        except asyncio.CancelledError:
            logger.debug("watch_daemon.cancelled", repo_url=self.repo_url)
        except Exception as e:
            logger.error("watch_daemon.loop_error", error=str(e))
        finally:
            self._running = False

    async def _handle_changes(self, changed_paths: set[str]):
        """处理检测到的文件变更：重新计算 diff 并触发增量扫描。"""
        from src.tools._repo_cache import repo_cache

        start = time.time()
        rh = file_hasher._repo_hash_from_url(self.repo_url)

        # 加载旧快照
        ctx = repo_cache.get(self.repo_url)
        if ctx is None:
            logger.warning("watch_daemon.no_cache", repo_url=self.repo_url)
            return

        old_snapshot = file_hasher.load_snapshot(rh)
        if old_snapshot is None:
            logger.warning("watch_daemon.no_snapshot", repo_url=self.repo_url)
            return

        new_snapshot = file_hasher.snapshot(ctx.clone_result.files)
        changes = file_hasher.diff(old_snapshot, new_snapshot)

        if changes.is_empty:
            return

        updated = await repo_cache.update_incremental(self.repo_url, changes)
        if updated is not None:
            file_hasher.save_snapshot(rh, new_snapshot)

            duration_ms = int((time.time() - start) * 1000)
            self._event_count += 1
            self._last_event = WatchEvent(
                repo_url=self.repo_url,
                files_changed=changes.total,
                modules_affected=[],  # 可后续扩展
                timestamp=time.time(),
                duration_ms=duration_ms,
            )
            logger.info(
                "watch_daemon.incremental_done",
                changed=changes.total,
                duration_ms=duration_ms,
            )


# ── 模块级 API ───────────────────────────────────────────


def get_watcher(repo_url: str) -> WatchDaemon | None:
    """获取已注册的 watcher。"""
    return _active_watchers.get(repo_url)


async def start_watching(repo_url: str, repo_path: str, debounce_ms: int = 500) -> str:
    """启动或获取已有的 watcher。"""
    if repo_url in _active_watchers:
        w = _active_watchers[repo_url]
        if w.is_running:
            return f"已在监听 {repo_path}"

    daemon = WatchDaemon(repo_url=repo_url, repo_path=repo_path, debounce_ms=debounce_ms)
    _active_watchers[repo_url] = daemon
    return await daemon.start()


async def stop_watching(repo_url: str) -> str:
    """停止 watcher。"""
    daemon = _active_watchers.pop(repo_url, None)
    if daemon is None:
        return f"未找到 {repo_url} 的监听进程"
    return await daemon.stop()


def get_all_status() -> list[dict]:
    """返回所有活跃 watcher 的状态。"""
    result = []
    for url, daemon in _active_watchers.items():
        status: dict = {
            "repo_url": url,
            "repo_path": daemon.repo_path,
            "is_running": daemon.is_running,
            "event_count": daemon._event_count,
        }
        if daemon.last_event:
            status["last_event"] = {
                "files_changed": daemon.last_event.files_changed,
                "timestamp": daemon.last_event.timestamp,
                "duration_ms": daemon.last_event.duration_ms,
            }
        result.append(status)
    return result
