"""
CodeBook Codegen — 自然语言代码生成 Prompt 构建器

将「用户自然语言指令 + locate 定位结果」组装为完整的 LLM prompt，
并解析 LLM 输出为结构化的变更方案。

用法:
    builder = CodegenPromptBuilder()
    messages = builder.build(
        user_instruction="把注册时的报错文案改成中文友好提示",
        locate_result=locate_result,
        current_code={"app/resources/strings.py": "..."},
    )
    # messages → 可直接传给 LLM API 的 messages 列表

    parser = CodegenOutputParser()
    result = parser.parse(llm_response_text)
    # result → CodegenResult 结构化对象
"""

from __future__ import annotations

import json
import re
import textwrap
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ───────────────────────────────────────────
# 数据模型
# ───────────────────────────────────────────

@dataclass
class ExactLocation:
    """Locate 阶段输出的单个精确定位点。"""
    file: str
    line: int
    why_it_matters: str
    certainty: str  # "非常确定" | "很确定" | "有一定把握"


@dataclass
class LocateResult:
    """Locate 阶段的完整输出。"""
    matched_modules: str          # Markdown 格式的相关模块列表
    call_chain_mermaid: str       # Mermaid graph TD 代码
    exact_locations: list[ExactLocation]
    diagnosis: str                # 业务语言诊断结论


@dataclass
class ChangeSummaryItem:
    """变更摘要中的一项（一个文件的业务语言变更说明）。"""
    file: str
    line_range: str
    before: str  # 改之前做什么（业务语言）
    after: str   # 改之后做什么（业务语言）


@dataclass
class DiffBlock:
    """单个文件的 unified diff 代码块。"""
    file: str
    title: str           # 变更标题（业务语言）
    diff_content: str    # unified diff 文本
    before_desc: str     # 改之前一句话
    after_desc: str      # 改之后一句话


class ActionRequired(Enum):
    MUST = "需要"
    SUGGEST = "建议"
    INFO_ONLY = "仅需知晓"


@dataclass
class BlastRadiusItem:
    """影响范围中的一项。"""
    file_or_module: str
    impact: str               # 业务语言的影响描述
    action_required: ActionRequired


@dataclass
class VerificationStep:
    """验证步骤中的一项。"""
    step: str               # 用户做什么操作
    expected_result: str    # 预期看到什么


@dataclass
class CodegenResult:
    """Codegen 引擎的完整输出。"""
    change_summary: list[ChangeSummaryItem]
    diff_blocks: list[DiffBlock]
    blast_radius: list[BlastRadiusItem]
    verification_steps: list[VerificationStep]
    raw_text: str = ""  # 原始 LLM 输出文本


# ───────────────────────────────────────────
# System Prompt
# ───────────────────────────────────────────

CODEGEN_SYSTEM_PROMPT = textwrap.dedent("""\
你是 CodeBook 的代码生成引擎。

你的用户是不会写代码的产品经理、创业者、设计师。他们用自然语言描述想要的修改，\
你负责生成精确的代码变更，并用他们能看懂的语言解释这些变更。

## 你的任务

1. 读懂用户的自然语言指令
2. 基于 locate 阶段定位到的代码位置，生成最小化的精确代码变更
3. 用业务语言解释每个变更「改了什么、为什么改、改完会怎样」
4. 列出所有受影响的文件和模块
5. 给出用户可以亲自验证改动的操作步骤

## 核心规则

### 规则 1：变更最小化
只改必要的代码。如果只需要改一行文案，就只改那一行。\
不要为了「更好的结构」引入额外改动。\
每个变更必须直接服务于用户指令。\
如果你认为有额外的改进机会，放在影响范围中作为「建议」提出，不要直接改。

### 规则 2：Diff 必须精确可应用
- 使用标准 unified diff 格式
- 行号必须与当前代码中的实际行号一致
- 上下文行（不变的行）至少保留 3 行
- diff 必须可以直接通过 `git apply` 或 `patch -p1` 应用
- 如果同一个文件有多处修改，合并为一个 diff block，用 @@ 分隔不同的 hunk

### 规则 3：双轨输出——业务语言 + 代码
每个变更同时提供两种描述：
- **变更摘要**（给 PM 看）：纯业务语言，禁止出现代码术语
- **代码变更**（给程序员看）：精确 unified diff

在代码变更上方始终加引导语：
> 以下是给程序员看的具体代码改动。如果你只关心业务变化，看上面的变更摘要就够了。

### 规则 4：影响范围必须具体
影响范围中的每一项必须包含：
- 具体的文件路径或模块名
- 用业务语言解释为什么会被影响
- 明确是否需要同步修改（需要 / 建议 / 仅需知晓）

### 规则 5：验证步骤必须是用户操作
验证步骤必须用用户能实际执行的操作来写：
- 主语是「用户」或具体角色
- 描述具体的页面操作（点击、输入、提交）
- 预期结果必须是用户可观察到的
- HTTP 状态码出现时必须加中文括号注释：如 400（请求有误）、201（创建成功）

### 规则 6：术语管控
在变更摘要、影响范围、验证步骤中：
- 禁止出现编程术语（函数名、变量名、类名、设计模式名）
- 技术概念必须翻译为业务含义
- 状态码必须附中文注释

在代码变更的 diff 中：
- 可以使用任何技术语言（这部分本来就是给程序员看的）

## 输出格式

严格按照以下 Markdown 结构输出，不要增减一级标题：

```
## 变更摘要
（表格）

## 代码变更
（引导语 + 每个变更的 diff block）

## 影响范围
（表格）

## 验证方式
（编号步骤列表）
```

## 自检清单

输出前逐条检查：
□ 变更摘要中每个文件都有「改之前 → 改之后」的业务描述？
□ 变更摘要中没有代码术语？
□ 代码变更上方有引导语？
□ diff 的行号与当前代码一致？
□ 影响范围中每项都有具体文件名 + 业务影响 + 是否需要同步修改？
□ 验证步骤是用户可执行的操作（不是运行测试命令）？
□ 验证步骤中的状态码都有中文注释？
□ 变更范围最小化（没有不必要的结构改动）？
□ 没有偏离用户原始指令的范围？
""")


