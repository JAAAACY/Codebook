# Blueprint v2 Phase 2: SVG 画布引擎 + 双击下钻渲染器

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 SVG 交互式画布替换当前列表式蓝图渲染器，实现 UE5 蓝图风格的两级视图（Overview 世界地图 + 双击进入模块子页面），让 PM 能直观理解项目架构。

**Architecture:** 新建 `blueprint_renderer_v2.py`，保持与 v1 相同的公开 API（`render_blueprint_html(report_data, repo_url, total_time) -> str`）。生成的 HTML 是自包含的单文件，所有 JS/CSS 内联。SVG 画布引擎用纯 JS 实现（无外部依赖），支持节点拖拽、画布缩放/平移、贝塞尔曲线连线、双击下钻。数据来源是 Phase 1 的 `blueprint_summary`（嵌入为 `window.__BLUEPRINT_DATA`）。

**Tech Stack:** 纯 HTML/SVG/CSS/JS（零外部依赖），Python 生成器

---

### 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `src/tools/blueprint_renderer_v2.py` | 新建 | 新渲染器：组装 HTML + 内联 CSS/JS |
| `src/tools/canvas_layout.py` | 新建 | 自动布局算法：将模块/函数节点排布到画布坐标 |
| `src/tools/blueprint_renderer.py` | 修改 | `save_blueprint` 改为调用 v2 渲染器 |
| `tests/test_canvas_layout.py` | 新建 | 布局算法测试 |
| `tests/test_blueprint_renderer_v2.py` | 新建 | v2 渲染器 HTML 输出测试 |

---

### Task 1: 自动布局算法 canvas_layout.py

**Files:**
- Create: `src/tools/canvas_layout.py`
- Test: `tests/test_canvas_layout.py`

Overview 和子页面都需要将节点排布到 2D 坐标。布局算法是纯 Python 逻辑，不依赖 JS。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_canvas_layout.py
"""canvas_layout 自动布局测试。"""

import pytest
from src.tools.canvas_layout import (
    layout_overview,
    layout_module_detail,
    OverviewNode,
    OverviewEdge,
    DetailNode,
    DetailEdge,
)


class TestLayoutOverview:
    def test_single_node(self):
        modules = [{"code_path": "src/auth", "business_name": "认证系统", "description": "验证权限", "health": "green", "depends_on": [], "used_by": []}]
        connections = []
        nodes, edges = layout_overview(modules, connections)
        assert len(nodes) == 1
        assert nodes[0].x >= 0
        assert nodes[0].y >= 0
        assert nodes[0].label == "认证系统"

    def test_two_connected_nodes(self):
        modules = [
            {"code_path": "src/server", "business_name": "服务端", "description": "处理请求", "health": "green", "depends_on": [], "used_by": ["src/db"]},
            {"code_path": "src/db", "business_name": "数据库", "description": "存储数据", "health": "green", "depends_on": ["src/server"], "used_by": []},
        ]
        connections = [{"from_module": "src/server", "to_module": "src/db", "verb": "读写数据", "call_count": 5}]
        nodes, edges = layout_overview(modules, connections)
        assert len(nodes) == 2
        assert len(edges) == 1
        # 有连接的两个节点应有不同的 x 坐标（从左到右）
        server = next(n for n in nodes if n.id == "src/server")
        db = next(n for n in nodes if n.id == "src/db")
        assert server.x < db.x  # 被依赖者在左

    def test_nodes_dont_overlap(self):
        modules = [
            {"code_path": f"mod{i}", "business_name": f"模块{i}", "description": "", "health": "green", "depends_on": [], "used_by": []}
            for i in range(10)
        ]
        nodes, _ = layout_overview(modules, [])
        # 任意两个节点的中心距离应 > 节点最小间距
        for i, a in enumerate(nodes):
            for b in nodes[i+1:]:
                dist = ((a.x - b.x)**2 + (a.y - b.y)**2) ** 0.5
                assert dist > 100, f"Nodes {a.id} and {b.id} overlap"

    def test_health_color(self):
        modules = [
            {"code_path": "a", "business_name": "A", "description": "", "health": "red", "depends_on": [], "used_by": []},
            {"code_path": "b", "business_name": "B", "description": "", "health": "green", "depends_on": [], "used_by": []},
        ]
        nodes, _ = layout_overview(modules, [])
        red_node = next(n for n in nodes if n.id == "a")
        green_node = next(n for n in nodes if n.id == "b")
        assert red_node.color != green_node.color


