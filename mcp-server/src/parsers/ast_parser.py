"""ast_parser — 用 Tree-sitter 解析源代码文件，提取结构信息。"""

import asyncio
from dataclasses import dataclass, field

import structlog
try:
    import tree_sitter_language_pack as tree_sitter_languages
except ImportError:
    import tree_sitter_languages

from src.parsers.repo_cloner import FileInfo

logger = structlog.get_logger()

# ── 数据类 ──────────────────────────────────────────────


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
    caller_func: str  # 调用发生在哪个函数/方法内
    callee_name: str  # 被调用的函数/方法名
    line: int = 0


@dataclass
class ParseResult:
    """单个文件的解析结果。"""
    file_path: str  # 相对路径
    language: str
    classes: list[ClassInfo] = field(default_factory=list)
    functions: list[FunctionInfo] = field(default_factory=list)
    imports: list[ImportInfo] = field(default_factory=list)
    calls: list[CallInfo] = field(default_factory=list)
    line_count: int = 0
    parse_errors: list[str] = field(default_factory=list)


# ── 语言支持映射 ─────────────────────────────────────────

# Tree-sitter node types per language
LANG_CONFIG = {
    "python": {
        "function_def": ["function_definition"],
        "class_def": ["class_definition"],
        "import": ["import_statement", "import_from_statement"],
        "call": ["call"],
        "name_field": "name",
        "params_field": "parameters",
        "body_field": "body",
        "superclass_field": "superclasses",
    },
    "typescript": {
        "function_def": ["function_declaration", "method_definition", "arrow_function"],
        "class_def": ["class_declaration"],
        "import": ["import_statement"],
        "call": ["call_expression"],
        "name_field": "name",
        "params_field": "parameters",
        "body_field": "body",
        "superclass_field": "heritage",
    },
    "javascript": {
        "function_def": ["function_declaration", "method_definition", "arrow_function"],
        "class_def": ["class_declaration"],
        "import": ["import_statement"],
        "call": ["call_expression"],
        "name_field": "name",
        "params_field": "parameters",
        "body_field": "body",
        "superclass_field": "heritage",
    },
    "java": {
        "function_def": ["method_declaration", "constructor_declaration"],
        "class_def": ["class_declaration"],
        "import": ["import_declaration"],
        "call": ["method_invocation"],
        "name_field": "name",
        "params_field": "parameters",
        "body_field": "body",
        "superclass_field": "superclass",
    },
    "go": {
        "function_def": ["function_declaration", "method_declaration"],
        "class_def": ["type_declaration"],
        "import": ["import_declaration"],
        "call": ["call_expression"],
        "name_field": "name",
        "params_field": "parameters",
        "body_field": "body",
        "superclass_field": None,
    },
    "cpp": {
        "function_def": ["function_definition"],
        "class_def": ["class_specifier", "struct_specifier"],
        "import": ["preproc_include"],
        "call": ["call_expression"],
        "name_field": "declarator",
        "params_field": "parameters",
        "body_field": "body",
        "superclass_field": "base_class_clause",
    },
    "rust": {
        "function_def": ["function_item"],
        "class_def": ["struct_item", "impl_item", "enum_item"],
        "import": ["use_declaration"],
        "call": ["call_expression"],
        "name_field": "name",
        "params_field": "parameters",
        "body_field": "body",
        "superclass_field": None,
    },
    "c_sharp": {
        "function_def": ["method_declaration", "constructor_declaration"],
        "class_def": ["class_declaration"],
        "import": ["using_directive"],
        "call": ["invocation_expression"],
        "name_field": "name",
        "params_field": "parameters",
        "body_field": "body",
        "superclass_field": "base_list",
    },
}


# ── Tree-sitter 辅助 ────────────────────────────────────

def _get_node_text(node) -> str:
    """安全获取节点文本。"""
    if node is None:
        return ""
    return node.text.decode("utf-8", errors="replace")


def _find_child_by_field(node, field_name: str):
    """按 field name 查找子节点。"""
    return node.child_by_field_name(field_name)


def _find_children_by_type(node, type_name: str) -> list:
    """按 type 查找所有子节点。"""
    return [c for c in node.children if c.type == type_name]


def _walk_tree(node, callback, depth=0):
    """遍历 tree-sitter 语法树。"""
    callback(node, depth)
    for child in node.children:
        _walk_tree(child, callback, depth + 1)


