# CodeBook — 模块接口契约（已校准版）

> 本文件定义模块间的数据格式和调用约定。
> **任何流水线修改接口前，必须先更新本文件，再改代码。**
> 接口变更需在 CONTEXT.md 中标注，通知其他流水线。
>
> ⚠️ **2026-03-23 校准说明**：本文件已与实际代码逐行对齐。
> 原版使用了推断的 `ParsedSymbol`/`Module` 等结构，实际代码中不存在。
> 以下为真实实现。

---

## 核心数据流

```
用户输入 (repo_url / question / instruction)
    ↓
[server.py] ─── MCP 协议路由 ───→ [tools/*]
                                      ↓
                                [parsers/*] ── Tree-sitter AST
                                      ↓
                                [NetworkX] ── 依赖图
                                      ↓
                              工具输出 (JSON / Mermaid / Diff)
```

---

## 1. 解析器输出格式（parsers/ → tools/）

### 1.1 AST 解析结果

> 文件：`mcp-server/src/parsers/ast_parser.py`

```python
@dataclass
class ImportInfo:
    """一条 import 语句。"""
    module: str
    names: list[str] = field(default_factory=list)
    is_relative: bool = False
    line: int = 0

@dataclass
class FunctionInfo:
    """一个函数/方法定义。"""
    name: str
    params: list[str] = field(default_factory=list)
    return_type: str | None = None
    line_start: int = 0
    line_end: int = 0
    docstring: str | None = None
    is_method: bool = False
    parent_class: str | None = None

@dataclass
class ClassInfo:
    """一个类定义。"""
    name: str
    methods: list[str] = field(default_factory=list)
    parent_class: str | None = None
    line_start: int = 0
    line_end: int = 0

@dataclass
class CallInfo:
    """一次函数调用。"""
    caller_func: str
    callee_name: str
    line: int = 0

@dataclass
class ParseResult:
    """单个文件的解析结果。这是解析器的核心输出单元。"""
    file_path: str
    language: str
    classes: list[ClassInfo] = field(default_factory=list)
    functions: list[FunctionInfo] = field(default_factory=list)
    imports: list[ImportInfo] = field(default_factory=list)
    calls: list[CallInfo] = field(default_factory=list)
    line_count: int = 0
    parse_errors: list[str] = field(default_factory=list)
```

**⚠️ 注意**：原版 INTERFACES 定义了 `ParsedSymbol`，实际代码**不存在**此类。
解析结果按文件组织为 `ParseResult`，其中函数/类/导入/调用各有独立 dataclass。

### 1.2 模块分组结果

> 文件：`mcp-server/src/parsers/module_grouper.py`

```python
@dataclass
class ModuleGroup:
    """一个逻辑模块的分组结果。"""
    name: str                          # 模块名（通常是目录名）
    dir_path: str                      # 模块目录路径
    files: list[str] = field(default_factory=list)           # 包含的文件路径列表
    entry_functions: list[str] = field(default_factory=list)  # 入口函数名列表
    public_interfaces: list[str] = field(default_factory=list)# 对外接口列表
    total_lines: int = 0               # 模块总行数
    is_special: bool = False           # 是否为辅助模块（如 config、tests）
```

**⚠️ 注意**：原版定义的 `Module` 类实际名为 `ModuleGroup`。
字段差异：无 `symbols` 和 `description`，有 `entry_functions`、`public_interfaces`、`total_lines`、`is_special`。

### 1.3 克隆结果

> 文件：`mcp-server/src/parsers/repo_cloner.py`

```python
@dataclass
class FileInfo:
    """一个源代码文件的基本信息。"""
    path: str
    abs_path: str
    language: str
    size_bytes: int
    line_count: int
    is_config: bool = False

@dataclass
class CloneResult:
    """克隆结果。"""
    repo_path: str                                          # 本地克隆路径
    files: list[FileInfo] = field(default_factory=list)     # 文件列表
    languages: dict[str, int] = field(default_factory=dict) # 语言 → 文件数
    total_lines: int = 0
    skipped_count: int = 0
```

### 1.4 依赖图结构

> 文件：`mcp-server/src/parsers/dependency_graph.py`

