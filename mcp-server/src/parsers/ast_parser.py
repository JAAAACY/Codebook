"""ast_parser — 用 Tree-sitter 解析源代码文件，提取结构信息。"""

import asyncio
import os
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field

import structlog

from src.parsers.repo_cloner import FileInfo

logger = structlog.get_logger()

# ── Tree-sitter 依赖隔离（M1-6）─────────────────────────
# tree-sitter-language-pack 是核心依赖（M3-1 提升）
# 缺失时系统可启动，走正则 fallback

_tree_sitter_module = None


def _try_import_tree_sitter():
    """尝试导入 tree-sitter 包，包括用户 site-packages 路径修复。"""
    global _tree_sitter_module
    if _tree_sitter_module is not None:
        return

    # 第一次尝试：直接导入
    try:
        import tree_sitter_language_pack as mod
        _tree_sitter_module = mod
        return
    except ImportError:
        pass

    try:
        import tree_sitter_languages as mod
        _tree_sitter_module = mod
        return
    except ImportError:
        pass

    # 第二次尝试：显式添加用户 site-packages 到 sys.path
    # MCP server 进程可能缺少用户级 site-packages 路径
    import sys
    import site
    user_site = site.getusersitepackages()
    if user_site not in sys.path:
        sys.path.insert(0, user_site)
        logger.info("tree_sitter.path_fix", added_path=user_site)
        try:
            import tree_sitter_language_pack as mod
            _tree_sitter_module = mod
            return
        except ImportError:
            pass

    # 第三次尝试：搜索常见安装路径
    # MCP server 可能在容器、venv、或 Claude Desktop 拉起的隔离进程中运行，
    # sys.path 不一定覆盖 pip install --user 的目标目录。
    import glob as glob_mod
    py_ver = f"python{sys.version_info.major}.{sys.version_info.minor}"
    for pattern in [
        # 用户级 site-packages（含隐藏目录变体）
        os.path.expanduser(f"~/.local/lib/{py_ver}/site-packages"),
        os.path.expanduser("~/.local/lib/python*/site-packages"),
        # Cowork / MCP sandbox 常见路径
        f"/sessions/*/.local/lib/{py_ver}/site-packages",
        "/sessions/*/.*local/lib/python*/site-packages",
        # virtualenv / venv 常见布局
        os.path.expanduser(f"~/*/lib/{py_ver}/site-packages"),
        # pip install --target 的常见自定义路径
        os.path.expanduser("~/.codebook/lib/python*/site-packages"),
    ]:
        for path in glob_mod.glob(pattern):
            if path not in sys.path:
                sys.path.insert(0, path)
                try:
                    import tree_sitter_language_pack as mod
                    _tree_sitter_module = mod
                    logger.info("tree_sitter.found_at", path=path)
                    return
                except ImportError:
                    pass

    logger.warning("tree_sitter.unavailable",
                   msg="tree-sitter 包未安装，将使用正则 fallback")


# 启动时尝试导入
_try_import_tree_sitter()


# ── Tree-sitter 健康检测（M1-1）─────────────────────────

