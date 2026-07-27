"""Tests for the ConfidenceScorer."""

import pytest

from domain_models.api_models import CitationResponse
from domain_models.core import ScoredChunk
from src.agents.confidence_scorer import ConfidenceScorer


def _make_chunk(chunk_id: str, score: float, text: str = "") -> ScoredChunk:
    """Helper to create a ScoredChunk for testing."""
    if not text:
        text = f"Content of chunk {chunk_id} with some detailed text."
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
    """Tests for confidence composite formula correctness."""

    def test_composite_formula_basic(self, scorer):
        """Composite = 0.35*r + 0.40*c + 0.25*a, rounded to 2 decimal places."""
        # retrieval_confidence = max(0.8) = 0.8
        chunks = [_make_chunk("1", 0.8, text="The Transport Act requires vehicle registration.")]
        # answer with 2 sentences (split by '.'), 2 verified citations → coverage = 2/2 = 1.0
        answer = "The Transport Act requires all vehicles to be registered. Penalties apply for non-compliance with this regulation."
        citations = [_make_citation("verified"), _make_citation("verified")]
        # query: "transport vehicle registration requirements" → 4 words > 3 chars
        # concepts in chunk text: "transport" yes, "vehicle" yes, "registration" yes, "requirements" no
        # completeness = 3/4 = 0.75
        query = "transport vehicle registration requirements"

        result = scorer.compute(query, answer, chunks, citations)

        assert result.retrieval_confidence == 0.8
        assert result.citation_coverage == 1.0
        assert result.answer_completeness == 0.75
        assert result.composite == round(0.35 * 0.8 + 0.40 * 1.0 + 0.25 * 0.75, 2)

    def test_composite_formula_all_zeros(self, scorer):
        """All scores = 0.0 when no chunks, no citations, no answer."""
        result = scorer.compute("what is this", "", [], [])
        assert result.retrieval_confidence == 0.0
        assert result.citation_coverage == 0.0
        assert result.answer_completeness == 0.0
        assert result.composite == 0.0

    def test_composite_formula_perfect_scores(self, scorer):
        """Maximum scores produce expected composite."""
        # For perfect retrieval: score = 1.0
        # For perfect citation_coverage: verified citations >= sentences
        # For perfect answer_completeness: all query concepts present in chunk text
        # query: "regulation drivers licence" → 3 words > 3 chars
        chunks = [_make_chunk("1", 1.0, text="The regulation about drivers and their licence requirements.")]
        # Answer with 1 sentence, 1 verified citation → 1/1 = 1.0
        answer = "The regulation clearly states that all drivers must hold a valid licence."
        citations = [_make_citation("verified")]
        query = "regulation drivers licence"

        result = scorer.compute(query, answer, chunks, citations)

        assert result.retrieval_confidence == 1.0
        assert result.citation_coverage == 1.0
        # answer_completeness: "regulation" in chunk, "drivers" in chunk, "licence" in chunk → 3/3 = 1.0
        assert result.answer_completeness == 1.0
        assert result.composite == round(0.35 * 1.0 + 0.40 * 1.0 + 0.25 * 1.0, 2)
        assert result.composite == 1.0


class TestRetrievalConfidence:
    """Tests for retrieval_confidence sub-score."""

    def test_no_chunks_returns_zero(self, scorer):
        result = scorer.compute("query", "", [], [])
        assert result.retrieval_confidence == 0.0

    def test_single_chunk_returns_its_score(self, scorer):
        chunks = [_make_chunk("1", 0.75)]
        result = scorer.compute("query", "answer.", chunks, [])
        assert result.retrieval_confidence == 0.75

    def test_multiple_chunks_returns_max(self, scorer):
        chunks = [_make_chunk("1", 0.3), _make_chunk("2", 0.9), _make_chunk("3", 0.5)]
        result = scorer.compute("query", "answer.", chunks, [])
        assert result.retrieval_confidence == 0.9

    def test_score_clamped_to_one(self, scorer):
        """Scores are capped at 1.0."""
        chunks = [_make_chunk("1", 1.0)]
        result = scorer.compute("query", "answer.", chunks, [])
        assert result.retrieval_confidence == 1.0


