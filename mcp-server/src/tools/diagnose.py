"""diagnose — 定位：根据自然语言描述追踪问题到精确代码位置。

核心思路（不调用 LLM）：
1. 从 query 提取关键词
2. 在已解析的函数/类名中做模糊匹配，找到候选节点
3. 用 DependencyGraph 的 upstream/downstream 展开调用链
4. 生成 Mermaid 流程图 + 精确 file:line 定位
5. 返回结构化上下文，让 MCP 宿主（Claude Desktop）来推理
"""

import os
import re
from collections import deque
from datetime import datetime

import structlog

from src.parsers.ast_parser import ParseResult, FunctionInfo, ClassInfo
from src.parsers.dependency_graph import DependencyGraph
from src.parsers.module_grouper import ModuleGroup
from src.tools._repo_cache import repo_cache
from src.memory.project_memory import ProjectMemory
from src.memory.models import DiagnosisRecord
from src.summarizer.engine import _normalize_role

logger = structlog.get_logger()

# ── 关键词提取 ────────────────────────────────────────────

# 常见停用词（中英文混合）
_STOP_WORDS = {
    # 英文
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "shall",
    "should", "may", "might", "can", "could", "in", "on", "at", "to",
    "for", "of", "with", "by", "from", "as", "into", "through", "and",
    "or", "but", "not", "this", "that", "it", "its", "my", "your",
    "how", "what", "when", "where", "why", "which", "who", "whom",
    # 中文常见虚词
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都",
    "一", "个", "上", "也", "很", "到", "说", "要", "去", "你", "会",
    "着", "没有", "看", "好", "自己", "这", "他", "她", "它", "们",
    "时", "时候", "如何", "怎么", "怎样", "什么", "哪个", "哪些",
    "为什么", "吗", "呢", "吧", "啊", "啦",
}


def _extract_keywords(query: str) -> list[str]:
    """从自然语言 query 中提取关键词。

    策略：
    1. 按空格/标点拆分
    2. 英文转小写，保留 camelCase / snake_case 的子词
    3. 中文按单字符保留（简单策略）
    4. 过滤停用词和过短的词
    """
    if not query.strip():
        return []

    tokens = re.split(r'[\s,，。！？!?\'"、/\\()（）\[\]【】{}]+', query)

    keywords = []
    for token in tokens:
        token = token.strip()
        if not token:
            continue

        # 拆分 camelCase: handleUserLogin -> handle, user, login
        camel_parts = re.sub(r'([a-z])([A-Z])', r'\1 \2', token).split()
        # 拆分 snake_case: handle_user_login -> handle, user, login
        snake_parts = []
        for part in camel_parts:
            snake_parts.extend(part.split("_"))

        for sub in snake_parts:
            sub_lower = sub.lower()
            if len(sub_lower) < 2:
                continue
            if sub_lower in _STOP_WORDS:
                continue
            keywords.append(sub_lower)

    # 去重但保持顺序
    seen = set()
    unique = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            unique.append(kw)

    return unique


# ── 节点匹配 ────────────────────────────────────────────

def _score_node(node_id: str, node_data: dict, keywords: list[str],
                target_module_files: set[str] | None) -> float:
    """给一个图节点打分：和 query 关键词的匹配程度。

    评分规则：
    - 函数/类名包含关键词：+2 分/个
    - 文件路径包含关键词：+1 分/个
    - 如果限定了模块，非目标模块的节点打折 50%
    """
    label = node_data.get("label", "").lower()
    file_path = node_data.get("file", "").lower()
    score = 0.0

    for kw in keywords:
        if kw in label:
            score += 2.0
        if kw in file_path:
            score += 1.0

    # 模块过滤
    if target_module_files is not None:
        actual_file = node_data.get("file", "")
        if actual_file not in target_module_files:
            score *= 0.5

    return score


def _find_matching_nodes(
    dep_graph: DependencyGraph,
    keywords: list[str],
    target_module_files: set[str] | None,
    max_results: int = 10,
) -> list[tuple[str, float]]:
    """在依赖图中找到与关键词最匹配的节点。"""
    scored = []
    for node_id, data in dep_graph.graph.nodes(data=True):
        # 跳过 <module> 级的占位节点
        if data.get("label") == "<module>":
            continue
        s = _score_node(node_id, data, keywords, target_module_files)
        if s > 0:
            scored.append((node_id, s))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:max_results]


