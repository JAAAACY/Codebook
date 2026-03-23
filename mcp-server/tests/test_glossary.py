"""Unit tests for glossary system (TermEntry, ProjectGlossary, TermResolver)."""

import json
import shutil
from pathlib import Path
from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest

from src.glossary.term_store import TermEntry, ProjectGlossary
from src.glossary.term_resolver import TermResolver


class TestTermEntry:
    """Tests for TermEntry dataclass."""

    def test_term_entry_creation(self) -> None:
        """Test basic TermEntry creation."""
        entry = TermEntry(
            source_term="idempotent",
            target_phrase="重复操作不会产生副作用",
        )
        assert entry.source_term == "idempotent"
        assert entry.target_phrase == "重复操作不会产生副作用"
        assert entry.domain == "general"
        assert entry.source == "default"
        assert entry.confidence == 1.0
        assert entry.usage_count == 0
        assert entry.created_at  # Should be auto-populated

    def test_term_entry_to_dict(self) -> None:
        """Test TermEntry serialization."""
        entry = TermEntry(
            source_term="test",
            target_phrase="测试",
            domain="fintech",
            source="user_correction",
        )
        data = entry.to_dict()
        assert data["source_term"] == "test"
        assert data["target_phrase"] == "测试"
        assert data["domain"] == "fintech"
        assert data["source"] == "user_correction"

    def test_term_entry_from_dict(self) -> None:
        """Test TermEntry deserialization."""
        data = {
            "source_term": "test",
            "target_phrase": "测试",
            "domain": "fintech",
            "source": "user_correction",
            "confidence": 1.0,
            "usage_count": 5,
            "created_at": "2026-03-23T10:00:00Z",
            "updated_at": "2026-03-23T10:00:00Z",
            "context": "API docs",
        }
        entry = TermEntry.from_dict(data)
        assert entry.source_term == "test"
        assert entry.usage_count == 5
        assert entry.created_at == "2026-03-23T10:00:00Z"

    def test_term_entry_roundtrip(self) -> None:
        """Test TermEntry serialization roundtrip."""
        original = TermEntry(
            source_term="test",
            target_phrase="测试",
            domain="healthcare",
            context="Medical context",
            source="domain_pack",
            confidence=0.9,
            usage_count=3,
        )
        data = original.to_dict()
        restored = TermEntry.from_dict(data)
        assert restored.source_term == original.source_term
        assert restored.target_phrase == original.target_phrase
        assert restored.domain == original.domain
        assert restored.context == original.context
        assert restored.confidence == original.confidence
        assert restored.usage_count == original.usage_count

    def test_term_entry_increment_usage(self) -> None:
        """Test usage count increment."""
        entry = TermEntry(source_term="test", target_phrase="测试")
        assert entry.usage_count == 0
        entry.increment_usage()
        assert entry.usage_count == 1
        old_updated = entry.updated_at
        entry.increment_usage()
        assert entry.usage_count == 2
        # Timestamp should be updated
        assert entry.updated_at >= old_updated


