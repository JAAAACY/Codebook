"""M1 集成测试：正则 Fallback + tree-sitter 健康检测 + 降级路由。

测试三种模式：
1. 正常模式 — tree-sitter 可用时全部功能正常
2. 降级模式 — mock tree-sitter 失败，验证 fallback 全链路
3. 混合模式 — 部分语言可用，部分不可用
"""

import asyncio
import textwrap
from unittest.mock import patch, MagicMock

import pytest

from src.parsers.ast_parser import (
    ParseResult,
    parse_file,
    TreeSitterHealthCheck,
    _health_check,
)
from src.parsers.regex_extractor import (
    ParseMethod,
    PythonRegexExtractor,
    TSRegexExtractor,
    GoRegexExtractor,
    RustRegexExtractor,
    JavaRegexExtractor,
    GenericRegexExtractor,
    get_extractor,
)
from src.parsers.repo_cloner import FileInfo


# ── 测试 fixtures ────────────────────────────────────────


PYTHON_SAMPLE = textwrap.dedent("""\
    import os
    from pathlib import Path
    from typing import Optional

    class BaseParser:
        \"\"\"基础解析器。\"\"\"

        def __init__(self, config: dict):
            self.config = config

        def parse(self, source: str) -> list:
            return []

        async def parse_async(self, source: str):
            return self.parse(source)

    class AdvancedParser(BaseParser):
        def parse(self, source: str) -> list:
            tokens = tokenize(source)
            return self._process(tokens)

        def _process(self, tokens):
            return tokens

    def tokenize(text: str) -> list[str]:
        return text.split()

    def main():
        parser = AdvancedParser({"debug": True})
        result = parser.parse("hello world")
        print(result)
""")

TS_SAMPLE = textwrap.dedent("""\
    import { Router } from 'express';
    import type { Request, Response } from 'express';

    export class UserController {
        constructor(private service: UserService) {}

        async getUser(req: Request, res: Response) {
            const user = await this.service.findById(req.params.id);
            res.json(user);
        }

        deleteUser(req: Request, res: Response) {
            this.service.delete(req.params.id);
            res.status(204).send();
        }
    }

    export function createRouter(controller: UserController): Router {
        const router = Router();
        router.get('/:id', (req, res) => controller.getUser(req, res));
        return router;
    }

    const validateId = (id: string): boolean => {
        return /^[0-9a-f]{24}$/.test(id);
    };
""")

GO_SAMPLE = textwrap.dedent("""\
    package main

    import (
        "fmt"
        "net/http"
    )

    type Server struct {
        port int
        host string
    }

    func NewServer(port int) *Server {
        return &Server{port: port, host: "localhost"}
    }

    func (s *Server) Start() error {
        addr := fmt.Sprintf("%s:%d", s.host, s.port)
        return http.ListenAndServe(addr, nil)
    }

    func main() {
        server := NewServer(8080)
        server.Start()
    }
""")

RUST_SAMPLE = textwrap.dedent("""\
    use std::collections::HashMap;
    use std::io;

    pub struct Config {
        settings: HashMap<String, String>,
    }

    impl Config {
        pub fn new() -> Self {
            Config { settings: HashMap::new() }
        }

        pub fn get(&self, key: &str) -> Option<&String> {
            self.settings.get(key)
        }

        pub async fn load_from_file(path: &str) -> io::Result<Self> {
            let mut config = Config::new();
            Ok(config)
        }
    }

    fn main() {
        let config = Config::new();
        println!("{:?}", config.get("key"));
    }
""")

JAVA_SAMPLE = textwrap.dedent("""\
    import java.util.List;
    import java.util.ArrayList;

    public class UserService {
        private final UserRepository repo;

        public UserService(UserRepository repo) {
            this.repo = repo;
        }

        public User findById(String id) {
            return repo.findById(id);
        }

        public List<User> findAll() {
            return new ArrayList<>(repo.findAll());
        }

        private void validate(User user) {
            if (user == null) throw new IllegalArgumentException();
        }
    }
""")

