"""Unit tests for ProjectMemory system."""

import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from src.memory import (
    DiagnosisRecord,
    QARecord,
    AnnotationRecord,
    ModuleUnderstanding,
    Hotspot,
    SessionSummary,
    InteractionMemory,
    ProjectMemory,
)


@pytest.fixture
def temp_memory_dir():
    """Create a temporary memory directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict("os.environ", {"HOME": tmpdir}):
            yield Path(tmpdir) / ".codebook" / "memory"


@pytest.fixture
def project_memory():
    """Create a ProjectMemory instance for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.object(Path, "home", return_value=Path(tmpdir)):
            memory = ProjectMemory("https://github.com/example/test-repo")
            yield memory


class TestDiagnosisRecord:
    """Test DiagnosisRecord model."""

    def test_create_diagnosis_record(self):
        """Test creating a diagnosis record."""
        record = DiagnosisRecord(
            query="test query",
            diagnosis_summary="test summary",
            matched_locations=["file.py:10", "file.py:20"],
            timestamp="2026-03-23T10:00:00Z",
        )
        assert record.query == "test query"
        assert record.diagnosis_summary == "test summary"
        assert len(record.matched_locations) == 2

    def test_diagnosis_record_to_dict(self):
        """Test converting diagnosis record to dict."""
        record = DiagnosisRecord(
            query="test query",
            diagnosis_summary="test summary",
            matched_locations=["file.py:10"],
            timestamp="2026-03-23T10:00:00Z",
        )
        d = record.to_dict()
        assert d["query"] == "test query"
        assert d["diagnosis_summary"] == "test summary"
        assert d["matched_locations"] == ["file.py:10"]

    def test_diagnosis_record_from_dict(self):
        """Test constructing diagnosis record from dict."""
        data = {
            "query": "test query",
            "diagnosis_summary": "test summary",
            "matched_locations": ["file.py:10"],
            "timestamp": "2026-03-23T10:00:00Z",
        }
        record = DiagnosisRecord.from_dict(data)
        assert record.query == "test query"
        assert record.diagnosis_summary == "test summary"
        assert record.timestamp == "2026-03-23T10:00:00Z"

    def test_diagnosis_record_roundtrip(self):
        """Test converting record to dict and back."""
        original = DiagnosisRecord(
            query="test query",
            diagnosis_summary="test summary",
            matched_locations=["file.py:10", "file.py:20"],
            timestamp="2026-03-23T10:00:00Z",
        )
        reconstructed = DiagnosisRecord.from_dict(original.to_dict())
        assert reconstructed.query == original.query
        assert reconstructed.diagnosis_summary == original.diagnosis_summary
        assert reconstructed.matched_locations == original.matched_locations


class TestQARecord:
    """Test QARecord model."""

    def test_create_qa_record(self):
        """Test creating a Q&A record."""
        record = QARecord(
            question="how does this work",
            answer_summary="it works like this",
            confidence=0.95,
            follow_ups_used=["follow-up 1"],
            timestamp="2026-03-23T10:00:00Z",
        )
        assert record.question == "how does this work"
        assert record.confidence == 0.95

    def test_qa_record_to_dict(self):
        """Test converting Q&A record to dict."""
        record = QARecord(
            question="test question",
            answer_summary="test answer",
            confidence=0.85,
        )
        d = record.to_dict()
        assert d["question"] == "test question"
        assert d["confidence"] == 0.85

    def test_qa_record_roundtrip(self):
        """Test converting Q&A record to dict and back."""
        original = QARecord(
            question="test question",
            answer_summary="test answer",
            confidence=0.9,
            follow_ups_used=["follow-up"],
            timestamp="2026-03-23T10:00:00Z",
        )
        reconstructed = QARecord.from_dict(original.to_dict())
        assert reconstructed.question == original.question
        assert reconstructed.confidence == original.confidence
        assert reconstructed.follow_ups_used == original.follow_ups_used