# ── 调用链追踪 ──────────────────────────────────────────

def _trace_call_chain(
    dep_graph: DependencyGraph,
    seed_nodes: list[str],
    max_depth: int = 3,
    max_total_nodes: int = 30,
) -> dict:
    """从种子节点出发，向上游和下游追踪调用链。

    Returns:
        {
            "nodes": {node_id: {file, line_start, line_end, label, direction}},
            "edges": [(from, to, data)],
        }
    """
    chain_nodes: dict[str, dict] = {}
    chain_edges: list[tuple[str, str, dict]] = []
    visited = set()

    def _add_node(nid: str, direction: str):
        if nid in chain_nodes:
            return
        data = dep_graph.graph.nodes.get(nid, {})
        chain_nodes[nid] = {
            "file": data.get("file", ""),
            "line_start": data.get("line_start", 0),
            "line_end": data.get("line_end", 0),
            "label": data.get("label", nid.split("::")[-1]),
            "module_group": data.get("module_group", ""),
            "node_type": data.get("node_type", "function"),
            "direction": direction,  # "seed" | "upstream" | "downstream"
        }

    # 种子节点
    for nid in seed_nodes:
        _add_node(nid, "seed")

    # BFS 上游
    queue: deque[tuple[str, int]] = deque()
    for nid in seed_nodes:
        queue.append((nid, 0))
        visited.add(nid)

    while queue and len(chain_nodes) < max_total_nodes:
        current, depth = queue.popleft()
        if depth >= max_depth:
            continue
        for pred in dep_graph.get_upstream(current):
            if pred not in visited:
                visited.add(pred)
                _add_node(pred, "upstream")
                edge_data = dep_graph.graph.get_edge_data(pred, current) or {}
                chain_edges.append((pred, current, dict(edge_data)))
                queue.append((pred, depth + 1))

    # BFS 下游
    visited_down = set(seed_nodes)
    queue_down: deque[tuple[str, int]] = deque()
    for nid in seed_nodes:
        queue_down.append((nid, 0))

    while queue_down and len(chain_nodes) < max_total_nodes:
        current, depth = queue_down.popleft()
        if depth >= max_depth:
            continue
        for succ in dep_graph.get_downstream(current):
            if succ not in visited_down:
                visited_down.add(succ)
                _add_node(succ, "downstream")
                edge_data = dep_graph.graph.get_edge_data(current, succ) or {}
                chain_edges.append((current, succ, dict(edge_data)))
                queue_down.append((succ, depth + 1))

    # 补充种子节点间已有的边
    for u in seed_nodes:
        for v in seed_nodes:
            if u != v and dep_graph.graph.has_edge(u, v):
                edge_data = dep_graph.graph.get_edge_data(u, v) or {}
                chain_edges.append((u, v, dict(edge_data)))

    return {"nodes": chain_nodes, "edges": chain_edges}


# ── Mermaid 生成 ─────────────────────────────────────────

def _sanitize_id(text: str) -> str:
    return (text
            .replace("/", "_")
            .replace(".", "_")
            .replace("::", "__")
            .replace("-", "_")
            .replace(" ", "_")
            .replace("<", "")
            .replace(">", ""))


def _sanitize_label(text: str) -> str:
    return text.replace('"', "'").replace("<", "‹").replace(">", "›")


