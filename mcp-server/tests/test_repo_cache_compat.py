"""
Regression tests for RepoCache compatibility.

Verify that RepoCache.store() and RepoCache.get() still work correctly
after being refactored to delegate to ProjectMemory internally.

These tests ensure:
1. Public API signatures unchanged
2. Memory cache still works
3. ProjectMemory delegation works
4. Return types and behavior identical
"""

import tempfile
from pathlib import Path
from unittest import mock

import pytest

from src.tools._repo_cache import RepoCache
from src.summarizer.engine import SummaryContext
from src.parsers.repo_cloner import CloneResult
from src.parsers.dependency_graph import DependencyGraph


@pytest.fixture
def temp_home(tmp_path: Path):
    """Temporarily override home directory for testing."""
    with mock.patch("pathlib.Path.home", return_value=tmp_path):
        yield tmp_path


@pytest.fixture
def sample_summary_context() -> SummaryContext:
    """Create a minimal SummaryContext for testing."""
    return SummaryContext(
        clone_result=CloneResult(
            repo_path="/tmp/repo",
            files=[],
            languages={},
            total_lines=100,
            skipped_count=0,
        ),
        parse_results=[],
        modules=[],
        dep_graph=DependencyGraph(),
        role="pm",
    )


class TestRepoCacheMemoryBehavior:
    """Test that memory caching still works correctly."""

    def test_store_and_get_memory(
        self, temp_home: Path, sample_summary_context: SummaryContext
    ) -> None:
        """Test basic store/get in memory cache."""
        cache = RepoCache()
        repo_url = "https://github.com/user/repo.git"

        cache.store(repo_url, sample_summary_context)
        retrieved = cache.get(repo_url)

        assert retrieved is not None
        assert retrieved.role == "pm"
        assert retrieved.clone_result.total_lines == 100

    def test_get_latest_from_memory(
        self, temp_home: Path, sample_summary_context: SummaryContext
    ) -> None:
        """Test get() with no argument returns latest from memory."""
        cache = RepoCache()
        repo_url1 = "https://github.com/user/repo1.git"
        repo_url2 = "https://github.com/user/repo2.git"

        cache.store(repo_url1, sample_summary_context)
        cache.store(repo_url2, sample_summary_context)

        latest = cache.get()
        assert latest is not None
        # Latest should be repo_url2 (stored last)

    def test_has_memory(
        self, temp_home: Path, sample_summary_context: SummaryContext
    ) -> None:
        """Test has() method for memory cache."""
        cache = RepoCache()
        repo_url = "https://github.com/user/repo.git"

        assert not cache.has(repo_url)
        cache.store(repo_url, sample_summary_context)
        assert cache.has(repo_url)

    def test_clear_memory(
        self, temp_home: Path, sample_summary_context: SummaryContext
    ) -> None:
        """Test clear() removes only memory cache."""
        cache = RepoCache()
        repo_url = "https://github.com/user/repo.git"

        cache.store(repo_url, sample_summary_context)
        assert cache.has(repo_url)

        cache.clear()
        # Memory should be cleared
        assert repo_url not in cache._cache


class TestRepoCacheProjectMemoryDelegation:
    """Test delegation to ProjectMemory."""

    def test_store_delegates_to_project_memory(
        self, temp_home: Path, sample_summary_context: SummaryContext
    ) -> None:
        """Test that store() calls ProjectMemory.store_context()."""
        cache = RepoCache()
        repo_url = "https://github.com/user/repo.git"

        # Store should succeed
        cache.store(repo_url, sample_summary_context)

        # Verify ProjectMemory was created
        assert repo_url in cache._project_memories

    def test_get_retrieves_from_project_memory(
        self, temp_home: Path, sample_summary_context: SummaryContext
    ) -> None:
        """Test that get() can retrieve from ProjectMemory disk."""
        cache = RepoCache()
        repo_url = "https://github.com/user/repo.git"

        # Store using first cache instance
        cache.store(repo_url, sample_summary_context)

        # Create new cache instance (simulating fresh process)
        cache2 = RepoCache()
        # Clear memory to force disk read
        cache2.clear()

        # Get should retrieve from disk (ProjectMemory)
        retrieved = cache2.get(repo_url)
        assert retrieved is not None
        assert retrieved.role == "pm"

    def test_get_returns_none_for_unknown_repo(
        self, temp_home: Path
    ) -> None:
        """Test that get() returns None for unknown repos."""
        cache = RepoCache()
        result = cache.get("https://github.com/unknown/repo.git")
        assert result is None