class TestModuleUnderstanding:
    """Test ModuleUnderstanding model."""

    def test_create_module_understanding(self):
        """Test creating module understanding."""
        understanding = ModuleUnderstanding(
            module_name="payment",
            view_count=5,
            diagnose_count=2,
            ask_count=3,
        )
        assert understanding.module_name == "payment"
        assert understanding.view_count == 5
        assert len(understanding.diagnoses) == 0

    def test_module_understanding_to_dict(self):
        """Test converting module understanding to dict."""
        diagnosis = DiagnosisRecord(
            query="test",
            diagnosis_summary="summary",
            matched_locations=["file.py:10"],
        )
        understanding = ModuleUnderstanding(
            module_name="payment",
            diagnoses=[diagnosis],
            view_count=5,
        )
        d = understanding.to_dict()
        assert d["module_name"] == "payment"
        assert len(d["diagnoses"]) == 1
        assert d["view_count"] == 5

    def test_module_understanding_roundtrip(self):
        """Test converting module understanding to dict and back."""
        diagnosis = DiagnosisRecord(
            query="test",
            diagnosis_summary="summary",
            matched_locations=["file.py:10"],
            timestamp="2026-03-23T10:00:00Z",
        )
        original = ModuleUnderstanding(
            module_name="payment",
            diagnoses=[diagnosis],
            view_count=5,
            last_accessed="2026-03-23T10:00:00Z",
        )
        reconstructed = ModuleUnderstanding.from_dict(original.to_dict())
        assert reconstructed.module_name == original.module_name
        assert len(reconstructed.diagnoses) == 1
        assert reconstructed.view_count == original.view_count


class TestProjectMemoryStorageStructure:
    """Test ProjectMemory storage directory structure."""

    def test_memory_dir_creation(self, project_memory):
        """Test that memory directory is created."""
        assert project_memory.memory_dir.exists()
        assert project_memory.memory_dir.is_dir()

    def test_repo_hash_generation(self, project_memory):
        """Test that repo hash is generated consistently."""
        hash1 = project_memory._hash_repo_url("https://github.com/example/repo")
        hash2 = project_memory._hash_repo_url("https://github.com/example/repo")
        assert hash1 == hash2
        assert len(hash1) == 16

    def test_different_repos_different_hashes(self):
        """Test that different repos have different hashes."""
        hash1 = ProjectMemory._hash_repo_url("https://github.com/repo1/test")
        hash2 = ProjectMemory._hash_repo_url("https://github.com/repo2/test")
        assert hash1 != hash2


class TestProjectMemoryContextStorage:
    """Test structural memory (context.json) operations."""

    def test_store_and_retrieve_context(self, project_memory):
        """Test storing and retrieving SummaryContext."""
        context = {
            "clone_result": {"repo_url": "test"},
            "modules": ["module1", "module2"],
        }
        assert project_memory.store_context(context) is True

        retrieved = project_memory.get_context()
        assert retrieved is not None
        assert retrieved["clone_result"]["repo_url"] == "test"
        assert "module1" in retrieved["modules"]

    def test_get_context_missing_file(self, project_memory):
        """Test retrieving context when file doesn't exist."""
        retrieved = project_memory.get_context()
        assert retrieved is None

    def test_context_file_structure(self, project_memory):
        """Test that context.json has proper structure."""
        context = {"test": "data"}
        project_memory.store_context(context)

        with open(project_memory._get_json_path("context.json"), "r") as f:
            data = json.load(f)

        assert "version" in data
        assert "repo_url" in data
        assert "timestamp" in data
        assert "context" in data


