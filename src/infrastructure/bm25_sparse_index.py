"""BM25 Sparse Index adapter for SparseIndexPort.

In-memory BM25 keyword index using the rank_bm25 library.
Provides lexical/keyword search complementing dense vector search
for hybrid retrieval via Reciprocal Rank Fusion.

This is an in-memory implementation suitable for development and
moderate-scale production. For larger corpora, consider Elasticsearch
or OpenSearch behind the same port interface.
"""

from __future__ import annotations

import re
import time

import structlog
from rank_bm25 import BM25Okapi

from src.domain.models.entities import Chunk, ScoredChunk
from src.ports.sparse_index import (
    SparseIndexPort,  # noqa: F401 — documents which port this implements
)

logger = structlog.get_logger(__name__)


class SparseIndexError(Exception):
    """Raised when sparse index operations fail."""

    def __init__(self, message: str, operation: str = "") -> None:
        self.operation = operation
        super().__init__(message)


def _tokenize(text: str) -> list[str]:
    """Simple whitespace tokenizer with lowercasing and punctuation stripping.

    Splits on word boundaries, lowercases, and keeps tokens of length >= 2.
    Suitable for English text BM25 indexing.

    Args:
        text: Input text to tokenize.

    Returns:
        List of lowercase tokens.
    """
    tokens = re.findall(r"\b[a-z0-9]+\b", text.lower())
    return [t for t in tokens if len(t) > 1]


class BM25SparseIndexAdapter:
    """In-memory BM25 sparse index implementing SparseIndexPort.

    Maintains a BM25Okapi index over indexed chunks. Supports
    incremental indexing, keyword search, and document-level deletion.

    The index is rebuilt after deletions to maintain BM25 statistics
    accuracy (IDF values depend on corpus composition).

    Usage:
        adapter = BM25SparseIndexAdapter()
        await adapter.index(chunks)
        results = await adapter.search("deployment process", top_k=5)
        await adapter.delete_by_document("doc-uuid")
    """

    def __init__(self) -> None:
        """Initialize an empty BM25 sparse index."""
        self._chunks: list[Chunk] = []
        self._tokenized_corpus: list[list[str]] = []
        self._bm25: BM25Okapi | None = None

        logger.info("bm25_sparse_index.initialized", chunk_count=0)

    async def index(self, chunks: list[Chunk]) -> None:
        """Add chunks to the BM25 index.

        Tokenizes chunk text and rebuilds the BM25 model with
        the updated corpus. Handles duplicate chunk IDs by
        replacing existing entries.

        Args:
            chunks: List of Chunk objects to index.

        Raises:
            SparseIndexError: If indexing fails.
        """
        if not chunks:
            return

        start_time = time.perf_counter()

        try:
            # Remove any existing chunks with same IDs (for re-indexing)
            existing_ids = {str(c.id) for c in chunks}
            self._chunks = [c for c in self._chunks if str(c.id) not in existing_ids]
            self._tokenized_corpus = [_tokenize(c.text) for c in self._chunks]

            # Add new chunks
            for chunk in chunks:
                tokens = _tokenize(chunk.text)
                self._chunks.append(chunk)
                self._tokenized_corpus.append(tokens)

            # Rebuild BM25 model
            self._rebuild_index()

            duration_ms = (time.perf_counter() - start_time) * 1000

            logger.info(
                "bm25_sparse_index.index.success",
                new_chunks=len(chunks),
                total_chunks=len(self._chunks),
                duration_ms=round(duration_ms, 2),
            )

        except Exception as e:
            logger.error(
                "bm25_sparse_index.index.failed",
                error=str(e),
                chunks_count=len(chunks),
            )
            raise SparseIndexError(
                f"Failed to index chunks: {e}",
                operation="index",
            ) from e

    async def search(self, query: str, top_k: int) -> list[ScoredChunk]:
        """Search the BM25 index with a keyword query.

        Tokenizes the query and scores all indexed chunks using BM25Okapi.
        Returns the top-k results sorted by descending BM25 score,
        normalized to [0, 1] range.

        Args:
            query: The search query text.
            top_k: Maximum number of results to return.

        Returns:
            List of ScoredChunk objects sorted by BM25 relevance.

        Raises:
            SparseIndexError: If search fails.
        """
        start_time = time.perf_counter()

        try:
            if not self._bm25 or not self._chunks:
                return []

            query_tokens = _tokenize(query)
            if not query_tokens:
                return []

            # Get BM25 scores for all documents
            scores = self._bm25.get_scores(query_tokens)

            # Pair chunks with scores, filter zeros, sort descending
            scored_pairs = [
                (self._chunks[i], float(scores[i]))
                for i in range(len(self._chunks))
                if scores[i] > 0
            ]
            scored_pairs.sort(key=lambda x: x[1], reverse=True)

            # Take top_k
            top_results = scored_pairs[:top_k]

            # Normalize scores to [0, 1]
            if top_results:
                max_score = top_results[0][1]
                normalized = [
                    (chunk, score / max_score if max_score > 0 else 0.0)
                    for chunk, score in top_results
                ]
            else:
                normalized = []

            # Convert to ScoredChunk objects
            results = [
                ScoredChunk(
                    chunk=chunk,
                    score=score,
                    retrieval_method="sparse",
                )
                for chunk, score in normalized
            ]

            duration_ms = (time.perf_counter() - start_time) * 1000

            logger.info(
                "bm25_sparse_index.search.success",
                query_tokens=len(query_tokens),
                candidates=len(scored_pairs),
                results_count=len(results),
                top_k=top_k,
                duration_ms=round(duration_ms, 2),
            )

            return results

        except Exception as e:
            logger.error(
                "bm25_sparse_index.search.failed",
                error=str(e),
                query=query[:100],
            )
            raise SparseIndexError(
                f"Failed to search index: {e}",
                operation="search",
            ) from e

    async def delete_by_document(self, document_id: str) -> None:
        """Delete all chunks belonging to a document from the index.

        Removes chunks and rebuilds the BM25 model to maintain
        accurate IDF statistics.

        Args:
            document_id: The document UUID string whose chunks to remove.

        Raises:
            SparseIndexError: If deletion fails.
        """
        start_time = time.perf_counter()

        try:
            original_count = len(self._chunks)

            self._chunks = [
                c for c in self._chunks if str(c.document_id) != document_id
            ]

            removed_count = original_count - len(self._chunks)

            # Rebuild tokenized corpus and BM25 model
            self._tokenized_corpus = [_tokenize(c.text) for c in self._chunks]
            self._rebuild_index()

            duration_ms = (time.perf_counter() - start_time) * 1000

            logger.info(
                "bm25_sparse_index.delete_by_document.success",
                document_id=document_id,
                removed_count=removed_count,
                remaining_count=len(self._chunks),
                duration_ms=round(duration_ms, 2),
            )

        except Exception as e:
            logger.error(
                "bm25_sparse_index.delete_by_document.failed",
                error=str(e),
                document_id=document_id,
            )
            raise SparseIndexError(
                f"Failed to delete document from index: {e}",
                operation="delete_by_document",
            ) from e

    def _rebuild_index(self) -> None:
        """Rebuild the BM25 model from the current tokenized corpus."""
        if self._tokenized_corpus:
            self._bm25 = BM25Okapi(self._tokenized_corpus)
        else:
            self._bm25 = None

    @property
    def count(self) -> int:
        """Return the number of indexed chunks."""
        return len(self._chunks)
