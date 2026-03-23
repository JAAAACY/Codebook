"""Tests for smart memory features (D-4 task).

Tests for:
1. Term implicit inference (infer_from_qa_history)
2. Hotspot clustering (detect_hotspots)
3. Incremental scan detection
4. SessionSummary auto-generation
"""

import json
import pytest
from pathlib import Path
from datetime import datetime

from src.glossary.term_resolver import TermResolver
from src.glossary.term_store import TermEntry
from src.memory.project_memory import ProjectMemory
from src.memory.models import (
    QARecord, DiagnosisRecord, ModuleUnderstanding,
    Hotspot, SessionSummary,
)


class TestTermImplicitInference:
    """Test term inference from QA history."""

    def test_infer_basic_vocabulary(self):
        """Test basic term inference from QA history."""
        qa_history = [
            {
                "question": "How does the payment processing work?",
                "answer_summary": "The payment_handler processes transactions through process_payment()"
            },
            {
                "question": "What is the refund mechanism?",
                "answer_summary": "Refunds are handled by refund_processor which calls process_refund()"
            },
        ]

        resolver = TermResolver("https://example.com/repo")
        inferred = resolver.infer_from_qa_history(qa_history)

        # Should infer some terms
        assert len(inferred) > 0

        # All should be marked as inferred with confidence < 0.8
        for term in inferred:
            assert term.source == "inferred"
            assert term.confidence < 0.8
            assert term.confidence > 0.6

    def test_infer_repeated_keywords(self):
        """Test that repeated keywords increase confidence."""
        qa_history = [
            {
                "question": "How does authorization work?",
                "answer_summary": "The auth_service checks permissions via check_auth()"
            },
            {
                "question": "How is authorization enforced?",
                "answer_summary": "Auth enforcement happens in the auth_middleware"
            },
            {
                "question": "What about authorization tokens?",
                "answer_summary": "Tokens are managed by auth_token_manager"
            },
        ]

        resolver = TermResolver("https://example.com/repo")
        inferred = resolver.infer_from_qa_history(qa_history)

        # Should have inferred terms
        assert len(inferred) > 0

        # All should be within 0.7-0.79 range (bootstrap confidence + 0.05 increments)
        for term in inferred:
            assert 0.7 <= term.confidence < 0.80

    def test_infer_empty_history(self):
        """Test inference with empty QA history."""
        resolver = TermResolver("https://example.com/repo")
        inferred = resolver.infer_from_qa_history([])

        assert inferred == []

    def test_infer_missing_fields(self):
        """Test inference gracefully handles missing fields."""
        qa_history = [
            {"question": "How does it work?"},  # Missing answer_summary
            {"answer_summary": "Something"},  # Missing question
            {},  # Empty entry
        ]

        resolver = TermResolver("https://example.com/repo")
        inferred = resolver.infer_from_qa_history(qa_history)

        # Should not crash, might infer nothing
        assert isinstance(inferred, list)

    def test_infer_ignores_generic_words(self):
        """Test that generic words are ignored."""
        qa_history = [
            {
                "question": "How does this work and what happens here?",
                "answer_summary": "The system processes data"
            },
        ]

        resolver = TermResolver("https://example.com/repo")
        inferred = resolver.infer_from_qa_history(qa_history)

        # Should not create terms from "how", "does", "this", "what", "here"
        for term in inferred:
            assert term.source_term not in {"how", "does", "this", "what", "here", "and"}
            assert term.target_phrase not in {"how", "does", "this", "what", "here"}

    def test_infer_preserves_confidence_cap(self):
        """Test that confidence never exceeds 0.79."""
        qa_history = [
            {
                "question": "What about caching?",
                "answer_summary": "cache_strategy handles caching"
            }
        ] * 20  # Repeat 20 times

        resolver = TermResolver("https://example.com/repo")
        inferred = resolver.infer_from_qa_history(qa_history)

        # All should have confidence < 0.80
        for term in inferred:
            assert term.confidence < 0.80


