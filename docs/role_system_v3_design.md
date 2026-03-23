# CodeBook 角色系统 v0.3 设计方案

**版本**：v0.3 Draft
**日期**：2026-03-23
**关联**：Pipeline B (角色系统重构), CONTEXT.md D-004 (domain_expert 设计)
**目标**：从 4 角色模板式系统演进为面向四类用户群的动态翻译系统

---

## 一、执行总结

### 现状诊断

当前 CodeBook v0.2 的角色系统存在以下问题：

1. **四角色模型（ceo/pm/investor/qa）本质是措辞替换**
   - 同一功能只改措辞和禁用术语，不改输出结构或重点
   - 无法适应不同用户群的核心诉求差异

2. **对标用户群的覆盖不完整**
   - 产品战略（2026-03-22）明确了四类核心用户：**开发者、管理层、行业专家、QA/运维**
   - 当前系统无法满足行业专家（如金融合规人员、医疗数据官）的核心需求

3. **跨工具的角色系统不一致**
   - diagnose 有 "dev" 角色，其他 tool 无
   - ask_about 默认角色是 "ceo"，其他 tool 默认 "pm"
   - 角色配置散落在 diagnose.py / ask_about.py / scan_repo.py

4. **输出差异化程度有限**
   - 定量分析：仅 10-15% 的输出内容真正因角色而改变
   - 其余 85-90% 是共同的结构化数据

### v0.3 核心改进

本方案引入**三核心视图 + 动态领域适配**架构：

| 视图 | 目标用户 | 核心诉求 | 翻译策略 |
|------|---------|---------|---------|
| **dev** | 开发者、架构师 | 代码逻辑、性能瓶颈、边界条件 | 函数签名、调用栈、具体行号 |
| **pm** | 产品经理、管理层 | 功能影响、变更风险、交付估算 | 业务模块、完成度百分比、关键路径 |
| **domain_expert** | 行业专家、合规官 | 业务规则验证、风险识别、术语准确性 | 行业术语、领域逻辑、合规检查点 |

其中 `domain_expert` 通过 `project_domain` 参数接收行业类型，系统动态加载对应的术语表和检查规则。

### 重点设计决策（解答 D-004）

| 决策 | 方案 | 理由 |
|------|------|------|
| domain_expert 的 project_domain 如何传入？ | 三层策略：显式参数 > README/依赖推断 > 术语库 | 用户优先，自动推断兜底 |
| 向后兼容性 | ceo→pm, investor→pm, qa→dev | 平滑迁移，已有脚本不破坏 |
| 与术语飞轮的关系 | domain_expert + project_domain 直接驱动术语加载 | 术语精度由行业数据飞轮深度决定 |

---

## 二、现有系统审计

### 2.1 五个工具的角色处理对比

#### scan_repo

```python
def _role_badge(role: str) -> str:
    badges = {
        "ceo": "CEO 视角：关注商业价值与战略意义",
        "pm": "PM 视角：关注功能完整性与风险",
        "investor": "投资人视角：关注技术壁垒与可扩展性",
        "qa": "QA 视角：关注测试覆盖与边界条件",
    }
```

**输出中的角色差异**：
- `modules[i].role_badge`：4 种不同文本
- `project_overview` 前缀：4 种不同的开头（"从商业视角看"vs"从产品视角看"等）
- 其他字段（stats, connections, mermaid_diagram）：无差异

**评估**：约 5% 的输出真正差异化

#### diagnose

```python
ROLE_GUIDANCE = {
    "pm": "用产品视角解释代码调用链，关注用户体验影响...",
    "dev": "提供精确的代码定位、调用链分析和修复建议...",
    "ceo": "用商业语言解释问题的影响范围和严重程度...",
    "qa": "关注测试覆盖、边界条件和复现路径...",
}
```

**输出中的角色差异**：
- `guidance` 字段：4 种不同的系统提示
- `matched_nodes`, `call_chain`, `exact_locations`：无差异（纯技术数据）

**评估**：约 15% 的输出真正差异化（仅 guidance 字段）

#### ask_about

