"""repo_cloner — 克隆 Git 仓库并过滤非代码文件。"""

import asyncio
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import structlog

from src.config import settings

logger = structlog.get_logger()

# ── 过滤规则 ─────────────────────────────────────────────

EXCLUDED_DIRS = {
    ".git", "node_modules", "venv", ".venv", "__pycache__",
    ".next", "dist", "build", ".tox", ".mypy_cache", ".pytest_cache",
    "eggs", "*.egg-info", ".eggs", "vendor", "target",
}

EXCLUDED_EXTENSIONS = {
    # 图片 / 字体 / 多媒体
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".bmp", ".webp",
    ".ttf", ".otf", ".woff", ".woff2", ".eot",
    ".mp4", ".mp3", ".wav", ".avi", ".mov",
    # 二进制 / 压缩
    ".pyc", ".pyo", ".so", ".o", ".dll", ".exe", ".wasm",
    ".zip", ".tar", ".gz", ".bz2", ".7z", ".jar",
    # 数据
    ".sqlite", ".db", ".sqlite3",
}

EXCLUDED_FILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "Pipfile.lock", "poetry.lock", "composer.lock",
    "Gemfile.lock", "Cargo.lock",
}

CODE_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx",
    ".java", ".go", ".rs", ".cpp", ".c", ".h", ".hpp",
    ".cs", ".rb", ".php", ".swift", ".kt",
}

CONFIG_EXTENSIONS = {
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".env.example",
}

EXTENSION_TO_LANGUAGE = {
    ".py": "python",
    ".ts": "typescript", ".tsx": "typescript",
    ".js": "javascript", ".jsx": "javascript",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".cpp": "cpp", ".c": "cpp", ".h": "cpp", ".hpp": "cpp",
    ".cs": "c_sharp",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
}


# ── 数据类 ──────────────────────────────────────────────

@dataclass
class FileInfo:
    """一个源代码文件的基本信息。"""
    path: str  # 相对于仓库根目录的路径
    abs_path: str  # 绝对路径
    language: str  # tree-sitter 语言名
    size_bytes: int
    line_count: int
    is_config: bool = False


@dataclass
class CloneResult:
    """克隆结果。"""
    repo_path: str
    files: list[FileInfo] = field(default_factory=list)
    languages: dict[str, int] = field(default_factory=dict)  # language -> file count
    total_lines: int = 0
    skipped_count: int = 0


# ── 核心函数 ─────────────────────────────────────────────

def _should_skip_dir(dir_name: str) -> bool:
    """判断是否跳过目录。"""
    if dir_name.startswith("."):
        return True
    if dir_name in EXCLUDED_DIRS:
        return True
    if dir_name.endswith(".egg-info"):
        return True
    return False


def _count_lines(file_path: str) -> int:
    """快速统计文件行数。"""
    try:
        with open(file_path, "rb") as f:
            return sum(1 for _ in f)
    except (OSError, UnicodeDecodeError):
        return 0


def _scan_files(repo_path: str) -> tuple[list[FileInfo], int]:
    """扫描仓库目录，返回文件列表和跳过文件数。"""
    files: list[FileInfo] = []
    skipped = 0
    repo_root = Path(repo_path)

    for dirpath, dirnames, filenames in os.walk(repo_path):
        # 原地修改 dirnames 以跳过排除目录
        dirnames[:] = [d for d in dirnames if not _should_skip_dir(d)]

        for fname in filenames:
            # 排除特定文件名
            if fname in EXCLUDED_FILES:
                skipped += 1
                continue

            ext = Path(fname).suffix.lower()

            # 排除特定扩展名
            if ext in EXCLUDED_EXTENSIONS:
                skipped += 1
                continue

            abs_path = os.path.join(dirpath, fname)
            rel_path = os.path.relpath(abs_path, repo_path)

            # 判断是代码还是配置
            is_config = ext in CONFIG_EXTENSIONS
            is_code = ext in CODE_EXTENSIONS

            if not is_code and not is_config:
                skipped += 1
                continue

            language = EXTENSION_TO_LANGUAGE.get(ext, "unknown")
            size_bytes = os.path.getsize(abs_path)
            line_count = _count_lines(abs_path)

            files.append(FileInfo(
                path=rel_path,
                abs_path=abs_path,
                language=language,
                size_bytes=size_bytes,
                line_count=line_count,
                is_config=is_config,
            ))

    return files, skipped


async def clone_repo(url: str, target_dir: str | None = None) -> CloneResult:
    """克隆 Git 仓库，过滤非代码文件。

    Args:
        url: Git 仓库地址（HTTPS 格式）或本地目录路径。
        target_dir: 克隆目标目录。为 None 时使用临时目录。

    Returns:
        CloneResult 包含文件列表、语言统计、总行数。
    """
    # 如果 url 是本地目录，直接扫描
    if os.path.isdir(url):
        logger.info("scan_local_dir", path=url)
        repo_path = url
    else:
        # Git 克隆
        if target_dir is None:
            os.makedirs(settings.cache_dir, exist_ok=True)
            target_dir = tempfile.mkdtemp(prefix="codebook_", dir=settings.cache_dir)

        logger.info("clone_repo.start", url=url, target=target_dir)
        proc = await asyncio.create_subprocess_exec(
            "git", "clone", "--depth=1", "--single-branch", url, target_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=settings.clone_timeout_seconds,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"git clone failed: {stderr.decode()}")
        repo_path = target_dir
        logger.info("clone_repo.done", path=repo_path)

    # 扫描文件
    files, skipped = _scan_files(repo_path)

    # 语言统计
    languages: dict[str, int] = {}
    total_lines = 0
    for f in files:
        if not f.is_config:
            languages[f.language] = languages.get(f.language, 0) + 1
            total_lines += f.line_count

    result = CloneResult(
        repo_path=repo_path,
        files=files,
        languages=languages,
        total_lines=total_lines,
        skipped_count=skipped,
    )
    logger.info(
        "scan.summary",
        code_files=len([f for f in files if not f.is_config]),
        config_files=len([f for f in files if f.is_config]),
        languages=languages,
        total_lines=total_lines,
        skipped=skipped,
    )
    return result
