"""dependency_graph — 基于 NetworkX 构建代码依赖关系图。"""

from dataclasses import dataclass, field

import networkx as nx
import structlog

from src.parsers.ast_parser import ParseResult, CallInfo

logger = structlog.get_logger()

# ── 常量 ──────────────────────────────────────────────────
DEFAULT_MAX_OVERVIEW_NODES: int = 30
_HEAVY_EDGE_CALL_THRESHOLD: int = 5


@dataclass
class NodeAttrs:
    """依赖图节点属性。"""
    file: str
    line_start: int = 0
    line_end: int = 0
    module_group: str = ""
    node_type: str = "function"  # function | class | module


@dataclass
class EdgeAttrs:
    """依赖图边属性。"""
    data_label: str = ""
    call_count: int = 1
    is_critical_path: bool = False


class DependencyGraph:
    """代码依赖关系图。

    基于 NetworkX DiGraph 构建。
    节点: 每个 function/class，属性包含 file, line_range, module_group。
    边: 调用关系，属性包含 data_label, call_count, is_critical_path。
    """

    def __init__(self):
        self.graph = nx.DiGraph()
        self._file_functions: dict[str, set[str]] = {}  # file -> function names
        self._module_map: dict[str, str] = {}  # node_id -> module_group
        # ── Sprint 3: O(1) 查找索引 ──
        self._name_index: dict[str, list[str]] = {}  # func/class name -> [node_ids]
        self._file_class_methods: dict[str, dict[str, str]] = {}  # file -> {Class.method: node_id}
        self._method_name_index: dict[str, dict[str, str]] = {}  # file -> {method_name: node_id} for O(1) lookup
        self._module_path_index: dict[str, str] = {}  # import module path -> file_path

    def build(self, parse_results: list[ParseResult]) -> "DependencyGraph":
        """从解析结果构建依赖图。

        Args:
            parse_results: ast_parser 的输出列表。

        Returns:
            self，支持链式调用。
        """
        # 第一遍: 注册所有函数/类节点 + 构建查找索引
        for pr in parse_results:
            file_funcs = set()
            class_methods: dict[str, str] = {}
            for func in pr.functions:
                node_id = self._make_node_id(pr.file_path, func.name, func.parent_class)
                self.graph.add_node(node_id, **{
                    "file": pr.file_path,
                    "line_start": func.line_start,
                    "line_end": func.line_end,
                    "module_group": "",
                    "node_type": "method" if func.is_method else "function",
                    "label": func.name,
                })
                file_funcs.add(func.name)
                # 索引: 函数名 → node_ids
                self._name_index.setdefault(func.name, []).append(node_id)
                # 索引: 类方法 → node_id
                if func.parent_class:
                    class_methods[f"{func.parent_class}.{func.name}"] = node_id

            for cls in pr.classes:
                node_id = f"{pr.file_path}::{cls.name}"
                self.graph.add_node(node_id, **{
                    "file": pr.file_path,
                    "line_start": cls.line_start,
                    "line_end": cls.line_end,
                    "module_group": "",
                    "node_type": "class",
                    "label": cls.name,
                })
                # 索引: 类名 → node_ids
                self._name_index.setdefault(cls.name, []).append(node_id)

            self._file_functions[pr.file_path] = file_funcs
            if class_methods:
                self._file_class_methods[pr.file_path] = class_methods
                # Reverse index: method_name -> node_id for O(1) step-2/3 lookup.
                # When multiple classes in the same file share a method name, the last
                # one wins — callers should use the Class.method key if precision matters.
                self._method_name_index[pr.file_path] = {
                    cls_key.rsplit(".", 1)[1]: node_id
                    for cls_key, node_id in class_methods.items()
                }

            # 索引: import 模块路径 → file_path（用于跨文件解析）
            self._module_path_index[pr.file_path] = pr.file_path
            # 从 file_path 推断可能的模块路径 (src/parsers/foo.py → src.parsers.foo)
            module_path = pr.file_path.replace("/", ".").replace("\\", ".")
            for suffix in (".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java"):
                if module_path.endswith(suffix):
                    module_path = module_path[: -len(suffix)]
                    break
            self._module_path_index[module_path] = pr.file_path
            # 也存最后一级路径 (foo → file_path)
            parts = module_path.rsplit(".", 1)
            if len(parts) == 2:
                short_name = parts[1]
                existing = self._module_path_index.get(short_name)
                if existing is not None and existing != pr.file_path:
                    logger.debug(
                        "dependency_graph.short_name_collision",
                        short_name=short_name,
                        existing_file=existing,
                        ignored_file=pr.file_path,
                    )
                else:
                    self._module_path_index[short_name] = pr.file_path

        # 第二遍: 添加调用关系边
        for pr in parse_results:
            for call in pr.calls:
                caller_id = self._resolve_node(pr.file_path, call.caller_func, pr)
                callee_id = self._resolve_callee(pr, call)

                if caller_id and callee_id and caller_id != callee_id:
                    if self.graph.has_edge(caller_id, callee_id):
                        # 增加调用次数
                        self.graph[caller_id][callee_id]["call_count"] += 1
                    else:
                        self.graph.add_edge(caller_id, callee_id, **{
                            "data_label": self._infer_data_label(call),
                            "call_count": 1,
                            "is_critical_path": False,
                        })

        # 标记关键路径
        self._mark_critical_paths()

        logger.info(
            "dependency_graph.built",
            nodes=self.graph.number_of_nodes(),
            edges=self.graph.number_of_edges(),
        )
        return self

    def set_module_groups(self, module_map: dict[str, str]):
        """设置节点的模块分组。

        Args:
            module_map: {node_id: module_group_name}
        """
        self._module_map = module_map
        for node_id, group in module_map.items():
            if node_id in self.graph:
                self.graph.nodes[node_id]["module_group"] = group

    def get_module_graph(self) -> nx.DiGraph:
        """合并为模块级依赖图。

        Returns:
            模块级 DiGraph，节点为模块名。
        """
        module_graph = nx.DiGraph()

        # 收集所有模块
        modules = set()
        for _, data in self.graph.nodes(data=True):
            mg = data.get("module_group", "")
            if mg:
                modules.add(mg)
                module_graph.add_node(mg)

        # 合并边
        for u, v, data in self.graph.edges(data=True):
            u_mod = self.graph.nodes[u].get("module_group", "")
            v_mod = self.graph.nodes[v].get("module_group", "")
            if u_mod and v_mod and u_mod != v_mod:
                if module_graph.has_edge(u_mod, v_mod):
                    module_graph[u_mod][v_mod]["call_count"] += data.get("call_count", 1)
                else:
                    module_graph.add_edge(u_mod, v_mod, call_count=data.get("call_count", 1))

        return module_graph

    def get_upstream(self, node_id: str) -> list[str]:
        """谁调用了这个节点。"""
        if node_id not in self.graph:
            return []
        return list(self.graph.predecessors(node_id))

    def get_downstream(self, node_id: str) -> list[str]:
        """这个节点调用了谁。"""
        if node_id not in self.graph:
            return []
        return list(self.graph.successors(node_id))

    def _build_super_groups(self) -> dict[str, list[str]]:
        """将模块按顶层目录聚合为超级节点组。

        Returns:
            {顶层目录: [子模块名列表]}
            单模块的组直接保留原名，不聚合。
        """
        mg = self.get_module_graph()
        groups: dict[str, list[str]] = {}
        for node in mg.nodes:
            top = node.split("/")[0] if "/" in node else node
            groups.setdefault(top, []).append(node)
        return groups

    def get_expandable_groups(self) -> dict[str, dict[str, int]]:
        """返回可展开的超级节点组元数据。

        Returns:
            {group_name: {sub_modules: N, total_files: N, total_lines: N}}
            仅包含子模块数 > 1 的组。
        """
        super_groups = self._build_super_groups()
        result: dict[str, dict] = {}

        for group_name, sub_modules in super_groups.items():
            if len(sub_modules) <= 1:
                continue

            seen_files: set[str] = set()
            total_lines = 0
            sub_set = set(sub_modules)
            for _node_id, data in self.graph.nodes(data=True):
                mg = data.get("module_group", "")
                if mg in sub_set:
                    file_path = data.get("file", "")
                    if file_path:
                        seen_files.add(file_path)
                    total_lines += data.get("line_end", 0) - data.get("line_start", 0)
            total_files = len(seen_files)

            result[group_name] = {
                "sub_modules": len(sub_modules),
                "total_files": total_files,
                "total_lines": total_lines,
            }

        return result

    def to_mermaid(
        self,
        level: str = "module",
        focus: str | None = None,
        max_nodes: int = DEFAULT_MAX_OVERVIEW_NODES,
    ) -> str:
        """生成 Mermaid flowchart 图。

        Args:
            level: "module" 生成模块级图，"function" 生成函数级图，
                   "overview" 生成聚合后的顶层概览图。
            focus: 展开某个超级节点（顶层目录名），仅 overview 模式有效。
            max_nodes: 顶层图的最大节点数，仅 overview 模式有效。

        Returns:
            Mermaid graph TD 字符串。
        """
        if level == "overview":
            if focus:
                return self._focused_module_mermaid(focus)
            return self._overview_mermaid(max_nodes)
        if level == "module":
            return self._module_level_mermaid()
        return self._function_level_mermaid()

    # ── 私有方法 ──────────────────────────────────────────

    def _make_node_id(self, file_path: str, func_name: str, parent_class: str | None = None) -> str:
        """生成节点 ID。"""
        if parent_class:
            return f"{file_path}::{parent_class}.{func_name}"
        return f"{file_path}::{func_name}"

    def _resolve_node(self, file_path: str, func_name: str, pr: ParseResult) -> str | None:
        """解析节点 ID。"""
        if func_name == "<module>":
            return f"{file_path}::<module>"

        # 先尝试直接匹配
        direct = f"{file_path}::{func_name}"
        if direct in self.graph:
            return direct

        # 尝试类方法匹配
        for cls in pr.classes:
            candidate = f"{file_path}::{cls.name}.{func_name}"
            if candidate in self.graph:
                return candidate

        # 创建 <module> 级节点作为后备
        module_id = f"{file_path}::<module>"
        if module_id not in self.graph:
            self.graph.add_node(module_id, **{
                "file": file_path,
                "line_start": 0,
                "line_end": 0,
                "module_group": "",
                "node_type": "module",
                "label": "<module>",
            })
        return module_id

    def _resolve_callee(self, caller_pr: ParseResult, call: CallInfo) -> str | None:
        """解析被调用函数的节点 ID。

        Sprint 3 优化: 使用预构建索引替代全文件扫描，O(n²) → O(1) 查找。
        """
        callee_name = call.callee_name

        # 1. 本文件内查找 — O(1) 哈希查找
        direct = f"{caller_pr.file_path}::{callee_name}"
        if direct in self.graph:
            return direct

        # 2. 本文件的类方法 — O(1) 通过 _method_name_index 索引
        file_mn = self._method_name_index.get(caller_pr.file_path)
        if file_mn:
            node_id = file_mn.get(callee_name)
            if node_id:
                return node_id

        # 3. 跨文件查找（通过 import → 模块路径索引） — O(imports) 而非 O(n)
        for imp in caller_pr.imports:
            if callee_name in imp.names or callee_name == imp.module.split(".")[-1]:
                # 通过模块路径索引定位目标文件
                target_file = self._module_path_index.get(imp.module)
                if target_file:
                    candidate = f"{target_file}::{callee_name}"
                    if candidate in self.graph:
                        return candidate
                    # 检查目标文件的类方法 — O(1) 通过 _method_name_index
                    target_mn = self._method_name_index.get(target_file)
                    if target_mn:
                        mn_hit = target_mn.get(callee_name)
                        if mn_hit:
                            return mn_hit

        # 4. 全局索引查找 — O(候选数) 而非 O(n)
        candidates = self._name_index.get(callee_name, [])
        for node_id in candidates:
            if not node_id.startswith(f"{caller_pr.file_path}::"):
                return node_id

        return None

    def _infer_data_label(self, call: CallInfo) -> str:
        """从调用推断数据标签。"""
        # 简单策略：用被调用函数名推断
        name = call.callee_name
        if "get" in name.lower():
            return "查询数据"
        elif "create" in name.lower() or "add" in name.lower():
            return "创建数据"
        elif "update" in name.lower() or "set" in name.lower():
            return "更新数据"
        elif "delete" in name.lower() or "remove" in name.lower():
            return "删除数据"
        elif "check" in name.lower() or "verify" in name.lower() or "validate" in name.lower():
            return "校验"
        elif "send" in name.lower() or "emit" in name.lower():
            return "发送"
        return ""

    def _mark_critical_paths(self):
        """标记关键路径（入度或出度最高的路径）。"""
        if not self.graph.edges:
            return

        # 找到入口节点（无入边）和高调用次数的边
        for u, v, data in self.graph.edges(data=True):
            if data.get("call_count", 1) >= 3:
                data["is_critical_path"] = True

    def _sanitize_mermaid_id(self, text: str) -> str:
        """生成 Mermaid 安全的节点 ID。"""
        return text.replace("/", "_").replace(".", "_").replace("::", "__").replace("-", "_").replace(" ", "_")

    def _sanitize_mermaid_label(self, text: str) -> str:
        """清理 Mermaid 标签中的特殊字符。"""
        return text.replace('"', "'").replace("<", "‹").replace(">", "›")

    def _overview_mermaid(self, max_nodes: int = DEFAULT_MAX_OVERVIEW_NODES) -> str:
        """生成聚合后的顶层概览图（Level 0）。

        将子模块按顶层目录聚合为超级节点。
        若模块数 ≤ max_nodes，直接返回 module 级图。
        """
        max_nodes = max(max_nodes, 1)
        mg = self.get_module_graph()
        if not mg.nodes:
            return "graph TD\n  empty[暂无模块依赖数据]"

        # 如果模块数已在限制内，直接用 module 级图
        if len(mg.nodes) <= max_nodes:
            return self._module_level_mermaid()

        super_groups = self._build_super_groups()

        # 聚合后仍超限 → 按子模块数排序取 Top N-1，其余合并为"其他"
        if len(super_groups) > max_nodes:
            sorted_groups = sorted(
                super_groups.items(),
                key=lambda kv: len(kv[1]),
                reverse=True,
            )
            keep = dict(sorted_groups[: max_nodes - 1])
            overflow_modules: list[str] = []
            for _, subs in sorted_groups[max_nodes - 1 :]:
                overflow_modules.extend(subs)
            keep["其他"] = overflow_modules
            super_groups = keep

        # 构建超级节点标签
        lines = ["graph TD"]
        for group_name, sub_modules in super_groups.items():
            safe_id = self._sanitize_mermaid_id(group_name)
            if len(sub_modules) > 1:
                label = f"{group_name} ({len(sub_modules)} 子模块)"
            else:
                label = group_name
            lines.append(f"  {safe_id}[\"{self._sanitize_mermaid_label(label)}\"]")

        # 聚合边：将模块级边合并为超级节点间的边
        super_edges: dict[tuple[str, str], int] = {}
        module_to_super: dict[str, str] = {}
        for group_name, sub_modules in super_groups.items():
            for sm in sub_modules:
                module_to_super[sm] = group_name

        for u, v, data in mg.edges(data=True):
            u_super = module_to_super.get(u, u)
            v_super = module_to_super.get(v, v)
            if u_super != v_super:
                key = (u_super, v_super)
                super_edges[key] = super_edges.get(key, 0) + data.get("call_count", 1)

        for (u, v), count in super_edges.items():
            safe_u = self._sanitize_mermaid_id(u)
            safe_v = self._sanitize_mermaid_id(v)
            if count >= _HEAVY_EDGE_CALL_THRESHOLD:
                lines.append(f"  {safe_u} ==> {safe_v}")
            else:
                lines.append(f"  {safe_u} --> {safe_v}")

        return "\n".join(lines)

    def _focused_module_mermaid(self, focus: str) -> str:
        """展开单个超级节点的详细视图。

        focus 组内子模块完整展示（subgraph），
        外部模块折叠为超级节点，
        外部→内部的边用虚线表示。
        """
        super_groups = self._build_super_groups()
        if focus not in super_groups:
            logger.warning("dependency_graph.focus_not_found", focus=focus)
            safe_label = self._sanitize_mermaid_label(focus)
            return f"graph TD\n  empty[\"未找到模块组: {safe_label}\"]"

        mg = self.get_module_graph()
        focus_modules = set(super_groups[focus])

        # 构建 module → super_group 映射
        module_to_super: dict[str, str] = {}
        for group_name, sub_modules in super_groups.items():
            for sm in sub_modules:
                module_to_super[sm] = group_name

        lines = ["graph TD"]

        # focus 组内子模块展开为 subgraph
        safe_focus = self._sanitize_mermaid_id(focus)
        lines.append(f"  subgraph {safe_focus}[\"{self._sanitize_mermaid_label(focus)}\"]")
        for sm in sorted(focus_modules):
            safe_id = self._sanitize_mermaid_id(sm)
            lines.append(f"    {safe_id}[\"{self._sanitize_mermaid_label(sm)}\"]")
        lines.append("  end")

        # 外部超级节点（折叠）
        external_supers: set[str] = set()
        for u, v, _data in mg.edges(data=True):
            if u in focus_modules and v not in focus_modules:
                external_supers.add(module_to_super.get(v, v))
            elif v in focus_modules and u not in focus_modules:
                external_supers.add(module_to_super.get(u, u))

        for ext in sorted(external_supers):
            safe_id = self._sanitize_mermaid_id(ext)
            ext_subs = super_groups.get(ext, [ext])
            if len(ext_subs) > 1:
                label = f"{ext} ({len(ext_subs)} 子模块)"
            else:
                label = ext
            lines.append(f"  {safe_id}[\"{self._sanitize_mermaid_label(label)}\"]")

        # focus 组内部边（实线）
        for u, v, data in mg.edges(data=True):
            if u in focus_modules and v in focus_modules:
                safe_u = self._sanitize_mermaid_id(u)
                safe_v = self._sanitize_mermaid_id(v)
                count = data.get("call_count", 1)
                if count >= _HEAVY_EDGE_CALL_THRESHOLD:
                    lines.append(f"  {safe_u} ==> {safe_v}")
                else:
                    lines.append(f"  {safe_u} --> {safe_v}")

        # 外部连接（虚线）— 聚合到超级节点
        external_edges: dict[tuple[str, str], int] = {}
        for u, v, data in mg.edges(data=True):
            if u in focus_modules and v not in focus_modules:
                ext_super = module_to_super.get(v, v)
                key = (u, ext_super)
                external_edges[key] = external_edges.get(key, 0) + data.get("call_count", 1)
            elif v in focus_modules and u not in focus_modules:
                ext_super = module_to_super.get(u, u)
                key = (ext_super, v)
                external_edges[key] = external_edges.get(key, 0) + data.get("call_count", 1)

        for (u, v), _count in external_edges.items():
            safe_u = self._sanitize_mermaid_id(u)
            safe_v = self._sanitize_mermaid_id(v)
            lines.append(f"  {safe_u} -.- {safe_v}")

        return "\n".join(lines)

    def _module_level_mermaid(self) -> str:
        """生成模块级 Mermaid 图。"""
        mg = self.get_module_graph()
        if not mg.nodes:
            return "graph TD\n  empty[暂无模块依赖数据]"

        lines = ["graph TD"]
        for node in mg.nodes:
            safe_id = self._sanitize_mermaid_id(node)
            lines.append(f"  {safe_id}[{self._sanitize_mermaid_label(node)}]")

        for u, v, data in mg.edges(data=True):
            safe_u = self._sanitize_mermaid_id(u)
            safe_v = self._sanitize_mermaid_id(v)
            count = data.get("call_count", 1)
            if count >= 5:
                lines.append(f"  {safe_u} ==> {safe_v}")
            else:
                lines.append(f"  {safe_u} --> {safe_v}")

        return "\n".join(lines)

    def _function_level_mermaid(self) -> str:
        """生成函数级 Mermaid 图（带 subgraph 分组）。"""
        if not self.graph.nodes:
            return "graph TD\n  empty[暂无函数依赖数据]"

        lines = ["graph TD"]

        # 按模块分组
        groups: dict[str, list[str]] = {}
        ungrouped: list[str] = []
        for node_id, data in self.graph.nodes(data=True):
            mg = data.get("module_group", "")
            if mg:
                groups.setdefault(mg, []).append(node_id)
            else:
                ungrouped.append(node_id)

        # 渲染 subgraph
        for group_name, nodes in groups.items():
            safe_group = self._sanitize_mermaid_id(group_name)
            lines.append(f"  subgraph {safe_group}[{self._sanitize_mermaid_label(group_name)}]")
            for node_id in nodes:
                data = self.graph.nodes[node_id]
                safe_id = self._sanitize_mermaid_id(node_id)
                label = data.get("label", node_id.split("::")[-1])
                file_info = f"{data.get('file', '')}:{data.get('line_start', '')}"
                lines.append(f"    {safe_id}[\"{self._sanitize_mermaid_label(label)}\\n{file_info}\"]")
            lines.append("  end")

        # 无分组节点
        for node_id in ungrouped:
            data = self.graph.nodes[node_id]
            safe_id = self._sanitize_mermaid_id(node_id)
            label = data.get("label", node_id.split("::")[-1])
            lines.append(f"  {safe_id}[{self._sanitize_mermaid_label(label)}]")

        # 边
        for u, v, data in self.graph.edges(data=True):
            safe_u = self._sanitize_mermaid_id(u)
            safe_v = self._sanitize_mermaid_id(v)
            label = data.get("data_label", "")
            is_critical = data.get("is_critical_path", False)

            if is_critical:
                if label:
                    lines.append(f"  {safe_u} ==>|{label}| {safe_v}")
                else:
                    lines.append(f"  {safe_u} ==> {safe_v}")
            else:
                if label:
                    lines.append(f"  {safe_u} -->|{label}| {safe_v}")
                else:
                    lines.append(f"  {safe_u} --> {safe_v}")

        return "\n".join(lines)
