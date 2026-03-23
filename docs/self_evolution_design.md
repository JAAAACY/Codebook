# CodeBook 自我进化系统设计方案

> **版本**：v0.1 Draft
> **日期**：2026-03-23
> **关联**：Sprint 2 Pipeline B (角色系统重构), CONTEXT.md D-005 (数据飞轮冷启动)
> **目标**：让 CodeBook 越用越好用——用户的每一次交互都在为下一次交互提供更好的体验

---

## 一、设计全景

```
┌─────────────────────────────────────────────────────────────────┐
│                     用户交互层                                    │
│  scan_repo → read_chapter → diagnose → ask_about → codegen      │
└───────────┬──────────────────────────────────┬──────────────────┘
            │ 产生信号                          │ 消费知识
            ▼                                  ▼
┌─────────────────────┐          ┌──────────────────────────────┐
│   术语飞轮引擎        │          │   项目记忆系统                 │
│  TermFlywheel        │          │  ProjectMemory                │
│                     │          │                              │
│  · 领域术语库        │◄────────►│  · 模块理解缓存               │
│  · 用户纠正记录      │          │  · 高频问题沉淀               │
│  · 跨项目术语模式    │          │  · 对话历史索引               │
│  · 术语质量评分      │          │  · 跨会话知识图谱             │
└─────────┬───────────┘          └──────────┬───────────────────┘
          │                                 │
          └────────────┬────────────────────┘
                       ▼
              ┌──────────────────┐
              │  ~/.codebook/     │
              │  持久化存储层      │
              └──────────────────┘
```

**核心原则**：

1. **隐私优先**：所有数据存储在用户本地 (`~/.codebook/`)，不上传任何代码或业务数据
2. **渐进增强**：飞轮和记忆是锦上添花，缺失时系统完全可用，不降级
3. **低侵入**：现有 5 个 tool 的输入输出 JSON 格式不变，只优化自然语言翻译质量
4. **可观测**：每次翻译使用了哪些飞轮/记忆数据，在 debug 日志中可追溯

---

## 二、术语飞轮（TermFlywheel）

### 2.1 现状分析

当前术语系统是**静态词表**：

```
codebook_config_v0.2.json
  └── banned_terms_in_pm_fields.terms  →  11 个硬编码映射
  └── http_status_code_annotations     →  10 个状态码注释
```

注入路径：

```
engine.py::_get_banned_terms()  →  L2/L3 prompt 的 {banned_terms} 变量
ask_about.py::ROLE_CONFIG       →  4 个角色的 banned_terms 字符串
```

**问题**：
- 词表固定，无法适应不同行业（金融 vs 医疗 vs 电商）
- 用户发现翻译不准时无法反馈
- 同一个术语在不同项目中可能有不同的最佳翻译

### 2.2 目标架构

```
                         ┌─────────────────────┐
                         │  用户纠正一个术语     │
                         └──────────┬──────────┘
                                    ▼
┌──────────────┐    ┌──────────────────────────────┐
│ 全局默认词表  │    │     项目级术语库               │
│ (11个基础映射) │───►│  project_glossary.json         │
│ config v0.2  │    │  · 继承全局默认                │
│              │    │  · 用户纠正覆盖默认             │
│              │    │  · 按 project_domain 加载行业包 │
└──────────────┘    └──────────────┬───────────────┘
                                   │
                    ┌──────────────┼──────────────┐
                    ▼              ▼              ▼
              L2 prompt      L3 prompt     ask_about guidance
              注入术语表      注入术语表     注入术语表
```

### 2.3 数据结构设计

#### 2.3.1 术语条目（TermEntry）

```python
@dataclass
class TermEntry:
    """一条术语映射。"""
    source_term: str          # 原始术语（如 "idempotent", "幂等"）
    target_phrase: str         # 翻译后的业务表达（如 "重复操作不会产生副作用"）
    context: str = ""          # 适用场景描述（如 "API 接口描述中"）
    domain: str = "general"    # 所属领域（"general" | "fintech" | "healthcare" | ...）
    source: str = "default"    # 来源（"default" | "user_correction" | "inferred"）
    confidence: float = 1.0    # 置信度（0-1，用户纠正的=1.0，推断的<1.0）
    usage_count: int = 0       # 被使用次数（飞轮信号：越高说明越被接受）
    created_at: str = ""       # ISO 时间戳
    updated_at: str = ""       # ISO 时间戳
```

#### 2.3.2 项目级术语库（ProjectGlossary）

