"""
Data models for the three-layer memory system.

Structures:
- DiagnosisRecord: A single diagnosis result record
- QARecord: A Q&A interaction record
- AnnotationRecord: User annotation/comment
- ModuleUnderstanding: Cumulative understanding of a module
- Hotspot: Frequently asked region in codebase
- SessionSummary: Summary of a work session
- InteractionMemory: Cross-session interaction patterns
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DiagnosisRecord:
    """A single diagnosis result record."""
    query: str
    diagnosis_summary: str
    matched_locations: list[str]
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "query": self.query,
            "diagnosis_summary": self.diagnosis_summary,
            "matched_locations": self.matched_locations,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DiagnosisRecord":
        """Construct from dictionary."""
        return cls(
            query=data.get("query", ""),
            diagnosis_summary=data.get("diagnosis_summary", ""),
            matched_locations=data.get("matched_locations", []),
            timestamp=data.get("timestamp", ""),
        )


@dataclass
class QARecord:
    """A Q&A interaction record."""
    question: str
    answer_summary: str
    confidence: float = 0.0
    follow_ups_used: list[str] = field(default_factory=list)
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "question": self.question,
            "answer_summary": self.answer_summary,
            "confidence": self.confidence,
            "follow_ups_used": self.follow_ups_used,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QARecord":
        """Construct from dictionary."""
        return cls(
            question=data.get("question", ""),
            answer_summary=data.get("answer_summary", ""),
            confidence=float(data.get("confidence", 0.0)),
            follow_ups_used=data.get("follow_ups_used", []),
            timestamp=data.get("timestamp", ""),
        )


@dataclass
class AnnotationRecord:
    """User annotation/comment on code."""
    content: str
    author: str
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "content": self.content,
            "author": self.author,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AnnotationRecord":
        """Construct from dictionary."""
        return cls(
            content=data.get("content", ""),
            author=data.get("author", ""),
            timestamp=data.get("timestamp", ""),
        )


@dataclass
class ModuleUnderstanding:
    """Cumulative understanding of a single module."""
    module_name: str
    diagnoses: list[DiagnosisRecord] = field(default_factory=list)
    qa_history: list[QARecord] = field(default_factory=list)
    annotations: list[AnnotationRecord] = field(default_factory=list)
    view_count: int = 0
    diagnose_count: int = 0
    ask_count: int = 0
    last_accessed: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "module_name": self.module_name,
            "diagnoses": [d.to_dict() for d in self.diagnoses],
            "qa_history": [q.to_dict() for q in self.qa_history],
            "annotations": [a.to_dict() for a in self.annotations],
            "view_count": self.view_count,
            "diagnose_count": self.diagnose_count,
            "ask_count": self.ask_count,
            "last_accessed": self.last_accessed,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModuleUnderstanding":
        """Construct from dictionary."""
        return cls(
            module_name=data.get("module_name", ""),
            diagnoses=[DiagnosisRecord.from_dict(d) for d in data.get("diagnoses", [])],
            qa_history=[QARecord.from_dict(q) for q in data.get("qa_history", [])],
            annotations=[AnnotationRecord.from_dict(a) for a in data.get("annotations", [])],
            view_count=int(data.get("view_count", 0)),
            diagnose_count=int(data.get("diagnose_count", 0)),
            ask_count=int(data.get("ask_count", 0)),
            last_accessed=data.get("last_accessed", ""),
        )


@dataclass
class Hotspot:
    """A frequently asked region (knowledge hotspot)."""
    module_name: str
    topic: str
    question_count: int = 0
    typical_questions: list[str] = field(default_factory=list)
    suggested_doc: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "module_name": self.module_name,
            "topic": self.topic,
            "question_count": self.question_count,
            "typical_questions": self.typical_questions,
            "suggested_doc": self.suggested_doc,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Hotspot":
        """Construct from dictionary."""
        return cls(
            module_name=data.get("module_name", ""),
            topic=data.get("topic", ""),
            question_count=int(data.get("question_count", 0)),
            typical_questions=data.get("typical_questions", []),
            suggested_doc=data.get("suggested_doc", ""),
        )


@dataclass
class SessionSummary:
    """Summary of a single work session."""
    session_id: str
    timestamp: str
    modules_explored: list[str] = field(default_factory=list)
    key_findings: list[str] = field(default_factory=list)
    unresolved_questions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "modules_explored": self.modules_explored,
            "key_findings": self.key_findings,
            "unresolved_questions": self.unresolved_questions,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionSummary":
        """Construct from dictionary."""
        return cls(
            session_id=data.get("session_id", ""),
            timestamp=data.get("timestamp", ""),
            modules_explored=data.get("modules_explored", []),
            key_findings=data.get("key_findings", []),
            unresolved_questions=data.get("unresolved_questions", []),
        )


@dataclass
class InteractionMemory:
    """Cross-session interaction patterns and hotspots."""
    hotspots: list[Hotspot] = field(default_factory=list)
    focus_profile: dict[str, int] = field(default_factory=dict)
    session_summaries: list[SessionSummary] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "hotspots": [h.to_dict() for h in self.hotspots],
            "focus_profile": self.focus_profile,
            "session_summaries": [s.to_dict() for s in self.session_summaries],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "InteractionMemory":
        """Construct from dictionary."""
        return cls(
            hotspots=[Hotspot.from_dict(h) for h in data.get("hotspots", [])],
            focus_profile=data.get("focus_profile", {}),
            session_summaries=[SessionSummary.from_dict(s) for s in data.get("session_summaries", [])],
        )
