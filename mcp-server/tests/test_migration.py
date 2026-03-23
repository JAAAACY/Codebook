"""
Tests for memory migration system (old cache -> new ProjectMemory).

Tests cover:
- Migration detection and execution
- Migration idempotency
- Migration failure graceful degradation
"""

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Generator
from unittest import mock

import pytest

from src.memory.migration import (
    _get_old_cache_contexts,
    _get_old_cache_root,
    _get_migration_marker,
    _get_repo_hash,
    _migrate_context_file,
    perform_migration,
    should_migrate,
)
from src.memory.project_memory import ProjectMemory


@pytest.fixture
def temp_home(tmp_path: Path) -> Generator[Path, None, None]:
    """Temporarily override home directory for testing."""
    with mock.patch("pathlib.Path.home", return_value=tmp_path):
        yield tmp_path


class TestMigrationDetection:
    """Test migration detection logic."""

    def test_should_migrate_no_old_cache(self, temp_home: Path) -> None:
        """Should not migrate when old cache doesn't exist."""
        assert not should_migrate()

    def test_should_migrate_with_old_cache_present(
        self, temp_home: Path
    ) -> None:
        """Should migrate when old cache exists."""
        # Create mock old cache structure
        old_cache_dir = _get_old_cache_contexts()
        old_cache_dir.mkdir(parents=True, exist_ok=True)

        # Create a cache file
        cache_file = old_cache_dir / "test_repo_abc123.json"
        cache_file.write_text('{"repo_url": "https://example.com/repo.git"}')

        assert should_migrate()

    def test_should_not_migrate_if_already_migrated(
        self, temp_home: Path
    ) -> None:
        """Should not migrate if marker file exists."""
        # Create mock old cache structure
        old_cache_dir = _get_old_cache_contexts()
        old_cache_dir.mkdir(parents=True, exist_ok=True)

        # Create cache file
        cache_file = old_cache_dir / "test_repo_abc123.json"
        cache_file.write_text('{"repo_url": "https://example.com/repo.git"}')

        # Create migration marker
        marker_file = _get_migration_marker()
        marker_file.parent.mkdir(parents=True, exist_ok=True)
        marker_file.touch()

        assert not should_migrate()

    def test_should_not_migrate_empty_old_cache(
        self, temp_home: Path
    ) -> None:
        """Should not migrate when old cache directory is empty."""
        # Create empty old cache directory
        old_cache_dir = _get_old_cache_contexts()
        old_cache_dir.mkdir(parents=True, exist_ok=True)

        assert not should_migrate()