class TestProjectMemoryDiagnosisStorage:
    """Test understanding memory (diagnosis) operations."""

    def test_add_diagnosis(self, project_memory):
        """Test adding a diagnosis record."""
        record = DiagnosisRecord(
            query="test query",
            diagnosis_summary="test summary",
            matched_locations=["file.py:10"],
            timestamp="2026-03-23T10:00:00Z",
        )
        assert project_memory.add_diagnosis("payment", record) is True

    def test_get_module_understanding(self, project_memory):
        """Test retrieving module understanding."""
        record = DiagnosisRecord(
            query="test query",
            diagnosis_summary="test summary",
            matched_locations=["file.py:10"],
            timestamp="2026-03-23T10:00:00Z",
        )
        project_memory.add_diagnosis("payment", record)

        understanding = project_memory.get_module_understanding("payment")
        assert understanding is not None
        assert understanding.module_name == "payment"
        assert len(understanding.diagnoses) == 1
        assert understanding.diagnose_count == 1

    def test_add_multiple_diagnoses(self, project_memory):
        """Test adding multiple diagnoses to same module."""
        record1 = DiagnosisRecord(
            query="query 1",
            diagnosis_summary="summary 1",
            matched_locations=["file.py:10"],
        )
        record2 = DiagnosisRecord(
            query="query 2",
            diagnosis_summary="summary 2",
            matched_locations=["file.py:20"],
        )
        project_memory.add_diagnosis("payment", record1)
        project_memory.add_diagnosis("payment", record2)

        understanding = project_memory.get_module_understanding("payment")
        assert len(understanding.diagnoses) == 2
        assert understanding.diagnose_count == 2

    def test_module_understanding_nonexistent(self, project_memory):
        """Test retrieving understanding for non-existent module."""
        understanding = project_memory.get_module_understanding("nonexistent")
        assert understanding is None


class TestProjectMemoryQAStorage:
    """Test understanding memory (Q&A) operations."""

    def test_add_qa_record(self, project_memory):
        """Test adding a Q&A record."""
        record = QARecord(
            question="how does this work",
            answer_summary="it works like this",
            confidence=0.95,
            timestamp="2026-03-23T10:00:00Z",
        )
        assert project_memory.add_qa_record("payment", record) is True

    def test_qa_record_increments_count(self, project_memory):
        """Test that ask_count is incremented."""
        record = QARecord(
            question="test question",
            answer_summary="test answer",
            confidence=0.9,
        )
        project_memory.add_qa_record("payment", record)

        understanding = project_memory.get_module_understanding("payment")
        assert understanding.ask_count == 1

    def test_add_multiple_qa_records(self, project_memory):
        """Test adding multiple Q&A records."""
        for i in range(3):
            record = QARecord(
                question=f"question {i}",
                answer_summary=f"answer {i}",
                confidence=0.9,
            )
            project_memory.add_qa_record("payment", record)

        understanding = project_memory.get_module_understanding("payment")
        assert len(understanding.qa_history) == 3
        assert understanding.ask_count == 3


class TestProjectMemoryInteractionStorage:
    """Test interaction memory operations."""

    def test_add_session_summary(self, project_memory):
        """Test adding a session summary."""
        summary = SessionSummary(
            session_id="session-123",
            timestamp="2026-03-23T10:00:00Z",
            modules_explored=["payment", "auth"],
            key_findings=["found bug in payment flow"],
        )
        assert project_memory.add_session_summary(summary) is True

    def test_get_hotspots_empty(self, project_memory):
        """Test getting hotspots when none exist."""
        hotspots = project_memory.get_hotspots()
        assert isinstance(hotspots, list)
        assert len(hotspots) == 0

    def test_get_interaction_memory(self, project_memory):
        """Test retrieving interaction memory."""
        memory = project_memory.get_interaction_memory()
        assert isinstance(memory, InteractionMemory)
        assert len(memory.hotspots) == 0
        assert len(memory.session_summaries) == 0


class TestProjectMemoryMetadata:
    """Test metadata operations."""

    def test_get_meta_default(self, project_memory):
        """Test getting default metadata."""
        meta = project_memory.get_meta()
        assert "version" in meta
        assert "repo_url" in meta
        assert meta["repo_url"] == "https://github.com/example/test-repo"

    def test_update_meta(self, project_memory):
        """Test updating metadata."""
        assert project_memory.update_meta(project_domain="fintech") is True

        meta = project_memory.get_meta()
        assert meta["project_domain"] == "fintech"
        assert "updated_at" in meta

    def test_meta_persistence(self, project_memory):
        """Test that metadata is persisted."""
        project_memory.update_meta(custom_field="test_value")

        # Create new instance and verify metadata persists
        memory2 = ProjectMemory("https://github.com/example/test-repo")
        meta = memory2.get_meta()
        assert meta["custom_field"] == "test_value"


