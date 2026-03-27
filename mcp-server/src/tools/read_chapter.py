"""read_chapter — 看懂能力：读取指定模块的详细模块卡片。

需要先调用 scan_repo 扫描项目，read_chapter 从缓存中获取上下文。

P0 修复：大模块（如 Flask 的 src/flask，9201 行 23 文件）返回值可能
超过 Claude Desktop 的 token 限制。解决方案：
1. 默认返回摘要模式（函数签名 + 调用关系，不含源码）
2. 大模块自动拆分为子文件列表，用户可逐个查看
3. 控制 dependency_graph 只渲染当前模块的局部图
"""

import os
import time
from datetime import datetime

import structlog

from src.summarizer.engine import SummaryContext
from src.tools._repo_cache import repo_cache
from src.memory.project_memory import ProjectMemory

logger = structlog.get_logger()

# 单次返回的卡片数量上限
MAX_CARDS_PER_RESPONSE = 10
# 大模块阈值（行数）
LARGE_MODULE_THRESHOLD = 3000


async def read_chapter(module_name: str, role: str = "pm") -> dict:
    """读取指定模块的详细章节内容（模块卡片 + 依赖图）。

    Args:
        module_name: 模块名称（业务语言，如「用户认证」），或目录名（如 app/api）。
        role: 目标角色。支持：dev, pm, domain_expert（或向后兼容的旧名称：ceo, investor, qa）。

    Returns:
        包含 module_cards（JSON 数组）和 dependency_graph（Mermaid）的字典。
        大模块会分页返回，附 pagination 信息。
    """
    start = time.time()
    logger.info("read_chapter.start", module_name=module_name, role=role)

    # 获取缓存的上下文
    from src.tools._repo_cache import _ExpiredSentinel
    ctx = repo_cache.get()
    if isinstance(ctx, _ExpiredSentinel):
        return {
            "status": "error",
            "error": f"仓库「{ctx.repo_url}」的缓存已过期（超过 7 天未使用），请重新运行 scan_repo",
            "hint": "缓存按最后访问时间计算，连续 7 天未使用才会过期。重新扫描即可恢复。",
        }
    if ctx is None:
        return {
            "status": "error",
            "error": "请先调用 scan_repo 扫描项目",
            "hint": "read_chapter 需要先扫描项目才能查看模块详情。请先使用 scan_repo 工具扫描仓库。",
        }

    # 模糊匹配模块名：支持业务名和目录名
    exact_match = None
    fuzzy_matches = []
    for m in ctx.modules:
        if m.name == module_name or m.dir_path == module_name:
            exact_match = m
            break
        # 模糊：包含关系
        if module_name.lower() in m.name.lower() or module_name.lower() in m.dir_path.lower():
            fuzzy_matches.append(m)

    target = None
    if exact_match:
        target = exact_match
    elif len(fuzzy_matches) == 1:
        target = fuzzy_matches[0]
        logger.info("read_chapter.fuzzy_match", query=module_name, matched=target.name)
    elif len(fuzzy_matches) > 1:
        return {
            "status": "error",
            "error": f"模块名「{module_name}」匹配到多个模块，请更精确",
            "candidates": [m.name for m in fuzzy_matches],
        }
    else:
        return {
            "status": "error",
            "error": f"未找到模块「{module_name}」",
            "available_modules": [m.name for m in ctx.modules if not m.is_special],
        }

    # 生成摘要模式的模块卡片
    chapter = _generate_compact_chapter(ctx, target)

    elapsed = round(time.time() - start, 2)
    logger.info("read_chapter.done", module=target.name,
                cards=len(chapter.get("module_cards", [])), seconds=elapsed)

    # Increment view_count in ProjectMemory
    try:
        repo_url = ctx.repo_url or ""
        if repo_url:
            memory = ProjectMemory(repo_url)
            path = memory._get_json_path("understanding.json")
            data = memory._safe_read_json(path)
            if "modules" not in data:
                data = {"version": 1, "modules": {}}
            if target.name not in data["modules"]:
                data["modules"][target.name] = {
                    "module_name": target.name,
                    "diagnoses": [],
                    "qa_history": [],
                    "annotations": [],
                    "view_count": 1,
                    "diagnose_count": 0,
                    "ask_count": 0,
                    "last_accessed": datetime.utcnow().isoformat() + "Z",
                }
            else:
                data["modules"][target.name]["view_count"] += 1
                data["modules"][target.name]["last_accessed"] = datetime.utcnow().isoformat() + "Z"
            memory._safe_write_json(path, data)
            logger.info("read_chapter.view_count_updated", module=target.name)
    except Exception as e:
        logger.exception("read_chapter.view_count_update_failed", error=str(e))

    chapter["role"] = role
    return chapter


