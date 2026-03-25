"""Python AST extractor using the standard-library ``ast`` module."""

from __future__ import annotations

import ast
from typing import List, Optional

import structlog

from src.parsers.ast_parser import (
    CallInfo,
    ClassInfo,
    FunctionInfo,
    ImportInfo,
    ParseResult,
)
from .base import BaseNativeExtractor

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_params(args: ast.arguments) -> List[str]:
    """Return a flat list of parameter names, excluding ``self`` and ``cls``."""
    params: List[str] = []
    for arg in args.posonlyargs + args.args + args.kwonlyargs:
        if arg.arg not in ("self", "cls"):
            params.append(arg.arg)
    if args.vararg:
        params.append(f"*{args.vararg.arg}")
    if args.kwarg:
        params.append(f"**{args.kwarg.arg}")
    return params


def _resolve_callee(node: ast.expr) -> str:
    """Best-effort name for the callee of an ``ast.Call`` node."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return "<complex_call>"


# ---------------------------------------------------------------------------
# Visitor
# ---------------------------------------------------------------------------

class _Visitor(ast.NodeVisitor):
    """Walk a Python AST and collect structural information."""

    def __init__(self) -> None:
        self._functions: List[FunctionInfo] = []
        self._classes: List[ClassInfo] = []
        self._imports: List[ImportInfo] = []
        self._calls: List[CallInfo] = []
        self._class_stack: List[str] = []
        self._func_stack: List[str] = []

    # -- functions / methods ------------------------------------------------

    def _visit_func(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        name: str = node.name
        params: List[str] = _extract_params(node.args)
        return_type: Optional[str] = (
            ast.unparse(node.returns) if node.returns else None
        )
        line_start: int = node.lineno
        line_end: int = node.end_lineno  # type: ignore[assignment]
        docstring: Optional[str] = ast.get_docstring(node)
        is_method: bool = bool(self._class_stack)
        parent_class: Optional[str] = (
            self._class_stack[-1] if self._class_stack else None
        )

        self._functions.append(
            FunctionInfo(
                name=name,
                params=params,
                return_type=return_type,
                line_start=line_start,
                line_end=line_end,
                docstring=docstring,
                is_method=is_method,
                parent_class=parent_class,
            )
        )

        self._func_stack.append(name)
        self.generic_visit(node)
        self._func_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self._visit_func(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        self._visit_func(node)

    # -- classes ------------------------------------------------------------

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        name: str = node.name
        parent_class: Optional[str] = (
            ast.unparse(node.bases[0]) if node.bases else None
        )
        methods: List[str] = [
            n.name
            for n in node.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        line_start: int = node.lineno
        line_end: int = node.end_lineno  # type: ignore[assignment]

        self._classes.append(
            ClassInfo(
                name=name,
                methods=methods,
                parent_class=parent_class,
                line_start=line_start,
                line_end=line_end,
            )
        )

        self._class_stack.append(name)
        self.generic_visit(node)
        self._class_stack.pop()

    # -- imports ------------------------------------------------------------

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        for alias in node.names:
            self._imports.append(
                ImportInfo(
                    module=alias.name,
                    names=[],
                    is_relative=False,
                    line=node.lineno,
                )
            )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        module: str = node.module or ""
        names: List[str] = [alias.name for alias in node.names]
        is_relative: bool = (node.level or 0) > 0

        self._imports.append(
            ImportInfo(
                module=module,
                names=names,
                is_relative=is_relative,
                line=node.lineno,
            )
        )

    # -- calls --------------------------------------------------------------

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        caller_func: str = (
            self._func_stack[-1] if self._func_stack else "<module>"
        )
        callee_name: str = _resolve_callee(node.func)

        self._calls.append(
            CallInfo(
                caller_func=caller_func,
                callee_name=callee_name,
                line=node.lineno,
            )
        )

        self.generic_visit(node)


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------

class PythonAstExtractor(BaseNativeExtractor):
    """Extract structural information from Python source using ``ast``."""

    language: str = "python"

    def extract_all(self, source: str, file_path: str) -> ParseResult:
        """Parse *source* and return a ``ParseResult``.

        Raises:
            SyntaxError: If the source cannot be parsed by ``ast.parse``.
        """
        logger.debug("python_ast.extract_all", file_path=file_path)

        tree = ast.parse(source, filename=file_path)

        visitor = _Visitor()
        visitor.visit(tree)

        line_count = source.count("\n") + (1 if source and not source.endswith("\n") else 0)

        return ParseResult(
            file_path=file_path,
            language=self.language,
            classes=visitor._classes,
            functions=visitor._functions,
            imports=visitor._imports,
            calls=visitor._calls,
            line_count=line_count,
            parse_errors=[],
            parse_method=self.parse_method,
            parse_confidence=self.confidence,
            fallback_reason="",
        )
