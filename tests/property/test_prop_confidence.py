"""Property tests for confidence scoring and fallback behavior.

# Feature: production-rag-pipeline-hybrid-search, Properties 17-18
"""

from __future__ import annotations

import uuid

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.domain.models.entities import (
    Chunk,
    ConfidenceScore,
    FallbackInfo,
    GenerationResult,
    ScoredChunk,
)
from src.domain.models.enums import ChunkingStrategy

confidence_float = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)


def make_chunk_with_score(score: float) -> ScoredChunk:
    return ScoredChunk(
        chunk=Chunk(
            id=uuid.uuid4(), document_id=uuid.uuid4(), index=0, text="content",
            section_heading="S", strategy=ChunkingStrategy.FIXED_SIZE, char_count=7,
        ),
        score=score, retrieval_method="fused",
    )


@pytest.mark.property
@settings(max_examples=200)
@given(retrieval=confidence_float, citation=confidence_float, completeness=confidence_float)
def test_confidence_all_dimensions_in_range(
    retrieval: float, citation: float, completeness: float
) -> None:
    """Property 17a: All confidence dimensions are in [0, 1]."""
    composite = min(1.0, 0.35 * retrieval + 0.40 * citation + 0.25 * completeness)
    score = ConfidenceScore(
        retrieval_confidence=retrieval, citation_coverage=citation,
        answer_completeness=completeness, composite=composite,
    )
    assert 0.0 <= score.retrieval_confidence <= 1.0
    assert 0.0 <= score.citation_coverage <= 1.0
    assert 0.0 <= score.answer_completeness <= 1.0
    assert 0.0 <= score.composite <= 1.0


@pytest.mark.property
@settings(max_examples=200)
@given(retrieval=confidence_float, citation=confidence_float, completeness=confidence_float)
def test_confidence_composite_is_weighted_sum(
    retrieval: float, citation: float, completeness: float
) -> None:
    """Property 17b: Composite = weighted sum of dimensions."""
    expected = min(1.0, 0.35 * retrieval + 0.40 * citation + 0.25 * completeness)
    score = ConfidenceScore(
        retrieval_confidence=retrieval, citation_coverage=citation,
        answer_completeness=completeness, composite=expected,
    )
    actual = 0.35 * score.retrieval_confidence + 0.40 * score.citation_coverage + 0.25 * score.answer_completeness
    assert abs(score.composite - min(1.0, actual)) < 1e-6


@pytest.mark.property
@settings(max_examples=100)
@given(retrieval=st.floats(min_value=0.0, max_value=0.29, allow_nan=False))
def test_low_confidence_triggers_fallback(retrieval: float) -> None:
    """Property 18: retrieval_confidence < threshold triggers fallback."""
    result = GenerationResult(
        answer="Fallback", citations=[], context_chunks=[make_chunk_with_score(retrieval)],
        confidence=ConfidenceScore(
            retrieval_confidence=retrieval, citation_coverage=0.0,
            answer_completeness=0.2, composite=0.1,
        ),
        is_fallback=True,
        fallback_info=FallbackInfo(found=[], not_found=["q"], suggested_documents=[]),
    )
    assert result.is_fallback is True
    assert result.confidence.retrieval_confidence < 0.3
    assert result.fallback_info is not None


@pytest.mark.property
@settings(max_examples=100)
@given(retrieval=st.floats(min_value=0.0, max_value=0.001, allow_nan=False))
def test_zero_confidence_never_confident(retrieval: float) -> None:
    """Property 18b: Near-zero confidence always marked as fallback."""
    result = GenerationResult(
        answer="a", citations=[], context_chunks=[],
        confidence=ConfidenceScore(
            retrieval_confidence=retrieval, citation_coverage=0.0,
            answer_completeness=0.0, composite=retrieval * 0.35,
        ),
        is_fallback=True,
    )
    assert result.is_fallback is True
    assert result.confidence.composite < 0.05
