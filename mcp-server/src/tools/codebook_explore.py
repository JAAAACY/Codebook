"""codebook (explore) — 一键全链路编排工具。

将 scan_repo → read_chapter → diagnose 串联为一次自动化流水线。
支持三种输入：
1. repo_url — GitHub / Git 仓库链接
2. code_snippet — 粘贴的代码片段（降级模式）
3. query — 自然语言问题（结合上下文自动选择策略）

模块选择策略（混合驱动）：
- 有具体问题 → 问题驱动：用关键词匹配相关模块
- 无具体问题 → 拓扑驱动：按依赖入度选核心 hub 模块
"""

from __future__ import annotations

import time
from typing import Any, Optional

import structlog

from src.tools.scan_repo import scan_repo as _scan_repo
from src.tools.read_chapter import read_chapter as _read_chapter
from src.tools.diagnose import diagnose as _diagnose
from src.tools._repo_cache import repo_cache
from src.tools.blueprint_renderer import save_blueprint

logger = structlog.get_logger()

# ── 常量 ─────────────────────────────────────────────────

# 自动深入阅读的模块数上限
MAX_AUTO_CHAPTERS = 5
# 自动诊断的模块数上限
MAX_AUTO_DIAGNOSE = 3


# ── 模块选择策略 ─────────────────────────────────────────


