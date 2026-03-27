"""ask_about — 追问：针对特定模块进行多轮对话式追问。

上下文组装逻辑（按优先级填充，直到接近 token 上限）：
1. 目标模块的 L3 摘要（必选）
2. 目标模块的源代码（必选，但大文件截取关键部分）
3. 上下游 1 跳模块的 L3 摘要（高优先级）
4. 该模块已有的诊断结果（高优先级）
5. 其他用户对该模块的批注（如有）
6. 该模块的 QA 历史摘要（中优先级）
7. 相关热点信息（中优先级）
8. 上下游 2 跳模块的 L3 摘要（低优先级，空间不够可省略）
"""

from __future__ import annotations

import json
import os
import textwrap
import time
from typing import Any

import structlog

from src.config import settings
from src.summarizer.engine import SummaryContext, generate_local_chapter, _normalize_role
from src.parsers.module_grouper import ModuleGroup
from src.tools._repo_cache import repo_cache
from src.memory.project_memory import ProjectMemory

logger = structlog.get_logger()

# ───────────────────────────────────────────
# 常量
# ───────────────────────────────────────────

# 粗略估算：1 个中文字符 ≈ 2 tokens, 1 个英文单词 ≈ 1.3 tokens
# Claude 输入窗口较大，但我们给上下文设一个合理上限以保证质量
MAX_CONTEXT_CHARS = 60_000  # ≈ 30k tokens 的上下文预算
RESERVED_FOR_RESPONSE = 8_000  # 留给 LLM 回答的 token 数

ROLE_CONFIG = {
    "dev": {
        "name": "开发者",
        "language_style": "开发者视角、关注代码逻辑和技术细节，用完整的技术语言",
        "banned_terms": "",
    },
    "pm": {
        "name": "产品经理",
        "language_style": "产品视角、关注用户体验和功能逻辑，用清晰的业务语言",
        "banned_terms": "幂等、slug、冷启动、连接池、openapi、env_file、中间件、布尔值、回调、异步、序列化、AST、NetworkX、Tree-sitter",
    },
    "domain_expert": {
        "name": "行业专家",
        "language_style": "行业专家视角、用该领域的专业术语翻译代码逻辑，关注业务规则验证和合规性",
        "banned_terms": "",
    },
    # 向后兼容：旧角色名映射到新视图
    "ceo": {
        "name": "CEO / 创始人",
        "language_style": "高管视角、关注商业影响和战略风险，用简洁的业务语言",
        "banned_terms": "API、SDK、ORM、中间件、回调、异步、序列化、布尔值、连接池、冷启动",
        "_mapped_to": "pm",
    },
    "investor": {
        "name": "投资人",
        "language_style": "投资视角、关注技术壁垒、可扩展性和风险，用商业+技术概览语言",
        "banned_terms": "slug、env_file、中间件、序列化、回调",
        "_mapped_to": "pm",
    },
    "qa": {
        "name": "QA / 测试工程师",
        "language_style": "质量视角、关注边界条件、错误处理和测试覆盖，可以适度使用技术术语",
        "banned_terms": "",
        "_mapped_to": "dev",
    },
}


# ───────────────────────────────────────────
# 诊断结果缓存（简单内存存储）
# ───────────────────────────────────────────

class DiagnosisCache:
    """存储模块的诊断结果和用户批注，供 ask_about 引用。"""

    def __init__(self):
        self._diagnoses: dict[str, list[dict]] = {}  # module_name -> [diagnosis]
        self._annotations: dict[str, list[dict]] = {}  # module_name -> [annotation]

    def add_diagnosis(self, module_name: str, diagnosis: dict):
        self._diagnoses.setdefault(module_name, []).append(diagnosis)

    def add_annotation(self, module_name: str, annotation: dict):
        self._annotations.setdefault(module_name, []).append(annotation)

    def get_diagnoses(self, module_name: str) -> list[dict]:
        return self._diagnoses.get(module_name, [])

    def get_annotations(self, module_name: str) -> list[dict]:
        return self._annotations.get(module_name, [])


# 全局单例
diagnosis_cache = DiagnosisCache()