def _chain_to_mermaid(chain: dict) -> str:
    """将调用链转为 Mermaid flowchart。

    颜色约定：
    - seed 节点：红色（:::seed）
    - upstream 节点：蓝色
    - downstream 节点：绿色
    """
    nodes = chain["nodes"]
    edges = chain["edges"]

    if not nodes:
        return "graph TD\n  empty[未找到匹配的代码节点]"

    lines = ["graph TD"]

    # classDef 样式
    lines.append("  classDef seed fill:#ff6b6b,stroke:#c92a2a,color:#fff")
    lines.append("  classDef upstream fill:#74c0fc,stroke:#1971c2,color:#fff")
    lines.append("  classDef downstream fill:#69db7c,stroke:#2b8a3e,color:#fff")

    # 按 module_group 分组
    groups: dict[str, list[str]] = {}
    for nid, data in nodes.items():
        mg = data.get("module_group", "") or "其他"
        groups.setdefault(mg, []).append(nid)

    for group_name, node_ids in groups.items():
        safe_group = _sanitize_id(group_name)
        lines.append(f"  subgraph {safe_group}[\"{_sanitize_label(group_name)}\"]")
        for nid in node_ids:
            data = nodes[nid]
            safe_id = _sanitize_id(nid)
            label = data["label"]
            file_short = data["file"].split("/")[-1] if data["file"] else ""
            line_info = f"L{data['line_start']}" if data["line_start"] else ""
            display = f"{label}"
            if file_short:
                display += f"\\n{file_short}:{line_info}"
            lines.append(f"    {safe_id}[\"{_sanitize_label(display)}\"]")
        lines.append("  end")

    # 边
    seen_edges = set()
    for u, v, data in edges:
        edge_key = (u, v)
        if edge_key in seen_edges:
            continue
        seen_edges.add(edge_key)

        safe_u = _sanitize_id(u)
        safe_v = _sanitize_id(v)
        label = data.get("data_label", "")
        count = data.get("call_count", 1)

        if count >= 3:
            if label:
                lines.append(f"  {safe_u} ==>|\"{label}\"| {safe_v}")
            else:
                lines.append(f"  {safe_u} ==> {safe_v}")
        else:
            if label:
                lines.append(f"  {safe_u} -->|\"{label}\"| {safe_v}")
            else:
                lines.append(f"  {safe_u} --> {safe_v}")

    # 节点样式
    for nid, data in nodes.items():
        safe_id = _sanitize_id(nid)
        direction = data["direction"]
        lines.append(f"  class {safe_id} {direction}")

    return "\n".join(lines)


# ── 精确定位提取 ─────────────────────────────────────────

def _extract_locations(chain: dict, repo_path: str | None = None) -> list[dict]:
    """从调用链中提取精确的 file:line 定位信息。"""
    locations = []
    for nid, data in chain["nodes"].items():
        if data["direction"] == "seed":
            priority = "high"
        elif data["direction"] in ("upstream", "downstream"):
            priority = "medium"
        else:
            priority = "low"

        loc = {
            "node_id": nid,
            "label": data["label"],
            "file": data["file"],
            "line_start": data["line_start"],
            "line_end": data["line_end"],
            "module_group": data.get("module_group", ""),
            "node_type": data.get("node_type", "function"),
            "direction": data["direction"],
            "priority": priority,
            "ref": f"{data['file']}:L{data['line_start']}-L{data['line_end']}",
        }

        # 如果有 repo_path，尝试读取代码片段
        if repo_path and data["file"] and data["line_start"]:
            abs_path = os.path.join(repo_path, data["file"])
            try:
                with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                    all_lines = f.readlines()
                start = max(0, data["line_start"] - 1)
                end = min(len(all_lines), data["line_end"] or start + 20)
                snippet_lines = all_lines[start:end]
                # 带行号
                numbered = []
                for i, line in enumerate(snippet_lines, start=start + 1):
                    numbered.append(f"{i:4d} | {line.rstrip()}")
                loc["code_snippet"] = "\n".join(numbered)
            except OSError:
                pass

        locations.append(loc)

    # 按优先级排序：seed 在前
    priority_order = {"high": 0, "medium": 1, "low": 2}
    locations.sort(key=lambda x: priority_order.get(x["priority"], 9))
    return locations


# ── 辅助：收集模块相关的上下文 ──────────────────────────

def _build_context_text(
    chain: dict,
    locations: list[dict],
    modules: list[ModuleGroup],
    module_name: str,
) -> str:
    """构建供 Claude Desktop 推理的上下文文本。"""
    parts = []

    # 1. 匹配到的核心节点
    seed_nodes = [loc for loc in locations if loc["direction"] == "seed"]
    if seed_nodes:
        parts.append("## 匹配到的核心代码位置\n")
        for loc in seed_nodes:
            parts.append(f"### {loc['label']} ({loc['ref']})")
            parts.append(f"模块: {loc['module_group']}, 类型: {loc['node_type']}")
            if loc.get("code_snippet"):
                parts.append(f"```\n{loc['code_snippet']}\n```")
            parts.append("")

    # 2. 上游调用方
    upstream = [loc for loc in locations if loc["direction"] == "upstream"]
    if upstream:
        parts.append("## 上游调用方（谁调用了这段代码）\n")
        for loc in upstream:
            parts.append(f"- **{loc['label']}** @ {loc['ref']} (模块: {loc['module_group']})")
            if loc.get("code_snippet"):
                parts.append(f"  ```\n{loc['code_snippet']}\n  ```")
        parts.append("")

    # 3. 下游被调用
    downstream = [loc for loc in locations if loc["direction"] == "downstream"]
    if downstream:
        parts.append("## 下游调用（这段代码调用了谁）\n")
        for loc in downstream:
            parts.append(f"- **{loc['label']}** @ {loc['ref']} (模块: {loc['module_group']})")
            if loc.get("code_snippet"):
                parts.append(f"  ```\n{loc['code_snippet']}\n  ```")
        parts.append("")

    return "\n".join(parts)