# ───────────────────────────────────────────
# Prompt Builder
# ───────────────────────────────────────────

class CodegenPromptBuilder:
    """
    将用户指令 + locate 定位结果 + 当前代码组装为 LLM prompt messages。

    输出格式为 OpenAI/Anthropic 兼容的 messages 列表：
    [
        {"role": "system", "content": "..."},
        {"role": "user",   "content": "..."},
    ]
    """

    def __init__(
        self,
        system_prompt: str | None = None,
        max_file_lines: int = 500,
    ):
        """
        Args:
            system_prompt: 自定义 system prompt（默认使用内置版本）
            max_file_lines: 单个文件超过此行数时截取定位点周围的上下文
        """
        self.system_prompt = system_prompt or CODEGEN_SYSTEM_PROMPT
        self.max_file_lines = max_file_lines

    def build(
        self,
        user_instruction: str,
        locate_result: LocateResult,
        current_code: dict[str, str],
        module_cards: str | None = None,
        tech_stack: str | None = None,
        coding_conventions: str | None = None,
    ) -> list[dict[str, str]]:
        """
        构建完整的 messages 列表。

        Args:
            user_instruction: 用户的自然语言修改指令
            locate_result: Locate 阶段的结构化输出
            current_code: 文件路径 → 文件完整内容
            module_cards: 相关模块卡片（可选，Markdown）
            tech_stack: 技术栈信息（可选）
            coding_conventions: 编码规范（可选）

        Returns:
            messages 列表，可直接传给 LLM API
        """
        context_section = self._build_context(
            locate_result, current_code, module_cards, tech_stack, coding_conventions
        )
        user_section = self._build_user_prompt(user_instruction)

        return [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"{context_section}\n\n---\n\n{user_section}"},
        ]

    # ── 内部方法 ──

    def _build_context(
        self,
        locate_result: LocateResult,
        current_code: dict[str, str],
        module_cards: str | None,
        tech_stack: str | None,
        coding_conventions: str | None,
    ) -> str:
        parts: list[str] = []

        # ① locate 定位结果
        parts.append("## 定位结果\n")
        parts.append("以下是 locate 阶段的定位产物。\n")

        parts.append("### 相关模块\n")
        parts.append(locate_result.matched_modules)
        parts.append("")

        parts.append("### 调用链路图\n")
        parts.append(locate_result.call_chain_mermaid)
        parts.append("")

        parts.append("### 精确定位\n")
        parts.append("```json")
        locations_data = [
            {
                "file": loc.file,
                "line": loc.line,
                "why_it_matters": loc.why_it_matters,
                "certainty": loc.certainty,
            }
            for loc in locate_result.exact_locations
        ]
        parts.append(json.dumps(locations_data, ensure_ascii=False, indent=2))
        parts.append("```\n")

        parts.append("### 诊断结论\n")
        parts.append(locate_result.diagnosis)
        parts.append("")

        # ② 当前代码
        parts.append("## 当前代码\n")
        parts.append("以下是需要修改的源文件内容。你的 diff 必须基于这些内容生成。\n")

        for file_path, content in current_code.items():
            lang = self._detect_language(file_path)
            numbered = self._add_line_numbers(content, file_path, locate_result)
            parts.append(f"### `{file_path}`\n")
            parts.append(f"```{lang}")
            parts.append(numbered)
            parts.append("```\n")

        # ③ 可选上下文
        if module_cards:
            parts.append("## 模块卡片（参考信息）\n")
            parts.append(module_cards)
            parts.append("")

        if tech_stack:
            parts.append("## 技术栈\n")
            parts.append(tech_stack)
            parts.append("")

        if coding_conventions:
            parts.append("## 编码规范\n")
            parts.append(coding_conventions)
            parts.append("")

        return "\n".join(parts)

    def _build_user_prompt(self, user_instruction: str) -> str:
        return textwrap.dedent(f"""\
## 用户指令

{user_instruction}

---

请基于上面的定位结果和当前代码，生成代码变更方案。严格按照以下格式输出：

## 变更摘要

用表格列出每个被修改的文件：

| 文件 | 行号 | 改之前（当前做什么） | 改之后（变更做什么） |
|------|------|---------------------|---------------------|
| `file_path` | Lxx-Lyy | 业务语言描述 | 业务语言描述 |

---

## 代码变更

> 以下是给程序员看的具体代码改动。如果你只关心业务变化，看上面的变更摘要就够了。

### 变更 N：{{变更标题（业务语言）}}

**文件**：`{{file_path}}`

```diff
{{unified_diff}}
```

**改之前**：{{一句话业务描述}}
**改之后**：{{一句话业务描述}}

（对每个变更重复上述结构）

---

## 影响范围

| 受影响的模块/文件 | 影响说明 | 是否需要同步修改 |
|-------------------|----------|-----------------|
| **模块或文件名** | 业务语言的影响描述 | 需要 / 建议 / 仅需知晓 |

---

## 验证方式

验证这个改动生效的操作步骤：

1. **{{用户操作}}** → {{预期看到的结果}}
2. **{{用户操作}}** → {{预期看到的结果}}
""")

    def _add_line_numbers(
        self,
        content: str,
        file_path: str,
        locate_result: LocateResult,
    ) -> str:
        """为代码内容添加行号。文件过长时截取定位点周围的上下文。"""
        lines = content.splitlines()

        if len(lines) <= self.max_file_lines:
            return "\n".join(f"{i+1:4d} | {line}" for i, line in enumerate(lines))

        # 文件过长：提取定位点附近的行
        target_lines: set[int] = set()
        for loc in locate_result.exact_locations:
            if loc.file == file_path:
                # 定位点前后各取 context_radius 行
                context_radius = 30
                start = max(0, loc.line - context_radius)
                end = min(len(lines), loc.line + context_radius)
                target_lines.update(range(start, end))

        if not target_lines:
            # 没有定位点在这个文件：取前 max_file_lines 行
            return "\n".join(
                f"{i+1:4d} | {line}" for i, line in enumerate(lines[:self.max_file_lines])
            ) + f"\n... (文件共 {len(lines)} 行，已截取前 {self.max_file_lines} 行)"

        sorted_lines = sorted(target_lines)
        result_parts: list[str] = []
        prev = -2

        for line_idx in sorted_lines:
            if line_idx - prev > 1:
                result_parts.append(f"  ... (跳过 {line_idx - prev - 1} 行)")
            result_parts.append(f"{line_idx+1:4d} | {lines[line_idx]}")
            prev = line_idx

        if sorted_lines[-1] < len(lines) - 1:
            remaining = len(lines) - sorted_lines[-1] - 1
            result_parts.append(f"  ... (后续还有 {remaining} 行)")

        return "\n".join(result_parts)

    @staticmethod
    def _detect_language(file_path: str) -> str:
        """根据文件扩展名推断语言标识符。"""
        ext_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".tsx": "tsx",
            ".jsx": "jsx",
            ".java": "java",
            ".go": "go",
            ".rs": "rust",
            ".rb": "ruby",
            ".php": "php",
            ".html": "html",
            ".css": "css",
            ".sql": "sql",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".json": "json",
            ".toml": "toml",
            ".md": "markdown",
            ".sh": "bash",
        }
        for ext, lang in ext_map.items():
            if file_path.endswith(ext):
                return lang
        return ""