```python
ROLE_CONFIG = {
    "ceo": {"name": "CEO / 创始人", "language_style": "...", "banned_terms": "..."},
    "pm": {"name": "产品经理", "language_style": "...", "banned_terms": "..."},
    "investor": {...},
    "qa": {...},
}
```

**输出中的角色差异**：
- `guidance` 字段：通过 `_build_system_prompt(role)` 生成，注入 banned_terms 和 language_style
- 实际 LLM 回答由 MCP 宿主生成（系统看不到），但宿主会遵循 guidance

**评估**：约 10-20% 的差异（通过 guidance 间接影响 LLM 输出风格）

#### read_chapter

```python
async def read_chapter(module_name: str, role: str = "pm") -> dict:
    # role 参数声明但未在实现中使用
    logger.info("read_chapter.start", module_name=module_name, role=role)
    # ... 生成 module_summary, module_cards, dependency_graph
    return {
        "status": "ok",
        "module_name": module_name,
        "module_cards": [...],  # 无角色差异
        "role": role,
    }
```

**输出中的角色差异**：无。角色参数完全未使用。

**评估**：0% 差异化（decorative parameter）

#### codegen

```python
async def codegen(
    instruction: str,
    repo_path: str,
    locate_result: dict | None = None,
    file_paths: list[str] | None = None,
    role: str = "pm",
) -> dict:
    output = codegen_engine.execute(
        instruction=instruction,
        context=context,
        role=role,  # 传给 engine，但 engine 中角色影响有限
    )
```

**输出中的角色差异**：
- `change_summary` 中的业务语言描述可能有差异
- diff 本身无差异，但摘要措辞不同

**评估**：约 5-10% 差异

### 2.2 量化分析结论

| 工具 | 差异化程度 | 主要差异点 |
|------|----------|----------|
| scan_repo | ~5% | role_badge, project_overview 前缀 |
| read_chapter | 0% | 无差异（参数未使用） |
| diagnose | ~15% | guidance 字段 |
| ask_about | ~10-20% | guidance 通过 banned_terms 影响 LLM |
| codegen | ~5-10% | 变更摘要措辞 |
| **平均** | **~10-15%** | |

**结论**：当前系统的角色切换主要影响 **文案和措辞**，而非 **输出结构或重点**。这对开发者和管理层的差异还可以接受，但对行业专家完全不够——他们需要的是 **完全不同的代码解读视角**。

---

## 三、新角色系统 v0.3 设计

### 3.1 三核心视图的行为定义

#### 视图 1：dev（开发者）

**目标用户**：全栈开发者、架构师、技术 TL

**核心诉求**：
- 精确定位：我要修复这个 bug，从哪个函数开始？
- 理解逻辑：这个模块的调用链是什么？有循环依赖吗？
- 性能评估：哪些函数频繁调用？内存泄漏的风险在哪？
- 边界测试：这个函数的参数范围是什么？有 null 检查吗？

**输出策略**（相比 PM，新增/强化）：
- scan_repo：
  - 增加 `critical_functions`: 列出高频调用或关键路径函数
  - 增加 `complexity_metrics`: 圈复杂度、参数数量等
  - Mermaid 图默认显示全部细节（PM 版本应简化）
- read_chapter：
  - 默认展示所有函数签名（含参数类型、返回类型）
  - 关键函数标注 `@critical` 标记
  - 显示调用这个函数的上游函数列表
  - 边界条件的代码片段（if/else/try-catch）
- diagnose：
  - 增加 `code_snippet` 字段：完整的函数实现（截取关键部分）
  - `exact_locations` 包含全部匹配的函数/类，不做筛选
  - guidance 文本强调代码细节和实现细节
- ask_about：
  - 上下文中优先包含源代码而非文档
  - guidance 文本可以使用所有技术术语（无 banned_terms）
  - 支持追问函数签名、异常处理等技术细节
- codegen：
  - unified_diff 的行号精确到原始行数
  - 增加 `edge_cases` 段落：修改涉及的边界情况

**guidance 示例**：
```
你是 CodeBook 的 AI 助手，正在帮助开发者理解代码。
提供精确的代码定位、调用栈分析和实现细节。
关键信息：函数签名、参数类型、返回值、异常处理、循环依赖、性能瓶颈。
可以使用所有技术术语（AST、序列化、中间件、幂等性等）。
```