# ── 角色 guidance ─────────────────────────────────────────

ROLE_GUIDANCE = {
    "dev": (
        "你是 CodeBook 的 AI 助手，正在帮助开发者定位问题。\n"
        "提供精确的代码定位、调用链分析和修复建议。\n"
        "关键信息：函数签名、参数类型、返回值、异常处理、循环依赖、性能瓶颈。\n"
        "可以使用所有技术术语（AST、序列化、中间件、幂等性等）。\n"
        "重点关注代码逻辑和实现细节。"
    ),
    "pm": (
        "你是 CodeBook 的 AI 助手，正在帮助产品经理定位问题。\n"
        "用产品视角解释代码调用链，关注用户体验影响和功能逻辑。\n"
        "关键信息：功能完整性、用户体验影响、工作量估算、依赖关系。\n"
        "避免技术术语，用业务语言描述问题所在位置和影响范围。\n"
        "重点强调这个问题如何影响用户体验。"
    ),
    "domain_expert": (
        "你是 CodeBook 的 AI 助手，正在帮助行业专家审查代码。\n"
        "关键信息：业务规则验证、合规检查、风险识别、审计记录。\n"
        "重点识别涉及数据安全、合规要求、业务规则的代码部分。\n"
        "用该领域的专业术语翻译代码逻辑，让专家能够验证实现是否符合行业标准。"
    ),
    # 向后兼容：旧角色映射到新视图
    "ceo": (
        "你是 CodeBook 的 AI 助手，正在帮助决策者了解技术问题。\n"
        "用商业语言解释问题的影响范围和严重程度。\n"
        "关注对产品、用户和业务的影响。"
    ),
    "qa": (
        "你是 CodeBook 的 AI 助手，正在帮助测试工程师定位问题。\n"
        "关注测试覆盖、边界条件和复现路径。\n"
        "提供精确的调用链和可测试的断点位置。"
    ),
}


# ── 主入口 ────────────────────────────────────────────────

