# Changelog

All notable changes to CodeBook will be documented in this file.

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