```python
@dataclass
class NodeAttrs:
    """依赖图节点属性。"""
    file: str
    line_start: int = 0
    line_end: int = 0
    module_group: str = ""
    node_type: str = "function"        # "function" | "class" | ...

@dataclass
class EdgeAttrs:
    """依赖图边属性。"""
    data_label: str = ""               # 边标签（如调用说明）
    call_count: int = 1                # 调用次数
    is_critical_path: bool = False     # 是否关键路径
```

**⚠️ 与原版差异**：
- 原版边属性为 `type`/`source_line`/`target_line`，实际为 `data_label`/`call_count`/`is_critical_path`
- 节点额外有 `module_group`、`node_type` 字段
- 模块级依赖图通过 `DependencyGraph.get_module_graph()` 获取，是独立的 NetworkX DiGraph

**⚠️ 约束**：依赖图的节点 ID 格式一旦确定不可随意变更，所有 tool 都依赖这个格式做查询。

### 1.5 摘要引擎数据结构

> 文件：`mcp-server/src/summarizer/engine.py`

```python
@dataclass
class SummaryContext:
    """生成摘要所需的完整上下文。被 repo_cache 缓存，供所有 tool 共用。"""
    clone_result: CloneResult
    parse_results: list[ParseResult]
    modules: list[ModuleGroup]
    dep_graph: DependencyGraph
    role: str = "pm"

@dataclass
class ModuleMapItem:
    """L2 模块地图中的一个模块（由 LLM 或本地逻辑生成）。"""
    name: str = ""
    paths: list[str] = field(default_factory=list)
    responsibility: str = ""
    entry_points: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    used_by: list[str] = field(default_factory=list)
    pm_note: str = ""

@dataclass
class ModuleCard:
    """L3 模块卡片。"""
    name: str = ""
    path: str = ""
    what: str = ""
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    branches: list[dict] = field(default_factory=list)
    side_effects: list[str] = field(default_factory=list)
    blast_radius: list[str] = field(default_factory=list)
    key_code_refs: list[str] = field(default_factory=list)
    pm_note: str = ""

@dataclass
class ModuleChapter:
    """read_chapter 的内部输出。"""
    module_name: str = ""
    cards: list[ModuleCard] = field(default_factory=list)
    dependency_graph: str = ""
```

### 1.6 代码生成引擎数据结构

> 文件：`mcp-server/src/tools/codegen_engine.py`

```python
@dataclass
class ExactLocation:
    file: str
    line: int
    why_it_matters: str
    certainty: str = "非常确定"

@dataclass
class LocateResult:
    matched_modules: str
    call_chain_mermaid: str
    exact_locations: list[ExactLocation]
    diagnosis: str

@dataclass
class ChangeSummaryItem:
    file: str
    line_range: str
    before: str
    after: str

@dataclass
class DiffBlock:
    file: str
    title: str
    diff_content: str
    before_desc: str
    after_desc: str

@dataclass
class BlastRadiusItem:
    file_or_module: str
    impact: str
    action_required: str

@dataclass
class VerificationStep:
    step: str
    expected_result: str

@dataclass
class CodegenOutput:
    change_summary: list[ChangeSummaryItem] = field(default_factory=list)
    diff_blocks: list[DiffBlock] = field(default_factory=list)
    blast_radius: list[BlastRadiusItem] = field(default_factory=list)
    verification_steps: list[VerificationStep] = field(default_factory=list)
    unified_diff: str = ""
    diff_valid: bool = False
    validation_detail: str = ""
    raw_llm_output: str = ""
```

### 1.7 Diff 验证数据结构

> 文件：`mcp-server/src/tools/diff_validator.py`

```python
@dataclass
class DiffHunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[str]

@dataclass
class FileDiff:
    old_path: str
    new_path: str
    hunks: list[DiffHunk] = field(default_factory=list)

@dataclass
class ValidationResult:
    valid: bool
    message: str
    details: list[str] = field(default_factory=list)
    repaired_diff: str | None = None
```

---

## 2. Tool 输入输出契约（MCP 对外接口）

### 2.1 scan_repo

> 文件：`mcp-server/src/tools/scan_repo.py`

**输入**：
```python
{
    "repo_url": str,           # Git 仓库 URL 或本地路径（必填）
    "role": str,               # "ceo" | "pm" | "investor" | "qa"（默认 "pm"）
    "depth": str,              # "overview" | "detailed"（默认 "overview"）
}
```

