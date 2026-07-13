"""Cross-Encoder Reranker adapter for RerankerPort.

Uses a sentence-transformers cross-encoder model to rerank retrieval
candidates by scoring query-passage pairs. Runs locally on CPU —
no API calls needed.

Model: cross-encoder/ms-marco-MiniLM-L-12-v2 (default)
Latency: ~10-50ms for 20 candidates on CPU
"""

from __future__ import annotations

import time
from typing import Any

import structlog

from src.domain.models.entities import ScoredChunk
from src.ports.reranker import RerankerPort  # noqa: F401 — documents which port this implements

logger = structlog.get_logger(__name__)

DEFAULT_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-12-v2"


class RerankerError(Exception):
    """Raised when reranking operations fail."""

    def __init__(self, message: str, operation: str = "") -> None:
        self.operation = operation
        super().__init__(message)


class CrossEncoderRerankerAdapter:
    """Cross-encoder reranker implementing RerankerPort.

    Loads a cross-encoder model from sentence-transformers and scores
    query-passage pairs for relevance. Returns candidates reordered
    by cross-encoder score (descending).

    The model is loaded lazily on first use to avoid slow import
    at application startup.

    Usage:
        reranker = CrossEncoderRerankerAdapter()
        reranked = await reranker.rerank("what is docker?", candidates, top_n=5)
    """

    def __init__(self, model_name: str = DEFAULT_MODEL_NAME) -> None:
        """Initialize the cross-encoder reranker.

        Args:
            model_name: Hugging Face model identifier for the cross-encoder.
                Default: cross-encoder/ms-marco-MiniLM-L-12-v2
        """
        self._model_name = model_name
        self._model: Any = None  # Lazy-loaded CrossEncoder instance

        logger.info(
            "cross_encoder_reranker.initialized",
            model_name=model_name,
            loaded=False,
        )

    def _load_model(self) -> None:
        """Lazy-load the cross-encoder model on first use."""
        if self._model is not None:
            return

        start_time = time.perf_counter()

        from sentence_transformers import CrossEncoder

        self._model = CrossEncoder(self._model_name)

        duration_ms = (time.perf_counter() - start_time) * 1000

        logger.info(
            "cross_encoder_reranker.model_loaded",
            model_name=self._model_name,
            duration_ms=round(duration_ms, 2),
        )

    async def rerank(
        self, query: str, candidates: list[ScoredChunk], top_n: int
    ) -> list[ScoredChunk]:
        """Rerank candidates using cross-encoder query-passage scoring.

        Scores each (query, chunk.text) pair and returns the top_n
        candidates sorted by cross-encoder score descending.

        Args:
            query: The search query text.
            candidates: List of ScoredChunk candidates to rerank.
            top_n: Number of top results to return.

        Returns:
            List of top_n ScoredChunk objects reranked by cross-encoder score.

        Raises:
            RerankerError: If reranking fails.
        """
        if not candidates:
            return []

        if not query or not query.strip():
            return candidates[:top_n]

        start_time = time.perf_counter()

        try:
            self._load_model()

            # Build query-passage pairs
            pairs = [(query, candidate.chunk.text) for candidate in candidates]

            # Score all pairs
            scores = self._model.predict(pairs)

            # Pair candidates with new scores
            scored_candidates = list(zip(candidates, scores, strict=True))

            # Sort by cross-encoder score descending
            scored_candidates.sort(key=lambda x: float(x[1]), reverse=True)

            # Take top_n and build new ScoredChunks with updated scores
            reranked: list[ScoredChunk] = []
            for candidate, ce_score in scored_candidates[:top_n]:
                reranked.append(
                    ScoredChunk(
                        chunk=candidate.chunk,
                        score=float(ce_score),
                        retrieval_method="reranked",
                    )
                )

            duration_ms = (time.perf_counter() - start_time) * 1000

            logger.info(
                "cross_encoder_reranker.rerank.success",
                query_length=len(query),
                candidates_count=len(candidates),
                top_n=top_n,
                results_count=len(reranked),
                top_score=round(float(reranked[0].score), 4) if reranked else 0.0,
                duration_ms=round(duration_ms, 2),
            )

            return reranked

        except Exception as e:
            logger.error(
                "cross_encoder_reranker.rerank.failed",
                error=str(e),
                query_length=len(query),
                candidates_count=len(candidates),
            )
            raise RerankerError(
                f"Failed to rerank candidates: {e}",
                operation="rerank",
            ) from e

    @property
    def model_name(self) -> str:
        """Return the model name."""
        return self._model_name

    @property
    def is_loaded(self) -> bool:
        """Return whether the model has been loaded."""
        return self._model is not None