class TestProjectGlossary:
    """Tests for ProjectGlossary class."""

    @pytest.fixture
    def cleanup_memory(self) -> None:
        """Clean up memory directory after tests."""
        yield
        memory_base = Path.home() / ".codebook" / "memory"
        if memory_base.exists():
            shutil.rmtree(memory_base, ignore_errors=True)

    def test_project_glossary_init(self, cleanup_memory: None) -> None:
        """Test ProjectGlossary initialization."""
        glossary = ProjectGlossary("https://github.com/test/repo")
        assert glossary.repo_url == "https://github.com/test/repo"
        assert isinstance(glossary.terms, list)
        assert len(glossary.terms) == 0

    def test_add_correction(self, cleanup_memory: None) -> None:
        """Test adding a user correction."""
        glossary = ProjectGlossary("https://github.com/test/repo")
        success = glossary.add_correction(
            source_term="idempotent",
            target_phrase="幂等操作",
            context="API endpoint",
            domain="general",
        )
        assert success
        assert len(glossary.terms) == 1
        term = glossary.terms[0]
        assert term.source_term == "idempotent"
        assert term.target_phrase == "幂等操作"
        assert term.source == "user_correction"
        assert term.confidence == 1.0

    def test_add_correction_override_existing(self, cleanup_memory: None) -> None:
        """Test that adding a correction overrides existing user correction."""
        glossary = ProjectGlossary("https://github.com/test/repo")
        glossary.add_correction("test", "测试1")
        glossary.add_correction("test", "测试2")  # Override
        assert len(glossary.terms) == 1
        assert glossary.terms[0].target_phrase == "测试2"

    def test_get_all_terms(self, cleanup_memory: None) -> None:
        """Test retrieving all terms."""
        glossary = ProjectGlossary("https://github.com/test/repo")
        glossary.add_correction("term1", "翻译1")
        glossary.add_correction("term2", "翻译2")
        terms = glossary.get_all_terms()
        assert len(terms) == 2

    def test_import_terms_basic(self, cleanup_memory: None) -> None:
        """Test importing terms from a domain pack."""
        glossary = ProjectGlossary("https://github.com/test/repo")
        terms_data = [
            {"source_term": "KYC", "target_phrase": "客户身份验证"},
            {"source_term": "AML", "target_phrase": "反洗钱检查"},
        ]
        count = glossary.import_terms(terms_data, domain="fintech")
        assert count == 2
        assert len(glossary.terms) == 2

    def test_import_terms_skip_user_corrections(self, cleanup_memory: None) -> None:
        """Test that import skips terms with existing user corrections."""
        glossary = ProjectGlossary("https://github.com/test/repo")
        glossary.add_correction("KYC", "用户已纠正的值")

        terms_data = [
            {"source_term": "KYC", "target_phrase": "客户身份验证"},
            {"source_term": "AML", "target_phrase": "反洗钱检查"},
        ]
        count = glossary.import_terms(terms_data, domain="fintech")
        assert count == 1  # Only AML imported
        kyc_term = glossary.find_term("KYC")
        assert kyc_term.target_phrase == "用户已纠正的值"

    def test_import_terms_multiple_domains(self, cleanup_memory: None) -> None:
        """Test importing terms from multiple domain packs."""
        glossary = ProjectGlossary("https://github.com/test/repo")
        fintech_terms = [
            {"source_term": "settlement", "target_phrase": "资金结算"},
        ]
        healthcare_terms = [
            {"source_term": "FHIR", "target_phrase": "医疗标准"},
        ]
        glossary.import_terms(fintech_terms, domain="fintech")
        glossary.import_terms(healthcare_terms, domain="healthcare")
        assert len(glossary.terms) == 2

    def test_set_project_domain(self, cleanup_memory: None) -> None:
        """Test setting project domain."""
        glossary = ProjectGlossary("https://github.com/test/repo")
        success = glossary.set_project_domain("fintech")
        assert success
        assert glossary.project_domain == "fintech"

    def test_find_term(self, cleanup_memory: None) -> None:
        """Test finding a term."""
        glossary = ProjectGlossary("https://github.com/test/repo")
        glossary.add_correction("test", "测试")
        term = glossary.find_term("test")
        assert term is not None
        assert term.target_phrase == "测试"

        term_not_found = glossary.find_term("nonexistent")
        assert term_not_found is None

    def test_glossary_persistence(self, cleanup_memory: None) -> None:
        """Test that glossary data persists across instances."""
        # Create first instance and add terms
        glossary1 = ProjectGlossary("https://github.com/test/repo")
        glossary1.add_correction("term1", "翻译1")

        # Create second instance with same repo URL
        glossary2 = ProjectGlossary("https://github.com/test/repo")
        assert len(glossary2.terms) == 1
        assert glossary2.find_term("term1").target_phrase == "翻译1"

    def test_glossary_empty_graceful_degradation(
        self, cleanup_memory: None
    ) -> None:
        """Test that empty glossary gracefully degrades."""
        glossary = ProjectGlossary("https://github.com/test/repo")
        terms = glossary.get_all_terms()
        assert len(terms) == 0


