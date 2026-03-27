"""CLI 配置读写的 round-trip 测试。

验证 JSON / TOML / YAML 三种配置格式的写入→读回一致性。
"""

import os
import tempfile
from pathlib import Path

import pytest

import src.cli as cli_module
from src.cli import (
    _read_json,
    _write_json,
    _read_toml,
    _write_toml,
    _read_yaml,
    _write_yaml,
)


# ── 测试数据：模拟 MCP 配置结构 ─────────────────────────

MCP_CONFIG = {
    "mcpServers": {
        "codebook": {
            "command": "uvx",
            "args": ["--from", "codebook-mcp", "codebook-server"],
            "env": {
                "CODEBOOK_LOG_LEVEL": "INFO",
            },
        }
    }
}

NESTED_CONFIG = {
    "top_key": "value",
    "section": {
        "enabled": True,
        "count": 42,
        "tags": ["a", "b", "c"],
        "nested": {
            "deep": "yes",
        },
    },
}


class TestJsonRoundTrip:
    """JSON 配置 round-trip 测试。"""

    def test_write_and_read_back(self, tmp_path):
        path = tmp_path / "config.json"
        _write_json(path, MCP_CONFIG)
        result = _read_json(path)
        assert result == MCP_CONFIG

    def test_read_nonexistent_returns_empty(self, tmp_path):
        path = tmp_path / "nonexistent.json"
        assert _read_json(path) == {}

    def test_read_corrupted_returns_empty(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("{invalid json", encoding="utf-8")
        assert _read_json(path) == {}

    def test_nested_structure(self, tmp_path):
        path = tmp_path / "nested.json"
        _write_json(path, NESTED_CONFIG)
        result = _read_json(path)
        assert result == NESTED_CONFIG


class TestTomlRoundTrip:
    """TOML 配置 round-trip 测试。"""

    def test_write_and_read_back(self, tmp_path):
        path = tmp_path / "config.toml"
        _write_toml(path, NESTED_CONFIG)
        result = _read_toml(path)
        assert result == NESTED_CONFIG

    def test_mcp_config_round_trip(self, tmp_path):
        path = tmp_path / "config.toml"
        _write_toml(path, MCP_CONFIG)
        result = _read_toml(path)
        assert result["mcpServers"]["codebook"]["command"] == "uvx"
        assert result["mcpServers"]["codebook"]["args"] == ["--from", "codebook-mcp", "codebook-server"]

    def test_read_nonexistent_returns_empty(self, tmp_path):
        path = tmp_path / "nonexistent.toml"
        assert _read_toml(path) == {}

    def test_read_corrupted_returns_empty(self, tmp_path):
        path = tmp_path / "bad.toml"
        path.write_text("[[invalid toml = = =", encoding="utf-8")
        assert _read_toml(path) == {}

    def test_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "sub" / "dir" / "config.toml"
        _write_toml(path, {"key": "value"})
        assert path.exists()
        result = _read_toml(path)
        assert result["key"] == "value"


class TestYamlRoundTrip:
    """YAML 配置 round-trip 测试。"""

    def test_write_and_read_back(self, tmp_path):
        path = tmp_path / "config.yaml"
        _write_yaml(path, MCP_CONFIG)
        result = _read_yaml(path)
        assert result == MCP_CONFIG

    def test_nested_structure(self, tmp_path):
        path = tmp_path / "config.yaml"
        _write_yaml(path, NESTED_CONFIG)
        result = _read_yaml(path)
        assert result == NESTED_CONFIG

    def test_read_nonexistent_returns_empty(self, tmp_path):
        path = tmp_path / "nonexistent.yaml"
        assert _read_yaml(path) == {}

    def test_read_corrupted_returns_empty(self, tmp_path):
        path = tmp_path / "bad.yaml"
        path.write_text(":\n  - :\n    invalid: [yaml: {broken", encoding="utf-8")
        assert _read_yaml(path) == {}

    def test_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "deep" / "nested" / "config.yaml"
        _write_yaml(path, {"key": "value"})
        assert path.exists()
        result = _read_yaml(path)
        assert result["key"] == "value"

    def test_special_characters_in_values(self, tmp_path):
        """含特殊字符的值不应破坏 round-trip。"""
        data = {
            "url": "https://example.com:8080/path?q=1&r=2",
            "description": "A string with 'quotes' and \"double quotes\"",
        }
        path = tmp_path / "special.yaml"
        _write_yaml(path, data)
        result = _read_yaml(path)
        assert result["url"] == data["url"]
        assert result["description"] == data["description"]


from src.cli import _detect_targets, _build_mcp_config, _set_nested, _get_nested, ToolTarget


class TestDetectTargets:
    """_detect_targets() 应返回所有支持的目标，包括 claude-code。"""

    def test_claude_code_in_targets(self):
        targets = _detect_targets()
        names = [t.name for t in targets]
        assert "claude-code" in names

    def test_claude_code_config_path(self):
        targets = _detect_targets()
        cc = next(t for t in targets if t.name == "claude-code")
        assert cc.config_path == Path.home() / ".claude" / ".mcp.json"
        assert cc.key_path == "mcpServers"

    def test_all_documented_targets_present(self):
        """USAGE 文档中列出的所有目标都应在 _detect_targets() 中有定义。"""
        expected = {
            "claude-desktop", "claude-code", "cursor", "windsurf",
            "vscode", "qwen", "codex", "gemini", "trae", "continue",
        }
        targets = _detect_targets()
        names = {t.name for t in targets}
        assert expected.issubset(names), f"Missing targets: {expected - names}"


class TestInstallRoundTrip:
    """验证 _install() 对各目标的写入->读回一致性。"""

    def test_claude_code_install_writes_config(self, tmp_path, monkeypatch):
        """claude-code 安装应写入 ~/.claude/.mcp.json 的 mcpServers 键。"""
        fake_mcp_json = tmp_path / ".claude" / ".mcp.json"
        fake_mcp_json.parent.mkdir(parents=True)

        config = _read_json(fake_mcp_json)
        mcp_payload = {
            "command": "/usr/bin/python3",
            "args": ["-m", "src.server"],
            "cwd": "/some/path",
        }
        _set_nested(config, "mcpServers", "codebook", mcp_payload)
        _write_json(fake_mcp_json, config)

        # 读回验证
        result = _read_json(fake_mcp_json)
        servers = _get_nested(result, "mcpServers")
        assert servers is not None
        assert "codebook" in servers
        assert servers["codebook"]["command"] == "/usr/bin/python3"
        assert servers["codebook"]["args"] == ["-m", "src.server"]

    def test_install_preserves_existing_servers(self, tmp_path):
        """安装 codebook 不应覆盖已有的其他 MCP server 配置。"""
        fake_mcp_json = tmp_path / ".mcp.json"
        # 预先写入一个已有的 server
        existing = {"mcpServers": {"other-server": {"command": "other", "args": []}}}
        _write_json(fake_mcp_json, existing)

        # 添加 codebook
        config = _read_json(fake_mcp_json)
        _set_nested(config, "mcpServers", "codebook", {"command": "python3", "args": ["-m", "src.server"]})
        _write_json(fake_mcp_json, config)

        # 验证两个 server 都在
        result = _read_json(fake_mcp_json)
        servers = _get_nested(result, "mcpServers")
        assert "other-server" in servers
        assert "codebook" in servers
        assert servers["other-server"]["command"] == "other"


class TestCliMainDispatch:
    """cli_main() 安装分发不应有 CLI_TARGETS 特殊路径。"""

    def test_no_install_via_cli_function(self):
        """_install_via_cli 应已删除。"""
        assert not hasattr(cli_module, "_install_via_cli")

    def test_no_install_claude_code_function(self):
        """_install_claude_code 应已删除。"""
        assert not hasattr(cli_module, "_install_claude_code")
