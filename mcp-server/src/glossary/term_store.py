"""Term storage and project glossary management."""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Optional

import structlog

from ..memory.project_memory import ProjectMemory

logger = structlog.get_logger(__name__)


@dataclass
class TermEntry:
    """A terminology mapping entry."""

    source_term: str
    target_phrase: str
    context: str = ""
    domain: str = "general"
    source: str = "default"  # "default" | "user_correction" | "inferred"
    confidence: float = 1.0  # 0-1, user corrections = 1.0
    usage_count: int = 0
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        """Initialize timestamps if not provided."""
        if not self.created_at:
            self.created_at = datetime.utcnow().isoformat() + "Z"
        if not self.updated_at:
            self.updated_at = datetime.utcnow().isoformat() + "Z"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TermEntry":
        """Create from dictionary."""
        return cls(**data)

    def increment_usage(self) -> None:
        """Increment usage count and update timestamp."""
        self.usage_count += 1
        self.updated_at = datetime.utcnow().isoformat() + "Z"


class ProjectGlossary:
    """Project-level glossary management, delegating to ProjectMemory."""

    def __init__(self, repo_url: str):
        """Initialize with repository URL.

        Args:
            repo_url: URL of the repository.
        """
        self.repo_url = repo_url
        self.memory = ProjectMemory(repo_url)
        self.terms: list[TermEntry] = []
        self.project_domain: Optional[str] = None
        self._load_from_storage()

    def _load_from_storage(self) -> None:
        """Load glossary from ProjectMemory storage."""
        try:
            glossary_data = self.memory.get_glossary()
            if not glossary_data:
                logger.debug("glossary_empty", repo_url=self.repo_url)
                self.terms = []
                return

            # Extract project domain if present
            self.project_domain = glossary_data.get("project_domain")

            # Load terms
            terms_data = glossary_data.get("terms", [])
            self.terms = [TermEntry.from_dict(t) for t in terms_data]
            logger.debug(
                "glossary_loaded",
                repo_url=self.repo_url,
                term_count=len(self.terms),
            )
        except Exception as e:
            logger.exception(
                "glossary_load_failed",
                repo_url=self.repo_url,
                error=str(e),
            )
            self.terms = []

    def _save_to_storage(self) -> bool:
        """Save glossary to ProjectMemory storage."""
        try:
            glossary_data = {
                "version": 1,
                "repo_url": self.repo_url,
                "project_domain": self.project_domain,
                "terms": [t.to_dict() for t in self.terms],
            }
            success = self.memory.store_glossary(glossary_data)
            if success:
                logger.debug(
                    "glossary_saved",
                    repo_url=self.repo_url,
                    term_count=len(self.terms),
                )
            return success
        except Exception as e:
            logger.exception(
                "glossary_save_failed",
                repo_url=self.repo_url,
                error=str(e),
            )
            return False

    def add_correction(
        self,
        source_term: str,
        target_phrase: str,
        context: str = "",
        domain: str = "general",
    ) -> bool:
        """Add a user correction as a high-confidence term.

        Args:
            source_term: The original term.
            target_phrase: The corrected translation.
            context: Usage context.
            domain: Domain classification.

        Returns:
            True if successful.
        """
        try:
            # Check if term already exists and update it
            for term in self.terms:
                if (
                    term.source_term == source_term
                    and term.source == "user_correction"
                ):
                    term.target_phrase = target_phrase
                    term.context = context
                    term.domain = domain
                    term.confidence = 1.0
                    term.updated_at = datetime.utcnow().isoformat() + "Z"
                    logger.debug(
                        "term_correction_updated",
                        source_term=source_term,
                        target_phrase=target_phrase,
                    )
                    return self._save_to_storage()

            # Add new correction
            entry = TermEntry(
                source_term=source_term,
                target_phrase=target_phrase,
                context=context,
                domain=domain,
                source="user_correction",
                confidence=1.0,
            )
            self.terms.append(entry)
            logger.debug(
                "term_correction_added",
                source_term=source_term,
                target_phrase=target_phrase,
            )
            return self._save_to_storage()
        except Exception as e:
            logger.exception(
                "add_correction_failed",
                source_term=source_term,
                error=str(e),
            )
            return False

    def get_all_terms(self) -> list[TermEntry]:
        """Get all terms in the glossary.

        Returns:
            List of TermEntry objects.
        """
        return self.terms.copy()

    def import_terms(
        self, terms: list[dict[str, Any]], domain: str = "general"
    ) -> int:
        """Bulk import terms from a domain pack.

        Args:
            terms: List of term dictionaries with source_term and target_phrase.
            domain: Domain classification for imported terms.

        Returns:
            Number of terms successfully imported.
        """
        imported_count = 0
        try:
            for term_data in terms:
                if "source_term" not in term_data or "target_phrase" not in term_data:
                    logger.warning(
                        "invalid_term_data",
                        term_data=term_data,
                    )
                    continue

                source_term = term_data["source_term"]
                target_phrase = term_data["target_phrase"]
                context = term_data.get("context", "")

                # Skip if user correction already exists for this term
                if any(
                    t.source_term == source_term and t.source == "user_correction"
                    for t in self.terms
                ):
                    logger.debug(
                        "term_skipped_user_correction_exists",
                        source_term=source_term,
                    )
                    continue

                # Check if term already exists (non-user correction)
                existing = None
                for term in self.terms:
                    if (
                        term.source_term == source_term
                        and term.source != "user_correction"
                    ):
                        existing = term
                        break

                if existing:
                    # Update existing term only if new source has higher priority
                    if domain != "general" or existing.domain == "general":
                        existing.target_phrase = target_phrase
                        existing.context = context
                        existing.domain = domain
                        existing.source = "domain_pack"
                        existing.updated_at = datetime.utcnow().isoformat() + "Z"
                else:
                    # Add new term
                    entry = TermEntry(
                        source_term=source_term,
                        target_phrase=target_phrase,
                        context=context,
                        domain=domain,
                        source="domain_pack",
                    )
                    self.terms.append(entry)

                imported_count += 1
                logger.debug(
                    "term_imported",
                    source_term=source_term,
                    domain=domain,
                )
        except Exception as e:
            logger.exception(
                "import_terms_failed",
                domain=domain,
                error=str(e),
            )

        if imported_count > 0:
            self._save_to_storage()

        logger.info(
            "terms_imported",
            domain=domain,
            count=imported_count,
        )
        return imported_count

    def set_project_domain(self, domain: str) -> bool:
        """Set the project domain classification.

        Args:
            domain: Domain name (e.g., "fintech", "healthcare").

        Returns:
            True if successful.
        """
        self.project_domain = domain
        return self._save_to_storage()

    def find_term(self, source_term: str) -> Optional[TermEntry]:
        """Find a term by source term.

        Args:
            source_term: The source term to search for.

        Returns:
            TermEntry if found, None otherwise.
        """
        for term in self.terms:
            if term.source_term == source_term:
                return term
        return None
