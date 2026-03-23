# CodeBook — 可执行开发手册 v2

> **版本**: v2.0（整合 Sprint 2 全部需求 + 自我进化系统）
> **日期**: 2026-03-23
> **前版**: v1.0（流水线 A/B/C 任务模板）
> **变更**: 新增流水线 D（自我进化基础设施）；整合所有待做/已做；优化 Token 损耗；增加并行执行策略
>
> 每个模板是一段可以直接复制到 Claude Code 的完整任务指令。
> 使用前替换 `{{变量}}` 为实际值。
> 所有字段名和输出结构已对齐 INTERFACES.md（2026-03-23 校准版）。

---

## 〇、全局任务总览

### 完成状态一览

| ID | 任务 | 流水线 | 状态 | 完成日期 |
|----|------|--------|------|---------|
| M-001 | 5 个 MCP tool 实现 | — | ✅ 已完成 | 03-22 |
| M-002 | Prompt Config v0.1 → v0.2 | — | ✅ 已完成 | 03-21 |
| M-003 | MCP v0.1 验收（167测试/99.3%） | — | ✅ 已完成 | 03-22 |
| M-004 | INTERFACES.md 与代码校准 | 跨线 | ✅ 已完成 | 03-23 |
| M-005 | 自我进化系统设计方案 | — | ✅ 已完成 | 03-23 |
| A-1 | 环境准备（clone 测试仓库） | A | ⬜ 待做 | — |
| A-2 | scan_repo 压力测试 | A | ⬜ 待做 | — |
| A-3 | read_chapter + diagnose 压力测试 | A | ⬜ 待做 | — |
| A-4 | ask_about + codegen 压力测试 | A | ⬜ 待做 | — |
| A-5 | 瓶颈分析与优化 | A | ⬜ 待做 | — |
| B-1 | 现有 Prompt 角色分析 | B | ⬜ 待做 | — |
| B-2 | 角色系统实现 | B | ⬜ 待做 | — |
| C-1 | 修复已知测试问题 | C | ⬜ 待做 | — |
| C-2 | 建立 CI Pipeline | C | ⬜ 待做 | — |
| D-1 | 持久化存储层 | D | ⬜ 待做 | — |
| D-2 | 术语飞轮 MVP | D | ⬜ 待做 | — |
| D-3 | 项目记忆持久化 | D | ⬜ 待做 | — |
| D-4 | 智能记忆 + 隐式推断 | D | ⬜ 待做 | — |

### 待确认决策状态

| ID | 决策项 | 状态 | 计划解答 |
|----|--------|------|---------|
| D-001 | 大项目超时：增量扫描 vs lazy loading | 待 A 线压测数据 | D-3 实现增量扫描 |
| D-002 | Mermaid 图过密：分层 vs 折叠 | 待 A 线压测数据 | A-5 优化 |
| D-003 | 是否需要缓存层 | 待 A 线压测数据 | D-1 统一存储层 |
| D-004 | domain_expert 的 project_domain 传入机制 | 待 B 线设计 | B-1 → D-2 衔接 |
| D-005 | 数据飞轮冷启动存储格式 | 待定 | D-1 定义 JSON 格式 |

### 已知问题状态

| ID | 问题 | 优先级 | 状态 | 解决任务 |
|----|------|--------|------|---------|
| I-001 | test_mcp_server_has_four_tools 断言 | 低 | ⬜ 待修 | C-1 |
| I-002 | 25 项 Conduit 集成测试跳过 | 中 | ⬜ 待修 | C-1 |
| I-003 | 角色系统需重构 | 中 | ⬜ 待做 | B-1 → B-2 |
| I-004 | README.md 为空 | 低 | ⬜ 待做 | C-2 附带 |
| I-005 | 未做大代码库压力测试 | 高 | ⬜ 待做 | A-1~A-5 |
| I-006 | INTERFACES.md 不符 | — | ✅ 已解决 | M-004 |

---

## 〇.一、并行执行策略

### 执行波次规划

Token 效率核心策略：**每个 session 只读必要文件，不重复读全量文档**。

