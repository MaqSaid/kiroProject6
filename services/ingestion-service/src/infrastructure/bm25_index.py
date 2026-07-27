"""BM25 in-memory sparse index for the Ingestion Service.

Provides keyword-based sparse retrieval using rank-bm25.
"""

from __future__ import annotations

import re

import structlog

logger = structlog.get_logger(__name__)


class BM25Index:
    """In-memory BM25 sparse index for document chunks."""

    def __init__(self) -> None:
        self._corpus: list[list[str]] = []
        self._chunk_ids: list[str] = []
        self._index: object | None = None

    @property
    def is_initialized(self) -> bool:
        """Always True — in-memory index is available immediately."""
        return True

    @property
    def document_count(self) -> int:
        """Return the number of indexed documents."""
        return len(self._chunk_ids)

    def add_documents(self, chunk_ids: list[str], texts: list[str]) -> None:
        """Add tokenized documents to the BM25 index.

        Args:
            chunk_ids: Unique IDs for each chunk.
            texts: Raw text content to tokenize and index.
        """
        from rank_bm25 import BM25Okapi

        for chunk_id, text in zip(chunk_ids, texts):
            tokens = self._tokenize(text)
            self._corpus.append(tokens)
            self._chunk_ids.append(chunk_id)

        # Rebuild index with full corpus
        self._index = BM25Okapi(self._corpus)
        logger.info("bm25_documents_added", count=len(chunk_ids), total=len(self._chunk_ids))

    def _tokenize(self, text: str) -> list[str]:
        """Simple whitespace + punctuation tokenizer."""
        text = text.lower()
        tokens = re.findall(r"\b\w+\b", text)
        return tokens
