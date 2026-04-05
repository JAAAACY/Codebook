"""blueprint_summary — 蓝图摘要数据模型、降级构建、LLM 上下文组装与解析。

提供四个核心 dataclass（FunctionSummary, ModuleSummary, ConnectionSummary,
BlueprintSummary）以及三个公共函数：

- build_fallback_summary: 纯规则降级，无需 LLM
- build_summary_context: 为 LLM 组装上下文（modules + prompt）
- parse_llm_response: 解析 LLM 返回，失败时自动降级
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

from src.summarizer.business_namer import (
    infer_business_description,
    infer_business_name,
    infer_connection_verb,
    infer_function_explanation,
)

logger = structlog.get_logger()

# 避免循环导入 — SummaryContext 仅用于类型注解
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.summarizer.engine import SummaryContext


# ── 数据模型 ─────────────────────────────────────────────────


@dataclass
class FunctionSummary:
    """一个函数/方法的摘要。"""

    code_name: str
    business_name: str
    explanation: str
    file_path: str
    line_start: int
    params: list[str] = field(default_factory=list)
    return_type: str | None = None


@dataclass
class ModuleSummary:
    """一个模块的摘要。"""

    code_path: str
    business_name: str
    description: str
    health: str  # "green" | "yellow" | "red"
    functions: list[FunctionSummary] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    used_by: list[str] = field(default_factory=list)


@dataclass
class ConnectionSummary:
    """两个模块之间的连接描述。"""

    from_module: str
    to_module: str
    verb: str
    call_count: int = 0


@dataclass
class BlueprintSummary:
    """完整的蓝图摘要。"""

    project_name: str
    project_description: str
    modules: list[ModuleSummary] = field(default_factory=list)
    connections: list[ConnectionSummary] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """序列化为纯 dict（可直接 json.dumps）。"""
        return {
            "project_name": self.project_name,
            "project_description": self.project_description,
            "modules": [
                {
                    "code_path": m.code_path,
                    "business_name": m.business_name,
                    "description": m.description,
                    "health": m.health,
                    "functions": [
                        {
                            "code_name": f.code_name,
                            "business_name": f.business_name,
                            "explanation": f.explanation,
                            "file_path": f.file_path,
                            "line_start": f.line_start,
                            "params": list(f.params),
                            "return_type": f.return_type,
                        }
                        for f in m.functions
                    ],
                    "depends_on": list(m.depends_on),
                    "used_by": list(m.used_by),
                }
                for m in self.modules
            ],
            "connections": [
                {
                    "from_module": c.from_module,
                    "to_module": c.to_module,
                    "verb": c.verb,
                    "call_count": c.call_count,
                }
                for c in self.connections
            ],
        }


# ── 健康度评估 ───────────────────────────────────────────────


def _assess_health(total_lines: int) -> str:
    """按行数评估模块健康度。"""
    if total_lines > 3000:
        return "red"
    if total_lines > 1000:
        return "yellow"
    return "green"


# ── build_fallback_summary ───────────────────────────────────


def build_fallback_summary(ctx: SummaryContext) -> BlueprintSummary:
    """使用 business_namer 规则生成降级蓝图摘要（无需 LLM）。

    跳过 is_special 的模块。为每个模块和函数生成中文名称与描述。
    """
    # 建立文件 → ParseResult 的索引
    pr_by_file: dict[str, Any] = {}
    for pr in ctx.parse_results:
        pr_by_file[pr.file_path] = pr

    # 获取模块级依赖图
    module_graph = ctx.dep_graph.get_module_graph()

    module_summaries: list[ModuleSummary] = []
    module_name_set: set[str] = set()

    for mg in ctx.modules:
        if mg.is_special:
            continue

        module_name_set.add(mg.name)
        business_name = infer_business_name(mg.dir_path)

        # 收集模块内所有函数
        all_functions: list[FunctionSummary] = []
        all_func_names: list[str] = []
        all_class_names: list[str] = []

        for file_path in mg.files:
            pr = pr_by_file.get(file_path)
            if pr is None:
                continue

            all_func_names.extend(f.name for f in pr.functions)
            all_class_names.extend(c.name for c in pr.classes)

            for fi in pr.functions:
                explanation = infer_function_explanation(
                    fi.name,
                    fi.params,
                    fi.return_type,
                    fi.docstring,
                )
                func_business_name = infer_business_name(fi.name)
                all_functions.append(
                    FunctionSummary(
                        code_name=fi.name,
                        business_name=func_business_name,
                        explanation=explanation,
                        file_path=file_path,
                        line_start=fi.line_start,
                        params=list(fi.params),
                        return_type=fi.return_type,
                    )
                )

        description = infer_business_description(
            mg.name,
            all_func_names,
            all_class_names,
            len(mg.files),
            mg.total_lines,
        )

        # 依赖关系
        depends_on: list[str] = []
        used_by: list[str] = []
        if module_graph.has_node(mg.name):
            depends_on = list(module_graph.successors(mg.name))
            used_by = list(module_graph.predecessors(mg.name))

        module_summaries.append(
            ModuleSummary(
                code_path=mg.dir_path,
                business_name=business_name,
                description=description,
                health=_assess_health(mg.total_lines),
                functions=all_functions,
                depends_on=depends_on,
                used_by=used_by,
            )
        )

    # 连接
    connections: list[ConnectionSummary] = []
    for u, v, data in module_graph.edges(data=True):
        # 只保留非 special 模块之间的连接
        if u in module_name_set and v in module_name_set:
            verb = infer_connection_verb(u, v, data.get("call_count", 1))
            connections.append(
                ConnectionSummary(
                    from_module=u,
                    to_module=v,
                    verb=verb,
                    call_count=data.get("call_count", 1),
                )
            )

    # 项目名：从 repo_url 推断或使用目录名
    project_name = _infer_project_name(ctx)

    return BlueprintSummary(
        project_name=project_name,
        project_description=f"{project_name} 项目蓝图（规则降级）",
        modules=module_summaries,
        connections=connections,
    )


def _infer_project_name(ctx: SummaryContext) -> str:
    """从 repo_url 或 clone_result.repo_path 推断项目名。"""
    if ctx.repo_url:
        # https://github.com/user/repo -> repo
        return ctx.repo_url.rstrip("/").rsplit("/", maxsplit=1)[-1].removesuffix(".git")
    return ctx.clone_result.repo_path.rstrip("/").rsplit("/", maxsplit=1)[-1]


# ── build_summary_context ────────────────────────────────────


def build_summary_context(ctx: SummaryContext) -> dict[str, Any]:
    """组装 LLM 上下文：modules 数据 + prompt 指令。

    Returns:
        dict with keys: "modules", "connections", "prompt"
    """
    modules_data: list[dict[str, Any]] = []
    module_graph = ctx.dep_graph.get_module_graph()

    pr_by_file: dict[str, Any] = {}
    for pr in ctx.parse_results:
        pr_by_file[pr.file_path] = pr

    for mg in ctx.modules:
        if mg.is_special:
            continue

        func_list: list[dict[str, Any]] = []
        for file_path in mg.files:
            pr = pr_by_file.get(file_path)
            if pr is None:
                continue
            for fi in pr.functions:
                func_list.append({
                    "code_name": fi.name,
                    "params": list(fi.params),
                    "return_type": fi.return_type,
                    "file_path": file_path,
                    "line_start": fi.line_start,
                    "docstring": fi.docstring,
                })

        depends_on: list[str] = []
        if module_graph.has_node(mg.name):
            depends_on = list(module_graph.successors(mg.name))

        modules_data.append({
            "name": mg.name,
            "dir_path": mg.dir_path,
            "total_lines": mg.total_lines,
            "file_count": len(mg.files),
            "functions": func_list,
            "depends_on": depends_on,
        })

    connections_data: list[dict[str, Any]] = []
    non_special_names = {mg.name for mg in ctx.modules if not mg.is_special}
    for u, v, data in module_graph.edges(data=True):
        if u in non_special_names and v in non_special_names:
            connections_data.append({
                "from": u,
                "to": v,
                "call_count": data.get("call_count", 1),
            })

    prompt = _build_llm_prompt(modules_data, connections_data)

    return {
        "modules": modules_data,
        "connections": connections_data,
        "prompt": prompt,
    }


def _build_llm_prompt(
    modules: list[dict[str, Any]],
    connections: list[dict[str, Any]],
) -> str:
    """构建发送给 LLM 的中文指令 prompt。"""
    module_list = "\n".join(
        f"  - {m['name']}（{m['dir_path']}，{m['total_lines']} 行，"
        f"{len(m['functions'])} 个函数，依赖：{m['depends_on']}）"
        for m in modules
    )
    conn_list = "\n".join(
        f"  - {c['from']} → {c['to']}（{c['call_count']} 次调用）"
        for c in connections
    )

    return (
        "你是一个软件架构分析助手。请根据以下代码结构信息，为每个模块和函数生成中文业务描述。\n"
        "\n"
        "## 模块列表\n"
        f"{module_list}\n"
        "\n"
        "## 模块间连接\n"
        f"{conn_list if conn_list else '（无跨模块连接）'}\n"
        "\n"
        "## 输出要求\n"
        "请返回一个 JSON 对象，包含以下字段：\n"
        "- project_name: 项目名称\n"
        "- project_description: 一句话项目描述（中文）\n"
        "- modules: 模块数组，每个模块包含：\n"
        "  - code_path: 目录路径\n"
        "  - business_name: 中文业务名称（如「认证系统」「数据库」）\n"
        "  - description: 一句话中文描述\n"
        "  - health: 健康度（green/yellow/red）\n"
        "  - functions: 函数数组，每个函数包含：\n"
        "    - code_name: 函数名\n"
        "    - business_name: 中文业务名称\n"
        "    - explanation: 中文功能说明\n"
        "    - file_path, line_start, params, return_type\n"
        "  - depends_on: 依赖的模块名列表\n"
        "  - used_by: 被依赖的模块名列表\n"
        "- connections: 连接数组，每个连接包含：\n"
        "  - from, to, verb（中文动词）, call_count\n"
    )


# ── parse_llm_response ───────────────────────────────────────


def parse_llm_response(response: dict, ctx: SummaryContext) -> BlueprintSummary:
    """解析 LLM 返回的 dict，构建 BlueprintSummary。

    如果解析失败（类型错误、缺失字段等），自动降级到 build_fallback_summary。
    """
    try:
        if not isinstance(response, dict):
            raise ValueError("response is not a dict")

        project_name = response["project_name"]
        project_description = response["project_description"]

        modules: list[ModuleSummary] = []
        for mod_data in response["modules"]:
            functions: list[FunctionSummary] = []
            for fn_data in mod_data.get("functions", []):
                functions.append(
                    FunctionSummary(
                        code_name=fn_data["code_name"],
                        business_name=fn_data["business_name"],
                        explanation=fn_data["explanation"],
                        file_path=fn_data["file_path"],
                        line_start=fn_data["line_start"],
                        params=fn_data.get("params", []),
                        return_type=fn_data.get("return_type"),
                    )
                )
            modules.append(
                ModuleSummary(
                    code_path=mod_data["code_path"],
                    business_name=mod_data["business_name"],
                    description=mod_data["description"],
                    health=mod_data.get("health", "green"),
                    functions=functions,
                    depends_on=mod_data.get("depends_on", []),
                    used_by=mod_data.get("used_by", []),
                )
            )

        connections: list[ConnectionSummary] = []
        for conn_data in response.get("connections", []):
            connections.append(
                ConnectionSummary(
                    from_module=conn_data.get("from", conn_data.get("from_module", "")),
                    to_module=conn_data.get("to", conn_data.get("to_module", "")),
                    verb=conn_data["verb"],
                    call_count=conn_data.get("call_count", 0),
                )
            )

        return BlueprintSummary(
            project_name=project_name,
            project_description=project_description,
            modules=modules,
            connections=connections,
        )

    except Exception:
        logger.warning("llm_response_parse_failed", exc_info=True)
        return build_fallback_summary(ctx)
