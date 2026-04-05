"""测试 summarize_for_blueprint 和 save_blueprint_summary MCP 工具。"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── 工具注册 ─────────────────────────────────────────────


def test_summarize_tool_registered():
    """确认 summarize_for_blueprint 已注册到 MCP Server。"""
    from src.server import mcp

    tools = mcp._tool_manager._tools
    assert "summarize_for_blueprint" in tools


def test_save_summary_tool_registered():
    """确认 save_blueprint_summary 已注册到 MCP Server。"""
    from src.server import mcp

    tools = mcp._tool_manager._tools
    assert "save_blueprint_summary" in tools


# ── summarize_for_blueprint ──────────────────────────────


async def test_summarize_returns_context_when_cached():
    """repo_cache 有缓存时，返回 status=context_ready。"""
    mock_ctx = MagicMock()
    mock_ctx.modules = []
    mock_ctx.parse_results = []
    mock_ctx.dep_graph = MagicMock()
    mock_ctx.dep_graph.get_module_graph.return_value = MagicMock(
        edges=MagicMock(return_value=[]),
        has_node=MagicMock(return_value=False),
    )
    mock_ctx.repo_url = "https://github.com/test/repo"
    mock_ctx.clone_result = MagicMock()
    mock_ctx.clone_result.repo_path = "/tmp/test-repo"
    mock_ctx.role = "pm"

    with patch("src.tools.summarize_for_blueprint.repo_cache") as mock_cache:
        mock_cache.get.return_value = mock_ctx

        from src.tools.summarize_for_blueprint import summarize_for_blueprint

        result = await summarize_for_blueprint(repo_url="https://github.com/test/repo")

    assert result["status"] == "context_ready"
    assert "prompt" in result
    assert "modules" in result
    assert "connections" in result
    assert "fallback_summary" in result
    assert "guidance" in result


async def test_summarize_returns_error_when_not_scanned():
    """repo_cache 无缓存时，返回 status=error。"""
    with patch("src.tools.summarize_for_blueprint.repo_cache") as mock_cache:
        mock_cache.get.return_value = None

        from src.tools.summarize_for_blueprint import summarize_for_blueprint

        result = await summarize_for_blueprint(repo_url="https://github.com/test/repo")

    assert result["status"] == "error"
    assert "scan_repo" in result["message"]


# ── save_blueprint_summary ───────────────────────────────


async def test_save_saves_valid_summary():
    """传入合法 summary_json，返回 status=ok。"""
    mock_ctx = MagicMock()
    mock_ctx.modules = []
    mock_ctx.parse_results = []
    mock_ctx.dep_graph = MagicMock()
    mock_ctx.dep_graph.get_module_graph.return_value = MagicMock(
        edges=MagicMock(return_value=[]),
        has_node=MagicMock(return_value=False),
    )
    mock_ctx.repo_url = "https://github.com/test/repo"
    mock_ctx.clone_result = MagicMock()
    mock_ctx.clone_result.repo_path = "/tmp/test-repo"
    mock_ctx.role = "pm"

    valid_json = {
        "project_name": "TestProject",
        "project_description": "A test project",
        "modules": [],
        "connections": [],
    }

    with (
        patch("src.tools.save_blueprint_summary.repo_cache") as mock_cache,
        patch("src.tools.save_blueprint_summary._save_to_memory") as mock_save,
    ):
        mock_cache.get.return_value = mock_ctx

        from src.tools.save_blueprint_summary import save_blueprint_summary

        result = await save_blueprint_summary(
            repo_url="https://github.com/test/repo",
            summary_json=valid_json,
        )

    assert result["status"] == "ok"
    assert "summary" in result
    mock_save.assert_called_once()


async def test_save_falls_back_on_invalid_json():
    """传入无效 JSON，不崩溃且返回 status=ok（降级）。"""
    mock_ctx = MagicMock()
    mock_ctx.modules = []
    mock_ctx.parse_results = []
    mock_ctx.dep_graph = MagicMock()
    mock_ctx.dep_graph.get_module_graph.return_value = MagicMock(
        edges=MagicMock(return_value=[]),
        has_node=MagicMock(return_value=False),
    )
    mock_ctx.repo_url = "https://github.com/test/repo"
    mock_ctx.clone_result = MagicMock()
    mock_ctx.clone_result.repo_path = "/tmp/test-repo"
    mock_ctx.role = "pm"

    with (
        patch("src.tools.save_blueprint_summary.repo_cache") as mock_cache,
        patch("src.tools.save_blueprint_summary._save_to_memory") as mock_save,
    ):
        mock_cache.get.return_value = mock_ctx

        from src.tools.save_blueprint_summary import save_blueprint_summary

        result = await save_blueprint_summary(
            repo_url="https://github.com/test/repo",
            summary_json={"bad": "data"},
        )

    assert result["status"] == "ok"
    assert "summary" in result