class TestLayoutModuleDetail:
    def test_lays_out_functions(self):
        functions = [
            {"code_name": "check_perm", "business_name": "验证权限", "explanation": "检查权限", "file_path": "auth.py", "line_start": 10, "params": ["user_id"], "return_type": "bool"},
            {"code_name": "create_session", "business_name": "创建会话", "explanation": "新建会话", "file_path": "auth.py", "line_start": 30, "params": ["user"], "return_type": "Session"},
        ]
        callers_map = {"check_perm": ["server/handle_request"], "create_session": []}
        callees_map = {"check_perm": ["db/query"], "create_session": ["check_perm"]}
        nodes, edges = layout_module_detail(functions, callers_map, callees_map)
        assert len(nodes) == 2
        for n in nodes:
            assert n.x >= 0
            assert n.y >= 0
            assert n.business_name != ""
            assert n.explanation != ""

    def test_edges_between_connected_functions(self):
        functions = [
            {"code_name": "a", "business_name": "A", "explanation": "", "file_path": "f.py", "line_start": 1, "params": [], "return_type": None},
            {"code_name": "b", "business_name": "B", "explanation": "", "file_path": "f.py", "line_start": 10, "params": [], "return_type": None},
        ]
        callers_map = {"a": [], "b": ["a"]}
        callees_map = {"a": ["b"], "b": []}
        nodes, edges = layout_module_detail(functions, callers_map, callees_map)
        assert len(edges) >= 1
        assert edges[0].from_id == "a"
        assert edges[0].to_id == "b"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/jacky/Desktop/Codebook/mcp-server && python3 -m pytest tests/test_canvas_layout.py -v`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 3: 实现布局算法**

```python
# src/tools/canvas_layout.py
"""canvas_layout — 蓝图画布自动布局算法。

将 BlueprintSummary 中的模块和函数排布到 2D 坐标，
供 SVG 渲染器使用。
"""

from __future__ import annotations

from dataclasses import dataclass


# ── 数据结构 ─────────────────────────────────────────────


@dataclass
class OverviewNode:
    """Overview 页的模块节点。"""
    id: str           # code_path
    label: str        # business_name
    description: str
    health: str
    color: str        # 边框颜色
    x: float
    y: float
    width: float = 220
    height: float = 80


@dataclass
class OverviewEdge:
    """Overview 页的模块间连线。"""
    from_id: str
    to_id: str
    verb: str
    call_count: int = 0


@dataclass
class DetailNode:
    """子页面的函数节点。"""
    id: str           # code_name
    business_name: str
    code_name: str
    file_path: str
    line_start: int
    explanation: str
    params: list[str]
    return_type: str | None
    x: float
    y: float
    width: float = 280
    height: float = 140


@dataclass
class DetailEdge:
    """子页面的函数间连线。"""
    from_id: str
    to_id: str
    label: str = ""


# ── 颜色常量 ─────────────────────────────────────────────

_HEALTH_COLORS = {
    "green": "#10b981",
    "yellow": "#f59e0b",
    "red": "#ef4444",
}

_DEFAULT_COLOR = "#6366f1"


# ── Overview 布局 ────────────────────────────────────────


def layout_overview(
    modules: list[dict],
    connections: list[dict],
) -> tuple[list[OverviewNode], list[OverviewEdge]]:
    """为 Overview 页排布模块节点。

    使用拓扑排序 + 分层布局：
    - 入度为 0 的模块在最左列
    - 按依赖关系逐层向右排列
    - 同层内垂直均匀分布

    Args:
        modules: BlueprintSummary.modules 的 dict 列表。
        connections: BlueprintSummary.connections 的 dict 列表。

    Returns:
        (nodes, edges)
    """
    if not modules:
        return [], []

    # 构建邻接表
    module_ids = {m["code_path"] for m in modules}
    outgoing: dict[str, list[str]] = {m["code_path"]: [] for m in modules}
    incoming: dict[str, list[str]] = {m["code_path"]: [] for m in modules}

    valid_edges: list[dict] = []
    for c in connections:
        src = c.get("from_module", "")
        dst = c.get("to_module", "")
        if src in module_ids and dst in module_ids and src != dst:
            outgoing[src].append(dst)
            incoming[dst].append(src)
            valid_edges.append(c)

    # 拓扑分层（Kahn's algorithm 变体）
    in_degree = {mid: len(incoming[mid]) for mid in module_ids}
    layers: list[list[str]] = []
    remaining = set(module_ids)

    while remaining:
        # 当前层：入度为 0 的节点
        current = [mid for mid in remaining if in_degree.get(mid, 0) == 0]
        if not current:
            # 有环，把剩余的都放到当前层
            current = sorted(remaining)
        current.sort()
        layers.append(current)
        for mid in current:
            remaining.discard(mid)
            for dst in outgoing.get(mid, []):
                if dst in remaining:
                    in_degree[dst] = in_degree.get(dst, 0) - 1

    # 计算坐标
    node_width = 220
    node_height = 80
    h_gap = 120  # 层间水平间距
    v_gap = 40   # 同层垂直间距
    margin = 60

    module_map = {m["code_path"]: m for m in modules}
    nodes: list[OverviewNode] = []
    id_to_node: dict[str, OverviewNode] = {}

    for col, layer in enumerate(layers):
        x = margin + col * (node_width + h_gap)
        total_height = len(layer) * node_height + (len(layer) - 1) * v_gap
        start_y = margin + max(0, (400 - total_height) / 2)  # 居中

        for row, mid in enumerate(layer):
            y = start_y + row * (node_height + v_gap)
            m = module_map.get(mid, {})
            health = m.get("health", "green")
            node = OverviewNode(
                id=mid,
                label=m.get("business_name", mid),
                description=m.get("description", ""),
                health=health,
                color=_HEALTH_COLORS.get(health, _DEFAULT_COLOR),
                x=x,
                y=y,
                width=node_width,
                height=node_height,
            )
            nodes.append(node)
            id_to_node[mid] = node

    edges = [
        OverviewEdge(
            from_id=c.get("from_module", ""),
            to_id=c.get("to_module", ""),
            verb=c.get("verb", "调用"),
            call_count=c.get("call_count", 0),
        )
        for c in valid_edges
    ]

    return nodes, edges


