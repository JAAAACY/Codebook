"""
ProjectMemory: Unified storage layer for three-layer memory system.

Storage layout:
~/.codebook/memory/{repo_hash}/
├── context.json         # Structural memory (SummaryContext)
├── understanding.json   # Understanding memory (ModuleUnderstanding records)
├── interactions.json    # Interaction memory (hotspots, sessions)
├── glossary.json        # Terminology storage
└── meta.json           # Metadata (repo_url, domain, stats)
"""

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import structlog

from .models import (
    DiagnosisRecord,
    QARecord,
    AnnotationRecord,
    ModuleUnderstanding,
    Hotspot,
    SessionSummary,
    InteractionMemory,
)

logger = structlog.get_logger(__name__)


class ProjectMemory:
    """Unified storage for project memory across three layers."""

    def __init__(self, repo_url: str):
        """Initialize ProjectMemory with a repository URL.

        Args:
            repo_url: URL of the repository being analyzed.
        """
        self.repo_url = repo_url
        self.repo_hash = self._hash_repo_url(repo_url)
        self.memory_dir = self._get_memory_dir()
        self._ensure_memory_dir()

    @staticmethod
    def _hash_repo_url(repo_url: str) -> str:
        """Generate a stable hash for the repository URL."""
        return hashlib.sha256(repo_url.encode()).hexdigest()[:16]

    def _get_memory_dir(self) -> Path:
        """Get the memory directory path."""
        codebook_home = Path.home() / ".codebook" / "memory" / self.repo_hash
        return codebook_home

    def _ensure_memory_dir(self) -> None:
        """Ensure memory directory exists."""
        self.memory_dir.mkdir(parents=True, exist_ok=True)

    def _get_json_path(self, filename: str) -> Path:
        """Get full path for a JSON file."""
        return self.memory_dir / filename

    def _safe_read_json(self, path: Path) -> dict[str, Any]:
        """Safely read JSON file, return empty dict on missing file."""
        try:
            if not path.exists():
                logger.debug("json_file_missing", path=str(path))
                return {}
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                logger.debug("json_file_read", path=str(path), size=len(data))
                return data
        except Exception as e:
            logger.exception(
                "json_read_failed",
                path=str(path),
                error=str(e),
            )
            return {}

    def _safe_write_json(self, path: Path, data: dict[str, Any]) -> bool:
        """Safely write JSON file, return success status."""
        try:
            self._ensure_memory_dir()
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.debug("json_file_written", path=str(path), size=len(data))
            return True
        except Exception as e:
            logger.exception(
                "json_write_failed",
                path=str(path),
                error=str(e),
            )
            return False

    # ========== Structural Memory (context.json) ==========

    def store_context(self, ctx: dict[str, Any]) -> bool:
        """Store SummaryContext to context.json."""
        data = {
            "version": 1,
            "repo_url": self.repo_url,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "context": ctx,
        }
        return self._safe_write_json(self._get_json_path("context.json"), data)

    def get_context(self) -> Optional[dict[str, Any]]:
        """Retrieve SummaryContext from context.json."""
        data = self._safe_read_json(self._get_json_path("context.json"))
        if not data:
            return None
        return data.get("context")

    # ========== Understanding Memory (understanding.json) ==========

    def get_understanding(self) -> Optional[dict[str, Any]]:
        """Retrieve entire understanding data (all modules)."""
        data = self._safe_read_json(self._get_json_path("understanding.json"))
        if not data:
            return None
        return data

    def add_diagnosis(self, module_name: str, record: DiagnosisRecord) -> bool:
        """Add a diagnosis record to a module's understanding."""
        try:
            path = self._get_json_path("understanding.json")
            data = self._safe_read_json(path)

            # Initialize structure if needed
            if "version" not in data:
                data = {
                    "version": 1,
                    "modules": {},
                }

            if "modules" not in data:
                data["modules"] = {}

            # Get or create module entry
            if module_name not in data["modules"]:
                data["modules"][module_name] = {
                    "module_name": module_name,
                    "diagnoses": [],
                    "qa_history": [],
                    "annotations": [],
                    "view_count": 0,
                    "diagnose_count": 0,
                    "ask_count": 0,
                    "last_accessed": datetime.utcnow().isoformat() + "Z",
                }

            # Add diagnosis
            data["modules"][module_name]["diagnoses"].append(record.to_dict())
            data["modules"][module_name]["diagnose_count"] += 1
            data["modules"][module_name]["last_accessed"] = (
                datetime.utcnow().isoformat() + "Z"
            )

            return self._safe_write_json(path, data)
        except Exception as e:
            logger.exception("add_diagnosis_failed", module=module_name, error=str(e))
            return False

    def add_qa_record(self, module_name: str, record: QARecord) -> bool:
        """Add a Q&A record to a module's understanding."""
        try:
            path = self._get_json_path("understanding.json")
            data = self._safe_read_json(path)

            # Initialize structure if needed
            if "version" not in data:
                data = {
                    "version": 1,
                    "modules": {},
                }

            if "modules" not in data:
                data["modules"] = {}

            # Get or create module entry
            if module_name not in data["modules"]:
                data["modules"][module_name] = {
                    "module_name": module_name,
                    "diagnoses": [],
                    "qa_history": [],
                    "annotations": [],
                    "view_count": 0,
                    "diagnose_count": 0,
                    "ask_count": 0,
                    "last_accessed": datetime.utcnow().isoformat() + "Z",
                }

            # Add Q&A record
            data["modules"][module_name]["qa_history"].append(record.to_dict())
            data["modules"][module_name]["ask_count"] += 1
            data["modules"][module_name]["last_accessed"] = (
                datetime.utcnow().isoformat() + "Z"
            )

            return self._safe_write_json(path, data)
        except Exception as e:
            logger.exception("add_qa_record_failed", module=module_name, error=str(e))
            return False

    def get_module_understanding(self, module_name: str) -> Optional[ModuleUnderstanding]:
        """Retrieve understanding for a specific module."""
        try:
            path = self._get_json_path("understanding.json")
            data = self._safe_read_json(path)

            if not data or "modules" not in data:
                return None

            module_data = data["modules"].get(module_name)
            if not module_data:
                return None

            return ModuleUnderstanding.from_dict(module_data)
        except Exception as e:
            logger.exception(
                "get_module_understanding_failed",
                module=module_name,
                error=str(e),
            )
            return None

    # ========== Interaction Memory (interactions.json) ==========

    def add_session_summary(self, summary: SessionSummary) -> bool:
        """Add a session summary to interaction memory."""
        try:
            path = self._get_json_path("interactions.json")
            data = self._safe_read_json(path)

            # Initialize structure if needed
            if "version" not in data:
                data = {
                    "version": 1,
                    "hotspots": [],
                    "focus_profile": {},
                    "session_summaries": [],
                }

            if "session_summaries" not in data:
                data["session_summaries"] = []

            # Add session summary
            data["session_summaries"].append(summary.to_dict())

            return self._safe_write_json(path, data)
        except Exception as e:
            logger.exception("add_session_summary_failed", error=str(e))
            return False

    def get_hotspots(self, module_name: Optional[str] = None) -> list[Hotspot]:
        """Retrieve hotspots, optionally filtered by module."""
        try:
            path = self._get_json_path("interactions.json")
            data = self._safe_read_json(path)

            if not data or "hotspots" not in data:
                return []

            hotspots = [Hotspot.from_dict(h) for h in data["hotspots"]]

            if module_name:
                hotspots = [h for h in hotspots if h.module_name == module_name]

            return hotspots
        except Exception as e:
            logger.exception("get_hotspots_failed", module=module_name, error=str(e))
            return []

    def get_interaction_memory(self) -> InteractionMemory:
        """Retrieve complete interaction memory."""
        try:
            path = self._get_json_path("interactions.json")
            data = self._safe_read_json(path)

            if not data:
                return InteractionMemory()

            return InteractionMemory.from_dict(data)
        except Exception as e:
            logger.exception("get_interaction_memory_failed", error=str(e))
            return InteractionMemory()

    # ========== Metadata (meta.json) ==========

    def get_meta(self) -> dict[str, Any]:
        """Retrieve metadata."""
        data = self._safe_read_json(self._get_json_path("meta.json"))
        if not data:
            return {
                "version": 1,
                "repo_url": self.repo_url,
                "created_at": datetime.utcnow().isoformat() + "Z",
            }
        return data

    def update_meta(self, **kwargs: Any) -> bool:
        """Update metadata fields."""
        try:
            path = self._get_json_path("meta.json")
            data = self.get_meta()

            # Update with provided kwargs
            for key, value in kwargs.items():
                data[key] = value

            data["updated_at"] = datetime.utcnow().isoformat() + "Z"

            return self._safe_write_json(path, data)
        except Exception as e:
            logger.exception("update_meta_failed", error=str(e))
            return False

    # ========== Glossary (glossary.json) ==========

    def get_glossary(self) -> dict[str, Any]:
        """Retrieve glossary data."""
        return self._safe_read_json(self._get_json_path("glossary.json"))

    def store_glossary(self, glossary: dict[str, Any]) -> bool:
        """Store glossary data."""
        return self._safe_write_json(self._get_json_path("glossary.json"), glossary)

    # ========== Hotspot Detection ==========

    def detect_hotspots(self) -> list[Hotspot]:
        """Detect knowledge hotspots from understanding and diagnosis records.

        Rule: Same module queried 3+ times with keyword overlap > 50%.

        Returns:
            List of Hotspot objects representing frequently asked areas.
        """
        hotspots: dict[str, Hotspot] = {}

        try:
            # Read understanding.json to get all modules and their records
            path = self._get_json_path("understanding.json")
            understanding = self._safe_read_json(path)
            if not understanding or "modules" not in understanding:
                return []

            # Analyze each module
            for module_name, module_data in understanding.get("modules", {}).items():
                diagnoses = module_data.get("diagnoses", [])
                qa_history = module_data.get("qa_history", [])

                # Skip if fewer than 3 queries
                total_queries = len(diagnoses) + len(qa_history)
                if total_queries < 3:
                    continue

                # Extract keywords from all queries
                all_keywords: list[str] = []

                for diag in diagnoses:
                    query = diag.get("query", "")
                    keywords = self._extract_keywords(query)
                    all_keywords.extend(keywords)

                for qa in qa_history:
                    question = qa.get("question", "")
                    keywords = self._extract_keywords(question)
                    all_keywords.extend(keywords)

                # Find dominant topics (keywords appearing in > 50% of queries)
                if not all_keywords:
                    continue

                keyword_freq = {}
                for kw in all_keywords:
                    keyword_freq[kw] = keyword_freq.get(kw, 0) + 1

                threshold = total_queries * 0.5

                for keyword, count in keyword_freq.items():
                    if count >= threshold:
                        hotspot_key = f"{module_name}:{keyword}"

                        if hotspot_key not in hotspots:
                            # Collect typical questions
                            typical_questions = self._collect_typical_questions(
                                module_name, keyword, understanding
                            )

                            hotspots[hotspot_key] = Hotspot(
                                module_name=module_name,
                                topic=keyword,
                                question_count=count,
                                typical_questions=typical_questions,
                                suggested_doc="",
                            )

            result = list(hotspots.values())
            logger.info(
                "hotspots_detected",
                hotspot_count=len(result),
            )
            return result

        except Exception as e:
            logger.exception("detect_hotspots_failed", error=str(e))
            return []

    @staticmethod
    def _extract_keywords(text: str) -> list[str]:
        """Extract keywords from text (lowercased, min 3 chars)."""
        if not text:
            return []

        words = text.lower().split()
        return [
            w.strip(".,!?;:")
            for w in words
            if len(w.strip(".,!?;:")) >= 3
            and not w in {"the", "and", "how", "what", "when", "where", "why", "this", "that"}
        ]

    @staticmethod
    def _collect_typical_questions(
        module_name: str, keyword: str, understanding: dict
    ) -> list[str]:
        """Collect up to 3 most representative questions containing the keyword."""
        matching_questions = []

        module_data = understanding.get("modules", {}).get(module_name, {})

        # From diagnoses
        for diag in module_data.get("diagnoses", []):
            query = diag.get("query", "")
            if keyword.lower() in query.lower():
                matching_questions.append(query)

        # From QA history
        for qa in module_data.get("qa_history", []):
            question = qa.get("question", "")
            if keyword.lower() in question.lower():
                matching_questions.append(question)

        # Return up to 3, preferring longer questions (more context)
        return sorted(matching_questions, key=len, reverse=True)[:3]

    # ========== Session Finalization ==========

    def finalize_session(self, session_id: str) -> Optional[SessionSummary]:
        """Finalize a session by creating a summary and updating metadata.

        Summarizes: modules_explored, key_findings, unresolved_questions.

        Args:
            session_id: Session identifier.

        Returns:
            SessionSummary object if successful, None otherwise.
        """
        try:
            # Read understanding.json to get all modules and their records
            path = self._get_json_path("understanding.json")
            understanding = self._safe_read_json(path)

            # Initialize empty data if missing
            if not understanding:
                understanding = {"version": 1, "modules": {}}

            # Collect modules explored
            modules_explored = list(understanding.get("modules", {}).keys())

            # Extract key findings from diagnoses
            key_findings = []
            for module_name, module_data in understanding.get("modules", {}).items():
                for diag in module_data.get("diagnoses", [])[-3:]:  # Last 3 diagnoses
                    diag_summary = diag.get("diagnosis_summary", "")
                    if diag_summary:
                        key_findings.append(diag_summary)

            # Extract unresolved questions (questions with low confidence)
            unresolved_questions = []
            for module_name, module_data in understanding.get("modules", {}).items():
                for qa in module_data.get("qa_history", []):
                    confidence = float(qa.get("confidence", 0.0))
                    if confidence < 0.7:  # Low confidence = unresolved
                        question = qa.get("question", "")
                        if question:
                            unresolved_questions.append(question)

            # Create SessionSummary
            session_summary = SessionSummary(
                session_id=session_id,
                timestamp=datetime.utcnow().isoformat() + "Z",
                modules_explored=modules_explored,
                key_findings=key_findings[:5],  # Top 5 findings
                unresolved_questions=unresolved_questions[:5],  # Top 5 unresolved
            )

            # Store the session summary
            interactions_path = self._get_json_path("interactions.json")
            interactions = self._safe_read_json(interactions_path)

            if "version" not in interactions:
                interactions = {
                    "version": 1,
                    "hotspots": [],
                    "focus_profile": {},
                    "session_summaries": [],
                }

            # Append the new session summary
            if "session_summaries" not in interactions:
                interactions["session_summaries"] = []

            interactions["session_summaries"].append(session_summary.to_dict())

            # Keep only last 50 sessions
            if len(interactions["session_summaries"]) > 50:
                interactions["session_summaries"] = interactions["session_summaries"][-50:]

            self._safe_write_json(interactions_path, interactions)

            # Update metadata
            self.update_meta(
                last_session_at=datetime.utcnow().isoformat() + "Z",
                last_session_id=session_id,
            )

            logger.info(
                "session_finalized",
                session_id=session_id,
                modules_explored=len(modules_explored),
                findings_count=len(key_findings),
            )

            return session_summary

        except Exception as e:
            logger.exception("finalize_session_failed", session_id=session_id, error=str(e))
            return None
