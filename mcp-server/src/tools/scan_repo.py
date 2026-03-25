"""scan_repo — 蓝图能力：扫描项目源代码，输出模块总览和依赖图。

完整流程:
1. repo_cloner.clone_repo(repo_url)
2. ast_parser.parse_all(files)
3. module_grouper.group_modules(parse_results)
4. dependency_graph.build(parse_results)
5. summarizer.generate_project_overview(ctx)
6. dependency_graph.to_mermaid(level='module')

错误处理:
- clone 失败 → 友好提示检查地址和网络
- 解析失败 → 提示文件编码或语言不支持
- 超时 → 提示仓库可能过大
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from pathlib import Path
from typing import Any, Optional

import structlog

from src.memory.project_memory import ProjectMemory
from src.parsers.ast_parser import ParseResult, parse_all
from src.parsers.dependency_graph import DependencyGraph
from src.parsers.module_grouper import (
    ModuleGroup,
    build_node_module_map,
    group_modules,
)
from src.parsers.repo_cloner import CloneResult, clone_repo as _clone
from src.summarizer.engine import (
    SummaryContext,
    generate_local_blueprint,
    generate_local_chapter,
)
from src.tools._repo_cache import repo_cache

logger = structlog.get_logger()

# ── 常量 ─────────────────────────────────────────────────

# 各步骤的超时秒数
_CLONE_TIMEOUT = 180
_PARSE_TIMEOUT = 120
_GROUP_TIMEOUT = 30
_GRAPH_TIMEOUT = 30
_SUMMARY_TIMEOUT = 30
_CHAPTER_TIMEOUT = 60


# ── 辅助函数 ─────────────────────────────────────────────


def _health_from_lines(total_lines: int) -> str:
    """根据模块行数推断健康度。

    > 3000 行 → red（过度膨胀，建议拆分）
    > 1000 行 → yellow（需要关注）
    其余 → green
    """
    if total_lines > 3000:
        return "red"
    if total_lines > 1000:
        return "yellow"
    return "green"


def _role_badge(role: str) -> str:
    """根据角色生成角色标签。"""
    from src.summarizer.engine import _normalize_role

    normalized_role = _normalize_role(role)
    badges = {
        "dev": "开发者视角：关注代码逻辑、性能瓶颈、边界条件",
        "pm": "PM 视角：关注功能完整性、变更影响、风险识别",
        "domain_expert": "行业专家视角：关注业务规则验证、合规检查、风险识别",
    }
    return badges.get(normalized_role, f"{normalized_role} 视角")


def _build_project_overview(
    clone_result: CloneResult,
    modules: list[ModuleGroup],
    dep_graph: DependencyGraph,
    parse_results: list[ParseResult],
    role: str,
) -> str:
    """构建丰富的项目概览文本（L3+L4 级别）。

    不依赖 LLM，纯粹从解析数据中提取。
    """
    langs = clone_result.languages
    if not langs:
        return "该项目未检测到已知编程语言的源代码文件。"

    # 主语言和辅助语言
    sorted_langs = sorted(langs.items(), key=lambda x: x[1], reverse=True)
    primary_lang, primary_count = sorted_langs[0]
    total_code_files = sum(v for v in langs.values())

    lang_breakdown = "、".join(
        f"{lang}({count} 文件)" for lang, count in sorted_langs[:4]
    )

    # 业务模块 vs 特殊模块
    biz_modules = [m for m in modules if not m.is_special]
    special_modules = [m for m in modules if m.is_special]

    # 架构特征推断
    arch_hints = _infer_architecture(clone_result, parse_results, biz_modules)

    # 模块级依赖密度
    mg = dep_graph.get_module_graph()
    edge_count = mg.number_of_edges()
    node_count = mg.number_of_nodes()
    coupling = "低耦合" if node_count > 0 and edge_count / max(node_count, 1) < 1.5 else "中等耦合"

    # 角色化描述
    role_intro = {
        "ceo": "从商业视角看，",
        "pm": "从产品视角看，",
        "investor": "从技术投资视角看，",
        "qa": "从质量保障视角看，",
    }.get(role, "")

    overview = (
        f"{role_intro}该项目是一个以 {primary_lang} 为主的应用，"
        f"包含 {len(clone_result.files)} 个文件（{clone_result.total_lines} 行代码），"
        f"语言分布: {lang_breakdown}。\n\n"
        f"项目分为 {len(biz_modules)} 个业务模块"
    )

    if special_modules:
        special_names = "、".join(m.name for m in special_modules)
        overview += f"和 {len(special_modules)} 个辅助模块（{special_names}）"

    overview += f"，模块间{coupling}（{edge_count} 条依赖关系）。"

    if arch_hints:
        overview += f"\n\n架构特征: {'; '.join(arch_hints)}。"

    # 最大模块警告
    if biz_modules:
        largest = max(biz_modules, key=lambda m: m.total_lines)
        health = _health_from_lines(largest.total_lines)
        if health in ("yellow", "red"):
            status_text = "需要关注" if health == "yellow" else "建议拆分"
            overview += (
                f"\n\n注意: 模块「{largest.name}」有 {largest.total_lines} 行代码，"
                f"{status_text}。"
            )

    return overview


def _infer_architecture(
    clone_result: CloneResult,
    parse_results: list[ParseResult],
    biz_modules: list[ModuleGroup],
) -> list[str]:
    """从文件结构和代码特征推断架构模式。"""
    hints: list[str] = []

    all_files = {f.path.lower() for f in clone_result.files}
    all_dirs = set()
    for f in clone_result.files:
        parts = f.path.split("/")
        for i in range(1, len(parts)):
            all_dirs.add("/".join(parts[:i]).lower())

    # Web 框架检测
    has_routes = any("route" in d or "router" in d or "api" in d for d in all_dirs)
    has_models = any("model" in d for d in all_dirs)
    has_views = any("view" in d or "template" in d or "component" in d for d in all_dirs)
    has_controllers = any("controller" in d or "handler" in d for d in all_dirs)

    if has_routes and has_models and (has_views or has_controllers):
        hints.append("MVC/分层架构")
    elif has_routes and has_models:
        hints.append("REST API 架构")

    # 前端框架
    has_components = any("component" in d for d in all_dirs)
    has_pages = any("page" in d for d in all_dirs)
    if has_components:
        hints.append("组件化前端")
    if has_pages:
        hints.append("页面路由架构")

    # 数据库 / ORM
    has_migration = any("migration" in d or "alembic" in d for d in all_dirs)
    if has_migration:
        hints.append("有数据库迁移管理")

    # Docker
    has_docker = any("dockerfile" in f or "docker-compose" in f for f in all_files)
    if has_docker:
        hints.append("Docker 容器化部署")

    # 测试
    has_tests = any("test" in d or "spec" in d or "e2e" in d for d in all_dirs)
    if has_tests:
        hints.append("有自动化测试")

    return hints


def _enhance_modules(
    blueprint_modules: list[dict[str, Any]],
    modules: list[ModuleGroup],
    parse_results: list[ParseResult],
    role: str,
) -> list[dict[str, Any]]:
    """将 blueprint 的模块数据增强为完整的卡片格式。"""
    # 构建 name → ModuleGroup 查找表
    mod_lookup: dict[str, ModuleGroup] = {m.name: m for m in modules}

    enhanced = []
    for mod_data in blueprint_modules:
        name = mod_data["name"]
        mg_obj = mod_lookup.get(name)

        # 收集代码引用（最多 5 个关键函数）
        source_refs = _collect_source_refs(mg_obj, parse_results) if mg_obj else []

        # 构建 node_body：比 responsibility 更丰富
        node_body = _build_node_body(mod_data, mg_obj)

        enhanced.append({
            "name": name,
            "node_title": mod_data.get("responsibility", name),
            "node_body": node_body,
            "inputs": mod_data.get("entry_points", []),
            "outputs": mod_data.get("used_by", []),
            "health": _health_from_lines(mg_obj.total_lines if mg_obj else 0),
            "role_badge": _role_badge(role),
            "source_refs": source_refs,
            "paths": mod_data.get("paths", []),
            "depends_on": mod_data.get("depends_on", []),
            "used_by": mod_data.get("used_by", []),
            "pm_note": mod_data.get("pm_note", ""),
        })

    return enhanced


def _collect_source_refs(
    mg_obj: ModuleGroup,
    parse_results: list[ParseResult],
    max_refs: int = 5,
) -> list[str]:
    """收集模块中关键函数的 file:L-L 引用。"""
    source_refs: list[str] = []
    module_files = set(mg_obj.files)

    for pr in parse_results:
        if pr.file_path not in module_files:
            continue
        for func in pr.functions:
            if func.name.startswith("_"):
                continue  # 跳过私有函数
            source_refs.append(
                f"{pr.file_path}:L{func.line_start}-L{func.line_end}"
            )
            if len(source_refs) >= max_refs:
                return source_refs

    return source_refs


def _build_node_body(
    mod_data: dict[str, Any],
    mg_obj: ModuleGroup | None,
) -> str:
    """构建模块描述文本。"""
    parts = []

    responsibility = mod_data.get("responsibility", "")
    if responsibility:
        parts.append(responsibility)

    if mg_obj:
        # 入口函数信息
        if mg_obj.entry_functions:
            entries = ", ".join(mg_obj.entry_functions[:3])
            parts.append(f"入口: {entries}")

        # 公开接口信息
        if mg_obj.public_interfaces:
            apis = ", ".join(mg_obj.public_interfaces[:3])
            remaining = len(mg_obj.public_interfaces) - 3
            suffix = f" 等 {len(mg_obj.public_interfaces)} 个" if remaining > 0 else ""
            parts.append(f"对外接口: {apis}{suffix}")

    return "。".join(parts) if parts else mod_data.get("responsibility", "")


def _build_connections(
    dep_graph: DependencyGraph,
) -> list[dict[str, str]]:
    """从模块级依赖图构建 connections 列表。"""
    mg = dep_graph.get_module_graph()
    connections: list[dict[str, str]] = []

    for u, v, data in mg.edges(data=True):
        count = data.get("call_count", 1)
        connections.append({
            "from": u,
            "to": v,
            "label": f"调用 {count} 次",
            "strength": "strong" if count >= 5 else "weak",
        })

    return connections


def _make_error(error: str, hint: str = "", **extra: Any) -> dict[str, Any]:
    """构建统一的错误返回结构。"""
    result: dict[str, Any] = {
        "status": "error",
        "error": error,
    }
    if hint:
        result["hint"] = hint
    result.update(extra)
    return result


# ── 主入口 ───────────────────────────────────────────────


async def scan_repo(
    repo_url: str,
    role: str = "pm",
    depth: str = "overview",
) -> dict[str, Any]:
    """扫描项目仓库，生成蓝图和模块卡片。

    完整流程:
    1. repo_cloner.clone_repo(repo_url)
    2. ast_parser.parse_all(files)
    3. module_grouper.group_modules(parse_results)
    4. dependency_graph.build(parse_results)
    5. 生成项目概览 + 模块增强数据
    6. dependency_graph.to_mermaid(level='module')

    Args:
        repo_url: Git 仓库地址（HTTPS）或本地目录路径。
        role: 目标角色，决定输出的语言风格。可选: ceo, pm, investor, qa。
        depth: 扫描深度。overview = 只生成蓝图总览；detailed = 同时生成所有模块卡片。

    Returns:
        包含 project_overview、modules、connections、mermaid_diagram、stats 的字典。

        depth='overview': 只生成 L3+L4，跳过章节详情
        depth='detailed': 同时预生成所有模块的 read_chapter 内容
    """
    total_start = time.time()
    step_times: dict[str, float] = {}

    # ── Step 1: Clone / Scan ─────────────────────────────
    step_start = time.time()
    logger.info("scan_repo.step1_clone.start", url=repo_url)

    try:
        clone_result: CloneResult = await asyncio.wait_for(
            _clone(repo_url),
            timeout=_CLONE_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.error("scan_repo.clone_timeout", url=repo_url, timeout=_CLONE_TIMEOUT)
        return _make_error(
            error=f"克隆仓库超时（{_CLONE_TIMEOUT} 秒）",
            hint="仓库可能过大或网络较慢。可尝试克隆到本地后传入本地路径。",
        )
    except Exception as e:
        logger.error("scan_repo.clone_failed", url=repo_url, error=str(e))
        return _make_error(
            error=f"克隆仓库失败：{e}",
            hint="请检查仓库地址是否正确，或者网络是否可用。"
            "如果是私有仓库，请确保已配置 SSH key 或 HTTPS token。",
        )

    step_times["clone"] = round(time.time() - step_start, 2)
    logger.info(
        "scan_repo.step1_clone.done",
        files=len(clone_result.files),
        languages=clone_result.languages,
        seconds=step_times["clone"],
    )

    # 过滤出代码文件
    code_files = [f for f in clone_result.files if not f.is_config]
    if not code_files:
        return _make_error(
            error="未找到任何代码文件",
            hint=(
                "仓库中没有可识别的源代码文件（.py/.ts/.js/.java/.go/.rs/.cpp 等）。"
                "请确认仓库地址指向包含源代码的项目。"
            ),
        )

    # ── Step 2: Parse ────────────────────────────────────
    step_start = time.time()
    logger.info("scan_repo.step2_parse.start", files=len(code_files))

    try:
        parse_results: list[ParseResult] = await asyncio.wait_for(
            parse_all(code_files),
            timeout=_PARSE_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.error(
            "scan_repo.parse_timeout", files=len(code_files), timeout=_PARSE_TIMEOUT,
        )
        return _make_error(
            error=f"代码解析超时（{_PARSE_TIMEOUT} 秒，{len(code_files)} 个文件）",
            hint="项目文件过多导致解析超时。可尝试只扫描核心目录。",
        )
    except Exception as e:
        logger.error("scan_repo.parse_failed", error=str(e))
        return _make_error(
            error=f"代码解析失败：{e}",
            hint="解析过程中出错。可能是文件编码问题或不支持的语言。",
        )

    total_funcs = sum(len(r.functions) for r in parse_results)
    total_classes = sum(len(r.classes) for r in parse_results)
    total_imports = sum(len(r.imports) for r in parse_results)
    total_calls = sum(len(r.calls) for r in parse_results)

    # M1: 解析质量统计
    parse_quality = {
        "native": sum(1 for r in parse_results if r.parse_method == "native"),
        "full": sum(1 for r in parse_results if r.parse_method == "full"),
        "partial": sum(1 for r in parse_results if r.parse_method == "partial"),
        "basic": sum(1 for r in parse_results if r.parse_method == "basic"),
        "failed": sum(1 for r in parse_results if r.parse_method == "failed"),
    }
    avg_confidence = (
        sum(r.parse_confidence for r in parse_results) / len(parse_results)
        if parse_results else 1.0
    )

    step_times["parse"] = round(time.time() - step_start, 2)
    logger.info(
        "scan_repo.step2_parse.done",
        parsed=len(parse_results),
        functions=total_funcs,
        classes=total_classes,
        imports=total_imports,
        calls=total_calls,
        parse_quality=parse_quality,
        seconds=step_times["parse"],
    )

    # ── Step 3: Module Grouping ──────────────────────────
    step_start = time.time()
    logger.info("scan_repo.step3_group.start")

    try:
        modules: list[ModuleGroup] = await asyncio.wait_for(
            group_modules(parse_results, clone_result.repo_path),
            timeout=_GROUP_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.error("scan_repo.group_timeout", timeout=_GROUP_TIMEOUT)
        return _make_error(
            error=f"模块分组超时（{_GROUP_TIMEOUT} 秒）",
            hint="项目结构过于复杂，分组耗时过长。",
        )
    except Exception as e:
        logger.error("scan_repo.group_failed", error=str(e))
        return _make_error(error=f"模块分组失败：{e}")

    step_times["group"] = round(time.time() - step_start, 2)
    biz_modules = [m for m in modules if not m.is_special]
    special_modules = [m for m in modules if m.is_special]
    logger.info(
        "scan_repo.step3_group.done",
        business_modules=len(biz_modules),
        special_modules=len(special_modules),
        seconds=step_times["group"],
    )

    # ── Step 4: Dependency Graph ─────────────────────────
    step_start = time.time()
    logger.info("scan_repo.step4_graph.start")

    try:
        dep_graph = DependencyGraph()
        dep_graph.build(parse_results)
        node_map = build_node_module_map(modules, parse_results)
        dep_graph.set_module_groups(node_map)
    except Exception as e:
        logger.error("scan_repo.graph_failed", error=str(e))
        return _make_error(
            error=f"依赖图构建失败：{e}",
            hint="构建代码依赖关系时出错，可能是项目结构不规范。",
        )

    step_times["graph"] = round(time.time() - step_start, 2)
    logger.info(
        "scan_repo.step4_graph.done",
        nodes=dep_graph.graph.number_of_nodes(),
        edges=dep_graph.graph.number_of_edges(),
        module_nodes=dep_graph.get_module_graph().number_of_nodes(),
        module_edges=dep_graph.get_module_graph().number_of_edges(),
        seconds=step_times["graph"],
    )

    # ── Step 5: Generate Blueprint ───────────────────────
    step_start = time.time()
    logger.info("scan_repo.step5_summary.start", role=role)

    ctx = SummaryContext(
        clone_result=clone_result,
        parse_results=parse_results,
        modules=modules,
        dep_graph=dep_graph,
        role=role,
        repo_url=repo_url,
    )

    # 缓存 context 供 read_chapter / diagnose / ask_about 使用
    repo_cache.store(repo_url, ctx)

    # 生成蓝图数据（基于解析结果，不调用 LLM）
    blueprint = generate_local_blueprint(ctx)

    # 生成丰富的项目概览
    project_overview = _build_project_overview(
        clone_result=clone_result,
        modules=modules,
        dep_graph=dep_graph,
        parse_results=parse_results,
        role=role,
    )

    step_times["summary"] = round(time.time() - step_start, 2)
    logger.info("scan_repo.step5_summary.done", seconds=step_times["summary"])

    # ── Step 6: 增强模块数据 + Connections + Mermaid ─────
    step_start = time.time()

    enhanced_modules = _enhance_modules(
        blueprint_modules=blueprint["modules"],
        modules=modules,
        parse_results=parse_results,
        role=role,
    )

    connections = _build_connections(dep_graph)
    mermaid = dep_graph.to_mermaid(level="module")

    step_times["enhance"] = round(time.time() - step_start, 2)
    logger.info(
        "scan_repo.step6_enhance.done",
        modules=len(enhanced_modules),
        connections=len(connections),
        seconds=step_times["enhance"],
    )

    # ── depth=detailed: 预生成所有模块卡片 ───────────────
    chapters: dict[str, dict] | None = None
    if depth == "detailed":
        step_start = time.time()
        logger.info("scan_repo.detailed_chapters.start", modules=len(biz_modules))

        chapters = {}
        for m in biz_modules:
            try:
                chapter = generate_local_chapter(ctx, m.name)
                if chapter.get("status") == "ok":
                    chapters[m.name] = chapter
            except Exception as e:
                logger.warning(
                    "scan_repo.chapter_failed",
                    module=m.name,
                    error=str(e),
                )

        step_times["chapters"] = round(time.time() - step_start, 2)
        logger.info(
            "scan_repo.detailed_chapters.done",
            count=len(chapters),
            seconds=step_times["chapters"],
        )

    # ── 组装最终结果 ──────────────────────────────────────
    total_time = round(time.time() - total_start, 2)
    logger.info("scan_repo.done", total_seconds=total_time)

    result: dict[str, Any] = {
        "status": "ok",
        "repo_url": repo_url,
        "role": role,
        "depth": depth,
        "project_overview": project_overview,
        "modules": enhanced_modules,
        "connections": connections,
        "mermaid_diagram": mermaid,
        "stats": {
            "files": len(clone_result.files),
            "code_files": len(code_files),
            "modules": len(enhanced_modules),
            "functions": total_funcs,
            "classes": total_classes,
            "imports": total_imports,
            "calls": total_calls,
            "total_lines": clone_result.total_lines,
            "languages": clone_result.languages,
            "scan_time_seconds": total_time,
            "step_times": step_times,
            "parse_quality": parse_quality,
            "avg_parse_confidence": round(avg_confidence, 2),
        },
    }

    if chapters is not None:
        result["chapters"] = chapters

    # M1: 降级提示
    partial_ratio = (
        (parse_quality["partial"] + parse_quality["basic"]) / len(parse_results)
        if parse_results else 0
    )
    if partial_ratio > 0:
        warnings = []
        if parse_quality["partial"] > 0 or parse_quality["basic"] > 0:
            warnings.append(
                f"{parse_quality['partial'] + parse_quality['basic']}/{len(parse_results)} "
                f"个文件使用了简化解析（正则 fallback），结构数据可能不完整。"
            )
        if parse_quality["failed"] > 0:
            warnings.append(
                f"{parse_quality['failed']} 个文件解析失败。"
            )
        if partial_ratio > 0.5:
            warnings.insert(0,
                "⚠️ 超过半数文件使用简化解析，依赖图和影响分析的准确性可能受限。"
            )
        result["parse_warnings"] = warnings

    return result