# ── 子页面布局 ───────────────────────────────────────────


def layout_module_detail(
    functions: list[dict],
    callers_map: dict[str, list[str]],
    callees_map: dict[str, list[str]],
) -> tuple[list[DetailNode], list[DetailEdge]]:
    """为模块子页面排布函数节点。

    简单网格布局：按函数出现顺序从上到下、从左到右排列。
    有调用关系的函数对生成 edges。

    Args:
        functions: FunctionSummary 的 dict 列表。
        callers_map: {func_name: [caller_names]}
        callees_map: {func_name: [callee_names]}

    Returns:
        (nodes, edges)
    """
    if not functions:
        return [], []

    node_width = 280
    node_height = 140
    h_gap = 80
    v_gap = 40
    margin = 60
    cols = 3  # 每行最多 3 个节点

    func_ids = {f["code_name"] for f in functions}
    nodes: list[DetailNode] = []

    for i, f in enumerate(functions):
        col = i % cols
        row = i // cols
        x = margin + col * (node_width + h_gap)
        y = margin + row * (node_height + v_gap)

        nodes.append(DetailNode(
            id=f["code_name"],
            business_name=f.get("business_name", f["code_name"]),
            code_name=f["code_name"],
            file_path=f.get("file_path", ""),
            line_start=f.get("line_start", 0),
            explanation=f.get("explanation", ""),
            params=f.get("params", []),
            return_type=f.get("return_type"),
            x=x,
            y=y,
            width=node_width,
            height=node_height,
        ))

    # 生成内部调用边
    edges: list[DetailEdge] = []
    seen = set()
    for f in functions:
        fname = f["code_name"]
        for callee in callees_map.get(fname, []):
            # callee 可能是 "module/func" 格式，取最后一部分
            callee_short = callee.split("/")[-1] if "/" in callee else callee
            if callee_short in func_ids and (fname, callee_short) not in seen:
                edges.append(DetailEdge(from_id=fname, to_id=callee_short))
                seen.add((fname, callee_short))

    return nodes, edges
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /Users/jacky/Desktop/Codebook/mcp-server && python3 -m pytest tests/test_canvas_layout.py -v`
Expected: ALL PASS

- [ ] **Step 5: 提交**

```bash
cd /Users/jacky/Desktop/Codebook
git add mcp-server/src/tools/canvas_layout.py mcp-server/tests/test_canvas_layout.py
git commit -m "feat: canvas layout algorithm for blueprint v2 overview and detail views"
```

---

### Task 2: SVG 画布渲染器 — Overview 页

**Files:**
- Create: `src/tools/blueprint_renderer_v2.py`
- Test: `tests/test_blueprint_renderer_v2.py`

这是最大的 Task。生成一个自包含 HTML 文件，包含 SVG 画布引擎。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_blueprint_renderer_v2.py
"""blueprint_renderer_v2 SVG 画布渲染器测试。"""

import pytest
from src.tools.blueprint_renderer_v2 import render_blueprint_v2


def _make_report_data():
    """构造最小 report_data（含 blueprint_summary）。"""
    return {
        "overview": {"stats": {"files": 10, "modules": 3}, "mermaid_diagram": ""},
        "module_cards": [],
        "role": "pm",
        "blueprint_summary": {
            "project_name": "测试项目",
            "project_description": "一个用于测试的项目",
            "modules": [
                {
                    "code_path": "src/server",
                    "business_name": "服务端",
                    "description": "处理请求",
                    "health": "green",
                    "functions": [
                        {"code_name": "handle", "business_name": "处理请求", "explanation": "接收并处理 HTTP 请求", "file_path": "server.py", "line_start": 10, "params": ["request"], "return_type": "Response"},
                    ],
                    "depends_on": [],
                    "used_by": ["src/db"],
                },
                {
                    "code_path": "src/db",
                    "business_name": "数据库",
                    "description": "存储数据",
                    "health": "green",
                    "functions": [
                        {"code_name": "query", "business_name": "查询数据", "explanation": "执行 SQL 查询", "file_path": "db.py", "line_start": 5, "params": ["sql"], "return_type": "list"},
                    ],
                    "depends_on": ["src/server"],
                    "used_by": [],
                },
            ],
            "connections": [
                {"from_module": "src/server", "to_module": "src/db", "verb": "读写数据", "call_count": 5},
            ],
        },
    }


class TestRenderBlueprintV2:
    def test_returns_valid_html(self):
        html = render_blueprint_v2(_make_report_data())
        assert html.startswith("<!DOCTYPE html>")
        assert "</html>" in html

    def test_contains_svg_canvas(self):
        html = render_blueprint_v2(_make_report_data())
        assert "<svg" in html
        assert "viewBox" in html or "viewbox" in html.lower()

    def test_embeds_blueprint_data(self):
        html = render_blueprint_v2(_make_report_data())
        assert "__BLUEPRINT_DATA" in html
        assert "测试项目" in html

    def test_contains_project_name(self):
        html = render_blueprint_v2(_make_report_data(), repo_url="https://github.com/test/repo")
        assert "测试项目" in html

    def test_contains_module_nodes(self):
        html = render_blueprint_v2(_make_report_data())
        assert "服务端" in html
        assert "数据库" in html

    def test_contains_connection_verbs(self):
        html = render_blueprint_v2(_make_report_data())
        assert "读写数据" in html

    def test_contains_canvas_js_functions(self):
        html = render_blueprint_v2(_make_report_data())
        # 画布核心 JS 函数
        assert "handleZoom" in html or "onWheel" in html
        assert "dblclick" in html  # 双击下钻

    def test_contains_detail_view_js(self):
        html = render_blueprint_v2(_make_report_data())
        assert "showModuleDetail" in html or "enterModule" in html

    def test_contains_breadcrumb(self):
        html = render_blueprint_v2(_make_report_data())
        assert "breadcrumb" in html.lower() or "Overview" in html

    def test_no_external_dependencies(self):
        html = render_blueprint_v2(_make_report_data())
        # 不应引用外部 CDN（Mermaid 等）
        assert "cdnjs.cloudflare.com" not in html
        assert "unpkg.com" not in html

    def test_empty_summary_fallback(self):
        """没有 blueprint_summary 时不崩溃。"""
        data = {"overview": {"stats": {}}, "module_cards": [], "role": "pm"}
        html = render_blueprint_v2(data)
        assert "<!DOCTYPE html>" in html

    def test_chat_placeholder(self):
        """右侧对话框占位提示。"""
        html = render_blueprint_v2(_make_report_data())
        assert "MCP" in html or "对话" in html or "chat" in html.lower()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /Users/jacky/Desktop/Codebook/mcp-server && python3 -m pytest tests/test_blueprint_renderer_v2.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 SVG 画布渲染器**

创建 `src/tools/blueprint_renderer_v2.py`。这个文件是一个 Python 函数，返回一个包含完整 SVG 画布引擎的 HTML 字符串。

核心结构：
```
render_blueprint_v2(report_data, repo_url, total_time) -> str
  ├── 提取 blueprint_summary（没有则用空数据）
  ├── 调用 layout_overview() 计算 Overview 节点坐标
  ├── 为每个模块预计算 detail 节点坐标
  ├── 将所有数据序列化为 JSON 嵌入 HTML
  └── 生成 HTML 模板（CSS + SVG 画布 + JS 引擎）