# ───────────────────────────────────────────
# Output Parser
# ───────────────────────────────────────────

class CodegenOutputParser:
    """
    解析 LLM 输出的 Markdown 文本为结构化的 CodegenResult。

    支持解析四个核心段落：
    - ## 变更摘要 → list[ChangeSummaryItem]
    - ## 代码变更 → list[DiffBlock]
    - ## 影响范围 → list[BlastRadiusItem]
    - ## 验证方式 → list[VerificationStep]
    """

    def parse(self, raw_text: str) -> CodegenResult:
        """
        解析完整的 LLM 输出文本。

        Args:
            raw_text: LLM 返回的 Markdown 格式文本

        Returns:
            CodegenResult 结构化对象
        """
        sections = self._split_sections(raw_text)

        return CodegenResult(
            change_summary=self._parse_change_summary(
                sections.get("变更摘要", sections.get("change_summary", ""))
            ),
            diff_blocks=self._parse_diff_blocks(
                sections.get("代码变更", sections.get("unified_diff", ""))
            ),
            blast_radius=self._parse_blast_radius(
                sections.get("影响范围", sections.get("blast_radius", ""))
            ),
            verification_steps=self._parse_verification_steps(
                sections.get("验证方式", sections.get("verification_steps", ""))
            ),
            raw_text=raw_text,
        )

    # ── Section splitter ──

    def _split_sections(self, text: str) -> dict[str, str]:
        """按 ## 标题切分文本为 {标题: 内容} 字典。"""
        sections: dict[str, str] = {}
        current_title = ""
        current_lines: list[str] = []

        for line in text.splitlines():
            match = re.match(r"^##\s+(.+)$", line)
            if match:
                if current_title:
                    sections[current_title] = "\n".join(current_lines).strip()
                current_title = match.group(1).strip()
                current_lines = []
            else:
                current_lines.append(line)

        if current_title:
            sections[current_title] = "\n".join(current_lines).strip()

        return sections

    # ── Change Summary Parser ──

    def _parse_change_summary(self, text: str) -> list[ChangeSummaryItem]:
        """解析变更摘要表格。"""
        items: list[ChangeSummaryItem] = []
        # 匹配表格行: | `file` | Lxx | before | after |
        row_pattern = re.compile(
            r"\|\s*`?([^`|]+)`?\s*\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|"
        )
        for line in text.splitlines():
            m = row_pattern.match(line.strip())
            if m:
                file_val = m.group(1).strip()
                line_range = m.group(2).strip()
                before = m.group(3).strip()
                after = m.group(4).strip()
                # 跳过表头和分隔行
                if file_val in ("文件", "file", "File") or line_range.startswith("-"):
                    continue
                items.append(ChangeSummaryItem(
                    file=file_val,
                    line_range=line_range,
                    before=before,
                    after=after,
                ))
        return items

    # ── Diff Blocks Parser ──

    def _parse_diff_blocks(self, text: str) -> list[DiffBlock]:
        """解析代码变更中的多个 diff block。"""
        blocks: list[DiffBlock] = []

        # 按 ### 变更 N 切分
        change_pattern = re.compile(r"###\s+变更\s*\d+[：:]\s*(.+)")
        file_pattern = re.compile(r"\*\*文件\*\*[：:]\s*`([^`]+)`")
        before_pattern = re.compile(r"\*\*改之前\*\*[：:]\s*(.+)")
        after_pattern = re.compile(r"\*\*改之后\*\*[：:]\s*(.+)")

        # 提取所有 diff 代码块
        parts = re.split(r"(###\s+变更\s*\d+)", text)

        current_title = ""
        for part in parts:
            title_match = change_pattern.search(part)
            if title_match:
                current_title = title_match.group(1).strip()
                continue

            # 在当前 part 中查找 file, diff, before, after
            file_match = file_pattern.search(part)
            diff_match = re.search(r"```diff\n(.*?)```", part, re.DOTALL)
            before_match = before_pattern.search(part)
            after_match = after_pattern.search(part)

            if diff_match:
                blocks.append(DiffBlock(
                    file=file_match.group(1) if file_match else "",
                    title=current_title,
                    diff_content=diff_match.group(1).strip(),
                    before_desc=before_match.group(1).strip() if before_match else "",
                    after_desc=after_match.group(1).strip() if after_match else "",
                ))

        return blocks

    # ── Blast Radius Parser ──

    def _parse_blast_radius(self, text: str) -> list[BlastRadiusItem]:
        """解析影响范围表格。"""
        items: list[BlastRadiusItem] = []
        row_pattern = re.compile(r"\|\s*\*?\*?([^|*]+)\*?\*?\s*\|\s*([^|]+)\|\s*([^|]+)\|")

        for line in text.splitlines():
            m = row_pattern.match(line.strip())
            if m:
                module_name = m.group(1).strip()
                impact = m.group(2).strip()
                action_str = m.group(3).strip()

                if module_name in ("受影响的模块/文件", "模块或文件名") or impact.startswith("-"):
                    continue

                action = ActionRequired.INFO_ONLY
                if "需要" in action_str and "仅" not in action_str:
                    action = ActionRequired.MUST
                elif "建议" in action_str:
                    action = ActionRequired.SUGGEST

                items.append(BlastRadiusItem(
                    file_or_module=module_name,
                    impact=impact,
                    action_required=action,
                ))
        return items

    # ── Verification Steps Parser ──

    def _parse_verification_steps(self, text: str) -> list[VerificationStep]:
        """解析验证步骤列表。"""
        items: list[VerificationStep] = []

        # 匹配: 1. **操作** → 预期结果  或  1. **操作**（...）→ 预期结果
        step_pattern = re.compile(
            r"\d+\.\s*\*\*(.+?)\*\*[（(]?([^)）]*)?[)）]?\s*[→\->]+\s*(.+)"
        )
        for line in text.splitlines():
            m = step_pattern.match(line.strip())
            if m:
                step_text = m.group(1).strip()
                # 如果有括号内容（如操作细节），拼上
                detail = m.group(2).strip() if m.group(2) else ""
                if detail:
                    step_text = f"{step_text}（{detail}）"
                expected = m.group(3).strip()
                items.append(VerificationStep(step=step_text, expected_result=expected))

        # 也支持 JSON 格式的 verification_steps
        json_match = re.search(r"```json\n(.*?)```", text, re.DOTALL)
        if json_match and not items:
            try:
                data = json.loads(json_match.group(1))
                for entry in data:
                    items.append(VerificationStep(
                        step=entry.get("step", ""),
                        expected_result=entry.get("expected_result", ""),
                    ))
            except (json.JSONDecodeError, KeyError, TypeError):
                pass

        return items