```
         ┌─────────────────────────────────────────────────┐
 Wave 1  │ A-1 环境准备 ║ C-1 修复测试 ║ D-1 存储层      │  3 路并行
 (Day1-2) │ (无依赖)    ║ (无依赖)     ║ (无依赖)        │
         └──────┬───────╨──────┬───────╨──────┬──────────┘
                │              │              │
         ┌──────▼───────╥──────▼───────╥──────▼──────────┐
 Wave 2  │ A-2 scan压测 ║ B-1 角色分析 ║ D-2 术语飞轮MVP │  3 路并行
 (Day3-5) │ (依赖A-1)   ║ (可独立)     ║ (依赖D-1)      │
         └──────┬───────╨──────┬───────╨──────┬──────────┘
                │              │              │
         ┌──────▼───────╥──────▼───────╥──────▼──────────┐
 Wave 3  │ A-3 RC+Diag  ║ B-2 角色实现 ║ D-3 项目记忆    │  3 路并行
 (Day6-8) │ (依赖A-2)   ║ (依赖B-1)   ║ (依赖D-1)      │
         └──────┬───────╨──────┬───────╨──────┬──────────┘
                │              │              │
         ┌──────▼───────╥──────▼───────╥──────▼──────────┐
 Wave 4  │ A-4 AA+CG    ║ C-2 CI      ║ D-4 智能记忆    │  3 路并行
 (Day9-11)│ (依赖A-3)   ║ (依赖C-1)   ║ (依赖D-2+D-3)  │
         └──────┬───────╨─────────────╨──────────────────┘
                │
         ┌──────▼───────┐
 Wave 5  │ A-5 瓶颈优化  │  单线
 (Day12)  │ (依赖A-2~4)  │
         └──────────────┘
```

### Token 损耗优化规则

**规则 1：分层读取，不读全量**

每个任务 prompt 只指定该任务必须读取的文件，不再使用「通用前缀读三个文件」的模式。

| 文件 | 大小 | 何时读 |
|------|------|--------|
| CLAUDE.md | ~4.5K token | 仅首次 session 或跨线操作时读 |
| CONTEXT.md | ~3K token | 每个 session 开始时读（获取进度） |
| INTERFACES.md | ~8K token | 仅涉及 tool 接口修改时读对应 §（不读全文） |
| TASK_PROMPTS.md | 本文件 | 不需要在 session 中读取——任务 prompt 已自包含 |
| self_evolution_design.md | ~6K token | 仅 D 线任务读（且按章节读取） |

**规则 2：结果文件作为上下文桥梁**

跨任务依赖通过结果文件传递，不需要读源文件重新理解：

```
A-2 产出 test_results/fastapi/scan_repo.json
  → A-3 只需读这个 JSON，不需要重新理解 scan_repo.py 源码

B-1 产出 docs/role_system_v3_design.md
  → B-2 只需读设计文档，不需要重新分析 prompt config

D-1 产出 src/memory/project_memory.py
  → D-2/D-3 只需读 D-1 的接口，不需要重新分析 _repo_cache.py
```

**规则 3：Prompt 内联关键接口片段**

对于需要参考接口的任务，直接在 prompt 中内联关键字段定义（< 20 行），避免读取整个 INTERFACES.md（600+ 行）。

### 并行冲突矩阵

| | A 线文件 | B 线文件 | C 线文件 | D 线文件 |
|---|---------|---------|---------|---------|
| **A 线** | — | ⚠️ ask_about.py（B-2 改角色，A-4 测试） | 无 | ⚠️ _repo_cache.py（D-1 重构） |
| **B 线** | ⚠️ 同上 | — | 无 | ⚠️ engine.py（D-2 改术语注入） |
| **C 线** | 无 | 无 | — | 无 |
| **D 线** | ⚠️ 同上 | ⚠️ 同上 | 无 | — |

**冲突解决**：
- A-4 和 B-2 不能同 Wave（已在规划中错开）
- D-1 重构 `_repo_cache.py` 在 Wave 1，A 线从 Wave 2 开始使用缓存——无冲突
- D-2 改 `engine.py` 术语注入在 Wave 2，B-2 改角色在 Wave 3——D-2 先完成，B-2 在其基础上改

---

## 一、通用 Prompt 片段库

> 以下片段在各任务 prompt 中按需引用，用 `{{片段名}}` 标记。
> 直接内联到任务 prompt 中，不需要额外读取文件。

### {{读取进度}}
```
读取 files/CONTEXT.md，确认：
- 当前 sprint 目标和你所属的流水线状态
- 已知问题列表中与本次任务相关的项
```

### {{pytest收尾}}
```
任务完成后：
1. cd mcp-server && python -m pytest tests/ -x -q
2. 记录结果：X passed, Y failed, Z skipped
3. 如有新增失败，必须在本任务内修复
```

### {{更新CONTEXT}}
```
在 files/CONTEXT.md 的「任务日志」部分追加：

### 任务 {{编号}} — {{日期}} {{流水线}}
**目标**：{{一句话}}
**完成情况**：{{✅/❌ + 说明}}
**发现的问题**：{{如有}}
**下一步建议**：{{如有}}
**修改的文件**：{{列表}}
**pytest 结果**：X passed, Y failed, Z skipped
```

### {{scan_repo输出关键字段}}
```python
# scan_repo 输出中与本任务相关的字段（摘自 INTERFACES.md §2.1）：
{
    "status": "ok",
    "modules": [{"name": str, "health": str, "source_refs": list[str], ...}],
    "connections": [{"from": str, "to": str, "strength": str}],
    "mermaid_diagram": str,
    "stats": {"files": int, "modules": int, "functions": int, "scan_time_seconds": float, "step_times": dict}
}
```