```

HTML 内的 JS 引擎功能：
- 画布缩放（鼠标滚轮）和平移（拖拽空白区域）
- SVG 节点渲染（矩形 + 文字 + 引脚圆点）
- 贝塞尔曲线连线（带动词标签）
- 双击节点 → 切换到 detail 视图（清除画布，渲染函数节点）
- 面包屑导航（点击 Overview 返回）
- 右侧对话框占位面板

完整实现代码太长（约 400-500 行 Python 生成器 + 300 行内联 JS），这里给出关键骨架和所有必要细节。子代理实现时应参照此骨架，确保所有测试通过。

```python
# src/tools/blueprint_renderer_v2.py
"""blueprint_renderer_v2 — UE5 蓝图风格 SVG 画布渲染器。

生成自包含的单 HTML 文件，内联所有 CSS 和 JS。
零外部依赖。

公开 API:
    render_blueprint_v2(report_data, repo_url, total_time) -> str
"""

from __future__ import annotations

import json
from typing import Any

from src.tools.canvas_layout import (
    layout_overview,
    layout_module_detail,
)


def _safe(text: str) -> str:
    """HTML 转义。"""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def render_blueprint_v2(
    report_data: dict[str, Any],
    repo_url: str = "",
    total_time: float = 0,
) -> str:
    """渲染 Blueprint v2 交互式 SVG 画布。

    Args:
        report_data: codebook_explore 生成的 report_data（必须含 blueprint_summary）。
        repo_url: 仓库地址。
        total_time: 扫描耗时。

    Returns:
        自包含 HTML 字符串。
    """
    summary = report_data.get("blueprint_summary") or {}
    project_name = summary.get("project_name", "项目")
    project_desc = summary.get("project_description", "")
    modules = summary.get("modules", [])
    connections = summary.get("connections", [])

    # 计算 Overview 布局
    overview_nodes, overview_edges = layout_overview(modules, connections)

    # 为每个模块预计算 detail 布局
    detail_views: dict[str, dict] = {}
    for mod in modules:
        functions = mod.get("functions", [])
        if not functions:
            continue

        # 构建内部调用关系
        func_names = {f["code_name"] for f in functions}
        callers_map: dict[str, list[str]] = {}
        callees_map: dict[str, list[str]] = {}
        # 从 call_chains 数据构建（如果可用）
        for f in functions:
            callers_map[f["code_name"]] = []
            callees_map[f["code_name"]] = []

        # 从 report_data 的 module_cards 提取 call_chains
        for card in report_data.get("module_cards", []):
            if card.get("name") == mod["code_path"]:
                for chain in card.get("call_chains", []):
                    fn = chain.get("function", "")
                    if fn in func_names:
                        callers_map[fn] = chain.get("callers", [])
                        callees_map[fn] = chain.get("callees", [])

        detail_nodes, detail_edges = layout_module_detail(functions, callers_map, callees_map)
        detail_views[mod["code_path"]] = {
            "business_name": mod.get("business_name", mod["code_path"]),
            "nodes": [vars(n) for n in detail_nodes],
            "edges": [vars(e) for e in detail_edges],
        }

    # 序列化为 JSON
    blueprint_data = {
        "project_name": project_name,
        "project_description": project_desc,
        "overview": {
            "nodes": [vars(n) for n in overview_nodes],
            "edges": [vars(e) for e in overview_edges],
        },
        "details": detail_views,
    }
    data_json = json.dumps(blueprint_data, ensure_ascii=False).replace("</", "<\\/")

    # 生成 HTML
    return _build_html(data_json, project_name, project_desc, repo_url, total_time)


