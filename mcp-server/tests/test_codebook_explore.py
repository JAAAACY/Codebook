"""codebook_explore 编排工具的单元测试。

测试覆盖：
1. 无输入 → need_input 提示
2. 仅代码片段 → snippet_only 降级
3. 模块选择策略（问题驱动 + 拓扑驱动）
4. 完整链路（使用 mini_project）
"""

from __future__ import annotations

import pytest

from src.tools.codebook_explore import (
    _select_modules_by_query,
    _select_modules_by_topology,
    codebook_explore,
    MAX_AUTO_CHAPTERS,
)


# ── 模块选择策略测试 ─────────────────────────────────────


class TestModuleSelection:
    """测试混合驱动的模块选择逻辑。"""

    SAMPLE_MODULES = [
        {"name": "用户认证", "node_title": "认证与登录", "node_body": "处理 login, register, JWT token"},
        {"name": "数据库", "node_title": "数据存储层", "node_body": "用户表、订单表的 CRUD"},
        {"name": "API 路由", "node_title": "HTTP 路由", "node_body": "REST API 入口，请求分发"},
        {"name": "支付", "node_title": "支付处理", "node_body": "支付宝、微信支付集成"},
        {"name": "通知", "node_title": "消息通知", "node_body": "邮件、短信、推送通知"},
    ]

    SAMPLE_CONNECTIONS = [
        {"from": "API 路由", "to": "用户认证"},
        {"from": "API 路由", "to": "支付"},
        {"from": "API 路由", "to": "通知"},
        {"from": "用户认证", "to": "数据库"},
        {"from": "支付", "to": "数据库"},
        {"from": "支付", "to": "通知"},
    ]

    def test_query_driven_exact_match(self):
        """问题关键词精确匹配模块名。"""
        result = _select_modules_by_query(self.SAMPLE_MODULES, "登录失败")
        assert "用户认证" in result

    def test_query_driven_body_match(self):
        """问题关键词匹配模块描述。"""
        result = _select_modules_by_query(self.SAMPLE_MODULES, "JWT token 过期")
        assert "用户认证" in result

    def test_query_driven_payment(self):
        """支付相关问题。"""
        result = _select_modules_by_query(self.SAMPLE_MODULES, "支付宝回调超时")
        assert "支付" in result

    def test_query_driven_empty_query(self):
        """空 query 返回空列表。"""
        result = _select_modules_by_query(self.SAMPLE_MODULES, "")
        assert result == []

    def test_query_driven_no_match(self):
        """无匹配时返回空列表。"""
        result = _select_modules_by_query(self.SAMPLE_MODULES, "blockchain NFT")
        assert result == []

    def test_topology_driven_hub_selection(self):
        """拓扑驱动应选出连接最多的 hub 模块。"""
        result = _select_modules_by_topology(self.SAMPLE_MODULES, self.SAMPLE_CONNECTIONS)
        # API 路由 out_degree=3, 数据库 in_degree=2, 应该排前面
        assert len(result) >= 3
        assert "API 路由" in result
        assert "数据库" in result

    def test_topology_driven_respects_limit(self):
        """不超过 MAX_AUTO_CHAPTERS。"""
        result = _select_modules_by_topology(self.SAMPLE_MODULES, self.SAMPLE_CONNECTIONS)
        assert len(result) <= MAX_AUTO_CHAPTERS

    def test_topology_driven_no_connections(self):
        """无依赖关系时按顺序取前 3 个。"""
        result = _select_modules_by_topology(self.SAMPLE_MODULES, [])
        assert len(result) == 3
        assert result[0] == "用户认证"  # 列表第一个


# ── 编排工具集成测试 ──────────────────────────────────────


class TestCodebookExplore:
    """测试 codebook_explore 主函数的各种输入场景。"""

    @pytest.mark.asyncio
    async def test_no_input_returns_need_input(self):
        """无输入时返回友好提示。"""
        result = await codebook_explore()
        assert result["status"] == "need_input"
        assert "欢迎使用 CodeBook" in result["message"]

    @pytest.mark.asyncio
    async def test_snippet_only_mode(self):
        """只有代码片段时进入降级模式。"""
        result = await codebook_explore(
            code_snippet="def hello(): return 'world'",
        )
        assert result["status"] == "snippet_only"
        assert result["mode"] == "snippet_only"
        assert "建议提供完整的仓库链接" in result["message"]

    @pytest.mark.asyncio
    async def test_snippet_with_query(self):
        """代码片段 + 问题，降级模式保留 query。"""
        result = await codebook_explore(
            code_snippet="def hello(): return 'world'",
            query="这个函数是做什么的？",
        )
        assert result["status"] == "snippet_only"
        assert result["query"] == "这个函数是做什么的？"

    @pytest.mark.asyncio
    async def test_full_pipeline_with_local_path(self, mini_project_path):
        """完整链路：本地路径 → scan → chapters → diagnose。"""
        result = await codebook_explore(
            repo_url=mini_project_path,
            role="pm",
        )

        # 基础断言
        assert result["status"] == "ok"
        assert result["mode"] == "full"

        # Phase 1: scan 成功
        scan = result["phases"]["scan"]
        assert scan["status"] == "ok"
        assert len(scan["modules"]) > 0

        # 有选中的模块
        assert len(result["selected_modules"]) > 0
        assert result["selection_strategy"] == "topology_driven"

        # Phase 2: 至少读了一些章节
        chapters = result["phases"]["chapters"]
        assert chapters["count"] > 0

        # Phase 3: 有诊断结果
        diagnose = result["phases"]["diagnose"]
        assert diagnose["count"] > 0

        # report_data 存在
        assert "report_data" in result
        report = result["report_data"]
        assert len(report["module_cards"]) > 0

    @pytest.mark.asyncio
    async def test_query_driven_pipeline(self, mini_project_path):
        """带问题的全链路：应走问题驱动选模块。"""
        result = await codebook_explore(
            repo_url=mini_project_path,
            query="登录认证是怎么实现的",
            role="pm",
        )

        assert result["status"] == "ok"
        # 有问题时应该走问题驱动（或 topology_fallback）
        assert result["selection_strategy"] in ("query_driven", "topology_fallback")

    @pytest.mark.asyncio
    async def test_invalid_repo_url(self):
        """无效的仓库地址应返回错误。"""
        result = await codebook_explore(
            repo_url="https://github.com/nonexistent/impossible-repo-12345",
        )
        assert result["status"] == "error"


# ── report_data 结构测试 ──────────────────────────────────


class TestReportData:
    """验证 report_data 结构的完整性。"""

    @pytest.mark.asyncio
    async def test_report_data_structure(self, mini_project_path):
        """report_data 应包含所有前端渲染所需字段。"""
        result = await codebook_explore(
            repo_url=mini_project_path,
            role="pm",
        )

        report = result["report_data"]

        # 顶层字段
        assert "overview" in report
        assert "module_cards" in report
        assert "role" in report
        assert "selection_strategy" in report

        # overview
        overview = report["overview"]
        assert "project_overview" in overview
        assert "stats" in overview
        assert "mermaid_diagram" in overview

        # module_cards
        for card in report["module_cards"]:
            assert "name" in card
            assert "health" in card
            assert "is_selected" in card

        # 被选中的模块应有 chapter 数据
        selected = [c for c in report["module_cards"] if c["is_selected"]]
        if selected:
            has_chapter = any("chapter" in c for c in selected)
            assert has_chapter, "至少一个被选中的模块应有 chapter 数据"
