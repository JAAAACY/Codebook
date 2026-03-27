# Sprint 3: Mermaid 分层展示设计方案

**日期**: 2026-03-27
**关联决策**: D-002（已确认：分层展示，顶层 <30 nodes，点击展开子模块，Mermaid subgraph）
**状态**: 待实现

---

## 一、问题诊断

### 现状数据（FastAPI 仓库）

| 指标 | 当前值 | 目标值 |
|------|--------|--------|
| 模块图节点数 | 85 | 顶层 ≤ 30 |
| 模块图边数 | 187 | 顶层 ≤ 60 |
| Mermaid 输出行数 | 273 | 顶层 ≤ 80 |
| 可读性 | 密集不可读 | 一眼看清主架构 |

### 根因

1. **模块粒度过细**: `module_grouper` 按 `top_dir/sub_dir` 二级目录拆分，FastAPI 的 `docs_src/` 下有 70+ 子目录各成一个模块。
2. **无层级折叠**: 所有模块平铺到同一层，小项目没问题，大项目 Mermaid 图直接爆炸。
3. **无聚合能力**: 同一顶层目录下的子模块之间没有"父→子"关系，无法折叠。

---

## 二、设计方案

### 核心思路：两级 Mermaid 图

```
Level 0 (顶层概览)       Level 1 (模块展开)
┌─────────────────┐     ┌──────────────────────┐
│ fastapi [5]     │     │ fastapi/             │
│ docs_src [70]   │──→  │   _compat            │
│ tests [1]       │     │   dependencies        │
│ scripts [2]     │     │   middleware          │
│ config [1]      │     │   openapi             │
└─────────────────┘     │   security            │
                        └──────────────────────┘
```

**Level 0（顶层概览图）**: 将同一顶层目录下的子模块聚合为一个"超级节点"，标注内含子模块数量。边数也聚合（子模块间的跨组调用合并为组间边）。保证节点数 ≤ 30。

**Level 1（模块展开图）**: 用户通过 `read_chapter` 或 `to_mermaid(focus="fastapi")` 展开某个超级节点，看到该组内的子模块及其内部依赖。

### API 变更

```python
# dependency_graph.py

def to_mermaid(
    self,
    level: str = "module",      # "module" | "function" | "overview"
    focus: str | None = None,   # 展开某个超级节点（顶层目录名）
    max_nodes: int = 30,        # 顶层图的最大节点数
) -> str:
```

- `level="overview"`: 新增，生成聚合后的顶层概览图（Level 0）
- `level="module"` + `focus="fastapi"`: 只展示 fastapi/ 下的子模块图（Level 1）
- `level="module"` 不带 focus: 保持现有行为（向后兼容）

### scan_repo 集成

```python
# scan_repo.py 输出变更

{
    "mermaid_overview": "graph TD\n  ...",       # 新增: 顶层概览图（≤30 节点）
    "mermaid_full": "graph TD\n  ...",           # 现有: 完整模块图（向后兼容）
    "expandable_groups": {                        # 新增: 可展开的组信息
        "docs_src": {"sub_modules": 70, "total_files": 389, "total_lines": 6840},
        "fastapi": {"sub_modules": 5, "total_files": 47, "total_lines": 19291},
        "scripts": {"sub_modules": 2, "total_files": 24, "total_lines": 4414},
    }
}
```

---

## 三、实现计划

### 3.1 新增: `_build_super_groups()` 方法

在 `dependency_graph.py` 中，将模块按顶层目录聚合：

```python
def _build_super_groups(self) -> dict[str, list[str]]:
    """将模块按顶层目录聚合为超级节点组。

    Returns:
        {顶层目录: [子模块名列表]}
        单模块的组直接保留原名，不聚合。
    """
    groups: dict[str, list[str]] = {}
    for node, data in self.get_module_graph().nodes(data=True):
        top = node.split("/")[0] if "/" in node else node
        groups.setdefault(top, []).append(node)
    return groups
```

