"""dependency_graph — 基于 NetworkX 构建代码依赖关系图。"""

from dataclasses import dataclass, field

import networkx as nx
import structlog

from src.parsers.ast_parser import ParseResult, CallInfo

logger = structlog.get_logger()


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

    def build(self, parse_results: list[ParseResult]) -> "DependencyGraph":
        """从解析结果构建依赖图。

        Args:
            parse_results: ast_parser 的输出列表。

        Returns:
            self，支持链式调用。
        """
        # 第一遍: 注册所有函数/类节点
        for pr in parse_results:
            file_funcs = set()
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

            self._file_functions[pr.file_path] = file_funcs

        # 第二遍: 添加调用关系边
        for pr in parse_results:
            for call in pr.calls:
                caller_id = self._resolve_node(pr.file_path, call.caller_func, pr)
                callee_id = self._resolve_callee(pr, call, parse_results)

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

    def to_mermaid(self, level: str = "module") -> str:
        """生成 Mermaid flowchart 图。

        Args:
            level: "module" 生成模块级图，"function" 生成函数级图。

        Returns:
            Mermaid graph TD 字符串。
        """
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

    def _resolve_callee(self, caller_pr: ParseResult, call: CallInfo,
                        all_results: list[ParseResult]) -> str | None:
        """解析被调用函数的节点 ID。"""
        callee_name = call.callee_name

        # 1. 本文件内查找
        direct = f"{caller_pr.file_path}::{callee_name}"
        if direct in self.graph:
            return direct

        # 2. 本文件的类方法
        for cls in caller_pr.classes:
            candidate = f"{caller_pr.file_path}::{cls.name}.{callee_name}"
            if candidate in self.graph:
                return candidate

        # 3. 跨文件查找（通过 import 关系）
        for imp in caller_pr.imports:
            if callee_name in imp.names or callee_name == imp.module.split(".")[-1]:
                for pr in all_results:
                    candidate = f"{pr.file_path}::{callee_name}"
                    if candidate in self.graph:
                        return candidate
                    for cls in pr.classes:
                        candidate = f"{pr.file_path}::{cls.name}.{callee_name}"
                        if candidate in self.graph:
                            return candidate

        # 4. 全局搜索（函数名匹配）
        for pr in all_results:
            if pr.file_path == caller_pr.file_path:
                continue
            candidate = f"{pr.file_path}::{callee_name}"
            if candidate in self.graph:
                return candidate

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