### {{read_chapter输出关键字段}}
```python
# read_chapter 输出中与本任务相关的字段（摘自 INTERFACES.md §2.2）：
{
    "status": "ok",
    "module_summary": {"total_files": int, "total_lines": int, "entry_functions": list, "public_interfaces": list},
    "module_cards": [{"name": str, "path": str, "functions": list, "calls": list, "imports": list, "ref": str}],
    "dependency_graph": str,  # Mermaid
    "pagination": {"showing": int, "total": int} | None
}
```

### {{diagnose输出关键字段}}
```python
# diagnose 输出（摘自 INTERFACES.md §2.3）：
{
    "status": "ok" | "no_exact_match",
    "keywords": list[str],
    "matched_nodes": [{"node_id": str, "score": float, "file": str}],
    "exact_locations": [{"file": str, "line_start": int, "line_end": int, "direction": str, "ref": str, "code_snippet": str}],
    "call_chain": str,  # Mermaid
    "context": str, "guidance": str
}
```

---

## 二、流水线 A：压力测试 + 引擎优化

> **目标**：用递增规模的开源项目测试 5 个 tool 的极限，发现并修复瓶颈
> **所属 Wave**：A-1(W1) → A-2(W2) → A-3(W3) → A-4(W4) → A-5(W5)
> **文件锁**：A 线拥有 `test_results/` 的写权限，不修改 src/ 下文件（A-5 除外）

### A-1：环境准备

```
【任务】流水线 A / 环境准备
【所属】Wave 1（可与 C-1、D-1 并行）

{{读取进度}}

执行步骤：
1. 按以下梯度 clone 测试仓库到 mcp-server/repos/ 目录：

   | 梯度 | 项目 | 语言 | 预估行数 |
   |------|------|------|---------|
   | 中型 | FastAPI（本体） | Python | ~1.5万 |
   | 中大型 | Sentry Python SDK | Python | ~3万 |
   | 大型 | Next.js | TypeScript | ~10万+ |
   | 超大型 | VS Code | TypeScript | ~50万+ |

   每个用 `git clone --depth 1 {{repo_url}}`

2. 对每个项目统计文件数和代码行数（cloc 或 find+wc）
3. 每个项目的统计写入 test_results/{{project_name}}/stats.json：
   {"project": str, "repo_url": str, "clone_date": "YYYY-MM-DD",
    "file_count": N, "code_lines": N, "languages": {"Python": N, ...}}

4. 更新 CONTEXT.md 中测试项目梯度表的状态

不做其他事。不跑 scan_repo。不修改 src/ 下任何代码。
```

### A-2：scan_repo 压力测试

```
【任务】流水线 A / scan_repo 压力测试
【所属】Wave 2（可与 B-1、D-2 并行）
【前置】A-1 已完成（repos/ 下有测试仓库）

{{读取进度}}

对以下项目按顺序运行 scan_repo（overview 模式），从小到大逐个测试。
每个项目如果崩溃，记录错误后继续下一个，不要停下。

{{scan_repo输出关键字段}}

对每个项目 {{project_name}} 记录到 test_results/{{project_name}}/scan_repo.json：

{
  "性能": {
    "scan_time_seconds": N,
    "step_times": {...},
    "total_lines": N
  },
  "规模": {
    "modules": N, "functions": N, "classes": N,
    "imports": N, "calls": N, "languages": {...}
  },
  "质量": {
    "mermaid_nodes": N,
    "mermaid_readable": "1-10 分 + 说明",
    "health_distribution": {"green": N, "yellow": N, "red": N},
    "module_grouping_score": "1-10 分 + 说明",
    "error": null | "错误信息"
  }
}

全部项目测完后，写一份 test_results/scan_repo_summary.md 横向对比四个项目。

{{更新CONTEXT}}
```

### A-3：read_chapter + diagnose 压力测试

```
【任务】流水线 A / read_chapter + diagnose 压力测试
【所属】Wave 3（可与 B-2、D-3 并行）
【前置】A-2 已完成（test_results/ 下有 scan_repo 结果）

{{读取进度}}

先读取 test_results/scan_repo_summary.md 了解各项目的模块分布。

{{read_chapter输出关键字段}}
{{diagnose输出关键字段}}

**对每个成功完成 scan_repo 的项目**：

read_chapter 测试：
1. 从 scan_repo 结果的 modules 中选 3 个不同规模的模块（按 total_lines 分小/中/大）
2. 对每个运行 read_chapter
3. 记录到 test_results/{{project_name}}/read_chapter.json：
   - 响应时间
   - module_cards 数组长度
   - 是否触发 pagination
   - 翻译质量（PM 视角 1-10）

diagnose 测试：
4. 针对项目特点设计 2 个跨文件问题场景
5. 对每个运行 diagnose（输入参数是 query，不是 description）
6. 记录到 test_results/{{project_name}}/diagnose.json：
   - keywords 提取准确性
   - matched_nodes 命中数和 score 分布
   - exact_locations 准确性（抽查 3 个）
   - call_chain Mermaid 完整性

{{更新CONTEXT}}
```