存储位置：`~/.codebook/glossaries/{repo_hash}/glossary.json`

```json
{
  "version": 1,
  "repo_url": "https://github.com/example/fintech-app",
  "project_domain": "fintech",
  "terms": [
    {
      "source_term": "transaction rollback",
      "target_phrase": "交易撤销",
      "context": "支付流程中",
      "domain": "fintech",
      "source": "user_correction",
      "confidence": 1.0,
      "usage_count": 12,
      "created_at": "2026-03-23T10:00:00Z",
      "updated_at": "2026-03-23T10:00:00Z"
    }
  ],
  "correction_log": [
    {
      "timestamp": "2026-03-23T10:00:00Z",
      "original": "事务回滚",
      "corrected": "交易撤销",
      "source_term": "transaction rollback",
      "module_context": "payment_processing"
    }
  ]
}
```

#### 2.3.3 行业术语包（DomainPack）

存储位置：`~/.codebook/domain_packs/{domain}.json`

预装包随 CodeBook 分发，用户可扩展。

```json
{
  "domain": "fintech",
  "version": "1.0",
  "display_name": "金融科技",
  "terms": [
    {"source_term": "KYC", "target_phrase": "客户身份验证（Know Your Customer）"},
    {"source_term": "AML", "target_phrase": "反洗钱检查"},
    {"source_term": "settlement", "target_phrase": "资金结算"},
    {"source_term": "ledger", "target_phrase": "账本记录"},
    {"source_term": "reconciliation", "target_phrase": "对账"}
  ]
}
```

### 2.4 术语解析优先级

当生成翻译时，术语查找按以下优先级合并：

```
1. 用户纠正（source=user_correction, confidence=1.0）    ← 最高
2. 项目级术语库（project_glossary.json 中的条目）
3. 行业术语包（按 project_domain 加载）
4. 全局默认词表（codebook_config_v0.2.json）              ← 最低
```

**合并规则**：高优先级覆盖低优先级，同优先级按 confidence 排序。

### 2.5 用户纠正工作流

#### 方式一：ask_about 对话中纠正

```
用户: "这里说的'事务回滚'不准确，在我们的业务里应该叫'交易撤销'"

→ MCP 宿主识别到纠正意图
→ 调用新增的 term_correct tool
→ 写入 project_glossary.json
→ 后续所有 tool 输出自动使用新术语
```

#### 方式二：新增 MCP tool `term_correct`

```python
# 新增 tool 接口
{
    "tool": "term_correct",
    "input": {
        "source_term": "transaction rollback",     # 原始术语
        "wrong_translation": "事务回滚",           # 错误翻译（可选）
        "correct_translation": "交易撤销",         # 正确翻译
        "context": "支付流程中",                   # 适用场景（可选）
    },
    "output": {
        "status": "ok",
        "message": "已记录：transaction rollback → 交易撤销。后续翻译将自动使用。",
        "affected_scope": "当前项目"
    }
}
```

#### 方式三：批量导入

```python
# 支持从 CSV/JSON 批量导入术语
{
    "tool": "term_import",
    "input": {
        "file_path": "/path/to/glossary.csv",      # CSV: source_term, target_phrase, context
        "domain": "fintech",                         # 标记领域
        "merge_strategy": "user_wins"                # 冲突时用户导入优先
    }
}
```

### 2.6 飞轮机制：隐式学习

除了显式纠正，系统还通过以下信号隐式优化术语质量：

**信号 1：使用频率追踪**

每次翻译命中某个术语映射时，`usage_count += 1`。高频使用说明用户接受了这个翻译。

**信号 2：术语在 ask_about 中的出现**

如果用户在追问时反复用某个业务词汇指代某个代码概念，系统可以推断出一个新的术语映射（`source=inferred, confidence=0.7`），下次遇到同样的代码概念时优先使用。

**信号 3：跨项目模式**

如果同一个 `project_domain` 下多个项目都产生了相同的术语纠正，可以提升该映射到行业术语包级别（需要用户确认）。

### 2.7 代码改动清单