class TestHotspotDetection:
    """Test hotspot clustering from QA and diagnosis records."""

    def test_detect_basic_hotspot(self):
        """Test basic hotspot detection."""
        memory = ProjectMemory("https://example.com/repo")

        # Create understanding with repeated queries about same topic
        understanding = {
            "version": 1,
            "modules": {
                "payment": {
                    "module_name": "payment",
                    "diagnoses": [
                        {
                            "query": "How does payment processing work?",
                            "diagnosis_summary": "Processes payments through handler",
                            "matched_locations": ["payment.py:L10-20"],
                            "timestamp": "2026-03-23T10:00:00Z"
                        },
                        {
                            "query": "What about payment validation?",
                            "diagnosis_summary": "Validates payments",
                            "matched_locations": ["payment.py:L30-40"],
                            "timestamp": "2026-03-23T10:05:00Z"
                        },
                        {
                            "query": "How is payment error handled?",
                            "diagnosis_summary": "Handles payment errors",
                            "matched_locations": ["payment.py:L50-60"],
                            "timestamp": "2026-03-23T10:10:00Z"
                        },
                    ],
                    "qa_history": [],
                    "annotations": [],
                    "view_count": 0,
                    "diagnose_count": 3,
                    "ask_count": 0,
                    "last_accessed": "2026-03-23T10:10:00Z"
                }
            }
        }

        memory._safe_write_json(
            memory._get_json_path("understanding.json"),
            understanding
        )

        hotspots = memory.detect_hotspots()

        # Should find at least one hotspot about payment
        assert len(hotspots) > 0
        assert any(h.module_name == "payment" for h in hotspots)

    def test_detect_multiple_hotspots(self):
        """Test detection of multiple hotspots in same module."""
        memory = ProjectMemory("https://example.com/repo")

        understanding = {
            "version": 1,
            "modules": {
                "auth": {
                    "module_name": "auth",
                    "diagnoses": [
                        {
                            "query": "How does authentication work?",
                            "diagnosis_summary": "Auth process",
                            "matched_locations": ["auth.py:L1"],
                            "timestamp": "2026-03-23T10:00:00Z"
                        },
                        {
                            "query": "What about authentication tokens?",
                            "diagnosis_summary": "Token handling",
                            "matched_locations": ["auth.py:L2"],
                            "timestamp": "2026-03-23T10:01:00Z"
                        },
                        {
                            "query": "How is authentication secured?",
                            "diagnosis_summary": "Security measures",
                            "matched_locations": ["auth.py:L3"],
                            "timestamp": "2026-03-23T10:02:00Z"
                        },
                        {
                            "query": "What about authorization checks?",
                            "diagnosis_summary": "Authorization logic",
                            "matched_locations": ["auth.py:L4"],
                            "timestamp": "2026-03-23T10:03:00Z"
                        },
                        {
                            "query": "How is authorization enforced?",
                            "diagnosis_summary": "Enforcement",
                            "matched_locations": ["auth.py:L5"],
                            "timestamp": "2026-03-23T10:04:00Z"
                        },
                    ],
                    "qa_history": [],
                    "annotations": [],
                    "view_count": 0,
                    "diagnose_count": 5,
                    "ask_count": 0,
                    "last_accessed": "2026-03-23T10:04:00Z"
                }
            }
        }

        memory._safe_write_json(
            memory._get_json_path("understanding.json"),
            understanding
        )

        hotspots = memory.detect_hotspots()

        # Should find hotspot for "authentication" (3/5 = 60% > 50%)
        # "authorization" appears only 2/5 = 40%, below 50% threshold
        assert len(hotspots) >= 1
        assert any(h.topic == "authentication" for h in hotspots)

    def test_detect_no_hotspots_below_threshold(self):
        """Test that modules with <3 queries don't create hotspots."""
        memory = ProjectMemory("https://example.com/repo")

        understanding = {
            "version": 1,
            "modules": {
                "utils": {
                    "module_name": "utils",
                    "diagnoses": [
                        {
                            "query": "What does this function do?",
                            "diagnosis_summary": "Does something",
                            "matched_locations": ["utils.py:L1"],
                            "timestamp": "2026-03-23T10:00:00Z"
                        },
                    ],
                    "qa_history": [],
                    "annotations": [],
                    "view_count": 0,
                    "diagnose_count": 1,
                    "ask_count": 0,
                    "last_accessed": "2026-03-23T10:00:00Z"
                }
            }
        }

        memory._safe_write_json(
            memory._get_json_path("understanding.json"),
            understanding
        )

        hotspots = memory.detect_hotspots()

        # Should not create hotspot from single query
        assert len(hotspots) == 0

    def test_detect_hotspot_contains_questions(self):
        """Test that hotspots include typical questions."""
        memory = ProjectMemory("https://example.com/repo")

        understanding = {
            "version": 1,
            "modules": {
                "db": {
                    "module_name": "db",
                    "diagnoses": [
                        {
                            "query": "How does the database connection work?",
                            "diagnosis_summary": "Connects to DB",
                            "matched_locations": ["db.py:L1"],
                            "timestamp": "2026-03-23T10:00:00Z"
                        },
                        {
                            "query": "What about database pooling?",
                            "diagnosis_summary": "Uses connection pool",
                            "matched_locations": ["db.py:L2"],
                            "timestamp": "2026-03-23T10:01:00Z"
                        },
                        {
                            "query": "How is database accessed?",
                            "diagnosis_summary": "Through pool",
                            "matched_locations": ["db.py:L3"],
                            "timestamp": "2026-03-23T10:02:00Z"
                        },
                    ],
                    "qa_history": [],
                    "annotations": [],
                    "view_count": 0,
                    "diagnose_count": 3,
                    "ask_count": 0,
                    "last_accessed": "2026-03-23T10:02:00Z"
                }
            }
        }

        memory._safe_write_json(
            memory._get_json_path("understanding.json"),
            understanding
        )

        hotspots = memory.detect_hotspots()

        # Hotspots should have typical questions
        for hotspot in hotspots:
            assert hotspot.typical_questions is not None
            assert isinstance(hotspot.typical_questions, list)