### A-4：ask_about + codegen 压力测试

```
【任务】流水线 A / ask_about + codegen 压力测试
【所属】Wave 4（可与 C-2、D-4 并行）
【前置】A-3 已完成

{{读取进度}}

⚠️ 关键架构理解（不需要读 INTERFACES.md 全文，以下即为关键信息）：
- ask_about 在 MCP 模式下不内部调用 LLM。返回 context + guidance，由宿主推理。
  评估的是：(1) context 组装质量 (2) 宿主最终输出的翻译质量
- codegen 输出含 diff_valid 字段，表示 diff 是否通过 apply 验证

**对最大的成功项目**：

ask_about 测试：
1. 选 1 个核心业务模块
2. 用 PM 视角连续提问 3 轮（通过 conversation_history 传递）
3. 记录到 test_results/{{project_name}}/ask_about.json：
   - context 长度和 context_modules_used
   - guidance 是否与 role 匹配
   - 翻译质量（PM 视角 1-10）
   - 多轮 context 是否递进
   - 是否出现幻觉

codegen 测试：
4. 设计 1 个涉及多文件修改的需求
5. 先用 diagnose 定位，再将输出作为 locate_result 传给 codegen
6. 记录到 test_results/{{project_name}}/codegen.json：
   - diff_valid, validation_detail
   - change_summary 准确性
   - blast_radius 完整性
   - verification_steps 可操作性

{{更新CONTEXT}}
```

### A-5：瓶颈分析与优化

```
【任务】流水线 A / 瓶颈分析与优化
【所属】Wave 5（单线执行，确保无并行冲突）
【前置】A-2 ~ A-4 全部完成

{{读取进度}}

执行步骤：
1. 读取 test_results/ 下所有 JSON 结果
2. 按严重程度排序：崩溃 > 超时 > 质量下降 > 轻微问题
3. 选最严重的 1 个问题，分析根因
4. 实施修复（只修一个问题，改动最小化）
5. 如果修复涉及接口变更，先更新 INTERFACES.md 对应 § 再改代码
6. 跑 pytest 全量测试确认不回退
7. 重新跑受影响的 tool 验证效果
8. 写入 test_results/optimization_log.json：修复前后指标对比

{{pytest收尾}}
{{更新CONTEXT}}

⚠️ 不要一次修多个问题。一个任务一个修复。
如果有多个严重问题，记录在 CONTEXT.md 中，下一个 session 继续。
```

---

## 三、流水线 B：角色系统重构

> **目标**：从 4 角色模板式切换 → 面向四类用户群的动态翻译
> **所属 Wave**：B-1(W2) → B-2(W3)
> **文件锁**：B 线拥有 prompt 配置 + 角色相关代码的修改权
> **与 D 线衔接**：B-1 的 project_domain 设计直接驱动 D-2 术语飞轮

### B-1：现有 Prompt 角色分析 + 新系统设计

```
【任务】流水线 B / 角色分析 + 新系统设计
【所属】Wave 2（可与 A-2、D-2 并行）

{{读取进度}}

⚠️ 产品战略背景（不需要读 CLAUDE.md 全文，以下为核心信息）：
- 四类目标用户：开发者、管理层、行业专家（最关键新增）、QA/运维
- 行业专家核心需求：用领域术语翻译代码
- 多角色视图质量取决于数据飞轮深度

⚠️ 与自我进化系统的衔接（读取 docs/self_evolution_design.md 第二章「术语飞轮」§2.3-2.5）：
- 新角色系统的 project_domain 参数直接驱动术语飞轮的行业术语包加载
- TermResolver 的术语解析优先级需要在角色设计中考虑

执行步骤：
1. 读取 prompts/codebook_config_v0.2.json 的角色配置
2. Grep 所有 tool 中的 ROLE_GUIDANCE / role / banned_terms 使用
3. 对比 4 个角色的输出差异：
   - 有意义的差异 vs 纯措辞替换 vs 完全缺失
4. 设计新角色系统：
   - 至少支持 dev / pm / domain_expert 三种视图
   - domain_expert 需要 project_domain 参数
   - 定义 project_domain 的传入机制（解答 Decision D-004）：
     · scan_repo 输入参数传入
     · 自动推断兜底（README 关键词 + 依赖包名）
   - 确保向后兼容（ceo/investor→pm, qa→dev）
5. 将设计写入 docs/role_system_v3_design.md

产出验收标准：
- docs/role_system_v3_design.md 包含完整设计
- D-004 决策有明确方案
- 设计文档中明确与 TermResolver 的集成点

{{更新CONTEXT}}

这个任务只做分析和设计，不写实现代码。
```

