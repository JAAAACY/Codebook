# CodeBook — The Code Understanding Layer

[![Tests](https://github.com/codebook-app/codebook/actions/workflows/test.yml/badge.svg)](https://github.com/codebook-app/codebook/actions/workflows/test.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

CodeBook is a universal translation layer for software code — an MCP Server that bridges non-technical stakeholders (PMs, domain experts, managers) and developers by understanding code intent through natural language and providing clear, role-specific insights into complex systems.

## What is CodeBook?

CodeBook enables anyone to understand, diagnose, and propose changes to software systems without writing code. It transforms code repositories into structured, queryable knowledge that adapts its explanations based on your role.

**Core capabilities:**
1. **Blueprint Scanning** — Analyze entire codebases and create visual dependency maps
2. **Module Understanding** — Deep dive into specific components with contextual summaries
3. **Problem Diagnosis** — Trace code paths to pinpoint bugs or understand functionality
4. **Interactive Q&A** — Ask domain-specific questions and get structured answers
5. **Code Generation** — Propose changes with unified diffs and impact analysis

**Target Users:**
- **Developers** — Understand new projects and unfamiliar modules faster
- **Project Managers** — See architectural dependencies and change impact in business terms
- **Domain Experts** — Verify implementations match domain requirements
- **QA/DevOps** — Track system health and change coverage

## Installation

### Prerequisites
- Python 3.10 or higher
- pip or uv

### Quick Start

```bash
# Clone the repository
git clone https://github.com/codebook-app/codebook.git
cd codebook

# Install the MCP server
cd mcp-server
pip install -e ".[dev]"

# Verify installation
python -m pytest tests/ -q
```

### Integration with Claude Desktop

CodeBook runs as an MCP Server, providing instant access within Claude Desktop or other MCP-compatible applications.

Edit your MCP configuration file (typically `~/.claude_desktop_config.json` or platform-specific equivalent):

```json
{
  "mcpServers": {
    "codebook": {
      "command": "python",
      "args": ["-m", "src.server"],
      "cwd": "/path/to/codebook/mcp-server"
    }
  }
}
```

Then restart Claude Desktop to activate the tools.

## 7 Core Tools

### 1. **scan_repo**
Analyzes a Git repository to create a blueprint overview with module grouping and dependency visualization.

**Inputs:**
- `repo_url` (string) — HTTPS Git URL
- `role` (string) — "dev" | "pm" | "domain_expert" (controls output language style)
- `depth` (string) — "overview" (lightweight blueprint) | "detailed" (all module cards)

**Outputs:**
- Module list with file counts and public interfaces
- NetworkX-based dependency graph
- Mermaid diagram for visualization
- Repository statistics (functions, classes, imports, calls)

**Example:**
```json
{
  "repo_url": "https://github.com/fastapi/fastapi.git",
  "role": "pm",
  "depth": "overview"
}
```

### 2. **read_chapter**
Deep-dive into a specific module with function signatures, class definitions, call relationships, and contextual summaries.

**Inputs:**
- `module_name` (string) — Name of the logical module (e.g., "authentication", "database")
- `role` (string) — "dev" | "pm" | "domain_expert"

**Outputs:**
- Module summary (translated to role perspective)
- Module cards (per-file functions/classes/calls)
- Dependency graph for this module

**Example:**
```json
{
  "module_name": "authentication",
  "role": "domain_expert"
}
```

### 3. **diagnose**
Trace code paths from natural language problem descriptions to exact file locations and call chains.

**Inputs:**
- `query` (string) — Natural language description (e.g., "Where does the login timeout error get triggered?")
- `module_name` (string) — Optional scope restriction
- `role` (string) — "dev" | "pm" | "domain_expert"

**Outputs:**
- Matched nodes (functions/classes that fit the query)
- Call chain (Mermaid sequence diagram)
- Exact file:line locations

**Example:**
```json
{
  "query": "How is user authentication verified during login?",
  "module_name": "auth",
  "role": "domain_expert"
}
```

### 4. **ask_about**
Multi-turn conversation about a module, combining code context with LLM reasoning for complex questions.

**Inputs:**
- `module_name` (string) — Target module
- `question` (string) — Natural language question
- `conversation_history` (array, optional) — Prior Q&A turns
- `role` (string) — "ceo" | "pm" | "dev" | "qa"

**Outputs:**
- Structured context (code snippets, dependencies)
- Guidance for the host LLM
- Modules referenced in the answer

**Example:**
```json
{
  "module_name": "payment_processor",
  "question": "What happens when a payment fails?",
  "role": "pm",
  "conversation_history": []
}
```

### 5. **codegen**
Proposes code changes based on natural language instructions, with validation and blast radius analysis.

**Inputs:**
- `instruction` (string) — What to change (e.g., "Rename getUserById to getUser across all files")
- `repo_path` (string) — Local path to cloned repository
- `locate_result` (object, optional) — Diagnostic output from prior tools
- `role` (string) — "dev" | "pm"

**Outputs:**
- Change summary (human-readable)
- Unified diff (apply with `patch -p1`)
- Blast radius (affected modules)
- Verification steps

**Example:**
```json
{
  "instruction": "Add error handling for network timeouts in the API client",
  "repo_path": "/path/to/repo",
  "role": "dev"
}
```

### 6. **term_correct** (Optional)
Normalizes domain terminology across different naming conventions (internal vocabulary builder).

### 7. **memory_feedback** (Optional)
Logs user annotations to improve future explanations (data flywheel for semantic learning).

## Role System: Adapting Output to Your Perspective

CodeBook outputs change based on your role:

| Role | Best For | Output Style |
|------|----------|--------------|
| **dev** | Developers | Technical, mentions function signatures, call chains, implementation details |
| **pm** | Project Managers | Business impact, module boundaries, change risks, team communication |
| **domain_expert** | Subject Matter Experts | Domain terminology, business rules validation, regulatory/compliance concerns |
| **ceo** | Leadership | Executive summary, strategic implications, resource impact |
| **qa** | QA/Testers | Test coverage, edge cases, integration points |

Each tool translates its output to match your role's needs without changing the underlying analysis.

## Configuration

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `CODEBOOK_LOG_LEVEL` | `INFO` | Logging verbosity (DEBUG, INFO, WARNING, ERROR) |
| `CODEBOOK_MAX_REPO_SIZE_MB` | `100` | Maximum repository size to analyze |
| `CODEBOOK_CACHE_DIR` | `~/.codebook/` | Local cache for parsed repositories |

### Prompt Configuration

CodeBook uses structured prompt templates in `mcp-server/src/config/` to generate role-specific explanations. Edit these to customize output style for your organization.

## Architecture Overview

```
User Input (natural language query)
    ↓
[MCP Server Layer] ── Routes requests to appropriate tool
    ↓
[Code Analysis Layer] ── Tree-sitter AST parsing + regex fallback
    ↓                     (graceful degradation when tree-sitter unavailable)
    ↓
[Role Adapter Layer] ── Translates technical details to user role perspective
    ↓
[Output Formatter] ── Mermaid diagrams, JSON, unified diffs
```

CodeBook does not train custom models. It leverages high-quality LLM reasoning (via the MCP host) combined with precise code analysis to deliver accurate insights.

## Graceful Degradation

CodeBook uses a two-tier parsing strategy to ensure reliability:

1. **Full mode** (tree-sitter): High-fidelity AST parsing with complete function signatures, class hierarchies, call chains, and scope tracking. Requires `tree-sitter-language-pack`.
2. **Partial mode** (regex fallback): When tree-sitter is unavailable or fails for a specific language, CodeBook automatically falls back to regex-based extraction. This captures top-level functions, classes, imports, and basic call patterns.

Each parsed file includes a `parse_method` field (`full` / `partial` / `basic` / `failed`) so downstream tools and users know the precision level. When more than 50% of files use simplified parsing, scan results include a warning.

`tree-sitter-language-pack` is a **core dependency** and will be installed automatically with `pip install -e .` or `pip install codebook-mcp`. After installation, run `codebook doctor` to verify all language parsers are available.

If tree-sitter is missing or a specific language grammar fails to load at runtime, the system automatically falls back to regex extraction — it never crashes, and always produces usable results at the best available precision level.

## Testing

All 396 tests pass (100% coverage of core features):

```bash
cd mcp-server

# Run all tests
python -m pytest tests/ -v

# Run specific test module
python -m pytest tests/test_scan_repo.py -v

# Run with coverage
python -m pytest tests/ --cov=src --cov-report=html
```

Tests include:
- **Acceptance tests** — Full end-to-end workflows with real codebases
- **Unit tests** — Parser, graph, summarizer, and tool logic
- **Integration tests** — Tool interaction with caching and role adaptation

## Development Workflow

### Project Structure

```
codebook/
├── .github/
│   └── workflows/
│       └── test.yml              # GitHub Actions CI pipeline
├── mcp-server/                   # Main MCP server package
│   ├── src/
│   │   ├── server.py             # MCP entry point
│   │   ├── tools/                # 7 tool implementations
│   │   ├── parsers/              # Code analysis (AST, modules, dependencies)
│   │   ├── summarizer/           # Module card generation
│   │   ├── memory/               # Project memory & data flywheel
│   │   └── config/               # Prompt templates
│   ├── tests/                    # 396 tests
│   ├── pyproject.toml            # Dependencies and build config
│   └── README.md                 # Server-specific documentation
├── files/                        # Design documents
│   ├── CLAUDE.md                 # Immutable project rules
│   ├── CONTEXT.md                # Dynamic development status
│   └── INTERFACES.md             # Data structure contracts
└── docs/                         # User guides and API reference
```

### Code Standards

- **Language**: Python 3.10+
- **Testing**: pytest with 99%+ pass rate
- **Logging**: structlog (no print statements)
- **Type Safety**: Full type hints on public APIs
- **Dependencies**: Tree-sitter (parsing), NetworkX (graphs), FastMCP (server)

### Making Changes

1. Create a feature branch
2. Edit code in `mcp-server/src/`
3. Add tests in `mcp-server/tests/`
4. Run `pytest tests/ -q` to verify
5. Create a pull request with description

## Contributing

We welcome contributions! Please:

1. **Fork** the repository
2. **Create a feature branch**: `git checkout -b feature/your-feature`
3. **Write tests** for new functionality (CodeBook aims for 99%+ test coverage)
4. **Follow code style** — PEP 8, type hints, structlog for logging
5. **Document changes** in code comments and commit messages
6. **Push and open a Pull Request** with a clear description

### Contributing Guidelines

- Keep commits atomic and well-described
- Update INTERFACES.md if you modify tool contracts
- Run full test suite before submitting: `pytest tests/ -q`
- Avoid external API calls in tests; use fixtures and mocks

## License

CodeBook is released under the [MIT License](LICENSE). See the LICENSE file for full terms.

## Roadmap

- **Q2 2026**: Web UI for non-developer stakeholders
- **Q3 2026**: Integration with CI/CD pipelines (GitHub Actions, GitLab CI)
- **Q4 2026**: Custom domain terminology learning (data flywheel v2)

## Support

- **Documentation**: [codebook.app/docs](https://codebook.app/docs)
- **Issues**: [GitHub Issues](https://github.com/codebook-app/codebook/issues)
- **Discussions**: [GitHub Discussions](https://github.com/codebook-app/codebook/discussions)

---

**CodeBook** — Making code transparent to everyone.