def _find_enclosing_function(node, lang_config: dict) -> str:
    """从当前节点向上查找所在的函数/方法名。"""
    func_types = set(lang_config.get("function_def", []))
    current = node.parent
    while current is not None:
        if current.type in func_types:
            name_node = _find_child_by_field(current, lang_config["name_field"])
            if name_node:
                return _get_node_text(name_node)
        current = current.parent
    return "<module>"


def _extract_callee_name(call_node, language: str) -> str:
    """从 call 节点提取被调用函数名。"""
    if language == "python":
        func_node = call_node.children[0] if call_node.children else None
        if func_node:
            text = _get_node_text(func_node)
            # 只取最后的名字部分 e.g. self.method -> method
            if "." in text:
                return text.split(".")[-1]
            return text
    else:
        # 通用策略：取 function 字段或第一个子节点
        func_node = _find_child_by_field(call_node, "function")
        if func_node is None and call_node.children:
            func_node = call_node.children[0]
        if func_node:
            text = _get_node_text(func_node)
            if "." in text:
                return text.split(".")[-1]
            return text
    return "<unknown>"


# ── Python 专用提取 ─────────────────────────────────────

def _extract_python_docstring(func_node) -> str | None:
    """提取 Python 函数的 docstring。"""
    body = _find_child_by_field(func_node, "body")
    if body is None:
        return None
    for child in body.children:
        if child.type == "expression_statement":
            for sub in child.children:
                if sub.type == "string":
                    text = _get_node_text(sub)
                    # 去掉引号
                    if text.startswith(('"""', "'''")):
                        return text[3:-3].strip()
                    elif text.startswith(('"', "'")):
                        return text[1:-1].strip()
    return None


def _extract_python_params(params_node) -> list[str]:
    """提取 Python 函数参数名列表。"""
    if params_node is None:
        return []
    params = []
    for child in params_node.children:
        if child.type == "identifier":
            name = _get_node_text(child)
            if name != "self" and name != "cls":
                params.append(name)
        elif child.type in ("typed_parameter", "default_parameter", "typed_default_parameter"):
            name_node = child.children[0] if child.children else None
            if name_node:
                name = _get_node_text(name_node)
                if name != "self" and name != "cls":
                    params.append(name)
    return params


def _extract_python_imports(node) -> list[ImportInfo]:
    """提取 Python import 语句。"""
    imports = []
    if node.type == "import_statement":
        for child in node.children:
            if child.type == "dotted_name":
                imports.append(ImportInfo(
                    module=_get_node_text(child),
                    line=node.start_point[0] + 1,
                ))
    elif node.type == "import_from_statement":
        module = ""
        names = []
        is_relative = False
        for child in node.children:
            if child.type == "dotted_name":
                module = _get_node_text(child)
            elif child.type == "relative_import":
                is_relative = True
                dotted = _find_children_by_type(child, "dotted_name")
                if dotted:
                    module = _get_node_text(dotted[0])
            elif child.type == "import_prefix":
                is_relative = True
            elif child.type == "aliased_import":
                name_node = child.children[0] if child.children else None
                if name_node:
                    names.append(_get_node_text(name_node))
            elif child.type == "identifier":
                text = _get_node_text(child)
                if text not in ("from", "import"):
                    names.append(text)
        imports.append(ImportInfo(
            module=module,
            names=names,
            is_relative=is_relative,
            line=node.start_point[0] + 1,
        ))
    return imports


# ── 核心解析函数 ─────────────────────────────────────────

