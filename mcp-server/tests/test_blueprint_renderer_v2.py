"""Tests for blueprint_renderer_v2 — SVG canvas renderer."""

from __future__ import annotations

import pytest


def _make_report_data() -> dict:
    return {
        "overview": {"stats": {"files": 10, "modules": 3}, "mermaid_diagram": ""},
        "module_cards": [
            {
                "name": "src/server",
                "call_chains": [
                    {"function": "handle", "callers": [], "callees": ["db/query"]}
                ],
            },
        ],
        "role": "pm",
        "blueprint_summary": {
            "project_name": "测试项目",
            "project_description": "一个用于测试的项目",
            "modules": [
                {
                    "code_path": "src/server",
                    "business_name": "服务端",
                    "description": "处理请求",
                    "health": "green",
                    "functions": [
                        {
                            "code_name": "handle",
                            "business_name": "处理请求",
                            "explanation": "接收并处理 HTTP 请求",
                            "file_path": "server.py",
                            "line_start": 10,
                            "params": ["request"],
                            "return_type": "Response",
                        }
                    ],
                    "depends_on": [],
                    "used_by": ["src/db"],
                },
                {
                    "code_path": "src/db",
                    "business_name": "数据库",
                    "description": "存储数据",
                    "health": "green",
                    "functions": [
                        {
                            "code_name": "query",
                            "business_name": "查询数据",
                            "explanation": "执行 SQL 查询",
                            "file_path": "db.py",
                            "line_start": 5,
                            "params": ["sql"],
                            "return_type": "list",
                        }
                    ],
                    "depends_on": ["src/server"],
                    "used_by": [],
                },
            ],
            "connections": [
                {
                    "from_module": "src/server",
                    "to_module": "src/db",
                    "verb": "读写数据",
                    "call_count": 5,
                }
            ],
        },
    }


@pytest.fixture()
def report_data() -> dict:
    return _make_report_data()


@pytest.fixture()
def rendered_html(report_data: dict) -> str:
    from src.tools.blueprint_renderer_v2 import render_blueprint_v2

    return render_blueprint_v2(report_data, repo_url="https://github.com/test/repo", total_time=1.5)


class TestBlueprintRendererV2:
    def test_returns_valid_html(self, rendered_html: str) -> None:
        assert rendered_html.startswith("<!DOCTYPE html>")
        assert "</html>" in rendered_html

    def test_contains_svg_canvas(self, rendered_html: str) -> None:
        assert "<svg" in rendered_html

    def test_embeds_blueprint_data(self, rendered_html: str) -> None:
        assert "__BLUEPRINT_DATA" in rendered_html
        assert "测试项目" in rendered_html

    def test_contains_module_nodes(self, rendered_html: str) -> None:
        assert "服务端" in rendered_html
        assert "数据库" in rendered_html

    def test_contains_connection_verbs(self, rendered_html: str) -> None:
        assert "读写数据" in rendered_html

    def test_contains_canvas_js(self, rendered_html: str) -> None:
        assert "wheel" in rendered_html or "onWheel" in rendered_html
        assert "dblclick" in rendered_html

    def test_contains_detail_view(self, rendered_html: str) -> None:
        assert "enterModule" in rendered_html or "showModuleDetail" in rendered_html

    def test_contains_breadcrumb(self, rendered_html: str) -> None:
        assert "Overview" in rendered_html

    def test_no_external_dependencies(self, rendered_html: str) -> None:
        assert "cdnjs.cloudflare.com" not in rendered_html
        assert "unpkg.com" not in rendered_html

    def test_empty_summary_fallback(self) -> None:
        from src.tools.blueprint_renderer_v2 import render_blueprint_v2

        data: dict = {"overview": {"stats": {}}, "module_cards": [], "role": "pm"}
        result = render_blueprint_v2(data)
        assert "<!DOCTYPE html>" in result
        assert "</html>" in result

    def test_chat_placeholder(self, rendered_html: str) -> None:
        lower = rendered_html.lower()
        assert "mcp" in lower or "对话" in lower or "chat" in lower
