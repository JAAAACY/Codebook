"""ask_about 验收测试。

验收标准：
1. 单轮追问返回正确 JSON
2. 回答引用了 context 信息
3. evidence 指向真实代码位置
4. follow_up 有意义
5. 多轮保持连贯（第2轮引用第1轮内容）
6. 切换角色后语言风格变化
7. 超出范围的问题诚实回答
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# 确保 src 可以被 import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.parsers.ast_parser import ParseResult, FunctionInfo, ClassInfo, ImportInfo, CallInfo
from src.parsers.dependency_graph import DependencyGraph
from src.parsers.module_grouper import ModuleGroup
from src.parsers.repo_cloner import CloneResult, FileInfo
from src.summarizer.engine import SummaryContext
from src.tools._repo_cache import RepoCache, repo_cache
from src.tools.ask_about import (
    ask_about,
    diagnosis_cache,
    DiagnosisCache,
    ROLE_CONFIG,
    assemble_context,
    _find_module,
    _get_neighbor_modules,
    _build_system_prompt,
    _parse_llm_response,
    _build_module_l3_summary,
    _build_diagnosis_context,
    _build_annotation_context,
    _AskAboutLLMCaller,
)


# ── 测试用 fixtures ────────────────────────────────────


@pytest.fixture
def temp_repo(tmp_path):
    """创建一个临时仓库结构用于测试。"""
    # 支付模块
    pay_dir = tmp_path / "app" / "payment"
    pay_dir.mkdir(parents=True)
    (pay_dir / "processor.py").write_text(textwrap.dedent("""\
        import os
        from app.order import Order

        class PaymentProcessor:
            \"\"\"处理支付请求。\"\"\"

            def process_payment(self, order_id: str, amount: float) -> dict:
                \"\"\"执行支付流程。\"\"\"
                order = Order.get(order_id)
                if amount <= 0:
                    raise ValueError("金额必须大于零")
                if amount > 10000:
                    return {"status": "需要人工审核", "reason": "大额支付"}
                return {"status": "成功", "transaction_id": "txn_123"}

            def refund(self, transaction_id: str) -> dict:
                \"\"\"退款。\"\"\"
                return {"status": "退款成功"}

            def _validate_card(self, card_number: str) -> bool:
                \"\"\"内部校验。\"\"\"
                return len(card_number) == 16
    """), encoding="utf-8")

    # 订单模块
    order_dir = tmp_path / "app" / "order"
    order_dir.mkdir(parents=True)
    (order_dir / "models.py").write_text(textwrap.dedent("""\
        class Order:
            \"\"\"订单模型。\"\"\"
            def __init__(self, order_id, user_id, amount):
                self.order_id = order_id
                self.user_id = user_id
                self.amount = amount

            @classmethod
            def get(cls, order_id):
                return cls(order_id, "user_1", 100.0)

            def cancel(self):
                self.status = "cancelled"
    """), encoding="utf-8")

    # 通知模块
    notify_dir = tmp_path / "app" / "notification"
    notify_dir.mkdir(parents=True)
    (notify_dir / "sender.py").write_text(textwrap.dedent("""\
        def send_email(to: str, subject: str, body: str) -> bool:
            \"\"\"发送邮件通知。\"\"\"
            return True

        def send_sms(phone: str, message: str) -> bool:
            \"\"\"发送短信。\"\"\"
            return True
    """), encoding="utf-8")

    return tmp_path


@pytest.fixture
def build_ctx(temp_repo):
    """构建完整的 SummaryContext。"""
    repo_path = str(temp_repo)

    # FileInfo
    files = [
        FileInfo(path="app/payment/processor.py",
                 abs_path=str(temp_repo / "app/payment/processor.py"),
                 language="python", size_bytes=500, line_count=25, is_config=False),
        FileInfo(path="app/order/models.py",
                 abs_path=str(temp_repo / "app/order/models.py"),
                 language="python", size_bytes=300, line_count=15, is_config=False),
        FileInfo(path="app/notification/sender.py",
                 abs_path=str(temp_repo / "app/notification/sender.py"),
                 language="python", size_bytes=200, line_count=10, is_config=False),
    ]

    clone_result = CloneResult(
        repo_path=repo_path,
        files=files,
        languages={"python": 50},
        total_lines=50,
    )

    # ParseResults
    payment_pr = ParseResult(
        file_path="app/payment/processor.py",
        language="python",
        classes=[ClassInfo(name="PaymentProcessor", methods=["process_payment", "refund", "_validate_card"],
                           parent_class=None, line_start=4, line_end=24)],
        functions=[
            FunctionInfo(name="process_payment", params=["self", "order_id", "amount"],
                         return_type="dict", line_start=7, line_end=14,
                         docstring="执行支付流程。", is_method=True, parent_class="PaymentProcessor"),
            FunctionInfo(name="refund", params=["self", "transaction_id"],
                         return_type="dict", line_start=16, line_end=18,
                         docstring="退款。", is_method=True, parent_class="PaymentProcessor"),
            FunctionInfo(name="_validate_card", params=["self", "card_number"],
                         return_type="bool", line_start=20, line_end=22,
                         docstring="内部校验。", is_method=True, parent_class="PaymentProcessor"),
        ],
        imports=[
            ImportInfo(module="os", names=["os"], is_relative=False, line=1),
            ImportInfo(module="app.order", names=["Order"], is_relative=False, line=2),
        ],
        calls=[
            CallInfo(caller_func="process_payment", callee_name="Order.get", line=9),
        ],
        line_count=25,
        parse_errors=[],
    )

    order_pr = ParseResult(
        file_path="app/order/models.py",
        language="python",
        classes=[ClassInfo(name="Order", methods=["get", "cancel"],
                           parent_class=None, line_start=1, line_end=14)],
        functions=[
            FunctionInfo(name="get", params=["cls", "order_id"],
                         return_type=None, line_start=9, line_end=10,
                         docstring=None, is_method=True, parent_class="Order"),
            FunctionInfo(name="cancel", params=["self"],
                         return_type=None, line_start=12, line_end=13,
                         docstring=None, is_method=True, parent_class="Order"),
        ],
        imports=[],
        calls=[],
        line_count=14,
        parse_errors=[],
    )

    notify_pr = ParseResult(
        file_path="app/notification/sender.py",
        language="python",
        classes=[],
        functions=[
            FunctionInfo(name="send_email", params=["to", "subject", "body"],
                         return_type="bool", line_start=1, line_end=3,
                         docstring="发送邮件通知。", is_method=False, parent_class=None),
            FunctionInfo(name="send_sms", params=["phone", "message"],
                         return_type="bool", line_start=5, line_end=7,
                         docstring="发送短信。", is_method=False, parent_class=None),
        ],
        imports=[],
        calls=[],
        line_count=7,
        parse_errors=[],
    )

    parse_results = [payment_pr, order_pr, notify_pr]

    # ModuleGroups
    modules = [
        ModuleGroup(name="支付模块", dir_path="app/payment",
                    files=["app/payment/processor.py"],
                    entry_functions=["process_payment"],
                    public_interfaces=["PaymentProcessor"],
                    total_lines=25, is_special=False),
        ModuleGroup(name="订单模块", dir_path="app/order",
                    files=["app/order/models.py"],
                    entry_functions=["get"],
                    public_interfaces=["Order"],
                    total_lines=14, is_special=False),
        ModuleGroup(name="通知模块", dir_path="app/notification",
                    files=["app/notification/sender.py"],
                    entry_functions=["send_email", "send_sms"],
                    public_interfaces=["send_email", "send_sms"],
                    total_lines=7, is_special=False),
    ]

    # DependencyGraph
    dep_graph = DependencyGraph()
    dep_graph.build(parse_results)

    # 设置模块分组
    module_map = {}
    for pr in parse_results:
        for m in modules:
            if pr.file_path in m.files:
                for func in pr.functions:
                    if func.parent_class:
                        nid = f"{pr.file_path}::{func.parent_class}.{func.name}"
                    else:
                        nid = f"{pr.file_path}::{func.name}"
                    module_map[nid] = m.name
                for cls in pr.classes:
                    nid = f"{pr.file_path}::{cls.name}"
                    module_map[nid] = m.name
    dep_graph.set_module_groups(module_map)

    ctx = SummaryContext(
        clone_result=clone_result,
        parse_results=parse_results,
        modules=modules,
        dep_graph=dep_graph,
        role="pm",
    )

    return ctx


# ── 验收测试 ────────────────────────────────────────────


class TestAskAboutAcceptance:
    """ask_about 验收测试套件。"""

    # ── 1. 单轮追问返回正确 JSON ──

    @pytest.mark.asyncio
    async def test_single_turn_returns_valid_json(self, build_ctx):
        """验收1：单轮追问返回正确 JSON 结构。"""
        ctx = build_ctx
        repo_cache.store("test-repo", ctx)

        result = await ask_about(
            module_name="支付模块",
            question="支付模块是做什么的？",
            role="ceo",
        )

        # 结构完整性检查
        assert result["status"] == "ok"
        assert result["module_name"] == "支付模块"
        assert result["role"] == "ceo"
        assert isinstance(result["context"], str)
        assert len(result["context"]) > 0
        assert "支付模块" in result["context"]
        assert isinstance(result["guidance"], str)
        assert len(result["guidance"]) > 0
        assert isinstance(result["question"], str)
        assert result["question"] == "支付模块是做什么的？"
        assert isinstance(result["conversation_history"], list)
        assert isinstance(result["context_modules_used"], list)
        assert "支付模块" in result["context_modules_used"]

    # ── 2. 回答引用了 context 信息 ──

    @pytest.mark.asyncio
    async def test_answer_uses_context(self, build_ctx):
        """验收2：返回的 context 中包含了模块信息和源代码。"""
        ctx = build_ctx
        repo_cache.store("test-repo", ctx)

        result = await ask_about(
            module_name="支付模块",
            question="这个模块做什么？",
            role="pm",
        )

        assert result["status"] == "ok"

        # 验证上下文中包含了模块信息和代码
        context = result["context"]
        assert "支付模块" in context
        assert "process_payment" in context or "processor.py" in context

    # ── 3. evidence 指向真实代码位置 ──

    @pytest.mark.asyncio
    async def test_evidence_points_to_real_code(self, build_ctx):
        """验收3：返回的 context 中包含了真实代码位置。"""
        ctx = build_ctx
        repo_cache.store("test-repo", ctx)

        result = await ask_about(
            module_name="支付模块",
            question="支付有什么校验逻辑？",
            role="pm",
        )

        assert result["status"] == "ok"
        context = result["context"]

        # 验证上下文中包含了源代码和文件路径
        assert "app/payment/processor.py" in context or "processor.py" in context
        # 验证源代码片段在上下文中
        assert "process_payment" in context or "amount" in context

    # ── 4. follow_up 有意义 ──

    @pytest.mark.asyncio
    async def test_follow_up_suggestions_meaningful(self, build_ctx):
        """验收4：返回的 guidance 包含 follow_up 建议的系统提示。"""
        ctx = build_ctx
        repo_cache.store("test-repo", ctx)

        result = await ask_about(
            module_name="支付模块",
            question="支付流程是什么？",
            role="ceo",
        )

        assert result["status"] == "ok"
        # 验证 guidance 包含后续追问的指导
        assert "follow_up" in result["guidance"].lower() or "后续" in result["guidance"]
        assert isinstance(result["guidance"], str)
        assert len(result["guidance"]) > 100

    # ── 5. 多轮保持连贯 ──

    @pytest.mark.asyncio
    async def test_multi_turn_coherence(self, build_ctx):
        """验收5：多轮对话时 conversation_history 被正确传递。"""
        ctx = build_ctx
        repo_cache.store("test-repo", ctx)

        # 第1轮
        r1 = await ask_about(
            module_name="支付模块",
            question="什么情况下需要人工审核？",
            role="ceo",
        )

        assert r1["status"] == "ok"
        assert len(r1["context"]) > 0

        # 第2轮（带历史）
        history = [
            {"role": "user", "content": "什么情况下需要人工审核？"},
            {"role": "assistant", "content": "支付模块在金额超过一万元时需要人工审核。"},
        ]
        r2 = await ask_about(
            module_name="支付模块",
            question="审核的金额阈值是多少？",
            role="ceo",
            conversation_history=history,
        )

        assert r2["status"] == "ok"
        # 验证对话历史被返回了
        assert r2["conversation_history"] == history
        assert len(r2["context"]) > 0

    # ── 6. 切换角色后语言风格变化 ──

    @pytest.mark.asyncio
    async def test_role_switch_changes_style(self, build_ctx):
        """验收6：不同角色的 guidance 差异显著。"""
        ctx = build_ctx
        repo_cache.store("test-repo", ctx)

        r_ceo = await ask_about(
            module_name="支付模块",
            question="这个模块重要吗？",
            role="ceo",
        )
        r_qa = await ask_about(
            module_name="支付模块",
            question="这个模块重要吗？",
            role="qa",
        )

        assert r_ceo["status"] == "ok"
        assert r_qa["status"] == "ok"

        # 比较 guidance
        ceo_guidance = r_ceo["guidance"]
        qa_guidance = r_qa["guidance"]

        # CEO guidance 包含商业语言
        assert "CEO" in ceo_guidance or "创始人" in ceo_guidance
        assert "商业影响" in ceo_guidance or "战略" in ceo_guidance

        # QA guidance 包含质量语言
        assert "QA" in qa_guidance or "测试" in qa_guidance
        assert "边界条件" in qa_guidance or "质量" in qa_guidance

        # 两者不同
        assert ceo_guidance != qa_guidance

    # ── 7. 超出范围的问题诚实回答 ──

    @pytest.mark.asyncio
    async def test_out_of_scope_honest_answer(self, build_ctx):
        """验收7：超出上下文范围的问题，guidance 包含坦诚说明的指示。"""
        ctx = build_ctx
        repo_cache.store("test-repo", ctx)

        result = await ask_about(
            module_name="支付模块",
            question="数据库的连接池配置在哪里？",
            role="pm",
        )

        assert result["status"] == "ok"

        # guidance 中包含了"坦诚说明"和"超出范围"的指示
        guidance = result["guidance"]
        assert "超出" in guidance or "坦诚" in guidance or "范围" in guidance


class TestAskAboutEdgeCases:
    """边界情况测试。"""

    @pytest.mark.asyncio
    async def test_no_scan_returns_error(self):
        """未扫描项目时返回错误提示。"""
        repo_cache.clear_all()

        result = await ask_about(
            module_name="任意模块",
            question="这是什么？",
            role="ceo",
        )

        assert result["status"] == "error"
        assert "scan_repo" in result["error"]

    @pytest.mark.asyncio
    async def test_unknown_module_returns_candidates(self, build_ctx):
        """查询不存在的模块时返回可用模块列表。"""
        ctx = build_ctx
        repo_cache.store("test-repo", ctx)

        result = await ask_about(
            module_name="不存在的模块",
            question="这是什么？",
            role="pm",
        )

        assert result["status"] == "error"
        assert "不存在" in result["error"] or "未找到" in result["error"]
        assert "available_modules" in result
        assert len(result["available_modules"]) > 0

    @pytest.mark.asyncio
    async def test_fuzzy_module_match(self, build_ctx):
        """模糊匹配模块名（部分匹配）。"""
        ctx = build_ctx
        repo_cache.store("test-repo", ctx)

        result = await ask_about(
            module_name="支付",
            question="这是什么？",
            role="pm",
        )

        assert result["status"] == "ok"
        assert result["module_name"] == "支付"
        assert len(result["context"]) > 0

    @pytest.mark.asyncio
    async def test_empty_conversation_history(self, build_ctx):
        """空对话历史不影响正常工作。"""
        ctx = build_ctx
        repo_cache.store("test-repo", ctx)

        result = await ask_about(
            module_name="订单模块",
            question="这个模块做什么？",
            role="pm",
            conversation_history=[],
        )

        assert result["status"] == "ok"
        assert result["conversation_history"] == []

    @pytest.mark.asyncio
    async def test_default_role_is_ceo(self, build_ctx):
        """默认角色是 ceo。"""
        ctx = build_ctx
        repo_cache.store("test-repo", ctx)

        result = await ask_about(
            module_name="支付模块",
            question="这是什么？",
        )

        assert result["role"] == "ceo"
        assert "CEO" in result["guidance"] or "创始人" in result["guidance"]


class TestContextAssembly:
    """上下文组装逻辑测试。"""

    def test_context_includes_target_module(self, build_ctx):
        """上下文包含目标模块的 L3 摘要。"""
        ctx = build_ctx
        target = ctx.modules[0]  # 支付模块
        context_text, modules_used = assemble_context(ctx, target, ctx.clone_result.repo_path)

        assert "支付模块" in context_text
        assert "支付模块" in modules_used

    def test_context_includes_source_code(self, build_ctx):
        """上下文包含源代码片段。"""
        ctx = build_ctx
        target = ctx.modules[0]  # 支付模块
        context_text, _ = assemble_context(ctx, target, ctx.clone_result.repo_path)

        # 应该包含源代码关键字
        assert "process_payment" in context_text or "processor.py" in context_text

    def test_context_modules_used_tracks_neighbors(self, build_ctx):
        """context_modules_used 包含上下游模块。"""
        ctx = build_ctx
        target = ctx.modules[0]  # 支付模块
        _, modules_used = assemble_context(ctx, target, ctx.clone_result.repo_path)

        assert "支付模块" in modules_used

    def test_diagnosis_context_included(self, build_ctx):
        """诊断结果被包含在上下文中。"""
        ctx = build_ctx

        # 添加一条诊断
        diagnosis_cache._diagnoses.clear()
        diagnosis_cache.add_diagnosis("支付模块", {
            "diagnosis": "支付模块缺少异常处理",
            "matched_modules": "支付模块",
            "exact_locations": [{"file": "app/payment/processor.py", "line": 10, "why_it_matters": "无 try/catch"}],
        })

        target = ctx.modules[0]
        context_text, _ = assemble_context(ctx, target, ctx.clone_result.repo_path)

        assert "诊断" in context_text or "异常处理" in context_text

        # 清理
        diagnosis_cache._diagnoses.clear()

    def test_annotation_context_included(self, build_ctx):
        """用户批注被包含在上下文中。"""
        ctx = build_ctx

        diagnosis_cache._annotations.clear()
        diagnosis_cache.add_annotation("支付模块", {
            "author": "PM-李",
            "text": "这个模块需要支持微信支付",
        })

        target = ctx.modules[0]
        context_text, _ = assemble_context(ctx, target, ctx.clone_result.repo_path)

        assert "微信支付" in context_text or "PM-李" in context_text

        # 清理
        diagnosis_cache._annotations.clear()


class TestHelperFunctions:
    """辅助函数单元测试。"""

    def test_find_module_exact_match(self, build_ctx):
        """精确匹配模块名。"""
        ctx = build_ctx
        m = _find_module(ctx, "支付模块")
        assert m is not None
        assert m.name == "支付模块"

    def test_find_module_dir_match(self, build_ctx):
        """目录名匹配。"""
        ctx = build_ctx
        m = _find_module(ctx, "app/payment")
        assert m is not None
        assert m.name == "支付模块"

    def test_find_module_fuzzy_match(self, build_ctx):
        """模糊匹配。"""
        ctx = build_ctx
        m = _find_module(ctx, "支付")
        assert m is not None
        assert m.name == "支付模块"

    def test_find_module_not_found(self, build_ctx):
        """不存在的模块返回 None。"""
        ctx = build_ctx
        m = _find_module(ctx, "不存在")
        assert m is None

    def test_build_system_prompt_all_roles(self):
        """所有角色都能生成 system prompt。"""
        for role in ["ceo", "pm", "investor", "qa"]:
            prompt = _build_system_prompt(role)
            assert isinstance(prompt, str)
            assert len(prompt) > 100
            assert "JSON" in prompt  # 要求 JSON 输出

    def test_build_system_prompt_unknown_role_falls_back(self):
        """未知角色回退到 pm。"""
        prompt = _build_system_prompt("unknown_role")
        assert "产品经理" in prompt

    def test_parse_llm_response_valid_json(self):
        """解析合法 JSON。"""
        raw = json.dumps({"answer": "test", "evidence": [], "follow_up_suggestions": [], "confidence": 0.8})
        result = _parse_llm_response(raw)
        assert result["answer"] == "test"
        assert result["confidence"] == 0.8

    def test_parse_llm_response_markdown_wrapped(self):
        """解析 markdown 包裹的 JSON。"""
        inner = json.dumps({"answer": "wrapped", "evidence": [], "follow_up_suggestions": [], "confidence": 0.7})
        raw = f"```json\n{inner}\n```"
        result = _parse_llm_response(raw)
        assert result["answer"] == "wrapped"

    def test_parse_llm_response_plain_text_fallback(self):
        """纯文本回退。"""
        result = _parse_llm_response("这是一个纯文本回答，没有 JSON 格式。")
        assert result["answer"] == "这是一个纯文本回答，没有 JSON 格式。"
        assert result["confidence"] == 0.5

    def test_diagnosis_cache_operations(self):
        """DiagnosisCache 增删查。"""
        cache = DiagnosisCache()
        cache.add_diagnosis("A", {"diagnosis": "问题1"})
        cache.add_diagnosis("A", {"diagnosis": "问题2"})
        cache.add_annotation("A", {"author": "x", "text": "备注"})

        assert len(cache.get_diagnoses("A")) == 2
        assert len(cache.get_annotations("A")) == 1
        assert len(cache.get_diagnoses("B")) == 0

    def test_role_config_completeness(self):
        """所有角色配置都包含必要字段。"""
        for role, cfg in ROLE_CONFIG.items():
            assert "name" in cfg, f"{role} 缺少 name"
            assert "language_style" in cfg, f"{role} 缺少 language_style"
            assert "banned_terms" in cfg, f"{role} 缺少 banned_terms"
