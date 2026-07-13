"""Retrieval Service — hybrid search with RRF fusion and reranking.

Executes dense + sparse + graph search in parallel, fuses via RRF,
and reranks the top candidates using a cross-encoder.
"""

from __future__ import annotations

import asyncio
import time

import structlog

from src.domain.models.entities import ScoredChunk
from src.domain.models.enums import RRFWeights
from src.ports.embedding import EmbeddingPort
from src.ports.graph_store import GraphStorePort
from src.ports.reranker import RerankerPort
from src.ports.sparse_index import SparseIndexPort
from src.ports.vector_store import VectorStorePort

logger = structlog.get_logger(__name__)

RRF_K = 60
DEFAULT_TOP_K = 10
DEFAULT_RERANK_CANDIDATES = 20
DEFAULT_FINAL_TOP_N = 5


class RetrievalService:
    """Hybrid retrieval with three-way search, RRF fusion, and reranking."""

    def __init__(
        self,
        embedding_port: EmbeddingPort,
        vector_store: VectorStorePort,
        sparse_index: SparseIndexPort,
        graph_store: GraphStorePort,
        reranker: RerankerPort,
    ) -> None:
        self._embedding = embedding_port
        self._vector_store = vector_store
        self._sparse_index = sparse_index
        self._graph_store = graph_store
        self._reranker = reranker
        logger.info("retrieval_service.initialized")

    async def retrieve(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        rrf_weights: RRFWeights | None = None,
        include_graph: bool = True,
        correlation_id: str = "",
    ) -> list[ScoredChunk]:
        """Execute hybrid search and return reranked results."""
        if rrf_weights is None:
            rrf_weights = RRFWeights()

        start_time = time.perf_counter()
        degraded_modes: list[str] = []

        # Embed query
        try:
            query_vector = await self._embedding.embed_single(query)
        except Exception as e:
            logger.error("retrieval_service.embed_failed", error=str(e))
            return []

        # Parallel search
        dense, sparse, graph = await self._parallel_search(
            query, query_vector, top_k, include_graph, degraded_modes
        )

        # RRF Fusion
        fused = self._reciprocal_rank_fusion(dense, sparse, graph, rrf_weights)

        # Rerank
        candidates = fused[:DEFAULT_RERANK_CANDIDATES]
        if candidates:
            try:
                reranked = await self._reranker.rerank(query, candidates, DEFAULT_FINAL_TOP_N)
            except Exception as e:
                logger.warning("retrieval_service.rerank_failed", error=str(e))
                reranked = candidates[:DEFAULT_FINAL_TOP_N]
                degraded_modes.append("reranker_unavailable")
        else:
            reranked = []

        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            "retrieval_service.retrieve.complete",
            dense_count=len(dense),
            sparse_count=len(sparse),
            graph_count=len(graph),
            fused_count=len(fused),
            final_count=len(reranked),
            degraded_modes=degraded_modes,
            duration_ms=round(duration_ms, 2),
            correlation_id=correlation_id,
        )

        return reranked

    async def _parallel_search(
        self,
        query: str,
        query_vector: list[float],
        top_k: int,
        include_graph: bool,
        degraded_modes: list[str],
    ) -> tuple[list[ScoredChunk], list[ScoredChunk], list[ScoredChunk]]:
        """Execute searches in parallel with graceful degradation."""

        async def dense_search() -> list[ScoredChunk]:
            try:
                return await self._vector_store.search(query_vector, top_k)
            except Exception as e:
                logger.error("retrieval_service.dense_failed", error=str(e))
                degraded_modes.append("dense_unavailable")
                return []

        async def sparse_search() -> list[ScoredChunk]:
            try:
                return await self._sparse_index.search(query, top_k)
            except Exception as e:
                logger.warning("retrieval_service.sparse_failed", error=str(e))
                degraded_modes.append("sparse_unavailable")
                return []

        async def graph_search() -> list[ScoredChunk]:
            if not include_graph:
                return []
            try:
                return await self._graph_store.traverse(query, max_hops=2)
            except Exception as e:
                logger.warning("retrieval_service.graph_failed", error=str(e))
                degraded_modes.append("graph_unavailable")
                return []

        return await asyncio.gather(dense_search(), sparse_search(), graph_search())

    def _reciprocal_rank_fusion(
        self,
        dense: list[ScoredChunk],
        sparse: list[ScoredChunk],
        graph: list[ScoredChunk],
        weights: RRFWeights,
    ) -> list[ScoredChunk]:
        """Combine ranked lists using weighted RRF: score(d) = Σ(w_i / (k + rank_i))."""
        scores: dict[str, float] = {}
        chunk_map: dict[str, ScoredChunk] = {}

        for rank, sc in enumerate(dense):
            cid = str(sc.chunk.id)
            scores[cid] = scores.get(cid, 0.0) + weights.dense / (RRF_K + rank + 1)
            if cid not in chunk_map:
                chunk_map[cid] = sc

        for rank, sc in enumerate(sparse):
            cid = str(sc.chunk.id)
            scores[cid] = scores.get(cid, 0.0) + weights.sparse / (RRF_K + rank + 1)
            if cid not in chunk_map:
                chunk_map[cid] = sc

        for rank, sc in enumerate(graph):
            cid = str(sc.chunk.id)
            scores[cid] = scores.get(cid, 0.0) + weights.graph / (RRF_K + rank + 1)
            if cid not in chunk_map:
                chunk_map[cid] = sc

        sorted_ids = sorted(scores.keys(), key=lambda c: scores[c], reverse=True)

        return [
            ScoredChunk(chunk=chunk_map[cid].chunk, score=scores[cid], retrieval_method="fused")
            for cid in sorted_ids
        ]