**输出（成功时）**：
```python
{
    "status": "ok",
    "repo_url": str,
    "role": str,
    "depth": str,
    "project_overview": str,           # 纯文本项目概览（不依赖 LLM，从解析数据提取）
    "modules": list[{                  # 增强后的模块列表
        "name": str,
        "node_title": str,             # 模块简短标题（来自 responsibility）
        "node_body": str,              # 丰富描述（含入口函数、公开接口）
        "inputs": list[str],           # 入口点
        "outputs": list[str],          # 被谁使用
        "health": str,                 # "green" | "yellow" | "red"
        "role_badge": str,             # 角色标签文本
        "source_refs": list[str],      # 关键函数的 file:L-L 引用（最多5个）
        "paths": list[str],            # 模块包含的路径
        "depends_on": list[str],       # 依赖的模块名
        "used_by": list[str],          # 被哪些模块使用
        "pm_note": str,               # PM 视角备注
    }],
    "connections": list[{              # 模块间连接关系
        "from": str,
        "to": str,
        "label": str,                  # 如 "调用 3 次"
        "strength": str,               # "strong" (>=5次) | "weak"
    }],
    "mermaid_diagram": str,            # 模块级 Mermaid 依赖图
    "stats": {
        "files": int,
        "code_files": int,
        "modules": int,
        "functions": int,
        "classes": int,
        "imports": int,
        "calls": int,
        "total_lines": int,
        "languages": dict[str, int],   # 语言 → 文件数
        "scan_time_seconds": float,
        "step_times": dict[str, float],# 各步骤耗时
    },
    "chapters": dict[str, dict] | None,  # 仅 depth="detailed" 时存在
}
```

**输出（错误时）**：
```python
{
    "status": "error",
    "error": str,
    "hint": str,               # 用户友好的解决建议
}
```

### 2.2 read_chapter

> 文件：`mcp-server/src/tools/read_chapter.py`

**输入**：
```python
{
    "module_name": str,        # 模块名称（支持精确/目录路径/模糊匹配）
    "role": str,               # 默认 "pm"
}
```

**输出（成功时）**：
```python
{
    "status": "ok",
    "module_name": str,
    "module_summary": {
        "dir_path": str,
        "total_files": int,
        "total_lines": int,
        "entry_functions": list[str],     # 最多10个
        "public_interfaces": list[str],   # 最多10个
    },
    "module_cards": list[{               # 每个文件一张卡片
        "name": str,                      # 文件名（无扩展名）
        "path": str,                      # 文件路径
        "summary": str,                   # 如 "5 个函数, 2 个类, 120 行"
        "functions": list[{
            "name": str,
            "params": list[str],          # 最多5个
            "return_type": str | None,
            "lines": str,                 # 如 "10-25"
            "is_method": bool,
            "doc": str | None,            # docstring 第一行（最多80字符）
            "class": str | None,          # 所属类名（method 才有）
        }],
        "classes": list[{
            "name": str,
            "methods": list[str],         # 最多10个
            "lines": str,
        }],
        "calls": list[{
            "from": str,
            "to": str,
            "line": int,
        }],
        "imports": list[str],             # 最多8个，格式如 "module (name1, name2)"
        "ref": str,                       # 如 "path/file.py:L1-L120"
    }],
    "dependency_graph": str,             # 模块内部 Mermaid 调用关系图
    "role": str,
    "pagination": {                      # 仅大模块（>3000行）且文件数>10 时存在
        "showing": int,
        "total": int,
        "remaining_files": list[str],
        "hint": str,
    } | None,
}
```

### 2.3 diagnose

> 文件：`mcp-server/src/tools/diagnose.py`

**输入**：
```python
{
    "module_name": str,        # 默认 "all"（全项目扫描）
    "role": str,               # 默认 "pm"
    "query": str,              # 自然语言问题描述（必填，用于关键词提取）
}
```

**输出（成功时）**：
```python
{
    "status": "ok",
    "module_name": str,
    "role": str,
    "query": str,
    "keywords": list[str],                   # 从 query 提取的关键词
    "matched_modules": list[str],            # 匹配到的模块名
    "matched_nodes": list[{                  # 匹配到的图节点
        "node_id": str,
        "score": float,
        "label": str,
        "file": str,
    }],
    "call_chain": str,                       # Mermaid 流程图（带颜色标记）
    "exact_locations": list[{                # 精确代码定位
        "node_id": str,
        "label": str,
        "file": str,
        "line_start": int,
        "line_end": int,
        "module_group": str,
        "node_type": str,
        "direction": str,                    # "seed" | "upstream" | "downstream"
        "priority": str,                     # "high" | "medium" | "low"
        "ref": str,                          # 如 "file.py:L10-L25"
        "code_snippet": str | None,          # 带行号的代码片段
    }],
    "context": str,                          # 供 MCP 宿主推理的结构化上下文文本
    "guidance": str,                         # 角色引导文本
}
```

