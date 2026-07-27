"""Cross-encoder reranker for final candidate ordering.

Reranks fused retrieval candidates using a cross-encoder model
to produce a final top-N set for the Generation Agent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from domain_models.core import ScoredChunk

logger = structlog.get_logger(__name__)


class Reranker:
    """Cross-encoder reranker for final candidate ordering.

    Supports a "fake" mode where it simply returns the top N candidates
    sorted by their existing score (no model needed). This allows unit tests
    to run without downloading cross-encoder models.
    """

    def __init__(
        self,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L-12-v2",
        fake: bool = False,
    ) -> None:
        self._model_name = model_name
        self._fake = fake
        self._model = None  # Lazy load
        self._load_failed = False

    def _load_model(self) -> bool:
        """Lazy-load the cross-encoder model on first use.

        Returns:
            True if model loaded successfully, False if loading failed.
        """
        if self._model is not None:
            return True
        if self._fake:
            return True
        try:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self._model_name)
            logger.info("reranker.model_loaded", model=self._model_name)
            return True
        except Exception as e:
            logger.error("reranker.model_load_failed", model=self._model_name, error=str(e))
            self._load_failed = True
            return False

    async def rerank(
        self, query: str, candidates: list[ScoredChunk], top_n: int = 5
    ) -> list[ScoredChunk]:
        """Rerank candidates using cross-encoder scoring.

        Args:
            query: The user's natural language query.
            candidates: Fused candidate chunks to rerank (up to 20).
            top_n: Number of top results to return (default 5).

        Returns:
            Top min(top_n, len(candidates)) chunks sorted by reranker score.
            Returns empty list if candidates is empty.
        """
        if not candidates:
            return []

        if self._fake:
            return self._fake_rerank(candidates, top_n)

        # If model loading fails, fall back to returning candidates in original order
        if not self._load_model():
            logger.warning(
                "reranker.fallback_to_original_order",
                reason="model_load_failed",
                candidate_count=len(candidates),
            )
            result_count = min(top_n, len(candidates))
            return candidates[:result_count]

        return self._model_rerank(query, candidates, top_n)

    def _fake_rerank(self, candidates: list[ScoredChunk], top_n: int) -> list[ScoredChunk]:
        """Fake reranking: sort by existing score descending, return top N."""
        sorted_candidates = sorted(candidates, key=lambda c: c.score, reverse=True)
        result_count = min(top_n, len(sorted_candidates))
        return sorted_candidates[:result_count]

    def _model_rerank(
        self, query: str, candidates: list[ScoredChunk], top_n: int
    ) -> list[ScoredChunk]:
        """Real cross-encoder reranking using sentence-transformers."""
        from domain_models.core import ScoredChunk as ScoredChunkModel

        # Build (query, passage) pairs for the cross-encoder
        pairs = [(query, candidate.text) for candidate in candidates]

        # Score all pairs
        scores = self._model.predict(pairs)

        # Pair scores with candidates and sort descending
        scored_pairs = list(zip(scores, candidates))
        scored_pairs.sort(key=lambda x: x[0], reverse=True)

        # Return top_n with normalized scores
        result_count = min(top_n, len(scored_pairs))
        results = []
        for score, candidate in scored_pairs[:result_count]:
            # Normalize cross-encoder score to [0, 1] using sigmoid-like clamping
            normalized_score = min(1.0, max(0.0, float(score)))
            results.append(
                ScoredChunkModel(
                    chunk_id=candidate.chunk_id,
                    document_id=candidate.document_id,
                    text=candidate.text,
                    section_heading=candidate.section_heading,
                    score=normalized_score,
                    retrieval_method=candidate.retrieval_method,
                    metadata=candidate.metadata,
                )
            )

        logger.info(
            "reranker.complete",
            input_count=len(candidates),
            output_count=len(results),
        )
        return results