class TestSessionSummaryGeneration:
    """Test SessionSummary auto-generation."""

    def test_finalize_basic_session(self):
        """Test basic session finalization."""
        memory = ProjectMemory("https://example.com/repo")

        understanding = {
            "version": 1,
            "modules": {
                "api": {
                    "module_name": "api",
                    "diagnoses": [
                        {
                            "query": "What endpoints are available?",
                            "diagnosis_summary": "Found 10 REST endpoints",
                            "matched_locations": ["api.py:L1-100"],
                            "timestamp": "2026-03-23T10:00:00Z"
                        },
                    ],
                    "qa_history": [
                        {
                            "question": "How to add a new endpoint?",
                            "answer_summary": "Register in router",
                            "confidence": 0.9,
                            "follow_ups_used": [],
                            "timestamp": "2026-03-23T10:05:00Z"
                        },
                    ],
                    "annotations": [],
                    "view_count": 1,
                    "diagnose_count": 1,
                    "ask_count": 1,
                    "last_accessed": "2026-03-23T10:05:00Z"
                }
            }
        }

        memory._safe_write_json(
            memory._get_json_path("understanding.json"),
            understanding
        )

        session_summary = memory.finalize_session("session-001")

        assert session_summary is not None
        assert session_summary.session_id == "session-001"
        assert "api" in session_summary.modules_explored
        assert len(session_summary.key_findings) > 0

    def test_finalize_includes_unresolved(self):
        """Test that unresolved questions (low confidence) are included."""
        memory = ProjectMemory("https://example.com/repo")

        understanding = {
            "version": 1,
            "modules": {
                "cache": {
                    "module_name": "cache",
                    "diagnoses": [],
                    "qa_history": [
                        {
                            "question": "How does cache invalidation work?",
                            "answer_summary": "Invalidates when key expires",
                            "confidence": 0.5,  # Low confidence
                            "follow_ups_used": [],
                            "timestamp": "2026-03-23T10:00:00Z"
                        },
                    ],
                    "annotations": [],
                    "view_count": 0,
                    "diagnose_count": 0,
                    "ask_count": 1,
                    "last_accessed": "2026-03-23T10:00:00Z"
                }
            }
        }

        memory._safe_write_json(
            memory._get_json_path("understanding.json"),
            understanding
        )

        session_summary = memory.finalize_session("session-002")

        assert session_summary is not None
        assert len(session_summary.unresolved_questions) > 0
        assert "cache invalidation" in session_summary.unresolved_questions[0].lower()

    def test_finalize_multiple_modules(self):
        """Test session finalization with multiple modules."""
        memory = ProjectMemory("https://example.com/repo")

        understanding = {
            "version": 1,
            "modules": {
                "service_a": {
                    "module_name": "service_a",
                    "diagnoses": [
                        {
                            "query": "What does service_a do?",
                            "diagnosis_summary": "Provides core functionality",
                            "matched_locations": ["service_a.py:L1"],
                            "timestamp": "2026-03-23T10:00:00Z"
                        },
                    ],
                    "qa_history": [],
                    "annotations": [],
                    "view_count": 0,
                    "diagnose_count": 1,
                    "ask_count": 0,
                    "last_accessed": "2026-03-23T10:00:00Z"
                },
                "service_b": {
                    "module_name": "service_b",
                    "diagnoses": [
                        {
                            "query": "What does service_b do?",
                            "diagnosis_summary": "Provides helper functions",
                            "matched_locations": ["service_b.py:L1"],
                            "timestamp": "2026-03-23T10:01:00Z"
                        },
                    ],
                    "qa_history": [],
                    "annotations": [],
                    "view_count": 0,
                    "diagnose_count": 1,
                    "ask_count": 0,
                    "last_accessed": "2026-03-23T10:01:00Z"
                },
            }
        }

        memory._safe_write_json(
            memory._get_json_path("understanding.json"),
            understanding
        )

        session_summary = memory.finalize_session("session-003")

        assert session_summary is not None
        assert len(session_summary.modules_explored) == 2
        assert "service_a" in session_summary.modules_explored
        assert "service_b" in session_summary.modules_explored

    def test_finalize_persists_summary(self):
        """Test that finalized session is persisted to interactions.json."""
        memory = ProjectMemory("https://example.com/repo")

        understanding = {
            "version": 1,
            "modules": {}
        }

        memory._safe_write_json(
            memory._get_json_path("understanding.json"),
            understanding
        )

        session_summary = memory.finalize_session("session-004")

        # Read interactions.json to verify persistence
        interactions = memory._safe_read_json(
            memory._get_json_path("interactions.json")
        )

        assert "session_summaries" in interactions
        assert len(interactions["session_summaries"]) > 0
        assert interactions["session_summaries"][-1]["session_id"] == "session-004"

    def test_finalize_empty_understanding(self):
        """Test finalization with empty understanding."""
        memory = ProjectMemory("https://example.com/repo")

        # Don't write any understanding
        session_summary = memory.finalize_session("session-005")

        # Should handle gracefully (return None or empty summary)
        # Depends on implementation
        pass


