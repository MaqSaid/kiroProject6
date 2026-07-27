"""Unit tests for Retrieval Agent hybrid search and RRF fusion.

Covers the task-specified test cases:
- RRF fusion produces correct scores
- Weight renormalization when one method unavailable
- Weight renormalization when two methods unavailable
- All items from all lists appear in fused output
- Output sorted by descending score
- Timeout handling (method declared unavailable after 5s)

Requirements: 10.1, 10.2, 10.3, 10.4
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from domain_models.core import ScoredChunk

from src.agents.retrieval_agent import (
    DEFAULT_WEIGHTS,
    RRF_K,
    TOP_K,
    AllRetrievalMethodsUnavailableError,
    RetrievalAgent,
)


# --- Helpers ---


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


# --- RRF Fusion Score Tests ---


class TestRRFFusionScores:
    """Tests that RRF fusion produces correct scores according to the formula."""

    def test_rrf_fusion_correct_scores_single_method(self):
        """RRF scores follow the formula weight / (k + rank + 1) for a single method."""
        chunks = _make_chunks("a", 3, "dense")
        results_by_method = {"dense": chunks}
        weights = {"dense": 1.0}

        fused = RetrievalAgent._rrf_fusion(results_by_method, weights)

        # Verify raw RRF scores before normalization:
        # rank 0: 1.0 / (60 + 0 + 1) = 1/61
        # rank 1: 1.0 / (60 + 1 + 1) = 1/62
        # rank 2: 1.0 / (60 + 2 + 1) = 1/63
        # After normalization (divide by max = 1/61):
        # rank 0: 1.0
        # rank 1: (1/62) / (1/61) = 61/62
        # rank 2: (1/63) / (1/61) = 61/63
        assert len(fused) == 3
        assert fused[0].score == 1.0
        expected_score_1 = round(61 / 62, 4)
        expected_score_2 = round(61 / 63, 4)
        assert fused[1].score == expected_score_1
        assert fused[2].score == expected_score_2

    def test_rrf_fusion_correct_scores_multiple_methods(self):
        """RRF scores accumulate correctly across multiple methods."""
        # chunk_a in dense rank 0 and graph rank 0
        # chunk_b in sparse rank 0 only
        dense = [_make_chunk("chunk_a", method="dense")]
        sparse = [_make_chunk("chunk_b", method="sparse")]
        graph = [_make_chunk("chunk_a", method="graph")]

        results_by_method = {"dense": dense, "sparse": sparse, "graph": graph}
        weights = {"dense": 0.5, "sparse": 0.2, "graph": 0.3}

        fused = RetrievalAgent._rrf_fusion(results_by_method, weights)

        # chunk_a RRF score: 0.5/(60+1) + 0.3/(60+1) = 0.8/61
        # chunk_b RRF score: 0.2/(60+1) = 0.2/61
        # After normalization (max = 0.8/61):
        # chunk_a: 1.0
        # chunk_b: (0.2/61) / (0.8/61) = 0.2/0.8 = 0.25
        assert len(fused) == 2
        assert fused[0].chunk_id == "chunk_a"
        assert fused[0].score == 1.0
        assert fused[1].chunk_id == "chunk_b"
        assert fused[1].score == round(0.25, 4)

    def test_rrf_fusion_rank_matters(self):
        """Higher rank (later position) produces lower RRF contribution."""
        # chunk_a at rank 0 in dense, chunk_b at rank 1 in dense
        # Both also appear in sparse at same rank
        dense = [_make_chunk("a", method="dense"), _make_chunk("b", method="dense")]
        sparse = [_make_chunk("a", method="sparse"), _make_chunk("b", method="sparse")]

        results_by_method = {"dense": dense, "sparse": sparse}
        weights = {"dense": 0.5, "sparse": 0.5}

        fused = RetrievalAgent._rrf_fusion(results_by_method, weights)

        # chunk_a: 0.5/(61) + 0.5/(61) = 1.0/61
        # chunk_b: 0.5/(62) + 0.5/(62) = 1.0/62
        # chunk_a score > chunk_b score
        assert fused[0].chunk_id == "a"
        assert fused[1].chunk_id == "b"
        assert fused[0].score > fused[1].score


# --- Weight Renormalization Tests ---


class TestWeightRenormalization:
    """Tests for weight renormalization when methods are unavailable."""

    def test_one_method_unavailable_preserves_ratio(self):
        """When one method (graph) is unavailable, remaining weights preserve ratio and sum to 1."""
        weights = RetrievalAgent._renormalize_weights(
            DEFAULT_WEIGHTS, ["dense", "sparse"]
        )
        # Original: dense=0.5, sparse=0.2. Total available = 0.7
        # Renormalized: dense=0.5/0.7, sparse=0.2/0.7
        expected_dense = 0.5 / 0.7
        expected_sparse = 0.2 / 0.7

        assert abs(weights["dense"] - expected_dense) < 1e-10
        assert abs(weights["sparse"] - expected_sparse) < 1e-10
        assert abs(sum(weights.values()) - 1.0) < 1e-10
        # Ratio preserved: dense/sparse = 0.5/0.2 = 2.5
        assert abs(weights["dense"] / weights["sparse"] - 2.5) < 1e-10

    def test_one_method_unavailable_sparse_down(self):
        """When sparse is unavailable, dense and graph renormalize."""
        weights = RetrievalAgent._renormalize_weights(
            DEFAULT_WEIGHTS, ["dense", "graph"]
        )
        # Original: dense=0.5, graph=0.3. Total = 0.8
        expected_dense = 0.5 / 0.8
        expected_graph = 0.3 / 0.8

        assert abs(weights["dense"] - expected_dense) < 1e-10
        assert abs(weights["graph"] - expected_graph) < 1e-10
        assert abs(sum(weights.values()) - 1.0) < 1e-10
        assert "sparse" not in weights

    def test_two_methods_unavailable_only_dense(self):
        """When sparse and graph are unavailable, dense gets weight 1.0."""
        weights = RetrievalAgent._renormalize_weights(
            DEFAULT_WEIGHTS, ["dense"]
        )
        assert abs(weights["dense"] - 1.0) < 1e-10
        assert len(weights) == 1
        assert abs(sum(weights.values()) - 1.0) < 1e-10

    def test_two_methods_unavailable_only_sparse(self):
        """When dense and graph are unavailable, sparse gets weight 1.0."""
        weights = RetrievalAgent._renormalize_weights(
            DEFAULT_WEIGHTS, ["sparse"]
        )
        assert abs(weights["sparse"] - 1.0) < 1e-10
        assert len(weights) == 1

    def test_two_methods_unavailable_only_graph(self):
        """When dense and sparse are unavailable, graph gets weight 1.0."""
        weights = RetrievalAgent._renormalize_weights(
            DEFAULT_WEIGHTS, ["graph"]
        )
        assert abs(weights["graph"] - 1.0) < 1e-10
        assert len(weights) == 1

    def test_all_methods_available_weights_unchanged(self):
        """When all methods are available, weights are returned as-is (already sum to 1)."""
        weights = RetrievalAgent._renormalize_weights(
            DEFAULT_WEIGHTS, ["dense", "sparse", "graph"]
        )
        assert abs(weights["dense"] - 0.5) < 1e-10
        assert abs(weights["sparse"] - 0.2) < 1e-10
        assert abs(weights["graph"] - 0.3) < 1e-10
        assert abs(sum(weights.values()) - 1.0) < 1e-10


# --- All Items in Fused Output ---


class TestFusedOutputCompleteness:
    """Tests that all items from all lists appear in fused output."""

    def test_all_unique_items_appear_in_fused_output(self):
        """Every unique chunk across all methods appears in fused results (up to top-k)."""
        # 5 unique in dense, 5 unique in sparse, 5 unique in graph = 15 total
        dense = _make_chunks("d", 5, "dense")
        sparse = _make_chunks("s", 5, "sparse")
        graph = _make_chunks("g", 5, "graph")

        results_by_method = {"dense": dense, "sparse": sparse, "graph": graph}
        weights = {"dense": 0.5, "sparse": 0.2, "graph": 0.3}

        fused = RetrievalAgent._rrf_fusion(results_by_method, weights)

        # All 15 unique chunks should appear (15 < TOP_K=20)
        fused_ids = {chunk.chunk_id for chunk in fused}
        all_input_ids = {c.chunk_id for c in dense + sparse + graph}
        assert fused_ids == all_input_ids

    def test_overlapping_items_appear_once(self):
        """Chunks appearing in multiple methods appear exactly once in fused output."""
        # "common" appears in all 3 methods
        dense = [_make_chunk("common", method="dense"), _make_chunk("d1", method="dense")]
        sparse = [_make_chunk("common", method="sparse"), _make_chunk("s1", method="sparse")]
        graph = [_make_chunk("common", method="graph"), _make_chunk("g1", method="graph")]

        results_by_method = {"dense": dense, "sparse": sparse, "graph": graph}
        weights = {"dense": 0.5, "sparse": 0.2, "graph": 0.3}

        fused = RetrievalAgent._rrf_fusion(results_by_method, weights)

        # "common" appears once, plus d1, s1, g1 = 4 total
        fused_ids = [chunk.chunk_id for chunk in fused]
        assert fused_ids.count("common") == 1
        assert len(fused) == 4  # common + d1 + s1 + g1

    def test_more_than_top_k_items_caps_at_top_k(self):
        """When total unique items exceed TOP_K, output is capped at TOP_K."""
        # 20 unique per method, all different = 60 unique total
        dense = _make_chunks("d", 20, "dense")
        sparse = _make_chunks("s", 20, "sparse")
        graph = _make_chunks("g", 20, "graph")

        results_by_method = {"dense": dense, "sparse": sparse, "graph": graph}
        weights = {"dense": 0.5, "sparse": 0.2, "graph": 0.3}

        fused = RetrievalAgent._rrf_fusion(results_by_method, weights)

        assert len(fused) == TOP_K  # capped at 20


# --- Output Sorted by Descending Score ---


class TestFusedOutputSorting:
    """Tests that output is sorted by descending RRF score."""

    def test_output_sorted_descending(self):
        """Fused results are sorted in strictly descending score order."""
        dense = _make_chunks("d", 10, "dense")
        sparse = _make_chunks("s", 10, "sparse")
        graph = _make_chunks("g", 10, "graph")

        results_by_method = {"dense": dense, "sparse": sparse, "graph": graph}
        weights = {"dense": 0.5, "sparse": 0.2, "graph": 0.3}

        fused = RetrievalAgent._rrf_fusion(results_by_method, weights)

        scores = [chunk.score for chunk in fused]
        assert scores == sorted(scores, reverse=True)

    def test_first_item_has_score_one(self):
        """First fused result always has normalized score of 1.0."""
        dense = _make_chunks("d", 5, "dense")
        sparse = _make_chunks("s", 5, "sparse")

        results_by_method = {"dense": dense, "sparse": sparse}
        weights = {"dense": 0.7, "sparse": 0.3}

        fused = RetrievalAgent._rrf_fusion(results_by_method, weights)

        assert fused[0].score == 1.0

    def test_all_scores_in_valid_range(self):
        """All fused scores are in range [0.0, 1.0]."""
        dense = _make_chunks("d", 20, "dense")
        sparse = _make_chunks("s", 20, "sparse")
        graph = _make_chunks("g", 20, "graph")

        results_by_method = {"dense": dense, "sparse": sparse, "graph": graph}
        weights = {"dense": 0.5, "sparse": 0.2, "graph": 0.3}

        fused = RetrievalAgent._rrf_fusion(results_by_method, weights)

        for chunk in fused:
            assert 0.0 <= chunk.score <= 1.0

    def test_retrieval_method_set_to_hybrid(self):
        """All fused chunks have retrieval_method='hybrid'."""
        dense = _make_chunks("d", 3, "dense")
        sparse = _make_chunks("s", 3, "sparse")

        results_by_method = {"dense": dense, "sparse": sparse}
        weights = {"dense": 0.6, "sparse": 0.4}

        fused = RetrievalAgent._rrf_fusion(results_by_method, weights)

        for chunk in fused:
            assert chunk.retrieval_method == "hybrid"


# --- Timeout Handling Tests ---


class TestTimeoutHandling:
    """Tests that methods exceeding 5s timeout are declared unavailable."""

    @pytest.mark.asyncio
    async def test_dense_timeout_declared_unavailable(self):
        """Dense search timing out results in degraded mode with sparse+graph."""
        # Embedding client times out (simulates > 5s)
        embedding_client = AsyncMock()
        embedding_client.post = AsyncMock(side_effect=asyncio.TimeoutError())

        chromadb_store = AsyncMock()

        # BM25 returns results
        bm25_index = AsyncMock()
        bm25_index.search = AsyncMock(return_value=[
            {"chunk_id": "s1", "document_id": "doc1", "text": "sparse text",
             "section_heading": "S1", "score": 0.8, "metadata": {}},
        ])

        # Graph client returns results
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

        results = await agent.retrieve("test query", "corr-timeout-1")

        # Should get results from sparse and graph only
        assert len(results) > 0
        chunk_ids = {r.chunk_id for r in results}
        assert "s1" in chunk_ids
        assert "g1" in chunk_ids

    @pytest.mark.asyncio
    async def test_graph_timeout_declared_unavailable(self):
        """Graph search timing out results in degraded mode with dense+sparse."""
        # Embedding client works
        embedding_client = AsyncMock()
        embed_response = MagicMock()
        embed_response.json.return_value = {"vector": [0.1] * 768, "tokens_used": 5}
        embed_response.raise_for_status = MagicMock()
        embedding_client.post = AsyncMock(return_value=embed_response)

        # ChromaDB works
        chromadb_store = AsyncMock()
        chromadb_store.search = AsyncMock(return_value=[
            {"chunk_id": "d1", "document_id": "doc1", "text": "dense text",
             "section_heading": "D1", "score": 0.9, "metadata": {}},
        ])

        # BM25 works
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

        results = await agent.retrieve("test query", "corr-timeout-2")

        assert len(results) > 0
        chunk_ids = {r.chunk_id for r in results}
        assert "d1" in chunk_ids
        assert "s1" in chunk_ids

    @pytest.mark.asyncio
    async def test_sparse_timeout_declared_unavailable(self):
        """Sparse search timing out results in degraded mode with dense+graph."""
        # Embedding client works
        embedding_client = AsyncMock()
        embed_response = MagicMock()
        embed_response.json.return_value = {"vector": [0.1] * 768, "tokens_used": 5}
        embed_response.raise_for_status = MagicMock()
        embedding_client.post = AsyncMock(return_value=embed_response)

        # ChromaDB works
        chromadb_store = AsyncMock()
        chromadb_store.search = AsyncMock(return_value=[
            {"chunk_id": "d1", "document_id": "doc1", "text": "dense text",
             "section_heading": "D1", "score": 0.9, "metadata": {}},
        ])

        # BM25 throws exception (simulates timeout)
        bm25_index = AsyncMock()
        bm25_index.search = AsyncMock(side_effect=asyncio.TimeoutError())

        # Graph client works
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

        results = await agent.retrieve("test query", "corr-timeout-3")

        assert len(results) > 0
        chunk_ids = {r.chunk_id for r in results}
        assert "d1" in chunk_ids
        assert "g1" in chunk_ids

    @pytest.mark.asyncio
    async def test_all_methods_timeout_raises_error(self):
        """When all 3 methods time out, raises AllRetrievalMethodsUnavailableError."""
        embedding_client = AsyncMock()
        embedding_client.post = AsyncMock(side_effect=asyncio.TimeoutError())

        chromadb_store = AsyncMock()
        bm25_index = AsyncMock()
        bm25_index.search = AsyncMock(side_effect=asyncio.TimeoutError())

        graph_client = AsyncMock()
        graph_client.post = AsyncMock(side_effect=asyncio.TimeoutError())

        agent = RetrievalAgent(
            embedding_client=embedding_client,
            graph_client=graph_client,
            chromadb_store=chromadb_store,
            bm25_index=bm25_index,
        )

        with pytest.raises(AllRetrievalMethodsUnavailableError):
            await agent.retrieve("test query", "corr-all-timeout")

    @pytest.mark.asyncio
    async def test_circuit_breaker_open_declared_unavailable(self):
        """CircuitBreakerOpenError on a method declares it unavailable."""
        from service_client import CircuitBreakerOpenError

        embedding_client = AsyncMock()
        embedding_client.post = AsyncMock(
            side_effect=CircuitBreakerOpenError(
                service_name="embedding-service", reset_timeout=30.0
            )
        )

        chromadb_store = AsyncMock()

        # BM25 works
        bm25_index = AsyncMock()
        bm25_index.search = AsyncMock(return_value=[
            {"chunk_id": "s1", "document_id": "doc1", "text": "sparse text",
             "section_heading": "S1", "score": 0.8, "metadata": {}},
        ])

        # Graph works
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

        results = await agent.retrieve("test query", "corr-cb-open")

        # Dense unavailable (circuit open), sparse + graph work
        assert len(results) > 0
        chunk_ids = {r.chunk_id for r in results}
        assert "s1" in chunk_ids
        assert "g1" in chunk_ids