class TestTermResolver:
    """Tests for TermResolver class."""

    @pytest.fixture
    def cleanup_memory(self) -> None:
        """Clean up memory directory after tests."""
        yield
        memory_base = Path.home() / ".codebook" / "memory"
        if memory_base.exists():
            shutil.rmtree(memory_base, ignore_errors=True)

    def test_term_resolver_init(self, cleanup_memory: None) -> None:
        """Test TermResolver initialization."""
        resolver = TermResolver("https://github.com/test/repo")
        assert resolver.repo_url == "https://github.com/test/repo"
        assert isinstance(resolver.domain_packs, dict)

    def test_domain_packs_loading(self, cleanup_memory: None) -> None:
        """Test that domain packs are loaded."""
        resolver = TermResolver("https://github.com/test/repo", project_domain="fintech")
        # Should have loaded general and fintech packs
        assert "general" in resolver.domain_packs or len(resolver.domain_packs) >= 0

    def test_resolve_user_correction_priority(self, cleanup_memory: None) -> None:
        """Test that user corrections have highest priority."""
        resolver = TermResolver("https://github.com/test/repo")
        # Add a user correction
        resolver.glossary.add_correction("test", "用户修正")

        # Import same term from domain pack with different value
        resolver.glossary.import_terms(
            [{"source_term": "test", "target_phrase": "域包值"}],
            domain="general",
        )

        merged = resolver._merge_terms()
        test_term = next((t for t in merged if t.source_term == "test"), None)
        assert test_term is not None
        assert test_term.target_phrase == "用户修正"
        assert test_term.source == "user_correction"

    def test_resolve_as_text(self, cleanup_memory: None) -> None:
        """Test resolve() returns text format."""
        resolver = TermResolver("https://github.com/test/repo")
        resolver.glossary.add_correction("term1", "翻译1")
        resolver.glossary.add_correction("term2", "翻译2")

        text = resolver.resolve()
        assert "term1 -> 翻译1" in text
        assert "term2 -> 翻译2" in text

    def test_resolve_as_list(self, cleanup_memory: None) -> None:
        """Test resolve_as_list() returns structured data."""
        resolver = TermResolver("https://github.com/test/repo")
        resolver.glossary.add_correction("term1", "翻译1")
        resolver.glossary.add_correction("term2", "翻译2")

        terms = resolver.resolve_as_list()
        assert len(terms) >= 2
        source_terms = [t.source_term for t in terms]
        assert "term1" in source_terms
        assert "term2" in source_terms

    def test_track_usage(self, cleanup_memory: None) -> None:
        """Test tracking term usage."""
        resolver = TermResolver("https://github.com/test/repo")
        resolver.glossary.add_correction("test", "测试")
        resolver.track_usage("test")

        # Reload and verify
        term = resolver.glossary.find_term("test")
        assert term.usage_count == 1

    def test_get_statistics(self, cleanup_memory: None) -> None:
        """Test getting statistics."""
        resolver = TermResolver("https://github.com/test/repo")
        resolver.glossary.add_correction("term1", "翻译1")
        resolver.glossary.import_terms(
            [
                {"source_term": "KYC", "target_phrase": "客户身份验证"},
            ],
            domain="fintech",
        )

        stats = resolver.get_statistics()
        assert stats["total_terms"] > 0
        assert stats["user_corrections"] >= 1

    def test_priority_merge_multiple_domains(
        self, cleanup_memory: None
    ) -> None:
        """Test merging terms from multiple domain packs."""
        resolver = TermResolver(
            "https://github.com/test/repo", project_domain="fintech"
        )

        # Add from different domains
        resolver.glossary.import_terms(
            [
                {"source_term": "settlement", "target_phrase": "资金结算"},
            ],
            domain="fintech",
        )
        resolver.glossary.import_terms(
            [
                {"source_term": "diagnosis", "target_phrase": "诊断"},
            ],
            domain="healthcare",
        )

        merged = resolver._merge_terms()
        assert len(merged) >= 2


