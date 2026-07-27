"""Tests for the cross-encoder Reranker."""

import pytest

from domain_models.core import ScoredChunk
from src.agents.reranker import Reranker


def _make_chunk(chunk_id: str, score: float, text: str = "Sample text") -> ScoredChunk:
    """Helper to create a ScoredChunk for testing."""
    return ScoredChunk(
        chunk_id=chunk_id,
        document_id=f"doc-{chunk_id}",
        text=text,
        section_heading=f"Section {chunk_id}",
        score=score,
        retrieval_method="dense",
        metadata={},
    )


@pytest.fixture
def reranker():
    """Create a fake-mode reranker for testing without model download."""
    return Reranker(fake=True)


class TestRerankerEmptyInput:
    """Tests for empty input handling."""

    async def test_empty_candidates_returns_empty(self, reranker):
        result = await reranker.rerank("test query", [])
        assert result == []


class TestRerankerOutputSize:
    """Tests for reranker output size invariant: returns min(5, N) results."""

    async def test_fewer_than_5_candidates_returns_all(self, reranker):
        """Reranker returns all candidates when fewer than 5 are available."""
        candidates = [_make_chunk(str(i), 0.5 + i * 0.1) for i in range(3)]
        result = await reranker.rerank("test query", candidates, top_n=5)
        assert len(result) == 3

    async def test_exactly_5_candidates_returns_all(self, reranker):
        """Reranker returns all 5 when exactly 5 candidates are available."""
        candidates = [_make_chunk(str(i), 0.5 + i * 0.05) for i in range(5)]
        result = await reranker.rerank("test query", candidates, top_n=5)
        assert len(result) == 5

    async def test_20_candidates_returns_top_5(self, reranker):
        """Reranker returns top 5 from 20 candidates."""
        candidates = [_make_chunk(str(i), i * 0.05) for i in range(20)]
        result = await reranker.rerank("test query", candidates, top_n=5)
        assert len(result) == 5

    async def test_10_candidates_returns_top_5(self, reranker):
        """Reranker returns top 5 from 10 candidates."""
        candidates = [_make_chunk(str(i), i * 0.1) for i in range(10)]
        result = await reranker.rerank("test query", candidates, top_n=5)
        assert len(result) == 5

    async def test_1_candidate_returns_1(self, reranker):
        """Reranker returns the single candidate when only 1 is available."""
        candidates = [_make_chunk("0", 0.8)]
        result = await reranker.rerank("test query", candidates, top_n=5)
        assert len(result) == 1


class TestRerankerSorting:
    """Tests for reranker sorting behavior in fake mode."""

    async def test_results_sorted_by_score_descending(self, reranker):
        """Fake reranker returns candidates sorted by existing score descending."""
        candidates = [
            _make_chunk("low", 0.2),
            _make_chunk("high", 0.9),
            _make_chunk("mid", 0.5),
        ]
        result = await reranker.rerank("test query", candidates, top_n=5)
        scores = [c.score for c in result]
        assert scores == sorted(scores, reverse=True)
        assert result[0].chunk_id == "high"
        assert result[1].chunk_id == "mid"
        assert result[2].chunk_id == "low"


class TestRerankerModelFailure:
    """Tests for model loading failure fallback behavior."""

    async def test_model_load_failure_returns_original_order(self):
        """When model loading fails, reranker returns candidates in original order."""
        # Use a non-existent model name to trigger load failure
        reranker = Reranker(model_name="non-existent-model/does-not-exist", fake=False)

        candidates = [
            _make_chunk("first", 0.3),
            _make_chunk("second", 0.8),
            _make_chunk("third", 0.5),
            _make_chunk("fourth", 0.1),
            _make_chunk("fifth", 0.9),
            _make_chunk("sixth", 0.7),
        ]
        result = await reranker.rerank("test query", candidates, top_n=5)

        # Should return first 5 candidates in ORIGINAL order (not sorted by score)
        assert len(result) == 5
        assert result[0].chunk_id == "first"
        assert result[1].chunk_id == "second"
        assert result[2].chunk_id == "third"
        assert result[3].chunk_id == "fourth"
        assert result[4].chunk_id == "fifth"
