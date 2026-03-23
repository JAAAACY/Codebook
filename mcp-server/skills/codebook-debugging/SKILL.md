---
name: codebook-debugging
description: Use when encountering any bug, test failure, or unexpected behavior in CodeBook, before proposing fixes. Covers tree-sitter AST inspection, parser data flow tracing, and CLI config diagnostics.
---

# CodeBook 系统化调试

## 铁律

```
没有找到根因，不准提出修复方案。
```

"先改改试试" = 浪费时间 + 制造新 bug。

## 四阶段流程

### Phase 1: 根因调查

**修任何东西之前：**

1. **完整读错误信息** — 不要跳过。行号、类型、值全部看完。
2. **稳定复现** — 写出精确的复现步骤。不能复现？收集更多数据，不要猜。
3. **检查最近变更** — `git diff`，最近的 commit，新加的依赖。
4. **追踪数据流** — 错误值从哪来？一层层往上追，直到找到源头。

### Phase 2: 模式分析

1. 找到**正常工作**的类似代码
2. 逐项对比异常路径和正常路径的差异
3. 列出每个差异，不假设"这个不可能有关"

### Phase 3: 假设 + 测试

1. 明确假设："我认为 X 是根因，因为 Y"
2. 做**最小改动**验证假设
3. 一次只改一个变量
4. 没验证就不叠加第二个修复

**如果连续 3 次修复失败：停下来质疑架构，不要再试第 4 次。**

### Phase 4: 实现修复

1. **先写回归测试**复现 bug（用 `codebook-tdd` skill）
2. 看着测试失败
3. 实现修复
4. 看着测试通过
5. 跑全量回归
6. **派子代理审查**（用 `codebook-dev-workflow` skill Phase 5）— 修复者不能审查自己的修复

**门禁：** 子代理审查未通过，不得提交。

## CodeBook 专用调试工具箱

### 工具 1: Tree-sitter AST 打印

遇到解析问题，第一步永远是看 AST：

```python
import tree_sitter_language_pack as tsl

parser = tsl.get_parser("python")  # 或 "swift", "java" 等
tree = parser.parse(source_bytes)

def print_tree(node, indent=0):
    print(" " * indent + f"{node.type} [{node.start_point[0]}:{node.start_point[1]}]")
    for c in node.children:
        print_tree(c, indent + 2)

print_tree(tree.root_node)
```

**用它来验证：**
- 节点类型是否和 `LANG_CONFIG` 匹配
- body field 名称是否正确（Python 用 `body`，Swift 用 `class_body`）
- 参数、继承、docstring 的节点结构

### 工具 2: Visitor 数据流追踪

在 `parse_file` 的 visitor 中插入临时 print：

```python
def visitor(node, depth):
    if node.type in class_types:
        print(f"ENTER class: {name}, stack={class_stack}")
    elif node.type in func_types:
        print(f"FUNC: {name}, is_method={is_method}, parent={parent_class}, stack={class_stack}")
```

### 工具 3: CLI 配置文件检查

```python
from src.cli import _read_json, _read_toml, _read_yaml, _detect_targets

# 查看所有检测到的目标
for t in _detect_targets():
    print(f"{t.display_name}: exists={t.exists()}, path={t.config_path}")

# 读取并检查特定配置
config = _read_json(Path("~/.cursor/mcp.json").expanduser())
print(json.dumps(config, indent=2))
```

### 工具 4: MCP Server 本地测试

```bash
# 直接调用 MCP tool 看响应
echo '{"jsonrpc":"2.0","method":"tools/list","id":1}' | python -m src.server
```

## 典型根因模式

| 症状 | 常见根因 | 调查方向 |
|------|---------|---------|
| 解析结果全是零 | `LANG_CONFIG` 缺少该语言 | 检查 config dict |
| 函数被错标为方法 | `class_stack` 作用域管理 | 追踪 push/pop 时机 |
| docstring 为 None | AST 节点结构不匹配 | 打印 AST 看实际结构 |
| import 丢失 | 语言专用提取函数未覆盖 | 打印 import 节点的 children |
| CLI 安装后工具没生效 | 配置路径或 key_path 错误 | 读回配置文件检查 |
| 依赖图为空 | 零函数/类 → NetworkX 无节点 | 先查解析是否正常 |

## 关联 Skill

- **测试驱动开发** → `codebook-tdd`：Phase 4 的回归测试遵循 TDD 的 RED-GREEN-REFACTOR 循环
- **开发工作流** → `codebook-dev-workflow`：修复完成后必须走 Phase 5 子代理审查，再进入 Phase 6 交付

## 红旗清单

- "先改改试试看"
- "应该是 X 的问题，我直接改"
- "加多个改动，跑一下看"
- "不用看 AST，我知道结构"
- 连续第 3 次修复失败还在继续
- 假设了根因但没有验证

**看到以上任何一条：停下来，回到 Phase 1。**
