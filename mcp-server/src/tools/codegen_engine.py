"""codegen_engine — Codegen 引擎：端到端编排层。

将 prompt 构建、LLM 调用、输出解析、diff 验证整合为一个完整的流水线。
"""

from __future__ import annotations

import json
import re
import textwrap
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import structlog

from src.config import settings
from src.tools.diff_validator import (
    DiffValidator,
    ValidationResult,
    assemble_full_diff,
)

logger = structlog.get_logger()


# ───────────────────────────────────────────
# 数据模型
# ───────────────────────────────────────────

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
    action_required: str  # "需要" | "建议" | "仅需知晓"


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


# ───────────────────────────────────────────
# System Prompt
# ───────────────────────────────────────────

CODEGEN_SYSTEM_PROMPT = textwrap.dedent("""\
你是 CodeBook 的代码生成引擎。

你的用户是不会写代码的产品经理、创业者、设计师。他们用自然语言描述想要的修改，\
你负责生成精确的代码变更，并用他们能看懂的语言解释这些变更。

## 核心规则

### 规则 1：变更最小化
只改必要的代码。不要为了「更好的结构」引入额外改动。

### 规则 2：Diff 必须精确可应用
- 使用标准 unified diff 格式，包含完整的 --- a/path 和 +++ b/path 文件头
- @@ -old_start,old_count +new_start,new_count @@ hunk header 的行号必须精确
- 上下文行（不变的行）至少保留 3 行
- diff 必须可以直接通过 `git apply` 或 `patch -p1` 应用
- 上下文行和删除行的内容必须与当前代码中的内容完全一致（包括缩进）
- 如果同一个文件有多处修改，合并为一个 diff block

### 规则 3：双轨输出
每个变更同时提供：
- **变更摘要**（给 PM 看）：纯业务语言，禁止出现代码术语
- **unified diff**（给程序员看）：精确 diff

### 规则 4：影响范围必须包含
- 具体的文件路径或模块名
- 业务语言解释为什么被影响
- 是否需要同步修改（需要 / 建议 / 仅需知晓）

### 规则 5：验证步骤必须是用户操作
- 主语是「用户」或具体角色
- 描述页面操作（点击、输入、提交）
- 预期结果是可观察的（看到某文案、页面跳转）
- HTTP 状态码加中文注释

## 输出格式

严格用以下 JSON 格式输出，不要加任何 Markdown 修饰：

```json
{
  "change_summary": [
    {
      "file": "文件路径",
      "line_range": "Lxx-Lyy",
      "before": "改之前做什么（业务语言）",
      "after": "改之后做什么（业务语言）"
    }
  ],
  "diff_blocks": [
    {
      "file": "文件路径",
      "title": "变更标题（业务语言）",
      "diff_content": "完整的 unified diff（包含 --- +++ @@ 行）",
      "before_desc": "改之前一句话",
      "after_desc": "改之后一句话"
    }
  ],
  "blast_radius": [
    {
      "file_or_module": "文件或模块名",
      "impact": "业务语言的影响描述",
      "action_required": "需要 / 建议 / 仅需知晓"
    }
  ],
  "verification_steps": [
    {
      "step": "用户做什么操作",
      "expected_result": "预期看到什么"
    }
  ]
}
```

在 diff_content 字段中，diff 必须像这样完整：
```
--- a/path/to/file.py
+++ b/path/to/file.py
@@ -10,7 +10,7 @@
 context line
 context line
-old line
+new line
 context line
 context line
```

关键：上下文行开头必须有一个空格字符。删除行以 - 开头，新增行以 + 开头。\
行号必须与当前代码中的实际行号完全一致。
""")


# ───────────────────────────────────────────
# LLM 调用器
# ───────────────────────────────────────────

