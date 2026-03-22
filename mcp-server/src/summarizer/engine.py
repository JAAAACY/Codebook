"""summarizer.engine — 模块卡片生成引擎。

读取 prompts/summary/ 下的 Prompt 模板，填充变量后调用 LLM 生成
项目概览（L1）、模块地图（L2）、模块卡片（L3）和代码细节（L4）。
"""

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

import structlog

from src.config import settings
from src.parsers.ast_parser import ParseResult
from src.parsers.dependency_graph import DependencyGraph
from src.parsers.module_grouper import ModuleGroup
from src.parsers.repo_cloner import CloneResult

logger = structlog.get_logger()

# ── Prompt 模板路径 ──────────────────────────────────────

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "prompts" / "summary"
CONFIG_PATH = Path(__file__).resolve().parent.parent.parent.parent / "prompts" / "codebook_config_v0.2.json"


# ── 数据类 ──────────────────────────────────────────────

@dataclass
class SummaryContext:
    """生成摘要所需的完整上下文。"""
    clone_result: CloneResult
    parse_results: list[ParseResult]
    modules: list[ModuleGroup]
    dep_graph: DependencyGraph
    role: str = "pm"


@dataclass
class ProjectOverview:
    """L1 项目概览。"""
    project_summary: str = ""


@dataclass
class ModuleMapItem:
    """L2 模块地图中的一个模块。"""
    name: str = ""
    paths: list[str] = field(default_factory=list)
    responsibility: str = ""
    entry_points: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    used_by: list[str] = field(default_factory=list)
    pm_note: str = ""


@dataclass
class ModuleMap:
    """L2 模块总览地图。"""
    modules: list[ModuleMapItem] = field(default_factory=list)
    mermaid_diagram: str = ""


@dataclass
class ModuleCard:
    """L3 模块卡片。"""
    name: str = ""
    path: str = ""
    what: str = ""
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    branches: list[dict] = field(default_factory=list)
    side_effects: list[str] = field(default_factory=list)
    blast_radius: list[str] = field(default_factory=list)
    key_code_refs: list[str] = field(default_factory=list)
    pm_note: str = ""


@dataclass
class ModuleChapter:
    """read_chapter 的输出：一个模块的所有卡片 + 依赖图。"""
    module_name: str = ""
    cards: list[ModuleCard] = field(default_factory=list)
    dependency_graph: str = ""


# ── Prompt 加载 ──────────────────────────────────────────

def _load_prompt_template(level: str) -> dict:
    """加载指定级别的 Prompt 模板 JSON。"""
    filenames = {
        "L1": "L1_project_overview.json",
        "L2": "L2_module_map.json",
        "L3": "L3_module_card.json",
        "L4": "L4_code_detail.json",
    }
    filepath = PROMPTS_DIR / filenames[level]
    if not filepath.exists():
        raise FileNotFoundError(f"Prompt template not found: {filepath}")
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_codebook_config() -> dict:
    """加载 codebook_config_v0.2.json。"""
    if not CONFIG_PATH.exists():
        logger.warning("config.not_found", path=str(CONFIG_PATH))
        return {}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _get_banned_terms() -> str:
    """获取禁用术语表的文本形式。"""
    config = _load_codebook_config()
    banned = config.get("banned_terms_in_pm_fields", {}).get("terms", {})
    if not banned:
        return "（未配置禁用术语表）"
    lines = []
    for term, replacement in banned.items():
        lines.append(f"- 「{term}」→ {replacement}")
    return "\n".join(lines)


def _get_http_annotations() -> str:
    """获取 HTTP 状态码注释表。"""
    config = _load_codebook_config()
    codes = config.get("http_status_code_annotations", {}).get("codes", {})
    if not codes:
        return "（未配置状态码注释表）"
    lines = []
    for code, meaning in codes.items():
        lines.append(f"- {code}（{meaning}）")
    return "\n".join(lines)


# ── 上下文提取辅助 ───────────────────────────────────────

def _build_file_tree(clone_result: CloneResult, max_depth: int = 2) -> str:
    """从 CloneResult 构建目录树文本。"""
    dirs: set[str] = set()
    for f in clone_result.files:
        parts = Path(f.path).parts
        for i in range(1, min(len(parts), max_depth + 1)):
            dirs.add("/".join(parts[:i]))
    sorted_dirs = sorted(dirs)
    return "\n".join(sorted_dirs) if sorted_dirs else "(empty)"


