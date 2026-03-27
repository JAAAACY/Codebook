"""codebook CLI — 一键安装 CodeBook MCP Server 到 AI 工具。

用法:
    codebook install          # 自动检测并配置所有支持的 AI 工具
    codebook install --target claude-desktop   # 只配置 Claude Desktop
    codebook install --target claude-code      # 只配置 Claude Code
    codebook install --target cursor           # 只配置 Cursor
    codebook uninstall        # 从所有已配置的工具中移除
    codebook status           # 显示当前安装状态
    codebook doctor           # 诊断环境问题
"""

import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


# ── 常量 ────────────────────────────────────────────────

APP_NAME = "CodeBook"
SERVER_NAME = "codebook"

# MCP 配置内容（stdio 模式）
def _build_mcp_config() -> dict:
    """构建 MCP Server 配置，自动定位 Python 和 server 路径。"""
    python_path = sys.executable
    # 找到 src/server.py 所在目录
    src_dir = Path(__file__).resolve().parent.parent
    return {
        "command": python_path,
        "args": ["-m", "src.server"],
        "cwd": str(src_dir),
    }


# ── 工具配置路径检测 ────────────────────────────────────

class ToolTarget:
    """一个 AI 工具的配置目标。"""

    def __init__(self, name: str, display_name: str, config_path: Path, key_path: str):
        self.name = name
        self.display_name = display_name
        self.config_path = config_path
        self.key_path = key_path  # JSON 路径到 mcpServers 的父级

    def exists(self) -> bool:
        """配置文件的父目录存在（说明工具已安装）。"""
        return self.config_path.parent.exists()


def _detect_targets() -> list[ToolTarget]:
    """检测当前系统上所有已安装的 AI 工具。"""
    system = platform.system()
    home = Path.home()
    targets: list[ToolTarget] = []

    # ── Claude Desktop ──
    if system == "Darwin":
        claude_config = home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    elif system == "Windows":
        claude_config = Path(os.environ.get("APPDATA", "")) / "Claude" / "claude_desktop_config.json"
    else:
        claude_config = home / ".config" / "Claude" / "claude_desktop_config.json"

    targets.append(ToolTarget(
        name="claude-desktop",
        display_name="Claude Desktop",
        config_path=claude_config,
        key_path="mcpServers",
    ))

    # ── Cursor ──
    if system == "Darwin":
        cursor_config = home / ".cursor" / "mcp.json"
    elif system == "Windows":
        cursor_config = home / ".cursor" / "mcp.json"
    else:
        cursor_config = home / ".cursor" / "mcp.json"

    targets.append(ToolTarget(
        name="cursor",
        display_name="Cursor",
        config_path=cursor_config,
        key_path="mcpServers",
    ))

    # ── Windsurf ──
    windsurf_config = home / ".codeium" / "windsurf" / "mcp_config.json"
    targets.append(ToolTarget(
        name="windsurf",
        display_name="Windsurf",
        config_path=windsurf_config,
        key_path="mcpServers",
    ))

    # ── VS Code (GitHub Copilot) ──
    if system == "Darwin":
        vscode_config = home / "Library" / "Application Support" / "Code" / "User" / "settings.json"
    elif system == "Windows":
        vscode_config = Path(os.environ.get("APPDATA", "")) / "Code" / "User" / "settings.json"
    else:
        vscode_config = home / ".config" / "Code" / "User" / "settings.json"

    targets.append(ToolTarget(
        name="vscode",
        display_name="VS Code (Copilot)",
        config_path=vscode_config,
        key_path="mcp.servers",  # VS Code 的 MCP 路径不同
    ))

    # ── Qwen Code (通义灵码) ──
    qwen_config = home / ".qwen" / "settings.json"
    targets.append(ToolTarget(
        name="qwen",
        display_name="Qwen Code",
        config_path=qwen_config,
        key_path="mcpServers",
    ))

    # ── Gemini CLI ──
    gemini_config = home / ".gemini" / "settings.json"
    targets.append(ToolTarget(
        name="gemini",
        display_name="Gemini CLI",
        config_path=gemini_config,
        key_path="mcpServers",
    ))

    # ── Codex CLI ──  (TOML 格式，特殊处理)
    codex_config = home / ".codex" / "config.toml"
    targets.append(ToolTarget(
        name="codex",
        display_name="Codex CLI",
        config_path=codex_config,
        key_path="mcp_servers",  # TOML table 路径
    ))

    # ── Trae（字节跳动，国内主流 AI IDE）──
    if system == "Darwin":
        trae_config = home / "Library" / "Application Support" / "Trae" / "User" / "mcp.json"
    elif system == "Windows":
        trae_config = Path(os.environ.get("APPDATA", "")) / "Trae" / "User" / "mcp.json"
    else:
        trae_config = home / ".config" / "Trae" / "User" / "mcp.json"

    targets.append(ToolTarget(
        name="trae",
        display_name="Trae (字节跳动)",
        config_path=trae_config,
        key_path="mcpServers",
    ))

    # ── Continue.dev（开源，常配合 DeepSeek/Ollama 使用）── YAML 格式
    continue_config = home / ".continue" / "config.yaml"
    targets.append(ToolTarget(
        name="continue",
        display_name="Continue.dev",
        config_path=continue_config,
        key_path="mcpServers",  # YAML 顶层键
    ))

    # -- Claude Code CLI --
    claude_code_config = home / ".claude" / ".mcp.json"
    targets.append(ToolTarget(
        name="claude-code",
        display_name="Claude Code",
        config_path=claude_code_config,
        key_path="mcpServers",
    ))

    return targets


