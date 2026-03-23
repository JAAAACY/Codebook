"""repo_cloner — 克隆 Git 仓库并过滤非代码文件。"""

import asyncio
import os
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    ".cs": "csharp",
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


def _scan_directory(dirpath: str, repo_path: str, max_files: int = 5000) -> tuple[list[FileInfo], int, bool]:
    """扫描单个目录，返回文件列表、跳过计数和是否超过限制。

    Args:
        dirpath: 目录路径
        repo_path: 仓库根路径
        max_files: 最大文件数限制（达到后停止扫描）

    Returns:
        (文件列表, 跳过数, 是否超出限制)
    """
    files: list[FileInfo] = []
    skipped = 0

    try:
        entries = os.listdir(dirpath)
    except (OSError, PermissionError):
        return [], 0, False

    for entry in entries:
        abs_entry = os.path.join(dirpath, entry)

        # 跳过排除目录
        if os.path.isdir(abs_entry) and _should_skip_dir(entry):
            continue

        if not os.path.isfile(abs_entry):
            continue

        # 排除特定文件名
        if entry in EXCLUDED_FILES:
            skipped += 1
            continue

        ext = Path(entry).suffix.lower()

        # 排除特定扩展名
        if ext in EXCLUDED_EXTENSIONS:
            skipped += 1
            continue

        rel_path = os.path.relpath(abs_entry, repo_path)

        # 判断是代码还是配置
        is_config = ext in CONFIG_EXTENSIONS
        is_code = ext in CODE_EXTENSIONS

        if not is_code and not is_config:
            skipped += 1
            continue

        language = EXTENSION_TO_LANGUAGE.get(ext, "unknown")
        try:
            size_bytes = os.path.getsize(abs_entry)
            line_count = _count_lines(abs_entry)
        except (OSError, PermissionError):
            skipped += 1
            continue

        files.append(FileInfo(
            path=rel_path,
            abs_path=abs_entry,
            language=language,
            size_bytes=size_bytes,
            line_count=line_count,
            is_config=is_config,
        ))

        if len(files) >= max_files:
            return files, skipped, True

    return files, skipped, False


def _scan_files_parallel(repo_path: str, max_files: int = 5000) -> tuple[list[FileInfo], int]:
    """使用并行遍历扫描仓库目录（针对大型仓库优化）。

    Args:
        repo_path: 仓库路径
        max_files: 最大扫描文件数（在 overview 模式下限制为 5000 以避免超时）

    Returns:
        (文件列表, 跳过文件数)
    """
    all_files: list[FileInfo] = []
    total_skipped = 0
    hit_limit = False

    # 线程安全的锁，用于保护共享列表
    files_lock = threading.Lock()

    # 收集所有顶级目录（排除大型目录如 node_modules, .git）
    try:
        entries = os.listdir(repo_path)
    except (OSError, PermissionError):
        logger.warning("scan_files.permission_denied", path=repo_path)
        return [], 0

    dirs_to_scan = []
    for entry in entries:
        abs_entry = os.path.join(repo_path, entry)
        if os.path.isdir(abs_entry) and not _should_skip_dir(entry):
            dirs_to_scan.append(abs_entry)

    # 添加仓库根目录本身
    dirs_to_scan.insert(0, repo_path)

    def scan_with_recursion(dirpath: str) -> tuple[list[FileInfo], int]:
        """递归扫描目录树（使用 os.walk，但对每层目录进行并行处理）。"""
        local_files: list[FileInfo] = []
        local_skipped = 0

        for root, dirnames, filenames in os.walk(dirpath):
            # 原地修改 dirnames 以跳过排除目录
            dirnames[:] = [d for d in dirnames if not _should_skip_dir(d)]

            # 处理该目录中的文件
            for fname in filenames:
                if len(local_files) >= max_files:
                    return local_files, local_skipped

                # 排除特定文件名
                if fname in EXCLUDED_FILES:
                    local_skipped += 1
                    continue

                ext = Path(fname).suffix.lower()

                # 排除特定扩展名
                if ext in EXCLUDED_EXTENSIONS:
                    local_skipped += 1
                    continue

                abs_path = os.path.join(root, fname)
                rel_path = os.path.relpath(abs_path, repo_path)

                # 判断是代码还是配置
                is_config = ext in CONFIG_EXTENSIONS
                is_code = ext in CODE_EXTENSIONS

                if not is_code and not is_config:
                    local_skipped += 1
                    continue

                try:
                    language = EXTENSION_TO_LANGUAGE.get(ext, "unknown")
                    size_bytes = os.path.getsize(abs_path)
                    line_count = _count_lines(abs_path)

                    local_files.append(FileInfo(
                        path=rel_path,
                        abs_path=abs_path,
                        language=language,
                        size_bytes=size_bytes,
                        line_count=line_count,
                        is_config=is_config,
                    ))
                except (OSError, PermissionError):
                    local_skipped += 1
                    continue

        return local_files, local_skipped

    # 使用线程池加速大型目录的遍历
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(scan_with_recursion, dirpath): dirpath for dirpath in dirs_to_scan}

        for future in as_completed(futures):
            if hit_limit:
                break

            try:
                files, skipped = future.result()
                with files_lock:
                    all_files.extend(files)
                    total_skipped += skipped
                    if len(all_files) >= max_files:
                        hit_limit = True
                        all_files = all_files[:max_files]
            except Exception as e:
                logger.warning("scan_files.thread_error", error=str(e))

    return all_files, total_skipped