#### 视图 2：pm（产品经理）

**目标用户**：产品经理、项目经理、管理层、非技术决策者

**核心诉求**：
- 功能概览：这个模块完成度怎样？还有多少工作量？
- 影响评估：改这里会影响其他哪些功能？
- 风险识别：有什么隐藏的复杂度我应该知道？
- 优先级：应该先改哪个？

**输出策略**（相比 dev，简化/转换）：
- scan_repo：
  - `role_badge` 和 `project_overview` 以"功能完整性"为中心
  - `modules` 中每个模块增加 `completion_hint`：如 "核心功能完成，待优化"
  - Mermaid 图简化到模块级（隐藏函数级细节）
  - 增加 `risk_areas`：列出最容易出问题的地方
- read_chapter：
  - 按文件组织，每个文件显示"做什么"而非"怎么做"
  - 隐藏函数签名细节，只显示功能名和 docstring
  - 强调"这个模块暴露给其他模块的接口"而非内部实现
- diagnose：
  - `matched_modules` 优先级：按影响范围排序
  - guidance 文本强调"这个问题会影响用户体验吗"
  - `blast_radius` 重点强调（对 PM 最重要的输出）
- ask_about：
  - 上下文中优先包含模块 L2 概览而非源代码
  - guidance 文本禁用技术术语（banned_terms）
  - 支持追问"完成度"、"工作量估算"等管理类问题
- codegen：
  - `change_summary` 用业务语言描述（"新增支付重试逻辑" vs "添加 retry_count 参数"）
  - `blast_radius` 中明确说明对用户的影响

**guidance 示例**：
```
你是 CodeBook 的 AI 助手，正在帮助产品经理理解代码变更的业务影响。
关键信息：功能完整性、用户体验影响、工作量估算、依赖关系。
禁止在主回答中使用以下术语：幂等、slug、冷启动、连接池、中间件、序列化、回调。
用业务语言描述问题。
```

#### 视图 3：domain_expert（行业专家）

**目标用户**：金融合规官、医疗数据官、电商风控专家、法律顾问

**核心诉求**：
- 业务规则验证：代码是否按照行业标准实现了规则 X？
- 风险识别：这个流程缺少合规检查吗？
- 术语准确性：代码中的"交易"是否对应我们的定义？
- 审计记录：这个操作是否记录了操作日志？

**输出策略**（全新视角，融合技术和业务）：
- scan_repo：
  - 新增 `domain_analysis` 段落：检测项目中涉及的业务规则
  - 如识别到 "payment" 相关代码，自动列出"涉及支付的模块有 X 个"
  - 如识别到 "audit" 日志，列出"已有审计记录的操作"
  - Mermaid 图按业务流程着色（而非技术拓扑）
- read_chapter：
  - 新增 `domain_rules` 段落：这个模块涉及的业务规则清单
  - 关键函数标注是否包含合规检查（如 KYC、AML）
  - 参数映射到业务概念（如 `user_id` → "持卡人身份")
- diagnose：
  - 支持用业务术语检索（如 "反洗钱" 而非 "aml"）
  - `matched_nodes` 中标注"这是否涉及风险操作"
  - guidance 文本强调"这个问题对合规性的影响"
  - 新增 `compliance_impact` 字段：列出相关的合规检查项
- ask_about：
  - 上下文注入该行业的术语表（通过 project_domain 参数）
  - 支持追问"这里是否满足 X 法规"
  - guidance 文本包含行业特定的检查清单
- codegen：
  - `change_summary` 用行业术语描述
  - 新增 `compliance_checklist` 段落：修改后需要检查的合规项
  - blast_radius 强调对数据安全/隐私的影响

**guidance 示例（金融领域）**：
```
你是 CodeBook 的 AI 助手，正在帮助金融合规官审查代码。
项目领域：金融科技。应当使用以下术语：
  - KYC = 客户身份验证
  - AML = 反洗钱检查
  - settlement = 资金结算
  - 幂等性 = 重复操作不产生副作用（关键）
关键检查项：交易金额限制、审计日志、加密存储、访问控制。
```