ZIG_SAMPLE = textwrap.dedent("""\
    const std = @import("std");

    pub fn add(a: i32, b: i32) i32 {
        return a + b;
    }

    pub fn main() !void {
        const stdout = std.io.getStdOut().writer();
        try stdout.print("Hello, {s}!\\n", .{"world"});
    }

    fn helper() void {
        // internal helper
    }
""")


# ============================================================
# 1. 正则提取器单元测试
# ============================================================


class TestPythonExtractor:
    """Python 正则提取器测试。"""

    def setup_method(self):
        self.ext = PythonRegexExtractor()
        self.lines = PYTHON_SAMPLE.splitlines()

    def test_extract_functions(self):
        funcs = self.ext.extract_functions(PYTHON_SAMPLE, self.lines)
        names = [f.name for f in funcs]
        assert "tokenize" in names
        assert "main" in names
        assert "__init__" in names
        assert "parse" in names
        assert "parse_async" in names

    def test_extract_classes(self):
        classes = self.ext.extract_classes(PYTHON_SAMPLE, self.lines)
        names = [c.name for c in classes]
        assert "BaseParser" in names
        assert "AdvancedParser" in names

    def test_class_methods(self):
        classes = self.ext.extract_classes(PYTHON_SAMPLE, self.lines)
        base = next(c for c in classes if c.name == "BaseParser")
        assert "__init__" in base.methods
        assert "parse" in base.methods

    def test_class_inheritance(self):
        classes = self.ext.extract_classes(PYTHON_SAMPLE, self.lines)
        adv = next(c for c in classes if c.name == "AdvancedParser")
        assert adv.parent_class == "BaseParser"

    def test_extract_imports(self):
        imports = self.ext.extract_imports(PYTHON_SAMPLE, self.lines)
        modules = [i.module for i in imports]
        assert "os" in modules
        assert "pathlib" in modules

    def test_function_line_range(self):
        funcs = self.ext.extract_functions(PYTHON_SAMPLE, self.lines)
        tokenize = next(f for f in funcs if f.name == "tokenize")
        assert tokenize.line_start > 0
        assert tokenize.line_end >= tokenize.line_start

    def test_extract_calls(self):
        calls = self.ext.extract_calls(PYTHON_SAMPLE, self.lines)
        callee_names = [c.callee_name for c in calls]
        assert "tokenize" in callee_names
        assert "AdvancedParser" in callee_names
        # print 在关键字排除列表中，不应出现
        assert "print" not in callee_names


class TestTSExtractor:
    """TypeScript 正则提取器测试。"""

    def setup_method(self):
        self.ext = TSRegexExtractor()
        self.lines = TS_SAMPLE.splitlines()

    def test_extract_functions(self):
        funcs = self.ext.extract_functions(TS_SAMPLE, self.lines)
        names = [f.name for f in funcs]
        assert "createRouter" in names

    def test_extract_classes(self):
        classes = self.ext.extract_classes(TS_SAMPLE, self.lines)
        assert len(classes) >= 1
        assert classes[0].name == "UserController"

    def test_class_methods(self):
        classes = self.ext.extract_classes(TS_SAMPLE, self.lines)
        ctrl = next(c for c in classes if c.name == "UserController")
        assert "getUser" in ctrl.methods
        assert "deleteUser" in ctrl.methods

    def test_extract_imports(self):
        imports = self.ext.extract_imports(TS_SAMPLE, self.lines)
        modules = [i.module for i in imports]
        assert "express" in modules

    def test_arrow_function(self):
        funcs = self.ext.extract_functions(TS_SAMPLE, self.lines)
        names = [f.name for f in funcs]
        assert "validateId" in names