def _scan_files(repo_path: str, max_files: int = 5000) -> tuple[list[FileInfo], int]:
    """扫描仓库目录，返回文件列表和跳过文件数。

    针对小型仓库（<5k files）使用单线程 os.walk；
    针对大型仓库使用并行扫描加速。

    Args:
        repo_path: 仓库路径
        max_files: 最大扫描文件数（overview 模式下限制）

    Returns:
        (文件列表, 跳过文件数)
    """
    # 首先估算文件数，快速决定是否需要并行处理
    try:
        # 快速估计：统计顶级目录数和排除情况
        entries = os.listdir(repo_path)
        excluded_count = sum(1 for e in entries if _should_skip_dir(e) and os.path.isdir(os.path.join(repo_path, e)))
        non_excluded_dirs = sum(1 for e in entries if not _should_skip_dir(e) and os.path.isdir(os.path.join(repo_path, e)))
    except (OSError, PermissionError):
        logger.warning("scan_files.cannot_estimate", path=repo_path)
        non_excluded_dirs = 1

    # 如果非排除目录数 > 4 个，使用并行扫描；否则使用标准 os.walk
    # 这是启发式判断：大型项目通常有多个顶级目录
    if non_excluded_dirs > 4:
        logger.info("scan_files.using_parallel", dirs_count=non_excluded_dirs)
        return _scan_files_parallel(repo_path, max_files)
    else:
        # 标准单线程扫描
        logger.info("scan_files.using_sequential", dirs_count=non_excluded_dirs)
        files: list[FileInfo] = []
        skipped = 0

        for dirpath, dirnames, filenames in os.walk(repo_path):
            # 原地修改 dirnames 以跳过排除目录
            dirnames[:] = [d for d in dirnames if not _should_skip_dir(d)]

            for fname in filenames:
                if len(files) >= max_files:
                    return files, skipped

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

                try:
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
                except (OSError, PermissionError):
                    skipped += 1
                    continue

        return files, skipped


async def clone_repo(url: str, target_dir: str | None = None, max_files: int = 5000) -> CloneResult:
    """克隆 Git 仓库，过滤非代码文件。

    Args:
        url: Git 仓库地址（HTTPS 格式）或本地目录路径。
        target_dir: 克隆目标目录。为 None 时使用临时目录。
        max_files: 最大扫描文件数（overview 模式下限制扫描范围）。默认 5000。

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
    files, skipped = _scan_files(repo_path, max_files=max_files)

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
