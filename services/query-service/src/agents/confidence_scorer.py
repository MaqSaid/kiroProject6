"""Confidence scoring for the agent pipeline output.

Computes composite confidence scores from retrieval quality,
citation coverage, and answer completeness sub-scores.
"""

from __future__ import annotations

import structlog

from domain_models.api_models import CitationResponse, ConfidenceScoreResponse
from domain_models.core import ScoredChunk

logger = structlog.get_logger(__name__)


class ConfidenceScorer:
    """Computes confidence scores for agent pipeline output.

    Formula: composite = 0.35 * retrieval_confidence
                       + 0.40 * citation_coverage
                       + 0.25 * answer_completeness

    All sub-scores are in [0.0, 1.0]. Composite is rounded to 2 decimal places.
    """

    def compute(
        self,
        query: str,
        answer: str,
        chunks: list[ScoredChunk],
        citations: list[CitationResponse],
    ) -> ConfidenceScoreResponse:
        """Compute confidence scores for a query-answer pair.

        Args:
            query: The original user query.
            answer: The generated answer text.
            chunks: Retrieved and reranked source chunks.
            citations: Verified citations from the citation agent.

        Returns:
            ConfidenceScoreResponse with all sub-scores and composite.
        """
        # If no chunks retrieved, all scores are 0.0
        if not chunks:
            return ConfidenceScoreResponse(
                retrieval_confidence=0.0,
                citation_coverage=0.0,
                answer_completeness=0.0,
                composite=0.0,
            )

        retrieval_confidence = self._compute_retrieval(chunks)
        citation_coverage = self._compute_citation_coverage(answer, citations)
        answer_completeness = self._compute_completeness(query, chunks)

        composite = round(
            0.35 * retrieval_confidence + 0.40 * citation_coverage + 0.25 * answer_completeness,
            2,
        )

        logger.info(
            "confidence_scorer.computed",
            retrieval_confidence=retrieval_confidence,
            citation_coverage=citation_coverage,
            answer_completeness=answer_completeness,
            composite=composite,
        )

        return ConfidenceScoreResponse(
            retrieval_confidence=retrieval_confidence,
            citation_coverage=citation_coverage,
            answer_completeness=answer_completeness,
            composite=composite,
        )

    def _compute_retrieval(self, chunks: list[ScoredChunk]) -> float:
        """Max reranked score normalized to [0.0, 1.0].

        Args:
            chunks: Retrieved source chunks with scores.

        Returns:
            Maximum score clamped to [0.0, 1.0], or 0.0 if no chunks.
        """
        if not chunks:
            return 0.0
        return min(1.0, max(c.score for c in chunks))

    def _compute_citation_coverage(
        self, answer: str, citations: list[CitationResponse]
    ) -> float:
        """Verified citations / total factual statements in the answer.

        Total factual statements = count of sentences with periods in the answer.

        Args:
            answer: The generated answer text.
            citations: List of citations with verification status.

        Returns:
            Ratio of verified citations to factual statements, clamped to [0.0, 1.0].
            Returns 0.0 if there are no factual statements.
        """
        # Total factual statements = count of sentences ending with periods
        statements = [s.strip() for s in answer.split(".") if s.strip()]
        total_factual_statements = len(statements)

        if total_factual_statements == 0:
            return 0.0

        verified = sum(1 for c in citations if c.verification_status == "verified")
        return min(1.0, verified / total_factual_statements)

    def _compute_completeness(self, query: str, chunks: list[ScoredChunk]) -> float:
        """Addressed concepts / total query concepts.

        answer_completeness = addressed_concepts / total_query_concepts
        where total_query_concepts = number of distinct words > 3 chars in the query,
        and addressed_concepts = number of query concepts found in chunk text.

        Args:
            query: The original user query.
            chunks: Retrieved and reranked source chunks.

        Returns:
            Ratio of addressed concepts to total query concepts, clamped to [0.0, 1.0].
            Returns 0.0 if there are no query concepts.
        """
        query_terms = set(word.lower() for word in query.split() if len(word) > 3)
        total_query_concepts = len(query_terms)

        if total_query_concepts == 0:
            return 0.0

        # Count how many query concepts appear in any chunk text
        chunk_texts_combined = " ".join(c.text.lower() for c in chunks)
        addressed_concepts = sum(
            1 for term in query_terms if term in chunk_texts_combined
        )

        return min(1.0, addressed_concepts / total_query_concepts)