class TreeSitterHealthCheck:
    """tree-sitter 可用性检测，带缓存。

    启动时探测一次，之后缓存结果。
    支持按语言检测：某些语言的 grammar 可能缺失。
    """

    _CACHE_TTL = 300  # 5 分钟缓存

    # 语言名别名映射：tree-sitter-language-pack 与 tree-sitter-languages
    # 可能使用不同的语言标识符
    _LANG_ALIASES: dict[str, list[str]] = {
        "bash": ["bash", "sh", "shell"],
        "javascript": ["javascript", "js"],
        "typescript": ["typescript", "tsx"],
        "cpp": ["cpp", "c_plus_plus"],
        "csharp": ["c_sharp", "csharp"],
        "objc": ["objc", "objective_c", "objective-c"],
    }

    def __init__(self):
        self._available: dict[str, bool] = {}
        self._global_available: bool | None = None
        self._last_check: float = 0
        # 记录成功的语言名映射：internal_name -> actual_ts_name
        self._resolved_names: dict[str, str] = {}

    def _check_global(self) -> bool:
        """检测 tree-sitter 模块是否整体可用。

        如果探测失败（如缓存损坏 / checksum mismatch），
        自动清理缓存并重试一次，实现运行时自愈。
        """
        if _tree_sitter_module is None:
            # 延迟重试：进程启动时可能还没装好
            _try_import_tree_sitter()
        if _tree_sitter_module is None:
            return False
        try:
            # 用 Python parser 做探测
            parser = _tree_sitter_module.get_parser("python")
            tree = parser.parse(b"def test(): pass")
            return tree.root_node is not None
        except Exception as e:
            logger.warning("tree_sitter.probe_failed", error=str(e))

            # 自动修复：清理缓存后重试一次
            try:
                if hasattr(_tree_sitter_module, "clean_cache"):
                    _tree_sitter_module.clean_cache()
                    logger.info("tree_sitter.cache_auto_cleaned")
                    parser = _tree_sitter_module.get_parser("python")
                    tree = parser.parse(b"def test(): pass")
                    if tree.root_node is not None:
                        logger.info("tree_sitter.auto_recovered")
                        return True
            except Exception as e2:
                logger.warning("tree_sitter.auto_recover_failed", error=str(e2))

            return False

    def _try_get_parser(self, language: str):
        """尝试获取 parser，支持别名回退。

        Returns:
            parser 对象，或 None（如果所有别名都失败）
        """
        # 如果已经有解析过的名称映射，直接用
        if language in self._resolved_names:
            return _tree_sitter_module.get_parser(self._resolved_names[language])

        # 尝试原始名称
        try:
            parser = _tree_sitter_module.get_parser(language)
            self._resolved_names[language] = language
            return parser
        except Exception:
            pass

        # 尝试别名
        aliases = self._LANG_ALIASES.get(language, [])
        for alias in aliases:
            if alias == language:
                continue  # 已经试过了
            try:
                parser = _tree_sitter_module.get_parser(alias)
                self._resolved_names[language] = alias
                logger.debug("tree_sitter.alias_resolved",
                             language=language, alias=alias)
                return parser
            except Exception:
                continue

        return None

    def get_parser(self, language: str):
        """获取指定语言的 parser（带别名解析）。

        外部代码应使用此方法代替直接调用 _tree_sitter_module.get_parser()。

        Raises:
            RuntimeError: 如果语言不可用
        """
        parser = self._try_get_parser(language)
        if parser is None:
            raise RuntimeError(f"tree-sitter parser not available for: {language}")
        return parser

    def is_available(self, language: str | None = None) -> bool:
        """检查 tree-sitter 是否可用。

        Args:
            language: 可选，检查特定语言的 parser 是否可用。
                      None 则检查全局可用性。
        """
        now = time.monotonic()
        # 缓存过期则重新检测
        if self._global_available is None or (now - self._last_check) > self._CACHE_TTL:
            self._global_available = self._check_global()
            self._last_check = now
            self._available.clear()
            self._resolved_names.clear()
            logger.info("tree_sitter.health_check",
                        available=self._global_available)

        if not self._global_available:
            return False

        if language is None:
            return True

        if language not in self._available:
            parser = self._try_get_parser(language)
            self._available[language] = parser is not None
            if not self._available[language]:
                logger.debug("tree_sitter.lang_unavailable",
                             language=language,
                             aliases_tried=self._LANG_ALIASES.get(language, []))

        return self._available[language]

    def reset(self):
        """重置缓存，强制下次重新检测。"""
        self._global_available = None
        self._available.clear()
        self._resolved_names.clear()
        self._last_check = 0