| 文件 | 改动内容 | 优先级 |
|------|---------|--------|
| **新增** `src/glossary/term_store.py` | TermEntry, ProjectGlossary, DomainPack 数据类 + 读写逻辑 | P0 |
| **新增** `src/glossary/term_resolver.py` | 术语解析器：合并多层级术语表，输出最终映射 | P0 |
| **新增** `src/tools/term_correct.py` | term_correct MCP tool 实现 | P0 |
| **修改** `src/summarizer/engine.py` | `_get_banned_terms()` → 改为调用 `term_resolver` | P0 |
| **修改** `src/tools/ask_about.py` | `ROLE_CONFIG.banned_terms` → 改为从 `term_resolver` 获取 | P0 |
| **修改** `src/tools/scan_repo.py` | 扫描时检测 project_domain（从 README/package.json 推断） | P1 |
| **修改** `server.py` | 注册 term_correct tool | P0 |
| **新增** `domain_packs/` 目录 | 预装 fintech / healthcare / ecommerce 三个行业包 | P1 |
| **新增** `src/tools/term_import.py` | 批量导入 tool（CSV/JSON） | P2 |

### 2.8 与 Pipeline B 的衔接

Pipeline B 正在设计的 `project_domain` 参数（Decision D-004）直接驱动术语飞轮的行业术语包加载：

```python
# scan_repo 输入中的 project_domain 参数
{
    "repo_url": "...",
    "role": "domain_expert",
    "project_domain": "fintech"  # ← 触发加载 fintech.json 行业术语包
}
```

如果用户不传 `project_domain`，系统尝试从以下位置自动推断：

1. `README.md` 中的关键词（"金融"、"支付"、"医疗"、"电商"等）
2. 依赖包名（`stripe`→fintech, `fhir`→healthcare）
3. 已有的项目级术语库中的 domain 字段

---

## 三、项目记忆系统（ProjectMemory）

### 3.1 现状分析

当前缓存架构：

```
_repo_cache.py (RepoCache)
  ├── 内存缓存：dict[repo_url → SummaryContext]
  └── 磁盘缓存：~/.codebook_cache/contexts/{hash}.json
      · 内容：CloneResult + ParseResults + ModuleGroups + DependencyGraph
      · TTL：7 天（touch on read 延长）
      · 版本：v1
```

```
ask_about.py (DiagnosisCache)
  ├── 诊断结果：dict[module_name → list[diagnosis]]
  └── 用户批注：dict[module_name → list[annotation]]
  · 纯内存，进程退出即丢失
```

**问题**：
- DiagnosisCache 不持久化——每次新会话从零开始
- 没有"这个模块被问过什么"的记录
- 没有跨会话的对话历史
- ask_about 的 conversation_history 只在单次调用内有效

### 3.2 目标架构

```
                    ┌──────────────────────────────┐
                    │     ProjectMemory             │
                    │  ~/.codebook/memory/{hash}/   │
                    │                              │
                    │  ┌────────────────────────┐  │
                    │  │ 1. 结构记忆             │  │
                    │  │    (现有 RepoCache 升级)  │  │
                    │  │    · SummaryContext      │  │
                    │  │    · 增量更新支持        │  │
                    │  └────────────────────────┘  │
                    │                              │
                    │  ┌────────────────────────┐  │
                    │  │ 2. 理解记忆             │  │
                    │  │    (新增)               │  │
                    │  │    · 诊断结果持久化      │  │
                    │  │    · 模块级 Q&A 索引     │  │
                    │  │    · 翻译质量反馈        │  │
                    │  └────────────────────────┘  │
                    │                              │
                    │  ┌────────────────────────┐  │
                    │  │ 3. 交互记忆             │  │
                    │  │    (新增)               │  │
                    │  │    · 对话摘要索引        │  │
                    │  │    · 高频问题聚类        │  │
                    │  │    · 用户关注点画像      │  │
                    │  └────────────────────────┘  │
                    │                              │
                    └──────────────────────────────┘
```

### 3.3 数据结构设计

#### 3.3.1 存储目录结构

```
~/.codebook/memory/{repo_hash}/
├── context.json              # 结构记忆（升级后的 SummaryContext，原 RepoCache）
├── understanding.json        # 理解记忆
├── interactions.json         # 交互记忆
└── meta.json                 # 元信息（repo_url, domain, 统计数据）
```

#### 3.3.2 理解记忆（UnderstandingMemory）