def _select_modules_by_query(
    modules: list[dict[str, Any]],
    query: str,
) -> list[str]:
    """问题驱动：根据 query 关键词匹配最相关的模块。

    使用双层匹配：
    1. 结构化关键词匹配（英文 camelCase/snake_case 友好）
    2. 中文子串直接匹配（跳过分词，用 query 的子串扫描模块文本）
    """
    if not query.strip():
        return []

    from src.tools.diagnose import _extract_keywords
    import re as _re

    keywords = _extract_keywords(query)

    # 额外提取中文连续片段（2 字及以上），作为子串匹配源
    cn_words = _re.findall(r'[\u4e00-\u9fff]{2,}', query)
    # 同时生成 2-gram 子串，以提高模糊匹配率
    cn_fragments = list(cn_words)
    for word in cn_words:
        if len(word) > 2:
            for i in range(len(word) - 1):
                bigram = word[i:i+2]
                if bigram not in cn_fragments:
                    cn_fragments.append(bigram)

    if not keywords and not cn_fragments:
        return []

    scored: list[tuple[str, float]] = []
    for mod in modules:
        name = mod.get("name", "")
        body = mod.get("node_body", "")
        title = mod.get("node_title", "")
        searchable = f"{name} {body} {title}"
        searchable_lower = searchable.lower()

        score = 0.0

        # 1. 英文关键词匹配
        for kw in keywords:
            kw_lower = kw.lower()
            if kw_lower in name.lower():
                score += 3.0
            elif kw_lower in searchable_lower:
                score += 1.0

        # 2. 中文子串匹配
        for frag in cn_fragments:
            if frag in name:
                score += 4.0  # 中文命中模块名权重最高
            elif frag in searchable:
                score += 2.0

        # 3. 原始 query 整体子串匹配（宽松兜底）
        query_clean = query.strip().lower()
        if len(query_clean) >= 2:
            if query_clean in searchable_lower or any(
                part in searchable_lower
                for part in query_clean.split()
                if len(part) >= 2
            ):
                score += 0.5

        if score > 0:
            scored.append((name, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return [name for name, _ in scored[:MAX_AUTO_CHAPTERS]]


def _select_modules_by_topology(
    modules: list[dict[str, Any]],
    connections: list[dict[str, str]],
) -> list[str]:
    """拓扑驱动：选被依赖最多的 hub 模块。"""
    # 计算入度（被调用次数）
    in_degree: dict[str, int] = {}
    out_degree: dict[str, int] = {}
    for conn in connections:
        target = conn.get("to", "")
        source = conn.get("from", "")
        in_degree[target] = in_degree.get(target, 0) + 1
        out_degree[source] = out_degree.get(source, 0) + 1

    # 综合得分：入度 * 2 + 出度（hub 节点既被依赖又依赖别人）
    module_names = [m["name"] for m in modules]
    scored: list[tuple[str, float]] = []
    for name in module_names:
        score = in_degree.get(name, 0) * 2 + out_degree.get(name, 0)
        scored.append((name, score))

    scored.sort(key=lambda x: x[1], reverse=True)

    # 至少选 3 个，最多 MAX_AUTO_CHAPTERS 个
    selected = [name for name, score in scored[:MAX_AUTO_CHAPTERS] if score > 0]
    if len(selected) < 3 and len(module_names) >= 3:
        # 补齐到 3 个（按模块列表顺序）
        for name in module_names:
            if name not in selected:
                selected.append(name)
            if len(selected) >= 3:
                break

    return selected[:MAX_AUTO_CHAPTERS]


# ── 主入口 ───────────────────────────────────────────────


async def codebook_explore(
    repo_url: str = "",
    query: str = "",
    code_snippet: str = "",
    role: str = "pm",
) -> dict[str, Any]:
    """一键全链路探索：scan → read_chapter → diagnose。

    Args:
        repo_url: Git 仓库地址（HTTPS）。如果为空且有 code_snippet，走降级模式。
        query: 用户的自然语言问题或意图描述（可选）。
            有 query 时走问题驱动模块选择；无 query 时走拓扑驱动。
        code_snippet: 粘贴的代码片段（可选）。仅在无 repo_url 时使用。
        role: 目标角色。

    Returns:
        包含全链路结果的字典：scan_result, chapters, diagnosis, selected_modules,
        以及用于生成交互式报告的 report_data。
    """
    total_start = time.time()
    logger.info(
        "codebook_explore.start",
        has_url=bool(repo_url),
        has_query=bool(query),
        has_snippet=bool(code_snippet),
        role=role,
    )

    result: dict[str, Any] = {
        "status": "ok",
        "mode": "full",  # full | snippet_only
        "role": role,
        "phases": {},
    }

    # ── 降级模式：只有代码片段，没有 repo ──────────────────
    if not repo_url and code_snippet:
        result["mode"] = "snippet_only"
        result["snippet"] = code_snippet
        result["message"] = (
            "检测到代码片段但未提供仓库地址。"
            "建议提供完整的仓库链接以获得更全面的分析（架构图、模块关系、依赖追踪）。\n\n"
            "当前将使用大模型直接分析该代码片段。"
        )
        if query:
            result["query"] = query
        result["status"] = "snippet_only"
        logger.info("codebook_explore.snippet_mode")
        return result

    # ── 无输入：提示用户 ──────────────────────────────────
    if not repo_url and not code_snippet:
        return {
            "status": "need_input",
            "message": (
                "欢迎使用 CodeBook！请提供以下任意一项：\n"
                "1. Git 仓库链接（如 https://github.com/user/repo）— 获得完整分析\n"
                "2. 代码片段 — 获得快速解读\n\n"
                "您也可以附带问题，例如「登录超时的原因是什么？」，"
                "CodeBook 会自动聚焦到相关模块。"
            ),
        }

    # ══════════════════════════════════════════════════════
    # Phase 1: scan_repo
    # ══════════════════════════════════════════════════════
    phase1_start = time.time()
    logger.info("codebook_explore.phase1_scan.start", url=repo_url)

    scan_result = await _scan_repo(repo_url=repo_url, role=role, depth="overview")

    if scan_result.get("status") != "ok":
        result["status"] = "error"
        result["phases"]["scan"] = scan_result
        result["error"] = scan_result.get("error", "扫描失败")
        return result

    result["phases"]["scan"] = {
        "status": "ok",
        "project_overview": scan_result.get("project_overview", ""),
        "modules": scan_result.get("modules", []),
        "connections": scan_result.get("connections", []),
        "mermaid_diagram": scan_result.get("mermaid_diagram", ""),
        "stats": scan_result.get("stats", {}),
        "parse_warnings": scan_result.get("parse_warnings", []),
        "time_seconds": round(time.time() - phase1_start, 2),
    }

    modules = scan_result.get("modules", [])
    connections = scan_result.get("connections", [])

    logger.info(
        "codebook_explore.phase1_scan.done",
        modules=len(modules),
        seconds=result["phases"]["scan"]["time_seconds"],
    )

    # ══════════════════════════════════════════════════════
    # 模块选择（混合驱动）
    # ══════════════════════════════════════════════════════
    if query:
        selected_modules = _select_modules_by_query(modules, query)
        selection_strategy = "query_driven"
        if not selected_modules:
            # 关键词没匹配到任何模块，降级到拓扑驱动
            selected_modules = _select_modules_by_topology(modules, connections)
            selection_strategy = "topology_fallback"
    else:
        selected_modules = _select_modules_by_topology(modules, connections)
        selection_strategy = "topology_driven"

    result["selected_modules"] = selected_modules
    result["selection_strategy"] = selection_strategy

    logger.info(
        "codebook_explore.module_selection",
        strategy=selection_strategy,
        selected=selected_modules,
    )

    # ══════════════════════════════════════════════════════
    # Phase 2: read_chapter (批量)
    # ══════════════════════════════════════════════════════
    phase2_start = time.time()
    logger.info(
        "codebook_explore.phase2_chapters.start",
        modules=selected_modules,
    )

    chapters: dict[str, dict] = {}
    for mod_name in selected_modules:
        try:
            chapter = await _read_chapter(module_name=mod_name, role=role)
            if chapter.get("status") == "ok":
                chapters[mod_name] = chapter
            else:
                logger.warning(
                    "codebook_explore.chapter_failed",
                    module=mod_name,
                    error=chapter.get("error", "unknown"),
                )
        except Exception as e:
            logger.warning(
                "codebook_explore.chapter_exception",
                module=mod_name,
                error=str(e),
            )

    result["phases"]["chapters"] = {
        "status": "ok",
        "count": len(chapters),
        "modules": list(chapters.keys()),
        "data": chapters,
        "time_seconds": round(time.time() - phase2_start, 2),
    }

    logger.info(
        "codebook_explore.phase2_chapters.done",
        count=len(chapters),
        seconds=result["phases"]["chapters"]["time_seconds"],
    )

    # ══════════════════════════════════════════════════════
    # Phase 3: diagnose
    # ══════════════════════════════════════════════════════
    phase3_start = time.time()

    diagnose_results: dict[str, dict] = {}

    if query:
        # 有具体问题：对选中的模块逐个诊断
        logger.info("codebook_explore.phase3_diagnose.start", mode="targeted")
        diagnose_targets = selected_modules[:MAX_AUTO_DIAGNOSE]

        for mod_name in diagnose_targets:
            try:
                diag = await _diagnose(
                    module_name=mod_name,
                    role=role,
                    query=query,
                )
                diagnose_results[mod_name] = diag
            except Exception as e:
                logger.warning(
                    "codebook_explore.diagnose_exception",
                    module=mod_name,
                    error=str(e),
                )
    else:
        # 无具体问题：对整个项目做一次健康概览
        logger.info("codebook_explore.phase3_diagnose.start", mode="health_overview")
        try:
            diag = await _diagnose(
                module_name="all",
                role=role,
                query="项目的关键入口点、核心调用路径和潜在风险点",
            )
            diagnose_results["_project_health"] = diag
        except Exception as e:
            logger.warning(
                "codebook_explore.diagnose_health_exception",
                error=str(e),
            )

    result["phases"]["diagnose"] = {
        "status": "ok",
        "count": len(diagnose_results),
        "data": diagnose_results,
        "time_seconds": round(time.time() - phase3_start, 2),
    }

    logger.info(
        "codebook_explore.phase3_diagnose.done",
        count=len(diagnose_results),
        seconds=result["phases"]["diagnose"]["time_seconds"],
    )

    # ══════════════════════════════════════════════════════
    # 组装报告数据（供前端渲染）
    # ══════════════════════════════════════════════════════
    result["report_data"] = _build_report_data(
        scan=result["phases"]["scan"],
        chapters=chapters,
        diagnoses=diagnose_results,
        selected_modules=selected_modules,
        selection_strategy=selection_strategy,
        query=query,
        role=role,
    )

    total_time = round(time.time() - total_start, 2)
    result["total_time_seconds"] = total_time

    # ══════════════════════════════════════════════════════
    # 自动生成 HTML 蓝图文件
    # ══════════════════════════════════════════════════════
    try:
        blueprint_path = save_blueprint(
            report_data=result["report_data"],
            repo_url=repo_url,
            total_time=total_time,
        )
        result["blueprint_path"] = blueprint_path
        logger.info("codebook_explore.blueprint_saved", path=blueprint_path)
    except Exception as e:
        logger.warning("codebook_explore.blueprint_save_failed", error=str(e))
        result["blueprint_path"] = None

    logger.info(
        "codebook_explore.done",
        total_seconds=total_time,
        modules_scanned=len(modules),
        modules_read=len(chapters),
        diagnoses=len(diagnose_results),
    )

    return result


def _build_report_data(
    scan: dict,
    chapters: dict[str, dict],
    diagnoses: dict[str, dict],
    selected_modules: list[str],
    selection_strategy: str,
    query: str,
    role: str,
) -> dict[str, Any]:
    """组装交互式报告所需的结构化数据。

    这份数据会被传给前端（HTML/React），生成可点击展开的交互式页面。
    """
    # 项目概览卡
    overview = {
        "project_overview": scan.get("project_overview", ""),
        "stats": scan.get("stats", {}),
        "mermaid_diagram": scan.get("mermaid_diagram", ""),
        "parse_warnings": scan.get("parse_warnings", []),
    }

    # 模块卡片列表（包含展开详情）
    module_cards: list[dict[str, Any]] = []
    all_modules = scan.get("modules", [])

    for mod in all_modules:
        name = mod.get("name", "")
        card: dict[str, Any] = {
            "name": name,
            "title": mod.get("node_title", name),
            "body": mod.get("node_body", ""),
            "health": mod.get("health", "green"),
            "paths": mod.get("paths", []),
            "depends_on": mod.get("depends_on", []),
            "used_by": mod.get("used_by", []),
            "is_selected": name in selected_modules,
        }

        # 如果有深入阅读的数据，嵌入进去
        if name in chapters:
            ch = chapters[name]
            card["chapter"] = {
                "module_cards": ch.get("module_cards", []),
                "dependency_graph": ch.get("dependency_graph", ""),
                "summary": ch.get("summary", ""),
            }

        # 如果有诊断数据
        if name in diagnoses:
            diag = diagnoses[name]
            card["diagnosis"] = {
                "matches": diag.get("matches", []),
                "call_chain": diag.get("call_chain", []),
                "mermaid": diag.get("mermaid_diagram", ""),
                "code_locations": diag.get("code_locations", []),
            }

        module_cards.append(card)

    # 项目健康概览（无具体问题时的诊断）
    health_overview = None
    if "_project_health" in diagnoses:
        health = diagnoses["_project_health"]
        health_overview = {
            "matches": health.get("matches", []),
            "call_chain": health.get("call_chain", []),
            "mermaid": health.get("mermaid_diagram", ""),
        }

    return {
        "overview": overview,
        "module_cards": module_cards,
        "health_overview": health_overview,
        "selection_strategy": selection_strategy,
        "query": query,
        "role": role,
    }