### 3.2 Per-Tool 字段级输出差异

#### scan_repo 输出（三视图对比）

| 字段 | dev | pm | domain_expert |
|------|-----|----|----|
| modules[i].name | ✓ | ✓ | ✓ |
| modules[i].node_body | 详细：主要函数列表、圈复杂度 | 简化：功能描述、完成度 | 业务术语：涉及的规则、敏感操作 |
| modules[i].source_refs | 全部高频函数 | 仅关键入口点 | 包含合规检查点 |
| **新增** critical_functions | ✓（dev 特有） | ✗ | ✗ |
| **新增** domain_analysis | ✗ | ✗ | ✓（domain_expert 特有） |
| mermaid_diagram | 函数级细节 | 模块级简化 | 按业务流程着色 |
| project_overview | 技术栈细节 | 功能完整性 | 业务规则覆盖 |

#### diagnose 输出（三视图对比）

| 字段 | dev | pm | domain_expert |
|------|-----|----|----|
| keywords | ✓（自 query） | ✓ | ✓（支持业务术语） |
| matched_nodes | 全量（不筛选） | 按影响范围排序 | 按合规风险排序 |
| exact_locations | 含完整代码片段 | 简化位置 | 标注合规相关性 |
| call_chain | 完整详细 | 简化为关键路径 | 按业务步骤标注 |
| **新增** compliance_impact | ✗ | ✗ | ✓（domain_expert 特有） |
| guidance | 强调代码细节 | 强调影响范围 | 强调规则符合性 |

#### ask_about 上下文组装优先级

**dev**（优先级递减）：
1. 源代码（完整函数体）
2. 调用链上游 1 跳的函数定义
3. 该模块的依赖 mock/stub（便于理解）
4. 同类函数的实现示例
5. 上游 2 跳模块摘要

**pm**（优先级递减）：
1. L2 模块概览（what）
2. 该模块的入口函数清单
3. 已有诊断结果摘要
4. 上下游依赖关系
5. 工作量/完成度指标

**domain_expert**（优先级递减）：
1. 项目领域的术语表注入
2. L3 模块卡片中的 domain_rules
3. 涉及敏感操作的代码片段（如支付、认证、访问控制）
4. 已有的审计/合规检查日志
5. 上下游的敏感模块

---

## 四、project_domain 推断机制（解答 D-004）

### 4.1 三层推断策略

当用户在 scan_repo 调用中未显式指定 `project_domain` 时，系统按以下优先级自动推断：

#### 层级 1：显式参数（最高优先级）

```python
scan_repo(
    repo_url="https://github.com/example/fintech-app",
    role="domain_expert",
    project_domain="fintech"  # ← 显式指定，直接使用
)
```

#### 层级 2：自动推断（README + 依赖包）

```python
def infer_domain_from_repo(clone_result: CloneResult, parse_results: list[ParseResult]) -> str | None:
    """尝试从 README 和依赖推断领域。"""

    # 2.1: 检查 README.md 关键词
    readme_keywords = {
        "fintech": ["金融", "支付", "交易", "钱包", "银行", "stripe", "paypal"],
        "healthcare": ["医疗", "诊断", "患者", "处方", "hl7", "fhir"],
        "ecommerce": ["电商", "购物车", "订单", "物流", "shopify", "magento"],
        "saas": ["软件即服务", "租户", "订阅", "多租户"],
    }

    readme_path = find_file(clone_result.files, "README.md")
    if readme_path:
        content = read_file(readme_path)
        for domain, keywords in readme_keywords.items():
            if any(kw in content for kw in keywords):
                return domain

    # 2.2: 检查依赖包名
    dependency_markers = {
        "fintech": ["stripe", "braintree", "square", "wise", "alipay"],
        "healthcare": ["fhir", "hl7", "dicom"],
        "ecommerce": ["shopify", "woocommerce", "bigcommerce"],
    }

    # 从 package.json / requirements.txt / go.mod 提取依赖
    deps = extract_dependencies(clone_result.files, parse_results)
    for domain, markers in dependency_markers.items():
        if any(marker in deps for marker in markers):
            return domain

    return None
```