# ───────────────────────────────────────────
# 上下文组装
# ───────────────────────────────────────────

def _estimate_chars(text: str) -> int:
    """估算文本长度（用字符数作为 token 的粗略代理）。"""
    return len(text)


def _find_module(ctx: SummaryContext, module_name: str) -> ModuleGroup | None:
    """模糊匹配模块名，支持业务名和目录名。"""
    # 精确匹配
    for m in ctx.modules:
        if m.name == module_name or m.dir_path == module_name:
            return m

    # 模糊匹配
    candidates = []
    for m in ctx.modules:
        if module_name.lower() in m.name.lower() or module_name.lower() in m.dir_path.lower():
            candidates.append(m)

    if len(candidates) == 1:
        return candidates[0]
    return None


def _get_neighbor_modules(
    ctx: SummaryContext,
    module: ModuleGroup,
    hops: int = 1,
) -> tuple[list[str], list[str]]:
    """获取上下游 N 跳模块名。

    Returns:
        (upstream_names, downstream_names)
    """
    mg = ctx.dep_graph.get_module_graph()
    name = module.name

    upstream: set[str] = set()
    downstream: set[str] = set()

    # BFS 遍历
    current_up = {name}
    current_down = {name}

    for _ in range(hops):
        next_up: set[str] = set()
        for n in current_up:
            if n in mg:
                for pred in mg.predecessors(n):
                    if pred != name:
                        next_up.add(pred)
        upstream.update(next_up)
        current_up = next_up

        next_down: set[str] = set()
        for n in current_down:
            if n in mg:
                for succ in mg.successors(n):
                    if succ != name:
                        next_down.add(succ)
        downstream.update(next_down)
        current_down = next_down

    return list(upstream), list(downstream)


def _build_module_l3_summary(ctx: SummaryContext, module_name: str) -> str:
    """生成模块的 L3 摘要文本。"""
    chapter = generate_local_chapter(ctx, module_name)
    if chapter.get("status") != "ok":
        return f"（模块 {module_name} 的摘要暂不可用）"

    cards = chapter.get("module_cards", [])
    parts = [f"## 模块：{module_name}\n"]

    for card in cards:
        parts.append(f"### {card.get('name', '未命名')}")
        parts.append(f"- 功能：{card.get('what', '未知')}")
        if card.get("inputs"):
            parts.append(f"- 输入：{', '.join(card['inputs'][:5])}")
        if card.get("outputs"):
            parts.append(f"- 输出：{', '.join(card['outputs'][:5])}")
        if card.get("branches"):
            branch_texts = [
                f"  - {b.get('condition', '')} → {b.get('result', '')}"
                for b in card["branches"][:3]
            ]
            parts.append(f"- 分支逻辑：\n" + "\n".join(branch_texts))
        if card.get("side_effects"):
            parts.append(f"- 副作用：{', '.join(card['side_effects'][:3])}")
        if card.get("blast_radius"):
            parts.append(f"- 影响范围：{', '.join(card['blast_radius'][:3])}")
        parts.append("")

    return "\n".join(parts)