### 3.2 新增: `_overview_mermaid()` 方法

生成聚合后的顶层概览图：

```
graph TD
  fastapi["fastapi (5 子模块)"]
  docs_src["docs_src (70 子模块)"]
  测试["测试"]
  配置["配置"]
  scripts["scripts (2 子模块)"]
  fastapi ==> docs_src
  fastapi --> scripts
  docs_src --> 测试
```

规则：
- 子模块数 ≤ 1 的组直接显示原名（不加计数）
- 子模块数 > 1 的组显示为 `name (N 子模块)`
- 边权重 = 组间所有子模块边的 call_count 之和
- 若聚合后仍 > max_nodes，按 total_lines 排序取 Top N，其余合并为"其他"

### 3.3 新增: `_focused_module_mermaid(focus)` 方法

展开单个超级节点的详细视图：

```
graph TD
  subgraph fastapi
    fastapi_core["fastapi (核心)"]
    fastapi___compat["_compat"]
    fastapi_dependencies["dependencies"]
    fastapi_middleware["middleware"]
    fastapi_openapi["openapi"]
    fastapi_security["security"]
  end
  %% 外部连接简化为虚线
  docs_src -.- fastapi_core
  scripts -.- fastapi_core
```

规则：
- focus 组内的子模块完整展示
- 外部模块折叠为超级节点
- 外部→内部的边用虚线表示来源方向

### 3.4 scan_repo 集成

```python
# scan_repo.py 中的变更

# 自动选择最佳展示层级
module_count = len(modules)
if module_count > 30:
    mermaid_overview = dep_graph.to_mermaid(level="overview", max_nodes=30)
    mermaid_detail = dep_graph.to_mermaid(level="module")  # 完整版备用
else:
    mermaid_overview = dep_graph.to_mermaid(level="module")  # 小项目直接用模块图
    mermaid_detail = None

# 输出新增字段
result["mermaid_overview"] = mermaid_overview
if mermaid_detail:
    result["mermaid_full"] = mermaid_detail
    result["expandable_groups"] = dep_graph.get_expandable_groups()
```

### 3.5 read_chapter 联动

`read_chapter` 已经有局部 Mermaid 图（`_build_module_local_mermaid`），无需大改。
但可以在返回中新增 `parent_group` 字段，告知用户当前模块属于哪个超级节点组。

---

## 四、测试计划

| 测试场景 | 验证点 |
|----------|--------|
| 小项目 (<30 模块) | `level="overview"` 等价于 `level="module"`，无聚合 |
| 大项目 (>30 模块) | 顶层节点 ≤ 30，子模块计数准确 |
| 边聚合 | 组间边的 call_count = 子模块边之和 |
| focus 展开 | 只展示目标组内子模块 + 外部简化连接 |
| 空图 / 单模块 | 不崩溃，合理降级 |
| 向后兼容 | `to_mermaid(level="module")` 输出不变 |
| scan_repo 输出 | 新增字段存在且结构正确 |
| read_chapter | parent_group 字段正确 |

预计新增测试: ~15 用例

---

## 五、预期效果

### FastAPI 仓库 (Before → After)

**Before (顶层)**:
- 85 节点, 187 边, 273 行 Mermaid → 不可读

**After (overview)**:
- ~8 节点 (fastapi, docs_src, scripts, 测试, 配置, ...), ~12 边, ~25 行 Mermaid → 一目了然

**After (focus="fastapi")**:
- 6 节点 (核心 + 5 子模块), ~8 边, ~20 行 Mermaid → 清晰展示内部架构

---

## 六、工作量估算

| 任务 | 预估 |
|------|------|
| `_build_super_groups` + `_overview_mermaid` | 核心逻辑 ~80 行 |
| `_focused_module_mermaid` | ~60 行 |
| `to_mermaid` API 扩展 | ~20 行 |
| `scan_repo` 集成 | ~30 行 |
| 测试 | ~15 用例, ~200 行 |
| **合计** | ~390 行新增代码 |
