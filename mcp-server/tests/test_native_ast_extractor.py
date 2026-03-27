"""Tests for PythonAstExtractor (M2) — native Python ast-based extraction.

Covers: functions, classes, imports, calls, edge cases, and degradation chain.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass
from unittest.mock import patch

import pytest

from src.parsers.native_extractors import PythonAstExtractor
from src.parsers.ast_parser import (
    ParseResult,
    FunctionInfo,
    ClassInfo,
    ImportInfo,
    CallInfo,
    parse_file,
)
from src.parsers.repo_cloner import FileInfo
from src.parsers.regex_extractor import ParseMethod


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ext = PythonAstExtractor()


def _parse(source: str, filename: str = "test.py") -> ParseResult:
    """Shorthand for extracting from a dedented source string."""
    return _ext.extract_all(textwrap.dedent(source), filename)


# ===========================================================================
# 1. TestPythonAstFunctions
# ===========================================================================


class TestPythonAstFunctions:
    """Function and method extraction tests."""

    def test_simple_function(self):
        result = _parse("def hello(): pass\n")
        assert len(result.functions) == 1
        assert result.functions[0].name == "hello"

    def test_async_function(self):
        result = _parse("async def fetch(): pass\n")
        assert len(result.functions) == 1
        assert result.functions[0].name == "fetch"

    def test_function_with_params(self):
        result = _parse("def f(a, b, c): pass\n")
        fn = result.functions[0]
        assert fn.params == ["a", "b", "c"]

    def test_function_with_type_annotations(self):
        result = _parse("def f(x: int) -> str: pass\n")
        fn = result.functions[0]
        assert fn.return_type == "str"
        assert fn.params == ["x"]

    def test_function_star_args_kwargs(self):
        result = _parse("def f(*args, **kwargs): pass\n")
        fn = result.functions[0]
        assert fn.params == ["*args", "**kwargs"]

    def test_function_docstring(self):
        source = '''\
        def greet():
            """Say hello."""
            pass
        '''
        result = _parse(source)
        assert result.functions[0].docstring == "Say hello."

    def test_function_no_docstring(self):
        result = _parse("def greet(): pass\n")
        assert result.functions[0].docstring is None

    def test_function_line_numbers(self):
        source = '''\
        def foo():
            x = 1
            return x
        '''
        result = _parse(source)
        fn = result.functions[0]
        assert fn.line_start == 1
        assert fn.line_end == 3

    def test_method_is_method_flag(self):
        source = '''\
        class MyClass:
            def my_method(self):
                pass
        '''
        result = _parse(source)
        methods = [f for f in result.functions if f.name == "my_method"]
        assert len(methods) == 1
        assert methods[0].is_method is True
        assert methods[0].parent_class == "MyClass"

    def test_standalone_after_class(self):
        source = '''\
        class MyClass:
            def inside(self):
                pass

        def outside():
            pass
        '''
        result = _parse(source)
        outside = [f for f in result.functions if f.name == "outside"][0]
        assert outside.is_method is False
        assert outside.parent_class is None

    def test_multiline_signature(self):
        source = '''\
        def long_func(
            a: int,
            b: str,
            c: float,
        ) -> bool:
            return True
        '''
        result = _parse(source)
        fn = result.functions[0]
        assert fn.name == "long_func"
        assert fn.params == ["a", "b", "c"]
        assert fn.return_type == "bool"


# ===========================================================================
# 2. TestPythonAstClasses
# ===========================================================================


class TestPythonAstClasses:
    """Class extraction tests."""

    def test_simple_class(self):
        result = _parse("class Foo: pass\n")
        assert len(result.classes) == 1
        assert result.classes[0].name == "Foo"
        assert result.classes[0].parent_class is None

    def test_class_with_single_inheritance(self):
        result = _parse("class Foo(Bar): pass\n")
        cls = result.classes[0]
        assert cls.parent_class == "Bar"

    def test_class_with_multiple_bases(self):
        result = _parse("class Foo(A, B): pass\n")
        cls = result.classes[0]
        assert cls.parent_class == "A"

    def test_class_methods_list(self):
        source = '''\
        class Svc:
            def m1(self): pass
            def m2(self): pass
            def m3(self): pass
        '''
        result = _parse(source)
        cls = result.classes[0]
        assert cls.methods == ["m1", "m2", "m3"]

    def test_nested_class(self):
        source = '''\
        class Outer:
            class Inner:
                def inner_method(self): pass
            def outer_method(self): pass
        '''
        result = _parse(source)
        names = [c.name for c in result.classes]
        assert "Outer" in names
        assert "Inner" in names

    def test_class_line_numbers(self):
        source = '''\
        class Demo:
            x = 1
            def foo(self): pass
        '''
        result = _parse(source)
        cls = result.classes[0]
        assert cls.line_start == 1
        assert cls.line_end == 3

    def test_dataclass(self):
        source = '''\
        from dataclasses import dataclass

        @dataclass
        class Cfg:
            x: int = 0
            y: str = ""
        '''
        result = _parse(source)
        cls_names = [c.name for c in result.classes]
        assert "Cfg" in cls_names


# ===========================================================================
# 3. TestPythonAstImports
# ===========================================================================


class TestPythonAstImports:
    """Import extraction tests."""

    def test_import_simple(self):
        result = _parse("import os\n")
        assert len(result.imports) == 1
        imp = result.imports[0]
        assert imp.module == "os"
        assert imp.names == []
        assert imp.is_relative is False

    def test_import_from(self):
        result = _parse("from os import path, getcwd\n")
        imp = result.imports[0]
        assert imp.module == "os"
        assert imp.names == ["path", "getcwd"]

    def test_import_relative(self):
        result = _parse("from .utils import helper\n")
        imp = result.imports[0]
        assert imp.is_relative is True

    def test_import_multiple_statements(self):
        source = '''\
        import os
        import sys
        from pathlib import Path
        '''
        result = _parse(source)
        assert len(result.imports) == 3

    def test_import_line_number(self):
        source = '''\
        x = 1
        import os
        '''
        result = _parse(source)
        assert result.imports[0].line == 2


# ===========================================================================
# 4. TestPythonAstCalls
# ===========================================================================


class TestPythonAstCalls:
    """Call extraction tests."""

    def test_simple_call(self):
        source = '''\
        def bar():
            foo()
        '''
        result = _parse(source)
        call = [c for c in result.calls if c.callee_name == "foo"]
        assert len(call) == 1

    def test_method_call(self):
        source = '''\
        def bar():
            obj.method()
        '''
        result = _parse(source)
        call = [c for c in result.calls if c.callee_name == "method"]
        assert len(call) == 1

    def test_caller_func_tracking(self):
        source = '''\
        def bar():
            foo()
        '''
        result = _parse(source)
        call = [c for c in result.calls if c.callee_name == "foo"][0]
        assert call.caller_func == "bar"

    def test_module_level_call(self):
        result = _parse("print('hello')\n")
        call = [c for c in result.calls if c.callee_name == "print"]
        assert len(call) == 1
        assert call[0].caller_func == "<module>"

    def test_call_line_number(self):
        source = '''\
        x = 1
        def f():
            g()
        '''
        result = _parse(source)
        call = [c for c in result.calls if c.callee_name == "g"][0]
        assert call.line == 3


# ===========================================================================
# 5. TestPythonAstEdgeCases
# ===========================================================================


class TestPythonAstEdgeCases:
    """Edge case and metadata tests."""

    def test_empty_source(self):
        result = _ext.extract_all("", "test.py")
        assert result.functions == []
        assert result.classes == []
        assert result.imports == []
        assert result.calls == []

    def test_syntax_error_raises(self):
        with pytest.raises(SyntaxError):
            _ext.extract_all("def f(\n", "bad.py")

    def test_parse_method_and_confidence(self):
        result = _parse("x = 1\n")
        assert result.parse_method == "native"
        assert result.parse_confidence == 0.99

    def test_complex_real_world(self):
        source = '''\
        import os
        from typing import Optional
        from .helpers import util_func

        def top_level():
            os.path.join("a", "b")

        class BaseService:
            """Base service class."""

            def __init__(self, name: str):
                self.name = name

            async def run(self) -> None:
                pass

        class ChildService(BaseService):
            """Extended service."""

            def process(self, data: list[str]) -> Optional[dict]:
                """Process incoming data."""
                result = util_func(data)
                return result

        def another_func():
            svc = ChildService("test")
            svc.process(["a"])
        '''
        result = _parse(source)

        # imports
        assert len(result.imports) == 3
        rel_imports = [i for i in result.imports if i.is_relative]
        assert len(rel_imports) == 1

        # classes
        cls_names = {c.name for c in result.classes}
        assert cls_names == {"BaseService", "ChildService"}
        child = [c for c in result.classes if c.name == "ChildService"][0]
        assert child.parent_class == "BaseService"

        # functions (top-level + methods)
        fn_names = [f.name for f in result.functions]
        assert "top_level" in fn_names
        assert "another_func" in fn_names
        assert "run" in fn_names
        assert "process" in fn_names
        assert "__init__" in fn_names

        # methods flagged correctly
        init_fn = [f for f in result.functions if f.name == "__init__"][0]
        assert init_fn.is_method is True
        assert init_fn.parent_class == "BaseService"

        # async method detected
        run_fn = [f for f in result.functions if f.name == "run"][0]
        assert run_fn.return_type == "None"

        # docstrings
        process_fn = [f for f in result.functions if f.name == "process"][0]
        assert process_fn.docstring == "Process incoming data."

        # calls present
        call_names = {c.callee_name for c in result.calls}
        assert "util_func" in call_names
        assert "ChildService" in call_names

        # metadata
        assert result.parse_method == "native"
        assert result.parse_confidence == 0.99


# ===========================================================================
# 6. TestNativeDegradationChain
# ===========================================================================


def _make_file_info(tmp_path, filename: str, content: str, language: str) -> FileInfo:
    """Write content to a temp file and return a FileInfo."""
    p = tmp_path / filename
    p.write_text(content, encoding="utf-8")
    return FileInfo(
        path=filename,
        abs_path=str(p),
        language=language,
        size_bytes=len(content.encode()),
        line_count=len(content.splitlines()),
        is_config=False,
    )


class TestNativeDegradationChain:
    """Integration tests for parse_file() degradation: native -> tree-sitter -> regex."""

    @pytest.mark.asyncio
    async def test_python_file_uses_native(self, tmp_path):
        content = "def hello(): pass\n"
        fi = _make_file_info(tmp_path, "test.py", content, "python")
        result = await parse_file(fi)
        assert result.parse_method == "native"

    @pytest.mark.asyncio
    async def test_python2_syntax_falls_to_fallback(self, tmp_path):
        content = 'print "hello"\n'
        fi = _make_file_info(tmp_path, "old.py", content, "python")
        result = await parse_file(fi)
        # Should fall through to tree-sitter or regex, not "native"
        assert result.parse_method in ("full", "partial", "basic")

    @pytest.mark.asyncio
    async def test_non_python_file_skips_native(self, tmp_path):
        content = "function hello() { return 1; }\n"
        fi = _make_file_info(tmp_path, "test.js", content, "javascript")
        result = await parse_file(fi)
        # Native extractor is Python-only; JS goes to tree-sitter or regex
        assert result.parse_method in ("full", "partial", "basic")

    def test_native_enum_value(self):
        assert ParseMethod.NATIVE.value == "native"

    @pytest.mark.asyncio
    async def test_native_fallback_sets_reason(self, tmp_path):
        content = "def hello(): pass\n"
        fi = _make_file_info(tmp_path, "test.py", content, "python")
        with patch(
            "src.parsers.native_extractors.python_ast.PythonAstExtractor.extract_all",
            side_effect=SyntaxError("mock"),
        ):
            result = await parse_file(fi)
        assert result.fallback_reason is not None
        # When tree-sitter is available, the original reason is preserved;
        # when tree-sitter is unavailable, it gets overwritten.
        assert (
            "ast parse error" in result.fallback_reason
            or "tree-sitter unavailable" in result.fallback_reason
        )