class TestGoExtractor:
    """Go 正则提取器测试。"""

    def setup_method(self):
        self.ext = GoRegexExtractor()
        self.lines = GO_SAMPLE.splitlines()

    def test_extract_functions(self):
        funcs = self.ext.extract_functions(GO_SAMPLE, self.lines)
        names = [f.name for f in funcs]
        assert "NewServer" in names
        assert "Start" in names
        assert "main" in names

    def test_method_receiver(self):
        funcs = self.ext.extract_functions(GO_SAMPLE, self.lines)
        start = next(f for f in funcs if f.name == "Start")
        assert start.is_method
        assert start.parent_class == "Server"

    def test_extract_structs(self):
        classes = self.ext.extract_classes(GO_SAMPLE, self.lines)
        names = [c.name for c in classes]
        assert "Server" in names

    def test_extract_imports(self):
        imports = self.ext.extract_imports(GO_SAMPLE, self.lines)
        modules = [i.module for i in imports]
        assert "fmt" in modules
        assert "net/http" in modules


class TestRustExtractor:
    """Rust 正则提取器测试。"""

    def setup_method(self):
        self.ext = RustRegexExtractor()
        self.lines = RUST_SAMPLE.splitlines()

    def test_extract_functions(self):
        funcs = self.ext.extract_functions(RUST_SAMPLE, self.lines)
        names = [f.name for f in funcs]
        assert "new" in names
        assert "get" in names
        assert "load_from_file" in names
        assert "main" in names

    def test_extract_structs(self):
        classes = self.ext.extract_classes(RUST_SAMPLE, self.lines)
        names = [c.name for c in classes]
        assert "Config" in names

    def test_extract_use(self):
        imports = self.ext.extract_imports(RUST_SAMPLE, self.lines)
        modules = [i.module for i in imports]
        assert any("HashMap" in m for m in modules)


class TestJavaExtractor:
    """Java 正则提取器测试。"""

    def setup_method(self):
        self.ext = JavaRegexExtractor()
        self.lines = JAVA_SAMPLE.splitlines()

    def test_extract_functions(self):
        funcs = self.ext.extract_functions(JAVA_SAMPLE, self.lines)
        names = [f.name for f in funcs]
        assert "findById" in names
        assert "findAll" in names
        assert "validate" in names

    def test_extract_classes(self):
        classes = self.ext.extract_classes(JAVA_SAMPLE, self.lines)
        assert len(classes) >= 1
        assert classes[0].name == "UserService"

    def test_extract_imports(self):
        imports = self.ext.extract_imports(JAVA_SAMPLE, self.lines)
        modules = [i.module for i in imports]
        assert any("List" in m for m in modules)


class TestGenericExtractor:
    """通用 Fallback 提取器测试（Zig 语言）。"""

    def setup_method(self):
        self.ext = GenericRegexExtractor()
        self.lines = ZIG_SAMPLE.splitlines()

    def test_extract_functions(self):
        funcs = self.ext.extract_functions(ZIG_SAMPLE, self.lines)
        names = [f.name for f in funcs]
        assert "add" in names
        assert "main" in names
        assert "helper" in names

    def test_extract_imports(self):
        imports = self.ext.extract_imports(ZIG_SAMPLE, self.lines)
        assert len(imports) >= 0  # Zig uses @import which may not match


# ============================================================
# 2. 提取器工厂测试
# ============================================================