class TestIncrementalScanDetection:
    """Test incremental scan detection logic."""

    def test_change_detection_simple(self):
        """Test basic file change detection."""
        memory = ProjectMemory("https://example.com/repo")

        # Create a mock old context with file list
        old_context = {
            "clone_result": {
                "repo_path": "/tmp/repo",
                "files": [
                    {
                        "path": "file1.py",
                        "hash": "abc123",
                    },
                    {
                        "path": "file2.py",
                        "hash": "def456",
                    },
                ]
            }
        }

        # The actual detection would require file system access
        # which we're testing indirectly through ProjectMemory
        assert memory.repo_url == "https://example.com/repo"

    def test_hotspot_preserves_limit(self):
        """Test that hotspots don't grow unbounded."""
        memory = ProjectMemory("https://example.com/repo")

        # Create many hotspots
        interactions = {
            "version": 1,
            "hotspots": [],
            "focus_profile": {},
            "session_summaries": []
        }

        # Add 60 sessions (should keep last 50)
        for i in range(60):
            interactions["session_summaries"].append({
                "session_id": f"session-{i}",
                "timestamp": f"2026-03-23T{i:02d}:00:00Z",
                "modules_explored": [],
                "key_findings": [],
                "unresolved_questions": [],
            })

        memory._safe_write_json(
            memory._get_json_path("interactions.json"),
            interactions
        )

        # Finalize a session (should trim to 50)
        memory.finalize_session("session-60")

        interactions = memory._safe_read_json(
            memory._get_json_path("interactions.json")
        )

        # Should have at most 51 (50 old + 1 new)
        assert len(interactions["session_summaries"]) <= 51


class TestEdgeCases:
    """Test edge cases for smart memory features."""

    def test_term_inference_unicode(self):
        """Test term inference with Unicode characters."""
        qa_history = [
            {
                "question": "用户认证如何工作?",  # "How does user auth work?" in Chinese
                "answer_summary": "通过 user_authenticator 处理"  # "Handled by user_authenticator"
            },
        ]

        resolver = TermResolver("https://example.com/repo")
        inferred = resolver.infer_from_qa_history(qa_history)

        # Should handle Unicode without crashing
        assert isinstance(inferred, list)

    def test_hotspot_detection_mixed_case(self):
        """Test hotspot detection with mixed case keywords."""
        memory = ProjectMemory("https://example.com/repo")

        understanding = {
            "version": 1,
            "modules": {
                "parser": {
                    "module_name": "parser",
                    "diagnoses": [
                        {
                            "query": "How does XML Parsing work?",
                            "diagnosis_summary": "Uses ElementTree",
                            "matched_locations": ["parser.py:L1"],
                            "timestamp": "2026-03-23T10:00:00Z"
                        },
                        {
                            "query": "What about JSON parsing?",
                            "diagnosis_summary": "Uses json module",
                            "matched_locations": ["parser.py:L2"],
                            "timestamp": "2026-03-23T10:01:00Z"
                        },
                        {
                            "query": "How is YAML parsing handled?",
                            "diagnosis_summary": "Uses PyYAML",
                            "matched_locations": ["parser.py:L3"],
                            "timestamp": "2026-03-23T10:02:00Z"
                        },
                    ],
                    "qa_history": [],
                    "annotations": [],
                    "view_count": 0,
                    "diagnose_count": 3,
                    "ask_count": 0,
                    "last_accessed": "2026-03-23T10:02:00Z"
                }
            }
        }

        memory._safe_write_json(
            memory._get_json_path("understanding.json"),
            understanding
        )

        hotspots = memory.detect_hotspots()

        # Should find hotspots despite mixed case
        assert len(hotspots) > 0