# ───────────────────────────────────────────
# Prompt Config (JSON 格式，用于 codebook_config 集成)
# ───────────────────────────────────────────

def get_codegen_prompt_config() -> dict:
    """
    返回 codegen 的 prompt 配置，与 codebook_config_v0.2.json 格式兼容。
    可以直接合并到 prompts 字段中。
    """
    return {
        "codegen_system": CODEGEN_SYSTEM_PROMPT,

        "codegen_prompt": textwrap.dedent("""\
用户指令：
{user_instruction}

定位结果：
{locate_result}

当前代码：
{current_code}

请输出：

## 变更摘要

| 文件 | 行号 | 改之前（当前做什么） | 改之后（变更做什么） |
|------|------|---------------------|---------------------|
| ... | ... | ... | ... |

## 代码变更

> 以下是给程序员看的具体代码改动。如果你只关心业务变化，看上面的变更摘要就够了。

### 变更 N：{变更标题}

**文件**：`{file_path}`

```diff
...
```

**改之前**：...
**改之后**：...

## 影响范围

| 受影响的模块/文件 | 影响说明 | 是否需要同步修改 |
|-------------------|----------|-----------------|
| ... | ... | 需要 / 建议 / 仅需知晓 |

## 验证方式

1. **{用户操作}** → {预期结果}

检查清单（输出前自检）：
- [ ] 变更摘要中没有代码术语？
- [ ] diff 上方有引导语？
- [ ] diff 行号与当前代码一致？
- [ ] 验证步骤中状态码都有中文注释？
- [ ] 变更范围最小化？
"""),
    }


# ───────────────────────────────────────────
# 便捷函数
# ───────────────────────────────────────────

def build_codegen_prompt(
    user_instruction: str,
    locate_result: LocateResult,
    current_code: dict[str, str],
    **kwargs,
) -> list[dict[str, str]]:
    """
    一步构建 codegen prompt messages。

    Args:
        user_instruction: 自然语言修改指令
        locate_result: Locate 定位结果
        current_code: {文件路径: 文件内容}
        **kwargs: 传递给 CodegenPromptBuilder.build 的额外参数

    Returns:
        messages 列表
    """
    builder = CodegenPromptBuilder()
    return builder.build(user_instruction, locate_result, current_code, **kwargs)


def parse_codegen_output(raw_text: str) -> CodegenResult:
    """
    一步解析 LLM 输出为结构化结果。

    Args:
        raw_text: LLM 返回的 Markdown 文本

    Returns:
        CodegenResult
    """
    parser = CodegenOutputParser()
    return parser.parse(raw_text)
