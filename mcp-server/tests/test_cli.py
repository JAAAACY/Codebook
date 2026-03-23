"""CLI 配置读写的 round-trip 测试。

验证 JSON / TOML / YAML 三种配置格式的写入→读回一致性。
"""

import os
import tempfile
from pathlib import Path

import pytest

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