def _build_html(
    data_json: str,
    project_name: str,
    project_desc: str,
    repo_url: str,
    total_time: float,
) -> str:
    """组装完整 HTML。"""
    safe_name = _safe(project_name)
    safe_desc = _safe(project_desc)
    safe_url = _safe(repo_url)

    return f'''<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CodeBook — {safe_name}</title>
<style>
{_CSS}
</style>
</head>
<body>
<div id="header">
  <div class="header-left">
    <span class="logo">CodeBook</span>
    <span class="breadcrumb" id="breadcrumb">
      <span class="bc-item bc-active" id="bc-overview" onclick="showOverview()">Overview</span>
      <span class="bc-sep" id="bc-sep" style="display:none"> / </span>
      <span class="bc-item" id="bc-module" style="display:none"></span>
    </span>
  </div>
  <div class="header-right">
    <span class="project-name">{safe_name}</span>
    <span class="project-desc">{safe_desc}</span>
  </div>
</div>

<div id="canvas-container">
  <svg id="canvas" xmlns="http://www.w3.org/2000/svg"></svg>
</div>

<div id="chat-panel" class="chat-collapsed">
  <div class="chat-toggle" onclick="toggleChat()">💬</div>
  <div class="chat-body">
    <div class="chat-header">对话助手</div>
    <div class="chat-content">
      <p class="chat-placeholder">连接 MCP 后可用。<br>可以询问任何关于项目的问题。</p>
    </div>
  </div>
</div>

<script>
var __BLUEPRINT_DATA = {data_json};
{_JS}
</script>
</body>
</html>'''


# ── CSS ──────────────────────────────────────────────────

_CSS = '''
* { margin: 0; padding: 0; box-sizing: border-box; }
html, body { width: 100%; height: 100%; overflow: hidden; background: #0a0b10; color: #e2e8f0; font-family: 'Inter', -apple-system, system-ui, sans-serif; }

#header { position: fixed; top: 0; left: 0; right: 0; height: 48px; background: #13151f; border-bottom: 1px solid #252838; display: flex; align-items: center; justify-content: space-between; padding: 0 20px; z-index: 100; }
.header-left { display: flex; align-items: center; gap: 16px; }
.header-right { display: flex; align-items: center; gap: 12px; }
.logo { font-size: 18px; font-weight: 800; background: linear-gradient(135deg, #6366f1, #818cf8); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.breadcrumb { font-size: 14px; color: #8892b0; }
.bc-item { cursor: pointer; transition: color 0.15s; }
.bc-item:hover { color: #e2e8f0; }
.bc-active { color: #6366f1; font-weight: 600; }
.bc-sep { color: #5a6380; margin: 0 4px; }
.project-name { font-size: 14px; font-weight: 600; color: #e2e8f0; }
.project-desc { font-size: 12px; color: #5a6380; max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

#canvas-container { position: fixed; top: 48px; left: 0; right: 0; bottom: 0; overflow: hidden; cursor: grab; }
#canvas-container.dragging { cursor: grabbing; }
#canvas { width: 100%; height: 100%; }

/* Overview 节点 */
.ov-node { cursor: pointer; }
.ov-node:hover .ov-bg { filter: brightness(1.2); }
.ov-bg { rx: 12; ry: 12; fill: #13151f; stroke-width: 2; transition: filter 0.15s; }
.ov-label { fill: #e2e8f0; font-size: 15px; font-weight: 700; font-family: inherit; }
.ov-desc { fill: #8892b0; font-size: 11px; font-family: inherit; }
.ov-pin { r: 5; fill: #5a6380; stroke: #252838; stroke-width: 1; }

/* Detail 节点 */
.dt-node { cursor: default; }
.dt-bg { rx: 10; ry: 10; fill: #13151f; stroke: #252838; stroke-width: 1.5; }
.dt-biz-name { fill: #818cf8; font-size: 13px; font-weight: 700; font-family: inherit; }
.dt-code { fill: #8892b0; font-size: 11px; font-family: 'JetBrains Mono', 'Fira Code', monospace; }
.dt-explain { fill: #5a6380; font-size: 10px; font-family: inherit; }
.dt-pin { r: 4; fill: #5a6380; stroke: #252838; stroke-width: 1; }

/* 连线 */
.edge-line { fill: none; stroke: #3a3f55; stroke-width: 1.5; }
.edge-line-strong { stroke-width: 2.5; stroke: #6366f1; }
.edge-label { fill: #5a6380; font-size: 10px; font-family: inherit; }

/* 对话框 */
#chat-panel { position: fixed; top: 48px; right: 0; bottom: 0; width: 320px; background: #13151f; border-left: 1px solid #252838; z-index: 50; transition: transform 0.25s ease; }
#chat-panel.chat-collapsed { transform: translateX(280px); }
.chat-toggle { position: absolute; left: -40px; top: 12px; width: 36px; height: 36px; background: #1a1d2b; border: 1px solid #252838; border-radius: 8px 0 0 8px; display: flex; align-items: center; justify-content: center; cursor: pointer; font-size: 18px; }
.chat-body { padding: 16px; height: 100%; overflow-y: auto; }
.chat-header { font-size: 14px; font-weight: 600; color: #e2e8f0; margin-bottom: 12px; }
.chat-placeholder { font-size: 13px; color: #5a6380; line-height: 1.6; }
'''