**推断结果示例**：

| 项目 | README 关键词 | 依赖包 | 推断结果 |
|------|-------------|-------|---------|
| stripe-python | "支付处理"、"Stripe API" | stripe | `fintech` |
| fhir-py | "FHIR 标准" | fhir | `healthcare` |
| shopify-python | "电商"、"订单管理" | shopify | `ecommerce` |

#### 层级 3：术语库备用（最低优先级）

如果层级 1、2 都未找到，但 project_memory 已有该项目的术语库记录：

```python
# ~/.codebook/memory/{repo_hash}/meta.json 中可能已有：
{
    "project_domain": "fintech"  # 从上次扫描记忆的
}
```

使用已记录的 domain。

### 4.2 推断规则表

| 关键词/包名 | 推断领域 | 可信度 | 备注 |
|----------|--------|-------|------|
| "金融"、"支付"、"交易" | fintech | 0.9 | 中文常见表述 |
| stripe、paypal、square | fintech | 0.95 | 行业标志性依赖 |
| "医疗"、"患者"、"诊断" | healthcare | 0.85 | 中文医疗术语 |
| fhir、hl7、dicom | healthcare | 0.98 | 医疗标准包 |
| "电商"、"购物车"、"订单" | ecommerce | 0.80 | 中文电商术语 |
| shopify、woocommerce | ecommerce | 0.95 | 电商平台官方包 |
| "SaaS"、"多租户"、"订阅" | saas | 0.75 | SaaS 特征词 |

### 4.3 与术语飞轮的关系

一旦推断或设定了 `project_domain`，系统的 `TermResolver` 会加载对应行业术语包：

```python
# 在 ask_about / diagnose / read_chapter 中

def get_terminology(project_domain: str) -> TermSet:
    """获取项目的术语表。"""

    # 优先级 1: 项目级术语库（用户纠正记录）
    project_glossary = load_project_glossary(repo_hash)
    if project_domain in project_glossary:
        return project_glossary[project_domain]

    # 优先级 2: 行业术语包（预装）
    domain_pack = load_domain_pack(project_domain)
    if domain_pack:
        return domain_pack.terms

    # 优先级 3: 全局默认词表
    return load_global_default_terms()
```

**关键设计**：project_domain 是术语飞轮的激活开关。同一个术语 "transaction" 在：
- fintech 项目：翻译为 "交易"
- healthcare 项目：翻译为 "处理" 或不翻译
- ecommerce 项目：翻译为 "订单交易"

---

## 五、向后兼容性映射表

### 5.1 旧角色 → 新视图映射

对外接口保持 JSON 兼容，但内部路由到新视图：

| 旧角色 | 新视图 | 映射逻辑 |
|--------|--------|---------|
| `ceo` | `pm` | CEO 关注商业，映射到 PM 的商业影响视角 |
| `pm` | `pm` | 直接对应 |
| `investor` | `pm` | 投资人关注可扩展性，映射到 PM 的风险识别 |
| `qa` | `dev` | QA 关注边界条件，映射到 dev 的精确定位视角 |
| **新增** `domain_expert` | `domain_expert` | 新增，需要显式传 project_domain |

### 5.2 迁移策略

**Phase 1：兼容期（v0.3.0 - 0.3.x）**

所有旧角色名继续可用，MCP 宿主收到：
```python
{
    "status": "ok",
    "role": "ceo",  # 原始角色名返回
    "_mapped_to_view": "pm",  # 新增字段，标注映射信息
    ...
}
```

**Phase 2：弃用期（v0.4+）**

在 guidance 中加入弃用警告：
```
{
    "status": "ok",
    "role": "ceo",
    "deprecation_warning": "角色 'ceo' 已弃用，请改用 'pm' 或新增的 'domain_expert'",
    ...
}
```

---

## 六、集成点与实施路线图

### 6.1 与 TermResolver 的集成

TermResolver（术语飞轮系统）在以下时刻被调用：

