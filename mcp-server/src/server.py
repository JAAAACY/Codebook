"""CodeBook MCP Server 入口 — 注册所有 tools 并启动服务。"""

from enum import Enum

import logging
import sys

import structlog
from mcp.server.fastmcp import FastMCP

from src.config import settings
from src.tools.ask_about import ask_about as _ask_about
from src.tools.codegen import codegen as _codegen
from src.tools.diagnose import diagnose as _diagnose
from src.tools.read_chapter import read_chapter as _read_chapter
from src.tools.scan_repo import scan_repo as _scan_repo
from src.tools.term_correct import term_correct as _term_correct
from src.tools.memory_feedback import memory_feedback as _memory_feedback

# ── 日志配置 ──────────────────────────────────────────────
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(
        logging.getLevelName(settings.log_level),
    ),
    logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
)
logger = structlog.get_logger()

# ── MCP Server 实例 ──────────────────────────────────────
mcp = FastMCP(
    name="CodeBook",
)


# ── 枚举定义 ─────────────────────────────────────────────
class Role(str, Enum):
    ceo = "ceo"
    pm = "pm"
    investor = "investor"
    qa = "qa"


class Depth(str, Enum):
    overview = "overview"
    detailed = "detailed"


# ── Tool 注册 ─────────────────────────────────────────────


@mcp.tool()
async def scan_repo(repo_url: str, role: Role = Role.pm, depth: Depth = Depth.overview) -> dict:
    """扫描项目仓库，生成蓝图总览（模块列表 + Mermaid 全局依赖图）。

    这是 CodeBook 的第一步：导入项目后自动扫描代码，输出项目全景地图。

    Args:
        repo_url: Git 仓库地址（HTTPS 格式，如 https://github.com/user/repo）。
        role: 目标角色，决定输出的语言风格和关注点。
        depth: 扫描深度。overview 只生成蓝图；detailed 同时生成所有模块卡片。
    """
    logger.info("tool.scan_repo", repo_url=repo_url, role=role.value, depth=depth.value)
    return await _scan_repo(repo_url=repo_url, role=role.value, depth=depth.value)


@mcp.tool()
async def read_chapter(module_name: str, role: Role = Role.pm) -> dict:
    """读取指定模块的详细卡片（看懂能力）。

    在蓝图总览中选中一个模块后，用这个工具深入查看该模块的子组件、
    调用关系、分支逻辑和代码位置。

    Args:
        module_name: 模块名称，使用业务语言（如「用户认证」「文章发布」）。
        role: 目标角色。
    """
    logger.info("tool.read_chapter", module_name=module_name, role=role.value)
    return await _read_chapter(module_name=module_name, role=role.value)


@mcp.tool()
async def diagnose(module_name: str = "all", role: Role = Role.pm, query: str = "") -> dict:
    """用自然语言描述问题，追踪调用链定位到精确代码位置（定位能力）。

    输入一段对问题的描述（如「注册时邮箱重复报错不友好」），
    系统会追踪调用链路，返回 Mermaid 流程图和精确的 file:line 定位。

    Args:
        module_name: 缩小诊断范围到指定模块，默认 "all" 全项目扫描。
        role: 目标角色。
        query: 用自然语言描述你观察到的问题或想了解的功能。
    """
    logger.info("tool.diagnose", module_name=module_name, role=role.value, query=query)
    return await _diagnose(module_name=module_name, role=role.value, query=query)


@mcp.tool()
async def codegen(
    instruction: str,
    repo_path: str,
    locate_result: dict | None = None,
    file_paths: list[str] | None = None,
    role: Role = Role.pm,
) -> dict:
    """用自然语言描述修改需求，自动生成可直接应用的代码变更（代码生成能力）。

    输入一段修改指令（如「把注册报错改成中文」），结合 locate 阶段的定位结果，
    生成精确的 unified diff 代码变更，附带业务语言说明和验证步骤。

    Args:
        instruction: 自然语言修改指令（如「邮箱已注册时引导用户去登录」）。
        repo_path: 本地仓库路径（scan_repo 的 clone 路径）。
        locate_result: diagnose 工具返回的定位结果。可选。
        file_paths: 要修改的文件路径列表。与 locate_result 互补。
        role: 目标角色。
    """
    logger.info("tool.codegen", instruction=instruction[:80], repo_path=repo_path)
    return await _codegen(
        instruction=instruction,
        repo_path=repo_path,
        locate_result=locate_result,
        file_paths=file_paths,
        role=role.value,
    )