# ── JS 引擎 ──────────────────────────────────────────────

_JS = '''
(function() {
  var data = __BLUEPRINT_DATA;
  var svg = document.getElementById("canvas");
  var container = document.getElementById("canvas-container");
  var currentView = "overview";  // "overview" | module code_path

  // ── 画布变换状态 ──
  var scale = 1;
  var panX = 0, panY = 0;
  var isDragging = false;
  var dragStartX, dragStartY, dragPanX, dragPanY;

  // ── 初始化 ──
  function init() {
    renderOverview();
    bindCanvasEvents();
  }

  // ── 画布事件 ──
  function bindCanvasEvents() {
    container.addEventListener("wheel", function(e) {
      e.preventDefault();
      var rect = container.getBoundingClientRect();
      var mx = e.clientX - rect.left;
      var my = e.clientY - rect.top;
      var delta = e.deltaY > 0 ? 0.9 : 1.1;
      var newScale = Math.max(0.2, Math.min(3, scale * delta));
      // 缩放时保持鼠标位置不变
      panX = mx - (mx - panX) * (newScale / scale);
      panY = my - (my - panY) * (newScale / scale);
      scale = newScale;
      applyTransform();
    }, {passive: false});

    container.addEventListener("mousedown", function(e) {
      if (e.target === container || e.target === svg || e.target.tagName === "svg") {
        isDragging = true;
        dragStartX = e.clientX;
        dragStartY = e.clientY;
        dragPanX = panX;
        dragPanY = panY;
        container.classList.add("dragging");
      }
    });

    window.addEventListener("mousemove", function(e) {
      if (!isDragging) return;
      panX = dragPanX + (e.clientX - dragStartX);
      panY = dragPanY + (e.clientY - dragStartY);
      applyTransform();
    });

    window.addEventListener("mouseup", function() {
      isDragging = false;
      container.classList.remove("dragging");
    });
  }

  function applyTransform() {
    var g = svg.querySelector("#canvas-root");
    if (g) g.setAttribute("transform", "translate(" + panX + "," + panY + ") scale(" + scale + ")");
  }

  // ── Overview 渲染 ──
  function renderOverview() {
    currentView = "overview";
    scale = 1; panX = 40; panY = 20;
    var nodes = data.overview.nodes;
    var edges = data.overview.edges;

    var html = '<g id="canvas-root" transform="translate(40,20)">';

    // 先画连线
    var nodeMap = {};
    nodes.forEach(function(n) { nodeMap[n.id] = n; });

    edges.forEach(function(e) {
      var from = nodeMap[e.from_id];
      var to = nodeMap[e.to_id];
      if (!from || !to) return;
      var x1 = from.x + from.width;
      var y1 = from.y + from.height / 2;
      var x2 = to.x;
      var y2 = to.y + to.height / 2;
      var cx = (x1 + x2) / 2;
      var cls = e.call_count >= 5 ? "edge-line edge-line-strong" : "edge-line";
      html += '<path class="' + cls + '" d="M' + x1 + ',' + y1 + ' C' + cx + ',' + y1 + ' ' + cx + ',' + y2 + ' ' + x2 + ',' + y2 + '"/>';
      // 连线标签
      var lx = (x1 + x2) / 2;
      var ly = (y1 + y2) / 2 - 8;
      html += '<text class="edge-label" x="' + lx + '" y="' + ly + '" text-anchor="middle">' + esc(e.verb) + '</text>';
    });

    // 再画节点
    nodes.forEach(function(n) {
      html += '<g class="ov-node" ondblclick="enterModule(\\'' + esc(n.id) + '\\')">';
      html += '<rect class="ov-bg" x="' + n.x + '" y="' + n.y + '" width="' + n.width + '" height="' + n.height + '" stroke="' + n.color + '"/>';
      html += '<text class="ov-label" x="' + (n.x + 16) + '" y="' + (n.y + 28) + '">' + esc(n.label) + '</text>';
      // 截断描述
      var desc = n.description.length > 20 ? n.description.substring(0, 20) + "..." : n.description;
      html += '<text class="ov-desc" x="' + (n.x + 16) + '" y="' + (n.y + 48) + '">' + esc(desc) + '</text>';
      // 引脚
      html += '<circle class="ov-pin" cx="' + n.x + '" cy="' + (n.y + n.height / 2) + '"/>';
      html += '<circle class="ov-pin" cx="' + (n.x + n.width) + '" cy="' + (n.y + n.height / 2) + '"/>';
      html += '</g>';
    });

    html += '</g>';
    svg.innerHTML = html;

    // 更新面包屑
    document.getElementById("bc-overview").className = "bc-item bc-active";
    document.getElementById("bc-sep").style.display = "none";
    document.getElementById("bc-module").style.display = "none";
  }

  // ── Detail 渲染 ──
  window.enterModule = function(moduleId) {
    var detail = data.details[moduleId];
    if (!detail) return;

    currentView = moduleId;
    scale = 1; panX = 40; panY = 20;
    var nodes = detail.nodes;
    var edges = detail.edges;

    var html = '<g id="canvas-root" transform="translate(40,20)">';

    // 节点映射
    var nodeMap = {};
    nodes.forEach(function(n) { nodeMap[n.id] = n; });

    // 连线
    edges.forEach(function(e) {
      var from = nodeMap[e.from_id];
      var to = nodeMap[e.to_id];
      if (!from || !to) return;
      var x1 = from.x + from.width;
      var y1 = from.y + from.height / 2;
      var x2 = to.x;
      var y2 = to.y + to.height / 2;
      var cx = (x1 + x2) / 2;
      html += '<path class="edge-line" d="M' + x1 + ',' + y1 + ' C' + cx + ',' + y1 + ' ' + cx + ',' + y2 + ' ' + x2 + ',' + y2 + '"/>';
      if (e.label) {
        var lx = (x1 + x2) / 2;
        var ly = (y1 + y2) / 2 - 6;
        html += '<text class="edge-label" x="' + lx + '" y="' + ly + '" text-anchor="middle">' + esc(e.label) + '</text>';
      }
    });

    // 函数节点
    nodes.forEach(function(n) {
      var h = n.height;
      html += '<g class="dt-node">';
      html += '<rect class="dt-bg" x="' + n.x + '" y="' + n.y + '" width="' + n.width + '" height="' + h + '"/>';
      // 业务名（高亮）
      html += '<text class="dt-biz-name" x="' + (n.x + 12) + '" y="' + (n.y + 22) + '">' + esc(n.business_name) + '</text>';
      // 函数名 + 文件
      html += '<text class="dt-code" x="' + (n.x + 12) + '" y="' + (n.y + 40) + '">' + esc(n.code_name) + '()</text>';
      html += '<text class="dt-code" x="' + (n.x + 12) + '" y="' + (n.y + 54) + '">' + esc(n.file_path) + ':' + n.line_start + '</text>';
      // 实现逻辑解释
      var lines = wordWrap(n.explanation, 35);
      for (var i = 0; i < Math.min(lines.length, 3); i++) {
        html += '<text class="dt-explain" x="' + (n.x + 12) + '" y="' + (n.y + 72 + i * 14) + '">' + esc(lines[i]) + '</text>';
      }
      // 引脚
      html += '<circle class="dt-pin" cx="' + n.x + '" cy="' + (n.y + h / 2) + '"/>';
      html += '<circle class="dt-pin" cx="' + (n.x + n.width) + '" cy="' + (n.y + h / 2) + '"/>';
      // 参数引脚标签
      if (n.params && n.params.length > 0) {
        for (var p = 0; p < Math.min(n.params.length, 3); p++) {
          html += '<text class="dt-explain" x="' + (n.x - 4) + '" y="' + (n.y + h/2 - 10 + p * 12) + '" text-anchor="end">' + esc(n.params[p]) + '</text>';
        }
      }
      if (n.return_type) {
        html += '<text class="dt-explain" x="' + (n.x + n.width + 4) + '" y="' + (n.y + h/2 + 4) + '">' + esc(n.return_type) + '</text>';
      }
      html += '</g>';
    });

    html += '</g>';
    svg.innerHTML = html;

    // 更新面包屑
    document.getElementById("bc-overview").className = "bc-item";
    document.getElementById("bc-sep").style.display = "inline";
    var bcMod = document.getElementById("bc-module");
    bcMod.style.display = "inline";
    bcMod.className = "bc-item bc-active";
    bcMod.textContent = detail.business_name;
  };

  window.showOverview = function() {
    renderOverview();
  };

  window.toggleChat = function() {
    document.getElementById("chat-panel").classList.toggle("chat-collapsed");
  };

  // ── 工具函数 ──
  function esc(s) {
    if (!s) return "";
    return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
  }

  function wordWrap(text, maxChars) {
    if (!text) return [""];
    var result = [];
    var remaining = text;
    while (remaining.length > maxChars) {
      var cut = remaining.lastIndexOf("，", maxChars);
      if (cut < maxChars / 2) cut = remaining.lastIndexOf(" ", maxChars);
      if (cut < maxChars / 2) cut = maxChars;
      result.push(remaining.substring(0, cut));
      remaining = remaining.substring(cut);
    }
    if (remaining) result.push(remaining);
    return result;
  }

  // ── 启动 ──
  init();
})();
'''
```

注意：上面的 JS 中使用了 `\\\'` 在 f-string 中转义单引号。实际实现时需要注意 Python f-string 和 JS 字符串转义的交互。建议把 `_CSS` 和 `_JS` 作为模块级常量字符串（非 f-string），在 `_build_html` 中用 `{_CSS}` 和 `{_JS}` 插入。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /Users/jacky/Desktop/Codebook/mcp-server && python3 -m pytest tests/test_blueprint_renderer_v2.py -v`
Expected: ALL PASS