| 工具 | 调用点 | 用途 |
|------|--------|------|
| scan_repo | `_build_project_overview()` | 将内部术语翻译为用户术语 |
| read_chapter | `generate_local_chapter()` | 为 PM 视角生成无技术术语的卡片 |
| diagnose | `_build_guidance()` | 注入角色+领域相关的术语列表 |
| ask_about | `assemble_context()` + `_build_system_prompt()` | 注入禁用术语 + 推荐术语 |
| codegen | `codegen_engine.execute()` | 生成业务语言的变更摘要 |

### 6.2 文件改动清单

#### 新增文件

| 文件 | 内容 | 优先级 |
|------|------|--------|
| `src/roles/core.py` | 三视图的核心定义（RoleView dataclass，三个 view 类） | P0 |
| `src/roles/domain_detector.py` | 领域自动推断逻辑（infer_domain_from_repo） | P0 |
| `src/roles/dev_view.py` | dev 视图的输出生成逻辑 | P0 |
| `src/roles/pm_view.py` | pm 视图的输出生成逻辑（可复用现有逻辑） | P0 |
| `src/roles/domain_expert_view.py` | domain_expert 视图的输出生成逻辑 | P0 |

#### 修改文件

| 文件 | 改动 | 优先级 |
|------|------|--------|
| `src/tools/scan_repo.py` | 1. 添加 `project_domain` 参数（可选）<br>2. 调用 `domain_detector.infer_domain_from_repo()`<br>3. 将输出交由角色视图处理 | P0 |
| `src/tools/read_chapter.py` | 1. 调用角色视图的 read_chapter 生成器<br>2. 保持 JSON 输出格式兼容 | P0 |
| `src/tools/diagnose.py` | 1. 整合 ROLE_GUIDANCE 到角色视图<br>2. 三视图分别生成 guidance + compliance_impact | P0 |
| `src/tools/ask_about.py` | 1. 整合 ROLE_CONFIG 到角色视图<br>2. guidance 生成中加入 project_domain 相关术语 | P0 |
| `src/tools/codegen.py` | 1. 将角色视图传给 codegen_engine<br>2. 三视图分别生成 change_summary | P0 |
| `src/summarizer/engine.py` | 1. 接受 role_view 参数<br>2. 调用 TermResolver 进行术语翻译 | P0 |
| `INTERFACES.md` | 更新 §3 角色系统接口定义 | P0 |

#### 修改 server.py（如需要）

```python
# 注册新参数（如果 project_domain 作为全局参数）
@mcp.tool()
async def scan_repo(
    repo_url: str,
    role: str = "pm",
    depth: str = "overview",
    project_domain: str | None = None,  # 新增
) -> dict:
    ...
```

### 6.3 实施路线图

**Phase 1：角色系统重构（1 周）**

| 日 | 任务 | 产出 |
|----|------|------|
| D1 | 实现 `src/roles/core.py` 和三个 view 类 | 角色视图基础设施 |
| D2 | 实现 `domain_detector.py` 领域推断逻辑 | 自动推断能力 |
| D3 | 修改 scan_repo.py 集成角色系统 | scan_repo 支持三视图 |
| D4 | 修改 read_chapter.py 和 diagnose.py | 两个工具支持三视图 |
| D5 | 修改 ask_about.py 和 codegen.py | 五个工具全部就绪 |
| D6-D7 | 集成测试 + 文档更新 | 验收 |

**Phase 2：术语飞轮与项目记忆集成（2 周，并行可做）**

与 D-1b / D-1c 流程同步（见 self_evolution_design.md）

**验收标准**：
- 所有 5 个工具支持三视图 + 自动领域推断
- INTERFACES.md 和 TASK_PROMPTS.md 同步更新
- 单测覆盖 > 90%，全量 pytest 通过
- 人工验证：FastAPI 项目用 dev/pm/domain_expert 三视角分别扫描，输出结构正确，差异化明显

---

## 七、设计决策追踪

### D-004：domain_expert 的 project_domain 如何传入？

**决策**：三层策略

```
优先级 1: scan_repo(project_domain="fintech")      [显式参数]
       ↓ （未指定）
优先级 2: README.md "金融支付" + stripe 依赖       [自动推断]
       ↓ （推断失败）
优先级 3: ~/.codebook/memory/{hash}/meta.json      [术语库记忆]
       ↓ （无记录）
默认值: None                                        [不加载行业包]
```

