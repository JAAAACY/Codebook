"""regex_extractor — 正则表达式 fallback 提取器。

当 tree-sitter 不可用时，用正则匹配提取函数、类、import 和调用信息。
精度低于 tree-sitter，但保证系统不崩溃。

M1 里程碑核心交付物。
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from enum import Enum

from src.parsers.ast_parser import (
    CallInfo,
    ClassInfo,
    FunctionInfo,
    ImportInfo,
    ParseResult,
)

# ── 解析方式枚举 ─────────────────────────────────────────


class ParseMethod(str, Enum):
    """解析方式标识。"""
    NATIVE = "native"       # Python ast 原生解析（M2）
    FULL = "full"           # tree-sitter 完整解析
    PARTIAL = "partial"     # 正则 fallback（有语言专用提取器）
    BASIC = "basic"         # 通用正则（仅行首关键字匹配）
    FAILED = "failed"       # 解析失败


# ── 基类 ─────────────────────────────────────────────────


class BaseRegexExtractor(ABC):
    """正则提取器抽象基类。

    所有语言专用提取器继承此类，实现四个 extract 方法。
    输出统一为 ast_parser 的数据类，下游零改动。
    """

    # 子类可覆盖，表示该提取器的预期可信度
    confidence: float = 0.6

    @abstractmethod
    def extract_functions(self, source: str, lines: list[str]) -> list[FunctionInfo]:
        """提取函数/方法定义。"""

    @abstractmethod
    def extract_classes(self, source: str, lines: list[str]) -> list[ClassInfo]:
        """提取类/结构体定义。"""

    @abstractmethod
    def extract_imports(self, source: str, lines: list[str]) -> list[ImportInfo]:
        """提取 import/require/use 语句。"""

    def extract_calls(self, source: str, lines: list[str]) -> list[CallInfo]:
        """提取函数调用（可选，默认返回空列表）。

        正则提取调用关系精度较低，大多数场景下返回空即可。
        """
        return []

    def extract_all(self, source: str, file_path: str, language: str) -> ParseResult:
        """一次性提取所有信息，返回 ParseResult。"""
        lines = source.splitlines()
        return ParseResult(
            file_path=file_path,
            language=language,
            classes=self.extract_classes(source, lines),
            functions=self.extract_functions(source, lines),
            imports=self.extract_imports(source, lines),
            calls=self.extract_calls(source, lines),
            line_count=len(lines),
            parse_errors=[],
            parse_method=ParseMethod.PARTIAL.value,
            parse_confidence=self.confidence,
        )


# ── 辅助工具 ─────────────────────────────────────────────


def _find_brace_end(lines: list[str], start_line: int) -> int:
    """从 start_line 开始，用花括号计数找到块的结束行（1-indexed 返回）。"""
    depth = 0
    found_open = False
    for i in range(start_line, len(lines)):
        line = lines[i]
        # 忽略字符串和注释中的花括号（简化处理）
        for ch in line:
            if ch == '{':
                depth += 1
                found_open = True
            elif ch == '}':
                depth -= 1
                if found_open and depth <= 0:
                    return i + 1  # 1-indexed
    return len(lines)  # 到文件末尾


def _find_indent_end(lines: list[str], start_line: int, base_indent: int) -> int:
    """从 start_line 的下一行开始，找缩进块结束位置。

    Args:
        lines: 所有行（0-indexed 列表）
        start_line: 块起始行（0-indexed）
        base_indent: 块定义行的缩进长度

    Returns:
        块最后一行的行号（1-indexed）
    """
    last_content_line = start_line  # 0-indexed
    for i in range(start_line + 1, len(lines)):
        line = lines[i]
        stripped = line.lstrip()
        if not stripped or stripped.startswith('#'):
            continue  # 跳过空行和注释
        current_indent = len(line) - len(stripped)
        if current_indent <= base_indent:
            return last_content_line + 1  # 1-indexed
        last_content_line = i
    return last_content_line + 1  # 1-indexed


# ── Python 提取器 ─────────────────────────────────────────


class PythonRegexExtractor(BaseRegexExtractor):
    """Python 语言正则提取器。"""

    confidence = 0.8

    _FUNC_RE = re.compile(
        r'^([^\S\n]*)(async\s+)?def\s+(\w+)\s*\(', re.MULTILINE
    )
    _CLASS_RE = re.compile(
        r'^([^\S\n]*)class\s+(\w+)\s*(?:\(([^)]*)\))?\s*:', re.MULTILINE
    )
    _IMPORT_RE = re.compile(
        r'^(from\s+([\w.]+)\s+import\s+(.+)|import\s+(.+))', re.MULTILINE
    )
    _CALL_RE = re.compile(r'(\w+)\s*\(')

    def extract_functions(self, source: str, lines: list[str]) -> list[FunctionInfo]:
        functions = []
        for m in self._FUNC_RE.finditer(source):
            indent = len(m.group(1))
            name = m.group(3)
            line_start = source[:m.start()].count('\n') + 1
            line_end = _find_indent_end(lines, line_start - 1, indent)

            # 提取参数（简化：取括号内容）
            params = self._extract_params(source, m.end() - 1)

            # 判断是否是方法（缩进 > 0 且在 class 内）
            is_method = indent > 0

            functions.append(FunctionInfo(
                name=name,
                params=params,
                line_start=line_start,
                line_end=line_end,
                is_method=is_method,
            ))
        return functions

    def extract_classes(self, source: str, lines: list[str]) -> list[ClassInfo]:
        classes = []
        for m in self._CLASS_RE.finditer(source):
            indent = len(m.group(1))
            name = m.group(2)
            parent = m.group(3).strip() if m.group(3) else None
            line_start = source[:m.start()].count('\n') + 1
            line_end = _find_indent_end(lines, line_start - 1, indent)

            # 收集方法名（line_start/line_end 是 1-indexed，lines 是 0-indexed）
            methods = []
            class_body = '\n'.join(lines[line_start - 1:line_end])
            for fm in re.finditer(r'^\s+(?:async\s+)?def\s+(\w+)\s*\(', class_body, re.MULTILINE):
                methods.append(fm.group(1))

            classes.append(ClassInfo(
                name=name,
                methods=methods,
                parent_class=parent,
                line_start=line_start,
                line_end=line_end,
            ))
        return classes

    def extract_imports(self, source: str, lines: list[str]) -> list[ImportInfo]:
        imports = []
        for m in self._IMPORT_RE.finditer(source):
            line = source[:m.start()].count('\n') + 1
            if m.group(2):  # from X import Y
                module = m.group(2)
                names = [n.strip() for n in m.group(3).split(',')]
                is_relative = module.startswith('.')
            else:  # import X
                raw = m.group(4).strip()
                parts = [p.strip() for p in raw.split(',')]
                module = parts[0].split(' as ')[0].strip()
                names = []
                is_relative = False
            imports.append(ImportInfo(
                module=module, names=names, is_relative=is_relative, line=line
            ))
        return imports

    def extract_calls(self, source: str, lines: list[str]) -> list[CallInfo]:
        calls = []
        keywords = {'if', 'for', 'while', 'with', 'except', 'elif', 'return',
                     'yield', 'assert', 'print', 'def', 'class', 'import', 'from',
                     'and', 'or', 'not', 'in', 'is', 'lambda', 'raise', 'del'}
        for m in self._CALL_RE.finditer(source):
            name = m.group(1)
            if name in keywords or name.startswith('_'):
                continue
            line = source[:m.start()].count('\n') + 1
            calls.append(CallInfo(caller_func="<module>", callee_name=name, line=line))
        return calls

    @staticmethod
    def _extract_params(source: str, paren_start: int) -> list[str]:
        """从左括号位置提取参数列表。"""
        depth = 0
        buf = []
        for i in range(paren_start, min(paren_start + 500, len(source))):
            ch = source[i]
            if ch == '(':
                depth += 1
                if depth == 1:
                    continue
            elif ch == ')':
                depth -= 1
                if depth == 0:
                    break
            if depth == 1:
                buf.append(ch)
        content = ''.join(buf).strip()
        if not content:
            return []
        params = []
        for p in content.split(','):
            p = p.strip()
            if p and p != 'self' and p != 'cls':
                name = p.split(':')[0].split('=')[0].strip()
                if name:
                    params.append(name)
        return params


# ── TypeScript / JavaScript 提取器 ────────────────────────


class TSRegexExtractor(BaseRegexExtractor):
    """TypeScript / JavaScript 正则提取器。"""

    confidence = 0.7

    _FUNC_RE = re.compile(
        r'^([^\S\n]*)(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*[(<]',
        re.MULTILINE
    )
    _ARROW_RE = re.compile(
        r'^([^\S\n]*)(?:export\s+)?(?:const|let|var)\s+(\w+)\s*(?::\s*\S+\s*)?=\s*(?:async\s+)?\(?',
        re.MULTILINE
    )
    _CLASS_RE = re.compile(
        r'^([^\S\n]*)(?:export\s+)?(?:abstract\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?',
        re.MULTILINE
    )
    _IMPORT_RE = re.compile(
        r"^import\s+(?:(?:type\s+)?(?:\{[^}]*\}|[\w*]+(?:\s+as\s+\w+)?)\s+from\s+)?['\"]([^'\"]+)['\"]",
        re.MULTILINE
    )
    _METHOD_RE = re.compile(
        r'^\s+(?:async\s+)?(\w+)\s*\([^)]*\)\s*(?::\s*\S+\s*)?\{',
        re.MULTILINE
    )

    def extract_functions(self, source: str, lines: list[str]) -> list[FunctionInfo]:
        functions = []
        seen_lines = set()

        # 普通函数
        for m in self._FUNC_RE.finditer(source):
            line_start = source[:m.start()].count('\n') + 1
            if line_start in seen_lines:
                continue
            seen_lines.add(line_start)
            name = m.group(2)
            line_end = _find_brace_end(lines, line_start - 1)
            functions.append(FunctionInfo(
                name=name, line_start=line_start, line_end=line_end
            ))

        # 箭头函数 / const 函数表达式
        for m in self._ARROW_RE.finditer(source):
            line_start = source[:m.start()].count('\n') + 1
            if line_start in seen_lines:
                continue
            seen_lines.add(line_start)
            name = m.group(2)
            # 检查后续是否有 => 或 function（在同行或下几行内）
            after = source[m.end():m.end()+200]
            if '=>' not in after and 'function' not in after:
                continue
            line_end = _find_brace_end(lines, line_start - 1)
            functions.append(FunctionInfo(
                name=name, line_start=line_start, line_end=line_end
            ))

        return functions

    def extract_classes(self, source: str, lines: list[str]) -> list[ClassInfo]:
        classes = []
        for m in self._CLASS_RE.finditer(source):
            name = m.group(2)
            parent = m.group(3)
            line_start = source[:m.start()].count('\n') + 1
            line_end = _find_brace_end(lines, line_start - 1)

            methods = []
            class_body = '\n'.join(lines[line_start:line_end])
            for fm in self._METHOD_RE.finditer(class_body):
                mname = fm.group(1)
                if mname not in ('constructor', 'if', 'for', 'while', 'switch'):
                    methods.append(mname)

            classes.append(ClassInfo(
                name=name, methods=methods, parent_class=parent,
                line_start=line_start, line_end=line_end,
            ))
        return classes

    def extract_imports(self, source: str, lines: list[str]) -> list[ImportInfo]:
        imports = []
        for m in self._IMPORT_RE.finditer(source):
            line = source[:m.start()].count('\n') + 1
            module = m.group(1)
            imports.append(ImportInfo(module=module, line=line))
        # require() 调用
        for m in re.finditer(r"require\(['\"]([^'\"]+)['\"]\)", source):
            line = source[:m.start()].count('\n') + 1
            imports.append(ImportInfo(module=m.group(1), line=line))
        return imports


# ── Go 提取器 ─────────────────────────────────────────────


class GoRegexExtractor(BaseRegexExtractor):
    """Go 语言正则提取器。"""

    confidence = 0.7

    _FUNC_RE = re.compile(
        r'^func\s+(?:\(\s*\w+\s+\*?(\w+)\s*\)\s+)?(\w+)\s*\(',
        re.MULTILINE
    )
    _TYPE_RE = re.compile(
        r'^type\s+(\w+)\s+struct\s*\{', re.MULTILINE
    )
    _INTERFACE_RE = re.compile(
        r'^type\s+(\w+)\s+interface\s*\{', re.MULTILINE
    )
    _IMPORT_RE = re.compile(
        r'^import\s+(?:\(\s*([\s\S]*?)\s*\)|"([^"]+)")',
        re.MULTILINE
    )

    def extract_functions(self, source: str, lines: list[str]) -> list[FunctionInfo]:
        functions = []
        for m in self._FUNC_RE.finditer(source):
            receiver = m.group(1)
            name = m.group(2)
            line_start = source[:m.start()].count('\n') + 1
            line_end = _find_brace_end(lines, line_start - 1)
            functions.append(FunctionInfo(
                name=name, line_start=line_start, line_end=line_end,
                is_method=receiver is not None,
                parent_class=receiver,
            ))
        return functions

    def extract_classes(self, source: str, lines: list[str]) -> list[ClassInfo]:
        classes = []
        for pattern in (self._TYPE_RE, self._INTERFACE_RE):
            for m in pattern.finditer(source):
                name = m.group(1)
                line_start = source[:m.start()].count('\n') + 1
                line_end = _find_brace_end(lines, line_start - 1)
                classes.append(ClassInfo(
                    name=name, line_start=line_start, line_end=line_end
                ))
        return classes

    def extract_imports(self, source: str, lines: list[str]) -> list[ImportInfo]:
        imports = []
        for m in self._IMPORT_RE.finditer(source):
            line = source[:m.start()].count('\n') + 1
            if m.group(1):  # 分组 import
                for pkg in re.findall(r'"([^"]+)"', m.group(1)):
                    imports.append(ImportInfo(module=pkg, line=line))
            elif m.group(2):  # 单行 import
                imports.append(ImportInfo(module=m.group(2), line=line))
        return imports


# ── Rust 提取器 ───────────────────────────────────────────


class RustRegexExtractor(BaseRegexExtractor):
    """Rust 语言正则提取器。"""

    confidence = 0.65

    _FUNC_RE = re.compile(
        r'^([^\S\n]*)(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?(?:unsafe\s+)?fn\s+(\w+)',
        re.MULTILINE
    )
    _STRUCT_RE = re.compile(
        r'^(?:pub(?:\([^)]*\))?\s+)?(?:struct|enum|trait)\s+(\w+)',
        re.MULTILINE
    )
    _IMPL_RE = re.compile(
        r'^impl(?:<[^>]*>)?\s+(?:(\w+)\s+for\s+)?(\w+)',
        re.MULTILINE
    )
    _USE_RE = re.compile(r'^use\s+(.+);', re.MULTILINE)
    _MOD_RE = re.compile(r'^(?:pub\s+)?mod\s+(\w+)\s*;', re.MULTILINE)

    def extract_functions(self, source: str, lines: list[str]) -> list[FunctionInfo]:
        functions = []
        for m in self._FUNC_RE.finditer(source):
            indent = len(m.group(1))
            name = m.group(2)
            line_start = source[:m.start()].count('\n') + 1
            line_end = _find_brace_end(lines, line_start - 1)
            functions.append(FunctionInfo(
                name=name, line_start=line_start, line_end=line_end,
                is_method=indent > 0,
            ))
        return functions

    def extract_classes(self, source: str, lines: list[str]) -> list[ClassInfo]:
        classes = []
        for m in self._STRUCT_RE.finditer(source):
            name = m.group(1)
            line_start = source[:m.start()].count('\n') + 1
            line_end = _find_brace_end(lines, line_start - 1)
            classes.append(ClassInfo(
                name=name, line_start=line_start, line_end=line_end
            ))
        return classes

    def extract_imports(self, source: str, lines: list[str]) -> list[ImportInfo]:
        imports = []
        for m in self._USE_RE.finditer(source):
            line = source[:m.start()].count('\n') + 1
            imports.append(ImportInfo(module=m.group(1).strip(), line=line))
        for m in self._MOD_RE.finditer(source):
            line = source[:m.start()].count('\n') + 1
            imports.append(ImportInfo(module=m.group(1), line=line))
        return imports


# ── Java 提取器 ───────────────────────────────────────────


class JavaRegexExtractor(BaseRegexExtractor):
    """Java 语言正则提取器。"""

    confidence = 0.65

    _CLASS_RE = re.compile(
        r'^([^\S\n]*)(?:public|private|protected)?\s*(?:abstract\s+)?(?:final\s+)?(?:class|interface|enum)\s+(\w+)(?:\s+extends\s+(\w+))?',
        re.MULTILINE
    )
    _FUNC_RE = re.compile(
        r'^([^\S\n]*)(?:public|private|protected)?\s*(?:static\s+)?(?:final\s+)?(?:abstract\s+)?(?:synchronized\s+)?(?:\w+(?:<[^>]*>)?(?:\[\])*\s+)(\w+)\s*\(',
        re.MULTILINE
    )
    _IMPORT_RE = re.compile(r'^import\s+(?:static\s+)?([^;]+);', re.MULTILINE)

    def extract_functions(self, source: str, lines: list[str]) -> list[FunctionInfo]:
        functions = []
        skip_names = {'if', 'for', 'while', 'switch', 'catch', 'return', 'new', 'class', 'interface'}
        for m in self._FUNC_RE.finditer(source):
            name = m.group(2)
            if name in skip_names:
                continue
            line_start = source[:m.start()].count('\n') + 1
            line_end = _find_brace_end(lines, line_start - 1)
            indent = len(m.group(1))
            functions.append(FunctionInfo(
                name=name, line_start=line_start, line_end=line_end,
                is_method=indent > 0,
            ))
        return functions

    def extract_classes(self, source: str, lines: list[str]) -> list[ClassInfo]:
        classes = []
        for m in self._CLASS_RE.finditer(source):
            name = m.group(2)
            parent = m.group(3)
            line_start = source[:m.start()].count('\n') + 1
            line_end = _find_brace_end(lines, line_start - 1)
            classes.append(ClassInfo(
                name=name, parent_class=parent,
                line_start=line_start, line_end=line_end
            ))
        return classes

    def extract_imports(self, source: str, lines: list[str]) -> list[ImportInfo]:
        imports = []
        for m in self._IMPORT_RE.finditer(source):
            line = source[:m.start()].count('\n') + 1
            imports.append(ImportInfo(module=m.group(1).strip(), line=line))
        return imports


# ── 通用 Fallback 提取器 ─────────────────────────────────


class GenericRegexExtractor(BaseRegexExtractor):
    """通用正则提取器，覆盖所有其他语言。

    只做最基础的行首关键字匹配，精度最低但覆盖面最广。
    """

    confidence = 0.5

    # 覆盖绝大多数语言的函数定义关键字
    _FUNC_KEYWORDS = (
        r'(?:pub(?:\([^)]*\))?\s+)?'
        r'(?:export\s+)?'
        r'(?:(?:private|protected|internal|public|open|fileprivate)\s+)?'
        r'(?:async\s+)?'
        r'(?:static\s+)?'
        r'(?:def|fn|func|function|fun|sub|proc|method|subroutine)\s+(\w+)\s*[\(\[]'
    )
    _FUNC_RE = re.compile(r'^([^\S\n]*)' + _FUNC_KEYWORDS, re.MULTILINE)

    _CLASS_KEYWORDS = (
        r'(?:pub(?:\([^)]*\))?\s+)?'
        r'(?:export\s+)?'
        r'(?:abstract\s+)?'
        r'(?:class|struct|interface|trait|enum|module|object|type|protocol)\s+(\w+)'
    )
    _CLASS_RE = re.compile(r'^([^\S\n]*)' + _CLASS_KEYWORDS, re.MULTILINE)

    _IMPORT_RE = re.compile(
        r'^(?:import|include|require|use|using|from\s+\S+\s+import)\s+(.+)',
        re.MULTILINE
    )

    def extract_functions(self, source: str, lines: list[str]) -> list[FunctionInfo]:
        functions = []
        for m in self._FUNC_RE.finditer(source):
            name = m.group(2)
            line_start = source[:m.start()].count('\n') + 1
            # 尝试花括号，不行就用缩进
            rest = '\n'.join(lines[line_start - 1:])
            if '{' in lines[line_start - 1] or (line_start < len(lines) and '{' in lines[line_start]):
                line_end = _find_brace_end(lines, line_start - 1)
            else:
                indent = len(m.group(1))
                line_end = _find_indent_end(lines, line_start - 1, indent)
            functions.append(FunctionInfo(
                name=name, line_start=line_start, line_end=line_end
            ))
        return functions

    def extract_classes(self, source: str, lines: list[str]) -> list[ClassInfo]:
        classes = []
        for m in self._CLASS_RE.finditer(source):
            name = m.group(2)
            line_start = source[:m.start()].count('\n') + 1
            if '{' in lines[line_start - 1] or (line_start < len(lines) and '{' in lines[line_start]):
                line_end = _find_brace_end(lines, line_start - 1)
            else:
                indent = len(m.group(1))
                line_end = _find_indent_end(lines, line_start - 1, indent)
            classes.append(ClassInfo(
                name=name, line_start=line_start, line_end=line_end
            ))
        return classes

    def extract_imports(self, source: str, lines: list[str]) -> list[ImportInfo]:
        imports = []
        for m in self._IMPORT_RE.finditer(source):
            line = source[:m.start()].count('\n') + 1
            raw = m.group(1).strip().rstrip(';')
            imports.append(ImportInfo(module=raw, line=line))
        return imports


# ── 提取器工厂 ────────────────────────────────────────────

# 语言 → 专用提取器映射
_EXTRACTOR_MAP: dict[str, type[BaseRegexExtractor]] = {
    "python": PythonRegexExtractor,
    "typescript": TSRegexExtractor,
    "javascript": TSRegexExtractor,
    "tsx": TSRegexExtractor,
    "go": GoRegexExtractor,
    "rust": RustRegexExtractor,
    "java": JavaRegexExtractor,
}

# 单例缓存
_extractor_cache: dict[str, BaseRegexExtractor] = {}


def get_extractor(language: str) -> BaseRegexExtractor:
    """获取指定语言的正则提取器实例。

    有专用提取器的语言使用专用提取器，其余使用通用 fallback。
    """
    if language not in _extractor_cache:
        cls = _EXTRACTOR_MAP.get(language, GenericRegexExtractor)
        _extractor_cache[language] = cls()
    return _extractor_cache[language]