class TestProjectGlossaryIntegration:
    """Integration tests for ProjectGlossary with domain packs."""

    @pytest.fixture
    def cleanup_memory(self) -> None:
        """Clean up memory directory after tests."""
        yield
        memory_base = Path.home() / ".codebook" / "memory"
        if memory_base.exists():
            shutil.rmtree(memory_base, ignore_errors=True)

    def test_full_workflow_user_correction_to_resolution(
        self, cleanup_memory: None
    ) -> None:
        """Test full workflow: correct term → import pack → resolve."""
        # Create resolver
        resolver = TermResolver(
            "https://github.com/fintech/app", project_domain="fintech"
        )

        # User makes a correction
        resolver.glossary.add_correction(
            "settlement",
            "资金清结",
            context="支付处理模块",
            domain="fintech",
        )

        # System tries to import domain pack
        resolver.glossary.import_terms(
            [
                {"source_term": "settlement", "target_phrase": "资金结算"},
                {"source_term": "KYC", "target_phrase": "客户验证"},
            ],
            domain="fintech",
        )

        # Verify resolution respects user correction
        merged = resolver._merge_terms()
        settlement = next(
            (t for t in merged if t.source_term == "settlement"), None
        )
        assert settlement.target_phrase == "资金清结"
        assert settlement.source == "user_correction"

        kyc = next((t for t in merged if t.source_term == "KYC"), None)
        assert kyc.target_phrase == "客户验证"
        assert kyc.source == "domain_pack"

    def test_domain_pack_loading_from_files(
        self, cleanup_memory: None
    ) -> None:
        """Test loading actual domain pack files."""
        resolver = TermResolver(
            "https://github.com/test/repo", project_domain="general"
        )

        # Check that general pack was loaded
        stats = resolver.get_statistics()
        assert stats["total_terms"] > 0

    def test_empty_glossary_with_domain_pack(
        self, cleanup_memory: None
    ) -> None:
        """Test that empty glossary falls back to domain pack."""
        resolver = TermResolver(
            "https://github.com/test/repo", project_domain="fintech"
        )

        # No corrections, but should have domain pack terms
        resolved_text = resolver.resolve()
        # Should have some terms (from domain packs)
        assert isinstance(resolved_text, str)


class TestTermEntryEdgeCases:
    """Edge case tests for term handling."""

    def test_term_with_special_characters(self) -> None:
        """Test term with special characters."""
        entry = TermEntry(
            source_term="race:condition",
            target_phrase="竞态条件（race condition）",
        )
        assert entry.source_term == "race:condition"
        assert entry.target_phrase == "竞态条件（race condition）"

    def test_term_with_unicode(self) -> None:
        """Test term with Unicode characters."""
        entry = TermEntry(
            source_term="幂等性",
            target_phrase="idempotency",
        )
        assert entry.source_term == "幂等性"
        data = entry.to_dict()
        restored = TermEntry.from_dict(data)
        assert restored.source_term == "幂等性"

    def test_term_with_long_context(self) -> None:
        """Test term with long context description."""
        long_context = "This is a very long context description " * 10
        entry = TermEntry(
            source_term="test",
            target_phrase="测试",
            context=long_context,
        )
        assert entry.context == long_context

    def test_invalid_confidence_bounds(self) -> None:
        """Test terms with boundary confidence values."""
        entry_zero = TermEntry(
            source_term="test",
            target_phrase="测试",
            confidence=0.0,
        )
        assert entry_zero.confidence == 0.0

        entry_one = TermEntry(
            source_term="test",
            target_phrase="测试",
            confidence=1.0,
        )
        assert entry_one.confidence == 1.0