### B-2：角色系统实现

```
【任务】流水线 B / 角色系统实现
【所属】Wave 3（可与 A-3、D-3 并行）
【前置】B-1 已完成（docs/role_system_v3_design.md 存在）
【并行注意】D-3 同 Wave 也在修改 ask_about.py / diagnose.py / read_chapter.py。
  B-2 只改角色逻辑（ROLE_CONFIG / ROLE_GUIDANCE），D-3 只改记忆读写。
  如果 D-3 已完成，注意处理 ProjectMemory 集成点（DiagnosisCache 已被替换）。
  如果 D-3 未完成，保持现有 DiagnosisCache 调用不变。

{{读取进度}}

读取 docs/role_system_v3_design.md 获取设计方案。

⚠️ 如果 D-2（术语飞轮 MVP）已完成：
   读取 mcp-server/src/glossary/term_resolver.py 的公开接口
   在角色逻辑中调用 TermResolver 获取术语表，替代硬编码的 banned_terms

⚠️ 如果 D-2 未完成：
   保持现有 _get_banned_terms() 调用不变，但预留 TermResolver 接入点
   在代码中加 TODO 注释标记集成位置

执行步骤：
1. 修改 prompt 配置和各 tool 中的角色逻辑
2. 保持向后兼容（ceo/investor→pm, qa→dev, 新增 domain_expert）
3. 对现有 4 个测试仓库跑 ask_about 和 read_chapter，收集对比
4. 测试 domain_expert 视图
5. 质量评估：PM 视角 ≥ 9.0/10
6. 更新 INTERFACES.md §3 中的角色系统接口

{{pytest收尾}}
{{更新CONTEXT}}
```

---

## 四、流水线 C：测试补全 + CI

> **目标**：补全测试覆盖，建立自动化 CI
> **所属 Wave**：C-1(W1) → C-2(W4)
> **文件锁**：C 线拥有 tests/ 和 .github/ 的修改权

### C-1：修复已知测试问题

```
【任务】流水线 C / 修复已知测试问题
【所属】Wave 1（可与 A-1、D-1 并行）

{{读取进度}}

目标：修复 I-001 + 激活 I-002 + 补充 codegen 边界测试

执行步骤：
1. 修复 test_mcp_server_has_four_tools → 断言 5 个 tool（I-001）
2. 分析 25 项 Conduit 集成测试跳过原因
3. 逐步激活：先 mock 环境依赖，每激活一批跑一次确认
4. 补充 codegen 边界测试：
   - diff_valid = False 时的错误路径
   - locate_result 和 file_paths 同时为空
   - 超大文件的 diff 生成
5. 目标：0 跳过（或记录无法解决的原因）

{{pytest收尾}}
{{更新CONTEXT}}
```

### C-2：建立 CI Pipeline

```
【任务】流水线 C / 建立 CI Pipeline
【所属】Wave 4（可与 A-4、D-4 并行）
【前置】C-1 已完成（测试稳定）

{{读取进度}}

执行步骤：
1. 创建 .github/workflows/test.yml
   - Python 3.10+
   - pip install 依赖
   - pytest 全量运行
   - 失败时显示详细输出
2. 本地验证 workflow 文件语法（act 或手动检查）
3. 填充 README.md（I-004）：
   - 产品简介（一段话）
   - 安装步骤
   - 5 个 tool 的简要说明
   - CI badge
4. 确保 CI 不会因为缺少外部仓库而失败（用 mock/fixture）

{{更新CONTEXT}}
```

---

## 五、流水线 D：自我进化基础设施（新增）

> **目标**：实现术语飞轮和项目记忆，让 CodeBook 越用越好用
> **设计文档**：docs/self_evolution_design.md
> **所属 Wave**：D-1(W1) → D-2(W2) / D-3(W3) → D-4(W4)
> **文件锁**：D 线拥有 src/glossary/、src/memory/、~/.codebook/ 的修改权
>             D 线修改 engine.py 和 ask_about.py 时需确认 B 线不在同时修改

### D-1：持久化存储层