**输出（无精确匹配时）**：
```python
{
    "status": "no_exact_match",
    "message": str,
    "module_name": str,
    "query": str,
    "keywords": list[str],
    "matched_modules": list[str],
    "call_chain": str,                       # 降级为模块级 Mermaid
    "exact_locations": [],
    "context": str,
    "guidance": str,
}
```

### 2.4 ask_about

> 文件：`mcp-server/src/tools/ask_about.py`
>
> **架构说明**：MCP 模式下，ask_about 不内部调用 LLM，而是将组装好的上下文
> 返回给 MCP 宿主（Claude Desktop），由宿主 LLM 直接推理。

**输入**：
```python
{
    "module_name": str,                    # 模块名称（必填）
    "question": str,                       # 自然语言问题（必填）
    "role": str,                           # 默认 "ceo"（注意不是 "pm"）
    "conversation_history": list[{         # 多轮对话历史（可选）
        "role": str,                       # "user" | "assistant"
        "content": str,
    }] | None,
}
```

**输出（成功时）**：
```python
{
    "status": "ok",
    "module_name": str,
    "role": str,
    "context": str,                        # 组装好的上下文（含 L3 摘要 + 源码 + 邻居模块）
    "guidance": str,                       # 角色化的 system prompt
    "question": str,
    "conversation_history": list[dict],
    "context_modules_used": list[str],     # 上下文中包含的模块列表
}
```

**上下文组装优先级**（按顺序填充直到 60,000 字符上限）：
1. 目标模块 L3 摘要（必选）
2. 目标模块源代码（必选，大文件截取关键部分，最多占剩余预算一半）
3. 上下游 1 跳模块 L3 摘要（高优先级，最多6个）
4. 该模块已有诊断结果（高优先级，最近3条）
5. 用户批注（如有，最近5条）
6. 上下游 2 跳模块 L3 摘要（低优先级，最多4个）

### 2.5 codegen

> 文件：`mcp-server/src/tools/codegen.py` + `mcp-server/src/tools/codegen_engine.py`

**输入**：
```python
{
    "instruction": str,                    # 自然语言修改指令（必填）
    "repo_path": str,                      # 本地仓库路径（必填）
    "locate_result": dict | None,          # diagnose 的输出（可选，提高精度）
    "file_paths": list[str] | None,        # 要修改的文件路径列表（与 locate_result 互补）
    "role": str,                           # 默认 "pm"
}
```

**输出（成功时）**：
```python
{
    "status": "success" | "partial",
    "change_summary": list[{               # 业务语言变更摘要
        "file": str,
        "line_range": str,
        "before": str,
        "after": str,
    }],
    "unified_diff": str,                   # 完整 unified diff（可 git apply）
    "diff_blocks": list[{                  # 分文件 diff 块
        "file": str,
        "title": str,
        "diff_content": str,
        "before_desc": str,
        "after_desc": str,
    }],
    "blast_radius": list[{                 # 影响范围
        "file_or_module": str,
        "impact": str,
        "action_required": str,
    }],
    "verification_steps": list[{           # 验证步骤
        "step": str,
        "expected_result": str,
    }],
    "diff_valid": bool,                    # diff 是否通过 apply 验证
    "validation_detail": str,              # 验证详情
    "raw_llm_output": str,                 # 原始 LLM 输出（调试用）
}
```

### 2.6 term_correct

> 文件：`mcp-server/src/tools/term_correct.py`

**功能**：用户反馈术语翻译，驱动术语飞轮优化

**输入**：
```python
{
    "repo_url": str,                   # Git 仓库 URL（必填）
    "source_term": str,                # 代码中出现的术语（如 "idempotency"）
    "correct_translation": str,        # 用户认为正确的翻译（如 "幂等性"）
    "context": str | None,             # 术语出现的代码上下文（可选）
    "domain": str | None,              # 所属领域（fintech/healthcare/ecommerce/saas/general）
}
```

