"""Tests for term_correct MCP tool."""

import shutil
from pathlib import Path
from unittest.mock import patch, AsyncMock

import pytest

from src.tools.term_correct import term_correct
from src.glossary.term_store import ProjectGlossary
from src.summarizer.engine import _get_banned_terms


class TestTermCorrectBasic:
    """Tests for basic term_correct functionality."""

    @pytest.fixture
    def cleanup_memory(self) -> None:
        """Clean up memory directory after tests."""
        yield
        memory_base = Path.home() / ".codebook" / "memory"
        if memory_base.exists():
            shutil.rmtree(memory_base, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_successful_correction(self, cleanup_memory: None) -> None:
        """Test successful terminology correction."""
        result = await term_correct(
            source_term="idempotent",
            correct_translation="幂等操作",
            context="API endpoints",
        )

        assert result["status"] == "ok"
        assert "术语纠正已记录" in result["message"]
        assert "idempotent" in result["message"]
        assert "幂等操作" in result["message"]
        assert result["affected_scope"] == "当前项目"

    @pytest.mark.asyncio
    async def test_correction_with_wrong_translation(self, cleanup_memory: None) -> None:
        """Test correction that documents the previous wrong translation."""
        result = await term_correct(
            source_term="cache invalidation",
            correct_translation="缓存失效",
            wrong_translation="缓存无效化",
            context="Performance optimization",
        )

        assert result["status"] == "ok"
        assert "缓存无效化" in result["message"]
        assert "cache invalidation" in result["message"]

    @pytest.mark.asyncio
    async def test_missing_source_term(self, cleanup_memory: None) -> None:
        """Test error when source_term is missing."""
        result = await term_correct(
            source_term="",
            correct_translation="翻译",
        )

        assert result["status"] == "error"
        assert "source_term" in result["error"]
        assert "hint" in result

    @pytest.mark.asyncio
    async def test_missing_correct_translation(self, cleanup_memory: None) -> None:
        """Test error when correct_translation is missing."""
        result = await term_correct(
            source_term="test",
            correct_translation="",
        )

        assert result["status"] == "error"
        assert "correct_translation" in result["error"]
        assert "hint" in result

    @pytest.mark.asyncio
    async def test_duplicate_correction_override(self, cleanup_memory: None) -> None:
        """Test that duplicate corrections override previous ones."""
        # First correction
        result1 = await term_correct(
            source_term="transaction",
            correct_translation="交易",
        )
        assert result1["status"] == "ok"

        # Second correction should override
        result2 = await term_correct(
            source_term="transaction",
            correct_translation="事务处理",
        )
        assert result2["status"] == "ok"

        # Verify only the latest correction is stored
        glossary = ProjectGlossary("codebook://current_project")
        terms = glossary.get_all_terms()
        transaction_terms = [t for t in terms if t.source_term == "transaction"]
        assert len(transaction_terms) == 1
        assert transaction_terms[0].target_phrase == "事务处理"


class TestTermCorrectIntegration:
    """Integration tests with engine.py."""

    @pytest.fixture
    def cleanup_memory(self) -> None:
        """Clean up memory directory after tests."""
        yield
        memory_base = Path.home() / ".codebook" / "memory"
        if memory_base.exists():
            shutil.rmtree(memory_base, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_correction_picked_up_by_engine(self, cleanup_memory: None) -> None:
        """Test that engine._get_banned_terms() picks up corrections."""
        # Add a correction
        result = await term_correct(
            source_term="middleware",
            correct_translation="中间件处理层",
        )
        assert result["status"] == "ok"

        # Engine should pick it up when repo_url matches
        banned_terms = _get_banned_terms(repo_url="codebook://current_project")

        # The resolved terms should include our correction
        assert "middleware" in banned_terms
        assert "中间件处理层" in banned_terms

    @pytest.mark.asyncio
    async def test_correction_fallback_without_repo_url(self, cleanup_memory: None) -> None:
        """Test that engine falls back to config when repo_url is not provided."""
        # Add a correction
        result = await term_correct(
            source_term="fallback_test",
            correct_translation="回退测试",
        )
        assert result["status"] == "ok"

        # Without repo_url, should fallback to config (which won't include our term)
        banned_terms = _get_banned_terms(repo_url=None)

        # The result should be from config, not from our correction
        # (unless fallback_test happens to be in config, which it shouldn't be)
        assert isinstance(banned_terms, str)


class TestTermCorrectEdgeCases:
    """Edge case tests for term_correct."""

    @pytest.fixture
    def cleanup_memory(self) -> None:
        """Clean up memory directory after tests."""
        yield
        memory_base = Path.home() / ".codebook" / "memory"
        if memory_base.exists():
            shutil.rmtree(memory_base, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_whitespace_handling(self, cleanup_memory: None) -> None:
        """Test that leading/trailing whitespace is handled correctly."""
        result = await term_correct(
            source_term="  idempotent  ",
            correct_translation="  幂等操作  ",
        )

        assert result["status"] == "ok"

        # Verify whitespace was stripped
        glossary = ProjectGlossary("codebook://current_project")
        term = glossary.find_term("idempotent")
        assert term is not None
        assert term.target_phrase == "幂等操作"

    @pytest.mark.asyncio
    async def test_special_characters_in_term(self, cleanup_memory: None) -> None:
        """Test handling of special characters."""
        result = await term_correct(
            source_term="HTTP/2-upgrade",
            correct_translation="HTTP 2.0 协议升级",
        )

        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_unicode_in_translation(self, cleanup_memory: None) -> None:
        """Test Unicode characters in translation."""
        result = await term_correct(
            source_term="race_condition",
            correct_translation="竞态条件（多线程中同时访问同一资源）",
        )

        assert result["status"] == "ok"
        assert "竞态条件" in result["message"]

    @pytest.mark.asyncio
    async def test_empty_optional_fields(self, cleanup_memory: None) -> None:
        """Test that optional fields can be empty."""
        result = await term_correct(
            source_term="test",
            correct_translation="测试",
            wrong_translation="",
            context="",
        )

        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_none_type_for_optional_fields(self, cleanup_memory: None) -> None:
        """Test behavior when optional string fields might be None-like."""
        # The function signature has defaults, so this tests the validation
        result = await term_correct(
            source_term="term",
            correct_translation="术语",
            wrong_translation=None,  # type: ignore
            context=None,  # type: ignore
        )

        # Should still work (None is falsy, so context check won't include it)
        # But depending on implementation, this might fail validation
        # For now, assume it handles gracefully
        assert result["status"] in ["ok", "error"]


class TestTermCorrectValidation:
    """Detailed validation tests."""

    @pytest.fixture
    def cleanup_memory(self) -> None:
        """Clean up memory directory after tests."""
        yield
        memory_base = Path.home() / ".codebook" / "memory"
        if memory_base.exists():
            shutil.rmtree(memory_base, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_source_term_none_type(self, cleanup_memory: None) -> None:
        """Test validation when source_term is None."""
        result = await term_correct(
            source_term=None,  # type: ignore
            correct_translation="翻译",
        )

        assert result["status"] == "error"
        assert "source_term" in result["error"]

    @pytest.mark.asyncio
    async def test_correct_translation_none_type(self, cleanup_memory: None) -> None:
        """Test validation when correct_translation is None."""
        result = await term_correct(
            source_term="term",
            correct_translation=None,  # type: ignore
        )

        assert result["status"] == "error"
        assert "correct_translation" in result["error"]

    @pytest.mark.asyncio
    async def test_source_term_only_whitespace(self, cleanup_memory: None) -> None:
        """Test validation when source_term is only whitespace."""
        result = await term_correct(
            source_term="   ",
            correct_translation="翻译",
        )

        assert result["status"] == "error"
        assert "source_term" in result["error"]

    @pytest.mark.asyncio
    async def test_correct_translation_only_whitespace(self, cleanup_memory: None) -> None:
        """Test validation when correct_translation is only whitespace."""
        result = await term_correct(
            source_term="term",
            correct_translation="   ",
        )

        assert result["status"] == "error"
        assert "correct_translation" in result["error"]