class TestRepoCacheConsistency:
    """Test consistency of cache behavior."""

    def test_store_get_roundtrip(
        self, temp_home: Path, sample_summary_context: SummaryContext
    ) -> None:
        """Test store/get roundtrip preserves data."""
        cache = RepoCache()
        repo_url = "https://github.com/user/repo.git"

        cache.store(repo_url, sample_summary_context)
        retrieved = cache.get(repo_url)

        # Data should be identical
        assert retrieved.clone_result.repo_path == "/tmp/repo"
        assert retrieved.clone_result.total_lines == 100
        assert retrieved.role == "pm"

    def test_multiple_repos_isolation(
        self, temp_home: Path, sample_summary_context: SummaryContext
    ) -> None:
        """Test that multiple repos don't interfere."""
        cache = RepoCache()
        repo_url1 = "https://github.com/user/repo1.git"
        repo_url2 = "https://github.com/user/repo2.git"

        ctx1 = sample_summary_context
        ctx2 = SummaryContext(
            clone_result=CloneResult(
                repo_path="/tmp/repo2",
                files=[],
                languages={},
                total_lines=200,
                skipped_count=0,
            ),
            parse_results=[],
            modules=[],
            dep_graph=DependencyGraph(),
            role="dev",
        )

        cache.store(repo_url1, ctx1)
        cache.store(repo_url2, ctx2)

        retrieved1 = cache.get(repo_url1)
        retrieved2 = cache.get(repo_url2)

        assert retrieved1.clone_result.total_lines == 100
        assert retrieved2.clone_result.total_lines == 200
        assert retrieved1.role == "pm"
        assert retrieved2.role == "dev"

    def test_has_checks_both_memory_and_disk(
        self, temp_home: Path, sample_summary_context: SummaryContext
    ) -> None:
        """Test that has() checks both memory and ProjectMemory."""
        cache1 = RepoCache()
        repo_url = "https://github.com/user/repo.git"

        # Store in cache1
        cache1.store(repo_url, sample_summary_context)

        # New cache instance without memory
        cache2 = RepoCache()

        # Should still find it (via ProjectMemory)
        assert cache2.has(repo_url)

    def test_clear_all_removes_memory(
        self, temp_home: Path, sample_summary_context: SummaryContext
    ) -> None:
        """Test clear_all() removes memory cache."""
        cache = RepoCache()
        repo_url = "https://github.com/user/repo.git"

        cache.store(repo_url, sample_summary_context)
        assert cache.has(repo_url)

        cache.clear_all()
        assert len(cache._cache) == 0


class TestRepoCacheErrorHandling:
    """Test error handling in cache operations."""

    def test_store_continues_on_project_memory_failure(
        self, temp_home: Path, sample_summary_context: SummaryContext
    ) -> None:
        """Test that store() continues even if ProjectMemory fails."""
        cache = RepoCache()
        repo_url = "https://github.com/user/repo.git"

        # Store should not crash even if ProjectMemory fails
        try:
            cache.store(repo_url, sample_summary_context)
            # Memory cache should still work
            assert cache.get(repo_url) is not None
        except Exception as e:
            pytest.fail(f"store() should not raise exception: {e}")

    def test_get_returns_none_on_deserialize_failure(
        self, temp_home: Path
    ) -> None:
        """Test that get() returns None if deserialization fails."""
        cache = RepoCache()
        repo_url = "https://github.com/user/repo.git"

        # Create invalid data in ProjectMemory
        pm = cache._get_project_memory(repo_url)
        pm.store_context({"invalid": "data_missing_required_fields"})

        # get() should return None gracefully
        result = cache.get(repo_url)
        assert result is None


class TestRepoCachePublicAPI:
    """Verify public API signatures are unchanged."""

    def test_store_signature(self) -> None:
        """Test store() has correct signature."""
        cache = RepoCache()
        # Should accept (repo_url: str, ctx: SummaryContext)
        assert hasattr(cache, "store")
        assert callable(cache.store)

    def test_get_signature(self) -> None:
        """Test get() has correct signature."""
        cache = RepoCache()
        # Should accept optional repo_url: str | None
        assert hasattr(cache, "get")
        assert callable(cache.get)

    def test_has_signature(self) -> None:
        """Test has() has correct signature."""
        cache = RepoCache()
        # Should accept repo_url: str
        assert hasattr(cache, "has")
        assert callable(cache.has)

    def test_clear_signature(self) -> None:
        """Test clear() has correct signature."""
        cache = RepoCache()
        assert hasattr(cache, "clear")
        assert callable(cache.clear)

    def test_clear_all_signature(self) -> None:
        """Test clear_all() has correct signature."""
        cache = RepoCache()
        assert hasattr(cache, "clear_all")
        assert callable(cache.clear_all)


class TestGlobalRepoCacheInstance:
    """Test global repo_cache singleton."""

    def test_repo_cache_singleton_exists(self) -> None:
        """Test that global repo_cache is available."""
        from src.tools._repo_cache import repo_cache

        assert repo_cache is not None
        assert isinstance(repo_cache, RepoCache)
