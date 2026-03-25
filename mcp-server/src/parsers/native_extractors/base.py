"""Abstract base class for native AST extractors."""

from abc import ABC, abstractmethod

from src.parsers.ast_parser import ParseResult


class BaseNativeExtractor(ABC):
    """Base class for language-specific native AST extractors.

    Subclasses must set ``language`` and implement ``extract_all``.
    """

    language: str = ""
    confidence: float = 0.99
    parse_method: str = "native"

    @abstractmethod
    def extract_all(self, source: str, file_path: str) -> ParseResult:
        """Parse *source* and return a fully-populated ``ParseResult``.

        Raises:
            SyntaxError: If the source code cannot be parsed.
        """
        ...
