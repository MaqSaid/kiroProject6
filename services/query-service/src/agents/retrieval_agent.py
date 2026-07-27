"""Retrieval Agent — hybrid search with RRF fusion.

Executes dense (Embedding Service + ChromaDB), sparse (BM25), and graph
(Graph Service /traverse) search in parallel with 5s timeout each, then
fuses results using Reciprocal Rank Fusion with weight renormalization.

Requirements: 4.1, 10.1, 10.2, 10.3, 10.4
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

import structlog

from domain_models.core import ScoredChunk
from service_client import CircuitBreakerOpenError, MaxRetriesExceededError, ResilientClient

from src.agents.prompt_loader import load_prompt
from src.infrastructure.bm25_index import BM25Index
from src.infrastructure.chromadb_store import ChromaDBStore

logger = structlog.get_logger(__name__)

# RRF parameters
RRF_K = 60
DEFAULT_WEIGHTS: dict[str, float] = {"dense": 0.5, "sparse": 0.2, "graph": 0.3}

# Cross-reference patterns that boost graph weight
CROSS_REF_KEYWORDS = {"AMENDS", "REFERENCES", "IMPLEMENTS"}
SECTION_PATTERNS = [
    re.compile(r"Section\s+\d+", re.IGNORECASE),
    re.compile(r"s\.\d+", re.IGNORECASE),
    re.compile(r"Part\s+\d+\s+Division\s+\d+", re.IGNORECASE),
]

# Adjusted weights when cross-reference is detected
CROSS_REF_WEIGHTS: dict[str, float] = {"dense": 0.3, "sparse": 0.2, "graph": 0.5}

# Search timeout in seconds
SEARCH_TIMEOUT = 5.0
TOP_K = 20


class AllRetrievalMethodsUnavailableError(Exception):
    """Raised when all three retrieval methods are unavailable."""

    pass


class RetrievalAgent:
    """Executes hybrid search: dense + sparse + graph with RRF fusion.

    Orchestrates parallel search across three methods:
    - Dense: Embedding Service (vector) + ChromaDB (similarity search)
    - Sparse: Local BM25 in-memory index
    - Graph: Graph Service /traverse endpoint

    Uses Reciprocal Rank Fusion (k=60) to combine results with
    configurable weights and graceful degradation.

    Loads its system prompt at initialization; raises ConfigurationError
    if the prompt is missing or empty (Requirement 4.1, 4.8).
    """

    def __init__(
        self,
        embedding_client: ResilientClient | None = None,
        graph_client: ResilientClient | None = None,
        chromadb_store: ChromaDBStore | None = None,
        bm25_index: BM25Index | None = None,
        system_prompt: str | None = None,
    ) -> None:
        self._embedding_client = embedding_client
        self._graph_client = graph_client
        self._chromadb_store = chromadb_store
        self._bm25_index = bm25_index
        # Load system prompt from file if not provided directly
        self._system_prompt = system_prompt or load_prompt("retrieval_agent")

    @property
    def system_prompt(self) -> str:
        """Return the loaded system prompt for this agent."""
        return self._system_prompt

    async def retrieve(self, query: str, correlation_id: str) -> list[ScoredChunk]:
        """Retrieve relevant chunks using hybrid search with RRF fusion.

        Executes dense, sparse, and graph search in parallel (5s timeout each),
        then fuses results using RRF with weight renormalization for unavailable
        methods.

        Args:
            query: The user's natural language query.
            correlation_id: Request correlation ID for tracing.

        Returns:
            Top 20 fused and scored chunks.

        Raises:
            AllRetrievalMethodsUnavailableError: If all methods fail.
        """
        logger.info(
            "retrieval_agent.retrieve.start",
            query=query[:100],
            correlation_id=correlation_id,
        )

        # Determine base weights (cross-reference detection)
        base_weights = self._select_weights(query)

        # Execute all 3 methods in parallel with 5s timeout each
        results_by_method: dict[str, list[ScoredChunk]] = {}
        available_methods: list[str] = []
        degraded_methods: list[dict[str, str]] = []

        tasks = {
            "dense": self._dense_search(query, correlation_id),
            "sparse": self._sparse_search(query),
            "graph": self._graph_search(query, correlation_id),
        }

        # Gather all tasks with individual timeouts
        gathered = await asyncio.gather(
            asyncio.wait_for(tasks["dense"], timeout=SEARCH_TIMEOUT),
            asyncio.wait_for(tasks["sparse"], timeout=SEARCH_TIMEOUT),
            asyncio.wait_for(tasks["graph"], timeout=SEARCH_TIMEOUT),
            return_exceptions=True,
        )

        method_names = ["dense", "sparse", "graph"]
        for method_name, result in zip(method_names, gathered):
            if isinstance(result, BaseException):
                error_type = type(result).__name__
                error_msg = str(result)
                degraded_methods.append(
                    {"method": method_name, "error_type": error_type, "error": error_msg}
                )
                logger.warning(
                    "search_method_unavailable",
                    method=method_name,
                    error_type=error_type,
                    error=error_msg,
                    correlation_id=correlation_id,
                )
            else:
                results_by_method[method_name] = result
                available_methods.append(method_name)

        # Log degradation summary
        if degraded_methods:
            logger.warning(
                "retrieval_agent.degraded",
                unavailable_methods=[d["method"] for d in degraded_methods],
                available_methods=available_methods,
                degradation_details=degraded_methods,
                correlation_id=correlation_id,
            )

        # If no methods available, raise
        if not available_methods:
            logger.error(
                "retrieval_agent.all_methods_unavailable",
                correlation_id=correlation_id,
            )
            raise AllRetrievalMethodsUnavailableError(
                "All retrieval methods (dense, sparse, graph) are unavailable"
            )

        # Renormalize weights for available methods
        weights = self._renormalize_weights(base_weights, available_methods)

        # RRF fusion
        fused = self._rrf_fusion(results_by_method, weights)

        logger.info(
            "retrieval_agent.retrieve.complete",
            available_methods=available_methods,
            result_count=len(fused),
            correlation_id=correlation_id,
        )

        return fused

    def _select_weights(self, query: str) -> dict[str, float]:
        """Select base weights based on query content.

        Cross-reference queries get boosted graph weight.
        """
        # Check for cross-reference keywords
        query_upper = query.upper()
        for keyword in CROSS_REF_KEYWORDS:
            if keyword in query_upper:
                return CROSS_REF_WEIGHTS.copy()

        # Check for section reference patterns
        for pattern in SECTION_PATTERNS:
            if pattern.search(query):
                return CROSS_REF_WEIGHTS.copy()

        return DEFAULT_WEIGHTS.copy()

    @staticmethod
    def _renormalize_weights(
        base_weights: dict[str, float], available_methods: list[str]
    ) -> dict[str, float]:
        """Renormalize weights proportionally for available methods.

        Preserves the ratio between available methods and ensures
        weights sum to 1.0.

        Args:
            base_weights: The base weight configuration.
            available_methods: List of method names that returned results.

        Returns:
            Renormalized weights summing to 1.0.
        """
        total_weight = sum(base_weights[m] for m in available_methods)
        if total_weight == 0:
            # Edge case: all available methods had 0 weight
            equal_weight = 1.0 / len(available_methods)
            return {m: equal_weight for m in available_methods}
        return {m: base_weights[m] / total_weight for m in available_methods}

    @staticmethod
    def _rrf_fusion(
        results_by_method: dict[str, list[ScoredChunk]],
        weights: dict[str, float],
    ) -> list[ScoredChunk]:
        """Fuse results using Reciprocal Rank Fusion.

        RRF score for a chunk = sum over methods of:
            weight[method] / (RRF_K + rank + 1)

        where rank is 0-indexed position in the method's result list.

        Args:
            results_by_method: Results keyed by method name.
            weights: Renormalized weights for each method.

        Returns:
            Top 20 chunks sorted by fused RRF score, with score normalized to [0, 1].
        """
        scores: dict[str, float] = {}
        chunk_map: dict[str, ScoredChunk] = {}

        for method, results in results_by_method.items():
            method_weight = weights.get(method, 0.0)
            for rank, chunk in enumerate(results):
                chunk_id = chunk.chunk_id
                rrf_score = method_weight / (RRF_K + rank + 1)
                scores[chunk_id] = scores.get(chunk_id, 0.0) + rrf_score

                # Keep the chunk with highest individual RRF contribution
                if chunk_id not in chunk_map:
                    chunk_map[chunk_id] = chunk

        # Sort by fused score descending
        sorted_ids = sorted(scores.keys(), key=lambda cid: scores[cid], reverse=True)

        # Take top 20 and normalize scores to [0, 1]
        top_ids = sorted_ids[:TOP_K]
        if not top_ids:
            return []

        max_score = scores[top_ids[0]]

        fused_chunks: list[ScoredChunk] = []
        for chunk_id in top_ids:
            original = chunk_map[chunk_id]
            # Normalize score to [0, 1]
            if max_score > 0:
                normalized_score = scores[chunk_id] / max_score
            else:
                normalized_score = 0.0
            # Clamp to valid range
            normalized_score = max(0.0, min(1.0, normalized_score))

            fused_chunks.append(
                ScoredChunk(
                    chunk_id=original.chunk_id,
                    document_id=original.document_id,
                    text=original.text,
                    section_heading=original.section_heading,
                    score=round(normalized_score, 4),
                    retrieval_method="hybrid",
                    metadata=original.metadata,
                )
            )

        return fused_chunks

    async def _dense_search(
        self, query: str, correlation_id: str
    ) -> list[ScoredChunk]:
        """Execute dense search: embed query then search ChromaDB.

        Args:
            query: Query text to embed and search.
            correlation_id: Correlation ID for tracing.

        Returns:
            Top 20 chunks from vector similarity search.

        Raises:
            CircuitBreakerOpenError: If Embedding Service circuit is open.
            asyncio.TimeoutError: If embedding or search exceeds timeout.
            Exception: On other failures.
        """
        if self._embedding_client is None or self._chromadb_store is None:
            logger.warning(
                "dense_search.not_configured",
                has_embedding_client=self._embedding_client is not None,
                has_chromadb_store=self._chromadb_store is not None,
                correlation_id=correlation_id,
            )
            return []

        # Step 1: Get embedding vector from Embedding Service
        response = await self._embedding_client.post(
            "/embed",
            correlation_id=correlation_id,
            json={"text": query},
        )
        response.raise_for_status()
        embed_data = response.json()
        vector = embed_data["vector"]

        # Step 2: Query ChromaDB with vector
        raw_results = await self._chromadb_store.search(vector=vector, top_k=TOP_K)

        # Convert raw results to ScoredChunk
        chunks: list[ScoredChunk] = []
        for result in raw_results:
            chunks.append(
                ScoredChunk(
                    chunk_id=result.get("chunk_id", result.get("id", "")),
                    document_id=result.get("document_id", ""),
                    text=result.get("text", ""),
                    section_heading=result.get("section_heading", ""),
                    score=float(result.get("score", 0.0)),
                    retrieval_method="dense",
                    metadata=result.get("metadata", {}),
                )
            )

        return chunks[:TOP_K]

    async def _sparse_search(self, query: str) -> list[ScoredChunk]:
        """Execute sparse BM25 keyword search.

        Args:
            query: Query text for keyword matching.

        Returns:
            Top 20 chunks from BM25 search.
        """
        if self._bm25_index is None:
            logger.warning("sparse_search.not_configured")
            return []

        raw_results = await self._bm25_index.search(query=query, top_k=TOP_K)

        # Convert raw results to ScoredChunk
        chunks: list[ScoredChunk] = []
        for result in raw_results:
            chunks.append(
                ScoredChunk(
                    chunk_id=result.get("chunk_id", result.get("id", "")),
                    document_id=result.get("document_id", ""),
                    text=result.get("text", ""),
                    section_heading=result.get("section_heading", ""),
                    score=float(result.get("score", 0.0)),
                    retrieval_method="sparse",
                    metadata=result.get("metadata", {}),
                )
            )

        return chunks[:TOP_K]

    async def _graph_search(
        self, query: str, correlation_id: str
    ) -> list[ScoredChunk]:
        """Execute graph traversal search via Graph Service.

        Args:
            query: Query text for graph traversal.
            correlation_id: Correlation ID for tracing.

        Returns:
            Top 20 chunks from graph traversal.

        Raises:
            CircuitBreakerOpenError: If Graph Service circuit is open.
            asyncio.TimeoutError: If traversal exceeds timeout.
            Exception: On other failures.
        """
        if self._graph_client is None:
            logger.warning(
                "graph_search.not_configured",
                correlation_id=correlation_id,
            )
            return []

        # Call Graph Service POST /traverse
        response = await self._graph_client.post(
            "/traverse",
            correlation_id=correlation_id,
            json={"query": query, "max_hops": 2},
        )
        response.raise_for_status()
        traverse_data = response.json()

        # Parse results from TraverseResponse format
        raw_results = traverse_data.get("results", [])
        chunks: list[ScoredChunk] = []
        for result in raw_results:
            chunks.append(
                ScoredChunk(
                    chunk_id=result.get("chunk_id", ""),
                    document_id=result.get("document_id", ""),
                    text=result.get("text", ""),
                    section_heading=result.get("section_heading", ""),
                    score=float(result.get("score", 0.0)),
                    retrieval_method="graph",
                    metadata=result.get("metadata", {}),
                )
            )

        return chunks[:TOP_K]
