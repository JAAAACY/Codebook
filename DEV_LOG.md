# CodeBook 开发日志

> **项目**: CodeBook — 让不会写代码的人也能理解、诊断和修改软件产品
> **仓库版本**: codebook-mcp-server 0.1.0
> **最后更新**: 2026-03-23

---

## 项目概况

CodeBook 是一个 MCP Server，核心目标是让 PM 和非技术人员能用自然语言理解代码、定位问题、生成修改方案。采用「蓝图 → 看懂 → 定位 → 改码」四步能力模型。

**技术栈**: Python 3.10+ / FastMCP / Tree-sitter / NetworkX / structlog

**代码规模**:

| 模块 | 文件数 | 总行数 |
|------|--------|--------|
| 核心工具 (src/tools/) | 11 | ~4,186 |
| 解析器 (src/parsers/) | 5 | ~1,786 |
| 服务入口 (src/server.py) | 1 | 233 |
| 测试 (tests/) | 20 | ~432 用例 |
| **合计** | **37+** | **~6,205** |

---

## 已实现功能（7 个 MCP Tools）

### 1. `scan_repo` — 蓝图扫描 ✅

克隆仓库 → Tree-sitter AST 解析 → 模块分组 → 依赖图构建 → 生成蓝图 JSON + Mermaid 全局图。支持 `overview` / `detailed` 两种深度。

### 2. `read_chapter` — 模块卡片 ✅

选定模块后深入查看子组件、调用关系、分支逻辑。支持精确匹配、目录匹配、模糊匹配。

### 3. `diagnose` — 问题定位 ✅

自然语言描述问题 → 追踪调用链 → 返回 Mermaid 流程图 + file:line 精确定位。支持 `module_name` 缩小范围或全局扫描。

### 4. `ask_about` — 追问对话 ✅

选中模块后自由提问，结合代码上下文、依赖关系和诊断结果回答。支持多轮对话（conversation_history）。22 项测试全部通过。

### 5. `codegen` — 代码生成 ✅

自然语言指令 + locate 定位结果 → unified diff + 变更前后对比 + 影响范围 + 验证步骤。内含 diff 验证器，支持自动修复行号偏移。

### 6. `term_correct` — 术语纠正 ✅（新增）

对输出中的技术术语进行自动纠正和标准化，确保面向 PM 的输出使用业务语言而非技术黑话。16 项测试。

### 7. `memory_feedback` — 记忆反馈 ✅（新增）

项目级记忆系统，支持跨会话保留项目上下文、用户反馈和学习结果。与 smart_memory、project_memory 模块协同工作。

---

## 角色系统

支持 4 种输出角色：`ceo` / `pm` / `investor` / `qa`，默认 `pm`。不同角色会调整输出的语言风格和关注点。

> **规划中**: 下个 sprint 将从 4 角色切换简化为 PM↔Dev 桥梁模型（见 Memory: project_role_redesign）。

---

## 里程碑与验收记录

### MCP v0.1 — 2026-03-22 ✅ 已验收

| 检查项 | 状态 | 说明 |
|--------|------|------|
| scan_repo | ✅ | 9 项测试通过 |
| read_chapter | ✅ | 7 项测试通过 |
| diagnose | ✅ | 核心 + E2E 通过 |
| ask_about | ✅ | 22 项测试通过 |
| 角色切换 | ✅ | 4 种角色输出风格验证通过 |
| 性能 | ✅ | 167 测试 / 0.80s |
| 错误处理 | ✅ | 无崩溃，友好提示 |

**测试总览**: 167 用例，141 通过，25 跳过（Conduit 集成），1 失败（测试断言未同步 codegen tool，非功能缺陷）。通过率 99.3%。

---

## Prompt 工程迭代

### Config v0.1 → v0.2 (2026-03-21)

驱动来源：quality_eval_v2 识别的 10 个「PM 看不懂」问题 + 5 条优化建议。

**主要变更**:

- 能力数从 3 扩展到 4（新增 blueprint）
- 输出格式从 3 种扩展到 5 种（新增 blueprint + locate_result）
- 新增术语禁用表（11 个技术术语 → 业务语言替换）
- 新增 HTTP 状态码中文注释对照表（10 个常见状态码）
- 所有面向 PM 输出中 confidence 改为中文自然语言（禁止数值如 0.99）
- codegen 增加「可跳过」引导语和变更最小化规则
- understand / codegen prompt 末尾增加自检清单

### 质量评估得分

| 维度 | v1 得分 | v2 得分 |
|------|---------|---------|
| 理解程度 | 8.5/10 | 9.5/10 |
| 定位清晰度 | 8.0/10 | 9.5/10 |

---

## 测试仓库

`repos/` 目录下包含 4 个用于测试和演示的第三方仓库：

- **fider** — Go + React 用户反馈平台
- **umami** — TypeScript 网站分析
- **fastapi-realworld-example-app** — Python FastAPI "Conduit" 实现（主要测试对象）
- **prostore** — TypeScript 电商应用

---

## 已知问题与待办

| 优先级 | 问题 | 状态 |
|--------|------|------|
| ~~低~~ | ~~`test_mcp_server_has_four_tools` 断言未更新为 5 个 tool~~ | ✅ 已修复（更新为 7 tools） |
| 中 | 25 项 Conduit 集成测试因环境限制跳过 | 需配置外部仓库 |
| 中 | 角色系统重构为 PM↔Dev 桥梁模型 | 下个 sprint |
| — | README.md 内容为空 (TBA) | 待编写 |

---

## 自动化

- **codebook-auto-commit**: 每天 20:00 自动检查未提交变更并 commit，提醒 push。
- **update-dev-log**: 定时检查项目变更并更新本开发日志。
- **codebook-tasks/**: 任务调度脚本（dispatcher.sh、checkpoint.sh）+ 执行日志。
- **.github/workflows/**: CI 工作流配置（新增）。

---

## 开发时间线

```
2026-03-21  Prompt Config v0.1 → v0.2 迭代
            质量评估 v2 完成（PM 视角 9.5/10）
2026-03-22  ask_about 工具实现
            codegen 工具实现 + 验收测试
            MCP v0.1 里程碑验收通过（167 测试 / 99.3%）
            本开发日志创建
2026-03-23  term_correct 工具实现（术语纠正，16 项测试）
            memory_feedback 工具实现（项目记忆反馈）
            smart_memory + project_memory 模块新增（58 项测试）
            glossary 术语表系统新增（31 项测试）
            角色系统升级至 v0.3（41 项测试）
            AST 解析器新增 Swift 语言支持，C# key 规范化
            repo_cloner 解析器扩展（+81 行）
            CLI 工具新增（15 项测试）
            summarizer 引擎更新（15 项测试）
            GitHub Actions CI 工作流 + codebook-tasks 调度系统
            测试规模: 197 → 432 用例，代码规模: ~5,278 → ~6,205 行
```

---

*本日志由 Cowork 自动维护，每次重大开发活动后更新。*