class TestProjectMemoryGracefulDegradation:
    """Test graceful handling of missing files."""

    def test_get_context_missing_file_returns_none(self, project_memory):
        """Test that missing context.json returns None."""
        context = project_memory.get_context()
        assert context is None

    def test_get_module_understanding_missing_file_returns_none(self, project_memory):
        """Test that missing understanding.json returns None."""
        understanding = project_memory.get_module_understanding("nonexistent")
        assert understanding is None

    def test_get_hotspots_missing_file_returns_empty_list(self, project_memory):
        """Test that missing interactions.json returns empty list."""
        hotspots = project_memory.get_hotspots()
        assert hotspots == []

    def test_get_glossary_missing_file_returns_empty_dict(self, project_memory):
        """Test that missing glossary.json returns empty dict."""
        glossary = project_memory.get_glossary()
        assert glossary == {}


class TestProjectMemoryConsistency:
    """Test read/write consistency."""

    def test_context_roundtrip_consistency(self, project_memory):
        """Test that context survives write and read."""
        original = {
            "modules": ["payment", "auth"],
            "stats": {"functions": 100, "classes": 20},
        }
        project_memory.store_context(original)

        retrieved = project_memory.get_context()
        assert retrieved == original

    def test_diagnosis_roundtrip_consistency(self, project_memory):
        """Test that diagnosis survives write and read."""
        record = DiagnosisRecord(
            query="original query",
            diagnosis_summary="original summary",
            matched_locations=["file1.py:10", "file2.py:20"],
            timestamp="2026-03-23T10:00:00Z",
        )
        project_memory.add_diagnosis("test_module", record)

        understanding = project_memory.get_module_understanding("test_module")
        retrieved_record = understanding.diagnoses[0]

        assert retrieved_record.query == record.query
        assert retrieved_record.diagnosis_summary == record.diagnosis_summary
        assert retrieved_record.matched_locations == record.matched_locations

    def test_qa_record_roundtrip_consistency(self, project_memory):
        """Test that Q&A records survive write and read."""
        record = QARecord(
            question="test question",
            answer_summary="test answer",
            confidence=0.87,
            follow_ups_used=["follow-up 1", "follow-up 2"],
            timestamp="2026-03-23T10:00:00Z",
        )
        project_memory.add_qa_record("test_module", record)

        understanding = project_memory.get_module_understanding("test_module")
        retrieved = understanding.qa_history[0]

        assert retrieved.question == record.question
        assert retrieved.answer_summary == record.answer_summary
        assert retrieved.confidence == record.confidence
        assert retrieved.follow_ups_used == record.follow_ups_used


class TestProjectMemoryConcurrency:
    """Test basic concurrency safety."""

    def test_concurrent_writes_to_different_modules(self, project_memory):
        """Test that writes to different modules don't interfere."""
        record1 = DiagnosisRecord(
            query="query1",
            diagnosis_summary="summary1",
            matched_locations=["file1.py:10"],
        )
        record2 = DiagnosisRecord(
            query="query2",
            diagnosis_summary="summary2",
            matched_locations=["file2.py:20"],
        )

        project_memory.add_diagnosis("module1", record1)
        project_memory.add_diagnosis("module2", record2)

        understanding1 = project_memory.get_module_understanding("module1")
        understanding2 = project_memory.get_module_understanding("module2")

        assert understanding1.diagnoses[0].query == "query1"
        assert understanding2.diagnoses[0].query == "query2"


class TestProjectMemorySessionFinalization:
    """Test session finalization."""

    def test_finalize_session(self, project_memory):
        """Test finalizing a session."""
        result = project_memory.finalize_session("session-123")
        assert result is not None

        meta = project_memory.get_meta()
        assert "last_session_at" in meta
        assert meta["last_session_id"] == "session-123"

    def test_finalize_session_updates_timestamp(self, project_memory):
        """Test that finalize_session updates timestamp."""
        before = datetime.utcnow().isoformat()
        project_memory.finalize_session("session-123")
        after = datetime.utcnow().isoformat()

        meta = project_memory.get_meta()
        assert before <= meta["last_session_at"] <= after