```
【任务】流水线 D / 持久化存储层
【所属】Wave 1（可与 A-1、C-1 并行）

{{读取进度}}

读取 docs/self_evolution_design.md 的第一章「设计全景」和第三章 §3.2-3.3（项目记忆架构和数据结构）。

目标：建立 ~/.codebook/ 统一存储基础设施，为术语飞轮和项目记忆提供持久化层。

⚠️ 现有缓存代码参考（不需要读全文，以下为关键信息）：
- mcp-server/src/tools/_repo_cache.py 的 RepoCache 类
- 当前用 ~/.codebook_cache/contexts/{hash}.json 存缓存
- 本任务需要将存储目录迁移到统一结构

执行步骤：

1. 创建 mcp-server/src/memory/__init__.py
2. 创建 mcp-server/src/memory/project_memory.py：

   ```python
   class ProjectMemory:
       """统一管理一个项目的所有记忆数据。

       存储目录结构：
       ~/.codebook/memory/{repo_hash}/
       ├── context.json          # 结构记忆（原 RepoCache 数据）
       ├── understanding.json    # 理解记忆（诊断+QA历史）
       ├── interactions.json     # 交互记忆（热点+会话摘要）
       ├── glossary.json         # 项目级术语库
       └── meta.json             # 元信息
       """

       def __init__(self, repo_url: str): ...

       # 结构记忆（兼容现有 RepoCache）
       def store_context(self, ctx: SummaryContext): ...
       def get_context(self) -> SummaryContext | None: ...

       # 理解记忆
       def add_diagnosis(self, module: str, record: DiagnosisRecord): ...
       def get_module_understanding(self, module: str) -> ModuleUnderstanding | None: ...

       # 交互记忆
       def add_session_summary(self, summary: SessionSummary): ...
       def get_hotspots(self, module: str = None) -> list[Hotspot]: ...

       # 元信息
       def get_meta(self) -> dict: ...
       def update_meta(self, **kwargs): ...
   ```

3. 创建数据类文件 mcp-server/src/memory/models.py：
   - DiagnosisRecord, QARecord, AnnotationRecord
   - ModuleUnderstanding
   - Hotspot, SessionSummary, InteractionMemory
   （字段定义见 self_evolution_design.md §3.3.2-3.3.3）

4. 修改 mcp-server/src/tools/_repo_cache.py：
   - RepoCache.store() 内部委托给 ProjectMemory.store_context()
   - RepoCache.get() 内部委托给 ProjectMemory.get_context()
   - 保持 RepoCache 的公开 API 不变（向后兼容）
   - 首次使用时自动迁移旧缓存目录到新结构

5. 创建 mcp-server/src/memory/migration.py：
   - 检测 ~/.codebook_cache/ 旧目录
   - 自动迁移到 ~/.codebook/memory/ 新结构
   - 迁移后在旧目录留 marker 文件防止重复迁移

6. 测试：
   - test_project_memory.py：读写各层记忆
   - test_migration.py：旧缓存迁移
   - test_repo_cache_compat.py：确认 RepoCache 行为不变

{{pytest收尾}}
{{更新CONTEXT}}
```

### D-2：术语飞轮 MVP

```
【任务】流水线 D / 术语飞轮 MVP
【所属】Wave 2（可与 A-2、B-1 并行）
【前置】D-1 已完成（ProjectMemory 存储层可用）

{{读取进度}}

读取 docs/self_evolution_design.md 第二章「术语飞轮」§2.3-2.7。

目标：用户可以纠正术语并立即生效；支持行业术语包加载。

⚠️ 当前术语注入点（不需要读全文源码）：
- engine.py L115-124：_get_banned_terms() 从 codebook_config_v0.2.json 读术语
- engine.py L328：build_l2_prompt 注入 {banned_terms}
- engine.py L347-348：build_l3_prompt 注入 {banned_terms} + {http_status_annotations}
- ask_about.py 中 ROLE_CONFIG 各角色有 banned_terms 字符串

执行步骤：

1. 创建 mcp-server/src/glossary/__init__.py
2. 创建 mcp-server/src/glossary/term_store.py：

   ```python
   @dataclass
   class TermEntry:
       source_term: str
       target_phrase: str
       context: str = ""
       domain: str = "general"
       source: str = "default"     # "default" | "user_correction" | "domain_pack" | "inferred"
       confidence: float = 1.0
       usage_count: int = 0
       created_at: str = ""
       updated_at: str = ""

   class ProjectGlossary:
       """一个项目的术语库。存储在 ProjectMemory 的 glossary.json 中。"""
       def __init__(self, repo_url: str): ...
       def add_correction(self, source_term: str, target_phrase: str, context: str = ""): ...
       def get_all_terms(self) -> list[TermEntry]: ...
       def import_terms(self, terms: list[dict], domain: str): ...
   ```

3. 创建 mcp-server/src/glossary/term_resolver.py：

   ```python
   class TermResolver:
       """多层级术语解析器。合并优先级：用户纠正 > 项目库 > 行业包 > 全局默认"""

       def __init__(self, repo_url: str, project_domain: str | None = None): ...

       def resolve(self) -> str:
           """返回合并后的术语禁用表文本（可直接注入 prompt）。"""
           ...

       def resolve_as_list(self) -> list[TermEntry]:
           """返回合并后的术语列表（用于程序化访问）。"""
           ...

       def track_usage(self, term: str):
           """记录某术语被使用一次。"""
           ...
   ```

4. 创建 mcp-server/src/tools/term_correct.py：

   新增 MCP tool，注册到 server.py：
   - 输入：source_term, correct_translation, wrong_translation(可选), context(可选)
   - 输出：{"status": "ok", "message": str, "affected_scope": "当前项目"}

5. 修改 mcp-server/src/summarizer/engine.py：
   - _get_banned_terms() → 内部优先调用 TermResolver.resolve()
   - 如果 TermResolver 不可用（无 repo_url 上下文），降级到原逻辑
   - 不改变函数签名

6. 创建预装行业术语包 mcp-server/domain_packs/：
   - general.json（从 codebook_config_v0.2.json 迁移现有 11 个映射）
   - fintech.json（10-15 个金融术语）
   - healthcare.json（10-15 个医疗术语）

7. 修改 mcp-server/src/server.py：注册 term_correct tool

8. 测试：
   - test_term_store.py：术语读写和纠正
   - test_term_resolver.py：多层级合并优先级
   - test_term_correct_tool.py：MCP tool 端到端

⚠️ 注意不要修改 ask_about.py 中的角色逻辑——那是 B 线的职责。
   只修改 engine.py 中的术语获取方式。

{{pytest收尾}}
{{更新CONTEXT}}
```

