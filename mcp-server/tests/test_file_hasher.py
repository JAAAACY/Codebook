"""file_hasher 单元测试。"""

import json
import pytest
from pathlib import Path

from src.watcher.file_hasher import (
    compute_hash,
    snapshot,
    diff,
    save_snapshot,
    load_snapshot,
    FileChanges,
)
from src.parsers.repo_cloner import FileInfo


class TestComputeHash:
    def test_consistent_hash(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("print('hello')")
        h1 = compute_hash(str(f))
        h2 = compute_hash(str(f))
        assert h1 == h2
        assert len(h1) == 64  # SHA256 hex

    def test_different_content_different_hash(self, tmp_path):
        f1 = tmp_path / "a.py"
        f2 = tmp_path / "b.py"
        f1.write_text("aaa")
        f2.write_text("bbb")
        assert compute_hash(str(f1)) != compute_hash(str(f2))

    def test_nonexistent_file_returns_empty(self):
        assert compute_hash("/nonexistent/file.py") == ""


class TestSnapshot:
    def test_captures_all_files(self, tmp_path):
        (tmp_path / "a.py").write_text("a")
        (tmp_path / "b.py").write_text("b")
        files = [
            FileInfo(path="a.py", abs_path=str(tmp_path / "a.py"), language="python", size_bytes=1, line_count=1),
            FileInfo(path="b.py", abs_path=str(tmp_path / "b.py"), language="python", size_bytes=1, line_count=1),
        ]
        snap = snapshot(files)
        assert len(snap) == 2
        assert "a.py" in snap
        assert "b.py" in snap


class TestDiff:
    def test_added_files(self):
        old = {"a.py": "hash_a"}
        new = {"a.py": "hash_a", "b.py": "hash_b"}
        changes = diff(old, new)
        assert changes.added == ["b.py"]
        assert changes.modified == []
        assert changes.removed == []

    def test_modified_files(self):
        old = {"a.py": "hash_a"}
        new = {"a.py": "hash_a_changed"}
        changes = diff(old, new)
        assert changes.added == []
        assert changes.modified == ["a.py"]
        assert changes.removed == []

    def test_removed_files(self):
        old = {"a.py": "hash_a", "b.py": "hash_b"}
        new = {"a.py": "hash_a"}
        changes = diff(old, new)
        assert changes.removed == ["b.py"]

    def test_no_changes(self):
        old = {"a.py": "hash_a"}
        new = {"a.py": "hash_a"}
        changes = diff(old, new)
        assert changes.is_empty
        assert changes.total == 0

    def test_mixed_changes(self):
        old = {"a.py": "h1", "b.py": "h2", "c.py": "h3"}
        new = {"a.py": "h1_mod", "c.py": "h3", "d.py": "h4"}
        changes = diff(old, new)
        assert changes.added == ["d.py"]
        assert changes.modified == ["a.py"]
        assert changes.removed == ["b.py"]
        assert changes.total == 3

    def test_results_are_sorted(self):
        old = {}
        new = {"z.py": "h1", "a.py": "h2", "m.py": "h3"}
        changes = diff(old, new)
        assert changes.added == ["a.py", "m.py", "z.py"]


class TestFileChanges:
    def test_frozen(self):
        fc = FileChanges(added=["a.py"], modified=[], removed=[])
        with pytest.raises(AttributeError):
            fc.added = ["b.py"]  # type: ignore


class TestSaveLoadSnapshot:
    def test_round_trip(self, tmp_path, monkeypatch):
        # 将 ~/.codebook 重定向到 tmp_path
        monkeypatch.setenv("HOME", str(tmp_path))
        # Patch Path.home() for consistent behavior
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        snap = {"a.py": "hash_a", "b.py": "hash_b"}
        save_snapshot("test_repo_hash", snap)
        loaded = load_snapshot("test_repo_hash")
        assert loaded == snap

    def test_load_nonexistent(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        assert load_snapshot("nonexistent_hash") is None
