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


# ── 入口 ─────────────────────────────────────────────────


def main():
    """启动 CodeBook MCP Server。"""
    logger.info(
        "server.starting",
        name=settings.app_name,
        version=settings.app_version,
    )
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