**理由**：
1. 用户优先：显式参数覆盖一切（用户最清楚自己项目的业务）
2. 自动兜底：大多数项目 README 和依赖包能清晰表达领域
3. 记忆持久：重复扫描同一项目时利用上次推断
4. 优雅降级：无法推断时系统仍可用（domain_expert 功能退化为 pm）

### D-005：术语存储格式？

**决策**：JSON 格式，存 `~/.codebook/memory/{repo_hash}/glossary.json`

结构：
```json
{
  "version": 1,
  "repo_url": "...",
  "project_domain": "fintech",
  "terms": [
    {
      "source_term": "transaction",
      "target_phrase": "交易",
      "context": "支付流程中",
      "domain": "fintech",
      "source": "user_correction",
      "confidence": 1.0,
      "usage_count": 12,
      "created_at": "2026-03-23T...",
      "updated_at": "2026-03-23T..."
    }
  ]
}
```

**理由**：
1. JSON 易于版本控制和迁移
2. 字段完整：支持追踪来源、置信度、使用频率
3. 与 ProjectMemory 一致：存储位置统一，便于备份和同步

---

## 八、质量指标与验收

### 8.1 功能验收标准

| 指标 | 目标 | 验收方式 |
|------|------|---------|
| 三视图 JSON 格式兼容 | 100% | 结构化对比（INTERFACES.md） |
| domain_expert 推断精度 | ≥80% | 5 个项目手工验证 |
| 向后兼容性 | 100% | 旧脚本无修改可继续运行 |
| 输出差异化程度 | ≥40%（相比 v0.2 的 10-15%） | 定性评估 3 个项目 3 个视角 |

### 8.2 编码质量指标

| 指标 | 目标 |
|------|------|
| pytest 通过率 | ≥99%（全量测试） |
| 单测覆盖率 | ≥90%（新增代码） |
| 代码重复率 | ≤15%（三个 view 类可共享通用逻辑） |
| 文档完整性 | §1-6 设计覆盖所有改动点 |

### 8.3 人工验收流程

用 FastAPI 项目（已 clone）测试：

**步骤 1：dev 视角**
```bash
scan_repo(
    repo_url="mcp-server/repos/fastapi",
    role="dev"
)
```
验证：
- [ ] critical_functions 列表正确
- [ ] call_chain 包含完整细节
- [ ] guidance 强调代码细节
- [ ] mermaid 图显示函数级

**步骤 2：pm 视角**
```bash
scan_repo(
    repo_url="mcp-server/repos/fastapi",
    role="pm"
)
```
验证：
- [ ] project_overview 强调"功能完整性"
- [ ] role_badge = "PM 视角..."
- [ ] risk_areas 列表有意义
- [ ] mermaid 图简化为模块级

**步骤 3：domain_expert 视角**
```bash
scan_repo(
    repo_url="mcp-server/repos/fastapi",
    role="domain_expert"
    # project_domain 不指定，让系统推断
)
```
验证：
- [ ] domain_analysis 正确识别为 "web_framework" 或 "general"
- [ ] 无运行时错误（domain_expert 需要显式 project_domain 时应返回有用错误）

**步骤 4：兼容性验证**
```bash
scan_repo(
    repo_url="mcp-server/repos/fastapi",
    role="ceo"  # 旧角色
)
```
验证：
- [ ] 仍可运行
- [ ] 返回 "_mapped_to_view": "pm"
- [ ] 输出内容与 pm 视角一致

---

## 九、实施中的注意事项

### 9.1 关键路径依赖

1. **优先完成 core.py**：三个视图类的基础设施，其他所有改动都依赖它
2. **domain_detector 需测试**：推断精度直接影响 domain_expert 质量，需充分测试
3. **TermResolver 必须就绪**：domain_expert 的术语加载依赖术语飞轮（D-1b）

### 9.2 风险与缓解

