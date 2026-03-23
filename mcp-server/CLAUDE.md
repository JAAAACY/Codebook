# CodeBook MCP Server — 开发规范

## 项目概述

CodeBook 是一个 MCP Server，让不会写代码的人通过可视化蓝图理解软件项目。核心能力：扫描 GitHub 项目 → Tree-sitter 解析 → 生成模块依赖图 + 函数调用链。

## 硬性规则（无例外）

### 1. 开发流程门禁

**任何功能开发或 bug 修复，必须按以下顺序执行：**

```
构思确认 → 计划文档 → TDD 实现 → 验证通过 → 子代理审查 → 提交
```

- **多维度子代理审查不可跳过。** 实现者审查自己的代码 = 确认偏误。并行派出正确性/工程规范/架构一致性三个独立审查员（轻量变更可用单代理）。

- 加载 `skills/codebook-dev-workflow/` 获取完整流程
- 加载 `skills/codebook-tdd/` 获取 TDD 规范
- 加载 `skills/codebook-debugging/` 获取调试规范

**跳过任何一步 = 违规。"赶时间"不是理由。**

### 多代理审查规则

**架构：** 三个专家审查员并行（正确性 / 工程规范 / 架构一致性），主代理汇总裁决。详见 `skills/codebook-dev-workflow/` Phase 5。

**反作弊规则（适用于所有审查角色）：**
- **不传会话历史** — 每个子代理只接收精心裁剪的角色 prompt，不是你的对话上下文
- **不暗示结果** — prompt 中不出现"应该没问题"、"帮我确认"等引导性语言
- **不预设期望** — 只描述变更目标，不描述你认为的实现质量
- **角色隔离** — 三个审查员互不可见对方的结果，各自独立出报告
- **主代理不篡改** — 汇总时如实呈现各审查员结论，不降级别、不删条目
- **审查员说错了？** — 用技术理由反驳，不要盲从，但也不要因为不想改就否定
- **Critical/Important 未修复不得提交** — 修完后重新走 Phase 4 + 重新派出对应审查角色

**轻量模式条件：** ≤2 文件、≤30 行、不涉及公共 API 或 tree-sitter 节点类型时，可用单代理。

### 2. 测试铁律

- **没有失败测试，不写生产代码**
- **没有验证命令输出，不声称"完成"**
- **Bug 修复必须附带回归测试**
- Tree-sitter 测试必须用真实源代码文件，不 mock AST
- CLI 安装器测试必须验证 round-trip（写入 → 读回 → 一致）

### 3. 验证清单

声称"完成"前必须执行：

```bash
# 语法检查
python -c "import ast; ast.parse(open('src/parsers/ast_parser.py').read())"

# 全量测试
python -m pytest tests/ -v

# 期望: 0 failed，无回归
```

**"应该没问题" ≠ 验证。证据先于断言。**

## 技术架构

```
src/
  parsers/
    ast_parser.py    — Tree-sitter 解析核心（LANG_CONFIG + visitor）
    repo_cloner.py   — Git 克隆 + 文件扫描
    module_grouper.py — 模块分组（目录/Swift Package/配置文件）
    dep_graph.py     — NetworkX 依赖图 + Mermaid 输出
  server.py          — MCP Server 入口（JSON-RPC）
  cli.py             — 一键安装器（10 个工具，3 种配置格式）
  config.py          — 全局配置
```

## 关键设计决策

1. **`_walk_tree` 支持 `on_leave` 回调** — 用于 class_stack 作用域管理，离开 class 节点时 pop。不可删除。
2. **`_extract_python_docstring` 兼容两种 AST 结构** — `body > expression_statement > string` 和 `body > string`，适配不同版本 tree-sitter。
3. **CLI 统一配置分发** — `_read_config` / `_write_config` 自动根据后缀选择 JSON/TOML/YAML。新增工具只需在 `_detect_targets()` 追加一个 `ToolTarget`。
4. **`--cn` 模式** — 中国网络适配，使用清华镜像安装依赖。

## 新增语言支持清单

添加新语言时必须完成：

1. `LANG_CONFIG` 中添加语言条目（含所有 node type 映射）
2. 如有特殊语法（如 Swift 参数、TOML 配置），写专用提取函数
3. `config.py` 的 `supported_languages` 列表中添加
4. `tests/test_parsers.py` 中添加完整测试用例
5. `module_grouper.py` 中添加包管理器检测（如适用）

## 常见陷阱

- **class_stack 只 push 不 pop** — 已修复，但类似模式（任何 stack/context 管理）必须确保有 leave 回调
- **tree-sitter 不同版本 AST 结构不同** — 不要硬编码单一路径，做 fallback
- **`_find_child_by_field` 返回 None** — 不同语言的 field name 可能不一致，用 `node.children` 遍历兜底
