"""summarizer/engine.py 的测试 — 验证 Prompt 构建和本地摘要生成。"""

import json
import os

import pytest

from src.parsers.repo_cloner import clone_repo
from src.parsers.ast_parser import parse_all
from src.parsers.dependency_graph import DependencyGraph
from src.parsers.module_grouper import group_modules, build_node_module_map
from src.summarizer.engine import (
    SummaryContext,
    build_l1_prompt,
    build_l2_prompt,
    build_l3_prompt,
    build_l4_prompt,
    generate_local_blueprint,
    generate_local_chapter,
    _load_prompt_template,
    _get_banned_terms,
    _get_http_annotations,
)

CONDUIT_PATH = "/tmp/conduit"
CONDUIT_EXISTS = os.path.isdir(CONDUIT_PATH)

skip_if_no_conduit = pytest.mark.skipif(
    not CONDUIT_EXISTS, reason="Conduit not found at /tmp/conduit",
)


@pytest.fixture
async def conduit_ctx():
    """构建 Conduit 项目的 SummaryContext。"""
    clone_result = await clone_repo(CONDUIT_PATH)
    py_files = [f for f in clone_result.files if f.language == "python" and not f.is_config]
    parse_results = await parse_all(py_files)
    modules = await group_modules(parse_results, CONDUIT_PATH)
    dep_graph = DependencyGraph()
    dep_graph.build(parse_results)
    node_map = build_node_module_map(modules, parse_results)
    dep_graph.set_module_groups(node_map)

    return SummaryContext(
        clone_result=clone_result,
        parse_results=parse_results,
        modules=modules,
        dep_graph=dep_graph,
        role="pm",
    )


# ══════════════════════════════════════════════════════════
# Prompt 模板加载测试
# ══════════════════════════════════════════════════════════


class TestPromptTemplates:
    def test_load_l1(self):
        t = _load_prompt_template("L1")
        assert t["level"] == "L1"
        assert "system_prompt" in t
        assert "user_prompt" in t
        assert "variables" in t

    def test_load_l2(self):
        t = _load_prompt_template("L2")
        assert t["level"] == "L2"
        assert "{module_groups}" in t["user_prompt"]

    def test_load_l3(self):
        t = _load_prompt_template("L3")
        assert t["level"] == "L3"
        assert "module_card" in t["name"].lower() or "模块卡片" in t["name"]
        assert "{module_name}" in t["user_prompt"]

    def test_load_l4(self):
        t = _load_prompt_template("L4")
        assert t["level"] == "L4"
        assert "{code_content}" in t["user_prompt"]

    def test_load_invalid_level(self):
        with pytest.raises(KeyError):
            _load_prompt_template("L5")

    def test_banned_terms_not_empty(self):
        terms = _get_banned_terms()
        assert len(terms) > 0
        assert "幂等" in terms or "slug" in terms

    def test_http_annotations_not_empty(self):
        annotations = _get_http_annotations()
        assert "400" in annotations
        assert "200" in annotations


# ══════════════════════════════════════════════════════════
# Prompt 构建测试
# ══════════════════════════════════════════════════════════


class TestPromptBuilding:
    @skip_if_no_conduit
    async def test_build_l1_prompt(self, conduit_ctx):
        system, user = build_l1_prompt(conduit_ctx)
        assert len(system) > 50
        assert len(user) > 50
        assert "项目" in system
        # user prompt 应包含填充后的文件树
        assert "app" in user

    @skip_if_no_conduit
    async def test_build_l2_prompt(self, conduit_ctx):
        system, user = build_l2_prompt(conduit_ctx, project_summary="测试项目概览")
        assert len(system) > 50
        assert "测试项目概览" in user
        # 应包含模块信息
        assert "文件" in user

    @skip_if_no_conduit
    async def test_build_l3_prompt(self, conduit_ctx):
        # 取第一个非特殊模块
        target = None
        for m in conduit_ctx.modules:
            if not m.is_special:
                target = m
                break
        assert target is not None

        system, user = build_l3_prompt(conduit_ctx, target, CONDUIT_PATH)
        assert len(system) > 50
        assert target.name in user
        # 应包含状态码注释和禁用术语
        assert "400" in system
        assert "幂等" in system or "slug" in system

    def test_build_l4_prompt(self):
        system, user = build_l4_prompt(
            file_path="app/api/routes/users.py",
            line_start=10,
            line_end=25,
            symbol_name="create_user",
            language="python",
            code_content="async def create_user(...):\n    pass",
            module_name="用户管理",
            callers=["register_route"],
            callees=["save_to_db"],
        )
        assert len(system) > 50
        assert "create_user" in user
        assert "app/api/routes/users.py" in user
        assert "register_route" in user
        assert "save_to_db" in user


# ══════════════════════════════════════════════════════════
# 本地摘要生成测试
# ══════════════════════════════════════════════════════════


class TestLocalGeneration:
    @skip_if_no_conduit
    async def test_generate_local_blueprint(self, conduit_ctx):
        result = generate_local_blueprint(conduit_ctx)

        assert result["status"] == "ok"
        assert len(result["project_overview"]) > 0
        assert len(result["modules"]) > 0
        assert len(result["mermaid_diagram"]) > 0
        assert "graph TD" in result["mermaid_diagram"]
        assert result["stats"]["files"] > 0
        assert result["stats"]["modules"] > 0
        assert result["stats"]["functions"] > 0
        assert result["stats"]["scan_time_seconds"] >= 0

        # 每个模块应有必要字段
        for mod in result["modules"]:
            assert "name" in mod
            assert "paths" in mod
            assert "responsibility" in mod

    @skip_if_no_conduit
    async def test_generate_local_chapter_exists(self, conduit_ctx):
        # 取第一个非特殊模块
        target_name = None
        for m in conduit_ctx.modules:
            if not m.is_special and len(m.files) > 1:
                target_name = m.name
                break
        assert target_name is not None

        result = generate_local_chapter(conduit_ctx, target_name)

        assert result["status"] == "ok"
        assert result["module_name"] == target_name
        assert len(result["module_cards"]) > 0
        assert len(result["dependency_graph"]) > 0

        # 卡片字段完整性
        card = result["module_cards"][0]
        for field in ["name", "path", "what", "inputs", "outputs", "branches",
                       "key_code_refs", "pm_note"]:
            assert field in card, f"Missing field: {field}"

    @skip_if_no_conduit
    async def test_generate_local_chapter_not_found(self, conduit_ctx):
        result = generate_local_chapter(conduit_ctx, "不存在的模块")
        assert result["status"] == "error"
        assert "available_modules" in result

    @skip_if_no_conduit
    async def test_blueprint_module_card_schema_consistent(self, conduit_ctx):
        """蓝图模块 schema 与 codebook_config 一致。"""
        blueprint = generate_local_blueprint(conduit_ctx)

        # codebook_config 中定义的 blueprint module 字段
        expected_fields = {"name", "paths", "responsibility", "entry_points",
                           "depends_on", "used_by", "pm_note"}

        for mod in blueprint["modules"]:
            actual_fields = set(mod.keys())
            assert expected_fields.issubset(actual_fields), (
                f"Module '{mod['name']}' missing fields: {expected_fields - actual_fields}"
            )