# ── TOML 读写（Codex CLI 专用）─────────────────────────

def _read_toml(path: Path) -> dict:
    """安全读取 TOML 文件，不存在则返回空 dict。兼容 Python 3.10+。"""
    if not path.exists():
        return {}
    try:
        # Python 3.11+ 内置 tomllib
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib  # type: ignore[no-redef]
        with open(path, "rb") as f:
            return tomllib.load(f)
    except Exception:
        return {}


def _write_toml(path: Path, data: dict):
    """写入 TOML 文件。手动序列化，避免额外依赖。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []

    # 先写顶层简单键值
    for k, v in data.items():
        if not isinstance(v, dict):
            lines.append(f"{k} = {_toml_value(v)}")

    # 再写所有 table（嵌套 dict）
    for k, v in data.items():
        if isinstance(v, dict):
            _write_toml_table(lines, [k], v)

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
        f.write("\n")


def _write_toml_table(lines: list[str], path_parts: list[str], data: dict):
    """递归写入 TOML table。"""
    # 收集简单值和子 table
    simple_keys = {k: v for k, v in data.items() if not isinstance(v, dict)}
    sub_tables = {k: v for k, v in data.items() if isinstance(v, dict)}

    if simple_keys:
        lines.append("")
        lines.append(f"[{'.'.join(path_parts)}]")
        for k, v in simple_keys.items():
            lines.append(f"{k} = {_toml_value(v)}")

    for k, v in sub_tables.items():
        _write_toml_table(lines, path_parts + [k], v)


def _toml_value(v) -> str:
    """将 Python 值转为 TOML 值字符串。"""
    if isinstance(v, str):
        return json.dumps(v)  # JSON 双引号转义 == TOML 基本字符串
    elif isinstance(v, bool):
        return "true" if v else "false"
    elif isinstance(v, (int, float)):
        return str(v)
    elif isinstance(v, list):
        items = ", ".join(_toml_value(i) for i in v)
        return f"[{items}]"
    return json.dumps(str(v))


def _is_toml_target(target: "ToolTarget") -> bool:
    """判断目标是否使用 TOML 格式。"""
    return target.config_path.suffix == ".toml"


# ── YAML 读写（Continue.dev 专用）─────────────────────

def _read_yaml(path: Path) -> dict:
    """安全读取 YAML 文件。"""
    if not path.exists():
        return {}
    try:
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_yaml(path: Path, data: dict):
    """写入 YAML 文件，自动创建父目录。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import yaml
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    except ImportError:
        # 没有 PyYAML 则用简易 YAML 写入（仅支持 MCP 配置所需的结构）
        with open(path, "w", encoding="utf-8") as f:
            _write_simple_yaml(f, data, indent=0)


