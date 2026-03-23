# CodeBook — Claude Code 项目规则

> 本文件由所有 Claude Code session 自动加载。内容为不可变规则，非动态进度。
> 动态进度见 `CONTEXT.md`，模块接口契约见 `INTERFACES.md`，任务模板见 `TASK_PROMPTS.md`。

---

## 产品定义

CodeBook 是**代码世界的通用翻译层**——一个 MCP Server，向上对接不懂代码的业务专家（PM、行业专家、管理层），向下嵌入开发者工作流，中间靠持续积累的行业语义数据构建壁垒。

**核心能力模型**：蓝图（scan_repo）→ 看懂（read_chapter）→ 定位（diagnose）→ 追问（ask_about）→ 改码（codegen）

**四类目标用户**：

| 用户 | 核心痛点 | CodeBook 提供的价值 |
|------|---------|-------------------|
| 开发者 | 接手新项目 / Review 陌生模块的理解成本 | 自然语言理解代码意图，减少上下文切换 |
| 管理层（CTO/PM） | 跨角色沟通断层，"改动影响多大"要花 30 分钟解释 | 业务语言直接呈现架构依赖和变更影响 |
| 行业专家（最关键的新增用户群） | 有判断力但没有观察窗口 | 用领域术语翻译代码逻辑，让专家能验证实现 |
| QA / 运维 | 代码库腐化不可见，变更影响范围不清晰 | 全局健康度 + 变更影响范围分析 |

**分发三阶段**：MCP 插件先行验证引擎 → Web 平台扩展到非开发者用户 → CI/CD 集成锁定团队

当前版本：codebook-mcp-server 0.1.0（阶段一：MCP 插件）

---

## 技术栈约束（不可变）

| 层 | 技术 | 备注 |
|---|---|---|
| 语言 | Python 3.10+ | 不迁移到其他语言 |
| MCP 框架 | FastMCP | 不换框架 |
| AST 解析 | Tree-sitter (py-tree-sitter) | 核心解析器，不替换 |
| 依赖图 | NetworkX | 模块/函数级依赖关系 |
| 日志 | structlog | 所有日志必须用 structlog |
| 测试 | pytest | 所有新代码必须附带测试 |

**架构原则**（来自产品战略）：
- 工程管道优先，不训练自有模型，依赖大语言模型能力
- 多角色视图 = 引擎动态生成，非预设模板
- 早期管道模式：不碰用户数据，不为第三方 LLM 数据安全担责

---

## 代码结构（不可随意变更目录布局）

```
mcp-server/
├── src/
│   ├── server.py          # MCP 服务入口（173 行），不要随意修改 tool 注册逻辑
│   ├── tools/             # 5 个 MCP tool 实现（~3,791 行）
│   │   ├── scan_repo.py   # 蓝图扫描
│   │   ├── read_chapter.py# 模块卡片
│   │   ├── diagnose.py    # 问题定位
│   │   ├── ask_about.py   # 追问对话
│   │   ├── codegen.py     # 代码生成（调用 codegen_engine.py）
│   │   ├── codegen_engine.py  # 代码生成核心引擎
│   │   ├── diff_validator.py  # diff 格式验证与修复
│   │   └── _repo_cache.py    # SummaryContext 缓存（7天过期）
│   ├── parsers/           # Tree-sitter 解析器（~1,312 行）
│   │   ├── ast_parser.py      # AST 解析 → ParseResult
│   │   ├── module_grouper.py  # 文件 → ModuleGroup 分组
│   │   ├── dependency_graph.py# NetworkX 依赖图
│   │   └── repo_cloner.py     # 仓库克隆 → CloneResult
│   ├── summarizer/
│   │   └── engine.py          # SummaryContext / ModuleMapItem / ModuleCard
│   └── config/            # Prompt 配置文件
├── tests/                 # pytest 测试（9 文件，197 用例）
└── repos/                 # 测试用第三方仓库（不提交）
```

---

## 5 个 MCP Tools（不可删除或重命名）

> ⚠️ 以下为校准后的真实接口。完整字段定义见 `INTERFACES.md`。

| Tool | 功能 | 关键输入 | 关键输出 |
|------|------|---------|---------|
| `scan_repo` | 克隆 → AST 解析 → 模块分组 → 依赖图 → 蓝图 | repo_url, role, depth | modules(增强), connections, mermaid_diagram, stats |
| `read_chapter` | 查看模块详情：按文件组织的函数/类/调用卡片 | module_name, role | module_summary, module_cards, dependency_graph |
| `diagnose` | 自然语言 → 关键词提取 → 调用链追踪 → 精确定位 | query, module_name, role | matched_nodes, call_chain(Mermaid), exact_locations |
| `ask_about` | 组装模块上下文，交给 MCP 宿主 LLM 推理 | module_name, question, conversation_history | context, guidance, context_modules_used |
| `codegen` | 自然语言指令 → unified diff + 验证 | instruction, repo_path, locate_result | change_summary, unified_diff, blast_radius, diff_valid |