def _build_source_code_context(
    ctx: SummaryContext,
    module: ModuleGroup,
    repo_path: str,
    max_chars: int = 15_000,
) -> str:
    """读取模块源代码，大文件截取关键部分（公开函数、类定义）。"""
    module_files = set(module.files)
    relevant_prs = [pr for pr in ctx.parse_results if pr.file_path in module_files]

    parts = []
    total_chars = 0

    for pr in relevant_prs:
        abs_path = os.path.join(repo_path, pr.file_path)
        try:
            with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except OSError:
            continue

        lines = content.splitlines()

        if len(lines) <= 200:
            # 小文件完整包含
            numbered = _add_line_numbers(content)
            section = f"\n### {pr.file_path}\n```\n{numbered}\n```\n"
        else:
            # 大文件：截取关键部分（函数签名 + 前几行、类定义）
            key_ranges: list[tuple[int, int]] = []

            for func in pr.functions:
                if not func.name.startswith("_") or func.name == "__init__":
                    start = max(0, func.line_start - 1)
                    end = min(len(lines), start + 20)  # 函数前 20 行
                    key_ranges.append((start, end))

            for cls in pr.classes:
                start = max(0, cls.line_start - 1)
                end = min(len(lines), start + 10)
                key_ranges.append((start, end))

            # 合并重叠区间
            key_ranges.sort()
            merged: list[tuple[int, int]] = []
            for s, e in key_ranges:
                if merged and s <= merged[-1][1] + 2:
                    merged[-1] = (merged[-1][0], max(merged[-1][1], e))
                else:
                    merged.append((s, e))

            snippets = []
            for s, e in merged[:10]:
                snippet_lines = lines[s:e]
                numbered_snippet = "\n".join(
                    f"{i + s + 1:4d} | {line}" for i, line in enumerate(snippet_lines)
                )
                snippets.append(numbered_snippet)

            section = (
                f"\n### {pr.file_path} （共 {len(lines)} 行，截取关键部分）\n```\n"
                + "\n...\n".join(snippets)
                + "\n```\n"
            )

        section_len = _estimate_chars(section)
        if total_chars + section_len > max_chars:
            parts.append(f"\n（剩余文件因上下文空间不足而省略）")
            break
        parts.append(section)
        total_chars += section_len

    return "\n".join(parts)


def _add_line_numbers(content: str) -> str:
    """给代码添加行号。"""
    lines = content.splitlines()
    return "\n".join(f"{i + 1:4d} | {line}" for i, line in enumerate(lines))


def _build_diagnosis_context(module_name: str) -> str:
    """构建该模块已有的诊断结果上下文。"""
    diagnoses = diagnosis_cache.get_diagnoses(module_name)
    if not diagnoses:
        return ""

    parts = ["## 已有诊断结果\n"]
    for i, diag in enumerate(diagnoses[-3:], 1):  # 最近 3 条
        parts.append(f"### 诊断 {i}")
        if isinstance(diag, dict):
            if diag.get("diagnosis"):
                parts.append(f"- 结论：{diag['diagnosis']}")
            if diag.get("matched_modules"):
                parts.append(f"- 涉及模块：{diag['matched_modules']}")
            if diag.get("exact_locations"):
                locs = diag["exact_locations"]
                for loc in locs[:3]:
                    if isinstance(loc, dict):
                        parts.append(
                            f"- 定位：{loc.get('file', '?')}:{loc.get('line', '?')} "
                            f"— {loc.get('why_it_matters', '')}"
                        )
        parts.append("")

    return "\n".join(parts)


def _build_annotation_context(module_name: str) -> str:
    """构建该模块的用户批注上下文。"""
    annotations = diagnosis_cache.get_annotations(module_name)
    if not annotations:
        return ""

    parts = ["## 用户批注\n"]
    for ann in annotations[-5:]:  # 最近 5 条
        if isinstance(ann, dict):
            author = ann.get("author", "匿名")
            text = ann.get("text", "")
            parts.append(f"- [{author}] {text}")

    return "\n".join(parts)


def _build_qa_history_context(memory: ProjectMemory, module_name: str) -> str:
    """构建该模块的 QA 历史摘要（优先级 6）。"""
    try:
        understanding = memory.get_module_understanding(module_name)
        if not understanding or not understanding.qa_history:
            return ""

        parts = ["## 历史问题与回答\n"]
        for qa in understanding.qa_history[-3:]:  # 最近 3 条
            parts.append(f"### 问题：{qa.question}")
            parts.append(f"- 回答摘要：{qa.answer_summary}")
            parts.append(f"- 置信度：{qa.confidence:.1%}")
            if qa.follow_ups_used:
                parts.append(f"- 后续追问方向：{', '.join(qa.follow_ups_used[:2])}")
            parts.append("")

        return "\n".join(parts)
    except Exception as e:
        logger.debug("qa_history_context_failed", error=str(e))
        return ""


