# Changelog

All notable changes to CodeBook will be documented in this file.

## [0.5.0] — Sprint 3: Graph Optimization + Mermaid Layered Display (2026-03-27)

### Added
- **依赖图 O(1) 索引查找**: `build()` 第一遍注册节点时同步构建三张索引表（`_name_index`、`_method_name_index`、`_module_path_index`），`_resolve_callee` 从 O(n²) 全文件扫描改为 O(1) 哈希查找。FastAPI 1122 文件基准测试图构建 2.02s → 0.034s（**59x 提速**）。
- **Mermaid 分层展示**: `to_mermaid()` 新增 `level="overview"` 模式，大项目（>30 模块）自动将子模块按顶层目录聚合为超级节点。FastAPI 85 模块 → 5 个顶层节点，Mermaid 输出从 273 行降到 23 行。
- **Mermaid 聚焦展开**: `to_mermaid(level="overview", focus="fastapi")` 展开单个超级节点，内部子模块实线连接 + 外部模块虚线连接。
- **`get_expandable_groups()`**: 返回可展开超级节点组的元数据（子模块数、文件数、代码行数）。
- **scan_repo 分层集成**: 输出新增 `mermaid_overview`（顶层概览图）、`mermaid_full`（完整模块图）、`expandable_groups` 字段，模块数 ≤ 30 时自动降级到模块图。
- 28 个新测试覆盖索引优化、分层展示、边界情况（`test_sprint3_graph.py`）。
- 设计文档 `docs/sprint3_mermaid_layered_design.md`。
- Total test count: **592** (up from 487 in M2, +21.6%).

### Changed
- **`_resolve_callee` 签名简化**: 不再需要传入 `all_results` 参数，改为使用内部索引。
- **`DEFAULT_MAX_OVERVIEW_NODES` 常量**: 新增全局常量控制顶层图最大节点数（默认 30）。

### Fixed
- **`memory_feedback` repo_url 缓存传递**: 修复 `ctx.clone_result.repo_url`（不存在）→ `ctx.repo_url`（正确路径），同步修复 `ask_about`、`read_chapter`、`diagnose` 中相同的属性访问错误。`_repo_cache` 序列化/反序列化增加 `repo_url` 字段持久化。
- 短模块名冲突时的 debug 日志记录，避免索引覆盖。

## [0.4.0] — M2: Python Native AST Extractor (2026-03-24)

### Added
- **Native extractor framework**: Zero-dependency AST extraction using language-native stdlib parsers, sitting at the top of a three-level degradation chain (Native → Tree-sitter → Regex).
  - `BaseNativeExtractor`: Abstract base class defining the `extract_all()` / `SyntaxError` contract and standard metadata (confidence 0.99, parse_method "native").
  - `PythonAstExtractor`: Reference implementation using Python's `ast` module — extracts functions (incl. async, multiline signatures, *args/**kwargs), classes (inheritance, nesting, dataclass), imports (absolute/relative), and call sites (with caller tracking).
- **`ParseMethod.NATIVE` enum value**: New top-priority parse method for native extraction results.
- **Degradation chain integration in `parse_file()`**: Python files automatically attempt native extraction first; `SyntaxError` triggers transparent fallback to tree-sitter with `fallback_reason` tracking.
- **Native extractor guide**: `docs/native-extractor-guide.md` — 5-step guide for adding new language extractors.
- 37 new test cases in `test_native_ast_extractor.py` covering functions, classes, imports, calls, edge cases, and degradation chain integration.
- Total test count: **487** (up from 475 in M1, +2.5%).

## [0.3.0] — M1: Regex Fallback + Tree-sitter Stabilization (2026-03-24)

### Added
- **Regex fallback engine**: When tree-sitter is unavailable or fails, CodeBook gracefully degrades to regex-based extraction instead of crashing.
  - `PythonRegexExtractor`: function/class/import extraction via indentation-based boundary detection
  - `TSRegexExtractor`: TypeScript/JavaScript support with arrow function and ES module detection
  - `GoRegexExtractor`: Go functions, method receivers, structs, and imports
  - `RustRegexExtractor`: Rust fn/struct/use extraction with pub visibility support
  - `JavaRegexExtractor`: Java method/class/import extraction with access modifier support
  - `GenericRegexExtractor`: Fallback for all other languages (30+) using common keyword patterns
- **`TreeSitterHealthCheck`**: Per-language availability detection with 5-minute TTL caching. Probes tree-sitter-language-pack on startup and caches the result.
- **`ParseResult` quality fields**: New `parse_method` (full/partial/basic/failed), `parse_confidence` (0.0-1.0), and `fallback_reason` fields for downstream transparency.
- **Parse quality summary in `scan_repo`**: Aggregates parse method statistics and emits warnings when >50% of files use simplified parsing.
- **`protocol` keyword support**: GenericRegexExtractor now recognizes Swift `protocol` declarations as class-like definitions.

### Changed
- **tree-sitter-language-pack is now an optional dependency**: Moved from `dependencies` to `[project.optional-dependencies] full`. Install with `pip install codebook-mcp[full]` for full tree-sitter support. Without it, the system runs in regex fallback mode.
- **Test compatibility**: All async tests updated from deprecated `asyncio.get_event_loop().run_until_complete()` to native `async def` / `await` for Python 3.14 compatibility.
- **Swift tests**: Now handle both tree-sitter and regex fallback modes gracefully.

### Fixed
- Python 3.14 `RuntimeError: There is no current event loop` in 14 async test methods.
- YAML round-trip test failures due to missing PyYAML dev dependency.

## [0.2.0] — Sprint 2: Self-Evolution Infrastructure (2026-03-23)

### Added
- **ProjectMemory**: Unified storage layer at `~/.codebook/memory/{repo_hash}/` with 5 JSON files for context, understanding, interactions, glossary, and metadata.
- **Term glossary system**: Four-layer resolution priority (user correction > project glossary > industry pack > global default). Includes `term_correct` and `memory_feedback` MCP tools.
- **Role system v0.3**: Three-view architecture (dev/pm/domain_expert) with backward compatibility mapping for legacy role names.
- **Parallel file traversal**: 128x speedup for scan_repo on large repositories.
- **Incremental scanning**: SHA256-based change detection, <30% changed files trigger incremental path.
- **Hotspot clustering**: Modules queried 3+ times automatically marked as hotspots.
- 428 tests (100% pass rate), up from 167 in v0.1.

## [0.1.0] — MCP v0.1: Core Engine (2026-03-22)

### Added
- Initial MCP Server with 5 core tools: `scan_repo`, `read_chapter`, `diagnose`, `ask_about`, `codegen`.
- Tree-sitter AST parsing for 30+ languages.
- NetworkX dependency graph construction with Mermaid diagram output.
- Role-based output adaptation (dev/pm/domain_expert/ceo/qa).
- 167 tests (99.3% pass rate).