**关键架构理解**：
- `diagnose` 和 `ask_about` 在 MCP 模式下**不内部调用 LLM**，而是返回结构化上下文让宿主推理
- `scan_repo` 的结果缓存在 `_repo_cache` 中，`read_chapter`/`diagnose`/`ask_about` 都从缓存读取
- 缓存按最后访问时间计算，7 天未用过期

**新增 tool 需要同步更新**：server.py 注册、tests/ 测试、INTERFACES.md 接口定义、DEV_LOG.md。

---

## 核心数据结构速查

> 完整定义见 `INTERFACES.md`。这里只列最常遇到的。

| 类名 | 文件 | 用途 |
|------|------|------|
| `ParseResult` | parsers/ast_parser.py | 单文件解析结果（含 FunctionInfo/ClassInfo/ImportInfo/CallInfo） |
| `ModuleGroup` | parsers/module_grouper.py | 逻辑模块分组（name, dir_path, files, entry_functions, public_interfaces） |
| `NodeAttrs` / `EdgeAttrs` | parsers/dependency_graph.py | 依赖图节点/边属性 |
| `SummaryContext` | summarizer/engine.py | 全局上下文（clone_result + parse_results + modules + dep_graph），被缓存 |
| `CodegenOutput` | tools/codegen_engine.py | 代码生成输出（diff_blocks, blast_radius, verification_steps） |

**⚠️ 常见误解**：
- 代码中没有 `ParsedSymbol` 类——函数/类/导入/调用各有独立 dataclass
- 模块类叫 `ModuleGroup`，不叫 `Module`
- 依赖图边属性是 `data_label`/`call_count`/`is_critical_path`，不是 type/source_line/target_line

---

## 编码规范

1. **所有新代码必须附带 pytest 测试**，覆盖正常路径 + 至少一个异常路径
2. **不引入新的重依赖**——如需新库，先在 CONTEXT.md 中记录理由，等待确认
3. **日志一律用 structlog**，禁止 print / logging.getLogger
4. **错误处理**：对外返回 `{"status": "error", "error": str, "hint": str}`，不暴露 traceback
5. **类型注解**：所有公共函数必须有完整的类型注解
6. **commit 信息格式**：`[模块] 简述`，如 `[scan_repo] 增加增量扫描支持`

---

## 禁止事项

- ❌ 不要修改 `server.py` 的 tool 注册逻辑，除非明确在任务中要求
- ❌ 不要删除或跳过现有测试用例（可以新增，不可删除）
- ❌ 不要硬编码 API Key 或模型名称到代码中
- ❌ 不要把 repos/ 下的测试仓库代码提交到 CodeBook 自己的仓库
- ❌ 不要引入 async/await 到当前同步架构中（除非任务明确要求重构）
- ❌ 不要在单个 session 中同时修改两个以上 tool 的核心逻辑
- ❌ 不要在 INTERFACES.md 未更新的情况下修改任何 tool 的输入输出格式

---

## 每个 session 的标准流程

### 开始时
1. 读取 `CONTEXT.md` 了解当前进度和本次任务
2. 读取 `INTERFACES.md` 确认模块接口（尤其是你要修改的 tool）
3. 明确本次任务的单一目标和验收标准

### 进行中
4. 每完成一个子步骤，跑 `pytest` 确认不回退
5. 如果需要改接口，**先更新 INTERFACES.md，再改代码**
6. 发现 INTERFACES.md 与实际代码不一致时，以代码为准，更新文档

### 结束时
7. 跑全量 `pytest`，报告通过率
8. 在 `CONTEXT.md` 追加本次任务总结（使用固定格式，见 CONTEXT.md）
9. 如有需要，更新 `DEV_LOG.md`

---

## 质量红线

- 全量 pytest 通过率 ≥ 99%（当前基线：99.3%）
- 任何 tool 的响应不允许出现 Python traceback
- PM 视角翻译质量评分不低于 9.0/10（当前基线：9.5/10）
- 所有 tool 输出必须包含 `status` 字段（"ok" | "error" | "no_exact_match" | "success" | "partial"）

---

## 并行开发规则

当多个 Claude Code session 并行工作时：

1. **每个 session 只负责一条流水线**，不跨线操作
2. **INTERFACES.md 是共同基准**——修改接口前必须先更新此文件，并在 CONTEXT.md 中标注
3. 每个 session 结束前跑全量 pytest
4. 如果发现其他流水线的代码有问题，在 CONTEXT.md 中记录，不要自行修复
5. **流水线优先级**：A（压力测试）> B（角色系统重构）> C（测试补全）。冲突时高优先级流水线优先
6. **共享文件修改冲突时**：只有负责该模块的流水线可以修改代码，其他流水线只能提 issue 到 CONTEXT.md
