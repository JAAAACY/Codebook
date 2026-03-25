# Native Extractor Guide

## Overview

Native extractors are zero-dependency AST-based code analyzers that use a language's own standard-library parser (e.g., Python's `ast` module) instead of tree-sitter. They sit at the top of a three-level degradation chain:

1. **Native** (highest fidelity) — stdlib AST, confidence 0.99
2. **Tree-sitter** — universal parser, confidence 1.0
3. **Regex** (fallback) — pattern matching, confidence 0.5–0.8

If a native extractor raises `SyntaxError`, `parse_file()` falls through to tree-sitter automatically.

## Directory Structure

```
src/parsers/native_extractors/
├── __init__.py          # Re-exports all extractor classes
├── base.py              # BaseNativeExtractor abstract class
└── python_ast.py        # Reference implementation (Python)
```

## Interface Contract

```python
# base.py
class BaseNativeExtractor(ABC):
    language: str = ""
    confidence: float = 0.99
    parse_method: str = "native"

    @abstractmethod
    def extract_all(self, source: str, file_path: str) -> ParseResult:
        """Parse source and return a fully-populated ParseResult.
        Raises SyntaxError if the source cannot be parsed.
        """
```

## How to Add a New Language

### Step 1 — Create the extractor

Create `src/parsers/native_extractors/xxx_ast.py`:

```python
from src.parsers.ast_parser import (
    CallInfo, ClassInfo, FunctionInfo, ImportInfo, ParseResult,
)
from .base import BaseNativeExtractor

class XxxAstExtractor(BaseNativeExtractor):
    language: str = "xxx"

    def extract_all(self, source: str, file_path: str) -> ParseResult:
        # Parse using the language's stdlib parser.
        # Let SyntaxError propagate for unparseable files.
        tree = xxx_parse(source)
        # ... walk tree, collect functions/classes/imports/calls ...
        return ParseResult(
            file_path=file_path, language=self.language,
            classes=classes, functions=functions,
            imports=imports, calls=calls,
            line_count=line_count, parse_errors=[],
            parse_method=self.parse_method,
            parse_confidence=self.confidence,
            fallback_reason="",
        )
```

### Step 2 — Export from `__init__.py`

Add to `src/parsers/native_extractors/__init__.py`:

```python
from .xxx_ast import XxxAstExtractor
```

### Step 3 — Register in `parse_file()`

In `src/parsers/ast_parser.py`, add a block following the existing Python pattern:

```python
if file.language == "xxx":
    try:
        from src.parsers.native_extractors import XxxAstExtractor
        text = source.decode("utf-8", errors="replace")
        native_result = XxxAstExtractor().extract_all(text, file.path)
        # copy fields to result ...
        return result
    except SyntaxError as e:
        result.fallback_reason = f"ast parse error: {e}"
    except Exception as e:
        result.fallback_reason = f"native ast error: {e}"
```

### Step 4 — Update `ParseMethod` if needed

Add `"xxx"` to any parse-method enums or stats tracking that distinguishes native parsing.

### Step 5 — Write tests

Follow the patterns in `tests/test_native_ast_extractor.py`:

- Test basic extraction (functions, classes, imports, calls)
- Test edge cases (syntax errors, empty files, nested structures)
- Verify `parse_method == "native"` and `parse_confidence == 0.99`

## Reference Implementation

See `src/parsers/native_extractors/python_ast.py` — the canonical example covering functions, classes, imports, and call-site extraction.

## Data Classes

All defined in `src/parsers/ast_parser.py`:

| Class | Key Fields |
|-------|-----------|
| `FunctionInfo` | `name`, `params`, `return_type`, `line_start`, `line_end`, `docstring`, `is_method`, `parent_class` |
| `ClassInfo` | `name`, `methods`, `parent_class`, `line_start`, `line_end` |
| `ImportInfo` | `module`, `names`, `is_relative`, `line` |
| `CallInfo` | `caller_func`, `callee_name`, `line` |
| `ParseResult` | `file_path`, `language`, `classes`, `functions`, `imports`, `calls`, `line_count`, `parse_errors`, `parse_method`, `parse_confidence`, `fallback_reason` |