class LLMCaller:
    """兼容层：保留类接口供测试使用，但实际运行时不再调用外部 LLM。

    MCP 架构下，codegen 不再自行调用 Anthropic API，
    而是将组装好的上下文返回给 MCP 宿主（Claude Desktop），由宿主 LLM 生成代码。
    """

    def __init__(self, model: str | None = None, max_tokens: int | None = None):
        self.model = model or settings.ai_model
        self.max_tokens = max_tokens or settings.ai_max_tokens

    async def call(self, messages: list[dict[str, str]]) -> str:
        """兼容接口 — MCP 模式下不再被主流程调用。"""
        raise NotImplementedError(
            "MCP 架构下不再需要内部 LLM 调用。"
            "codegen 现在返回上下文和 prompt，由 MCP 宿主生成代码。"
        )


# ───────────────────────────────────────────
# 输出解析器
# ───────────────────────────────────────────

class CodegenOutputParser:
    """将 LLM 的 JSON 输出解析为结构化对象。"""

    def parse(self, raw_text: str) -> CodegenOutput:
        """解析 LLM 输出。支持 JSON 和 Markdown 两种格式。"""
        output = CodegenOutput(raw_llm_output=raw_text)

        # 尝试提取 JSON
        json_data = self._extract_json(raw_text)
        if json_data:
            output.change_summary = [
                ChangeSummaryItem(**item) for item in json_data.get("change_summary", [])
            ]
            output.diff_blocks = [
                DiffBlock(**item) for item in json_data.get("diff_blocks", [])
            ]
            output.blast_radius = [
                BlastRadiusItem(**item) for item in json_data.get("blast_radius", [])
            ]
            output.verification_steps = [
                VerificationStep(**item) for item in json_data.get("verification_steps", [])
            ]
        else:
            # 回退到 Markdown 格式解析
            output = self._parse_markdown(raw_text, output)

        return output

    def _extract_json(self, text: str) -> dict | None:
        """从文本中提取 JSON 块。"""
        # 尝试直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 尝试从 ```json ... ``` 中提取
        match = re.search(r"```json\s*\n(.*?)\n```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # 尝试从 { ... } 中提取（贪心匹配最外层大括号）
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        return None

    def _parse_markdown(self, text: str, output: CodegenOutput) -> CodegenOutput:
        """从 Markdown 格式解析（后备方案）。"""
        sections = self._split_sections(text)

        # 变更摘要
        summary_text = sections.get("变更摘要", "")
        if summary_text:
            output.change_summary = self._parse_table_rows(
                summary_text,
                lambda cols: ChangeSummaryItem(
                    file=cols[0], line_range=cols[1],
                    before=cols[2], after=cols[3],
                ) if len(cols) >= 4 else None,
            )

        # diff blocks
        diff_text = sections.get("代码变更", "")
        if diff_text:
            output.diff_blocks = self._parse_diff_blocks(diff_text)

        # 影响范围
        blast_text = sections.get("影响范围", "")
        if blast_text:
            output.blast_radius = self._parse_table_rows(
                blast_text,
                lambda cols: BlastRadiusItem(
                    file_or_module=cols[0].strip("*"),
                    impact=cols[1],
                    action_required=cols[2],
                ) if len(cols) >= 3 else None,
            )

        # 验证方式
        verify_text = sections.get("验证方式", "")
        if verify_text:
            output.verification_steps = self._parse_verify_steps(verify_text)

        return output

    def _split_sections(self, text: str) -> dict[str, str]:
        sections: dict[str, str] = {}
        current = ""
        lines: list[str] = []
        for line in text.splitlines():
            m = re.match(r"^##\s+(.+)$", line)
            if m:
                if current:
                    sections[current] = "\n".join(lines).strip()
                current = m.group(1).strip()
                lines = []
            else:
                lines.append(line)
        if current:
            sections[current] = "\n".join(lines).strip()
        return sections

    def _parse_table_rows(self, text, row_factory):
        items = []
        for line in text.splitlines():
            if not line.strip().startswith("|"):
                continue
            cols = [c.strip().strip("`") for c in line.split("|")[1:-1]]
            if not cols or cols[0] in ("文件", "受影响的模块/文件", "File"):
                continue
            if all(c.startswith("-") for c in cols):
                continue
            item = row_factory(cols)
            if item:
                items.append(item)
        return items

    def _parse_diff_blocks(self, text: str) -> list[DiffBlock]:
        blocks = []
        parts = re.split(r"###\s+变更\s*\d+[：:]?\s*", text)
        for part in parts:
            if not part.strip():
                continue
            title_match = re.match(r"(.+?)[\n]", part)
            title = title_match.group(1).strip() if title_match else ""
            file_match = re.search(r"\*\*文件\*\*[：:]\s*`([^`]+)`", part)
            diff_match = re.search(r"```diff\n(.*?)```", part, re.DOTALL)
            before_match = re.search(r"\*\*改之前\*\*[：:]\s*(.+)", part)
            after_match = re.search(r"\*\*改之后\*\*[：:]\s*(.+)", part)

            if diff_match:
                blocks.append(DiffBlock(
                    file=file_match.group(1) if file_match else "",
                    title=title,
                    diff_content=diff_match.group(1).strip(),
                    before_desc=before_match.group(1).strip() if before_match else "",
                    after_desc=after_match.group(1).strip() if after_match else "",
                ))
        return blocks

    def _parse_verify_steps(self, text: str) -> list[VerificationStep]:
        items = []
        pattern = re.compile(
            r"\d+\.\s*\*\*(.+?)\*\*.*?[→\->]+\s*(.+)"
        )
        for line in text.splitlines():
            m = pattern.match(line.strip())
            if m:
                items.append(VerificationStep(
                    step=m.group(1).strip(),
                    expected_result=m.group(2).strip(),
                ))
        return items


# ───────────────────────────────────────────
# 引擎主类
# ───────────────────────────────────────────

class CodegenEngine:
    """Codegen 引擎：编排 prompt 构建 → LLM 调用 → 解析 → 验证。"""

    def __init__(
        self,
        repo_path: str,
        llm_caller: LLMCaller | None = None,
        max_retries: int = 1,
    ):
        self.repo_path = Path(repo_path)
        self.llm = llm_caller or LLMCaller()
        self.parser = CodegenOutputParser()
        self.validator = DiffValidator(repo_path)
        self.max_retries = max_retries

    async def run(
        self,
        instruction: str,
        locate_result: dict | None = None,
        file_paths: list[str] | None = None,
        role: str = "pm",
    ) -> dict:
        """
        组装代码上下文，返回给 MCP 宿主 LLM 推理。

        MCP 架构下不再内部调用 LLM，而是返回：
        - 当前源代码（带行号）
        - 定位结果
        - 生成指引（system prompt）
        - 用户指令

        Returns:
            结构化字典，包含 guidance, current_code, locate_info 等
        """
        # Step 1: 准备输入
        locate = self._build_locate_result(locate_result)
        current_code = self._load_files(locate, file_paths)

        if not current_code:
            return self._error_result("没有找到可修改的源文件。请检查文件路径。")

        logger.info(
            "codegen: files loaded",
            files=list(current_code.keys()),
            total_lines=sum(len(v.splitlines()) for v in current_code.values()),
        )

        # Step 2: 构建带行号的源代码
        numbered_code = {}
        for file_path, content in current_code.items():
            numbered_code[file_path] = self._add_line_numbers(content)

        # Step 3: 构建定位信息
        locate_info = {}
        if locate.matched_modules and locate.matched_modules != "（未提供定位信息）":
            locate_info["matched_modules"] = locate.matched_modules
        if locate.call_chain_mermaid:
            locate_info["call_chain_mermaid"] = locate.call_chain_mermaid
        if locate.exact_locations:
            locate_info["exact_locations"] = [
                {"file": l.file, "line": l.line,
                 "why_it_matters": l.why_it_matters, "certainty": l.certainty}
                for l in locate.exact_locations
            ]
        if locate.diagnosis:
            locate_info["diagnosis"] = locate.diagnosis

        # Step 4: 返回上下文（由 MCP 宿主 LLM 推理生成代码）
        return {
            "status": "context_ready",
            "instruction": instruction,
            "guidance": CODEGEN_SYSTEM_PROMPT,
            "current_code": numbered_code,
            "locate_info": locate_info,
            "files": list(current_code.keys()),
        }

    # ── Step 1: 输入准备 ──

    def _build_locate_result(self, raw: dict | None) -> LocateResult:
        """将字典转为 LocateResult 结构。"""
        if not raw:
            return LocateResult(
                matched_modules="（未提供定位信息）",
                call_chain_mermaid="",
                exact_locations=[],
                diagnosis="（用户直接指定文件路径，未经过 locate 阶段）",
            )

        locations = []
        for loc in raw.get("exact_locations", []):
            if isinstance(loc, dict):
                locations.append(ExactLocation(
                    file=loc.get("file", ""),
                    line=loc.get("line", 0),
                    why_it_matters=loc.get("why_it_matters", ""),
                    certainty=loc.get("certainty", "非常确定"),
                ))

        return LocateResult(
            matched_modules=raw.get("matched_modules", ""),
            call_chain_mermaid=raw.get("call_chain", raw.get("call_chain_mermaid", "")),
            exact_locations=locations,
            diagnosis=raw.get("diagnosis", ""),
        )

    def _load_files(
        self,
        locate: LocateResult,
        file_paths: list[str] | None,
    ) -> dict[str, str]:
        """从仓库中读取需要修改的文件内容。"""
        paths_to_load: set[str] = set()

        # 从 locate 结果中提取文件路径
        for loc in locate.exact_locations:
            if loc.file:
                paths_to_load.add(loc.file)

        # 用户指定的文件路径
        if file_paths:
            paths_to_load.update(file_paths)

        current_code: dict[str, str] = {}
        for rel_path in sorted(paths_to_load):
            full_path = self.repo_path / rel_path
            if full_path.exists() and full_path.is_file():
                try:
                    current_code[rel_path] = full_path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    logger.warning("file encoding error, skipping", path=rel_path)

        return current_code

    # ── Step 2: Prompt 构建 ──

    def _build_prompt(
        self,
        instruction: str,
        locate: LocateResult,
        current_code: dict[str, str],
    ) -> list[dict[str, str]]:
        """三层 prompt 组装。"""

        # Context layer
        context_parts = []

        context_parts.append("## 定位结果\n")
        if locate.matched_modules and locate.matched_modules != "（未提供定位信息）":
            context_parts.append("### 相关模块\n")
            context_parts.append(
                locate.matched_modules
                if isinstance(locate.matched_modules, str)
                else "\n".join(f"- {m}" for m in locate.matched_modules)
            )
            context_parts.append("")

        if locate.call_chain_mermaid:
            context_parts.append("### 调用链路图\n")
            context_parts.append(locate.call_chain_mermaid)
            context_parts.append("")

        if locate.exact_locations:
            context_parts.append("### 精确定位\n```json")
            locs_data = [
                {
                    "file": l.file, "line": l.line,
                    "why_it_matters": l.why_it_matters,
                    "certainty": l.certainty,
                }
                for l in locate.exact_locations
            ]
            context_parts.append(json.dumps(locs_data, ensure_ascii=False, indent=2))
            context_parts.append("```\n")

        if locate.diagnosis:
            context_parts.append("### 诊断结论\n")
            context_parts.append(locate.diagnosis)
            context_parts.append("")

        # 当前代码（带行号）
        context_parts.append("## 当前代码\n")
        context_parts.append("以下是需要修改的源文件完整内容（带行号）。diff 必须基于这些内容生成。\n")

        for file_path, content in current_code.items():
            lang = self._detect_language(file_path)
            numbered = self._add_line_numbers(content)
            context_parts.append(f"### `{file_path}`\n```{lang}")
            context_parts.append(numbered)
            context_parts.append("```\n")

        context_text = "\n".join(context_parts)

        # User layer
        user_text = f"""## 用户指令

{instruction}

---

请基于上面的定位结果和当前代码，生成精确的代码变更方案。

重要：diff_content 字段中的 unified diff 必须包含完整的文件头（--- a/path 和 +++ b/path）\
和精确的 @@ hunk header。上下文行的内容必须与当前代码完全一致。"""

        return [
            {"role": "system", "content": CODEGEN_SYSTEM_PROMPT},
            {"role": "user", "content": f"{context_text}\n\n---\n\n{user_text}"},
        ]

    # ── Step 3: LLM 调用 ──

    async def _call_and_parse(
        self, messages: list[dict[str, str]]
    ) -> CodegenOutput:
        """调用 LLM 并解析输出，含一次重试。"""
        for attempt in range(self.max_retries + 1):
            raw = await self.llm.call(messages)
            output = self.parser.parse(raw)

            if output.diff_blocks:
                return output

            if attempt < self.max_retries:
                logger.warning("codegen: no diff blocks, retrying", attempt=attempt)
                # 追加提示
                messages = messages + [
                    {"role": "assistant", "content": raw},
                    {"role": "user", "content": (
                        "你的输出中没有 diff_blocks。"
                        "请重新生成，确保 JSON 中包含 diff_blocks 数组，"
                        "每个元素的 diff_content 字段包含完整的 unified diff。"
                    )},
                ]

        output.raw_llm_output = raw
        return output

    # ── Step 6: 格式化 ──

    def _format_result(self, output: CodegenOutput) -> dict:
        """将 CodegenOutput 转为 API 返回字典。"""
        status = "success" if output.diff_valid else "partial"
        if not output.diff_blocks:
            status = "error"

        return {
            "status": status,
            "change_summary": [asdict(s) for s in output.change_summary],
            "unified_diff": output.unified_diff,
            "diff_blocks": [
                {
                    "file": b.file,
                    "title": b.title,
                    "diff_content": b.diff_content,
                    "before_desc": b.before_desc,
                    "after_desc": b.after_desc,
                }
                for b in output.diff_blocks
            ],
            "blast_radius": [asdict(b) for b in output.blast_radius],
            "verification_steps": [asdict(v) for v in output.verification_steps],
            "diff_valid": output.diff_valid,
            "validation_detail": output.validation_detail,
            "raw_llm_output": output.raw_llm_output,
        }

    def _error_result(self, msg: str, raw: str = "") -> dict:
        return {
            "status": "error",
            "error": msg,
            "change_summary": [],
            "unified_diff": "",
            "diff_blocks": [],
            "blast_radius": [],
            "verification_steps": [],
            "diff_valid": False,
            "validation_detail": msg,
            "raw_llm_output": raw,
        }

    # ── 工具方法 ──

    @staticmethod
    def _add_line_numbers(content: str) -> str:
        lines = content.splitlines()
        return "\n".join(f"{i+1:4d} | {line}" for i, line in enumerate(lines))

    @staticmethod
    def _detect_language(file_path: str) -> str:
        ext_map = {
            ".py": "python", ".js": "javascript", ".ts": "typescript",
            ".tsx": "tsx", ".jsx": "jsx", ".java": "java", ".go": "go",
            ".rs": "rust", ".rb": "ruby", ".html": "html", ".css": "css",
            ".sql": "sql", ".yaml": "yaml", ".json": "json", ".sh": "bash",
        }
        for ext, lang in ext_map.items():
            if file_path.endswith(ext):
                return lang
        return ""