```python
@dataclass
class ModuleUnderstanding:
    """对一个模块的累积理解。"""
    module_name: str

    # 持久化的诊断结果（从 DiagnosisCache 升级）
    diagnoses: list[DiagnosisRecord] = field(default_factory=list)

    # 该模块被问过的问题 + 回答摘要
    qa_history: list[QARecord] = field(default_factory=list)

    # 用户批注
    annotations: list[AnnotationRecord] = field(default_factory=list)

    # 统计
    view_count: int = 0           # read_chapter 被调用次数
    diagnose_count: int = 0       # diagnose 涉及此模块的次数
    ask_count: int = 0            # ask_about 此模块的次数
    last_accessed: str = ""       # ISO 时间戳


@dataclass
class DiagnosisRecord:
    """一次诊断的持久记录。"""
    query: str                     # 原始问题
    diagnosis_summary: str         # 诊断结论摘要
    matched_locations: list[str]   # file:line 列表
    timestamp: str = ""


@dataclass
class QARecord:
    """一次 ask_about 对话的摘要记录。"""
    question: str                  # 用户问题
    answer_summary: str            # 回答摘要（不存全文，只存关键结论）
    confidence: float = 0.0        # 回答置信度
    follow_ups_used: list[str] = field(default_factory=list)  # 用户实际追问的方向
    timestamp: str = ""
```

存储格式（`understanding.json`）：

```json
{
  "version": 1,
  "modules": {
    "payment_processing": {
      "module_name": "payment_processing",
      "diagnoses": [
        {
          "query": "支付超时后用户重复点击会怎样",
          "diagnosis_summary": "缺少幂等检查，重复支付请求会创建多笔订单",
          "matched_locations": ["payment/handler.py:L45", "payment/handler.py:L78"],
          "timestamp": "2026-03-23T10:00:00Z"
        }
      ],
      "qa_history": [
        {
          "question": "这个模块怎么处理退款",
          "answer_summary": "退款通过 refund_processor 处理，先冻结原交易再创建反向交易",
          "confidence": 0.9,
          "follow_ups_used": ["退款失败怎么处理"],
          "timestamp": "2026-03-23T10:15:00Z"
        }
      ],
      "annotations": [],
      "view_count": 5,
      "diagnose_count": 2,
      "ask_count": 3,
      "last_accessed": "2026-03-23T10:15:00Z"
    }
  }
}
```

#### 3.3.3 交互记忆（InteractionMemory）

```python
@dataclass
class InteractionMemory:
    """跨会话的交互模式记忆。"""

    # 高频问题聚类：当多个不同问题指向同一模块的同一区域时，聚合为一个热点
    hotspots: list[Hotspot] = field(default_factory=list)

    # 用户关注点画像：哪些模块/主题被频繁访问
    focus_profile: dict[str, int] = field(default_factory=dict)  # module_name → 访问权重

    # 会话摘要索引
    session_summaries: list[SessionSummary] = field(default_factory=list)


@dataclass
class Hotspot:
    """一个知识热点——多次被问到的区域。"""
    module_name: str
    topic: str                    # 热点主题（如 "退款流程"、"权限检查"）
    question_count: int           # 相关问题数量
    typical_questions: list[str]  # 代表性问题（最多3个）
    suggested_doc: str = ""       # 系统建议补充的文档内容


@dataclass
class SessionSummary:
    """一次会话的摘要。"""
    session_id: str
    timestamp: str
    modules_explored: list[str]   # 本次会话涉及的模块
    key_findings: list[str]       # 关键发现（如 "发现支付模块缺少幂等检查"）
    unresolved_questions: list[str]  # 未解决的问题
```

### 3.4 记忆写入时机

| 事件 | 写入什么 | 写到哪里 |
|------|---------|---------|
| `scan_repo` 完成 | SummaryContext + meta | `context.json` + `meta.json` |
| `read_chapter` 完成 | `view_count += 1` | `understanding.json` |
| `diagnose` 完成 | DiagnosisRecord | `understanding.json` |
| `ask_about` 返回后（宿主推理完成） | QARecord | `understanding.json` |
| `term_correct` 调用 | 术语纠正 | `glossary.json`（术语飞轮侧） |
| 会话结束 | SessionSummary | `interactions.json` |

**关键设计决策**：`ask_about` 返回的是上下文而非答案（MCP 模式），所以 QARecord 的写入需要 MCP 宿主回调。方案有两个：

- **方案 A（推荐）**：新增 `memory_feedback` tool，宿主在生成回答后调用，传入回答摘要和置信度
- **方案 B**：在下一次 `ask_about` 调用时，从 `conversation_history` 中提取上一轮的回答摘要

### 3.5 记忆读取与注入

#### 3.5.1 ask_about 上下文增强

当前 `assemble_context()` 的优先级列表（6 级）扩展为 8 级：