@mcp.tool()
async def ask_about(
    module_name: str,
    question: str,
    role: Role = Role.pm,
    conversation_history: list[dict] | None = None,
) -> dict:
    """针对特定模块进行追问对话（追问能力）。

    选中一个模块后，可以用自然语言提出任何问题。系统会结合该模块的
    代码、上下游依赖和诊断结果来回答，并给出后续追问建议。
    支持多轮对话：将之前的问答历史传入 conversation_history 即可。

    Args:
        module_name: 要追问的模块名称（业务语言）。
        question: 你的问题（自然语言，如「这个模块最大的风险是什么？」）。
        role: 目标角色。
        conversation_history: 多轮对话历史。格式:
            [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
    """
    logger.info("tool.ask_about", module_name=module_name, question=question, role=role.value)
    return await _ask_about(
        module_name=module_name,
        question=question,
        role=role.value,
        conversation_history=conversation_history or [],
    )


@mcp.tool()
async def term_correct(
    source_term: str,
    correct_translation: str,
    wrong_translation: str = "",
    context: str = "",
) -> dict:
    """纠正项目术语映射（术语纠正能力）。

    用于 PM、领域专家等角色显式纠正代码术语到业务语言的映射。纠正后
    优先级最高，所有后续的 scan_repo、read_chapter、diagnose 等工具
    都会优先使用该纠正，确保术语翻译的一致性。

    Args:
        source_term: 原始代码术语（如 "idempotent"）。
        correct_translation: 正确的翻译或业务术语（如 "幂等操作"）。
        wrong_translation: 可选。之前的错误翻译（用于记录和文档）。
        context: 可选。此纠正适用的场景（如 "API 响应"、"支付对账"）。
    """
    logger.info("tool.term_correct", source_term=source_term, context=context)
    return await _term_correct(
        source_term=source_term,
        correct_translation=correct_translation,
        wrong_translation=wrong_translation,
        context=context,
    )


@mcp.tool()
async def memory_feedback(
    module_name: str,
    question: str,
    answer_summary: str,
    confidence: float = 0.9,
    follow_ups_used: list[str] | None = None,
) -> dict:
    """记录 ask_about 的回答摘要到项目记忆系统（记忆反馈能力）。

    在 MCP 宿主（Claude Desktop）生成完整回答后，调用此工具记录关键信息
    到 ProjectMemory，用于后续会话的上下文增强和知识热点识别。

    Args:
        module_name: 被追问的模块名称。
        question: 用户提出的问题。
        answer_summary: 回答摘要（关键结论，不是完整回答）。
        confidence: 可选。回答的置信度（0.0-1.0，默认 0.9）。
        follow_ups_used: 可选。用户在后续追问中实际使用的方向列表。
    """
    logger.info("tool.memory_feedback", module_name=module_name, confidence=confidence)
    return await _memory_feedback(
        module_name=module_name,
        question=question,
        answer_summary=answer_summary,
        confidence=confidence,
        follow_ups_used=follow_ups_used or [],
    )


# ── 入口 ─────────────────────────────────────────────────


def _startup_health_check():
    """启动时检查 tree-sitter 可用性，缓存损坏时自动修复。"""
    try:
        from tree_sitter_language_pack import get_language
        get_language("python")
        logger.info("tree_sitter.startup_ok")
        return
    except ImportError:
        logger.warning("tree_sitter.not_installed",
                       msg="tree-sitter-language-pack 未安装，将使用正则 fallback")
        return
    except Exception as e:
        logger.warning("tree_sitter.startup_failed", error=str(e),
                       msg="grammar 加载失败，尝试清理缓存...")

    # 尝试自动修复：清缓存后重试
    try:
        from tree_sitter_language_pack import clean_cache
        clean_cache()
        logger.info("tree_sitter.cache_cleaned")

        # 重试
        from tree_sitter_language_pack import get_language
        get_language("python")
        logger.info("tree_sitter.startup_recovered",
                     msg="缓存清理后恢复正常")
    except Exception as e2:
        logger.error("tree_sitter.startup_unrecoverable", error=str(e2),
                      msg="自动修复失败，请手动执行: "
                          "pip install tree-sitter-language-pack --force-reinstall --no-cache-dir")


def main():
    """启动 CodeBook MCP Server。"""
    logger.info(
        "server.starting",
        name=settings.app_name,
        version=settings.app_version,
    )
    _startup_health_check()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