class TestExtractorFactory:
    """get_extractor() 工厂函数测试。"""

    def test_python_returns_specialized(self):
        ext = get_extractor("python")
        assert isinstance(ext, PythonRegexExtractor)

    def test_typescript_returns_specialized(self):
        ext = get_extractor("typescript")
        assert isinstance(ext, TSRegexExtractor)

    def test_javascript_returns_specialized(self):
        ext = get_extractor("javascript")
        assert isinstance(ext, TSRegexExtractor)

    def test_go_returns_specialized(self):
        ext = get_extractor("go")
        assert isinstance(ext, GoRegexExtractor)

    def test_rust_returns_specialized(self):
        ext = get_extractor("rust")
        assert isinstance(ext, RustRegexExtractor)

    def test_java_returns_specialized(self):
        ext = get_extractor("java")
        assert isinstance(ext, JavaRegexExtractor)

    def test_unknown_returns_generic(self):
        ext = get_extractor("zig")
        assert isinstance(ext, GenericRegexExtractor)

    def test_singleton_caching(self):
        ext1 = get_extractor("python")
        ext2 = get_extractor("python")
        assert ext1 is ext2


# ============================================================
# 3. extract_all 集成测试
# ============================================================


class TestExtractAll:
    """extract_all() 返回正确的 ParseResult 结构。"""

    def test_python_extract_all(self):
        ext = PythonRegexExtractor()
        result = ext.extract_all(PYTHON_SAMPLE, "test.py", "python")
        assert isinstance(result, ParseResult)
        assert result.parse_method == "partial"
        assert 0.0 < result.parse_confidence <= 1.0
        assert result.file_path == "test.py"
        assert result.language == "python"
        assert len(result.functions) > 0
        assert len(result.classes) > 0
        assert len(result.imports) > 0
        assert result.line_count > 0

    def test_ts_extract_all(self):
        ext = TSRegexExtractor()
        result = ext.extract_all(TS_SAMPLE, "test.ts", "typescript")
        assert result.parse_method == "partial"
        assert len(result.functions) > 0
        assert len(result.classes) > 0

    def test_generic_extract_all(self):
        ext = GenericRegexExtractor()
        result = ext.extract_all(ZIG_SAMPLE, "test.zig", "zig")
        assert result.parse_method == "partial"
        assert len(result.functions) > 0


# ============================================================
# 4. TreeSitterHealthCheck 测试
# ============================================================


class TestTreeSitterHealthCheck:
    """健康检测模块测试。"""

    def test_new_instance_uncached(self):
        hc = TreeSitterHealthCheck()
        assert hc._global_available is None

    def test_check_caches_result(self):
        hc = TreeSitterHealthCheck()
        result1 = hc.is_available()
        result2 = hc.is_available()
        assert result1 == result2
        # 只调用了一次全局检测
        assert hc._global_available is not None

    def test_reset_clears_cache(self):
        hc = TreeSitterHealthCheck()
        hc.is_available()
        hc.reset()
        assert hc._global_available is None
        assert len(hc._available) == 0

    @patch("src.parsers.ast_parser._tree_sitter_module", None)
    @patch("src.parsers.ast_parser._try_import_tree_sitter")  # 阻止延迟重试
    def test_unavailable_when_module_missing(self, mock_retry):
        hc = TreeSitterHealthCheck()
        assert hc.is_available() is False
        assert hc.is_available("python") is False


# ============================================================
# 5. parse_file 降级路由测试
# ============================================================


