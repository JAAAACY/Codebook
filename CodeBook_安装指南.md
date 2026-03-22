# CodeBook MCP Server 安装指南

## 环境要求

Python 3.10 以上，Git 已安装。不需要任何 API Key。

## 安装

```bash
cd mcp-server
pip install -e ".[dev]"
```

安装完成后验证一下：

```bash
pytest tests/ -v --tb=short
```

预期结果：142 passed, 25 skipped, 0 failed。

## 连接 Claude Desktop

编辑配置文件：

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- Linux: `~/.config/Claude/claude_desktop_config.json`

写入以下内容（把路径改成你自己的）：

```json
{
  "mcpServers": {
    "codebook": {
      "command": "python",
      "args": ["-m", "src.server"],
      "cwd": "/你的路径/mcp-server"
    }
  }
}
```

保存后重启 Claude Desktop。输入框旁边出现锤子图标就说明连上了。

## 验证连接

点击锤子图标，应该能看到 5 个工具：scan_repo、read_chapter、diagnose、ask_about、codegen。

随便试一个：在对话里说"用 scan_repo 扫描 https://github.com/某个小项目"，能返回架构蓝图就说明一切正常。

## 可选配置

通过环境变量或 `.env` 文件调整，一般不需要改：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| CODEBOOK_LOG_LEVEL | INFO | 改成 DEBUG 可看详细日志 |
| CODEBOOK_MAX_REPO_SIZE_MB | 100 | 仓库大小上限 |
| CODEBOOK_CLONE_TIMEOUT_SECONDS | 120 | Git clone 超时时间 |

## 常见问题

**锤子图标没出现：** 检查 cwd 路径是否正确，在终端里 cd 到那个目录运行 `python -c "from src.server import mcp; print('OK')"` 看看能不能正常导入。

**扫描超时：** 仓库太大或网络慢，把 CODEBOOK_CLONE_TIMEOUT_SECONDS 调大。

**模块找不到：** read_chapter 支持模糊匹配，试试用目录名或部分名称。
