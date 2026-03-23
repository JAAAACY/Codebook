"""Term resolution with multi-layer priority merging."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
import json
import re

import structlog

from .term_store import TermEntry, ProjectGlossary

logger = structlog.get_logger(__name__)


class TermResolver:
    """Resolve terminology across multiple layers with priority merging."""

    def __init__(self, repo_url: str, project_domain: Optional[str] = None):
        """Initialize resolver.

        Args:
            repo_url: Repository URL.
            project_domain: Optional project domain for domain pack selection.
        """
        self.repo_url = repo_url
        self.project_domain = project_domain
        self.glossary = ProjectGlossary(repo_url)
        if project_domain:
            self.glossary.set_project_domain(project_domain)
        self.domain_packs: dict[str, list[TermEntry]] = {}
        self._load_domain_packs()

    def _load_domain_packs(self) -> None:
        """Load domain packs from default locations."""
        try:
            # Try to load from mcp-server/domain_packs/
            pack_dir = Path(__file__).parent.parent.parent / "domain_packs"

            if not pack_dir.exists():
                logger.debug("domain_packs_directory_not_found", path=str(pack_dir))
                return

            for pack_file in pack_dir.glob("*.json"):
                try:
                    with open(pack_file, "r", encoding="utf-8") as f:
                        pack_data = json.load(f)
                    domain = pack_data.get("domain", pack_file.stem)
                    terms_data = pack_data.get("terms", [])
                    self.domain_packs[domain] = [
                        TermEntry.from_dict(t) for t in terms_data
                    ]
                    logger.debug(
                        "domain_pack_loaded",
                        domain=domain,
                        term_count=len(self.domain_packs[domain]),
                    )
                except Exception as e:
                    logger.exception(
                        "domain_pack_load_failed",
                        path=str(pack_file),
                        error=str(e),
                    )
        except Exception as e:
            logger.exception("load_domain_packs_failed", error=str(e))

    def resolve(self) -> str:
        """Resolve all terms to a consolidated banned-terms text for prompt injection.

        Priority order (highest to lowest):
        1. User corrections (confidence=1.0, source=user_correction)
        2. Project glossary terms
        3. Project domain pack (if set)
        4. General domain pack
        5. Global defaults

        Returns:
            String with all terms in "source_term -> target_phrase" format.
        """
        try:
            merged_terms = self._merge_terms()

            # Format as text
            lines = []
            for term in merged_terms:
                lines.append(f"{term.source_term} -> {term.target_phrase}")

            result = "\n".join(lines)
            logger.debug(
                "resolve_complete",
                term_count=len(merged_terms),
            )
            return result
        except Exception as e:
            logger.exception("resolve_failed", error=str(e))
            return ""

    def resolve_as_list(self) -> list[TermEntry]:
        """Resolve all terms as a sorted list.

        Returns:
            List of TermEntry objects sorted by priority.
        """
        try:
            return self._merge_terms()
        except Exception as e:
            logger.exception("resolve_as_list_failed", error=str(e))
            return []

    def _merge_terms(self) -> list[TermEntry]:
        """Merge terms from all layers with priority handling.

        Returns:
            List of merged TermEntry objects, sorted by priority.
        """
        # Track seen source_terms to handle overrides
        seen: dict[str, TermEntry] = {}

        # Priority 1: User corrections (confidence=1.0)
        for term in self.glossary.get_all_terms():
            if term.source == "user_correction" and term.confidence == 1.0:
                seen[term.source_term] = term

        # Priority 2: Project glossary (non-correction terms)
        for term in self.glossary.get_all_terms():
            if term.source_term not in seen:
                seen[term.source_term] = term

        # Priority 3: Project domain pack
        if self.project_domain and self.project_domain in self.domain_packs:
            for term in self.domain_packs[self.project_domain]:
                if term.source_term not in seen:
                    seen[term.source_term] = term

        # Priority 4: General domain pack
        if "general" in self.domain_packs:
            for term in self.domain_packs["general"]:
                if term.source_term not in seen:
                    seen[term.source_term] = term

        # Sort by priority: user corrections first, then by confidence descending
        result = list(seen.values())
        result.sort(
            key=lambda t: (
                -(t.confidence),  # Higher confidence first
                t.source != "user_correction",  # User corrections first
            )
        )

        return result

    def track_usage(self, term: str) -> None:
        """Track that a term was used in output.

        Args:
            term: The source term that was used.
        """
        try:
            # Find and update term in glossary
            entry = self.glossary.find_term(term)
            if entry:
                entry.increment_usage()
                # Save back to storage
                self.glossary._save_to_storage()
                logger.debug("term_usage_tracked", source_term=term)
        except Exception as e:
            logger.exception("track_usage_failed", source_term=term, error=str(e))

    def get_statistics(self) -> dict[str, Any]:
        """Get statistics about loaded terms.

        Returns:
            Dictionary with term counts by source.
        """
        try:
            all_terms = self._merge_terms()
            stats = {
                "total_terms": len(all_terms),
                "user_corrections": sum(
                    1 for t in all_terms if t.source == "user_correction"
                ),
                "domain_pack_terms": sum(
                    1 for t in all_terms if t.source == "domain_pack"
                ),
                "inferred_terms": sum(
                    1 for t in all_terms if t.source == "inferred"
                ),
                "default_terms": sum(1 for t in all_terms if t.source == "default"),
                "domains_loaded": list(self.domain_packs.keys()),
            }
            logger.debug("statistics_generated", **stats)
            return stats
        except Exception as e:
            logger.exception("get_statistics_failed", error=str(e))
            return {"total_terms": 0}

    def infer_from_qa_history(self, qa_history: list[dict]) -> list[TermEntry]:
        """Infer business vocabulary ↔ code identifier associations from QA history.

        Extracts user business vocabulary from question/answer pairs and associates
        them with code concepts when mentioned together. Creates new TermEntry objects
        with source="inferred" and confidence=0.7.

        Args:
            qa_history: List of QA records, each with 'question' and 'answer_summary' fields.

        Returns:
            List of inferred TermEntry objects (confidence < 0.8 marked as "suggested").
        """
        inferred_terms: dict[str, TermEntry] = {}

        try:
            # Common technical identifier patterns (snake_case, camelCase, CONSTANT_CASE)
            identifier_pattern = re.compile(
                r'\b([a-z_][a-z0-9_]*|[a-z][a-zA-Z0-9]*|[A-Z][A-Z0-9_]*)\b'
            )

            for qa_entry in qa_history:
                if not isinstance(qa_entry, dict):
                    continue

                question = qa_entry.get("question", "")
                answer = qa_entry.get("answer_summary", "")

                if not question or not answer:
                    continue

                # Extract business terms from question (non-technical words)
                question_words = set(
                    word.lower() for word in question.split()
                    if len(word) > 3 and word.isalpha()
                )

                # Extract identifiers from answer
                answer_identifiers = set(
                    match.group(0) for match in identifier_pattern.finditer(answer)
                    if "_" in match.group(0) or match.group(0)[0].isupper()
                )

                # Build associations: business term → code identifier
                for term in question_words:
                    for identifier in answer_identifiers:
                        # Avoid generic terms
                        if term in {"how", "what", "when", "where", "why", "this", "that"}:
                            continue

                        # Create key combining both
                        key = f"{term}_{identifier}"

                        if key not in inferred_terms:
                            inferred_terms[key] = TermEntry(
                                source_term=identifier,
                                target_phrase=term,
                                context=f"Inferred from QA history",
                                domain=self.project_domain or "general",
                                source="inferred",
                                confidence=0.7,
                                usage_count=0,
                                created_at=self._get_iso_timestamp(),
                                updated_at=self._get_iso_timestamp(),
                            )
                        else:
                            # Increase confidence if we see the pattern again
                            inferred_terms[key].confidence = min(
                                0.79, inferred_terms[key].confidence + 0.05
                            )

            result = list(inferred_terms.values())
            logger.info(
                "infer_from_qa_history_complete",
                qa_history_count=len(qa_history),
                inferred_term_count=len(result),
            )
            return result

        except Exception as e:
            logger.exception("infer_from_qa_history_failed", error=str(e))
            return []

    @staticmethod
    def _get_iso_timestamp() -> str:
        """Get current timestamp in ISO format."""
        from datetime import datetime
        return datetime.utcnow().isoformat() + "Z"