**输出（成功时）**：
```python
{
    "status": "success",
    "repo_url": str,
    "source_term": str,
    "accepted_translation": str,
    "confidence_increased": float,     # 置信度提升百分点
    "affected_modules": list[str],     # 受影响的模块（该术语曾出现处）
    "suggestion": str,                 # 下次使用该术语时的建议
}
```

**输出（错误时）**：
```python
{
    "status": "error",
    "error": str,
    "hint": str,
}
```

### 2.7 memory_feedback

> 文件：`mcp-server/src/tools/memory_feedback.py`

**功能**：记录用户对诊断/问答结果的反馈，驱动 smart memory 学习

**输入**：
```python
{
    "repo_url": str,                   # Git 仓库 URL（必填）
    "module_name": str,                # 相关模块名（必填）
    "feedback_type": str,              # "helpful" | "unhelpful" | "incorrect" | "missing"
    "content": str,                    # 反馈内容（自由文本）
    "related_interaction": dict | None,# 关联的 diagnose/ask_about 交互记录（可选）
}
```

**输出（成功时）**：
```python
{
    "status": "ok",
    "repo_url": str,
    "feedback_id": str,                # 反馈记录 ID（用于审计）
    "stored_at": str,                  # ISO 8601 时间戳
    "suggestion": str,                 # 系统对此反馈的处理意见
    "hotspot_update": dict | None,     # 若检测到新热点，返回其信息
}
```

**输出（错误时）**：
```python
{
    "status": "error",
    "error": str,
    "hint": str,
}
```

---

## 3. 角色系统接口（v0.3 三核心视图系统）

**当前**：✅ v0.3 已实现 — 三核心视图系统（dev/pm/domain_expert）加向后兼容映射

**三种核心视图**：

| 视图 | 目标用户 | 核心诉求 | 翻译策略 |
|------|---------|---------|---------|
| **dev** | 开发者、架构师 | 代码逻辑、性能瓶颈、边界条件 | 函数签名、调用栈、精确行号、无术语限制 |
| **pm** | 产品经理、管理层 | 功能影响、变更风险、交付估算 | 业务模块、完成度、关键路径、禁止技术术语 |
| **domain_expert** | 行业专家、合规官 | 业务规则验证、风险识别、术语准确性 | 行业术语、领域逻辑、合规检查点、术语适配 |

**各 tool 的默认角色**：
- scan_repo: `"pm"`
- read_chapter: `"pm"`
- diagnose: `"pm"`
- ask_about: `"ceo"`（自动规范化为 `"pm"`，见下方向后兼容）
- codegen: `"pm"`

**向后兼容性映射**：

| 旧角色 | 映射到 | 说明 |
|--------|--------|------|
| `ceo` | `pm` | CEO 关注商业，映射到 PM 的商业影响视角 |
| `pm` | `pm` | 直接对应 |
| `investor` | `pm` | 投资人关注可扩展性，映射到 PM 的风险识别 |
| `qa` | `dev` | QA 关注边界条件，映射到 dev 的精确定位视角 |
| `dev` | `dev` | 直接对应 |
| `domain_expert` | `domain_expert` | 新增，需要显式传 project_domain |

**实现细节**：

1. **role 规范化**（engine.py 中的 `_normalize_role(role: str) -> str`）：
   - 接受 6 种输入：ceo, pm, investor, qa, dev, domain_expert
   - 输出 3 种规范化角色：dev, pm, domain_expert
   - 配置来源：codebook_config_v0.3.json 的 `backward_compatibility.mappings` 字段

2. **工具中的使用**：
   - ask_about.py：ROLE_CONFIG（包含两部分：新视图 + 向后兼容旧角色）+ `_build_system_prompt()` 中调用 `_normalize_role(role)`
   - diagnose.py：ROLE_GUIDANCE（包含新视图 + 向后兼容旧角色）+ `diagnose()` 函数中调用 `_normalize_role(role)`
   - scan_repo.py：`_role_badge(role)` 中调用 `_normalize_role(role)` 后返回对应标签
   - read_chapter.py：文档更新，说明支持 dev/pm/domain_expert（以及向后兼容的旧名称）
   - codegen.py：文档更新，说明支持 dev/pm/domain_expert