class TestCitationCoverage:
    """Tests for citation_coverage sub-score."""

    def test_no_citations_returns_zero(self, scorer):
        """Answer with statements but no citations returns 0.0."""
        chunks = [_make_chunk("1", 0.8)]
        answer = "The regulation requires all drivers to hold a valid licence. Penalties apply."
        result = scorer.compute("query", answer, chunks, [])
        assert result.citation_coverage == 0.0

    def test_no_statements_returns_zero(self, scorer):
        """Answer with no factual statements returns 0.0."""
        chunks = [_make_chunk("1", 0.8)]
        answer = ""
        citations = [_make_citation("verified")]
        result = scorer.compute("query", answer, chunks, citations)
        assert result.citation_coverage == 0.0

    def test_all_citations_unsupported_returns_zero(self, scorer):
        """All unsupported citations results in 0.0."""
        chunks = [_make_chunk("1", 0.8)]
        answer = "The regulation requires compliance. Penalties apply for violations."
        citations = [_make_citation("unsupported"), _make_citation("unsupported")]
        result = scorer.compute("query", answer, chunks, citations)
        assert result.citation_coverage == 0.0

    def test_partial_coverage(self, scorer):
        """Partial verified citations produce correct ratio."""
        chunks = [_make_chunk("1", 0.8)]
        answer = "The regulation requires compliance. Penalties apply for violations."
        citations = [_make_citation("verified"), _make_citation("unsupported")]
        # 2 sentences, 1 verified → 1/2 = 0.5
        result = scorer.compute("query", answer, chunks, citations)
        assert result.citation_coverage == 0.5


class TestAnswerCompleteness:
    """Tests for answer_completeness sub-score."""

    def test_no_query_terms_returns_zero(self, scorer):
        """Query with only short words: 0 query concepts → returns 0.0."""
        chunks = [_make_chunk("1", 0.8)]
        # "is a the" → no words > 3 chars → 0 query concepts → 0.0
        result = scorer.compute("is a the", "answer.", chunks, [])
        assert result.answer_completeness == 0.0

    def test_all_concepts_addressed(self, scorer):
        """All query concepts found in chunk text returns 1.0."""
        chunks = [_make_chunk("1", 0.8, text="The transport regulation covers penalty provisions.")]
        # "transport regulation penalty" → 3 concepts, all in chunk text
        result = scorer.compute("transport regulation penalty", "answer.", chunks, [])
        assert result.answer_completeness == 1.0

    def test_partial_concepts_addressed(self, scorer):
        """Some query concepts found in chunk text."""
        chunks = [_make_chunk("1", 0.8, text="The transport regulation is important.")]
        # "transport regulations penalty licence" → 4 concepts
        # "transport" in text → yes, "regulations" in "the transport regulation is important." → no
        # "penalty" → no, "licence" → no
        # Only "transport" matches → 1/4 = 0.25
        result = scorer.compute("transport regulations penalty licence", "answer.", chunks, [])
        assert result.answer_completeness == 0.25

    def test_fewer_chunks_than_concepts_but_text_matches(self, scorer):
        """Even with 1 chunk, if text contains all concepts, completeness = 1.0."""
        chunks = [_make_chunk("1", 0.8, text="Transport regulations impose penalty on licence holders.")]
        # "transport regulations penalty licence" → 4 concepts, all in chunk text
        result = scorer.compute("transport regulations penalty licence", "answer.", chunks, [])
        assert result.answer_completeness == 1.0


class TestFallbackTrigger:
    """Tests for fallback threshold behavior."""

    def test_fallback_triggered_when_composite_below_threshold(self, scorer):
        """Composite < 0.4 should trigger fallback."""
        result = scorer.compute("some query here", "", [], [])
        assert result.composite < 0.4

    def test_no_fallback_when_composite_at_threshold(self, scorer):
        """Composite >= 0.4 should not trigger fallback."""
        chunks = [_make_chunk("1", 0.9, text="The transport infrastructure defines obligations for all parties.")]
        answer = "The transport infrastructure act defines obligations."
        citations = [_make_citation("verified")]
        query = "transport infrastructure obligations"
        # retrieval = 0.9
        # citation_coverage = 1/1 = 1.0
        # completeness: "transport" in text, "infrastructure" in text, "obligations" in text → 3/3 = 1.0
        # composite = round(0.35*0.9 + 0.40*1.0 + 0.25*1.0, 2) = round(0.315+0.4+0.25, 2) = 0.97

        result = scorer.compute(query, answer, chunks, citations)
        assert result.composite >= 0.4


class TestZeroChunksEdgeCase:
    """Tests for zero-chunks edge case."""

    def test_zero_chunks_all_scores_zero(self, scorer):
        """When no chunks retrieved, all scores should be 0.0."""
        result = scorer.compute(
            query="what are the penalties",
            answer="",
            chunks=[],
            citations=[],
        )
        assert result.retrieval_confidence == 0.0
        assert result.citation_coverage == 0.0
        assert result.answer_completeness == 0.0
        assert result.composite == 0.0