- [ ] **Step 5: 提交**

```bash
cd /Users/jacky/Desktop/Codebook
git add mcp-server/src/tools/blueprint_renderer_v2.py mcp-server/tests/test_blueprint_renderer_v2.py
git commit -m "feat: SVG canvas renderer v2 with overview and detail views"
```

---

### Task 3: 切换 save_blueprint 到 v2 渲染器

**Files:**
- Modify: `src/tools/blueprint_renderer.py`
- Modify: `src/tools/codebook_explore.py`

- [ ] **Step 1: 修改 `blueprint_renderer.py` 的 `save_blueprint` 函数**

在 `save_blueprint` 函数中，尝试先用 v2 渲染器，v2 失败时回退到 v1：

```python
# 在 save_blueprint 函数内，替换 render_blueprint_html 调用

def save_blueprint(
    report_data: dict[str, Any],
    repo_url: str = "",
    total_time: float = 0,
    output_dir: str | Path | None = None,
) -> str:
    out_dir = Path(output_dir) if output_dir else _OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    slug = _repo_slug(repo_url)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = f"{slug}_blueprint_{timestamp}.html"
    filepath = out_dir / filename

    # 优先使用 v2 画布渲染器
    html_content = None
    if report_data.get("blueprint_summary"):
        try:
            from src.tools.blueprint_renderer_v2 import render_blueprint_v2
            html_content = render_blueprint_v2(
                report_data=report_data,
                repo_url=repo_url,
                total_time=total_time,
            )
        except Exception as e:
            logger.warning("blueprint.v2_failed", error=str(e))

    # 回退到 v1
    if html_content is None:
        html_content = render_blueprint_html(
            report_data=report_data,
            repo_url=repo_url,
            total_time=total_time,
        )

    filepath.write_text(html_content, encoding="utf-8")
    logger.info(
        "blueprint.saved",
        path=str(filepath),
        size_kb=round(len(html_content) / 1024, 1),
    )

    return str(filepath)
```

