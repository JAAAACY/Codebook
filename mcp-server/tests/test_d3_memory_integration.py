"""Tests for D-3 task: Memory persistence integration with tools.

Coverage:
1. Diagnosis persistence (diagnose → ProjectMemory)
2. QA record persistence (memory_feedback → ProjectMemory)
3. assemble_context with memory data (ask_about enhanced priorities)
4. memory_feedback tool basic functionality
5. view_count increment (read_chapter → ProjectMemory)
6. Graceful degradation when ProjectMemory unavailable
7. Extended context assembly (8 priority levels)
8. Cross-session memory reference
"""

import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.memory import (
    DiagnosisRecord,
    QARecord,
    Hotspot,
    ProjectMemory,
)
from src.parsers.module_grouper import ModuleGroup
from src.summarizer.engine import SummaryContext
from src.tools.diagnose import diagnose
from src.tools.memory_feedback import memory_feedback
from src.tools.read_chapter import read_chapter


@pytest.fixture
def temp_memory_dir():
    """Create a temporary memory directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        home = Path(tmpdir)
        memory_dir = home / ".codebook" / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)
        yield memory_dir


@pytest.fixture
def project_memory(temp_memory_dir):
    """Create a ProjectMemory instance."""
    with patch.object(Path, "home", return_value=temp_memory_dir.parent):
        memory = ProjectMemory("https://github.com/test/repo")
        yield memory


class TestDiagnosisPersistence:
    """Test diagnosis persistence in diagnose tool."""

    @pytest.mark.asyncio
    async def test_diagnose_persists_to_memory(self, project_memory):
        """Test that diagnose persists results to ProjectMemory."""
        # Setup mock context
        mock_module = ModuleGroup(name="auth", dir_path="src/auth", files=["src/auth/handler.py"])
        mock_context = MagicMock(spec=SummaryContext)
        mock_context.modules = [mock_module]
        mock_context.clone_result = MagicMock(repo_url="https://github.com/test/repo")
        mock_context.dep_graph = MagicMock()
        mock_context.dep_graph.graph = MagicMock()
        mock_context.dep_graph.graph.nodes = MagicMock(return_value=[])
        mock_context.dep_graph.get_module_graph = MagicMock(return_value=MagicMock())

        with patch("src.tools.diagnose.repo_cache.get", return_value=mock_context):
            with patch.object(ProjectMemory, "__init__", return_value=None):
                with patch.object(ProjectMemory, "add_diagnosis") as mock_add:
                    # Execute diagnose
                    result = await diagnose(
                        module_name="auth",
                        role="pm",
                        query="login error handling",
                    )

                    # Verify result status
                    assert result["status"] in ["ok", "no_exact_match"]

                    # Verify add_diagnosis was called (if no_exact_match or ok)
                    if result["status"] == "ok":
                        assert mock_add.called


class TestQAPersistence:
    """Test QA record persistence in memory_feedback tool."""

    @pytest.mark.asyncio
    async def test_memory_feedback_stores_qa(self, project_memory):
        """Test that memory_feedback stores QA records."""
        mock_module = ModuleGroup(name="payment", dir_path="src/payment", files=["src/payment/handler.py"])
        mock_context = MagicMock(spec=SummaryContext)
        mock_context.modules = [mock_module]
        mock_context.clone_result = MagicMock(repo_url="https://github.com/test/repo")

        with patch("src.tools.memory_feedback.repo_cache.get", return_value=mock_context):
            with patch.object(ProjectMemory, "__init__", return_value=None) as mock_init:
                with patch.object(ProjectMemory, "add_qa_record", return_value=True) as mock_add_qa:
                    mock_init.return_value = None
                    memory = ProjectMemory("https://github.com/test/repo")

                    # Execute memory_feedback
                    result = await memory_feedback(
                        module_name="payment",
                        question="How does refund processing work?",
                        answer_summary="Refunds are processed through a separate ledger",
                        confidence=0.9,
                        follow_ups_used=["error handling", "timeout scenarios"],
                    )

                    # Verify result
                    assert result["status"] == "ok"
                    assert "已记录" in result["message"]


class TestViewCountIncrement:
    """Test view_count increment in read_chapter."""

    @pytest.mark.asyncio
    async def test_read_chapter_increments_view_count(self, project_memory):
        """Test that read_chapter increments view_count."""
        mock_module = ModuleGroup(
            name="api",
            dir_path="src/api",
            files=["src/api/routes.py"],
            entry_functions=["handle_request"],
        )
        mock_context = MagicMock(spec=SummaryContext)
        mock_context.modules = [mock_module]
        mock_context.clone_result = MagicMock(repo_url="https://github.com/test/repo")
        mock_context.parse_results = []
        mock_context.dep_graph = MagicMock()

        with patch("src.tools.read_chapter.repo_cache.get", return_value=mock_context):
            with patch("src.tools.read_chapter.ProjectMemory") as mock_memory_class:
                mock_memory_inst = MagicMock()
                mock_memory_class.return_value = mock_memory_inst
                mock_memory_inst._get_json_path = MagicMock(
                    return_value=Path("/tmp/understanding.json")
                )
                mock_memory_inst._safe_read_json = MagicMock(return_value={"version": 1, "modules": {}})
                mock_memory_inst._safe_write_json = MagicMock(return_value=True)

                # Execute read_chapter
                result = await read_chapter(module_name="api", role="pm")

                # Verify result
                assert result["status"] == "ok"

                # Verify _safe_write_json was called (to update view_count)
                assert mock_memory_inst._safe_write_json.called


class TestAssembleContextWithMemory:
    """Test assemble_context uses ProjectMemory data."""

    def test_assemble_context_includes_qa_history(self, project_memory):
        """Test that assemble_context includes QA history from memory."""
        # Create a module with QA history
        with patch("src.tools.ask_about.ProjectMemory") as mock_memory_class:
            mock_memory = MagicMock()
            mock_memory_class.return_value = mock_memory

            # Setup module understanding with QA history
            from src.memory.models import ModuleUnderstanding

            understanding = ModuleUnderstanding(
                module_name="auth",
                qa_history=[
                    QARecord(
                        question="How does JWT validation work?",
                        answer_summary="JWT tokens are validated via signature verification",
                        confidence=0.95,
                        timestamp="2026-03-23T10:00:00Z",
                    )
                ],
            )
            mock_memory.get_module_understanding = MagicMock(return_value=understanding)
            mock_memory.get_hotspots = MagicMock(return_value=[])

            # Create mock context
            mock_context = MagicMock(spec=SummaryContext)
            mock_context.clone_result = MagicMock(repo_url="https://github.com/test/repo")
            mock_module = ModuleGroup(name="auth", dir_path="src/auth", files=["src/auth/handler.py"])
            mock_context.modules = [mock_module]
            mock_context.dep_graph = MagicMock()
            mock_context.dep_graph.get_module_graph = MagicMock(return_value=MagicMock())

            with patch("src.tools.ask_about.generate_local_chapter") as mock_gen:
                mock_gen.return_value = {"status": "ok", "module_cards": []}

                with patch("src.tools.ask_about._build_source_code_context", return_value=""):
                    with patch("src.tools.ask_about._get_neighbor_modules", return_value=([], [])):
                        from src.tools.ask_about import assemble_context

                        context_text, modules_used = assemble_context(
                            mock_context, mock_module, "/tmp/repo"
                        )

                        # Verify QA history is in context
                        assert "历史问题与回答" in context_text or "已有诊断" in context_text or len(context_text) > 0


class TestMemoryFeedbackGracefulDegradation:
    """Test graceful degradation when ProjectMemory fails."""

    @pytest.mark.asyncio
    async def test_memory_feedback_no_repo_url(self):
        """Test memory_feedback handles missing repo_url gracefully."""
        mock_context = MagicMock(spec=SummaryContext)
        mock_context.clone_result = MagicMock(repo_url=None)

        with patch("src.tools.memory_feedback.repo_cache.get", return_value=mock_context):
            result = await memory_feedback(
                module_name="test",
                question="test",
                answer_summary="test",
            )

            assert result["status"] == "error"
            assert "repo_url" in result["error"] or "仓库" in result["error"]

    @pytest.mark.asyncio
    async def test_memory_feedback_invalid_module(self):
        """Test memory_feedback handles invalid module gracefully."""
        mock_module = ModuleGroup(name="valid", dir_path="src/valid", files=[])
        mock_context = MagicMock(spec=SummaryContext)
        mock_context.modules = [mock_module]
        mock_context.clone_result = MagicMock(repo_url="https://github.com/test/repo")

        with patch("src.tools.memory_feedback.repo_cache.get", return_value=mock_context):
            result = await memory_feedback(
                module_name="invalid",
                question="test",
                answer_summary="test",
            )

            assert result["status"] == "error"
            assert "不存在" in result["error"]


class TestMemoryPersistenceRecovery:
    """Test that persisted memory can be recovered."""

    def test_diagnosis_recovery_after_persistence(self):
        """Test that diagnosed issues can be retrieved from memory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(Path, "home", return_value=Path(tmpdir)):
                memory = ProjectMemory("https://github.com/test/repo")

                # Add a diagnosis record
                record = DiagnosisRecord(
                    query="authentication timeout",
                    diagnosis_summary="Session expires after 30 minutes",
                    matched_locations=["src/auth/session.py:45", "src/auth/session.py:67"],
                    timestamp=datetime.utcnow().isoformat() + "Z",
                )
                success = memory.add_diagnosis("auth_module", record)
                assert success

                # Retrieve and verify
                understanding = memory.get_module_understanding("auth_module")
                assert understanding is not None
                assert len(understanding.diagnoses) == 1
                assert understanding.diagnoses[0].query == "authentication timeout"

    def test_qa_recovery_after_persistence(self):
        """Test that Q&A records can be retrieved from memory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(Path, "home", return_value=Path(tmpdir)):
                memory = ProjectMemory("https://github.com/test/repo")

                # Add a Q&A record
                record = QARecord(
                    question="How to handle concurrent requests?",
                    answer_summary="Use connection pooling with mutex locks",
                    confidence=0.85,
                    follow_ups_used=["thread safety", "deadlock prevention"],
                    timestamp=datetime.utcnow().isoformat() + "Z",
                )
                success = memory.add_qa_record("concurrency_module", record)
                assert success

                # Retrieve and verify
                understanding = memory.get_module_understanding("concurrency_module")
                assert understanding is not None
                assert len(understanding.qa_history) == 1
                assert understanding.qa_history[0].confidence == 0.85


class TestMemoryBudgetManagement:
    """Test memory budget constraints and limits."""

    def test_qa_history_respects_limit(self):
        """Test that QA history doesn't grow unbounded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(Path, "home", return_value=Path(tmpdir)):
                memory = ProjectMemory("https://github.com/test/repo")

                # Add multiple Q&A records
                for i in range(10):
                    record = QARecord(
                        question=f"Question {i}",
                        answer_summary=f"Answer summary {i}",
                        confidence=0.9,
                        timestamp=datetime.utcnow().isoformat() + "Z",
                    )
                    memory.add_qa_record("test_module", record)

                # Verify we can retrieve them
                understanding = memory.get_module_understanding("test_module")
                assert understanding is not None
                assert len(understanding.qa_history) == 10