def _generate_compact_chapter(ctx: SummaryContext, target) -> dict:
    """生成紧凑的模块卡片（不含源码，控制大小）。"""
    module_files = set(target.files)
    relevant_prs = [pr for pr in ctx.parse_results if pr.file_path in module_files]

    is_large = target.total_lines > LARGE_MODULE_THRESHOLD
    total_files = len(relevant_prs)

    # 对大模块只展示前 N 个文件的卡片
    display_prs = relevant_prs[:MAX_CARDS_PER_RESPONSE] if is_large else relevant_prs

    cards = []
    for pr in display_prs:
        if not pr.functions and not pr.classes:
            continue
        cards.append(_build_compact_card(pr, ctx))

    # 局部依赖图：只包含当前模块内部的调用关系
    dep_mermaid = _build_module_local_mermaid(ctx, target, relevant_prs)

    # Sprint 3: 确定当前模块属于哪个超级节点组
    parent_group = ""
    try:
        super_groups = ctx.dep_graph._build_super_groups()
        for grp, sub_modules in super_groups.items():
            if target.name in sub_modules or target.dir_path in sub_modules:
                parent_group = grp
                break
    except Exception:
        pass  # 不影响主流程

    result = {
        "status": "ok",
        "module_name": target.name,
        "parent_group": parent_group,
        "module_summary": {
            "dir_path": target.dir_path,
            "total_files": total_files,
            "total_lines": target.total_lines,
            "entry_functions": target.entry_functions[:10],
            "public_interfaces": target.public_interfaces[:10],
        },
        "module_cards": cards,
        "dependency_graph": dep_mermaid,
    }

    # 大模块分页提示
    if is_large and total_files > MAX_CARDS_PER_RESPONSE:
        remaining_files = [
            pr.file_path for pr in relevant_prs[MAX_CARDS_PER_RESPONSE:]
        ]
        result["pagination"] = {
            "showing": len(display_prs),
            "total": total_files,
            "remaining_files": remaining_files,
            "hint": f"模块较大（{target.total_lines} 行），"
                    f"当前显示前 {len(display_prs)} 个文件。"
                    f"可通过 read_chapter 指定子文件路径查看更多。",
        }

    return result


