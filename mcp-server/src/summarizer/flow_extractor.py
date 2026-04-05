"""flow_extractor — 从依赖图中提取业务流程骨架。

从代码调用图中提取 3-5 条核心业务流程线，用纯业务语言描述每个步骤。
不依赖 LLM，使用规则降级方案生成描述。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import networkx as nx
import structlog

from src.summarizer.business_namer import infer_function_explanation

logger = structlog.get_logger()

# 避免循环导入：使用 TYPE_CHECKING
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.summarizer.engine import SummaryContext

# ── 入口函数名模式 ──────────────────────────────────────────

_ENTRY_PATTERNS: set[str] = {
    "main", "app", "run", "start", "serve", "execute",
    "cli", "entrypoint", "entry_point", "bootstrap",
    "launch", "init", "initialize", "setup",
}

_ENTRY_PREFIXES: tuple[str, ...] = (
    "handle", "process", "dispatch", "on_", "route",
)

# ── 流程名推断映射 ──────────────────────────────────────────

_FLOW_NAME_MAP: dict[str, str] = {
    "main": "程序主流程",
    "app": "应用启动流程",
    "run": "运行流程",
    "start": "启动流程",
    "serve": "服务启动流程",
    "execute": "执行流程",
    "cli": "命令行执行流程",
    "bootstrap": "引导启动流程",
    "launch": "启动流程",
    "init": "初始化流程",
    "initialize": "初始化流程",
    "setup": "设置流程",
}

_FLOW_PREFIX_MAP: dict[str, str] = {
    "handle": "处理",
    "process": "处理",
    "dispatch": "分发",
    "on_": "响应",
    "route": "路由",
    "create": "创建",
    "update": "更新",
    "delete": "删除",
    "get": "获取",
    "fetch": "拉取",
    "send": "发送",
    "check": "检查",
    "validate": "验证",
    "sync": "同步",
    "import": "导入",
    "export": "导出",
    "login": "登录",
    "logout": "登出",
    "register": "注册",
    "upload": "上传",
    "download": "下载",
    "search": "搜索",
    "build": "构建",
    "generate": "生成",
    "parse": "解析",
    "render": "渲染",
    "publish": "发布",
    "subscribe": "订阅",
    "notify": "通知",
    "migrate": "迁移",
    "deploy": "部署",
    "test": "测试",
    "scan": "扫描",
    "analyze": "分析",
    "schedule": "调度",
}

# ── 技术词清理 ──────────────────────────────────────────────

_TECH_NOISE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"，参数为\s*[^，。]+"),  # 去掉参数描述
    re.compile(r"，返回\s*[^，。]+"),    # 去掉返回值描述
    re.compile(r"\b[a-zA-Z_][a-zA-Z0-9_]*\.(py|js|ts|go|rs|java|swift|kt)\b"),  # 文件路径
    re.compile(r"\b[a-zA-Z_][a-zA-Z0-9_]*::[a-zA-Z_][a-zA-Z0-9_]*\b"),  # node_id 格式
]


# ── 数据结构 ─────────────────────────────────────────────────


@dataclass
class FlowStep:
    """业务流程中的一个步骤。"""

    business_description: str  # 业务语言描述（展示给用户）
    # 以下字段仅供内部验证和 LLM 参考，不展示给用户
    _node_id: str = ""
    _func_name: str = ""
    _file_path: str = ""
    _line_start: int = 0
    _module: str = ""


@dataclass
class BusinessFlow:
    """一条业务流程线。"""

    name: str  # 流程名（业务语言）
    description: str  # 一句话概述
    steps: list[FlowStep] = field(default_factory=list)
    importance: float = 0.0  # 重要程度 0-1（用于排序）
    branch_flows: list["BusinessFlow"] = field(default_factory=list)


@dataclass
class FlowExtractionResult:
    """流程提取结果。"""

    project_name: str = ""
    project_description: str = ""
    main_flows: list[BusinessFlow] = field(default_factory=list)
    coverage: float = 0.0  # 主线覆盖了多少比例的核心函数


# ── 核心函数 ─────────────────────────────────────────────────


def extract_flows(ctx: "SummaryContext") -> FlowExtractionResult:
    """从 SummaryContext 中提取业务流程骨架。

    算法：找入口 → DFS 追踪 → 评分排序 → 贪心选主线 → 归类支线 → 生成描述。
    """
    graph = ctx.dep_graph.graph

    # 0. 项目名
    project_name = _infer_project_name(ctx)

    # 1. 找入口节点
    entries = _find_entry_nodes(ctx)
    if not entries:
        logger.warning("flow_extractor.no_entries")
        return FlowExtractionResult(
            project_name=project_name,
            project_description="未找到入口函数",
        )

    # 2. DFS 追踪调用链
    all_paths = _trace_paths(graph, entries)
    if not all_paths:
        logger.warning("flow_extractor.no_paths")
        return FlowExtractionResult(
            project_name=project_name,
            project_description="未找到有效调用链",
        )

    # 3. 评分
    scores = [_score_path(graph, p) for p in all_paths]

    # 4. 选主线
    main_paths = _select_main_flows(all_paths, scores)
    if not main_paths:
        return FlowExtractionResult(
            project_name=project_name,
            project_description="未找到足够长的调用链",
        )

    # 5. 归类支线
    branch_map = _assign_branch_flows(main_paths, all_paths)

    # 6. 生成 BusinessFlow
    main_flows: list[BusinessFlow] = []
    max_score = max(scores) if scores else 1.0
    for i, path in enumerate(main_paths):
        name = _infer_flow_name(path[0], graph)
        branches = branch_map.get(i, [])
        flow = _path_to_flow(graph, path, name, branches)
        # importance: 归一化分数
        path_idx = all_paths.index(path) if path in all_paths else 0
        raw_score = scores[path_idx] if path_idx < len(scores) else 0.0
        flow.importance = raw_score / max_score if max_score > 0 else 0.0
        main_flows.append(flow)

    # 排序
    main_flows.sort(key=lambda f: f.importance, reverse=True)

    # 计算覆盖率
    coverage = _compute_coverage(graph, main_paths)

    # 项目描述
    flow_names = "、".join(f.name for f in main_flows[:3])
    project_desc = f"包含 {flow_names} 等核心流程"

    return FlowExtractionResult(
        project_name=project_name,
        project_description=project_desc,
        main_flows=main_flows,
        coverage=coverage,
    )


# ── 辅助函数 ─────────────────────────────────────────────────


def _find_entry_nodes(ctx: "SummaryContext") -> list[str]:
    """找到所有候选入口节点 ID。

    来源：
    1. ModuleGroup.entry_functions（模块分组时识别的入口）
    2. 图中入度为 0 的函数节点
    3. 函数名匹配已知入口模式
    """
    graph = ctx.dep_graph.graph
    candidates: set[str] = set()

    # 1. 从 ModuleGroup 收集 entry_functions
    module_entry_names: set[str] = set()
    for module in ctx.modules:
        for ef in module.entry_functions:
            module_entry_names.add(ef)

    # 在图中找到对应的 node_id
    for node_id, data in graph.nodes(data=True):
        label = data.get("label", "")
        if label in module_entry_names:
            candidates.add(node_id)

    # 2. 入度为 0 的函数节点
    for node_id, data in graph.nodes(data=True):
        node_type = data.get("node_type", "")
        if node_type in ("function", "method") and graph.in_degree(node_id) == 0:
            candidates.add(node_id)

    # 3. 匹配已知入口模式
    for node_id, data in graph.nodes(data=True):
        label = data.get("label", "").lower()
        node_type = data.get("node_type", "")
        if node_type not in ("function", "method"):
            continue

        if label in _ENTRY_PATTERNS:
            candidates.add(node_id)
            continue

        for prefix in _ENTRY_PREFIXES:
            if label.startswith(prefix):
                candidates.add(node_id)
                break

    # 去掉 <module> 节点
    candidates = {n for n in candidates if "<module>" not in n}

    return sorted(candidates)


def _trace_paths(
    graph: nx.DiGraph,
    entries: list[str],
    max_depth: int = 15,
) -> list[list[str]]:
    """从入口节点 DFS 追踪所有调用路径。

    每个节点在同一条路径中只访问一次（避免环）。
    路径在无后继或到达最大深度时结束。
    """
    all_paths: list[list[str]] = []

    for entry in entries:
        if entry not in graph:
            continue
        _dfs_collect(graph, entry, [entry], set(), max_depth, all_paths)

    return all_paths


def _dfs_collect(
    graph: nx.DiGraph,
    current: str,
    path: list[str],
    visited: set[str],
    max_depth: int,
    result: list[list[str]],
) -> None:
    """DFS 递归收集路径。"""
    visited_with_current = visited | {current}
    successors = [
        s for s in graph.successors(current)
        if s not in visited_with_current
    ]

    depth_remaining = max_depth - (len(path) - 1)

    if not successors or depth_remaining <= 0:
        # 叶子节点或深度达上限，记录路径
        if len(path) >= 2:  # 至少有两个节点才是有意义的路径
            result.append(list(path))
        return

    for succ in successors:
        path.append(succ)
        _dfs_collect(graph, succ, path, visited_with_current, max_depth, result)
        path.pop()


def _score_path(graph: nx.DiGraph, path: list[str]) -> float:
    """为路径评分。

    分数 = 路径长度 x 平均 call_count x 入口加权。
    """
    if len(path) < 2:
        return 0.0

    # 平均 call_count
    total_calls = 0
    edge_count = 0
    for i in range(len(path) - 1):
        u, v = path[i], path[i + 1]
        if graph.has_edge(u, v):
            total_calls += graph[u][v].get("call_count", 1)
            edge_count += 1

    avg_calls = total_calls / edge_count if edge_count > 0 else 1.0

    # 入口加权：入口函数名匹配已知模式加分
    entry_label = graph.nodes[path[0]].get("label", "").lower() if path[0] in graph else ""
    entry_bonus = 2.0 if entry_label in _ENTRY_PATTERNS else 1.0
    for prefix in _ENTRY_PREFIXES:
        if entry_label.startswith(prefix):
            entry_bonus = max(entry_bonus, 1.5)

    return len(path) * avg_calls * entry_bonus


def _select_main_flows(
    paths: list[list[str]],
    scores: list[float],
    max_flows: int = 5,
) -> list[list[str]]:
    """贪心选择重叠最少的 top 路径。

    1. 过滤短路径（< 3 个节点）
    2. 按分数降序排列
    3. 贪心选择与已选路径重叠最少的
    """
    # 过滤短路径
    valid = [
        (path, score)
        for path, score in zip(paths, scores)
        if len(path) >= 3
    ]

    if not valid:
        return []

    # 按分数降序
    valid.sort(key=lambda x: x[1], reverse=True)

    selected: list[list[str]] = []
    covered_nodes: set[str] = set()

    for path, _score in valid:
        if len(selected) >= max_flows:
            break

        path_set = set(path)
        overlap = len(path_set & covered_nodes)
        overlap_ratio = overlap / len(path_set) if path_set else 1.0

        # 第一条无条件选；后续要求重叠率 < 70%
        if not selected or overlap_ratio < 0.7:
            selected.append(path)
            covered_nodes.update(path_set)

    return selected


def _assign_branch_flows(
    main_paths: list[list[str]],
    all_paths: list[list[str]],
) -> dict[int, list[list[str]]]:
    """将支线路径归类到最近的主线。

    返回 {主线索引: [支线路径列表]}。
    """
    main_sets = [set(p) for p in main_paths]
    main_path_set = set(id(p) for p in main_paths)

    result: dict[int, list[list[str]]] = {}

    for path in all_paths:
        # 跳过已选为主线的路径
        if any(path is mp for mp in main_paths):
            continue

        # 跳过太短的路径
        if len(path) < 2:
            continue

        path_set = set(path)

        # 找与哪条主线交集最大
        best_idx = -1
        best_overlap = 0
        for i, ms in enumerate(main_sets):
            overlap = len(path_set & ms)
            if overlap > best_overlap:
                best_overlap = overlap
                best_idx = i

        if best_idx >= 0 and best_overlap > 0:
            result.setdefault(best_idx, []).append(path)

    return result


def _path_to_flow(
    graph: nx.DiGraph,
    path: list[str],
    name: str,
    branches: list[list[str]],
) -> BusinessFlow:
    """将节点路径转换为 BusinessFlow。"""
    steps: list[FlowStep] = []
    for node_id in path:
        data = graph.nodes.get(node_id, {})
        func_name = data.get("label", node_id.split("::")[-1])
        file_path = data.get("file", "")
        line_start = data.get("line_start", 0)
        module = data.get("module_group", "")

        # 生成业务描述
        desc = _make_business_description(func_name, data)

        steps.append(FlowStep(
            business_description=desc,
            _node_id=node_id,
            _func_name=func_name,
            _file_path=file_path,
            _line_start=line_start,
            _module=module,
        ))

    # 生成流程描述
    step_summaries = [s.business_description for s in steps[:3]]
    description = " → ".join(step_summaries)

    # 生成支线
    branch_flows: list[BusinessFlow] = []
    for bp in branches[:5]:  # 最多 5 条支线
        branch_name = _infer_flow_name(bp[0], graph)
        bf = _path_to_flow(graph, bp, branch_name, [])
        branch_flows.append(bf)

    return BusinessFlow(
        name=name,
        description=description,
        steps=steps,
        branch_flows=branch_flows,
    )


def _infer_flow_name(entry_node_id: str, graph: nx.DiGraph) -> str:
    """从入口函数名推断流程业务名。"""
    data = graph.nodes.get(entry_node_id, {})
    label = data.get("label", entry_node_id.split("::")[-1])
    label_lower = label.lower()

    # 精确匹配
    if label_lower in _FLOW_NAME_MAP:
        return _FLOW_NAME_MAP[label_lower]

    # 前缀匹配
    for prefix, action in _FLOW_PREFIX_MAP.items():
        if label_lower.startswith(prefix):
            # 提取后缀作为对象
            suffix = label_lower[len(prefix):]
            suffix = suffix.lstrip("_")
            if suffix:
                # 翻译后缀
                from src.summarizer.business_namer import _KEYWORD_MAP
                suffix_cn = _KEYWORD_MAP.get(suffix, suffix.replace("_", " "))
                return f"{suffix_cn}{action}流程"
            return f"{action}流程"

    # 下划线拆分尝试
    tokens = label_lower.split("_")
    if tokens[0] in _FLOW_PREFIX_MAP:
        action = _FLOW_PREFIX_MAP[tokens[0]]
        rest = "_".join(tokens[1:])
        from src.summarizer.business_namer import _KEYWORD_MAP
        rest_cn = _KEYWORD_MAP.get(rest, rest.replace("_", " "))
        return f"{rest_cn}{action}流程"

    return f"{label}流程"


def _make_business_description(func_name: str, node_data: dict) -> str:
    """生成纯业务语言的步骤描述（不含代码元素）。"""
    # 使用 business_namer 的降级推断
    raw = infer_function_explanation(
        func_name=func_name,
        params=[],  # 不传参数，避免技术细节泄露
        return_type=None,
        docstring=None,  # 不传 docstring，它可能含技术术语
    )

    # 清理技术噪音
    cleaned = _sanitize_description(raw)
    return cleaned


def _sanitize_description(text: str) -> str:
    """清理描述中的技术细节，确保纯业务语言。"""
    result = text

    # 应用正则清理
    for pattern in _TECH_NOISE_PATTERNS:
        result = pattern.sub("", result)

    # 去掉尾部标点前的空白
    result = result.strip()

    # 如果清理后为空，返回通用描述
    if not result:
        return "执行处理操作"

    return result


def _compute_coverage(graph: nx.DiGraph, main_paths: list[list[str]]) -> float:
    """计算主线覆盖了多少比例的核心函数节点。"""
    # 核心函数 = 非 module 类型的节点
    core_nodes: set[str] = set()
    for node_id, data in graph.nodes(data=True):
        if data.get("node_type") != "module":
            core_nodes.add(node_id)

    if not core_nodes:
        return 0.0

    covered: set[str] = set()
    for path in main_paths:
        covered.update(path)

    return len(covered & core_nodes) / len(core_nodes)


def _infer_project_name(ctx: "SummaryContext") -> str:
    """从上下文推断项目名。"""
    if ctx.repo_url:
        # 从 URL 提取项目名
        parts = ctx.repo_url.rstrip("/").split("/")
        if parts:
            return parts[-1]

    # 从 clone_result.repo_path 提取
    path = ctx.clone_result.repo_path
    if path:
        return path.rstrip("/").split("/")[-1]

    return "未知项目"