def _build_hotspot_context(memory: ProjectMemory, module_name: str) -> str:
    """构建该模块的热点信息（优先级 7）。"""
    try:
        hotspots = memory.get_hotspots(module_name)
        if not hotspots:
            return ""

        parts = ["## 已知知识热点\n"]
        for hotspot in hotspots[:3]:  # 最多 3 个热点
            parts.append(f"### {hotspot.topic}")
            parts.append(f"- 相关问题数：{hotspot.question_count}")
            if hotspot.typical_questions:
                parts.append(f"- 代表性问题：")
                for q in hotspot.typical_questions[:2]:
                    parts.append(f"  - {q}")
            if hotspot.suggested_doc:
                parts.append(f"- 建议补充文档：{hotspot.suggested_doc[:100]}")
            parts.append("")

        return "\n".join(parts)
    except Exception as e:
        logger.debug("hotspot_context_failed", error=str(e))
        return ""


def assemble_context(
    ctx: SummaryContext,
    module: ModuleGroup,
    repo_path: str,
) -> tuple[str, list[str]]:
    """按优先级组装上下文，直到接近 token 上限。

    优先级：
    1. 目标模块 L3 摘要（必选）
    2. 目标模块源代码（必选）
    3. 上下游 1 跳模块的 L3 摘要（高优先级）
    4. 诊断结果（高优先级）
    5. 用户批注（高优先级）
    6. QA 历史摘要（中优先级）
    7. 热点信息（中优先级）
    8. 上下游 2 跳模块的 L3 摘要（低优先级）

    Returns:
        (context_text, modules_used_list)
    """
    budget = MAX_CONTEXT_CHARS
    parts: list[str] = []
    modules_used: list[str] = [module.name]

    def _try_append(text: str, label: str) -> bool:
        nonlocal budget
        cost = _estimate_chars(text)
        if cost > budget:
            logger.debug("context.budget_exceeded", label=label, cost=cost, remaining=budget)
            return False
        parts.append(text)
        budget -= cost
        return True

    # Initialize ProjectMemory if repo_url available
    memory = None
    try:
        repo_url = ctx.repo_url or ""
        if repo_url:
            memory = ProjectMemory(repo_url)
    except Exception as e:
        logger.debug("memory_initialization_failed", error=str(e))

    # ── 优先级 1：目标模块 L3 摘要（必选）──
    l3_summary = _build_module_l3_summary(ctx, module.name)
    _try_append(l3_summary, "target_l3")

    # ── 优先级 2：目标模块源代码（必选，大文件截取）──
    source_budget = min(15_000, budget // 2)  # 源代码最多占剩余预算的一半
    source_code = _build_source_code_context(ctx, module, repo_path, max_chars=source_budget)
    if source_code.strip():
        _try_append(f"## 模块源代码\n{source_code}", "target_source")

    # ── 优先级 3：上下游 1 跳模块的 L3 摘要（高优先级）──
    up_1hop, down_1hop = _get_neighbor_modules(ctx, module, hops=1)
    for neighbor_name in (up_1hop + down_1hop)[:6]:
        neighbor_summary = _build_module_l3_summary(ctx, neighbor_name)
        if _try_append(f"\n{neighbor_summary}", f"neighbor_1hop_{neighbor_name}"):
            modules_used.append(neighbor_name)
        else:
            break

    # ── 优先级 4：该模块已有的诊断结果（高优先级）──
    # Try ProjectMemory first, fall back to DiagnosisCache
    diag_text = ""
    if memory:
        try:
            understanding = memory.get_module_understanding(module.name)
            if understanding and understanding.diagnoses:
                diag_parts = ["## 已有诊断结果\n"]
                for i, diag in enumerate(understanding.diagnoses[-3:], 1):
                    diag_parts.append(f"### 诊断 {i}")
                    diag_parts.append(f"- 问题：{diag.query}")
                    diag_parts.append(f"- 结论：{diag.diagnosis_summary}")
                    if diag.matched_locations:
                        diag_parts.append(f"- 定位：{', '.join(diag.matched_locations[:3])}")
                    diag_parts.append("")
                diag_text = "\n".join(diag_parts)
        except Exception as e:
            logger.debug("diagnosis_from_memory_failed", error=str(e))

    if not diag_text:
        diag_text = _build_diagnosis_context(module.name)

    if diag_text:
        _try_append(diag_text, "diagnoses")

    # ── 优先级 5：用户批注（高优先级）──
    ann_text = _build_annotation_context(module.name)
    if ann_text:
        _try_append(ann_text, "annotations")

    # ── 优先级 6：QA 历史摘要（中优先级）──
    if memory:
        qa_text = _build_qa_history_context(memory, module.name)
        if qa_text:
            _try_append(qa_text, "qa_history")

    # ── 优先级 7：热点信息（中优先级）──
    if memory:
        hotspot_text = _build_hotspot_context(memory, module.name)
        if hotspot_text:
            _try_append(hotspot_text, "hotspots")

    # ── 优先级 8：上下游 2 跳模块的 L3 摘要（低优先级）──
    up_2hop, down_2hop = _get_neighbor_modules(ctx, module, hops=2)
    # 去掉已经包含的 1 跳
    already = set(modules_used)
    hop2_names = [n for n in (up_2hop + down_2hop) if n not in already]
    for neighbor_name in hop2_names[:4]:
        neighbor_summary = _build_module_l3_summary(ctx, neighbor_name)
        if _try_append(f"\n{neighbor_summary}", f"neighbor_2hop_{neighbor_name}"):
            modules_used.append(neighbor_name)
        else:
            break

    context_text = "\n".join(parts)
    return context_text, modules_used


# ───────────────────────────────────────────
# System Prompt 构建
# ───────────────────────────────────────────

def _build_system_prompt(role: str) -> str:
    """根据角色构建 system prompt。"""
    # 规范化角色名（处理向后兼容性）
    normalized_role = _normalize_role(role)

    cfg = ROLE_CONFIG.get(normalized_role, ROLE_CONFIG["pm"])
    role_name = cfg["name"]
    language_style = cfg["language_style"]
    banned_terms = cfg["banned_terms"]

    prompt_intro = f"你是 CodeBook 的 AI 助手，正在帮助{role_name}理解代码。\n用{language_style}回答。"

    if banned_terms:
        prompt_intro += f"\n禁止在主回答中使用以下术语：{banned_terms}。"

    return textwrap.dedent(f"""\
{prompt_intro}

## 回答规则

1. 如果用户的问题需要你查看代码细节，用非技术语言解释，
   把代码引用放在 evidence 字段中（不要在主回答中展示代码）。
2. 如果问题超出你的上下文范围，坦诚说明并建议追问其他模块。
3. 最后给 2-3 个后续追问建议，帮助用户深入了解。

## 输出格式

严格用以下 JSON 格式输出，不要加 Markdown 修饰：

```json
{{
  "answer": "角色适配后的自然语言回答",
  "evidence": [
    {{
      "type": "code | summary | diagnosis",
      "file": "文件路径（code 类型时提供）",
      "lines": "行号范围（code 类型时提供，如 10-25）",
      "snippet": "代码片段（code 类型时提供）",
      "module": "模块名（summary 类型时提供）",
      "text": "摘要文本（summary 类型时提供）",
      "finding": "诊断发现（diagnosis 类型时提供）"
    }}
  ],
  "follow_up_suggestions": [
    "你可能还想问：...",
    "你可能还想问：..."
  ],
  "confidence": 0.9
}}
```

confidence 取值说明：
- 0.9-1.0：上下文中有充分信息，回答确定
- 0.7-0.9：大部分信息可用，少量推断
- 0.5-0.7：信息有限，回答含有猜测成分
- 0.0-0.5：上下文不足，建议追问其他模块
""")


# ───────────────────────────────────────────
# 输出解析
# ───────────────────────────────────────────

def _parse_llm_response(raw_text: str) -> dict:
    """从 LLM 输出中解析 JSON 结构。"""
    import re

    # 尝试直接解析
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        pass

    # 尝试从 ```json ... ``` 中提取
    match = re.search(r"```json\s*\n(.*?)\n```", raw_text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # 尝试从最外层 { ... } 提取
    match = re.search(r"\{[\s\S]*\}", raw_text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    # 解析失败，构造回退响应
    return {
        "answer": raw_text,
        "evidence": [],
        "follow_up_suggestions": [],
        "confidence": 0.5,
    }


# ───────────────────────────────────────────
# 主入口
# ───────────────────────────────────────────

async def ask_about(
    module_name: str,
    question: str,
    role: str = "ceo",
    conversation_history: list[dict[str, str]] | None = None,
) -> dict:
    """针对指定模块进行追问，支持多轮对话。

    上下文组装逻辑（按优先级填充，直到接近 token 上限）：
    1. 目标模块的 L3 摘要（必选）
    2. 目标模块的源代码（必选，但大文件截取关键部分）
    3. 上下游 1 跳模块的 L3 摘要（高优先级）
    4. 该模块已有的诊断结果（高优先级）
    5. 其他用户对该模块的批注（如有）
    6. 上下游 2 跳模块的 L3 摘要（低优先级，空间不够可省略）

    Args:
        module_name: 要追问的模块名称（业务语言）。
        question: 用户的追问内容（自然语言）。
        role: 目标角色。可选: ceo, pm, investor, qa。
        conversation_history: 多轮对话历史。
            格式: [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]

    Returns:
        {
            "answer": "角色适配后的自然语言回答",
            "evidence": [...],
            "follow_up_suggestions": [...],
            "confidence": 0.9,
            "context_modules_used": ["目标模块", "上游A", "下游B"]
        }
    """
    start = time.time()
    logger.info(
        "ask_about.start",
        module_name=module_name,
        question=question[:80],
        role=role,
        history_turns=len(conversation_history) if conversation_history else 0,
    )

    if conversation_history is None:
        conversation_history = []

    # ── Step 1：获取缓存上下文 ──
    from src.tools._repo_cache import _ExpiredSentinel
    ctx = repo_cache.get()
    if isinstance(ctx, _ExpiredSentinel):
        return {
            "status": "error",
            "error": f"仓库「{ctx.repo_url}」的缓存已过期（超过 7 天未使用），请重新运行 scan_repo",
            "hint": "缓存按最后访问时间计算，连续 7 天未使用才会过期。重新扫描即可恢复。",
            "answer": None,
            "evidence": [],
            "follow_up_suggestions": [],
            "confidence": 0.0,
            "context_modules_used": [],
        }
    if ctx is None:
        return {
            "status": "error",
            "error": "请先调用 scan_repo 扫描项目",
            "hint": "ask_about 需要先扫描项目才能回答追问。请先使用 scan_repo 工具扫描仓库。",
            "answer": None,
            "evidence": [],
            "follow_up_suggestions": [],
            "confidence": 0.0,
            "context_modules_used": [],
        }

    # ── Step 2：查找目标模块 ──
    target_module = _find_module(ctx, module_name)
    if target_module is None:
        available = [m.name for m in ctx.modules if not m.is_special]
        return {
            "status": "error",
            "error": f"未找到模块「{module_name}」",
            "available_modules": available,
            "answer": None,
            "evidence": [],
            "follow_up_suggestions": [
                f"你可能想问的模块：{', '.join(available[:5])}"
            ],
            "confidence": 0.0,
            "context_modules_used": [],
        }

    # ── Step 3：获取仓库路径 ──
    repo_path = ctx.clone_result.repo_path

    # ── Step 4：组装上下文 ──
    context_text, modules_used = assemble_context(ctx, target_module, repo_path)

    logger.info(
        "ask_about.context_assembled",
        context_chars=len(context_text),
        modules_used=modules_used,
    )

    # ── Step 5：构建角色引导 ──
    guidance = _build_system_prompt(role)

    elapsed = round(time.time() - start, 2)
    logger.info(
        "ask_about.done",
        module=module_name,
        context_chars=len(context_text),
        seconds=elapsed,
    )

    # ── Step 6：返回上下文（由 MCP 宿主 LLM 推理） ──
    # 不再内部调用 Anthropic API，而是把组装好的上下文交给宿主
    return {
        "status": "ok",
        "module_name": module_name,
        "role": role,
        "context": context_text,
        "guidance": guidance,
        "question": question,
        "conversation_history": conversation_history,
        "context_modules_used": modules_used,
    }
