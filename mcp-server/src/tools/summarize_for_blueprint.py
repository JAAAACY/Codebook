"""summarize_for_blueprint — 为 LLM 组装蓝图摘要上下文。

扫描完成后调用，从 repo_cache 获取 SummaryContext，
组装 LLM 推理所需的模块结构 + prompt 指令 + 降级摘要。
"""

from __future__ import annotations

import structlog

from src.summarizer.blueprint_summary import build_fallback_summary, build_summary_context
from src.tools._repo_cache import repo_cache

logger = structlog.get_logger()


async def summarize_for_blueprint(repo_url: str) -> dict:
    """获取蓝图摘要的 LLM 上下文。

    从 repo_cache 中读取已扫描的 SummaryContext，组装 LLM 推理所需的
    模块数据、prompt 指令和降级摘要。

    Args:
        repo_url: 已扫描过的仓库地址。

    Returns:
        dict with status, prompt, modules, connections, fallback_summary, guidance.
    """
    ctx = repo_cache.get(repo_url)
    if ctx is None:
        logger.warning("summarize_for_blueprint.no_cache", repo_url=repo_url)
        return {
            "status": "error",
            "message": "请先使用 scan_repo 扫描该仓库",
        }

    # 提取业务流程
    from src.summarizer.flow_extractor import extract_flows
    flows_result = extract_flows(ctx)

    # 组装 LLM 上下文
    llm_context = build_summary_context(ctx, flows_result=flows_result)

    # 生成降级摘要（作为兜底）
    fallback = build_fallback_summary(ctx, flows_result=flows_result)

    logger.info(
        "summarize_for_blueprint.context_ready",
        repo_url=repo_url,
        module_count=len(llm_context["modules"]),
    )

    return {
        "status": "context_ready",
        "prompt": llm_context["prompt"],
        "modules": llm_context["modules"],
        "connections": llm_context["connections"],
        "fallback_summary": fallback.to_dict(),
        "guidance": (
            "请根据 prompt 和 modules/connections 数据进行推理，"
            "生成符合输出要求的 JSON 对象，然后调用 save_blueprint_summary 保存结果。"
            "如果推理失败，可直接使用 fallback_summary 作为降级结果。"
        ),
    }