- [ ] **Step 2: 运行全量测试**

Run: `cd /Users/jacky/Desktop/Codebook/mcp-server && python3 -m pytest tests/ -q`
Expected: ALL PASS

- [ ] **Step 3: 提交**

```bash
cd /Users/jacky/Desktop/Codebook
git add mcp-server/src/tools/blueprint_renderer.py
git commit -m "feat: switch save_blueprint to v2 canvas renderer with v1 fallback"
```

---

### Task 4: 端到端验证 + 视觉检查

**Files:** 无新文件

- [ ] **Step 1: 全量测试**

Run: `cd /Users/jacky/Desktop/Codebook/mcp-server && python3 -m pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 2: 用 claw-code 生成蓝图**

```bash
cd /Users/jacky/Desktop/Codebook/mcp-server
python3 -c "
import asyncio
from src.tools.codebook_explore import codebook_explore

result = asyncio.run(codebook_explore(
    repo_url='https://github.com/ultraworkers/claw-code',
    role='pm',
))
print('Blueprint:', result.get('blueprint_path', 'N/A'))
print('Status:', result.get('status'))
"
```

- [ ] **Step 3: 在浏览器中打开蓝图并验证**

```bash
open <blueprint_path>
```

验证清单：
- [ ] 页面打开显示 SVG 画布（不是列表）
- [ ] 能看到模块节点（中文业务名）
- [ ] 节点间有贝塞尔曲线连线（带动词标签）
- [ ] 鼠标滚轮缩放正常
- [ ] 拖拽画布平移正常
- [ ] 双击节点进入子页面
- [ ] 子页面显示函数级节点（三层信息）
- [ ] 面包屑导航可返回 Overview
- [ ] 右侧对话框可收起/展开
- [ ] 无外部 CDN 请求（离线可用）

- [ ] **Step 4: 提交 tag**

```bash
cd /Users/jacky/Desktop/Codebook
git tag -a blueprint-v2-phase2 -m "Blueprint v2 Phase 2: SVG canvas renderer with drill-down"
git push origin main --tags
```