### D-3：项目记忆持久化

```
【任务】流水线 D / 项目记忆持久化
【所属】Wave 3（可与 A-3、B-2 并行）
【前置】D-1 已完成（ProjectMemory 存储层可用）

{{读取进度}}

读取 docs/self_evolution_design.md 第三章 §3.4-3.5（记忆写入时机 + 读取注入）。

目标：DiagnosisCache 持久化到磁盘；ask_about 上下文注入历史理解。

⚠️ 当前 DiagnosisCache 位置：
- ask_about.py 中的 DiagnosisCache 类（纯内存 dict）
- 方法：add_diagnosis(), add_annotation(), get_diagnoses(), get_annotations()
- diagnose.py 不写入 DiagnosisCache（只有 ask_about 在内部使用）

执行步骤：

1. 修改 mcp-server/src/tools/diagnose.py：
   - diagnose 完成后，调用 ProjectMemory.add_diagnosis() 持久化
   - 传入：module_name, query, diagnosis_summary(从 context 提取), matched_locations(从 exact_locations 提取)

2. 修改 mcp-server/src/tools/ask_about.py：
   - DiagnosisCache → 改为从 ProjectMemory 读取
   - assemble_context() 扩展优先级列表：
     原来 6 级 → 8 级（新增 QA 历史摘要 和 热点信息）
   - 保持 60K 字符总预算不变

   ```python
   # 扩展后的优先级（在 assemble_context 中实现）：
   # 1. 目标模块 L3 摘要（必选）          ← 已有
   # 2. 目标模块源代码（必选）            ← 已有
   # 3. 上下游 1 跳模块 L3 摘要          ← 已有
   # 4. 持久化的诊断结果                 ← 从 ProjectMemory 读取
   # 5. 用户批注                        ← 从 ProjectMemory 读取
   # 6. 【新增】QA 历史摘要             ← 从 understanding.qa_history
   # 7. 【新增】热点信息                ← 从 interactions.hotspots
   # 8. 上下游 2 跳模块 L3 摘要          ← 已有（降级）
   ```

3. 修改 mcp-server/src/tools/read_chapter.py：
   - read_chapter 完成后，更新 ModuleUnderstanding.view_count += 1

4. 创建 mcp-server/src/tools/memory_feedback.py：
   新增 MCP tool（供宿主 LLM 在回答后回传摘要）：
   - 输入：module_name, question, answer_summary, confidence(可选)
   - 输出：{"status": "ok", "message": "已记录"}
   - 内部：写入 ProjectMemory.understanding.qa_history

5. 修改 mcp-server/src/server.py：注册 memory_feedback tool

6. 测试：
   - test_memory_persistence.py：重启后诊断结果仍在
   - test_ask_about_memory.py：assemble_context 能从记忆中获取历史
   - test_memory_feedback.py：MCP tool 端到端

{{pytest收尾}}
{{更新CONTEXT}}
```

### D-4：智能记忆 + 隐式推断