def _build_compact_card(pr, ctx: SummaryContext) -> dict:
    """为一个文件构建紧凑卡片（函数签名 + 调用关系，不含源码）。"""
    file_name = pr.file_path.split("/")[-1]
    stem = file_name.rsplit(".", 1)[0]

    # 函数签名列表（紧凑格式）
    functions = []
    for f in pr.functions:
        sig = {
            "name": f.name,
            "params": f.params[:5],
            "return_type": f.return_type,
            "lines": f"{f.line_start}-{f.line_end}",
            "is_method": f.is_method,
        }
        if f.docstring:
            # 只取第一行 docstring
            sig["doc"] = f.docstring.split("\n")[0].strip()[:80]
        if f.parent_class:
            sig["class"] = f.parent_class
        functions.append(sig)

    # 类列表
    classes = []
    for c in pr.classes:
        classes.append({
            "name": c.name,
            "methods": c.methods[:10],
            "lines": f"{c.line_start}-{c.line_end}",
        })

    # 调用关系（谁调谁）
    calls = []
    seen = set()
    for call in pr.calls:
        key = (call.caller_func, call.callee_name)
        if key not in seen:
            seen.add(key)
            calls.append({
                "from": call.caller_func,
                "to": call.callee_name,
                "line": call.line,
            })

    # 依赖输入
    imports = []
    for imp in pr.imports[:8]:
        if imp.module:
            names_str = ", ".join(imp.names[:3]) if imp.names else ""
            imports.append(f"{imp.module}" + (f" ({names_str})" if names_str else ""))

    return {
        "name": stem,
        "path": pr.file_path,
        "summary": f"{len(pr.functions)} 个函数, {len(pr.classes)} 个类, {pr.line_count} 行",
        "functions": functions,
        "classes": classes,
        "calls": calls,
        "imports": imports,
        "ref": f"{pr.file_path}:L1-L{pr.line_count}",
    }


def _build_module_local_mermaid(ctx: SummaryContext, target, relevant_prs) -> str:
    """只渲染当前模块内部的调用关系图（避免全项目函数图太大）。"""
    module_files = set(target.files)

    # 收集模块内所有节点 ID
    module_node_ids = set()
    for nid, data in ctx.dep_graph.graph.nodes(data=True):
        if data.get("file", "") in module_files:
            module_node_ids.add(nid)

    if not module_node_ids:
        return f"graph TD\n  empty[模块 {target.name} 暂无函数级依赖数据]"

    # 安全 ID 转换
    def safe(text: str) -> str:
        return (text.replace("/", "_").replace(".", "_")
                .replace("::", "__").replace("-", "_")
                .replace(" ", "_").replace("<", "").replace(">", ""))

    def safe_label(text: str) -> str:
        return text.replace('"', "'").replace("<", "‹").replace(">", "›")

    lines = ["graph TD"]

    # 按文件分 subgraph
    file_groups: dict[str, list[str]] = {}
    for nid in module_node_ids:
        data = ctx.dep_graph.graph.nodes[nid]
        fpath = data.get("file", "unknown")
        file_groups.setdefault(fpath, []).append(nid)

    for fpath, nids in file_groups.items():
        fname = fpath.split("/")[-1]
        lines.append(f"  subgraph {safe(fpath)}[\"{safe_label(fname)}\"]")
        for nid in nids:
            data = ctx.dep_graph.graph.nodes[nid]
            label = data.get("label", nid.split("::")[-1])
            if label == "<module>":
                continue
            lines.append(f"    {safe(nid)}[\"{safe_label(label)}\"]")
        lines.append("  end")

    # 只渲染模块内部的边
    edge_count = 0
    for u, v, data in ctx.dep_graph.graph.edges(data=True):
        if u in module_node_ids and v in module_node_ids:
            label_text = data.get("data_label", "")
            count = data.get("call_count", 1)
            arrow = "==>" if count >= 3 else "-->"
            if label_text:
                lines.append(f"  {safe(u)} {arrow}|\"{label_text}\"| {safe(v)}")
            else:
                lines.append(f"  {safe(u)} {arrow} {safe(v)}")
            edge_count += 1

    # 也显示跨模块的入口/出口（但只显示边，不展开外部节点详情）
    cross_in = 0
    cross_out = 0
    for u, v, _ in ctx.dep_graph.graph.edges(data=True):
        if v in module_node_ids and u not in module_node_ids:
            cross_in += 1
        if u in module_node_ids and v not in module_node_ids:
            cross_out += 1

    if cross_in > 0 or cross_out > 0:
        lines.append(f"  external[\"外部调用\\n入: {cross_in} 次, 出: {cross_out} 次\"]")
        lines.append(f"  style external fill:#f5f5f5,stroke:#ccc,stroke-dasharray: 5 5")

    return "\n".join(lines)
