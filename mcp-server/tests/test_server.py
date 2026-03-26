"""测试 CodeBook MCP Server — 验证 4 个 tool 注册成功且可调用。"""

import os
import pytest

from src.tools.ask_about import ask_about
from src.tools.diagnose import diagnose
from src.tools.read_chapter import read_chapter
from src.tools.scan_repo import scan_repo

CONDUIT_PATH = "/tmp/conduit"
CONDUIT_EXISTS = os.path.isdir(CONDUIT_PATH)

skip_if_no_conduit = pytest.mark.skipif(
    not CONDUIT_EXISTS, reason="Conduit not found at /tmp/conduit",
)


# ── scan_repo ─────────────────────────────────────────────


@skip_if_no_conduit
async def test_scan_repo_full_pipeline():
    """scan_repo 完整流程：扫描本地目录，返回蓝图。"""
    result = await scan_repo(repo_url=CONDUIT_PATH, role="pm", depth="overview")
    assert result["status"] == "ok"
    assert result["repo_url"] == CONDUIT_PATH
    assert result["role"] == "pm"
    assert result["depth"] == "overview"
    assert len(result["project_overview"]) > 0
    assert len(result["modules"]) > 0
    assert "mermaid_diagram" in result
    assert "graph TD" in result["mermaid_diagram"]
    assert result["stats"]["files"] > 0
    assert result["stats"]["modules"] > 0
    assert result["stats"]["functions"] > 0
    assert result["stats"]["scan_time_seconds"] >= 0


@skip_if_no_conduit
async def test_scan_repo_accepts_all_roles():
    """scan_repo 接受所有 4 种角色。"""
    for role in ("ceo", "pm", "investor", "qa"):
        result = await scan_repo(repo_url=CONDUIT_PATH, role=role)
        assert result["status"] == "ok"
        assert result["role"] == role


@skip_if_no_conduit
async def test_scan_repo_detailed_depth():
    """depth=detailed 时预生成所有模块卡片。"""
    result = await scan_repo(repo_url=CONDUIT_PATH, role="pm", depth="detailed")
    assert result["status"] == "ok"
    assert result["depth"] == "detailed"
    assert "chapters" in result
    assert len(result["chapters"]) > 0


async def test_scan_repo_clone_error():
    """scan_repo 处理克隆失败。"""
    result = await scan_repo(repo_url="https://github.com/nonexistent/repo123456789")
    assert result["status"] == "error"
    assert "error" in result


@skip_if_no_conduit
async def test_scan_repo_module_fields():
    """每个模块包含必要字段。"""
    result = await scan_repo(repo_url=CONDUIT_PATH, role="pm")
    for mod in result["modules"]:
        assert "name" in mod
        assert "node_title" in mod
        assert "health" in mod
        assert "role_badge" in mod
        assert "source_refs" in mod


@skip_if_no_conduit
async def test_scan_repo_connections():
    """connections 列表格式正确。"""
    result = await scan_repo(repo_url=CONDUIT_PATH)
    for conn in result["connections"]:
        assert "from" in conn
        assert "to" in conn
        assert "strength" in conn
        assert conn["strength"] in ("strong", "weak")


# ── read_chapter ──────────────────────────────────────────


@skip_if_no_conduit
async def test_read_chapter_after_scan():
    """先 scan 再 read_chapter 成功。"""
    await scan_repo(repo_url=CONDUIT_PATH)
    result = await read_chapter(module_name="app", role="pm")
    assert result["status"] == "ok"
    assert len(result["module_cards"]) > 0
    assert "dependency_graph" in result


async def test_read_chapter_without_scan():
    """未 scan 时 read_chapter 返回错误。"""
    from src.tools._repo_cache import repo_cache
    repo_cache.clear_all()
    result = await read_chapter(module_name="用户认证")
    assert result["status"] == "error"
    assert "scan_repo" in result["error"]


@skip_if_no_conduit
async def test_read_chapter_module_not_found():
    """read_chapter 查询不存在的模块。"""
    await scan_repo(repo_url=CONDUIT_PATH)
    result = await read_chapter(module_name="不存在的模块xyz")
    assert result["status"] == "error"
    assert "available_modules" in result


@skip_if_no_conduit
async def test_read_chapter_card_schema():
    """模块卡片包含完整 schema 字段。"""
    await scan_repo(repo_url=CONDUIT_PATH)
    result = await read_chapter(module_name="app")
    assert result["status"] == "ok"
    if result["module_cards"]:
        card = result["module_cards"][0]
        for field in ["name", "path", "summary", "functions", "classes",
                       "calls", "imports", "ref"]:
            assert field in card, f"卡片缺少字段: {field}"


# ── diagnose ──────────────────────────────────────────────


async def test_diagnose_returns_error_without_cache():
    """diagnose 无缓存时返回 error。"""
    from src.tools._repo_cache import repo_cache
    repo_cache.clear_all()
    result = await diagnose(module_name="all", role="pm", query="注册时邮箱重复报错不友好")
    assert result["status"] == "error"
    assert "scan_repo" in result["error"]


async def test_diagnose_empty_query_returns_error():
    """diagnose 空 query 返回关键词错误。"""
    from src.tools._repo_cache import repo_cache
    repo_cache.clear_all()
    result = await diagnose(role="pm")
    assert result["status"] == "error"


# ── ask_about ─────────────────────────────────────────────


async def test_ask_about_returns_placeholder():
    """ask_about 未扫描时返回 error 状态。"""
    from src.tools._repo_cache import repo_cache
    repo_cache.clear_all()
    result = await ask_about(
        module_name="用户认证",
        question="这个模块最大的风险是什么？",
        role="pm",
    )
    assert result["status"] == "error"
    assert "scan_repo" in result["error"]
    assert "answer" in result


# ── MCP Server tool 注册 ──────────────────────────────────


def test_mcp_server_has_five_tools():
    """MCP Server 注册了 8 个 tool。"""
    from src.server import mcp

    tools = mcp._tool_manager._tools
    tool_names = set(tools.keys())
    expected = {"scan_repo", "read_chapter", "diagnose", "ask_about", "codegen", "term_correct", "memory_feedback", "codebook"}
    assert expected == tool_names, f"Expected {expected}, got {tool_names}"


def test_mcp_server_tool_descriptions():
    """每个 tool 都有非空的 description。"""
    from src.server import mcp

    tools = mcp._tool_manager._tools
    for name, tool in tools.items():
        assert tool.description, f"Tool '{name}' has no description"


def test_config_loads():
    """配置模块可以正常加载。"""
    from src.config import settings

    assert settings.app_name == "CodeBook"
    assert settings.app_version == "0.1.0"
    assert "python" in settings.supported_languages