def _get_entry_file_content(clone_result: CloneResult, max_lines: int = 100) -> str:
    """找到入口文件并返回其内容。"""
    entry_patterns = ["main.py", "app.py", "index.ts", "index.js", "server.py", "app/__init__.py"]
    for pattern in entry_patterns:
        for f in clone_result.files:
            if f.path.endswith(pattern):
                try:
                    with open(f.abs_path, "r", encoding="utf-8", errors="replace") as fh:
                        lines = fh.readlines()
                    return "".join(lines[:max_lines])
                except OSError:
                    continue
    return "(入口文件未找到)"


def _module_groups_to_text(modules: list[ModuleGroup]) -> str:
    """将模块分组转为文本摘要。"""
    lines = []
    for m in modules:
        special = " [特殊模块]" if m.is_special else ""
        lines.append(f"- {m.name}{special}: {len(m.files)} 文件, {m.total_lines} 行")
        if m.entry_functions:
            lines.append(f"  入口函数: {', '.join(m.entry_functions[:5])}")
        if m.public_interfaces:
            lines.append(f"  公开接口: {', '.join(m.public_interfaces[:5])}")
    return "\n".join(lines)


def _dependency_edges_to_text(dep_graph: DependencyGraph) -> str:
    """将模块级依赖边转为文本。"""
    mg = dep_graph.get_module_graph()
    lines = []
    for u, v, data in mg.edges(data=True):
        count = data.get("call_count", 1)
        strength = "强" if count >= 5 else "弱"
        lines.append(f"- {u} → {v} (调用 {count} 次, {strength}依赖)")
    return "\n".join(lines) if lines else "(无模块间依赖)"


def _module_functions_to_text(
    modules: list[ModuleGroup],
    parse_results: list[ParseResult],
) -> str:
    """列出每个模块的关键函数和类。"""
    # file -> module 映射
    file_to_module: dict[str, str] = {}
    for m in modules:
        for f in m.files:
            file_to_module[f] = m.name

    # 按模块收集
    module_symbols: dict[str, list[str]] = {}
    for pr in parse_results:
        mod = file_to_module.get(pr.file_path, "未分组")
        symbols = module_symbols.setdefault(mod, [])
        for cls in pr.classes:
            symbols.append(f"class {cls.name} ({pr.file_path}:L{cls.line_start})")
        for func in pr.functions:
            if not func.name.startswith("_") and not func.is_method:
                symbols.append(f"func {func.name}({', '.join(func.params[:3])}) ({pr.file_path}:L{func.line_start})")

    lines = []
    for mod_name, syms in sorted(module_symbols.items()):
        lines.append(f"\n### {mod_name}")
        for s in syms[:10]:
            lines.append(f"  - {s}")
        if len(syms) > 10:
            lines.append(f"  - ... (还有 {len(syms)-10} 个)")
    return "\n".join(lines)


def _get_module_source(module: ModuleGroup, max_lines_per_file: int = 200) -> str:
    """读取模块所有文件的源代码。"""
    parts = []
    for fpath in module.files[:15]:  # 限制文件数量
        # 需要从 abs_path 读取，但 ModuleGroup 只存相对路径
        # engine 调用时需要传入 repo_path
        parts.append(f"\n--- {fpath} ---\n(源代码需要在运行时从仓库读取)")
    return "\n".join(parts)


def _get_module_source_from_repo(
    module: ModuleGroup,
    repo_path: str,
    max_lines_per_file: int = 200,
) -> str:
    """从仓库目录读取模块所有文件的源代码。"""
    parts = []
    for fpath in module.files[:15]:
        abs_path = os.path.join(repo_path, fpath)
        try:
            with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            content = "".join(lines[:max_lines_per_file])
            if len(lines) > max_lines_per_file:
                content += f"\n... (省略 {len(lines) - max_lines_per_file} 行)"
            parts.append(f"\n--- {fpath} ---\n{content}")
        except OSError:
            parts.append(f"\n--- {fpath} ---\n(无法读取)")
    return "\n".join(parts)