```
【任务】流水线 D / 智能记忆 + 隐式推断
【所属】Wave 4（可与 A-4、C-2 并行）
【前置】D-2 + D-3 已完成

{{读取进度}}

读取 docs/self_evolution_design.md 第四章「两个系统的协同」。

目标：术语飞轮和项目记忆联动；增量扫描；Hotspot 聚类。

执行步骤：

1. 术语隐式推断（在 term_resolver.py 中新增）：
   - 从 ProjectMemory 的 QA 历史中提取用户使用的业务词汇
   - 与代码中的标识符做关联（简单的关键词匹配）
   - 生成 source=inferred, confidence=0.7 的术语映射
   - confidence < 0.8 的不自动注入 prompt，标记为 "suggested"

2. Hotspot 聚类（在 memory/interactions.py 中实现）：
   - 当同一模块被 diagnose/ask_about 3+ 次，且问题关键词重叠 > 50%
   - 自动聚类为一个 Hotspot
   - Hotspot 写入 interactions.json

3. scan_repo 增量更新（在 scan_repo.py 中修改）：
   - 检查 ProjectMemory 中是否有该 repo 的 context
   - 如有，对比文件 hash（SHA256 of content）找出变更文件
   - 变更 < 30% 时走增量路径：只重新解析变更文件，合并到旧 context
   - 变更 >= 30% 时仍走全量扫描
   - 日志记录增量/全量路径选择

4. SessionSummary 自动生成：
   - 在 ProjectMemory 中新增 finalize_session() 方法
   - 汇总本次会话的 modules_explored, key_findings, unresolved_questions
   - 写入 interactions.json

5. 测试：
   - test_term_inference.py：从 QA 历史推断术语
   - test_hotspot.py：Hotspot 聚类触发
   - test_incremental_scan.py：增量 vs 全量路径选择
   - test_session_summary.py：会话摘要生成

{{pytest收尾}}
{{更新CONTEXT}}
```

---

## 六、验收标准总表

### Sprint 2 整体验收标准

| 维度 | 指标 | 基线 | 目标 |
|------|------|------|------|
| **测试** | pytest 通过率 | 99.3% (141/142) | ≥ 99%，0 跳过 |
| **翻译** | PM 视角翻译质量 | 9.5/10 | ≥ 9.0/10 |
| **性能** | scan_repo 中型项目耗时 | 待测 | < 60s |
| **性能** | scan_repo 大型项目耗时 | 待测 | < 300s |
| **精度** | diagnose exact_locations 命中率 | 待测 | ≥ 80% |
| **精度** | codegen diff_valid 通过率 | 待测 | ≥ 90% |
| **角色** | domain_expert 视角可用 | 不存在 | 可用且翻译合理 |
| **飞轮** | 术语纠正立即生效 | 不存在 | 纠正后下次翻译使用新术语 |
| **记忆** | 诊断结果跨会话保留 | 不保留 | 重启后仍可用 |
| **记忆** | ask_about 引用历史发现 | 不引用 | 新会话能引用旧发现 |
| **记忆** | 会话摘要自动生成 | 不存在 | 会话结束时写入 SessionSummary |
| **记忆** | 增量扫描可用 | 不存在 | 活跃项目 scan_repo 走增量路径 |
| **CI** | 自动化测试 | 手动 | push 自动触发 |

### 各流水线完成标志

| 流水线 | 完成标志 |
|--------|---------|
| A | 4 个梯度项目测试完成，优化 ≥ 1 个瓶颈，结果写入 test_results/ |
| B | domain_expert 视角可用，PM 评分 ≥ 9.0，INTERFACES.md §3 更新 |
| C | 0 个跳过测试（或有文档化理由），CI 绿色，README 非空 |
| D | term_correct + memory_feedback 两个新 tool 可用，增量扫描路径可用 |

---

## 七、文件修改总索引

> 快速查找每个任务修改哪些文件，避免并行冲突。

| 文件 | A 线 | B 线 | C 线 | D 线 |
|------|------|------|------|------|
| `src/server.py` | — | — | — | D-2, D-3（注册新 tool） |
| `src/tools/scan_repo.py` | A-2~4 读取 | — | — | D-4（增量扫描） |
| `src/tools/read_chapter.py` | A-3 读取 | B-2 改角色 | — | D-3（view_count） |
| `src/tools/diagnose.py` | A-3 读取 | B-2 改角色 | — | D-3（持久化诊断） |
| `src/tools/ask_about.py` | A-4 读取 | B-2 改角色 | — | D-3（记忆注入） |
| `src/tools/codegen.py` | A-4 读取 | B-2 改角色 | — | — |
| `src/tools/_repo_cache.py` | — | — | — | D-1（委托给 ProjectMemory） |
| `src/summarizer/engine.py` | — | B-2 改角色 | — | D-2（术语注入） |
| `src/glossary/*` | — | — | — | D-2（新建） |
| `src/memory/*` | — | — | — | D-1, D-3, D-4（新建） |
| `src/tools/term_correct.py` | — | — | — | D-2（新建） |
| `src/tools/memory_feedback.py` | — | — | — | D-3（新建） |
| `tests/*` | — | — | C-1（修复+补充） | D-1~4（新测试） |
| `.github/workflows/*` | — | — | C-2（新建） | — |
| `prompts/*` | — | B-1 分析, B-2 修改 | — | — |
| `domain_packs/*` | — | — | — | D-2（新建） |
| `docs/*` | — | B-1（设计文档） | — | — |
| `test_results/*` | A-1~5（写入） | — | — | — |
| `files/CONTEXT.md` | 所有任务 | 所有任务 | 所有任务 | 所有任务 |
| `files/INTERFACES.md` | A-5（如需） | B-2（§3） | — | D-2, D-3（新 tool 接口） |
| `README.md` | — | — | C-2 | — |