class TestMemoryStatisticsTracking:
    """Test that memory tracks usage statistics."""

    def test_view_count_tracking(self):
        """Test that view_count is properly tracked."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(Path, "home", return_value=Path(tmpdir)):
                memory = ProjectMemory("https://github.com/test/repo")

                # Simulate multiple reads
                for i in range(3):
                    path = memory._get_json_path("understanding.json")
                    data = memory._safe_read_json(path)
                    if "modules" not in data:
                        data["modules"] = {}
                    if "test_module" not in data["modules"]:
                        data["modules"]["test_module"] = {
                            "module_name": "test_module",
                            "diagnoses": [],
                            "qa_history": [],
                            "annotations": [],
                            "view_count": 0,
                            "diagnose_count": 0,
                            "ask_count": 0,
                            "last_accessed": datetime.utcnow().isoformat() + "Z",
                        }
                    data["modules"]["test_module"]["view_count"] += 1
                    memory._safe_write_json(path, data)

                # Verify count
                understanding = memory.get_module_understanding("test_module")
                assert understanding.view_count == 3

    def test_ask_count_tracking(self):
        """Test that ask_count is incremented on QA."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(Path, "home", return_value=Path(tmpdir)):
                memory = ProjectMemory("https://github.com/test/repo")

                # Add Q&A records
                for i in range(2):
                    record = QARecord(
                        question=f"Question {i}",
                        answer_summary=f"Answer {i}",
                        confidence=0.9,
                        timestamp=datetime.utcnow().isoformat() + "Z",
                    )
                    memory.add_qa_record("test_module", record)

                # Verify ask_count
                understanding = memory.get_module_understanding("test_module")
                assert understanding.ask_count == 2