def _parse_result_summary(
    module: ModuleGroup,
    parse_results: list[ParseResult],
) -> str:
    """生成模块的 ParseResult 摘要。"""
    module_files = set(module.files)
    relevant = [pr for pr in parse_results if pr.file_path in module_files]

    lines = []
    for pr in relevant:
        lines.append(f"\n文件: {pr.file_path}")
        if pr.classes:
            lines.append(f"  类: {', '.join(c.name for c in pr.classes)}")
        if pr.functions:
            func_names = [f"{f.name}({', '.join(f.params[:3])})" for f in pr.functions[:10]]
            lines.append(f"  函数: {', '.join(func_names)}")
        if pr.calls:
            call_summary = set(f"{c.caller_func}→{c.callee_name}" for c in pr.calls[:20])
            lines.append(f"  调用: {', '.join(list(call_summary)[:10])}")
    return "\n".join(lines)


def _get_upstream_downstream(
    module: ModuleGroup,
    dep_graph: DependencyGraph,
    modules: list[ModuleGroup],
) -> tuple[str, str]:
    """获取模块的上下游依赖文本。"""
    mg = dep_graph.get_module_graph()
    name = module.name

    upstream = []
    if name in mg:
        for pred in mg.predecessors(name):
            upstream.append(pred)

    downstream = []
    if name in mg:
        for succ in mg.successors(name):
            downstream.append(succ)

    up_text = ", ".join(upstream) if upstream else "(无上游依赖)"
    down_text = ", ".join(downstream) if downstream else "(无下游依赖)"
    return up_text, down_text


# ── Prompt 构建 ──────────────────────────────────────────

def _safe_format(template_str: str, **kwargs) -> str:
    """安全的模板替换，只替换已知变量，不碰其他花括号。"""
    result = template_str
    for key, value in kwargs.items():
        result = result.replace("{" + key + "}", str(value))
    return result


def build_l1_prompt(ctx: SummaryContext) -> tuple[str, str]:
    """构建 L1 项目概览的 system + user prompt。"""
    template = _load_prompt_template("L1")

    system = template["system_prompt"]
    user = _safe_format(
        template["user_prompt"],
        file_tree=_build_file_tree(ctx.clone_result),
        language_stats=json.dumps(ctx.clone_result.languages, ensure_ascii=False),
        entry_file_content=_get_entry_file_content(ctx.clone_result),
    )
    return system, user


def build_l2_prompt(ctx: SummaryContext, project_summary: str = "") -> tuple[str, str]:
    """构建 L2 模块总览的 system + user prompt。"""
    template = _load_prompt_template("L2")

    system = _safe_format(template["system_prompt"], banned_terms=_get_banned_terms())
    user = _safe_format(
        template["user_prompt"],
        project_summary=project_summary or "(待生成)",
        module_groups=_module_groups_to_text(ctx.modules),
        dependency_edges=_dependency_edges_to_text(ctx.dep_graph),
        module_functions=_module_functions_to_text(ctx.modules, ctx.parse_results),
    )
    return system, user


def build_l3_prompt(
    ctx: SummaryContext,
    module: ModuleGroup,
    repo_path: str,
) -> tuple[str, str]:
    """构建 L3 模块卡片的 system + user prompt。"""
    template = _load_prompt_template("L3")

    system = _safe_format(
        template["system_prompt"],
        http_status_annotations=_get_http_annotations(),
        banned_terms=_get_banned_terms(),
    )

    upstream, downstream = _get_upstream_downstream(module, ctx.dep_graph, ctx.modules)

    user = _safe_format(
        template["user_prompt"],
        module_name=module.name,
        module_info=json.dumps({
            "name": module.name,
            "dir_path": module.dir_path,
            "files": module.files,
            "entry_functions": module.entry_functions,
            "public_interfaces": module.public_interfaces,
            "total_lines": module.total_lines,
        }, ensure_ascii=False, indent=2),
        source_code=_get_module_source_from_repo(module, repo_path),
        parse_result=_parse_result_summary(module, ctx.parse_results),
        upstream=upstream,
        downstream=downstream,
    )
    return system, user


def build_l4_prompt(
    file_path: str,
    line_start: int,
    line_end: int,
    symbol_name: str,
    language: str,
    code_content: str,
    module_name: str,
    callers: list[str],
    callees: list[str],
) -> tuple[str, str]:
    """构建 L4 代码细节的 system + user prompt。"""
    template = _load_prompt_template("L4")

    system = template["system_prompt"]
    user = _safe_format(
        template["user_prompt"],
        file_path=file_path,
        line_start=str(line_start),
        line_end=str(line_end),
        symbol_name=symbol_name,
        language=language,
        code_content=code_content,
        module_name=module_name,
        callers=", ".join(callers) if callers else "(无调用方)",
        callees=", ".join(callees) if callees else "(无被调用函数)",
    )
    return system, user


