"""watch_daemon 单元测试。"""

import asyncio
import pytest

from src.watcher.watch_daemon import (
    WatchDaemon,
    WatchEvent,
    _should_watch,
    start_watching,
    stop_watching,
    get_all_status,
    get_watcher,
    _active_watchers,
)


class TestShouldWatch:
    def test_python_file(self):
        assert _should_watch("/repo/src/main.py")

    def test_typescript_file(self):
        assert _should_watch("/repo/src/index.ts")

    def test_config_file(self):
        assert _should_watch("/repo/config.json")

    def test_binary_file(self):
        assert not _should_watch("/repo/image.png")

    def test_excluded_dir(self):
        assert not _should_watch("/repo/node_modules/package/index.js")
        assert not _should_watch("/repo/__pycache__/module.cpython-312.pyc")
        assert not _should_watch("/repo/.git/objects/abc123")

    def test_venv_excluded(self):
        assert not _should_watch("/repo/venv/lib/site-packages/module.py")

    def test_unknown_extension(self):
        assert not _should_watch("/repo/readme.md")


class TestWatchDaemon:
    def test_init(self):
        d = WatchDaemon(repo_url="https://example.com/repo", repo_path="/tmp/repo")
        assert d.repo_url == "https://example.com/repo"
        assert d.repo_path == "/tmp/repo"
        assert d.debounce_ms == 500
        assert not d.is_running
        assert d.last_event is None

    @pytest.mark.asyncio
    async def test_stop_when_not_started(self):
        d = WatchDaemon(repo_url="test", repo_path="/tmp")
        msg = await d.stop()
        assert "停止" in msg

    @pytest.mark.asyncio
    async def test_start_without_watchfiles(self, monkeypatch):
        """如果 watchfiles 未安装，start 应返回安装提示。"""
        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "watchfiles":
                raise ImportError("No module named 'watchfiles'")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)
        d = WatchDaemon(repo_url="test", repo_path="/tmp")
        msg = await d.start()
        assert "watchfiles" in msg
        assert "pip install" in msg


class TestWatchEvent:
    def test_event_fields(self):
        ev = WatchEvent(
            repo_url="test",
            files_changed=3,
            modules_affected=["server", "db"],
            timestamp=1234567890.0,
            duration_ms=42,
        )
        assert ev.files_changed == 3
        assert ev.duration_ms == 42


class TestModuleAPI:
    @pytest.fixture(autouse=True)
    def clean_watchers(self):
        """每个测试后清理全局注册表。"""
        _active_watchers.clear()
        yield
        _active_watchers.clear()

    def test_get_watcher_nonexistent(self):
        assert get_watcher("nonexistent") is None

    def test_get_all_status_empty(self):
        assert get_all_status() == []

    @pytest.mark.asyncio
    async def test_stop_watching_nonexistent(self):
        msg = await stop_watching("nonexistent")
        assert "未找到" in msg

    @pytest.mark.asyncio
    async def test_start_creates_daemon(self):
        """start_watching 应创建并注册 daemon（即使 watchfiles 缺失也会注册）。"""
        msg = await start_watching("test_url", "/tmp/test_repo")
        assert "test_url" in _active_watchers
        # 清理
        await stop_watching("test_url")

    @pytest.mark.asyncio
    async def test_double_start_returns_existing(self):
        """重复 start 同一个 repo 不应创建新的 daemon。"""
        await start_watching("test_url", "/tmp/test_repo")
        msg = await start_watching("test_url", "/tmp/test_repo")
        # 可能返回 "已在监听" 或 watchfiles 缺失的提示
        assert "test_url" in _active_watchers
        await stop_watching("test_url")

    def test_status_with_active_watcher(self):
        d = WatchDaemon(repo_url="url1", repo_path="/path1")
        _active_watchers["url1"] = d
        status = get_all_status()
        assert len(status) == 1
        assert status[0]["repo_url"] == "url1"
        assert status[0]["is_running"] is False
