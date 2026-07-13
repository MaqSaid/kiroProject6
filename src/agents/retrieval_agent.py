"""Retrieval Agent — orchestrates hybrid search across dense, sparse, and graph stores.

This agent intelligently decides which retrieval paths to use based on the query,
performs parallel searches, fuses results via Reciprocal Rank Fusion (RRF),
and reranks the final candidates.

It wraps the VectorStorePort, SparseIndexPort, GraphStorePort, EmbeddingPort,
and RerankerPort as Strands tools.
"""

from __future__ import annotations

from typing import Any

import structlog
from strands import Agent, tool

from src.agents.base import AgentConfig, create_agent
from src.domain.models.entities import ScoredChunk
from src.ports.embedding import EmbeddingPort
from src.ports.graph_store import GraphStorePort
from src.ports.reranker import RerankerPort
from src.ports.sparse_index import SparseIndexPort
from src.ports.vector_store import VectorStorePort

logger = structlog.get_logger(__name__)

# RRF smoothing constant
RRF_K = 60


def _build_retrieval_tools(
    embedding_port: EmbeddingPort,
    vector_store: VectorStorePort,
    sparse_index: SparseIndexPort,
    graph_store: GraphStorePort,
    reranker: RerankerPort,
) -> list[Any]:
    """Build Strands tool functions that wrap port operations.

    Each tool is a closure over the injected port, making them
    usable by the Strands agent loop.
    """

    @tool
    def dense_search(query: str, top_k: int = 10) -> str:
        """Search the vector store using dense embeddings for semantically similar chunks.

        Use this for queries that require semantic understanding beyond keyword matching.
        Returns chunks ranked by cosine similarity to the query embedding.

        Args:
            query: The search query text.
            top_k: Maximum number of results to return (default: 10).
        """
        import asyncio

        async def _run() -> list[dict[str, Any]]:
            query_vector = await embedding_port.embed_single(query)
            results = await vector_store.search(query_vector, top_k)
            return [
                {
                    "chunk_id": str(chunk.chunk.id),
                    "document_id": str(chunk.chunk.document_id),
                    "text": chunk.chunk.text[:500],
                    "score": chunk.score,
                    "section": chunk.chunk.section_heading,
                    "method": "dense",
                }
                for chunk in results
            ]

        results = asyncio.run(_run())
        return str(results)

    @tool
    def sparse_search(query: str, top_k: int = 10) -> str:
        """Search using BM25 keyword matching for exact term relevance.

        Use this for queries with specific terms, names, or technical keywords
        that benefit from exact lexical matching rather than semantic similarity.

        Args:
            query: The search query text.
            top_k: Maximum number of results to return (default: 10).
        """
        import asyncio

        async def _run() -> list[dict[str, Any]]:
            results = await sparse_index.search(query, top_k)
            return [
                {
                    "chunk_id": str(chunk.chunk.id),
                    "document_id": str(chunk.chunk.document_id),
                    "text": chunk.chunk.text[:500],
                    "score": chunk.score,
                    "section": chunk.chunk.section_heading,
                    "method": "sparse",
                }
                for chunk in results
            ]

        results = asyncio.run(_run())
        return str(results)

    @tool
    def graph_search(query: str, max_hops: int = 2) -> str:
        """Traverse the knowledge graph to find entity-related chunks.

        Use this for queries about relationships between concepts, entities,
        or when the answer requires connecting information across documents.

        Args:
            query: The search query text.
            max_hops: Maximum relationship traversal depth (default: 2).
        """
        import asyncio

        async def _run() -> list[dict[str, Any]]:
            results = await graph_store.traverse(query, max_hops)
            return [
                {
                    "chunk_id": str(chunk.chunk.id),
                    "document_id": str(chunk.chunk.document_id),
                    "text": chunk.chunk.text[:500],
                    "score": chunk.score,
                    "section": chunk.chunk.section_heading,
                    "method": "graph",
                }
                for chunk in results
            ]

        results = asyncio.run(_run())
        return str(results)

    @tool
    def fuse_results(
        dense_results: str,
        sparse_results: str,
        graph_results: str,
        dense_weight: float = 0.5,
        sparse_weight: float = 0.2,
        graph_weight: float = 0.3,
    ) -> str:
        """Fuse results from multiple retrieval methods using Reciprocal Rank Fusion (RRF).

        Combines ranked lists from dense, sparse, and graph search into a single
        unified ranking. Each result's score is calculated as:
            score(d) = sum(weight_i / (k + rank_i(d)))

        Args:
            dense_results: JSON string of dense search results.
            sparse_results: JSON string of sparse search results.
            graph_results: JSON string of graph search results.
            dense_weight: Weight for dense results (default: 0.5).
            sparse_weight: Weight for sparse results (default: 0.2).
            graph_weight: Weight for graph results (default: 0.3).
        """
        import ast

        try:
            dense_list = ast.literal_eval(dense_results) if dense_results else []
            sparse_list = ast.literal_eval(sparse_results) if sparse_results else []
            graph_list = ast.literal_eval(graph_results) if graph_results else []
        except (ValueError, SyntaxError):
            return "Error: Could not parse result lists for fusion."

        # Build RRF scores
        scores: dict[str, float] = {}
        metadata: dict[str, dict[str, Any]] = {}

        for rank, item in enumerate(dense_list):
            chunk_id = item["chunk_id"]
            scores[chunk_id] = scores.get(chunk_id, 0.0) + dense_weight / (RRF_K + rank + 1)
            metadata[chunk_id] = item

        for rank, item in enumerate(sparse_list):
            chunk_id = item["chunk_id"]
            scores[chunk_id] = scores.get(chunk_id, 0.0) + sparse_weight / (RRF_K + rank + 1)
            if chunk_id not in metadata:
                metadata[chunk_id] = item

        for rank, item in enumerate(graph_list):
            chunk_id = item["chunk_id"]
            scores[chunk_id] = scores.get(chunk_id, 0.0) + graph_weight / (RRF_K + rank + 1)
            if chunk_id not in metadata:
                metadata[chunk_id] = item

        # Sort by fused score
        sorted_chunks = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        fused = []
        for chunk_id, score in sorted_chunks[:20]:
            entry = metadata[chunk_id].copy()
            entry["fused_score"] = round(score, 6)
            entry["method"] = "fused"
            fused.append(entry)

        return str(fused)

    @tool
    def rerank_results(query: str, candidates: str, top_n: int = 5) -> str:
        """Rerank fused candidates using a cross-encoder model for final ordering.

        Takes the top candidates from RRF fusion and applies a more expensive
        but accurate cross-encoder reranking to select the final top-N results.

        Args:
            query: The original search query.
            candidates: JSON string of fused candidate results.
            top_n: Number of top results to return after reranking (default: 5).
        """
        import ast
        import asyncio
        import uuid

        from src.domain.models.entities import Chunk
        from src.domain.models.enums import ChunkingStrategy

        try:
            candidate_list = ast.literal_eval(candidates) if candidates else []
        except (ValueError, SyntaxError):
            return "Error: Could not parse candidates for reranking."

        # Convert to ScoredChunk objects for the reranker port
        scored_chunks = []
        for item in candidate_list:
            chunk = Chunk(
                id=uuid.UUID(item["chunk_id"]),
                document_id=uuid.UUID(item["document_id"]),
                index=0,
                text=item.get("text", ""),
                section_heading=item.get("section", ""),
                strategy=ChunkingStrategy.FIXED_SIZE,
                char_count=len(item.get("text", "")),
            )
            scored_chunks.append(
                ScoredChunk(
                    chunk=chunk,
                    score=item.get("fused_score", 0.0),
                    retrieval_method=item.get("method", "fused"),
                )
            )

        async def _run() -> list[dict[str, Any]]:
            reranked = await reranker.rerank(query, scored_chunks, top_n)
            return [
                {
                    "chunk_id": str(sc.chunk.id),
                    "document_id": str(sc.chunk.document_id),
                    "text": sc.chunk.text[:500],
                    "score": sc.score,
                    "section": sc.chunk.section_heading,
                    "method": "reranked",
                }
                for sc in reranked
            ]

        results = asyncio.run(_run())
        return str(results)

    return [dense_search, sparse_search, graph_search, fuse_results, rerank_results]


