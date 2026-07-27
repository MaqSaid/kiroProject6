"""BM25 in-memory sparse index for keyword search.

Uses rank_bm25.BM25Okapi to provide lexical/keyword search
complementing dense vector search for hybrid retrieval via
Reciprocal Rank Fusion.

Requirements: 10.1 (sparse search component of hybrid retrieval)
"""

from __future__ import annotations

import re
import time

import structlog
from rank_bm25 import BM25Okapi

logger = structlog.get_logger(__name__)


class BM25IndexError(Exception):
    """Raised when BM25 index operations fail."""

    def __init__(self, message: str, operation: str = "") -> None:
        self.operation = operation
        super().__init__(message)


def _tokenize(text: str) -> list[str]:
    """Simple whitespace tokenizer with lowercasing and punctuation stripping.

    Splits on word boundaries, lowercases, and keeps tokens of length >= 2.
    Suitable for English legal text BM25 indexing.

    Args:
        text: Input text to tokenize.

    Returns:
        List of lowercase tokens.
    """
    tokens = re.findall(r"\b[a-z0-9]+\b", text.lower())
    return [t for t in tokens if len(t) > 1]


class BM25Index:
    """In-memory BM25 sparse search index.

    Maintains a BM25Okapi index over indexed chunks. Supports
    incremental indexing, keyword search, and document-level deletion.
    The index is rebuilt after deletions to maintain BM25 statistics
    accuracy (IDF values depend on corpus composition).
    """

    def __init__(self) -> None:
        """Initialize an empty BM25 sparse index."""
        self._documents: list[dict] = []
        self._tokenized_corpus: list[list[str]] = []
        self._bm25: BM25Okapi | None = None
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the BM25 index.

        Sets up the index for accepting documents and queries.
        """
        logger.info("bm25.initialize")
        self._initialized = True
        logger.info("bm25.initialized", document_count=len(self._documents))

    @property
    def is_initialized(self) -> bool:
        """Check if index is ready."""
        return self._initialized

    @property
    def count(self) -> int:
        """Return the number of indexed documents."""
        return len(self._documents)

    async def index_documents(self, documents: list[dict]) -> None:
        """Add documents to the BM25 index.

        Tokenizes document text and rebuilds the BM25 model with
        the updated corpus. Handles duplicate chunk IDs by replacing
        existing entries.

        Args:
            documents: List of dicts with at minimum 'chunk_id' and 'text' keys.
                       May also include 'document_id', 'section_heading', 'metadata'.

        Raises:
            BM25IndexError: If indexing fails.
        """
        if not documents:
            return

        start_time = time.perf_counter()

        try:
            # Remove any existing documents with same IDs (for re-indexing)
            existing_ids = {doc.get("chunk_id", "") for doc in documents}
            self._documents = [
                d for d in self._documents if d.get("chunk_id", "") not in existing_ids
            ]
            self._tokenized_corpus = [
                _tokenize(d.get("text", "")) for d in self._documents
            ]

            # Add new documents
            for doc in documents:
                tokens = _tokenize(doc.get("text", ""))
                self._documents.append(doc)
                self._tokenized_corpus.append(tokens)

            # Rebuild BM25 model
            self._rebuild_index()

            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.info(
                "bm25.index_documents.success",
                new_documents=len(documents),
                total_documents=len(self._documents),
                duration_ms=round(duration_ms, 2),
            )
        except Exception as e:
            logger.error(
                "bm25.index_documents.failed",
                error=str(e),
                count=len(documents),
            )
            raise BM25IndexError(
                f"Failed to index documents: {e}", operation="index_documents"
            ) from e

    async def search(self, query: str, top_k: int = 20) -> list[dict]:
        """Search the BM25 index for keyword matches.

        Tokenizes the query and scores all indexed documents using BM25Okapi.
        Returns the top-k results sorted by descending BM25 score,
        normalized to [0, 1] range.

        Args:
            query: Query text for keyword matching.
            top_k: Number of results to return.

        Returns:
            List of dicts with chunk_id, document_id, text, section_heading,
            score, and metadata fields sorted by BM25 relevance.

        Raises:
            BM25IndexError: If search fails.
        """
        start_time = time.perf_counter()

        try:
            if not self._bm25 or not self._documents:
                return []

            query_tokens = _tokenize(query)
            if not query_tokens:
                return []

            # Get BM25 scores for all documents
            scores = self._bm25.get_scores(query_tokens)

            # Pair documents with scores, filter zeros, sort descending
            scored_pairs = [
                (self._documents[i], float(scores[i]))
                for i in range(len(self._documents))
                if scores[i] > 0
            ]
            scored_pairs.sort(key=lambda x: x[1], reverse=True)

            # Take top_k
            top_results = scored_pairs[:top_k]

            # Normalize scores to [0, 1]
            if top_results:
                max_score = top_results[0][1]
                normalized = [
                    (doc, score / max_score if max_score > 0 else 0.0)
                    for doc, score in top_results
                ]
            else:
                normalized = []

            # Build result dicts
            results: list[dict] = []
            for doc, score in normalized:
                results.append({
                    "chunk_id": doc.get("chunk_id", ""),
                    "document_id": doc.get("document_id", ""),
                    "text": doc.get("text", ""),
                    "section_heading": doc.get("section_heading", ""),
                    "score": score,
                    "metadata": doc.get("metadata", {}),
                })

            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.info(
                "bm25.search.success",
                query_tokens=len(query_tokens),
                candidates=len(scored_pairs),
                results_count=len(results),
                top_k=top_k,
                duration_ms=round(duration_ms, 2),
            )
            return results

        except Exception as e:
            logger.error(
                "bm25.search.failed",
                error=str(e),
                query=query[:100],
            )
            raise BM25IndexError(
                f"Failed to search index: {e}", operation="search"
            ) from e

    async def delete_by_document(self, document_id: str) -> None:
        """Delete all chunks belonging to a document from the index.

        Removes documents and rebuilds the BM25 model to maintain
        accurate IDF statistics.

        Args:
            document_id: The document ID whose chunks to remove.

        Raises:
            BM25IndexError: If deletion fails.
        """
        start_time = time.perf_counter()

        try:
            original_count = len(self._documents)
            self._documents = [
                d for d in self._documents
                if d.get("document_id", "") != document_id
            ]
            removed_count = original_count - len(self._documents)

            # Rebuild tokenized corpus and BM25 model
            self._tokenized_corpus = [
                _tokenize(d.get("text", "")) for d in self._documents
            ]
            self._rebuild_index()

            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.info(
                "bm25.delete_by_document.success",
                document_id=document_id,
                removed_count=removed_count,
                remaining_count=len(self._documents),
                duration_ms=round(duration_ms, 2),
            )
        except Exception as e:
            logger.error(
                "bm25.delete_by_document.failed",
                error=str(e),
                document_id=document_id,
            )
            raise BM25IndexError(
                f"Failed to delete document from index: {e}",
                operation="delete_by_document",
            ) from e

    def _rebuild_index(self) -> None:
        """Rebuild the BM25 model from the current tokenized corpus."""
        if self._tokenized_corpus:
            self._bm25 = BM25Okapi(self._tokenized_corpus)
        else:
            self._bm25 = None
