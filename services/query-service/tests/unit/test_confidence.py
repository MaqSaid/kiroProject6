"""Unit tests for confidence scoring, fallback logic, and sub-score calculations.

Tests specified by Task 7.4:
- composite = 0.35*0.9 + 0.40*1.0 + 0.25*0.8 = 0.915 → round to 0.92
- composite = 0.0 when no chunks (all scores 0.0)
- fallback triggered when composite < 0.4
- fallback NOT triggered when composite >= 0.4
- retrieval_confidence = 0.0 when chunks is empty
- citation_coverage = 0.0 when no verified citations
"""

import pytest

from domain_models.api_models import CitationResponse
from domain_models.core import ScoredChunk
from src.agents.confidence_scorer import ConfidenceScorer


FALLBACK_THRESHOLD = 0.4


def _make_chunk(chunk_id: str, score: float) -> ScoredChunk:
    """Helper to create a ScoredChunk for testing."""
    return ScoredChunk(
        chunk_id=chunk_id,
        document_id=f"doc-{chunk_id}",
        text=f"Content of chunk {chunk_id} with some detailed text for testing purposes.",
        section_heading=f"Section {chunk_id}",
        score=score,
        retrieval_method="dense",
        metadata={},
    )


def _make_chunk_with_text(chunk_id: str, score: float, text: str) -> ScoredChunk:
    """Helper to create a ScoredChunk with specific text for testing."""
    return ScoredChunk(
        chunk_id=chunk_id,
        document_id=f"doc-{chunk_id}",
        text=text,
        section_heading=f"Section {chunk_id}",
        score=score,
        retrieval_method="dense",
        metadata={},
    )


def _make_citation(status: str = "verified") -> CitationResponse:
    """Helper to create a CitationResponse for testing."""
    return CitationResponse(
        index=0,
        source_reference="Act Title, Section 1",
        claim="A specific legal claim that is factual.",
        verification_status=status,
    )


@pytest.fixture
def scorer():
    return ConfidenceScorer()


class TestCompositeFormula:
    """Tests for the composite confidence formula."""

    def test_composite_known_values(self, scorer):
        """composite = 0.35*0.9 + 0.40*1.0 + 0.25*0.8 = 0.315 + 0.4 + 0.2 = 0.915 → round to 0.92."""
        # We need retrieval_confidence = 0.9, citation_coverage = 1.0, answer_completeness = 0.8
        # retrieval_confidence = max(chunk.score) = 0.9
        # answer_completeness = addressed_concepts / total_query_concepts
        # We need 0.8 → 4/5 = 0.8 → 5 query concepts, 4 addressed in chunk text
        # query concepts: "transport", "vehicle", "registration", "safety", "compliance" (5 words > 3 chars)
        # Chunks text must contain exactly 4 of those 5 concepts
        chunks = [
            _make_chunk_with_text("1", 0.9, "This chunk covers transport and vehicle topics."),
            _make_chunk_with_text("2", 0.9, "This chunk covers registration requirements."),
            _make_chunk_with_text("3", 0.9, "This chunk discusses safety measures."),
            _make_chunk_with_text("4", 0.9, "This chunk has other information."),
        ]

        # citation_coverage = verified / total_factual_statements
        # We need 1.0 → 2 verified citations, 2 sentences
        answer = "The act requires compliance. Penalties apply for violations."
        citations = [_make_citation("verified"), _make_citation("verified")]

        # query concepts = distinct words > 3 chars = 5
        # 4 of 5 addressed: "transport", "vehicle", "registration", "safety" in chunk text
        # "compliance" is NOT in chunk text → 4/5 = 0.8
        query = "transport vehicle registration safety compliance"

        result = scorer.compute(query, answer, chunks, citations)

        assert result.retrieval_confidence == 0.9
        assert result.citation_coverage == 1.0
        assert result.answer_completeness == 0.8
        assert result.composite == 0.92

    def test_composite_zero_when_no_chunks(self, scorer):
        """composite = 0.0 when no chunks (all scores 0.0)."""
        result = scorer.compute(
            query="what are the penalties for speeding",
            answer="",
            chunks=[],
            citations=[],
        )
        assert result.retrieval_confidence == 0.0
        assert result.citation_coverage == 0.0
        assert result.answer_completeness == 0.0
        assert result.composite == 0.0


class TestFallbackTrigger:
    """Tests for fallback threshold behavior."""

    def test_fallback_triggered_when_composite_below_threshold(self, scorer):
        """Fallback triggered when composite < 0.4."""
        # No chunks → composite = 0.0 < 0.4
        result = scorer.compute("some query here", "", [], [])
        assert result.composite < FALLBACK_THRESHOLD

    def test_fallback_not_triggered_when_composite_at_or_above_threshold(self, scorer):
        """Fallback NOT triggered when composite >= 0.4."""
        chunks = [_make_chunk(str(i), 0.85) for i in range(3)]
        answer = "The transport act defines these obligations clearly."
        citations = [_make_citation("verified")]
        query = "transport"

        result = scorer.compute(query, answer, chunks, citations)
        assert result.composite >= FALLBACK_THRESHOLD


class TestRetrievalConfidence:
    """Tests for retrieval_confidence sub-score."""

    def test_retrieval_confidence_zero_when_chunks_empty(self, scorer):
        """retrieval_confidence = 0.0 when chunks is empty."""
        result = scorer.compute(
            query="some query",
            answer="",
            chunks=[],
            citations=[],
        )
        assert result.retrieval_confidence == 0.0


class TestCitationCoverage:
    """Tests for citation_coverage sub-score."""

    def test_citation_coverage_zero_when_no_verified_citations(self, scorer):
        """citation_coverage = 0.0 when no verified citations."""
        chunks = [_make_chunk("1", 0.8)]
        answer = "The act requires compliance. Penalties apply for violations."
        citations = [_make_citation("unsupported"), _make_citation("unsupported")]
        query = "compliance"

        result = scorer.compute(query, answer, chunks, citations)
        assert result.citation_coverage == 0.0
