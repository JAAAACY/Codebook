"""save_blueprint_summary — 保存 LLM 生成的蓝图摘要。

接收 LLM 推理结果（JSON），解析为 BlueprintSummary 并持久化到磁盘。
解析失败时自动降级到 build_fallback_summary。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import structlog

from src.summarizer.blueprint_summary import parse_llm_response
from src.tools._repo_cache import repo_cache

logger = structlog.get_logger()


def _save_to_memory(repo_url: str, summary_dict: dict[str, Any]) -> Path:
    """将摘要保存到 ~/.codebook/memory/{repo_hash}/blueprint_summary.json。

    Returns:
        保存文件的 Path。
    """
    repo_hash = hashlib.sha256(repo_url.encode()).hexdigest()[:16]
    memory_dir = Path.home() / ".codebook" / "memory" / repo_hash
    memory_dir.mkdir(parents=True, exist_ok=True)

    file_path = memory_dir / "blueprint_summary.json"
    file_path.write_text(json.dumps(summary_dict, ensure_ascii=False, indent=2))

    logger.info(
        "save_blueprint_summary.saved",
        repo_url=repo_url,
        path=str(file_path),
    )
    return file_path


async def save_blueprint_summary(repo_url: str, summary_json: dict) -> dict:
    """保存 LLM 生成的蓝图摘要。

    解析 LLM 返回的 JSON，构建 BlueprintSummary 并持久化。
    如果解析失败，自动降级到规则生成的摘要。

    Args:
        repo_url: 已扫描过的仓库地址。
        summary_json: LLM 推理结果（符合 BlueprintSummary schema 的 dict）。

    Returns:
        dict with status, message, summary.
    """
    ctx = repo_cache.get(repo_url)
    if ctx is None:
        logger.warning("save_blueprint_summary.no_cache", repo_url=repo_url)
        return {
            "status": "error",
            "message": "请先使用 scan_repo 扫描该仓库",
        }

    # 解析 LLM 结果（失败自动降级）
    summary = parse_llm_response(summary_json, ctx)
    summary_dict = summary.to_dict()

    # 持久化
    saved_path = _save_to_memory(repo_url, summary_dict)

    logger.info(
        "save_blueprint_summary.completed",
        repo_url=repo_url,
        module_count=len(summary.modules),
        path=str(saved_path),
    )

    return {
        "status": "ok",
        "message": f"蓝图摘要已保存到 {saved_path}",
        "summary": summary_dict,
    }