# ── 主入口：基于代码解析结果生成本地摘要（不调用 LLM） ──

def generate_local_blueprint(ctx: SummaryContext) -> dict:
    """不调用 LLM，直接从解析结果生成蓝图数据。

    用于 placeholder 阶段或 LLM 不可用时，确保基本功能可用。

    Returns:
        与 scan_repo 工具返回格式一致的字典。
    """
    start_time = time.time()

    # 项目概览
    langs = ctx.clone_result.languages
    primary_lang = max(langs, key=langs.get) if langs else "unknown"
    project_summary = (
        f"该项目使用 {primary_lang} 语言，"
        f"包含 {len(ctx.clone_result.files)} 个文件、"
        f"{ctx.clone_result.total_lines} 行代码，"
        f"分为 {len([m for m in ctx.modules if not m.is_special])} 个业务模块。"
    )

    # 模块列表
    mg = ctx.dep_graph.get_module_graph()
    module_items = []
    for m in ctx.modules:
        if m.is_special:
            continue

        depends_on = list(mg.predecessors(m.name)) if m.name in mg else []
        used_by = list(mg.successors(m.name)) if m.name in mg else []

        module_items.append({
            "name": m.name,
            "paths": [m.dir_path],
            "responsibility": f"包含 {len(m.files)} 个文件、{m.total_lines} 行代码",
            "entry_points": m.entry_functions[:5],
            "depends_on": depends_on,
            "used_by": used_by,
            "pm_note": f"公开接口: {', '.join(m.public_interfaces[:3])}" if m.public_interfaces else "",
        })

    # Mermaid 图
    mermaid = ctx.dep_graph.to_mermaid(level="module")

    # 连接
    connections = []
    for u, v, data in mg.edges(data=True):
        connections.append({
            "from": u,
            "to": v,
            "label": "",
            "strength": "strong" if data.get("call_count", 1) >= 5 else "weak",
        })

    elapsed = time.time() - start_time

    return {
        "status": "ok",
        "project_overview": project_summary,
        "modules": module_items,
        "connections": connections,
        "mermaid_diagram": mermaid,
        "stats": {
            "files": len(ctx.clone_result.files),
            "modules": len(module_items),
            "functions": sum(len(pr.functions) for pr in ctx.parse_results),
            "scan_time_seconds": round(elapsed, 2),
        },
    }


def generate_local_chapter(
    ctx: SummaryContext,
    module_name: str,
) -> dict:
    """不调用 LLM，直接从解析结果生成模块卡片数据。

    Returns:
        与 read_chapter 工具返回格式一致的字典。
    """
    # 找到对应模块
    target = None
    for m in ctx.modules:
        if m.name == module_name:
            target = m
            break

    if target is None:
        return {
            "status": "error",
            "error": f"模块 '{module_name}' 不存在",
            "available_modules": [m.name for m in ctx.modules],
        }

    module_files = set(target.files)
    relevant_prs = [pr for pr in ctx.parse_results if pr.file_path in module_files]

    # 为每个文件生成简化卡片
    cards = []
    for pr in relevant_prs:
        if not pr.functions and not pr.classes:
            continue

        # 收集分支信息
        branches = []
        for func in pr.functions:
            branches.append({
                "condition": f"调用 {func.name}",
                "result": f"执行 {func.name} 逻辑",
                "code_ref": f"{pr.file_path}:L{func.line_start}",
            })

        cards.append({
            "name": pr.file_path.split("/")[-1].replace(".py", "").replace(".ts", ""),
            "path": pr.file_path,
            "what": f"包含 {len(pr.functions)} 个函数, {len(pr.classes)} 个类",
            "inputs": [f"来自 {imp.module}" for imp in pr.imports[:5] if imp.module],
            "outputs": [f.name for f in pr.functions if not f.name.startswith("_")][:5],
            "branches": branches[:5],
            "side_effects": [],
            "blast_radius": [],
            "key_code_refs": [
                f"{pr.file_path}:L{f.line_start}-L{f.line_end}"
                for f in pr.functions[:5]
            ],
            "pm_note": "",
        })

    # 局部依赖图
    dep_mermaid = ctx.dep_graph.to_mermaid(level="function")

    return {
        "status": "ok",
        "module_name": module_name,
        "module_cards": cards,
        "dependency_graph": dep_mermaid,
    }
