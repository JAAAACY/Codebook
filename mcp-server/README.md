# CodeBook MCP Server

让不会写代码的人也能理解、诊断和修改软件产品的 MCP 工具。

## 快速开始

```bash
cd mcp-server

# 安装依赖（macOS 请用 pip3）
pip3 install -e ".[dev]"

# 启动 MCP Server（stdio 模式，供 Claude Desktop 使用）
python3 -m src.server

# 或使用 entry point
codebook
```

## 配置 MCP 客户端

### Claude Desktop

编辑 `~/Library/Application Support/Claude/claude_desktop_config.json`：

```json
{
  "mcpServers": {
    "codebook": {
      "command": "codebook-server"
    }
  }
}
```

### Claude Code (CLI)

```bash
claude mcp add codebook -- codebook-server
```

## 可用工具

| 工具 | 说明 | 对应能力 |
|------|------|----------|
| `scan_repo` | 扫描项目，生成蓝图总览 + Mermaid 依赖图 | 蓝图 + 看懂 |
| `read_chapter` | 查看指定模块的详细卡片 | 看懂 |
| `diagnose` | 自然语言描述问题 → 追踪调用链 → 定位代码 | 定位 |
| `ask_about` | 针对模块进行多轮追问 | 追问 |

## 运行测试

```bash
pytest tests/ -v
```

## 项目结构

```
mcp-server/
├── src/
│   ├── server.py          # MCP Server 入口
│   ├── config.py          # pydantic-settings 配置
│   ├── tools/             # 4 个核心工具
│   ├── parsers/           # Tree-sitter 代码解析（Phase 1.2）
│   ├── prompts/           # Prompt 模板管理（Phase 1.3）
│   ├── summarizer/        # 模块卡片生成引擎（Phase 1.3）
│   └── diagnoser/         # 问题定位引擎（Phase 1.5）
├── tests/
├── pyproject.toml
└── README.md
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `CODEBOOK_LOG_LEVEL` | `INFO` | 日志级别 |
| `CODEBOOK_MAX_REPO_SIZE_MB` | `100` | 最大仓库大小限制 |

> **注意：** 不需要设置 `ANTHROPIC_API_KEY`。CodeBook 作为 MCP Server 运行在 Claude Desktop 内部，由宿主 LLM 直接推理，无需额外 API 调用。
