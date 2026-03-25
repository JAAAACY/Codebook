# codebook_config Changelog: v0.1 → v0.2

> 驱动来源：quality_eval_v2.md 中识别的 10 个「看不懂」问题 + 5 条优化建议
> 日期：2026-03-21

---

## 一、结构性新增

| 新增内容 | 说明 | 解决的评估问题 |
|----------|------|----------------|
| `capabilities.blueprint` | 新增蓝图能力定义（v0.1 只有 understand/locate/codegen 三个能力） | 评估 v1 发现蓝图缺失是最大结构性缺陷 |
| `output_formats.blueprint` | 新增蓝图输出格式 schema（project_summary + module_overview + global_dependency_graph） | 定义蓝图的标准化输出结构 |
| `output_formats.locate_result` | 新增定位结果的独立 schema（v0.1 只在 prompt 文本中描述，没有结构化定义） | 标准化 matched_modules → call_chain → exact_locations → diagnosis 四段式结构 |
| `prompts.blueprint_system` | 新增蓝图 system prompt | 蓝图能力的核心生成指令 |
| `prompts.blueprint_prompt` | 新增蓝图 user prompt 模板 | 蓝图能力的结构化输出模板 |
| `banned_terms_in_pm_fields` | 新增术语禁用表（11 个术语 + 替换方案） | 评估问题 #1-#6：蓝图 pm_note 技术词汇密度偏高 |
| `http_status_code_annotations` | 新增状态码中文注释对照表（10 个常见状态码） | 评估问题 #7-#8、#10：400/403/201 从未解释 |

---

## 二、Prompt 规则修正（逐条对应评估问题）

### 评估问题 #1：`asyncpg 连接池上限为 10` → PM 不懂

**修正位置**：`blueprint_system` 规则 4 + `banned_terms_in_pm_fields`

```
新增规则：「连接池」→「同时处理请求的上限」
新增规则：其他编程专有名词一律翻译为业务含义
```

### 评估问题 #2：`幂等设计` → PM 不懂

**修正位置**：`blueprint_system` 规则 4 + `banned_terms_in_pm_fields`

```
新增规则：「幂等」→ 描述重复操作的实际后果（如「重复点击会报错」）
```

### 评估问题 #3：`冷启动兜底` → PM 大概能猜但不确定

**修正位置**：`blueprint_system` 规则 4 + `banned_terms_in_pm_fields`

```
新增规则：「冷启动」→ 描述具体缺失场景（如「新用户没有关注任何人时首页为空」）
```

### 评估问题 #4：`Depends(get_repository(...))` → 纯代码

**修正位置**：`blueprint_system` 规则 3

```
v0.1: 无此规则
v0.2: entry_points 必须用业务描述，禁止出现代码表达式如 Depends(...)、get_xxx() 等
```

### 评估问题 #5：`slug` → PM 不知道是什么

**修正位置**：`blueprint_system` 规则 4 + `banned_terms_in_pm_fields`

```
新增规则：「slug」→「URL 中的文章标识」
```

### 评估问题 #6：`docs/openapi 暴露面` → PM 不懂

**修正位置**：`blueprint_system` 规则 4 + `banned_terms_in_pm_fields`

```
新增规则：「openapi / swagger」→「API 调试页面」
新增规则：「env_file / .env」→「配置文件」
```

### 评估问题 #7：`403` 和 `MALFORMED_PAYLOAD` → PM 不懂

**修正位置**：`understand_system` 规则 4 + 规则 5

```
v0.1: 仅有「技术概念首次出现时用一句话解释其业务含义」（太笼统）
v0.2:
  规则 4：HTTP 状态码必须加括号注释（附完整对照表）
  规则 5：错误常量名必须加括号中文解释（如 MALFORMED_PAYLOAD（令牌数据损坏））
```

### 评估问题 #8：`返回 400` 多次出现但从未解释

**修正位置**：`understand_system` 规则 4 + `http_status_code_annotations`

```
v0.1: 无状态码注释规则
v0.2: 新增全局状态码注释对照表，所有面向 PM 输出中首次出现必须加注
```

### 评估问题 #9：`confidence: 0.99` → PM 不需要数值

**修正位置**：`locate_system` + `output_formats.locate_result`

```
v0.1: 无 confidence 字段定义（prompt 中未提及）
v0.2: 明确要求使用 certainty 字段 + 中文自然语言（「非常确定 / 很确定 / 有一定把握」，不要用数值如 0.99）
```

### 评估问题 #10：`返回 201` → PM 不知道是什么

**修正位置**：`codegen_system` 规则 6 + `http_status_code_annotations`

```
v0.1: 无
v0.2: verification_steps 中出现 HTTP 状态码时必须加中文括号注释：如 201（创建成功）、400（请求有误）
```

---

## 三、其他优化建议的落实

### 建议 5：diff 段落缺少「可跳过」引导

**修正位置**：`codegen_system` 规则 2 + `output_formats.code_diff.schema.unified_diff`

```
v0.1: 无引导语
v0.2: unified_diff 上方必须加引导语：「以下是给程序员看的具体代码改动。如果你只关心业务变化，看上面的 change_summary 就够了。」
```

### 追加优化：codegen 变更最小化

**修正位置**：`codegen_system` 规则 7

```
v0.1: 无
v0.2: 变更要最小化：只改必要的文件，不要引入不必要的结构改动。
```
原因：v1 评估中编写文档得分最低（7.5/10），因为引入了不必要的 HTTPException 结构改动。

### 追加优化：自检清单

**修正位置**：`understand_prompt` 和 `codegen_prompt` 末尾

```
v0.1: 无
v0.2: 每个 prompt 模板末尾增加「检查清单（输出前自检）」，列出 4-5 条必须通过的检查项。
```

---

## 四、v0.1 → v0.2 对照总表

| 维度 | v0.1 | v0.2 |
|------|------|------|
| 能力数量 | 3（understand/locate/codegen） | **4**（+ blueprint） |
| output_formats 数量 | 3（module_card/call_chain/code_diff） | **5**（+ blueprint + locate_result） |
| prompt 数量 | 6（3 对 system+prompt） | **8**（4 对 system+prompt） |
| 术语管控 | 1 条笼统规则 | 禁用术语表（11 个）+ 状态码对照表（10 个） |
| 自检机制 | 无 | understand_prompt 和 codegen_prompt 末尾各有自检清单 |
| pm_note 约束 | 「PM 最需要知道的一件事」 | + 「必须用纯业务语言，禁止技术术语」 |
| certainty 字段 | 无定义 | 明确要求中文自然语言，禁止数值 |
| diff 引导语 | 无 | 强制要求加「可跳过」引导语 |
| 变更最小化 | 无 | 明确要求只改必要文件 |
