"""Glossary system: terminology storage and resolution."""

from .term_store import TermEntry, ProjectGlossary
from .term_resolver import TermResolver

__all__ = ["TermEntry", "ProjectGlossary", "TermResolver"]