async def diagnose(module_name: str = "all", role: str = "pm", query: str = "") -> dict:
    """根据自然语言描述定位问题代码。

    Args:
        module_name: 要诊断的模块名称，默认 "all" 表示全项目扫描。
        role: 目标角色。
        query: 用户用自然语言描述的问题或现象。

    Returns:
        包含 matched_modules、call_chain（Mermaid）、exact_locations、
        context、guidance 的字典，供 MCP 宿主推理使用。
    """
    logger.info("diagnose.start", module_name=module_name, role=role, query=query)

    # 1. 获取缓存的解析上下文
    from src.tools._repo_cache import _ExpiredSentinel
    ctx = repo_cache.get()
    if isinstance(ctx, _ExpiredSentinel):
        return {
            "status": "error",
            "error": f"仓库「{ctx.repo_url}」的缓存已过期（超过 7 天未使用），请重新运行 scan_repo",
            "module_name": module_name,
            "role": role,
            "query": query,
        }
    if ctx is None:
        return {
            "status": "error",
            "error": "请先运行 scan_repo 扫描一个仓库",
            "module_name": module_name,
            "role": role,
            "query": query,
        }

    # 2. 确定目标模块范围
    target_module_files: set[str] | None = None
    matched_modules: list[str] = []

    if module_name != "all":
        for m in ctx.modules:
            if m.name == module_name or module_name in m.name:
                target_module_files = target_module_files or set()
                target_module_files.update(m.files)
                matched_modules.append(m.name)

        if target_module_files is None:
            # 模块名未精确匹配，尝试模糊匹配
            query_lower = module_name.lower()
            for m in ctx.modules:
                if query_lower in m.name.lower() or query_lower in m.dir_path.lower():
                    target_module_files = target_module_files or set()
                    target_module_files.update(m.files)
                    matched_modules.append(m.name)

            if target_module_files is None:
                return {
                    "status": "error",
                    "error": f"模块 '{module_name}' 不存在",
                    "available_modules": [m.name for m in ctx.modules],
                }
    else:
        matched_modules = [m.name for m in ctx.modules if not m.is_special]

    # 3. 提取关键词
    keywords = _extract_keywords(query)
    logger.info("diagnose.keywords", keywords=keywords)

    if not keywords:
        return {
            "status": "error",
            "error": "无法从 query 中提取有效关键词，请提供更具体的描述",
            "query": query,
            "matched_modules": matched_modules,
        }

    # 4. 在依赖图中找匹配节点
    matches = _find_matching_nodes(
        ctx.dep_graph, keywords, target_module_files, max_results=5,
    )

    if not matches:
        # 降级：返回模块级信息
        normalized_role = _normalize_role(role)
        return {
            "status": "no_exact_match",
            "message": "未找到与描述精确匹配的代码节点，返回模块级概览",
            "module_name": module_name,
            "query": query,
            "keywords": keywords,
            "matched_modules": matched_modules,
            "call_chain": ctx.dep_graph.to_mermaid(level="module"),
            "exact_locations": [],
            "context": f"查询关键词 {keywords} 未在函数/类名中找到匹配。"
                        f"匹配的模块: {', '.join(matched_modules)}",
            "guidance": ROLE_GUIDANCE.get(normalized_role, ROLE_GUIDANCE["pm"]),
        }

    # 5. 追踪调用链
    seed_node_ids = [nid for nid, _ in matches]
    chain = _trace_call_chain(ctx.dep_graph, seed_node_ids, max_depth=3)

    # 6. 生成 Mermaid 流程图
    mermaid = _chain_to_mermaid(chain)

    # 7. 提取精确定位
    repo_path = getattr(ctx.clone_result, "repo_path", None)
    locations = _extract_locations(chain, repo_path)

    # 8. 构建上下文文本
    context_text = _build_context_text(chain, locations, ctx.modules, module_name)

    # 9. 收集匹配到的模块
    chain_modules = set()
    for nid, data in chain["nodes"].items():
        mg = data.get("module_group", "")
        if mg:
            chain_modules.add(mg)

    logger.info(
        "diagnose.done",
        seed_count=len(seed_node_ids),
        chain_nodes=len(chain["nodes"]),
        chain_edges=len(chain["edges"]),
        locations=len(locations),
    )

    normalized_role = _normalize_role(role)
    result = {
        "status": "ok",
        "module_name": module_name,
        "role": role,
        "query": query,
        "keywords": keywords,
        "matched_modules": list(chain_modules) or matched_modules,
        "matched_nodes": [
            {"node_id": nid, "score": score,
             "label": ctx.dep_graph.graph.nodes[nid].get("label", ""),
             "file": ctx.dep_graph.graph.nodes[nid].get("file", "")}
            for nid, score in matches
        ],
        "call_chain": mermaid,
        "exact_locations": locations,
        "context": context_text,
        "guidance": ROLE_GUIDANCE.get(normalized_role, ROLE_GUIDANCE["pm"]),
    }

    # Persist diagnosis to ProjectMemory for each matched module
    try:
        repo_url = ctx.repo_url or ""
        if repo_url:
            memory = ProjectMemory(repo_url)
            # Extract diagnosis summary from context and locations
            diagnosis_summary = f"Found {len(seed_node_ids)} matching nodes in call chain"
            matched_locations = [loc.get("ref", "") for loc in locations if loc.get("ref")]

            # Persist for target module if specified
            if module_name != "all":
                for m in (chain_modules or matched_modules):
                    record = DiagnosisRecord(
                        query=query,
                        diagnosis_summary=diagnosis_summary,
                        matched_locations=matched_locations,
                        timestamp=datetime.utcnow().isoformat() + "Z",
                    )
                    memory.add_diagnosis(m, record)
            logger.info("diagnose.persisted", modules=len(chain_modules or matched_modules))
    except Exception as e:
        logger.exception("diagnose.persistence_failed", error=str(e))

    return result