# 全局单例
_health_check = TreeSitterHealthCheck()

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
    # M1 新增：解析方式追踪
    parse_method: str = "full"      # full / partial / basic / failed
    parse_confidence: float = 1.0   # 0.0-1.0，tree-sitter=1.0，正则=0.5-0.8
    fallback_reason: str = ""       # 降级原因，如 "tree-sitter unavailable"


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
    "csharp": {
        "function_def": ["method_declaration", "constructor_declaration"],
        "class_def": ["class_declaration"],
        "import": ["using_directive"],
        "call": ["invocation_expression"],
        "name_field": "name",
        "params_field": "parameters",
        "body_field": "body",
        "superclass_field": "base_list",
    },
    "swift": {
        "function_def": ["function_declaration", "protocol_function_declaration"],
        "class_def": ["class_declaration", "protocol_declaration"],
        "import": ["import_declaration"],
        "call": ["call_expression"],
        "name_field": "name",
        "params_field": None,
        "body_field": "body",
        "superclass_field": None,
    },
    # ── 原有扩展名但缺 LANG_CONFIG 的语言 ──────────────────
    "ruby": {
        "function_def": ["method", "singleton_method"],
        "class_def": ["class", "module"],
        "import": ["call"],  # require / require_relative
        "call": ["call", "command_call"],
        "name_field": "name",
        "params_field": "parameters",
        "body_field": "body",
        "superclass_field": "superclass",
    },
    "php": {
        "function_def": ["function_definition", "method_declaration"],
        "class_def": ["class_declaration", "interface_declaration", "trait_declaration"],
        "import": ["namespace_use_declaration"],
        "call": ["function_call_expression", "member_call_expression"],
        "name_field": "name",
        "params_field": "parameters",
        "body_field": "body",
        "superclass_field": "base_clause",
    },
    "kotlin": {
        "function_def": ["function_declaration"],
        "class_def": ["class_declaration", "object_declaration"],
        "import": ["import_header"],
        "call": ["call_expression"],
        "name_field": "simple_identifier",
        "params_field": "function_value_parameters",
        "body_field": "function_body",
        "superclass_field": "delegation_specifiers",
    },
    # ── 系统级 / 编译型 ────────────────────────────────────
    "zig": {
        "function_def": ["FnDecl", "TestDecl"],
        "class_def": ["ContainerDecl"],  # struct / enum / union
        "import": ["BuiltinCallExpr"],  # @import(...)
        "call": ["CallExpr", "BuiltinCallExpr"],
        "name_field": "name",
        "params_field": "parameters",
        "body_field": "body",
        "superclass_field": None,
    },
    "nim": {
        "function_def": ["proc_def", "func_def", "method_def", "template_def", "macro_def"],
        "class_def": ["type_section"],
        "import": ["import_stmt", "from_stmt"],
        "call": ["call"],
        "name_field": "name",
        "params_field": "parameters",
        "body_field": "body",
        "superclass_field": None,
    },
    "v": {
        "function_def": ["function_declaration"],
        "class_def": ["struct_declaration", "interface_declaration", "enum_declaration"],
        "import": ["import_declaration"],
        "call": ["call_expression"],
        "name_field": "name",
        "params_field": "parameters",
        "body_field": "body",
        "superclass_field": None,
    },
    "d": {
        "function_def": ["function_declaration"],
        "class_def": ["class_declaration", "struct_declaration", "interface_declaration"],
        "import": ["import_declaration"],
        "call": ["call_expression"],
        "name_field": "name",
        "params_field": "parameters",
        "body_field": "body",
        "superclass_field": "base_class_list",
    },
    # ── JVM / .NET ─────────────────────────────────────────
    "scala": {
        "function_def": ["function_definition", "function_declaration"],
        "class_def": ["class_definition", "object_definition", "trait_definition"],
        "import": ["import_declaration"],
        "call": ["call_expression"],
        "name_field": "name",
        "params_field": "parameters",
        "body_field": "body",
        "superclass_field": "extends_clause",
    },
    "groovy": {
        "function_def": ["method_declaration"],
        "class_def": ["class_declaration"],
        "import": ["import_declaration"],
        "call": ["method_call"],
        "name_field": "name",
        "params_field": "parameters",
        "body_field": "body",
        "superclass_field": "superclass",
    },
    "clojure": {
        "function_def": ["list_lit"],  # (defn ...) — 通过首个符号判断
        "class_def": ["list_lit"],  # (defrecord ...) / (defprotocol ...)
        "import": ["list_lit"],  # (require ...) / (import ...)
        "call": ["list_lit"],
        "name_field": None,  # Clojure 是同像性语言，需要特殊提取
        "params_field": None,
        "body_field": None,
        "superclass_field": None,
    },
    # ── 移动端 ─────────────────────────────────────────────
    "dart": {
        "function_def": ["function_signature", "method_signature"],
        "class_def": ["class_definition"],
        "import": ["import_or_export"],
        "call": ["call_expression"],
        "name_field": "name",
        "params_field": "formal_parameter_list",
        "body_field": "function_body",
        "superclass_field": "superclass",
    },
    "objc": {
        "function_def": ["function_definition", "method_declaration"],
        "class_def": ["class_interface", "class_implementation", "protocol_declaration"],
        "import": ["preproc_import", "preproc_include"],
        "call": ["call_expression", "message_expression"],
        "name_field": "declarator",
        "params_field": "parameters",
        "body_field": "body",
        "superclass_field": "superclass_reference",
    },
    # ── 函数式 ─────────────────────────────────────────────
    "haskell": {
        "function_def": ["function"],
        "class_def": ["class", "data", "newtype"],
        "import": ["import"],
        "call": ["apply"],
        "name_field": "name",
        "params_field": "patterns",
        "body_field": "match",
        "superclass_field": None,
    },
    "ocaml": {
        "function_def": ["let_binding", "value_definition"],
        "class_def": ["type_definition", "class_definition", "module_definition"],
        "import": ["open_statement"],
        "call": ["application"],
        "name_field": "name",
        "params_field": "parameter",
        "body_field": "body",
        "superclass_field": None,
    },
    "elixir": {
        "function_def": ["call"],  # def / defp 是宏调用
        "class_def": ["call"],  # defmodule 是宏调用
        "import": ["call"],  # import / use / require / alias
        "call": ["call"],
        "name_field": None,  # 需要特殊提取
        "params_field": "arguments",
        "body_field": "do_block",
        "superclass_field": None,
    },
    "erlang": {
        "function_def": ["function"],
        "class_def": [],  # Erlang 无类概念
        "import": ["module_attribute"],  # -import(...)
        "call": ["call"],
        "name_field": "name",
        "params_field": "args",
        "body_field": "clause_body",
        "superclass_field": None,
    },
    # ── 脚本 / 数据科学 ───────────────────────────────────
    "lua": {
        "function_def": ["function_declaration", "function_definition", "local_function"],
        "class_def": [],  # Lua 无原生类
        "import": ["function_call"],  # require(...)
        "call": ["function_call"],
        "name_field": "name",
        "params_field": "parameters",
        "body_field": "body",
        "superclass_field": None,
    },
    "perl": {
        "function_def": ["subroutine_declaration_statement"],
        "class_def": ["package_statement"],
        "import": ["use_statement", "require_statement"],
        "call": ["call_expression", "method_call_expression"],
        "name_field": "name",
        "params_field": None,  # Perl 参数通过 @_ 隐式传递
        "body_field": "body",
        "superclass_field": None,
    },
    "r": {
        "function_def": ["function_definition"],
        "class_def": [],  # R 的 S4/R6 类不是语法级别的
        "import": ["call"],  # library() / require()
        "call": ["call"],
        "name_field": "name",
        "params_field": "parameters",
        "body_field": "body",
        "superclass_field": None,
    },
    "julia": {
        "function_def": ["function_definition", "short_function_definition"],
        "class_def": ["struct_definition", "abstract_definition"],
        "import": ["import_statement", "using_statement"],
        "call": ["call_expression"],
        "name_field": "name",
        "params_field": "parameters",
        "body_field": "body",
        "superclass_field": "supertype_clause",
    },
    # ── Shell ──────────────────────────────────────────────
    "bash": {
        "function_def": ["function_definition"],
        "class_def": [],
        "import": ["command"],  # source / .
        "call": ["command"],
        "name_field": "name",
        "params_field": None,
        "body_field": "body",
        "superclass_field": None,
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


def _walk_tree(node, callback, depth=0, on_leave=None):
    """遍历 tree-sitter 语法树（支持 enter/leave 回调）。"""
    callback(node, depth)
    for child in node.children:
        _walk_tree(child, callback, depth + 1, on_leave=on_leave)
    if on_leave is not None:
        on_leave(node, depth)


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

    def _try_extract_string(string_node) -> str | None:
        text = _get_node_text(string_node)
        if text.startswith(('"""', "'''")):
            return text[3:-3].strip()
        elif text.startswith(('"', "'")):
            return text[1:-1].strip()
        # tree-sitter 新版可能把 string 拆成 string_start + string_content + string_end
        for sub in string_node.children:
            if sub.type == "string_content":
                return _get_node_text(sub).strip()
        return None

    for child in body.children:
        if child.type == "expression_statement":
            for sub in child.children:
                if sub.type == "string":
                    return _try_extract_string(sub)
        # tree-sitter 某些版本中 docstring 直接是 body > string（无 expression_statement 包裹）
        elif child.type == "string":
            return _try_extract_string(child)
        else:
            # body 的第一个非空语句不是字符串，则没有 docstring
            break
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


# ── Swift 专用提取 ──────────────────────────────────────

def _extract_swift_params(func_node) -> list[str]:
    """提取 Swift 函数参数名列表。

    Swift 参数不在 field 中，而是直接作为 `parameter` 类型的子节点。
    每个 parameter 的文本格式为 `label name: Type` 或 `name: Type`。
    """
    params = []
    for child in func_node.children:
        if child.type == "parameter":
            text = _get_node_text(child).strip()
            # 解析 Swift 参数：可能是 "label name: Type" 或 "name: Type" 或 "_ name: Type"
            if ":" in text:
                before_colon = text.split(":")[0].strip()
                parts = before_colon.split()
                # 取最后一个标识符作为参数名（第一个是外部标签）
                param_name = parts[-1] if parts else before_colon
                if param_name != "_":
                    params.append(param_name)
    return params


def _extract_swift_imports(node) -> list[ImportInfo]:
    """提取 Swift import 语句。

    Swift import 格式: `import Foundation` 或 `import struct Module.Struct`
    """
    imports = []
    if node.type == "import_declaration":
        # 收集 identifier / simple_identifier 子节点
        for child in node.children:
            if child.type == "identifier":
                module_name = _get_node_text(child)
                imports.append(ImportInfo(
                    module=module_name,
                    line=node.start_point[0] + 1,
                ))
    return imports


def _extract_swift_inheritance(class_node) -> str | None:
    """提取 Swift 类/结构体的继承和协议遵循信息。

    Swift 通过 `inheritance_specifier` 子节点表示继承和协议遵循。
    """
    parents = []
    for child in class_node.children:
        if child.type == "inheritance_specifier":
            parents.append(_get_node_text(child).strip())
    return ", ".join(parents) if parents else None


def _extract_swift_callee_name(call_node) -> str:
    """从 Swift call_expression 提取被调用函数名。

    Swift 的 call_expression 结构:
    - simple_identifier + call_suffix  → 普通调用 e.g. print("hi")
    - navigation_expression + call_suffix → 成员调用 e.g. service.send(...)
    - 嵌套 call_expression + navigation_suffix → 链式调用 e.g. JSONDecoder().decode(...)
    """
    for child in call_node.children:
        if child.type == "navigation_expression":
            # 取 navigation_suffix 中的方法名
            for sub in child.children:
                if sub.type == "navigation_suffix":
                    text = _get_node_text(sub).lstrip(".")
                    return text
        elif child.type == "simple_identifier":
            return _get_node_text(child)
    # Fallback: 取整个第一个子节点文本
    if call_node.children:
        text = _get_node_text(call_node.children[0])
        if "." in text:
            return text.split(".")[-1]
        return text
    return "<unknown>"


# ── 核心解析函数 ─────────────────────────────────────────

async def parse_file(file: FileInfo) -> ParseResult:
    """解析单个文件，优先用 tree-sitter，不可用时降级到正则。

    M1 降级路由：
    1. 检查 tree-sitter 是否可用
    2. 可用 → 尝试 tree-sitter，失败再 fallback
    3. 不可用 → 直接走正则

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
    if file.is_config:
        return result

    # 读取源码（tree-sitter 和正则都需要）
    try:
        with open(file.abs_path, "rb") as f:
            source = f.read()
    except (OSError, UnicodeDecodeError) as e:
        result.parse_errors.append(f"Read error: {e}")
        result.parse_method = "failed"
        result.parse_confidence = 0.0
        return result

    # ── M2: Python native ast 优先解析 ──
    if file.language == "python":
        try:
            from src.parsers.native_extractors import PythonAstExtractor
            text = source.decode("utf-8", errors="replace")
            native_result = PythonAstExtractor().extract_all(text, file.path)
            result.classes = native_result.classes
            result.functions = native_result.functions
            result.imports = native_result.imports
            result.calls = native_result.calls
            result.line_count = native_result.line_count
            result.parse_method = native_result.parse_method
            result.parse_confidence = native_result.parse_confidence
            logger.debug(
                "parse_file.native_ast",
                file=file.path,
                functions=len(result.functions),
                classes=len(result.classes),
            )
            return result
        except SyntaxError as e:
            result.fallback_reason = f"ast parse error: {e}"
            logger.debug("parse_file.native_ast_fallback", file=file.path, error=str(e))
        except Exception as e:
            result.fallback_reason = f"native ast error: {e}"
            logger.debug("parse_file.native_ast_error", file=file.path, error=str(e))

    # ── M1 降级路由 ──
    # 语言不在 LANG_CONFIG 中，直接走正则
    if file.language not in LANG_CONFIG:
        return _parse_with_regex(file, source, result)

    lang_config = LANG_CONFIG[file.language]

    # 检查 tree-sitter 是否可用
    if not _health_check.is_available(file.language):
        result.fallback_reason = "tree-sitter unavailable"
        return _parse_with_regex(file, source, result)

    # 尝试 tree-sitter 解析（带超时保护）
    try:
        parser = _health_check.get_parser(file.language)
        tree = parser.parse(source)
    except Exception as e:
        # tree-sitter 失败，降级到正则
        logger.debug("tree_sitter.parse_failed", file=file.path, error=str(e))
        result.fallback_reason = f"tree-sitter parse error: {e}"
        return _parse_with_regex(file, source, result)

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

            # 继承 / 协议遵循
            parent = None
            if file.language == "swift":
                parent = _extract_swift_inheritance(node)
            else:
                sc_field = lang_config.get("superclass_field")
                if sc_field:
                    sc_node = _find_child_by_field(node, sc_field)
                    if sc_node:
                        parent = _get_node_text(sc_node).strip("()")

            # 收集方法名（需要搜索 body 子节点内的函数定义）
            methods = []
            # Swift 的 body 字段名为 class_body / protocol_body，不是通用的 "body"
            body_node = _find_child_by_field(node, "body")
            if body_node is None and file.language == "swift":
                # Swift: 尝试 class_body 或 protocol_body
                for child in node.children:
                    if child.type in ("class_body", "protocol_body", "enum_class_body"):
                        body_node = child
                        break
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
            if file.language == "swift":
                params = _extract_swift_params(node)
            elif file.language == "python":
                params_node = _find_child_by_field(node, lang_config["params_field"])
                params = _extract_python_params(params_node)
            elif lang_config.get("params_field") is not None:
                params_node = _find_child_by_field(node, lang_config["params_field"])
                params = [_get_node_text(p) for p in (params_node.children if params_node else [])
                          if p.type not in ("(", ")", ",")]
            else:
                # 语言无参数字段（如 bash）
                params = []

            # Docstring (Python only)
            docstring = None
            if file.language == "python":
                docstring = _extract_python_docstring(node)

            # 判断是否是方法
            is_method = bool(class_stack) or (
                node.parent and node.parent.type in class_types
            )
            # Swift: 方法的 parent 可能是 class_body / protocol_body
            if file.language == "swift" and not is_method and node.parent:
                is_method = node.parent.type in ("class_body", "protocol_body", "enum_class_body")
                if is_method and not class_stack:
                    # 尝试从 grandparent 获取类名
                    grandparent = node.parent.parent
                    if grandparent:
                        gp_name = _find_child_by_field(grandparent, "name")
                        if gp_name:
                            class_stack.append(_get_node_text(gp_name))

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
            elif file.language == "swift":
                result.imports.extend(_extract_swift_imports(node))
            else:
                result.imports.append(ImportInfo(
                    module=_get_node_text(node).strip(),
                    line=node.start_point[0] + 1,
                ))

        # ── 函数调用 ──
        elif node.type in call_types:
            caller = _find_enclosing_function(node, lang_config)
            if file.language == "swift":
                callee = _extract_swift_callee_name(node)
            else:
                callee = _extract_callee_name(node, file.language)
            result.calls.append(CallInfo(
                caller_func=caller,
                callee_name=callee,
                line=node.start_point[0] + 1,
            ))

    def on_leave(node, depth):
        """离开 class 节点时弹出 class_stack。"""
        if node.type in class_types and class_stack:
            class_stack.pop()

    _walk_tree(root, visitor, on_leave=on_leave)
    result.parse_method = "full"
    result.parse_confidence = 1.0
    logger.debug(
        "parse_file.done",
        file=file.path,
        method=result.parse_method,
        classes=len(result.classes),
        functions=len(result.functions),
        imports=len(result.imports),
        calls=len(result.calls),
    )
    return result


def _parse_with_regex(file: FileInfo, source: bytes, result: ParseResult) -> ParseResult:
    """用正则 fallback 解析文件（M1 核心降级路径）。"""
    from src.parsers.regex_extractor import get_extractor, ParseMethod

    try:
        text = source.decode("utf-8", errors="replace")
    except Exception as e:
        result.parse_errors.append(f"Decode error in fallback: {e}")
        result.parse_method = ParseMethod.FAILED.value
        result.parse_confidence = 0.0
        return result

    try:
        extractor = get_extractor(file.language)
        fallback_result = extractor.extract_all(text, file.path, file.language)

        # 将 fallback 结果合并到 result（保留已有的 parse_errors 和 fallback_reason）
        result.classes = fallback_result.classes
        result.functions = fallback_result.functions
        result.imports = fallback_result.imports
        result.calls = fallback_result.calls
        result.line_count = fallback_result.line_count
        result.parse_method = fallback_result.parse_method
        result.parse_confidence = fallback_result.parse_confidence

        logger.debug(
            "parse_file.regex_fallback",
            file=file.path,
            method=result.parse_method,
            confidence=result.parse_confidence,
            reason=result.fallback_reason,
            classes=len(result.classes),
            functions=len(result.functions),
            imports=len(result.imports),
        )
    except Exception as e:
        result.parse_errors.append(f"Regex fallback error: {e}")
        result.parse_method = ParseMethod.FAILED.value
        result.parse_confidence = 0.0
        logger.error("parse_file.regex_fallback_failed", file=file.path, error=str(e))

    return result


def _parse_file_sync(file: FileInfo) -> ParseResult:
    """同步版本的 parse_file，供 ThreadPoolExecutor 使用。

    每个线程创建独立的事件循环来运行 async parse_file。
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(parse_file(file))
    finally:
        loop.close()


# 并行解析默认配置
_DEFAULT_MAX_WORKERS = min(os.cpu_count() or 4, 8)
_SINGLE_FILE_TIMEOUT = 5  # 秒


async def parse_all(files: list[FileInfo]) -> list[ParseResult]:
    """并行解析所有文件（使用 ThreadPoolExecutor 实现真正的并行）。

    tree-sitter 是 C 扩展，会释放 GIL，因此 ThreadPoolExecutor
    可以实现真正的并行解析。每个线程创建独立的 Parser 实例。

    单文件超时 5 秒，超时则退化到正则 fallback 并记录警告。

    Args:
        files: 要解析的文件列表。

    Returns:
        每个文件的 ParseResult 列表。
    """
    code_files = [f for f in files if not f.is_config]

    if not code_files:
        return []

    parsed: list[ParseResult] = []
    loop = asyncio.get_event_loop()

    max_workers = min(_DEFAULT_MAX_WORKERS, len(code_files))
    logger.info("parse_all.start",
                total_files=len(code_files),
                max_workers=max_workers)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有任务
        future_to_file = {
            executor.submit(_parse_file_sync, f): f
            for f in code_files
        }

        # 收集结果（带单文件超时）
        for future in future_to_file:
            file = future_to_file[future]
            try:
                result = future.result(timeout=_SINGLE_FILE_TIMEOUT)
                parsed.append(result)
            except FuturesTimeoutError:
                logger.warning("parse_file.timeout",
                               file=file.path,
                               timeout=_SINGLE_FILE_TIMEOUT)
                # 超时 → 创建基础结果
                parsed.append(ParseResult(
                    file_path=file.path,
                    language=file.language,
                    line_count=file.line_count,
                    parse_method="basic",
                    parse_confidence=0.3,
                    fallback_reason=f"timeout after {_SINGLE_FILE_TIMEOUT}s",
                ))
            except Exception as e:
                logger.error("parse_file.exception",
                             file=file.path,
                             error=str(e))

    logger.info(
        "parse_all.done",
        total=len(files),
        parsed=len(parsed),
        total_functions=sum(len(r.functions) for r in parsed),
        total_classes=sum(len(r.classes) for r in parsed),
    )
    return parsed
