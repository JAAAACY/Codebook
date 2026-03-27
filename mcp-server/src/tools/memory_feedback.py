"""memory_feedback — 存储 ask_about 的回答摘要到项目记忆系统。

MCP 宿主在生成完整回答后，调用此工具记录关键信息到 ProjectMemory，
用于后续会话的上下文增强。

主要用途：
- 持久化 QA 历史记录（供后续 ask_about 调用参考）
- 跟踪回答置信度（帮助系统判断回答质量）
- 收集用户追问方向（识别知识热点）
"""

from datetime import datetime

import structlog

from src.memory.project_memory import ProjectMemory
from src.memory.models import QARecord
from src.tools._repo_cache import repo_cache

logger = structlog.get_logger()


async def memory_feedback(
    module_name: str,
    question: str,
    answer_summary: str,
    confidence: float = 0.9,
    follow_ups_used: list[str] | None = None,
) -> dict:
    """记录 ask_about 的回答摘要到项目记忆系统。

    Args:
        module_name: 被追问的模块名称。
        question: 用户提出的问题。
        answer_summary: 回答摘要（关键结论，非完整回答）。
        confidence: 回答的置信度（0.0-1.0）。可选，默认 0.9。
        follow_ups_used: 用户在后续追问中实际使用的方向。可选，默认空列表。

    Returns:
        {"status": "ok"|"error", "message": str}
    """
    logger.info(
        "memory_feedback.start",
        module_name=module_name,
        confidence=confidence,
        question_len=len(question),
    )

    if follow_ups_used is None:
        follow_ups_used = []

    # Get repository context from repo_cache
    ctx = repo_cache.get()
    if ctx is None:
        return {
            "status": "error",
            "error": "请先运行 scan_repo 扫描项目",
            "hint": "memory_feedback 需要项目上下文。请先使用 scan_repo 工具。",
        }

    # Get repo_url from cache context
    repo_url = ctx.repo_url
    if not repo_url:
        return {
            "status": "error",
            "error": "无法获取仓库 URL",
            "hint": "缓存的上下文中缺少 repo_url。",
        }

    # Validate module exists
    module_found = False
    for m in ctx.modules:
        if m.name == module_name or m.dir_path == module_name:
            module_found = True
            break

    if not module_found:
        available = [m.name for m in ctx.modules if not m.is_special]
        return {
            "status": "error",
            "error": f"模块「{module_name}」不存在",
            "available_modules": available,
        }

    # Create QA record and persist to ProjectMemory
    try:
        memory = ProjectMemory(repo_url)
        record = QARecord(
            question=question,
            answer_summary=answer_summary,
            confidence=confidence,
            follow_ups_used=follow_ups_used,
            timestamp=datetime.utcnow().isoformat() + "Z",
        )

        success = memory.add_qa_record(module_name, record)
        if not success:
            return {
                "status": "error",
                "error": "写入记忆系统失败",
                "hint": "可能是权限或磁盘空间问题。",
            }

        logger.info(
            "memory_feedback.done",
            module=module_name,
            confidence=confidence,
            follow_ups_count=len(follow_ups_used),
        )

        return {
            "status": "ok",
            "message": f"已记录：模块「{module_name}」的 Q&A 交互。"
            f"置信度 {confidence:.0%}，后续追问方向 {len(follow_ups_used)} 个。"
            f"后续相同模块的追问会自动参考本次记录。",
        }

    except Exception as e:
        logger.exception("memory_feedback.failed", module_name=module_name, error=str(e))
        return {
            "status": "error",
            "error": f"记忆系统错误：{str(e)}",
            "hint": "请检查磁盘空间和文件权限。",
        }