RETRIEVAL_SYSTEM_PROMPT = """You are a Retrieval Agent for a RAG (Retrieval-Augmented Generation) pipeline.

Your job is to find the most relevant document chunks for a given query using hybrid search.

## Retrieval Strategy

1. **Analyze the query** to determine the best search approach:
   - For semantic/conceptual queries → prioritize dense_search
   - For queries with specific terms/names → prioritize sparse_search
   - For relationship/entity queries → include graph_search
   - For most queries → use ALL three methods for comprehensive coverage

2. **Execute searches** using the appropriate tools. Always use at least dense_search and sparse_search.

3. **Fuse results** using the fuse_results tool with RRF. Use default weights unless the query type suggests otherwise:
   - Conceptual queries: dense_weight=0.6, sparse_weight=0.1, graph_weight=0.3
   - Keyword-heavy queries: dense_weight=0.3, sparse_weight=0.5, graph_weight=0.2
   - Relationship queries: dense_weight=0.3, sparse_weight=0.2, graph_weight=0.5

4. **Rerank** the fused results to get the final top-5 most relevant chunks.

## Output Format

After reranking, return the final results as a structured list. Include chunk_id, document_id, text preview, score, and section heading for each result.

## Important Rules

- ALWAYS run at least dense_search and sparse_search
- ALWAYS fuse results before reranking
- ALWAYS rerank before returning final results
- If any search method fails, continue with the others (graceful degradation)
- Never fabricate or modify chunk content
"""


def create_retrieval_agent(
    embedding_port: EmbeddingPort,
    vector_store: VectorStorePort,
    sparse_index: SparseIndexPort,
    graph_store: GraphStorePort,
    reranker: RerankerPort,
    config: AgentConfig | None = None,
) -> Agent:
    """Create a Retrieval Agent with hybrid search capabilities.

    Args:
        embedding_port: Port for generating query embeddings.
        vector_store: Port for dense vector search.
        sparse_index: Port for BM25 sparse search.
        graph_store: Port for knowledge graph traversal.
        reranker: Port for cross-encoder reranking.
        config: Optional agent configuration.

    Returns:
        A Strands Agent configured for hybrid retrieval.
    """
    tools = _build_retrieval_tools(
        embedding_port, vector_store, sparse_index, graph_store, reranker
    )

    agent = create_agent(
        tools=tools,
        system_prompt=RETRIEVAL_SYSTEM_PROMPT,
        config=config,
    )

    logger.info("retrieval_agent.created", tool_count=len(tools))
    return agent