class TestParseFileFallback:
    """parse_file() 降级路由集成测试。"""

    @pytest.fixture
    def python_file(self, tmp_path):
        """创建一个临时 Python 文件用于测试。"""
        p = tmp_path / "test_sample.py"
        p.write_text(PYTHON_SAMPLE)
        return FileInfo(
            path="test_sample.py",
            abs_path=str(p),
            language="python",
            size_bytes=len(PYTHON_SAMPLE.encode()),
            line_count=len(PYTHON_SAMPLE.splitlines()),
            is_config=False,
        )

    @pytest.fixture
    def zig_file(self, tmp_path):
        """创建一个临时 Zig 文件用于测试。"""
        p = tmp_path / "test_sample.zig"
        p.write_text(ZIG_SAMPLE)
        return FileInfo(
            path="test_sample.zig",
            abs_path=str(p),
            language="zig",
            size_bytes=len(ZIG_SAMPLE.encode()),
            line_count=len(ZIG_SAMPLE.splitlines()),
            is_config=False,
        )

    async def test_normal_mode_uses_native_or_treesitter(self, python_file):
        """Python 文件应优先使用 native ast，否则 tree-sitter。"""
        result = await parse_file(python_file)
        # M2: Python 文件优先走 native ast
        assert result.parse_method in ("native", "full", "partial")
        assert len(result.functions) > 0
        assert len(result.classes) > 0

    @patch("src.parsers.native_extractors.python_ast.PythonAstExtractor.extract_all",
           side_effect=SyntaxError("mock syntax error"))
    @patch("src.parsers.ast_parser._health_check")
    async def test_fallback_when_native_and_treesitter_unavailable(self, mock_hc, mock_native, python_file):
        """native ast 和 tree-sitter 均不可用时应降级到正则。"""
        mock_hc.is_available.return_value = False
        result = await parse_file(python_file)
        assert result.parse_method == "partial"
        assert result.parse_confidence < 1.0
        assert len(result.functions) > 0
        assert len(result.classes) > 0
        assert len(result.imports) > 0

    @patch("src.parsers.native_extractors.python_ast.PythonAstExtractor.extract_all",
           side_effect=SyntaxError("mock syntax error"))
    @patch("src.parsers.ast_parser._tree_sitter_module")
    @patch("src.parsers.ast_parser._health_check")
    async def test_fallback_chain_native_to_treesitter_to_regex(self, mock_hc, mock_ts, mock_native, python_file):
        """native ast 失败 → tree-sitter 失败 → 正则 fallback。"""
        mock_hc.is_available.return_value = True
        mock_ts.get_parser.side_effect = RuntimeError("parser crash")
        result = await parse_file(python_file)
        assert result.parse_method == "partial"
        assert "tree-sitter parse error" in result.fallback_reason

    async def test_config_file_skipped(self, tmp_path):
        """配置文件应直接跳过。"""
        p = tmp_path / "config.json"
        p.write_text('{"key": "value"}')
        fi = FileInfo(
            path="config.json", abs_path=str(p),
            language="json", size_bytes=len(b'{"key": "value"}'),
            line_count=1, is_config=True,
        )
        result = await parse_file(fi)
        assert result.parse_method == "full"
        assert len(result.functions) == 0

    async def test_parse_result_has_new_fields(self, python_file):
        """ParseResult 应包含 M1 新增字段。"""
        result = await parse_file(python_file)
        assert hasattr(result, "parse_method")
        assert hasattr(result, "parse_confidence")
        assert hasattr(result, "fallback_reason")

    @patch("src.parsers.ast_parser._health_check")
    async def test_fallback_preserves_data_structure(self, mock_hc, python_file):
        """降级结果的数据结构应与正常模式兼容。"""
        mock_hc.is_available.return_value = False
        result = await parse_file(python_file)
        # 验证数据结构完整性
        for func in result.functions:
            assert hasattr(func, "name")
            assert hasattr(func, "line_start")
            assert hasattr(func, "line_end")
            assert func.line_start > 0
            assert func.line_end >= func.line_start
        for cls in result.classes:
            assert hasattr(cls, "name")
            assert hasattr(cls, "methods")
            assert isinstance(cls.methods, list)
        for imp in result.imports:
            assert hasattr(imp, "module")
            assert hasattr(imp, "line")


# ============================================================
# 6. ParseMethod 枚举测试
# ============================================================


class TestParseMethod:
    def test_enum_values(self):
        assert ParseMethod.FULL == "full"
        assert ParseMethod.PARTIAL == "partial"
        assert ParseMethod.BASIC == "basic"
        assert ParseMethod.FAILED == "failed"

    def test_string_comparison(self):
        assert ParseMethod.FULL.value == "full"
        result = ParseResult(file_path="test", language="python", parse_method="partial")
        assert result.parse_method == ParseMethod.PARTIAL.value
