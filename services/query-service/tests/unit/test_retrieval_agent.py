"""Unit tests for RetrievalAgent hybrid search and RRF fusion.

Tests cover:
- RRF fusion produces correctly sorted results
- Weight renormalization when 1 method unavailable
- Weight renormalization when 2 methods unavailable
- Cross-reference detection adjusts weights
- Timeout handling (graceful degradation)
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from domain_models.core import ScoredChunk

from src.agents.retrieval_agent import (
    CROSS_REF_WEIGHTS,
    DEFAULT_WEIGHTS,
    RRF_K,
    TOP_K,
    AllRetrievalMethodsUnavailableError,
    RetrievalAgent,
)


def _make_chunk(chunk_id: str, doc_id: str = "doc1", method: str = "dense") -> ScoredChunk:
    """Helper to create a ScoredChunk for testing."""
    return ScoredChunk(
        chunk_id=chunk_id,
        document_id=doc_id,
        text=f"Text for {chunk_id}",
        section_heading=f"Section {chunk_id}",
        score=0.9,
        retrieval_method=method,
        metadata={},
    )


def _make_chunks(prefix: str, count: int, method: str = "dense") -> list[ScoredChunk]:
    """Create a list of chunks with sequential IDs."""
    return [_make_chunk(f"{prefix}_{i}", method=method) for i in range(count)]


class TestRRFFusion:
    """Tests for the RRF fusion algorithm."""

    def test_fusion_produces_sorted_results(self):
        """RRF fusion returns results sorted by descending fused score."""
        # Dense results: chunk_a at rank 0, chunk_b at rank 1
        dense_results = [_make_chunk("chunk_a", method="dense"), _make_chunk("chunk_b", method="dense")]
        # Sparse results: chunk_b at rank 0, chunk_c at rank 1
        sparse_results = [_make_chunk("chunk_b", method="sparse"), _make_chunk("chunk_c", method="sparse")]
        # Graph results: chunk_a at rank 0, chunk_c at rank 1
        graph_results = [_make_chunk("chunk_a", method="graph"), _make_chunk("chunk_c", method="graph")]

        results_by_method = {
            "dense": dense_results,
            "sparse": sparse_results,
            "graph": graph_results,
        }
        weights = {"dense": 0.5, "sparse": 0.2, "graph": 0.3}

        fused = RetrievalAgent._rrf_fusion(results_by_method, weights)

        # Verify scores are sorted descending
        scores = [chunk.score for chunk in fused]
        assert scores == sorted(scores, reverse=True)

        # chunk_a appears in dense rank 0 + graph rank 0 -> highest
        # RRF score for chunk_a: 0.5/(60+1) + 0.3/(60+1) = 0.8/61
        # chunk_b appears in dense rank 1 + sparse rank 0
        # RRF score for chunk_b: 0.5/(60+2) + 0.2/(60+1) = 0.5/62 + 0.2/61
        # chunk_c appears in sparse rank 1 + graph rank 1
        # RRF score for chunk_c: 0.2/(60+2) + 0.3/(60+2) = 0.5/62
        assert fused[0].chunk_id == "chunk_a"

    def test_fusion_returns_top_20(self):
        """RRF fusion caps results at 20."""
        # 20 dense + 20 sparse + 20 graph (all different) = 60 unique chunks
        dense = _make_chunks("d", 20, "dense")
        sparse = _make_chunks("s", 20, "sparse")
        graph = _make_chunks("g", 20, "graph")

        results_by_method = {"dense": dense, "sparse": sparse, "graph": graph}
        weights = {"dense": 0.5, "sparse": 0.2, "graph": 0.3}

        fused = RetrievalAgent._rrf_fusion(results_by_method, weights)
        assert len(fused) == TOP_K

    def test_fusion_with_overlapping_chunks(self):
        """Chunks appearing in multiple methods get higher scores."""
        # common_chunk appears in all three methods at rank 0
        dense = [_make_chunk("common", method="dense")] + _make_chunks("d", 5, "dense")
        sparse = [_make_chunk("common", method="sparse")] + _make_chunks("s", 5, "sparse")
        graph = [_make_chunk("common", method="graph")] + _make_chunks("g", 5, "graph")

        results_by_method = {"dense": dense, "sparse": sparse, "graph": graph}
        weights = {"dense": 0.5, "sparse": 0.2, "graph": 0.3}

        fused = RetrievalAgent._rrf_fusion(results_by_method, weights)

        # common_chunk should be first (highest fused score)
        assert fused[0].chunk_id == "common"
        # First score is always 1.0 (normalized to max)
        assert fused[0].score == 1.0

    def test_fusion_empty_results(self):
        """Empty input returns empty results."""
        fused = RetrievalAgent._rrf_fusion({}, {})
        assert fused == []

    def test_fusion_single_method(self):
        """Fusion works with results from only one method."""
        chunks = _make_chunks("a", 5, "sparse")
        results_by_method = {"sparse": chunks}
        weights = {"sparse": 1.0}

        fused = RetrievalAgent._rrf_fusion(results_by_method, weights)
        assert len(fused) == 5
        # First chunk should have score 1.0
        assert fused[0].score == 1.0

    def test_fusion_retrieval_method_is_hybrid(self):
        """Fused results have retrieval_method set to 'hybrid'."""
        chunks = _make_chunks("a", 3, "dense")
        results_by_method = {"dense": chunks}
        weights = {"dense": 1.0}

        fused = RetrievalAgent._rrf_fusion(results_by_method, weights)
        for chunk in fused:
            assert chunk.retrieval_method == "hybrid"


class TestWeightRenormalization:
    """Tests for weight renormalization when methods are unavailable."""

    def test_all_methods_available(self):
        """When all 3 methods available, weights are unchanged (already sum to 1)."""
        weights = RetrievalAgent._renormalize_weights(
            DEFAULT_WEIGHTS, ["dense", "sparse", "graph"]
        )
        assert abs(weights["dense"] - 0.5) < 1e-10
        assert abs(weights["sparse"] - 0.2) < 1e-10
        assert abs(weights["graph"] - 0.3) < 1e-10
        assert abs(sum(weights.values()) - 1.0) < 1e-10

    def test_one_method_unavailable_graph_down(self):
        """When graph is unavailable, dense and sparse renormalize to sum 1.0."""
        weights = RetrievalAgent._renormalize_weights(
            DEFAULT_WEIGHTS, ["dense", "sparse"]
        )
        # dense=0.5, sparse=0.2, total=0.7
        # renormalized: dense=0.5/0.7, sparse=0.2/0.7
        expected_dense = 0.5 / 0.7
        expected_sparse = 0.2 / 0.7
        assert abs(weights["dense"] - expected_dense) < 1e-10
        assert abs(weights["sparse"] - expected_sparse) < 1e-10
        assert abs(sum(weights.values()) - 1.0) < 1e-10
        assert "graph" not in weights

    def test_one_method_unavailable_dense_down(self):
        """When dense is unavailable, sparse and graph renormalize."""
        weights = RetrievalAgent._renormalize_weights(
            DEFAULT_WEIGHTS, ["sparse", "graph"]
        )
        # sparse=0.2, graph=0.3, total=0.5
        expected_sparse = 0.2 / 0.5
        expected_graph = 0.3 / 0.5
        assert abs(weights["sparse"] - expected_sparse) < 1e-10
        assert abs(weights["graph"] - expected_graph) < 1e-10
        assert abs(sum(weights.values()) - 1.0) < 1e-10

    def test_two_methods_unavailable_only_sparse(self):
        """When only sparse is available, it gets weight 1.0."""
        weights = RetrievalAgent._renormalize_weights(
            DEFAULT_WEIGHTS, ["sparse"]
        )
        assert abs(weights["sparse"] - 1.0) < 1e-10
        assert len(weights) == 1

    def test_two_methods_unavailable_only_dense(self):
        """When only dense is available, it gets weight 1.0."""
        weights = RetrievalAgent._renormalize_weights(
            DEFAULT_WEIGHTS, ["dense"]
        )
        assert abs(weights["dense"] - 1.0) < 1e-10
        assert len(weights) == 1

    def test_two_methods_unavailable_only_graph(self):
        """When only graph is available, it gets weight 1.0."""
        weights = RetrievalAgent._renormalize_weights(
            DEFAULT_WEIGHTS, ["graph"]
        )
        assert abs(weights["graph"] - 1.0) < 1e-10
        assert len(weights) == 1

    def test_ratio_preserved(self):
        """Renormalization preserves the ratio between available methods."""
        weights = RetrievalAgent._renormalize_weights(
            DEFAULT_WEIGHTS, ["dense", "graph"]
        )
        # Original ratio dense:graph = 0.5:0.3 = 5:3
        # After renormalization, ratio should be preserved
        ratio = weights["dense"] / weights["graph"]
        expected_ratio = 0.5 / 0.3
        assert abs(ratio - expected_ratio) < 1e-10


class TestCrossReferenceDetection:
    """Tests for cross-reference keyword detection adjusting weights."""

    def test_amends_keyword(self):
        """Query with AMENDS uses cross-reference weights."""
        agent = RetrievalAgent()
        weights = agent._select_weights("This section AMENDS section 12")
        assert weights == CROSS_REF_WEIGHTS

    def test_references_keyword(self):
        """Query with REFERENCES uses cross-reference weights."""
        agent = RetrievalAgent()
        weights = agent._select_weights("Act REFERENCES the Transport Act")
        assert weights == CROSS_REF_WEIGHTS

    def test_implements_keyword(self):
        """Query with IMPLEMENTS uses cross-reference weights."""
        agent = RetrievalAgent()
        weights = agent._select_weights("This regulation IMPLEMENTS the Act")
        assert weights == CROSS_REF_WEIGHTS

    def test_section_number_pattern(self):
        """Query with 'Section 45' uses cross-reference weights."""
        agent = RetrievalAgent()
        weights = agent._select_weights("What does Section 45 say about penalties?")
        assert weights == CROSS_REF_WEIGHTS

    def test_section_abbreviated_pattern(self):
        """Query with 's.12' uses cross-reference weights."""
        agent = RetrievalAgent()
        weights = agent._select_weights("Refer to s.12 for definitions")
        assert weights == CROSS_REF_WEIGHTS

    def test_part_division_pattern(self):
        """Query with 'Part 3 Division 2' uses cross-reference weights."""
        agent = RetrievalAgent()
        weights = agent._select_weights("Under Part 3 Division 2 of the Act")
        assert weights == CROSS_REF_WEIGHTS

    def test_normal_query_default_weights(self):
        """Query without cross-reference keywords uses default weights."""
        agent = RetrievalAgent()
        weights = agent._select_weights("What is the speed limit for heavy vehicles?")
        assert weights == DEFAULT_WEIGHTS

    def test_case_insensitive_keywords(self):
        """Cross-reference keywords are detected case-insensitively."""
        agent = RetrievalAgent()
        weights = agent._select_weights("this amends the regulation")
        assert weights == CROSS_REF_WEIGHTS

    def test_cross_ref_weights_boost_graph(self):
        """Cross-reference weights boost graph to 0.5."""
        assert CROSS_REF_WEIGHTS["graph"] == 0.5
        assert CROSS_REF_WEIGHTS["dense"] == 0.3
        assert CROSS_REF_WEIGHTS["sparse"] == 0.2


class TestTimeoutHandling:
    """Tests for timeout and graceful degradation."""

    @pytest.mark.asyncio
    async def test_dense_timeout_graceful_degradation(self):
        """When dense search times out, sparse and graph still work."""
        # Mock BM25 to return results
        bm25_index = AsyncMock()
        bm25_index.search = AsyncMock(return_value=[
            {"chunk_id": "s1", "document_id": "doc1", "text": "sparse text",
             "section_heading": "S1", "score": 0.8, "metadata": {}},
        ])

        # Mock embedding client to time out
        embedding_client = AsyncMock()
        embedding_client.post = AsyncMock(side_effect=asyncio.TimeoutError())

        chromadb_store = AsyncMock()

        # Mock graph client
        graph_client = AsyncMock()
        graph_response = MagicMock()
        graph_response.json.return_value = {
            "results": [
                {"chunk_id": "g1", "document_id": "doc1", "text": "graph text",
                 "section_heading": "G1", "score": 0.7, "metadata": {}},
            ]
        }
        graph_response.raise_for_status = MagicMock()
        graph_client.post = AsyncMock(return_value=graph_response)

        agent = RetrievalAgent(
            embedding_client=embedding_client,
            graph_client=graph_client,
            chromadb_store=chromadb_store,
            bm25_index=bm25_index,
        )

        results = await agent.retrieve("test query", "corr-123")

        # Should get results from sparse and graph only
        assert len(results) > 0
        chunk_ids = {r.chunk_id for r in results}
        assert "s1" in chunk_ids or "g1" in chunk_ids

    @pytest.mark.asyncio
    async def test_graph_timeout_graceful_degradation(self):
        """When graph search times out, dense and sparse still work."""
        # Mock embedding client
        embedding_client = AsyncMock()
        embed_response = MagicMock()
        embed_response.json.return_value = {"vector": [0.1] * 768, "tokens_used": 5}
        embed_response.raise_for_status = MagicMock()
        embedding_client.post = AsyncMock(return_value=embed_response)

        # Mock chromadb
        chromadb_store = AsyncMock()
        chromadb_store.search = AsyncMock(return_value=[
            {"chunk_id": "d1", "document_id": "doc1", "text": "dense text",
             "section_heading": "D1", "score": 0.9, "metadata": {}},
        ])

        # Mock BM25
        bm25_index = AsyncMock()
        bm25_index.search = AsyncMock(return_value=[
            {"chunk_id": "s1", "document_id": "doc1", "text": "sparse text",
             "section_heading": "S1", "score": 0.8, "metadata": {}},
        ])

        # Graph times out
        graph_client = AsyncMock()
        graph_client.post = AsyncMock(side_effect=asyncio.TimeoutError())

        agent = RetrievalAgent(
            embedding_client=embedding_client,
            graph_client=graph_client,
            chromadb_store=chromadb_store,
            bm25_index=bm25_index,
        )

        results = await agent.retrieve("test query", "corr-123")
        assert len(results) > 0

    @pytest.mark.asyncio
    async def test_all_methods_unavailable_raises(self):
        """When all methods fail, raises AllRetrievalMethodsUnavailableError."""
        embedding_client = AsyncMock()
        embedding_client.post = AsyncMock(side_effect=asyncio.TimeoutError())

        chromadb_store = AsyncMock()
        bm25_index = AsyncMock()
        bm25_index.search = AsyncMock(side_effect=Exception("BM25 failed"))

        graph_client = AsyncMock()
        graph_client.post = AsyncMock(side_effect=asyncio.TimeoutError())

        agent = RetrievalAgent(
            embedding_client=embedding_client,
            graph_client=graph_client,
            chromadb_store=chromadb_store,
            bm25_index=bm25_index,
        )

        with pytest.raises(AllRetrievalMethodsUnavailableError):
            await agent.retrieve("test query", "corr-123")

    @pytest.mark.asyncio
    async def test_no_clients_returns_empty(self):
        """Agent with no clients configured returns empty results gracefully."""
        agent = RetrievalAgent()

        # All methods return empty (not configured) — valid empty results
        results = await agent.retrieve("test query", "corr-123")
        assert results == []

    @pytest.mark.asyncio
    async def test_two_methods_timeout_one_succeeds(self):
        """When 2 methods time out, the remaining one still returns results."""
        # Only BM25 works
        bm25_index = AsyncMock()
        bm25_index.search = AsyncMock(return_value=[
            {"chunk_id": "s1", "document_id": "doc1", "text": "text",
             "section_heading": "S1", "score": 0.8, "metadata": {}},
            {"chunk_id": "s2", "document_id": "doc1", "text": "text2",
             "section_heading": "S2", "score": 0.7, "metadata": {}},
        ])

        # Both remote services time out
        embedding_client = AsyncMock()
        embedding_client.post = AsyncMock(side_effect=asyncio.TimeoutError())
        chromadb_store = AsyncMock()

        graph_client = AsyncMock()
        graph_client.post = AsyncMock(side_effect=asyncio.TimeoutError())

        agent = RetrievalAgent(
            embedding_client=embedding_client,
            graph_client=graph_client,
            chromadb_store=chromadb_store,
            bm25_index=bm25_index,
        )

        results = await agent.retrieve("test query", "corr-123")
        assert len(results) == 2
        assert results[0].chunk_id == "s1"
        assert results[1].chunk_id == "s2"
