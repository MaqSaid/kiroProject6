"""Property tests for retrieval: RRF fusion, reranker ordering, metadata.

# Feature: production-rag-pipeline-hybrid-search, Properties 10-12
"""

from __future__ import annotations

import uuid

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from src.domain.models.entities import Chunk, ScoredChunk
from src.domain.models.enums import ChunkingStrategy, RRFWeights
from src.domain.services.retrieval_service import RRF_K, RetrievalService

# --- Strategies ---


def make_scored_chunk(score: float, method: str = "dense") -> ScoredChunk:
    """Create a ScoredChunk with a random chunk ID."""
    return ScoredChunk(
        chunk=Chunk(
            id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            index=0,
            text="Test chunk content.",
            section_heading="Section",
            strategy=ChunkingStrategy.FIXED_SIZE,
            char_count=20,
        ),
        score=score,
        retrieval_method=method,
    )


def make_ranked_list(n: int, method: str = "dense") -> list[ScoredChunk]:
    """Create a ranked list of n scored chunks."""
    return [make_scored_chunk(1.0 - i * 0.05, method) for i in range(n)]


# --- Property 10: RRF fusion ---


@pytest.mark.property
@settings(max_examples=100)
@given(
    n_dense=st.integers(min_value=1, max_value=10),
    n_sparse=st.integers(min_value=1, max_value=10),
    n_graph=st.integers(min_value=0, max_value=5),
    dense_w=st.floats(min_value=0.1, max_value=0.8, allow_nan=False),
    sparse_w=st.floats(min_value=0.1, max_value=0.5, allow_nan=False),
)
def test_rrf_includes_all_unique_items(
    n_dense: int, n_sparse: int, n_graph: int, dense_w: float, sparse_w: float
) -> None:
    """Property 10a: All unique items from all lists are included in fused output."""
    graph_w = round(1.0 - dense_w - sparse_w, 4)
    assume(graph_w > 0)
    assume(abs(dense_w + sparse_w + graph_w - 1.0) < 0.01)

    dense = make_ranked_list(n_dense, "dense")
    sparse = make_ranked_list(n_sparse, "sparse")
    graph = make_ranked_list(n_graph, "graph")

    weights = RRFWeights(dense=dense_w, sparse=sparse_w, graph=graph_w)

    service = RetrievalService.__new__(RetrievalService)
    fused = service._reciprocal_rank_fusion(dense, sparse, graph, weights)

    input_ids = {str(sc.chunk.id) for sc in dense + sparse + graph}
    fused_ids = {str(sc.chunk.id) for sc in fused}
    assert input_ids == fused_ids


@pytest.mark.property
@settings(max_examples=100)
@given(n=st.integers(min_value=2, max_value=15))
def test_rrf_output_sorted_descending(n: int) -> None:
    """Property 10b: Output sorted by descending fused score."""
    dense = make_ranked_list(n, "dense")
    sparse = make_ranked_list(n, "sparse")
    weights = RRFWeights(dense=0.5, sparse=0.2, graph=0.3)

    service = RetrievalService.__new__(RetrievalService)
    fused = service._reciprocal_rank_fusion(dense, sparse, [], weights)

    scores = [sc.score for sc in fused]
    for i in range(len(scores) - 1):
        assert scores[i] >= scores[i + 1]


@pytest.mark.property
@settings(max_examples=50)
@given(n=st.integers(min_value=1, max_value=10))
def test_rrf_uses_correct_formula(n: int) -> None:
    """Property 10c: Scores match w / (k + rank + 1) formula."""
    dense = make_ranked_list(n, "dense")
    weights = RRFWeights(dense=0.5, sparse=0.2, graph=0.3)

    service = RetrievalService.__new__(RetrievalService)
    fused = service._reciprocal_rank_fusion(dense, [], [], weights)

    for rank, sc in enumerate(fused):
        expected = weights.dense / (RRF_K + rank + 1)
        assert abs(sc.score - expected) < 1e-6


# --- Property 12: Required metadata ---


@pytest.mark.property
@settings(max_examples=100)
@given(n=st.integers(min_value=1, max_value=10))
def test_retrieval_results_have_required_metadata(n: int) -> None:
    """Property 12: Every result has document_id, section, score >= 0, valid method."""
    dense = make_ranked_list(n, "dense")
    weights = RRFWeights(dense=0.5, sparse=0.2, graph=0.3)

    service = RetrievalService.__new__(RetrievalService)
    fused = service._reciprocal_rank_fusion(dense, [], [], weights)

    valid_methods = {"dense", "sparse", "graph", "fused", "reranked"}
    for sc in fused:
        assert sc.chunk.document_id is not None
        assert isinstance(sc.chunk.section_heading, str)
        assert sc.score >= 0
        assert sc.retrieval_method in valid_methods