3. **project_domain 参数**（用于 domain_expert 视角的术语适配）：
   - 三层推断机制（见 role_system_v0_3_design.md §4）：
     1. 显式参数（scan_repo 调用中的 `project_domain` 参数）
     2. 自动推断（从 README.md 关键词和依赖包名推断）
     3. 术语库记忆（从 ~/.codebook/memory/{repo_hash}/meta.json 读取）
   - 支持的领域：fintech, healthcare, ecommerce, saas, general
   - 各领域对应的 guidance 已在 codebook_config_v0.3.json 的 `guidance_templates` 中预配置

**质量目标**（相比 v0.2 的改进）**：
- dev 视角：输出包含完整代码片段和调用栈，函数签名、参数类型、返回值明确标注
- pm 视角：禁用所有技术术语（幂等、slug、连接池等），使用业务语言描述
- domain_expert 视角：术语映射精度由项目领域数据飞轮深度决定，金融领域已支持 KYC/AML 等专业术语

**⚠️ 实现约束**（保证兼容性）**：
- 对外接口保持向后兼容，旧角色名仍可使用，自动规范化
- 不改变 tool 的输入输出 JSON 格式，只影响输出的自然语言风格和 guidance 文本
- domain_expert 的翻译质量取决于 project_domain 的指定和行业数据飞轮的积累深度
- 所有工具的 role 参数都应先调用 `_normalize_role()` 再使用

---

## 4. 缓存机制

> 文件：`mcp-server/src/tools/_repo_cache.py`

- `scan_repo` 扫描后将 `SummaryContext` 存入 `repo_cache`
- `read_chapter`、`diagnose`、`ask_about` 通过 `repo_cache.get()` 获取上下文
- 缓存按最后访问时间计算，超过 7 天未使用会过期（返回 `_ExpiredSentinel`）
- 过期后需重新运行 `scan_repo`

---

## 5. 文件存储约定

| 路径 | 用途 | 持久化 |
|------|------|--------|
| `repos/` | clone 的测试仓库 | 不提交到 CodeBook 仓库 |
| `test_results/` | 压力测试结果 | 按项目名建子目录 |
| `src/config/` | Prompt 配置文件 | 提交 |
| `.codebook/` | 运行时缓存（AST 缓存、索引） | 不提交 |

---

## 变更记录

| 日期 | 变更内容 | 影响的模块 |
|------|---------|-----------|
| 2026-03-22 | 初始版本，基于 MCP v0.1 接口整理（推断版） | 全部 |
| 2026-03-23 | **全面校准**：与实际代码逐行对齐，修正所有数据结构 | 全部 |

### 2026-03-23 校准详情

| 原版内容 | 实际代码 | 差异说明 |
|----------|---------|---------|
| `ParsedSymbol` dataclass | 不存在 | 实际按类型拆分为 `FunctionInfo`/`ClassInfo`/`ImportInfo`/`CallInfo`，由 `ParseResult` 按文件聚合 |
| `Module` (name, path, files, symbols, description) | `ModuleGroup` (name, dir_path, files, entry_functions, public_interfaces, total_lines, is_special) | 类名不同，字段完全不同 |
| 依赖图边 `type`/`source_line`/`target_line` | `data_label`/`call_count`/`is_critical_path` | 边属性含义完全不同 |
| scan_repo 输出 `blueprint_json` | 输出 `project_overview` + `connections` + 增强 `modules` | 输出结构大幅不同 |
| scan_repo stats `total_symbols`/`scan_duration_ms` | 分项 `functions`/`classes`/`imports`/`calls` + `scan_time_seconds` + `step_times` | stats 粒度更细 |
| read_chapter 输出 `subcomponents`/`call_graph`/`branch_logic` | 输出 `module_summary` + `module_cards`（按文件组织的卡片） | 结构完全重设计 |
| diagnose 输入 `description` | 输入 `query` | 参数名不同 |
| diagnose 输出 `flow_chart`/`root_cause_hypothesis`/`suggested_next_steps` | 输出 `call_chain`/`matched_nodes`/`context`/`guidance` | diagnose 不做推理，把上下文交给 MCP 宿主 |
| ask_about 输出 `answer`/`references` | 输出 `context`/`guidance`/`context_modules_used` | MCP 模式下不内部调用 LLM，返回上下文让宿主推理 |
| codegen 输出 `diffs`/`impact_analysis` | 输出 `change_summary`/`diff_blocks`/`blast_radius`/`unified_diff`/`diff_valid` | 结构更丰富，增加 diff 验证 |
