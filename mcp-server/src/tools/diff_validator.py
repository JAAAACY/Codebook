"""diff_validator — 验证 unified diff 可以直接 git apply。

提供三层验证：
1. 格式验证：检查 diff 是否符合 unified diff 语法
2. 上下文验证：检查 diff 中的上下文行是否与源文件匹配
3. apply 验证：用 git apply --check 或内存模拟实际应用
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import structlog

logger = structlog.get_logger()


# ───────────────────────────────────────────
# 数据模型
# ───────────────────────────────────────────

@dataclass
class DiffHunk:
    """一个 diff hunk（一组连续的变更）。"""
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[str]  # 包含 +/- /空格前缀的行


@dataclass
class FileDiff:
    """单个文件的 diff。"""
    old_path: str
    new_path: str
    hunks: list[DiffHunk] = field(default_factory=list)


@dataclass
class ValidationResult:
    """验证结果。"""
    valid: bool
    message: str
    details: list[str] = field(default_factory=list)
    repaired_diff: str | None = None  # 如果修复了，放修复后的 diff


# ───────────────────────────────────────────
# 核心类
# ───────────────────────────────────────────

class DiffValidator:
    """验证和修复 unified diff。"""

    def __init__(self, repo_path: str):
        """
        Args:
            repo_path: 仓库根目录路径
        """
        self.repo_path = Path(repo_path)

    def validate(self, diff_text: str) -> ValidationResult:
        """
        完整验证流程：格式 → 上下文 → apply。

        Args:
            diff_text: unified diff 文本

        Returns:
            ValidationResult
        """
        # Step 1: 格式验证
        format_result = self.validate_format(diff_text)
        if not format_result.valid:
            return format_result

        # Step 2: 上下文行匹配验证
        context_result = self.validate_context(diff_text)
        if not context_result.valid:
            # 尝试修复行号偏移
            repaired = self.repair_line_offsets(diff_text)
            if repaired:
                re_check = self.validate_context(repaired)
                if re_check.valid:
                    logger.info("diff repaired successfully via line offset adjustment")
                    return ValidationResult(
                        valid=True,
                        message="diff 行号已自动修正，验证通过",
                        details=context_result.details + ["已自动修复行号偏移"],
                        repaired_diff=repaired,
                    )
            return context_result

        # Step 3: git apply --check（如果在 git 仓库内）
        apply_result = self.validate_git_apply(diff_text)
        return apply_result

    # ── 格式验证 ──

    def validate_format(self, diff_text: str) -> ValidationResult:
        """检查 diff 是否符合 unified diff 基本语法。"""
        issues: list[str] = []

        if not diff_text.strip():
            return ValidationResult(False, "diff 内容为空", ["未收到任何代码变更"])

        lines = diff_text.splitlines()

        has_minus = any(line.startswith("-") for line in lines)
        has_plus = any(line.startswith("+") for line in lines)

        if not has_minus and not has_plus:
            issues.append("diff 中没有任何变更行（没有以 + 或 - 开头的行）")

        # 检查是否有 hunk header 或 --- / +++ header
        has_hunk = any(line.startswith("@@") for line in lines)
        has_file_header = any(line.startswith("---") or line.startswith("+++") for line in lines)

        if not has_hunk and not has_file_header:
            # 可能是简单的 -/+ 格式（没有完整的 unified diff header）
            # 我们仍然接受它，但标记为 "simple format"
            if has_minus or has_plus:
                issues.append("缺少 @@ hunk header，这是简化格式的 diff")
            else:
                return ValidationResult(False, "不是有效的 unified diff 格式", issues)

        if issues:
            return ValidationResult(True, "格式基本正确，有以下注意事项", issues)

        return ValidationResult(True, "格式验证通过")

    # ── 上下文行验证 ──

    def validate_context(self, diff_text: str) -> ValidationResult:
        """检查 diff 中的上下文行是否与源文件实际内容匹配。"""
        file_diffs = self.parse_unified_diff(diff_text)
        issues: list[str] = []

        for fd in file_diffs:
            # 确定文件路径
            file_path = fd.new_path if fd.new_path != "/dev/null" else fd.old_path
            # 去掉 a/ 或 b/ 前缀
            clean_path = re.sub(r"^[ab]/", "", file_path)
            full_path = self.repo_path / clean_path

            if not full_path.exists():
                # 新文件情况 — 只有 + 行，无需验证上下文
                if all(
                    line.startswith("+") or line.startswith("@@") or line.strip() == ""
                    for hunk in fd.hunks
                    for line in hunk.lines
                ):
                    continue
                issues.append(f"文件不存在: {clean_path}")
                continue

            try:
                file_lines = full_path.read_text(encoding="utf-8").splitlines()
            except UnicodeDecodeError:
                issues.append(f"文件编码不支持（非 UTF-8）: {clean_path}")
                continue

            for hunk in fd.hunks:
                # 验证上下文行和删除行是否与文件内容匹配
                file_line_idx = hunk.old_start - 1  # diff 行号从 1 开始
                for diff_line in hunk.lines:
                    if diff_line.startswith("+"):
                        continue  # 新增行，无需匹配
                    # 上下文行（空格开头）或删除行（-开头）
                    expected_content = diff_line[1:]  # 去掉前缀
                    if file_line_idx < 0 or file_line_idx >= len(file_lines):
                        issues.append(
                            f"{clean_path}: 行号 {file_line_idx + 1} 超出文件范围"
                            f"（文件共 {len(file_lines)} 行）"
                        )
                        file_line_idx += 1
                        continue

                    actual_content = file_lines[file_line_idx]
                    if expected_content.rstrip() != actual_content.rstrip():
                        issues.append(
                            f"{clean_path} L{file_line_idx + 1}: "
                            f"diff 中为 '{expected_content.strip()[:50]}' "
                            f"但文件中为 '{actual_content.strip()[:50]}'"
                        )
                    file_line_idx += 1

        if issues:
            return ValidationResult(
                False,
                f"上下文行与源文件不匹配（{len(issues)} 处差异）",
                issues,
            )

        return ValidationResult(True, "上下文行匹配验证通过")

    # ── git apply 验证 ──

    def validate_git_apply(self, diff_text: str) -> ValidationResult:
        """用 git apply --check 验证 diff 是否可应用。"""
        # 检查是否在 git 仓库中
        git_dir = self.repo_path / ".git"
        if not git_dir.exists():
            return ValidationResult(
                True,
                "非 git 仓库，跳过 git apply 检查（上下文验证已通过）",
            )

        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".patch",
                delete=False,
                encoding="utf-8",
            ) as f:
                f.write(diff_text)
                patch_path = f.name

            result = subprocess.run(
                ["git", "apply", "--check", "--verbose", patch_path],
                cwd=str(self.repo_path),
                capture_output=True,
                text=True,
                timeout=10,
            )

            os.unlink(patch_path)

            if result.returncode == 0:
                return ValidationResult(True, "git apply --check 验证通过")
            else:
                stderr = result.stderr.strip()
                return ValidationResult(
                    False,
                    "git apply --check 失败",
                    [stderr] if stderr else ["git apply 返回非零状态码"],
                )

        except subprocess.TimeoutExpired:
            return ValidationResult(
                False, "git apply 超时", ["验证超时（10秒）"]
            )
        except FileNotFoundError:
            return ValidationResult(
                True,
                "git 命令不可用，跳过 git apply 检查（上下文验证已通过）",
            )
        except Exception as e:
            return ValidationResult(
                False, f"git apply 验证异常: {e}", [str(e)]
            )

    # ── Diff 解析 ──

    def parse_unified_diff(self, diff_text: str) -> list[FileDiff]:
        """将 unified diff 文本解析为结构化的 FileDiff 列表。"""
        file_diffs: list[FileDiff] = []
        lines = diff_text.splitlines()
        i = 0

        while i < len(lines):
            # 查找文件头
            if lines[i].startswith("--- "):
                old_path = lines[i][4:].strip()
                if i + 1 < len(lines) and lines[i + 1].startswith("+++ "):
                    new_path = lines[i + 1][4:].strip()
                    i += 2
                    fd = FileDiff(old_path=old_path, new_path=new_path)

                    # 读取所有 hunks
                    while i < len(lines) and not lines[i].startswith("--- "):
                        if lines[i].startswith("@@"):
                            hunk = self._parse_hunk_header(lines[i])
                            if hunk:
                                i += 1
                                # 收集 hunk 行
                                while i < len(lines):
                                    line = lines[i]
                                    if (
                                        line.startswith("@@")
                                        or line.startswith("--- ")
                                        or line.startswith("diff --git")
                                    ):
                                        break
                                    hunk.lines.append(line)
                                    i += 1
                                fd.hunks.append(hunk)
                            else:
                                i += 1
                        else:
                            i += 1

                    file_diffs.append(fd)
                    continue

            # 也处理 diff --git 格式
            if lines[i].startswith("diff --git"):
                match = re.match(r"diff --git a/(.+) b/(.+)", lines[i])
                if match:
                    old_path = "a/" + match.group(1)
                    new_path = "b/" + match.group(2)
                    i += 1
                    # 跳过 index 行等
                    while i < len(lines) and not (
                        lines[i].startswith("--- ") or lines[i].startswith("@@")
                    ):
                        i += 1
                    # 如果有 --- +++ header
                    if i < len(lines) and lines[i].startswith("--- "):
                        old_path = lines[i][4:].strip()
                        i += 1
                    if i < len(lines) and lines[i].startswith("+++ "):
                        new_path = lines[i][4:].strip()
                        i += 1

                    fd = FileDiff(old_path=old_path, new_path=new_path)
                    while i < len(lines) and not (
                        lines[i].startswith("diff --git") or lines[i].startswith("--- ")
                    ):
                        if lines[i].startswith("@@"):
                            hunk = self._parse_hunk_header(lines[i])
                            if hunk:
                                i += 1
                                while i < len(lines):
                                    line = lines[i]
                                    if (
                                        line.startswith("@@")
                                        or line.startswith("diff --git")
                                        or line.startswith("--- ")
                                    ):
                                        break
                                    hunk.lines.append(line)
                                    i += 1
                                fd.hunks.append(hunk)
                            else:
                                i += 1
                        else:
                            i += 1
                    file_diffs.append(fd)
                    continue

            i += 1

        return file_diffs

    def _parse_hunk_header(self, line: str) -> DiffHunk | None:
        """解析 @@ -old_start,old_count +new_start,new_count @@ 行。"""
        m = re.match(
            r"@@\s*-(\d+)(?:,(\d+))?\s*\+(\d+)(?:,(\d+))?\s*@@",
            line,
        )
        if not m:
            return None
        return DiffHunk(
            old_start=int(m.group(1)),
            old_count=int(m.group(2)) if m.group(2) else 1,
            new_start=int(m.group(3)),
            new_count=int(m.group(4)) if m.group(4) else 1,
            lines=[],
        )

    # ── Diff 修复 ──

    def repair_line_offsets(self, diff_text: str) -> str | None:
        """
        尝试修复 diff 中的行号偏移。

        当 LLM 生成的 diff 上下文行内容正确但行号有偏移时，
        在源文件中搜索上下文行的实际位置，重新计算行号。

        Returns:
            修复后的 diff 文本，或 None 如果无法修复
        """
        file_diffs = self.parse_unified_diff(diff_text)
        if not file_diffs:
            return None

        repaired_lines: list[str] = []
        any_repair = False

        for fd in file_diffs:
            file_path = fd.new_path if fd.new_path != "/dev/null" else fd.old_path
            clean_path = re.sub(r"^[ab]/", "", file_path)
            full_path = self.repo_path / clean_path

            if not full_path.exists():
                continue

            try:
                file_lines = full_path.read_text(encoding="utf-8").splitlines()
            except Exception:
                continue

            repaired_lines.append(f"--- a/{clean_path}")
            repaired_lines.append(f"+++ b/{clean_path}")

            for hunk in fd.hunks:
                # 提取上下文行和删除行（用来搜索实际位置）
                context_lines = []
                for diff_line in hunk.lines:
                    if diff_line.startswith(" ") or diff_line.startswith("-"):
                        context_lines.append(diff_line[1:])

                if not context_lines:
                    # 纯新增 hunk，行号不需要修复
                    header = f"@@ -{hunk.old_start},{hunk.old_count} +{hunk.new_start},{hunk.new_count} @@"
                    repaired_lines.append(header)
                    repaired_lines.extend(hunk.lines)
                    continue

                # 在源文件中查找这些上下文行的实际起始位置
                actual_start = self._find_context_in_file(
                    file_lines, context_lines, hunk.old_start - 1
                )

                if actual_start is None:
                    # 无法找到匹配位置，放弃修复
                    return None

                if actual_start != hunk.old_start - 1:
                    any_repair = True
                    offset = actual_start - (hunk.old_start - 1)
                    new_old_start = hunk.old_start + offset
                    new_new_start = hunk.new_start + offset
                else:
                    new_old_start = hunk.old_start
                    new_new_start = hunk.new_start

                header = f"@@ -{new_old_start},{hunk.old_count} +{new_new_start},{hunk.new_count} @@"
                repaired_lines.append(header)
                repaired_lines.extend(hunk.lines)

        if not any_repair:
            return None

        return "\n".join(repaired_lines) + "\n"

    def _find_context_in_file(
        self,
        file_lines: list[str],
        context_lines: list[str],
        hint_start: int,
    ) -> int | None:
        """
        在文件中查找上下文行序列的实际位置。

        先在 hint_start 附近搜索（±20行），找不到再全文搜索。

        Returns:
            找到的起始行索引（0-based），或 None
        """
        if not context_lines:
            return hint_start

        first_context = context_lines[0].rstrip()

        # 搜索窗口：先近后远
        search_ranges = [
            range(max(0, hint_start - 20), min(len(file_lines), hint_start + 20)),
            range(0, len(file_lines)),
        ]

        for search_range in search_ranges:
            for start_idx in search_range:
                if start_idx + len(context_lines) > len(file_lines):
                    continue

                if file_lines[start_idx].rstrip() != first_context:
                    continue

                # 检查后续行是否全部匹配
                all_match = True
                for j, ctx_line in enumerate(context_lines):
                    if file_lines[start_idx + j].rstrip() != ctx_line.rstrip():
                        all_match = False
                        break

                if all_match:
                    return start_idx

        return None


# ───────────────────────────────────────────
# 便捷函数
# ───────────────────────────────────────────

def assemble_full_diff(diff_blocks: list[dict]) -> str:
    """
    将多个 diff block 组装为一个完整的 unified diff 文件。

    Args:
        diff_blocks: 每个 block 包含 {file, diff_content}

    Returns:
        可直接 git apply 的完整 diff 文本
    """
    parts: list[str] = []

    for block in diff_blocks:
        file_path = block.get("file", "")
        content = block.get("diff_content", "")

        if not content.strip():
            continue

        # 如果 diff 内容没有文件头，添加
        if not content.startswith("--- ") and not content.startswith("diff --git"):
            header = f"--- a/{file_path}\n+++ b/{file_path}\n"

            # 如果也没有 @@ header，尝试从 +/- 行生成
            if not any(line.startswith("@@") for line in content.splitlines()):
                content = _add_hunk_header(content)

            parts.append(header + content)
        else:
            parts.append(content)

    return "\n".join(parts) + "\n" if parts else ""


def _add_hunk_header(simple_diff: str) -> str:
    """为只有 +/- 行的简单 diff 添加 @@ hunk header。"""
    lines = simple_diff.splitlines()
    old_count = sum(1 for l in lines if l.startswith("-") or l.startswith(" "))
    new_count = sum(1 for l in lines if l.startswith("+") or l.startswith(" "))
    header = f"@@ -1,{old_count} +1,{new_count} @@"
    return header + "\n" + simple_diff


def apply_diff_in_memory(
    file_content: str, diff_text: str
) -> tuple[str, bool]:
    """
    在内存中应用 diff，返回修改后的文件内容。

    仅支持单文件 diff。用于预览变更效果。

    Args:
        file_content: 原始文件内容
        diff_text: unified diff 文本

    Returns:
        (修改后的内容, 是否成功)
    """
    lines = file_content.splitlines()
    diff_lines = diff_text.splitlines()

    # 提取 hunks
    hunks: list[tuple[int, list[str]]] = []  # (old_start, hunk_lines)
    i = 0
    while i < len(diff_lines):
        m = re.match(r"@@\s*-(\d+)", diff_lines[i])
        if m:
            old_start = int(m.group(1)) - 1  # 转为 0-based
            i += 1
            hunk_lines: list[str] = []
            while i < len(diff_lines):
                line = diff_lines[i]
                if line.startswith("@@") or line.startswith("--- ") or line.startswith("+++ "):
                    break
                hunk_lines.append(line)
                i += 1
            hunks.append((old_start, hunk_lines))
        else:
            i += 1

    if not hunks:
        return file_content, False

    # 从后往前应用 hunks（避免行号偏移）
    result_lines = list(lines)
    for old_start, hunk_lines in reversed(hunks):
        # 计算要删除的旧行和要插入的新行
        remove_count = 0
        new_lines: list[str] = []
        for hl in hunk_lines:
            if hl.startswith("-"):
                remove_count += 1
            elif hl.startswith("+"):
                new_lines.append(hl[1:])
            elif hl.startswith(" "):
                remove_count += 1
                new_lines.append(hl[1:])

        # 替换
        result_lines[old_start: old_start + remove_count] = new_lines

    return "\n".join(result_lines), True