class TestMigrationExecution:
    """Test migration execution."""

    def test_get_repo_hash(self) -> None:
        """Test repo URL hashing consistency."""
        url = "https://github.com/user/repo.git"
        h1 = _get_repo_hash(url)
        h2 = _get_repo_hash(url)

        assert h1 == h2
        assert len(h1) == 16
        assert all(c in "0123456789abcdef" for c in h1)

    def test_migrate_single_context_file(
        self, temp_home: Path
    ) -> None:
        """Test migration of a single context file."""
        repo_url = "https://github.com/user/repo.git"
        repo_hash = _get_repo_hash(repo_url)

        # Create old cache file
        old_cache_dir = _get_old_cache_contexts()
        old_cache_dir.mkdir(parents=True, exist_ok=True)

        old_data = {
            "repo_url": repo_url,
            "version": 1,
            "timestamp": 1234567890.0,
            "clone_result": {"repo_path": "/tmp/repo", "files": []},
            "parse_results": [],
            "modules": [],
            "graph": {"nodes": {}, "edges": []},
        }
        old_file = old_cache_dir / "test_repo.json"
        old_file.write_text(json.dumps(old_data))

        # Perform migration
        success = _migrate_context_file(old_file, repo_url, repo_hash)

        assert success
        # Check new file exists
        new_memory_root = temp_home / ".codebook" / "memory"
        new_file = new_memory_root / repo_hash / "context.json"
        assert new_file.exists()

        # Check content was wrapped correctly
        new_data = json.loads(new_file.read_text())
        assert new_data["version"] == 1
        assert new_data["repo_url"] == repo_url
        assert "context" in new_data
        assert new_data["context"]["clone_result"]["files"] == []

    def test_migration_full_execution(self, temp_home: Path) -> None:
        """Test full migration execution with multiple files."""
        urls = [
            "https://github.com/user/repo1.git",
            "https://github.com/user/repo2.git",
        ]

        # Create old cache files
        old_cache_dir = _get_old_cache_contexts()
        old_cache_dir.mkdir(parents=True, exist_ok=True)

        for url in urls:
            old_data = {
                "repo_url": url,
                "version": 1,
                "timestamp": 1234567890.0,
                "clone_result": {"repo_path": "/tmp/repo", "files": []},
                "parse_results": [],
                "modules": [],
                "graph": {"nodes": {}, "edges": []},
            }
            filename = f"{url.split('/')[-1].replace('.git', '')}.json"
            (old_cache_dir / filename).write_text(json.dumps(old_data))

        # Perform migration
        result = perform_migration()

        assert result["migrated"]
        assert result["count"] == 2
        assert result["failed"] == 0

        # Check marker created
        marker = _get_migration_marker()
        assert marker.exists()

    def test_migration_idempotency(self, temp_home: Path) -> None:
        """Test that migration is idempotent (can run multiple times)."""
        repo_url = "https://github.com/user/repo.git"

        # Create old cache file
        old_cache_dir = _get_old_cache_contexts()
        old_cache_dir.mkdir(parents=True, exist_ok=True)

        old_data = {
            "repo_url": repo_url,
            "version": 1,
            "timestamp": 1234567890.0,
            "clone_result": {"repo_path": "/tmp/repo", "files": []},
            "parse_results": [],
            "modules": [],
            "graph": {"nodes": {}, "edges": []},
        }
        old_file = old_cache_dir / "test_repo.json"
        old_file.write_text(json.dumps(old_data))

        # Run migration twice
        result1 = perform_migration()
        result2 = perform_migration()

        # First migration should migrate
        assert result1["migrated"]
        assert result1["count"] == 1

        # Second migration should not (marker prevents it)
        assert not result2["migrated"]
        assert result2["count"] == 0

    def test_migration_failure_graceful_degradation(
        self, temp_home: Path
    ) -> None:
        """Test that migration failure doesn't crash the system."""
        # Create old cache dir
        old_cache_dir = _get_old_cache_contexts()
        old_cache_dir.mkdir(parents=True, exist_ok=True)

        # Create invalid JSON file (will fail to read)
        bad_file = old_cache_dir / "corrupt.json"
        bad_file.write_text("{ invalid json ")

        # Perform migration (should not crash)
        result = perform_migration()

        # Should still mark migration as done
        marker = _get_migration_marker()
        assert marker.exists()

        # Migration should have recorded failures
        assert result["failed"] > 0

    def test_migration_permission_denied(
        self, temp_home: Path
    ) -> None:
        """Test graceful handling when write permissions denied."""
        repo_url = "https://github.com/user/repo.git"

        # Create old cache file
        old_cache_dir = _get_old_cache_contexts()
        old_cache_dir.mkdir(parents=True, exist_ok=True)

        old_data = {
            "repo_url": repo_url,
            "version": 1,
            "timestamp": 1234567890.0,
            "clone_result": {"repo_path": "/tmp/repo", "files": []},
            "parse_results": [],
            "modules": [],
            "graph": {"nodes": {}, "edges": []},
        }
        old_file = old_cache_dir / "test_repo.json"
        old_file.write_text(json.dumps(old_data))

        # Mock mkdir to raise PermissionError
        with mock.patch.object(Path, "mkdir", side_effect=PermissionError("denied")):
            result = perform_migration()

            # Migration should catch exception and record error
            assert "error" in result
            assert result["error"] == "denied"


class TestMigrationIntegration:
    """Integration tests with ProjectMemory."""

    def test_migrated_data_readable_by_project_memory(
        self, temp_home: Path
    ) -> None:
        """Test that migrated data can be read by ProjectMemory."""
        repo_url = "https://github.com/user/repo.git"
        repo_hash = _get_repo_hash(repo_url)

        # Create old cache file
        old_cache_dir = temp_home / ".codebook_cache" / "contexts"
        old_cache_dir.mkdir(parents=True, exist_ok=True)

        old_data = {
            "repo_url": repo_url,
            "version": 1,
            "timestamp": 1234567890.0,
            "clone_result": {
                "repo_path": "/tmp/repo",
                "files": [],
                "languages": {},
                "total_lines": 100,
                "skipped_count": 0,
            },
            "parse_results": [],
            "modules": [],
            "graph": {"nodes": {}, "edges": [], "module_map": {}},
            "role": "pm",
        }
        old_file = old_cache_dir / "test_repo.json"
        old_file.write_text(json.dumps(old_data))

        # Perform migration
        perform_migration()

        # Read with ProjectMemory
        pm = ProjectMemory(repo_url)
        ctx = pm.get_context()

        assert ctx is not None
        assert ctx["clone_result"]["total_lines"] == 100