```python
# 现有
1. 目标模块 L3 摘要（必选）
2. 目标模块源代码（必选）
3. 上下游 1 跳模块 L3 摘要（高优先级）
4. 该模块已有诊断结果（高优先级）    ← 从 DiagnosisCache → 改为从 understanding.json
5. 用户批注（如有）                  ← 从 DiagnosisCache → 改为从 understanding.json

# 新增
6. 该模块的 QA 历史摘要（中优先级）   ← 新增：之前问过的问题和回答
7. 相关热点信息（中优先级）           ← 新增：如果当前问题命中已知热点

# 现有（降级）
8. 上下游 2 跳模块 L3 摘要（低优先级）
```

#### 3.5.2 diagnose 精度增强

如果 `understanding.json` 中已有该模块的诊断记录，`diagnose` 可以：
- 避免重复定位已知问题
- 在 `context` 字段中附带历史诊断信息，帮助宿主给出更精准的新诊断

#### 3.5.3 scan_repo 增量更新

当前 scan_repo 每次全量重扫。有了项目记忆后可以做增量：

```python
# 伪代码
if memory_exists(repo_url):
    old_context = load_context()
    changed_files = detect_changes(old_context, current_repo)
    if len(changed_files) / total_files < 0.3:  # 变更不超过 30%
        # 增量更新：只重新解析变更的文件
        incremental_scan(changed_files, old_context)
    else:
        # 变更太大，全量重扫
        full_scan()
```

这同时解决了 CONTEXT.md 中的 Decision D-001（大项目 scan_repo 超时）和 D-003（缓存层避免重复解析）。

### 3.6 代码改动清单

| 文件 | 改动内容 | 优先级 |
|------|---------|--------|
| **新增** `src/memory/project_memory.py` | ProjectMemory 主类：统一管理三层记忆的读写 | P0 |
| **新增** `src/memory/understanding.py` | ModuleUnderstanding, DiagnosisRecord, QARecord 数据类 | P0 |
| **新增** `src/memory/interactions.py` | InteractionMemory, Hotspot, SessionSummary 数据类 | P1 |
| **修改** `src/tools/_repo_cache.py` | RepoCache → 委托给 ProjectMemory 的结构记忆层 | P0 |
| **修改** `src/tools/ask_about.py` | DiagnosisCache → 改用 ProjectMemory；assemble_context 扩展 | P0 |
| **修改** `src/tools/diagnose.py` | 完成后写入 DiagnosisRecord | P0 |
| **修改** `src/tools/read_chapter.py` | 完成后更新 view_count | P1 |
| **新增** `src/tools/memory_feedback.py` | memory_feedback MCP tool（宿主回传回答摘要） | P1 |
| **修改** `server.py` | 注册 memory_feedback tool | P1 |

---

## 四、两个系统的协同

术语飞轮和项目记忆不是独立的——它们通过以下方式互相增强：

```
项目记忆                            术语飞轮
─────────                          ─────────
QA 历史中用户反复使用的 ──────────► 推断新的术语映射
业务词汇                            (source=inferred)

诊断结果中的模块上下文 ──────────► 术语的 context 字段
                                    (提高翻译精度)

                                    术语纠正记录
模块理解中的翻译质量 ◄──────────── (反馈到模块级
改进信号                            理解质量评分)
```

具体场景：

1. 用户在 `ask_about` 中问 "这个模块的风控阈值怎么配置"
2. 系统在 QARecord 中记录用户使用了 "风控阈值" 这个词
3. 如果代码中对应的是 `risk_threshold`，系统推断出映射 `risk_threshold → 风控阈值`
4. 下次 `read_chapter` 或 `diagnose` 涉及这个概念时，自动使用 "风控阈值"

---

## 五、实施路线图

### Phase 1：基础持久化（1-2 周）

**目标**：让现有的内存数据活过会话重启

| 任务 | 关联文件 | 估时 |
|------|---------|------|
| 实现 ProjectMemory 存储层（读写 JSON） | `memory/project_memory.py` | 2d |
| DiagnosisCache → 持久化到 understanding.json | `ask_about.py`, `diagnose.py` | 1d |
| RepoCache 迁移到 ProjectMemory 统一目录 | `_repo_cache.py` | 1d |
| 单元测试 | `tests/test_memory.py` | 1d |

**验收标准**：关闭并重启 MCP server 后，之前的诊断结果和扫描缓存仍然可用。

### Phase 2：术语飞轮 MVP（1-2 周）

**目标**：用户可以纠正术语，纠正立即生效