| 风险 | 影响 | 缓解策略 |
|------|------|---------|
| 角色视图类膨胀（每个工具 × 3 视角） | 代码维护成本高 | 抽取共同逻辑到 base class，视图类只实现差异部分 |
| domain_expert 推断失败时系统降级 | 用户期望落差 | 返回明确的 "domain_unknown" 状态，建议用户显式指定 |
| 向后兼容映射的歧义 | 旧脚本行为突变 | 在 deprecation_warning 中明确说明映射规则 |
| 术语表碰撞（多领域术语冲突） | 翻译不准 | TermResolver 按优先级严格合并，冲突时用户纠正优先 |

### 9.3 测试策略

#### 单元测试

```python
# tests/test_roles_core.py
def test_dev_view_generates_critical_functions():
    view = DevView(...)
    output = view.scan_repo_output(...)
    assert "critical_functions" in output
    assert len(output["critical_functions"]) > 0

# tests/test_domain_detector.py
def test_infer_domain_fintech_from_keywords():
    result = detect_domain_from_readme("支付处理平台")
    assert result == "fintech"

def test_infer_domain_from_dependency():
    deps = ["stripe", "requests"]
    result = detect_domain_from_deps(deps)
    assert result == "fintech"

# tests/test_role_compatibility.py
def test_ceo_maps_to_pm():
    output_ceo = scan_repo(..., role="ceo")
    output_pm = scan_repo(..., role="pm")
    assert output_ceo["_mapped_to_view"] == "pm"
    # 内容应该相同（除了 role 字段）
```

#### 集成测试

```python
# tests/test_role_integration.py
def test_three_views_all_produce_output():
    for role in ["dev", "pm", "domain_expert"]:
        output = scan_repo(..., role=role)
        assert output["status"] == "ok"
        assert output["role"] == role

def test_domain_expert_with_explicit_domain():
    output = scan_repo(
        ...,
        role="domain_expert",
        project_domain="fintech"
    )
    assert "domain_analysis" in output
    # 应该加载 fintech 术语表
```

---

## 十、附录：三视图的完整对照表

### scan_repo 输出字段完全对照

| 字段 | 数据类型 | dev | pm | domain_expert |
|------|---------|-----|----|----|
| status | str | ✓ | ✓ | ✓ |
| repo_url | str | ✓ | ✓ | ✓ |
| role | str | ✓ | ✓ | ✓ |
| depth | str | ✓ | ✓ | ✓ |
| project_overview | str | 技术栈+性能 | 功能完整性 | 业务规则覆盖 |
| modules[].name | str | ✓ | ✓ | ✓ |
| modules[].node_title | str | ✓ | ✓ | ✓ |
| modules[].node_body | str | 函数清单+复杂度 | 功能描述+完成度 | 规则清单+敏感操作 |
| modules[].health | str | 基于圈复杂度 | 基于完成度 | 基于合规检查 |
| modules[].role_badge | str | "Dev 视角：..." | "PM 视角：..." | "Domain Expert 视角：..." |
| **新增** modules[].critical_functions | list[str] | ✓ 填充 | ✗ 空列表 | ✗ 空列表 |
| **新增** modules[].compliance_markers | list[str] | ✗ | ✗ | ✓ 填充 |
| mermaid_diagram | str | 函数级详细 | 模块级简化 | 业务流程着色 |
| **新增** domain_analysis | str | ✗ | ✗ | ✓ 填充 |
| stats | dict | ✓ | ✓ | ✓ |

---

## 十一、总结与后续

本设计方案通过引入**三核心视图 + 动态领域适配**，将 CodeBook 的角色系统从"措辞替换"升级为"真正的多视角翻译"。

**核心改进**：
1. ✓ 覆盖四类用户群（dev/pm/domain_expert + qa→dev）
2. ✓ 输出差异化从 10-15% 提升到 40% 以上
3. ✓ domain_expert 通过 project_domain 参数激活行业特定功能
4. ✓ 与术语飞轮深度集成，越用越精准
5. ✓ 完全向后兼容，旧脚本无改动继续可用

**后续工作**：
- Phase 2：术语飞轮 MVP（TermResolver + term_correct tool）
- Phase 3：项目记忆与增量扫描
- Phase 4：跨项目模式识别和团队知识图谱
