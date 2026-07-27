"""Chunker Registry with auto-selection based on document format.

Wraps the factory pattern with format-based auto-selection logic,
fallback behavior, and availability tracking for chunking strategies.
"""

from __future__ import annotations

import os
import re
from typing import Any, Protocol

import structlog

logger = structlog.get_logger(__name__)

# Legislative keywords for auto-selection (case-insensitive)
# Uses lookahead/lookbehind for non-alphanumeric boundaries (treats _ as separator)
# Includes keywords from requirement 6.2 (Act, Regulation, Rule, Policy)
# and task-specified keywords (Section, Part, Division, Schedule)
_LEGISLATIVE_KEYWORDS = re.compile(
    r"(?<![a-zA-Z])(act|regulation|rule|policy|section|part|division|schedule)(?![a-zA-Z])",
    re.IGNORECASE,
)


class Chunker(Protocol):
    """Protocol for strategy-specific document chunkers."""

    def chunk(self, document: Any) -> list[Any]: ...


class ChunkerRegistry:
    """Registry with auto-selection based on document format.

    Registers chunking strategies with availability status and provides
    auto-selection based on file extension and legislative keywords,
    explicit selection by name, and fallback to fixed_size when the
    selected strategy is unavailable.
    """

    def __init__(self) -> None:
        self._chunkers: dict[str, Chunker] = {}
        self._availability: dict[str, bool] = {}

    def register(
        self, strategy_name: str, chunker: Chunker, available: bool = True
    ) -> None:
        """Register a chunker with availability status.

        Args:
            strategy_name: The name of the strategy (e.g., "fixed_size").
            chunker: The chunker implementation.
            available: Whether the strategy is currently available.
        """
        self._chunkers[strategy_name] = chunker
        self._availability[strategy_name] = available

    def auto_select(
        self,
        filename: str,
        metadata: dict[str, Any] | None = None,
        content_preview: str | None = None,
    ) -> Chunker:
        """Auto-select a chunker based on file extension and keywords.

        Selection rules:
        - .pdf/.md with legislative keywords → legal_hierarchical
        - .pdf/.md without keywords → recursive
        - .html → recursive
        - .txt → fixed_size
        - Other/unknown → fixed_size

        If the selected strategy is unavailable, falls back to fixed_size
        with a warning log.

        Args:
            filename: The document filename (used for extension and keyword detection).
            metadata: Optional metadata dict (checked for legislative keywords).
            content_preview: Optional content preview string (checked for legislative keywords).

        Returns:
            The selected Chunker instance.

        Raises:
            ValueError: If fixed_size fallback is also not registered.
        """
        strategy_name = self._determine_strategy(filename, metadata, content_preview)
        return self._resolve_chunker(strategy_name)

    def get_by_name(self, strategy_name: str) -> Chunker:
        """Explicitly select a chunker by registered name.

        Args:
            strategy_name: The name of a registered strategy.

        Returns:
            The Chunker instance for the given name.

        Raises:
            ValueError: If the strategy name is not registered.
        """
        if strategy_name not in self._chunkers:
            registered = list(self._chunkers.keys())
            raise ValueError(
                f"Strategy '{strategy_name}' is not recognized. "
                f"Registered strategies: {registered}"
            )
        return self._chunkers[strategy_name]

    @property
    def registered_strategies(self) -> list[dict[str, Any]]:
        """Return list of registered strategies with availability status.

        Returns:
            List of dicts with 'name' and 'available' keys.
        """
        return [
            {"name": name, "available": self._availability[name]}
            for name in self._chunkers
        ]

    def _determine_strategy(
        self,
        filename: str,
        metadata: dict[str, Any] | None,
        content_preview: str | None = None,
    ) -> str:
        """Determine the strategy name based on extension and keywords."""
        _, ext = os.path.splitext(filename)
        ext = ext.lower()

        if ext in (".pdf", ".md"):
            if self._has_legislative_keywords(filename, metadata, content_preview):
                return "legal_hierarchical"
            return "recursive"

        if ext == ".html":
            return "recursive"

        if ext == ".txt":
            return "fixed_size"

        # Unknown extension → fixed_size
        return "fixed_size"

    def _has_legislative_keywords(
        self,
        filename: str,
        metadata: dict[str, Any] | None,
        content_preview: str | None = None,
    ) -> bool:
        """Check if filename, metadata, or content preview contains legislative keywords."""
        if _LEGISLATIVE_KEYWORDS.search(filename):
            return True

        if metadata:
            # Check all string values in metadata for keywords
            for value in metadata.values():
                if isinstance(value, str) and _LEGISLATIVE_KEYWORDS.search(value):
                    return True

        if content_preview and _LEGISLATIVE_KEYWORDS.search(content_preview):
            return True

        return False

    def _resolve_chunker(self, strategy_name: str) -> Chunker:
        """Resolve a chunker, falling back to fixed_size if unavailable."""
        if strategy_name in self._chunkers and self._availability.get(
            strategy_name, False
        ):
            return self._chunkers[strategy_name]

        # Strategy unavailable — fall back to fixed_size
        if strategy_name != "fixed_size":
            logger.warning(
                "chunker_strategy_unavailable",
                selected_strategy=strategy_name,
                reason="strategy unavailable or not initialized",
                fallback="fixed_size",
            )

        if "fixed_size" not in self._chunkers:
            raise ValueError(
                f"Cannot fall back to fixed_size: it is not registered. "
                f"Original strategy '{strategy_name}' is also unavailable."
            )

        return self._chunkers["fixed_size"]