async def parse_file(file: FileInfo) -> ParseResult:
    """用 Tree-sitter 解析单个文件。

    提取所有 class、function、import 和函数调用。

    Args:
        file: FileInfo 对象。

    Returns:
        ParseResult 包含提取的类、函数、导入和调用列表。
    """
    result = ParseResult(
        file_path=file.path,
        language=file.language,
        line_count=file.line_count,
    )

    # 不支持的语言或配置文件
    if file.is_config or file.language not in LANG_CONFIG:
        return result

    lang_config = LANG_CONFIG[file.language]

    try:
        with open(file.abs_path, "rb") as f:
            source = f.read()
    except (OSError, UnicodeDecodeError) as e:
        result.parse_errors.append(f"Read error: {e}")
        return result

    try:
        parser = tree_sitter_languages.get_parser(file.language)
        tree = parser.parse(source)
    except Exception as e:
        result.parse_errors.append(f"Parse error: {e}")
        return result

    root = tree.root_node
    func_types = set(lang_config.get("function_def", []))
    class_types = set(lang_config.get("class_def", []))
    import_types = set(lang_config.get("import", []))
    call_types = set(lang_config.get("call", []))

    # 当前所在的 class 名（用于标记 method）
    class_stack: list[str] = []

    def visitor(node, depth):
        nonlocal class_stack

        # ── Class 定义 ──
        if node.type in class_types:
            name_node = _find_child_by_field(node, lang_config["name_field"])
            name = _get_node_text(name_node) if name_node else "<anonymous>"

            parent = None
            sc_field = lang_config.get("superclass_field")
            if sc_field:
                sc_node = _find_child_by_field(node, sc_field)
                if sc_node:
                    parent = _get_node_text(sc_node).strip("()")

            # 收集方法名（需要搜索 body 子节点内的函数定义）
            methods = []
            body_node = _find_child_by_field(node, "body")
            search_nodes = body_node.children if body_node else node.children
            for child in search_nodes:
                if child.type in func_types:
                    m_name_node = _find_child_by_field(child, lang_config["name_field"])
                    if m_name_node:
                        methods.append(_get_node_text(m_name_node))

            result.classes.append(ClassInfo(
                name=name,
                methods=methods,
                parent_class=parent,
                line_start=node.start_point[0] + 1,
                line_end=node.end_point[0] + 1,
            ))
            class_stack.append(name)

        # ── Function 定义 ──
        elif node.type in func_types:
            name_node = _find_child_by_field(node, lang_config["name_field"])
            name = _get_node_text(name_node) if name_node else "<anonymous>"

            # 参数
            params_node = _find_child_by_field(node, lang_config["params_field"])
            if file.language == "python":
                params = _extract_python_params(params_node)
            else:
                params = [_get_node_text(p) for p in (params_node.children if params_node else [])
                          if p.type not in ("(", ")", ",")]

            # Docstring (Python only)
            docstring = None
            if file.language == "python":
                docstring = _extract_python_docstring(node)

            # 判断是否是方法
            is_method = bool(class_stack) or (
                node.parent and node.parent.type in class_types
            )
            parent_class = class_stack[-1] if class_stack else None

            result.functions.append(FunctionInfo(
                name=name,
                params=params,
                line_start=node.start_point[0] + 1,
                line_end=node.end_point[0] + 1,
                docstring=docstring,
                is_method=is_method,
                parent_class=parent_class,
            ))

        # ── Import 语句 ──
        elif node.type in import_types:
            if file.language == "python":
                result.imports.extend(_extract_python_imports(node))
            else:
                result.imports.append(ImportInfo(
                    module=_get_node_text(node).strip(),
                    line=node.start_point[0] + 1,
                ))

        # ── 函数调用 ──
        elif node.type in call_types:
            caller = _find_enclosing_function(node, lang_config)
            callee = _extract_callee_name(node, file.language)
            result.calls.append(CallInfo(
                caller_func=caller,
                callee_name=callee,
                line=node.start_point[0] + 1,
            ))

    _walk_tree(root, visitor)

    # 清理 class_stack（简化实现，不做精确的范围追踪）
    logger.debug(
        "parse_file.done",
        file=file.path,
        classes=len(result.classes),
        functions=len(result.functions),
        imports=len(result.imports),
        calls=len(result.calls),
    )
    return result


async def parse_all(files: list[FileInfo]) -> list[ParseResult]:
    """并行解析所有文件。

    Args:
        files: 要解析的文件列表。

    Returns:
        每个文件的 ParseResult 列表。
    """
    tasks = [parse_file(f) for f in files if not f.is_config]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    parsed = []
    for r in results:
        if isinstance(r, Exception):
            logger.error("parse_file.exception", error=str(r))
        else:
            parsed.append(r)

    logger.info(
        "parse_all.done",
        total=len(files),
        parsed=len(parsed),
        total_functions=sum(len(r.functions) for r in parsed),
        total_classes=sum(len(r.classes) for r in parsed),
    )
    return parsed