| 任务 | 关联文件 | 估时 |
|------|---------|------|
| 实现 TermEntry + ProjectGlossary 数据结构 | `glossary/term_store.py` | 1d |
| 实现 TermResolver（多层级合并） | `glossary/term_resolver.py` | 1d |
| 实现 term_correct MCP tool | `tools/term_correct.py`, `server.py` | 1d |
| engine.py 和 ask_about.py 接入 TermResolver | `engine.py`, `ask_about.py` | 1d |
| 预装 3 个行业术语包 | `domain_packs/` | 2d |
| 集成测试 | `tests/test_glossary.py` | 1d |

**验收标准**：用户纠正一个术语后，后续所有 tool 输出立即使用新翻译。

### Phase 3：智能记忆（2-3 周）

**目标**：系统能利用历史交互提升翻译和定位质量

| 任务 | 关联文件 | 估时 |
|------|---------|------|
| QARecord 写入 + ask_about 上下文注入 | `ask_about.py`, `memory_feedback.py` | 2d |
| Hotspot 聚类算法（基于关键词相似度） | `memory/interactions.py` | 2d |
| scan_repo 增量更新（文件 hash 比对） | `scan_repo.py`, `project_memory.py` | 3d |
| 术语隐式推断（从 QA 历史中提取映射） | `glossary/term_resolver.py` | 2d |
| SessionSummary 自动生成 | `memory/interactions.py` | 1d |
| 端到端测试 | `tests/test_evolution.py` | 2d |

**验收标准**：同一项目的第二次会话中，ask_about 能引用第一次会话的发现；术语翻译质量可观测地提升。

### Phase 4：跨项目模式（远期）

- 同 domain 项目间的术语模式共享
- AST 拓扑签名 → 设计模式识别（CONTEXT.md D-005）
- 团队知识图谱（多用户场景）

---

## 六、风险与缓解

| 风险 | 影响 | 缓解策略 |
|------|------|---------|
| 磁盘存储膨胀 | 大项目的 memory 文件过大 | 每个记忆层设上限（understanding: 100 条/模块, interactions: 50 个会话），FIFO 淘汰 |
| 术语冲突 | 同一术语不同人纠正为不同翻译 | 单用户场景下不存在；多用户场景留到 Phase 4 设计投票机制 |
| 增量扫描不一致 | 文件间依赖变化导致增量结果不准 | 设 30% 变更阈值强制全量扫描；增量后跑依赖图一致性检查 |
| 旧版缓存兼容 | 现有 v1 cache 文件如何迁移 | ProjectMemory 初次加载时检测旧格式，自动迁移到新目录结构 |
| 推断术语不准 | 隐式推断的映射质量低 | confidence < 0.8 的推断术语标记为 "suggested"，不自动注入 prompt；需用户确认后才升为正式 |

---

## 七、度量指标

如何衡量"越用越好用"？

| 指标 | 采集方式 | 目标值 |
|------|---------|--------|
| **术语命中率** | 翻译时从飞轮命中的术语占比 | Phase 2 后 >30%，Phase 3 后 >50% |
| **纠正率趋势** | 每 10 次交互的用户纠正次数 | 随使用递减（说明翻译越来越准） |
| **缓存命中率** | ask_about 从记忆中获取到有用上下文的比例 | Phase 1 后 >60% |
| **增量扫描比例** | scan_repo 走增量路径的比例 | Phase 3 后活跃项目 >80% |
| **会话间连续性** | 新会话是否引用了上一会话的发现 | Phase 3 后 >40% |

所有指标通过 structlog 日志采集，可在 `~/.codebook/metrics/` 下生成周报。

---

## 附录 A：与现有决策的关系

| 决策 ID | 内容 | 本方案的解答 | 状态 |
|---------|------|------------|------|
| D-001 | 大项目超时：增量扫描 vs lazy loading | **增量扫描**——Phase 3 实现，基于文件 hash 比对 | ⏳ 待 A 线压测数据 |
| D-003 | 缓存层避免重复解析 | **ProjectMemory 统一存储层**（§3.2） | ✅ 03-23 确认 |
| D-004 | domain_expert 的 project_domain 传入 | **三层策略**：显式参数 > README/依赖推断 > 术语库 domain（§2.8） | ✅ 03-23 确认 |
| D-005 | 术语存储格式 | **JSON 格式**，存 ~/.codebook/memory/{repo_hash}/glossary.json（§2.3.2） | ✅ 03-23 确认 |
| D-004 | domain_expert 的 project_domain 传入机制 | scan_repo 输入参数 + 自动推断（README + 依赖包） |
| D-005 | 数据飞轮冷启动存储格式 | 术语飞轮 JSON + 行业术语包 JSON，存储在 `~/.codebook/` |
