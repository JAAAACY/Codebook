"""file_hasher — SHA256 文件指纹与变更检测。

对仓库中所有代码文件计算 SHA256 哈希，生成快照。
通过对比两次快照的 diff 来识别新增、修改、删除的文件。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import structlog

from src.parsers.repo_cloner import FileInfo

logger = structlog.get_logger()


def _repo_hash_from_url(repo_url: str) -> str:
    """与 ProjectMemory 一致的 repo_url 哈希。"""
    return hashlib.sha256(repo_url.encode()).hexdigest()[:16]


@dataclass(frozen=True)
class FileChanges:
    """两次快照之间的文件变更。"""
    added: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.added) + len(self.modified) + len(self.removed)

    @property
    def is_empty(self) -> bool:
        return self.total == 0


def compute_hash(file_path: str) -> str:
    """计算单个文件的 SHA256 哈希。

    Args:
        file_path: 文件绝对路径。

    Returns:
        十六进制 SHA256 字符串。
    """
    h = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
    except (OSError, IOError):
        return ""
    return h.hexdigest()


def snapshot(files: list[FileInfo]) -> dict[str, str]:
    """为一组文件生成哈希快照。

    Args:
        files: FileInfo 列表（来自 CloneResult.files）。

    Returns:
        {relative_path: sha256_hex}
    """
    result: dict[str, str] = {}
    for fi in files:
        h = compute_hash(fi.abs_path)
        if h:
            result[fi.path] = h
    return result


def diff(old: dict[str, str], new: dict[str, str]) -> FileChanges:
    """对比两个快照，返回文件变更。

    Args:
        old: 旧快照 {path: hash}。
        new: 新快照 {path: hash}。

    Returns:
        FileChanges 包含 added/modified/removed 列表。
    """
    old_keys = set(old)
    new_keys = set(new)

    added = sorted(new_keys - old_keys)
    removed = sorted(old_keys - new_keys)
    modified = sorted(
        p for p in old_keys & new_keys
        if old[p] != new[p]
    )

    return FileChanges(added=added, modified=modified, removed=removed)


def save_snapshot(repo_hash: str, snap: dict[str, str]) -> Path:
    """持久化快照到磁盘。

    Args:
        repo_hash: 仓库哈希（用于目录分隔）。
        snap: 快照字典。

    Returns:
        保存的文件路径。
    """
    store_dir = Path.home() / ".codebook" / "memory" / repo_hash
    store_dir.mkdir(parents=True, exist_ok=True)
    path = store_dir / "file_hashes.json"
    path.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.debug("file_hasher.saved", path=str(path), files=len(snap))
    return path


def load_snapshot(repo_hash: str) -> dict[str, str] | None:
    """从磁盘加载快照。

    Args:
        repo_hash: 仓库哈希。

    Returns:
        快照字典，文件不存在时返回 None。
    """
    path = Path.home() / ".codebook" / "memory" / repo_hash / "file_hashes.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, OSError):
        logger.warning("file_hasher.load_failed", path=str(path))
    return None