def _write_simple_yaml(f, data, indent: int):
    """极简 YAML 序列化，仅支持 dict/list/str/int/bool。"""
    prefix = "  " * indent
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, (dict, list)):
                f.write(f"{prefix}{k}:\n")
                _write_simple_yaml(f, v, indent + 1)
            else:
                f.write(f"{prefix}{k}: {_yaml_scalar(v)}\n")
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                f.write(f"{prefix}-\n")
                _write_simple_yaml(f, item, indent + 1)
            else:
                f.write(f"{prefix}- {_yaml_scalar(item)}\n")


def _yaml_scalar(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        if any(c in v for c in ":#{}[]&*!|>'\"@`"):
            return json.dumps(v)
        return v
    return str(v)


def _is_yaml_target(target: "ToolTarget") -> bool:
    """判断目标是否使用 YAML 格式。"""
    return target.config_path.suffix in (".yaml", ".yml")


# ── 配置读写（JSON）──────────────────────────────────────

def _read_json(path: Path) -> dict:
    """安全读取 JSON 文件，不存在则返回空 dict。"""
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _write_json(path: Path, data: dict):
    """写入 JSON 文件，自动创建父目录。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _set_nested(data: dict, key_path: str, key: str, value: dict):
    """在嵌套 dict 中设置值。key_path 用 . 分隔。"""
    parts = key_path.split(".")
    current = data
    for part in parts:
        if part not in current or not isinstance(current[part], dict):
            current[part] = {}
        current = current[part]
    current[key] = value


def _get_nested(data: dict, key_path: str) -> dict | None:
    """从嵌套 dict 中获取值。"""
    parts = key_path.split(".")
    current = data
    for part in parts:
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current if isinstance(current, dict) else None


def _remove_nested(data: dict, key_path: str, key: str) -> bool:
    """从嵌套 dict 中删除键。返回是否删除成功。"""
    container = _get_nested(data, key_path)
    if container and key in container:
        del container[key]
        return True
    return False


# ── 统一配置读写分发 ─────────────────────────────────

def _read_config(target: "ToolTarget") -> dict:
    """根据目标格式读取配置文件。"""
    if _is_toml_target(target):
        return _read_toml(target.config_path)
    elif _is_yaml_target(target):
        return _read_yaml(target.config_path)
    else:
        return _read_json(target.config_path)


def _write_config(target: "ToolTarget", data: dict):
    """根据目标格式写入配置文件。"""
    if _is_toml_target(target):
        _write_toml(target.config_path, data)
    elif _is_yaml_target(target):
        _write_yaml(target.config_path, data)
    else:
        _write_json(target.config_path, data)


# ── 核心命令 ──────────────────────────────────────────

def _get_tree_sitter_cache_dir() -> Path | None:
    """获取 tree-sitter-language-pack 的缓存目录。"""
    try:
        from tree_sitter_language_pack import cache_dir
        return Path(cache_dir())
    except Exception:
        pass
    # 手动推测常见缓存路径
    system = platform.system()
    home = Path.home()
    candidates = []
    if system == "Darwin":
        candidates.append(home / "Library" / "Caches" / "tree-sitter-language-pack")
    elif system == "Windows":
        local = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        candidates.append(local / "tree-sitter-language-pack" / "Cache")
    else:
        candidates.append(home / ".cache" / "tree-sitter-language-pack")
    for c in candidates:
        if c.exists():
            return c
    return None


def _clean_tree_sitter_cache(silent: bool = False) -> bool:
    """清理 tree-sitter-language-pack 的 grammar 缓存。"""
    # 方式 1：用包自带的 clean_cache()
    try:
        from tree_sitter_language_pack import clean_cache
        clean_cache()
        if not silent:
            print(f"  ✓ tree-sitter 缓存已清理（via clean_cache）")
        return True
    except Exception:
        pass

    # 方式 2：手动删除缓存目录
    cache = _get_tree_sitter_cache_dir()
    if cache and cache.exists():
        shutil.rmtree(cache, ignore_errors=True)
        if not silent:
            print(f"  ✓ tree-sitter 缓存已清理: {cache}")
        return True

    return False


def _probe_tree_sitter_grammars(tslp) -> tuple[int, list[str]]:
    """逐语言探测 tree-sitter grammar 可用性。返回 (ok_count, fail_langs)。"""
    test_languages = {
        "python":     b"def hello(): pass",
        "javascript": b"function hello() {}",
        "typescript": b"function hello(): void {}",
        "bash":       b"function hello() { echo hi; }",
        "go":         b"package main\nfunc hello() {}",
        "rust":       b"fn hello() {}",
        "java":       b"class A { void hello() {} }",
    }
    ok_count = 0
    fail_langs = []
    for lang, probe_code in test_languages.items():
        try:
            parser = tslp.get_parser(lang)
            tree = parser.parse(probe_code)
            if tree.root_node is not None:
                ok_count += 1
            else:
                fail_langs.append(lang)
        except Exception:
            fail_langs.append(lang)
    return ok_count, fail_langs


def _verify_tree_sitter():
    """安装后验证 tree-sitter 解析能力，检测降级风险。

    如果 grammar 加载失败（如 checksum mismatch），自动清缓存并重试。
    """
    print()
    print(f"  🔍 验证解析引擎")
    print(f"  {'─' * 40}")

    try:
        import tree_sitter_language_pack as tslp
    except ImportError:
        print(f"  ✗ tree-sitter-language-pack 未安装")
        print(f"    当前将使用正则 fallback（置信度 ≤0.7）")
        print(f"    修复: pip install tree-sitter-language-pack")
        print(f"  {'─' * 40}")
        return False

    # 第一轮探测
    ok_count, fail_langs = _probe_tree_sitter_grammars(tslp)

    # 如果有失败，可能是缓存损坏（checksum mismatch），自动清缓存重试
    if fail_langs:
        print(f"  ⚠ {len(fail_langs)} 种语言 grammar 加载失败，尝试清理缓存...")
        if _clean_tree_sitter_cache(silent=True):
            # 重新导入模块以拿到新的 grammar
            import importlib
            importlib.reload(tslp)
            ok_count, fail_langs = _probe_tree_sitter_grammars(tslp)
            if not fail_langs:
                print(f"  ✓ 缓存清理后恢复正常！")

    if not fail_langs:
        print(f"  ✓ tree-sitter 全部 {ok_count} 种语言可用（置信度 1.0）")
    else:
        print(f"  ✓ tree-sitter {ok_count}/{ok_count + len(fail_langs)} 种语言可用")
        print(f"  ⚠ 以下语言将使用正则 fallback: {', '.join(fail_langs)}")
        print(f"    修复: pip install tree-sitter-language-pack --force-reinstall --no-cache-dir")

    print(f"  {'─' * 40}")
    return len(fail_langs) == 0


def _install(target_filter: str | None = None):
    """安装 CodeBook MCP Server 到 AI 工具。"""
    mcp_config = _build_mcp_config()
    targets = _detect_targets()

    if target_filter:
        targets = [t for t in targets if t.name == target_filter]
        if not targets:
            print(f"\n  ✗ 未知的目标: {target_filter}")
            print(f"    支持的目标: claude-desktop, claude-code, cursor, windsurf, vscode, qwen, codex, gemini, trae, continue")
            return False

    print(f"\n  ⚡ CodeBook Installer")
    print(f"  {'─' * 40}")

    installed_count = 0
    skipped_count = 0

    for target in targets:
        if not target.exists():
            print(f"  ◻ {target.display_name:<20} 未安装，跳过")
            skipped_count += 1
            continue

        config = _read_config(target)
        existing = _get_nested(config, target.key_path)

        if existing and SERVER_NAME in existing:
            print(f"  ✓ {target.display_name:<20} 已配置，更新中...")
        else:
            print(f"  → {target.display_name:<20} 检测到，正在配置...")

        _set_nested(config, target.key_path, SERVER_NAME, mcp_config)
        _write_config(target, config)
        installed_count += 1
        print(f"  ✓ {target.display_name:<20} 配置完成 ✅")

    print(f"  {'─' * 40}")

    if installed_count == 0:
        print(f"  ✗ 未检测到任何已安装的 AI 工具")
        print(f"    请先安装 Claude Desktop、Cursor 或其他支持 MCP 的工具")
        return False

    print(f"  ✓ 已配置 {installed_count} 个工具")
    if skipped_count:
        print(f"  ◻ 跳过 {skipped_count} 个未安装的工具")
    print()
    # ── 安装后自动验证 tree-sitter 可用性 ──
    _verify_tree_sitter()

    print(f"  📋 下一步: 重启已配置的 AI 工具即可使用 CodeBook")
    print(f"  💡 验证: 在对话中输入 \"用 scan_repo 扫描一个 GitHub 项目\"")
    print()
    return True


def _uninstall():
    """从所有已配置的工具中移除 CodeBook。"""
    targets = _detect_targets()
    print(f"\n  🗑  CodeBook Uninstaller")
    print(f"  {'─' * 40}")

    removed = 0
    for target in targets:
        if not target.config_path.exists():
            continue

        config = _read_config(target)
        if _remove_nested(config, target.key_path, SERVER_NAME):
            _write_config(target, config)
            print(f"  ✓ {target.display_name:<20} 已移除")
            removed += 1

    # 清理 tree-sitter grammar 缓存
    cache_dir = _get_tree_sitter_cache_dir()
    if cache_dir and cache_dir.exists():
        cache_size_mb = sum(f.stat().st_size for f in cache_dir.rglob("*") if f.is_file()) / (1024 * 1024)
        shutil.rmtree(cache_dir, ignore_errors=True)
        print(f"  ✓ {'tree-sitter 缓存':<20} 已清理（{cache_size_mb:.1f} MB）")

    # 清理 CodeBook 项目记忆
    memory_dir = Path.home() / ".codebook"
    if memory_dir.exists():
        memory_size_mb = sum(f.stat().st_size for f in memory_dir.rglob("*") if f.is_file()) / (1024 * 1024)
        shutil.rmtree(memory_dir, ignore_errors=True)
        print(f"  ✓ {'项目记忆':<20} 已清理（{memory_size_mb:.1f} MB）")

    if removed == 0 and not (cache_dir and cache_dir.exists()):
        print(f"  ◻ 未找到任何已配置的 CodeBook 实例")
    else:
        print(f"  {'─' * 40}")
        print(f"  ✓ 已从 {removed} 个工具中移除 CodeBook")
        print(f"  📋 请重启相关工具以生效")
    print()


def _status():
    """显示当前安装状态。"""
    targets = _detect_targets()
    print(f"\n  📊 CodeBook 安装状态")
    print(f"  {'─' * 40}")

    for target in targets:
        if not target.exists():
            print(f"  ◻ {target.display_name:<20} 工具未安装")
            continue

        config = _read_config(target)
        existing = _get_nested(config, target.key_path)
        if existing and SERVER_NAME in existing:
            print(f"  ✓ {target.display_name:<20} 已配置 ✅")
        else:
            print(f"  ○ {target.display_name:<20} 未配置")

    print()


def _doctor():
    """诊断环境问题。"""
    print(f"\n  🩺 CodeBook 环境诊断")
    print(f"  {'─' * 40}")

    # Python 版本
    py_version = sys.version.split()[0]
    py_ok = sys.version_info >= (3, 10)
    print(f"  {'✓' if py_ok else '✗'} Python {py_version:<15} {'OK' if py_ok else '需要 3.10+'}")

    # Git
    git_ok = shutil.which("git") is not None
    print(f"  {'✓' if git_ok else '✗'} Git{'':17} {'OK' if git_ok else '未安装'}")

    # tree-sitter（不仅检查 import，还检查 grammar 是否真正可加载）
    ts_ok = False
    try:
        import tree_sitter_language_pack as tslp
        tslp.get_language("python")
        ts_ok = True
    except ImportError:
        pass
    except Exception as e:
        # import 成功但 grammar 加载失败（如 checksum mismatch）
        err_name = type(e).__name__
        print(f"  ✗ tree-sitter{'':8} 已安装但 grammar 损坏（{err_name}）")
        print(f"    修复: python3 -c \"from tree_sitter_language_pack import clean_cache; clean_cache()\"")
        print(f"          pip install tree-sitter-language-pack --upgrade --no-cache-dir")
    if ts_ok:
        print(f"  ✓ tree-sitter{'':8} OK")
    elif 'tslp' not in dir():
        print(f"  ✗ tree-sitter{'':8} 未安装：pip install tree-sitter-language-pack")

    # MCP
    try:
        import mcp
        mcp_ok = True
    except ImportError:
        mcp_ok = False
    print(f"  {'✓' if mcp_ok else '✗'} mcp{'':18} {'OK' if mcp_ok else '未安装：pip install mcp[cli]'}")

    # networkx
    try:
        import networkx
        nx_ok = True
    except ImportError:
        nx_ok = False
    print(f"  {'✓' if nx_ok else '✗'} networkx{'':13} {'OK' if nx_ok else '未安装：pip install networkx'}")

    all_ok = py_ok and git_ok and ts_ok and mcp_ok and nx_ok
    print(f"  {'─' * 40}")

    # ── 网络诊断（中国地区适配）──
    print(f"\n  🌐 网络连通性")
    print(f"  {'─' * 40}")
    cn_mode = _detect_china_network()

    if all_ok:
        print(f"  ✓ 所有依赖就绪，可以运行 codebook install")
    else:
        print(f"  ✗ 部分依赖缺失，请先安装缺失项")
        if cn_mode:
            print(f"    快速修复（国内镜像）:")
            print(f"    pip install codebook-mcp -i https://pypi.tuna.tsinghua.edu.cn/simple/")
        else:
            print(f"    快速修复: pip install codebook-mcp")
    print()
    return all_ok


# ── 中国网络适配 ──────────────────────────────────────

# 国内镜像源
CN_PIP_MIRRORS = {
    "清华": "https://pypi.tuna.tsinghua.edu.cn/simple/",
    "阿里云": "https://mirrors.aliyun.com/pypi/simple/",
    "中科大": "https://pypi.mirrors.ustc.edu.cn/simple/",
}
CN_NPM_MIRROR = "https://registry.npmmirror.com"
CN_GIT_MIRRORS = {
    "github.com": "https://ghproxy.com/https://github.com",  # ghproxy 加速
}


def _detect_china_network() -> bool:
    """检测是否在中国网络环境下（GitHub/PyPI 连通性差）。"""
    import urllib.request

    # 测试 GitHub 连通性
    github_ok = False
    try:
        req = urllib.request.Request("https://github.com", method="HEAD")
        urllib.request.urlopen(req, timeout=5)
        github_ok = True
        print(f"  ✓ GitHub{'':13} 可访问")
    except Exception:
        print(f"  ✗ GitHub{'':13} 不可访问（建议使用 --cn 模式）")

    # 测试 PyPI
    pypi_ok = False
    try:
        req = urllib.request.Request("https://pypi.org", method="HEAD")
        urllib.request.urlopen(req, timeout=5)
        pypi_ok = True
        print(f"  ✓ PyPI{'':15} 可访问")
    except Exception:
        print(f"  ✗ PyPI{'':15} 不可访问（建议: pip install -i 清华镜像）")

    # 测试清华镜像
    tuna_ok = False
    try:
        req = urllib.request.Request("https://pypi.tuna.tsinghua.edu.cn", method="HEAD")
        urllib.request.urlopen(req, timeout=5)
        tuna_ok = True
        print(f"  ✓ 清华镜像{'':11} 可访问 ✅")
    except Exception:
        print(f"  ○ 清华镜像{'':11} 不可访问")

    is_cn = not github_ok or not pypi_ok
    if is_cn:
        print(f"  {'─' * 40}")
        print(f"  📍 检测到国内网络环境，建议:")
        print(f"     pip install codebook-mcp -i https://pypi.tuna.tsinghua.edu.cn/simple/")
        print(f"     codebook install --cn")
    print(f"  {'─' * 40}")
    return is_cn


def _install_cn_deps():
    """使用国内镜像安装所有依赖。"""
    mirror = CN_PIP_MIRRORS["清华"]
    print(f"\n  🇨🇳 使用清华镜像安装依赖...")
    print(f"  {'─' * 40}")

    deps = [
        "tree-sitter-language-pack",
        "mcp[cli]",
        "networkx",
        "structlog",
        "pydantic-settings",
    ]

    for dep in deps:
        print(f"  → 安装 {dep}...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", dep, "-i", mirror,
             "--trusted-host", "pypi.tuna.tsinghua.edu.cn", "-q"],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            print(f"  ✓ {dep} 安装完成")
        else:
            print(f"  ✗ {dep} 安装失败: {result.stderr.strip()[:100]}")

    print(f"  {'─' * 40}")
    print(f"  ✓ 依赖安装完成，开始配置 AI 工具...")
    print()


# ── 入口 ──────────────────────────────────────────────

USAGE = """
  ⚡ CodeBook — 让不会写代码的人也能理解软件项目

  用法:
    codebook install [--target <tool>]   配置 AI 工具连接 CodeBook
    codebook install --cn                使用国内镜像安装依赖后配置
    codebook uninstall                   移除 CodeBook 配置
    codebook status                      查看安装状态
    codebook doctor                      诊断环境问题（中国地区自动检测网络）
    codebook server                      启动 MCP Server（通常由 AI 工具自动调用）

  支持的 --target:
    claude-desktop    Claude Desktop 桌面应用
    claude-code       Claude Code CLI
    cursor            Cursor 编辑器
    windsurf          Windsurf 编辑器
    vscode            VS Code (GitHub Copilot)
    qwen              Qwen Code (通义灵码)
    codex             Codex CLI (OpenAI)
    gemini            Gemini CLI (Google)
    trae              Trae (字节跳动 AI IDE)
    continue          Continue.dev (开源，配合 DeepSeek/Ollama)

  示例:
    pip install codebook-mcp && codebook install
    pip install codebook-mcp -i https://pypi.tuna.tsinghua.edu.cn/simple/ && codebook install --cn
"""


def cli_main():
    """CLI 入口点。"""
    args = sys.argv[1:]

    if not args or args[0] in ("-h", "--help", "help"):
        print(USAGE)
        return

    command = args[0]

    if command == "install":
        cn_mode = "--cn" in args

        target = None
        if "--target" in args:
            idx = args.index("--target")
            if idx + 1 < len(args):
                target = args[idx + 1]

        # 国内镜像模式：先安装依赖再配置
        if cn_mode:
            _install_cn_deps()

        _install(target_filter=target)

    elif command == "uninstall":
        _uninstall()

    elif command == "status":
        _status()

    elif command == "doctor":
        _doctor()

    elif command == "server":
        # 直接启动 MCP Server
        from src.server import main
        main()

    else:
        print(f"\n  ✗ 未知命令: {command}")
        print(USAGE)


if __name__ == "__main__":
    cli_main()
